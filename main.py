import io
import string
import copy
import csv
import random
import time
import traceback
import colorama
import ua_generator
import web3.exceptions

from termcolor import cprint
from enum import Enum
from pathlib import Path
from datetime import datetime
from requests_toolbelt import MultipartEncoder
from eth_account.account import Account

from logger import Logger, get_telegram_bot_chat_id
from utils import *
from config import *
from vars import *

colorama.init()

date_path = datetime.now().strftime('%d-%m-%Y-%H-%M-%S')
results_path = 'results/' + date_path
logs_root = 'logs/'
logs_path = logs_root + date_path
Path(results_path).mkdir(parents=True, exist_ok=True)
Path(logs_path).mkdir(parents=True, exist_ok=True)

logger = Logger(to_console=True, to_file=True, default_file=f'{logs_path}/console_output.txt')

with open('files/english_words.txt', 'r', encoding='utf-8') as words_file:
    english_words = words_file.read().splitlines()


def parse_mint_link(link):
    link = link.strip()
    if link == '' or link[0] == '#':
        return None
    if link.startswith('custom'):
        chain = link.split(':')[1]
        token_id = 'custom'
        nft_info = link[7 + len(chain) + 1:]
        chain = ZORA_CHAINS_MAP[chain]
        if chain not in MINT_CHAINS:
            return None
        return chain, nft_info, token_id
    if MINT_ONLY_CUSTOM:
        return None
    if link.startswith('https://'):
        link = link[8:]
    if link.startswith('zora.co/collect/'):
        link = link[16:]
    chain, nft_info = tuple(link.split(':'))
    if '/' in nft_info:
        nft_address, token_id = tuple(nft_info.split('/'))
    else:
        nft_address, token_id = nft_info, None
    chain = ZORA_CHAINS_MAP[chain]
    if chain not in MINT_CHAINS:
        return None
    nft_address = Web3.to_checksum_address(nft_address)
    token_id = int(token_id) if token_id else None
    return chain, nft_address, token_id


def get_random_words(n: int):
    return [random.choice(english_words) for _ in range(n)]


def decimal_to_int(d, n):
    return int(d * (10 ** n))


def int_to_decimal(i, n):
    return i / (10 ** n)


def readable_amount_int(i, n, d=2):
    return round(int_to_decimal(i, n), d)


def wait_next_tx(x=1.0):
    time.sleep(random.uniform(NEXT_TX_MIN_WAIT_TIME, NEXT_TX_MAX_WAIT_TIME) * x)


def _delay(r, *args, **kwargs):
    time.sleep(random.uniform(1, 2))


address2ua = {}
auto_bridged_cnt_by_address = {}


def get_default_mint_fun_headers(address):
    if address not in address2ua:
        address2ua[address] = ua_generator.generate(device='desktop', browser='chrome')
    ua = address2ua[address]
    return {
        'authority': 'mint.fun',
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'origin': 'https://mint.fun',
        'pragma': 'no-cache',
        'referer': 'https://mint.fun/',
        'sec-ch-ua': f'"{ua.ch.brands[2:]}"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{ua.platform.title()}"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': ua.text,
    }


class RunnerException(Exception):

    def __init__(self, message, caused=None):
        super().__init__()
        self.message = message
        self.caused = caused

    def __str__(self):
        if self.caused:
            return self.message + ": " + str(self.caused)
        return self.message


class PendingException(Exception):

    def __init__(self, chain, tx_hash, action):
        super().__init__()
        self.chain = chain
        self.tx_hash = tx_hash
        self.action = action

    def __str__(self):
        return f'{self.action}, chain = {self.chain}, tx_hash = {self.tx_hash.hex()}'

    def get_tx_hash(self):
        return self.tx_hash.hex()


def handle_traceback(msg=''):
    trace = traceback.format_exc()
    logger.print(msg + '\n' + trace, filename=f'{logs_path}/tracebacks.log', to_console=False, store_tg=False)


def runner_func(msg):
    def decorator(func):
        @retry(tries=MAX_TRIES, delay=1.5, backoff=2, jitter=(0, 1), exceptions=RunnerException)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (PendingException, InsufficientFundsException):
                raise
            except RunnerException as e:
                raise RunnerException(msg, e)
            except Exception as e:
                handle_traceback(msg)
                raise RunnerException(msg, e)

        return wrapper

    return decorator


class Status(Enum):
    ALREADY = 1
    PENDING = 2
    SUCCESS = 3
    SUCCESS_WITH_EXISTED_COLLECTION = 4
    FAILED = 5


class Runner:

    def __init__(self, private_key, proxy):
        if proxy is not None and len(proxy) > 4 and proxy[:4] != 'http':
            proxy = 'http://' + proxy
        self.proxy = proxy

        self.http_proxies = {'http': self.proxy, 'https': self.proxy} if self.proxy and self.proxy != '' else {}

        self.w3s = {chain: get_w3(chain, proxy=self.proxy) for chain in INVOLVED_CHAINS}

        self.private_key = private_key
        self.address = Account().from_key(private_key).address

        self.with_mint_fun = MINT_WITH_MINT_FUN and self.check_mint_fun_pass()

    def w3(self, chain):
        return self.w3s[chain]

    def check_mint_fun_pass(self):
        contract = self.w3('Ethereum').eth.contract(MINT_FUN_PASS_ADDRESS, abi=MINT_FUN_PASS_ABI)
        return contract.functions.balanceOf(self.address).call() > 0

    def tx_verification(self, chain, tx_hash, action=None):
        action_print = action + ' - ' if action else ''
        logger.print(f'{action_print}Tx was sent')
        try:
            transaction_data = self.w3(chain).eth.wait_for_transaction_receipt(tx_hash)
            status = transaction_data.get('status')
            if status is not None and status == 1:
                logger.print(f'{action_print}Successful tx: {SCANS[chain]}/tx/{tx_hash.hex()}')
            else:
                raise RunnerException(f'{action_print}Tx status = {status}, chain = {chain}, tx_hash = {tx_hash.hex()}')
        except web3.exceptions.TimeExhausted:
            logger.print(f'{action_print} Tx in pending: {SCANS[chain]}/tx/{tx_hash.hex()}')
            raise PendingException(chain, tx_hash, action_print[:-3])

    def get_native_balance(self, chain):
        return self.w3(chain).eth.get_balance(self.address)

    def build_and_send_tx(self, w3, func, action, value=0, tx_change_func=None):
        return build_and_send_tx(w3, self.address, self.private_key, func, value, self.tx_verification, action,
                                 tx_change_func=tx_change_func)

    def wait_for_eth_gas_price(self, current_w3):
        w3 = self.w3('Ethereum')
        max_eth_gas_price = MAX_ETH_GAS_PRICE if get_chain(current_w3) == 'Ethereum' else MAX_ETH_GAS_PRICE_FOR_L2
        t = 0
        while w3.eth.gas_price > Web3.to_wei(max_eth_gas_price, 'gwei'):
            gas_price = int_to_decimal(w3.eth.gas_price, 9)
            gas_price = round(gas_price, 2)
            logger.print(f'Gas price is too high - {gas_price}. Waiting for {WAIT_GAS_TIME}s')
            t += WAIT_GAS_TIME
            if t >= TOTAL_WAIT_GAS_TIME:
                break
            time.sleep(WAIT_GAS_TIME)

        if w3.eth.gas_price > Web3.to_wei(max_eth_gas_price, 'gwei'):
            raise RunnerException('Gas price is too high')

    def wait_for_bridge(self, init_balance):
        t = 0
        while init_balance >= self.get_native_balance('Zora') and t < BRIDGE_WAIT_TIME:
            t += 20
            logger.print('Assets not bridged')
            time.sleep(20)

        if init_balance >= self.get_native_balance('Zora'):
            raise RunnerException('Bridge takes too long')

        logger.print('Assets bridged successfully')

    @runner_func('Bridge')
    def bridge(self):
        w3 = self.w3('Ethereum')

        contract = w3.eth.contract(ZORA_BRIDGE_ADDRESS, abi=ZORA_BRIDGE_ABI)

        balance = w3.eth.get_balance(self.address)
        balance = int_to_decimal(balance, NATIVE_DECIMALS)

        self.wait_for_eth_gas_price(w3)

        estimated_fee = 0.00033 * (int_to_decimal(w3.eth.gas_price, 9) / 6.2) * 2
        balance -= estimated_fee

        if balance < BRIDGE_AMOUNT[0] / 2:
            raise Exception('Low balance on Ethereum')

        amount = random.uniform(min(balance, BRIDGE_AMOUNT[0]), min(balance, BRIDGE_AMOUNT[1]))
        amount = round(amount, random.randint(4, 6))

        value = Web3.to_wei(amount, 'ether')

        self.build_and_send_tx(
            w3,
            contract.functions.depositTransaction(self.address, value, ZORA_BRIDGE_GAS_LIMIT, False, b''),
            value=value,
            action='Bridge'
        )

        return Status.SUCCESS

    def mint_fun_tx_change(self, tx):
        if self.with_mint_fun:
            tx['data'] = tx['data'] + MINT_FUN_DATA_SUFFIX

    def _mint_erc721(self, w3, nft_address, with_rewards=True):
        contract = w3.eth.contract(nft_address, abi=ZORA_ERC721_ABI)

        balance = contract.functions.balanceOf(self.address).call()
        if balance >= MAX_NFT_PER_ADDRESS:
            return Status.ALREADY, None

        price = contract.functions.salesConfig().call()[0]

        value = contract.functions.zoraFeeForAmount(1).call()[1] + price

        if with_rewards:
            args = (self.address, 1, '', MINT_REF_ADDRESS)
            func = contract.functions.mintWithRewards
        else:
            args = (1,)
            func = contract.functions.purchase

        tx_hash = self.build_and_send_tx(
            w3,
            func(*args),
            action='Mint ERC721',
            value=value,
            tx_change_func=self.mint_fun_tx_change,
        )

        return Status.SUCCESS, tx_hash

    @runner_func('Mint ERC721')
    def mint_erc721(self, w3, nft_address):
        try:
            return self._mint_erc721(w3, nft_address)
        except web3.exceptions.ContractLogicError as e:
            if 'execution reverted' in str(e):
                return self._mint_erc721(w3, nft_address, with_rewards=False)
            else:
                raise e

    def _mint_erc1155(self, w3, nft_address, token_id, with_rewards=True):
        contract = w3.eth.contract(nft_address, abi=ZORA_ERC1155_ABI)

        balance = contract.functions.balanceOf(self.address, token_id).call()
        if balance >= MAX_NFT_PER_ADDRESS:
            return Status.ALREADY, None

        minter_address = MINTER_ADDRESSES['2.0.0'][get_chain(w3)]
        minter = w3.eth.contract(minter_address, abi=ZORA_MINTER_ABI)
        sale_config = minter.functions.sale(nft_address, token_id).call()
        if sale_config[0] == 0:
            minter_address = MINTER_ADDRESSES['Other'][get_chain(w3)]
            minter = w3.eth.contract(minter_address, abi=ZORA_MINTER_ABI)
            sale_config = minter.functions.sale(nft_address, token_id).call()
        price = sale_config[3]

        value = contract.functions.mintFee().call() + price

        bs = '0x' + ('0' * 24) + self.address.lower()[2:]

        if with_rewards:
            args = (minter_address, token_id, 1, to_bytes(bs), MINT_REF_ADDRESS)
            func = contract.functions.mintWithRewards
        else:
            args = (minter_address, token_id, 1, to_bytes(bs))
            func = contract.functions.mint

        tx_hash = self.build_and_send_tx(
            w3,
            func(*args),
            action='Mint ERC1155',
            value=value,
            tx_change_func=self.mint_fun_tx_change,
        )

        return Status.SUCCESS, tx_hash

    @runner_func('Mint ERC1155')
    def mint_erc1155(self, w3, nft_address, token_id):
        try:
            return self._mint_erc1155(w3, nft_address, token_id)
        except web3.exceptions.ContractLogicError as e:
            if 'execution reverted' in str(e):
                return self._mint_erc1155(w3, nft_address, token_id, with_rewards=False)
            else:
                raise e

    @runner_func('Mint Custom')
    def mint_custom(self, w3, nft_info):
        nft_address, cnt, price = tuple(nft_info.split(':'))
        nft_address = Web3.to_checksum_address(nft_address)
        cnt = int(cnt)
        price = decimal_to_int(float(price), NATIVE_DECIMALS)

        contract = w3.eth.contract(nft_address, abi=CUSTOM_ERC721_ABI)

        balance = contract.functions.balanceOf(self.address).call()
        if balance >= (cnt * MAX_NFT_PER_ADDRESS):
            return Status.ALREADY, None

        tx_hash = self.build_and_send_tx(
            w3,
            contract.functions.mint(cnt),
            action='Mint Custom',
            value=price,
            tx_change_func=self.mint_fun_tx_change,
        )

        return Status.SUCCESS, tx_hash

    @runner_func('Mint.fun submit')
    def mint_fun_submit(self, chain, tx_hash):
        if not self.with_mint_fun:
            return

        requests.post('https://mint.fun/api/mintfun/submit-tx', json={
            'address': self.address,
            'hash': tx_hash,
            'isAllowlist': False,
            'chainId': CHAIN_IDS[chain],
            'source': 'projectPage',
        }, headers=get_default_mint_fun_headers(self.address), proxies=self.http_proxies)

    def _mint(self, nft):
        chain, nft_address, token_id = nft
        if token_id != 'custom':
            nft_address = Web3.to_checksum_address(nft_address)
        w3 = self.w3(chain)
        logger.print(f'Starting mint: {chain} - {nft_address}{"" if token_id is None else " - Token " + str(token_id)}')

        self.wait_for_eth_gas_price(w3)

        if token_id is None:
            status, tx_hash = self.mint_erc721(w3, nft_address)
        elif token_id == 'custom':
            status, tx_hash = self.mint_custom(w3, nft_address)
        else:
            status, tx_hash = self.mint_erc1155(w3, nft_address, token_id)

        if status == Status.SUCCESS and tx_hash:
            try:
                self.mint_fun_submit(chain, tx_hash)
                logger.print(f'Mint: Mint.fun points added')
            except Exception as mfe:
                logger.print(f'Mint: Error claiming mint.fun points: {str(mfe)}', color='red')
                pass

        return status

    def zora_action_wrapper(self, func, *args):

        def run_action():
            try:
                return func(*args)
            except PendingException:
                return Status.PENDING

        try:
            return run_action(), False
        except InsufficientFundsException as e:
            if e.chain == 'Zora' and AUTO_BRIDGE:
                if self.address not in auto_bridged_cnt_by_address:
                    auto_bridged_cnt_by_address[self.address] = 0

                if auto_bridged_cnt_by_address[self.address] > AUTO_BRIDGE_MAX_CNT:
                    logger.print('Insufficient funds on Zora. But auto-bridge was already made max possible times')
                    raise e

                logger.print(f'Insufficient funds on Zora. Let\'s bridge')
                init_balance = self.get_native_balance(e.chain)
                self.bridge()
                self.wait_for_bridge(init_balance)
                wait_next_tx()
                auto_bridged_cnt_by_address[self.address] += 1
                return run_action(), True
            else:
                raise e

    def mint(self, nft):
        return self.zora_action_wrapper(self._mint, nft)

    def upload_ipfs(self, filename, data, ext):
        fields = {
            'file': (filename, io.BytesIO(data), ext),
        }
        boundary = '------WebKitFormBoundary' + ''.join(random.sample(string.ascii_letters + string.digits, 16))
        m = MultipartEncoder(fields=fields, boundary=boundary)
        resp = requests.post('https://ipfs-uploader.zora.co/api/v0/add?'
                             'stream-channels=true&cid-version=1&progress=false',
                             data=m, headers={'content-type': m.content_type}, proxies=self.http_proxies, timeout=60)
        if resp.status_code != 200:
            raise Exception(f'status_code = {resp.status_code}, response = {resp.text}')
        try:
            return resp.json()['Hash']
        except Exception:
            raise Exception(f'status_code = {resp.status_code}, response = {resp.text}')

    @runner_func('Upload Image to IPFS')
    def upload_image_ipfs(self, name):
        img_szs = [i for i in range(500, 1001, 50)]
        url = f'https://picsum.photos/{random.choice(img_szs)}/{random.choice(img_szs)}'
        resp = requests.get(url, proxies=self.http_proxies, timeout=60)
        if resp.status_code != 200:
            raise Exception(f'Get random image failed, status_code = {resp.status_code}, response = {resp.text}')
        filename = name.replace(' ', '_').lower() + '.jpg'
        return self.upload_ipfs(filename, resp.content, 'image/jpg')

    @classmethod
    def generate_description(cls):
        description_words = get_random_words(random.randint(3, 10))
        description_words[0] = description_words[0].capitalize()
        description = ' '.join(description_words)
        return description

    def get_image_uri(self, name):
        return 'ipfs://' + self.upload_image_ipfs(name)

    def get_json_uri(self, body):
        return 'ipfs://' + self.upload_ipfs('', bytes(body, 'utf-8'), '')

    @runner_func('Create ERC-721 Edition')
    def _create(self):
        w3 = self.w3('Zora')
        contract = w3.eth.contract(ZORA_NFT_CREATOR_ADDRESS, abi=ZORA_NFT_CREATOR_ABI)
        name = ' '.join(get_random_words(random.randint(1, 3))).title()
        symbol = ''
        for char in name:
            if char not in 'euioa ':
                symbol += char
        while len(name) < 4 and len(symbol) < 3:
            name = ' '.join(get_random_words(random.randint(1, 3))).title()
            symbol = ''
            for char in name:
                if char not in 'euioa ':
                    symbol += char
        symbol = symbol.upper()[:3]

        description = self.generate_description()

        price = decimal_to_int(round(random.uniform(MINT_PRICE[0], MINT_PRICE[1]), 6), NATIVE_DECIMALS)
        edition_size = 2 ** 64 - 1
        royalty = random.randint(0, 10) * 100
        merkle_root = '0x0000000000000000000000000000000000000000000000000000000000000000'
        sale_config = (price, 2 ** 32 - 1, int(time.time()), 2 ** 64 - 1, 0, 0, to_bytes(merkle_root))

        image_uri = self.get_image_uri(name)

        args = (
            name, symbol,
            edition_size, royalty,
            self.address, self.address,
            sale_config, description, '', image_uri
        )

        self.wait_for_eth_gas_price(w3)

        self.build_and_send_tx(
            w3,
            contract.functions.createEdition(*args),
            action='Create ERC-721 Edition',
        )

        return Status.SUCCESS

    def _generate_nft_1155_setup_actions(self, next_token_id, fixed_price_minter, image_uri=None):
        name = ' '.join(get_random_words(random.randint(1, 3))).title()
        description = self.generate_description()

        if image_uri is None:
            image_uri = self.get_image_uri(name)

        nft_params = f'''{{
  "name": "{name}",
  "description": "{description}",
  "image": "{image_uri}",
  "content": {{
    "mime": "image/jpg",
    "uri": "{image_uri}"
  }}
}}'''

        next_token_id_hex = hex(next_token_id)[2:].zfill(64)
        latest_token_id_hex = hex(next_token_id - 1)[2:].zfill(64)

        nft_uri = self.get_json_uri(nft_params)
        nft_uri_hex = nft_uri.encode('utf-8').hex()
        if len(nft_uri_hex) % 64 != 0:
            nft_uri_hex += ''.join(['0' for _ in range(64 - (len(nft_uri_hex) % 64))])

        now = int(time.time())
        auto_reserve = 10 * random.randint(1, 10)

        assume_last_token_action = f'0xe72878b4{latest_token_id_hex}'
        create_nft_action = f'0x674cbae6' \
                            f'0000000000000000000000000000000000000000000000000000000000000060' \
                            f'000000000000000000000000000000000000000000000000ffffffffffffffff' \
                            f'000000000000000000000000634ff7bfa0d8c06f2423cd26b91bc76a368ddc92' \
                            f'00000000000000000000000000000000000000000000000000000000000000{hex(len(nft_uri))[2:]}' \
                            f'{nft_uri_hex}'
        nft_settings_action = f'0xafed7e9e' \
                              f'{next_token_id_hex}' \
                              f'00000000000000000000000000000000000000000000000000000000000000{hex(auto_reserve)[2:]}' \
                              f'00000000000000000000000000000000000000000000000000000000000001f4' \
                              f'000000000000000000000000{self.address.lower()[2:]}'
        add_permission_action = f'0x8ec998a0' \
                                f'{next_token_id_hex}' \
                                f'000000000000000000000000{fixed_price_minter.lower()[2:]}' \
                                f'0000000000000000000000000000000000000000000000000000000000000004'
        call_sale_action = f'0xd904b94a' \
                           f'{next_token_id_hex}' \
                           f'000000000000000000000000{fixed_price_minter.lower()[2:]}' \
                           f'0000000000000000000000000000000000000000000000000000000000000060' \
                           f'00000000000000000000000000000000000000000000000000000000000000c4' \
                           f'34db7eee{next_token_id_hex}' \
                           f'00000000000000000000000000000000000000000000000000000000' \
                           f'{hex(now)[2:]}000000000000000000000000000000000000000000000000ffffffff' \
                           f'ffffffff00000000000000000000000000000000000000000000000000000000' \
                           f'0000000000000000000000000000000000000000000000000000000000000000' \
                           f'0000000000000000000000000000000000000000000000000000000000000000' \
                           f'0000000000000000000000000000000000000000000000000000000000000000'
        admin_mint_action = f'0xc238d1ee' \
                            f'000000000000000000000000{self.address.lower()[2:]}' \
                            f'{next_token_id_hex}' \
                            f'0000000000000000000000000000000000000000000000000000000000000001' \
                            f'0000000000000000000000000000000000000000000000000000000000000080' \
                            f'0000000000000000000000000000000000000000000000000000000000000014' \
                            f'0000000000000000000000000000000000000000000000000000000000000000'

        setup_actions = [
            assume_last_token_action,
            create_nft_action,
            nft_settings_action,
            add_permission_action,
            call_sale_action,
            admin_mint_action,
        ]
        setup_actions = [to_bytes(sa) for sa in setup_actions]

        return setup_actions

    @runner_func('Create 1155 Collection')
    def _create_1155_new_collection(self):
        logger.print('Creating new ERC-1155 Collection')
        w3 = self.w3('Zora')
        contract = w3.eth.contract(ZORA_1155_CREATOR_ADDRESS, abi=ZORA_1155_CREATOR_ABI)

        collection_name = ' '.join(get_random_words(random.randint(1, 3))).title()
        collection_description = self.generate_description()

        collection_image_uri = self.get_image_uri(collection_name)

        collection_params = f'''{{
  "name": "{collection_name}",
  "description": "{collection_description}",
  "image": "{collection_image_uri}"
}}'''

        new_contract_uri = self.get_json_uri(collection_params)

        fixed_price_minter = contract.functions.fixedPriceMinter().call()

        setup_actions = self._generate_nft_1155_setup_actions(1, fixed_price_minter, collection_image_uri)

        args = (
            new_contract_uri, collection_name, (0, 0, ZERO_ADDRESS), self.address,
            setup_actions
        )

        self.wait_for_eth_gas_price(w3)

        self.build_and_send_tx(
            w3,
            contract.functions.createContract(*args),
            action='Create ERC-1155 Collection',
        )

        return Status.SUCCESS

    @runner_func('Create 1155 NFT')
    def _create_1155_new_nft(self, collection_address):
        w3 = self.w3('Zora')
        collection_address = Web3.to_checksum_address(collection_address)
        logger.print(f'Creating new NFT for collection {collection_address}')
        contract = w3.eth.contract(collection_address, abi=ZORA_ERC1155_ABI)

        fixed_price_minter = w3.eth.contract(ZORA_1155_CREATOR_ADDRESS, abi=ZORA_1155_CREATOR_ABI). \
            functions.fixedPriceMinter().call()

        next_token_id = contract.functions.nextTokenId().call()

        setup_actions = self._generate_nft_1155_setup_actions(next_token_id, fixed_price_minter)

        self.wait_for_eth_gas_price(w3)

        self.build_and_send_tx(
            w3,
            contract.functions.multicall(setup_actions),
            action='Create ERC-1155 NFT',
        )

        return Status.SUCCESS_WITH_EXISTED_COLLECTION, collection_address

    def _create_1155(self):
        if random.randint(1, 100) <= CREATE_USING_EXISTED_COLLECTION_PROBABILITY:
            collections = self.get_created_zora_collections(True)
            if len(collections) > 0:
                return self._create_1155_new_nft(random.choice(collections))
        return self._create_1155_new_collection()

    def create(self, is_erc_1155):
        create_func = self._create_1155 if is_erc_1155 else self._create
        return self.zora_action_wrapper(create_func)

    @runner_func('Get created collection')
    def get_created_zora_collections(self, is_erc_1155, timestamp_from=None):
        resp_raw = requests.get(f'https://zora.co/api/user/{self.address}/admin'
                                f'?query=adminCollections'
                                f'&chainId=7777777'
                                f'&direction=desc'
                                f'&limit=1000'
                                f'&includeTokens=true')
        if resp_raw.status_code != 200:
            raise Exception(f'status_code = {resp_raw.status_code}, response = {resp_raw.text}')
        try:
            created_list = resp_raw.json()
            eligible_addresses = []
            standard = 'ERC1155' if is_erc_1155 else 'ERC721'
            for created in created_list:
                if is_erc_1155 is not None and created['contractStandard'] != standard:
                    continue
                if timestamp_from and int(created['txn']['timestamp']) < timestamp_from:
                    continue
                eligible_addresses.append(created['address'])
            return eligible_addresses
        except Exception as e:
            raise Exception(f'status_code = {resp_raw.status_code}, response = {resp_raw.text}: {str(e)}')

    def wait_recently_created_collection(self, is_erc_1155, timestamp_from):
        wait_time = 0

        while wait_time < 60:

            logger.print(f'Create: Waiting for collection creating')
            time.sleep(5)
            wait_time += 5

            try:
                collection_addresses = self.get_created_zora_collections(is_erc_1155, timestamp_from=timestamp_from)
                collection_address = collection_addresses[0] if len(collection_addresses) > 0 else None
            except Exception as e:
                logger.print(f'Create: Error getting created collection: {str(e)}', color='red')
                continue

            if collection_address:
                collection_link = f'https://zora.co/collect/zora:{collection_address}'
                if is_erc_1155:
                    w3 = self.w3('Zora')
                    contract = w3.eth.contract(Web3.to_checksum_address(collection_address), abi=ZORA_ERC1155_ABI)
                    next_token_id = contract.functions.nextTokenId().call()
                    collection_link += f'/{next_token_id - 1}'
                logger.print(f'Create: {collection_link}', color='green')
                with open(f'{results_path}/created_collections.txt', 'a', encoding='utf-8') as file:
                    file.write(f'{self.address}:{collection_link}\n')
                return parse_mint_link(collection_link)

        return None

    def save_created_1155_nft(self, collection_address):
        collection_link = f'https://zora.co/collect/zora:{collection_address.lower()}'
        w3 = self.w3('Zora')
        contract = w3.eth.contract(Web3.to_checksum_address(collection_address), abi=ZORA_ERC1155_ABI)
        next_token_id = contract.functions.nextTokenId().call()
        collection_link += f'/{next_token_id - 1}'
        logger.print(f'Create: {collection_link}', color='green')
        with open(f'{results_path}/created_collections.txt', 'a', encoding='utf-8') as file:
            file.write(f'{self.address}:{collection_link}\n')
        return parse_mint_link(collection_link)

    def update_image(self, w3, collection_address):
        contract = w3.eth.contract(EDITION_METADATA_RENDERER_ADDRESS, abi=EDITION_METADATA_RENDERER_ABI)
        nft_name = w3.eth.contract(collection_address, abi=ZORA_ERC721_ABI).functions.name().call()
        image_uri = self.get_image_uri(nft_name)
        self.build_and_send_tx(
            w3,
            contract.functions.updateMediaURIs(collection_address, image_uri, ''),
            action='Update image'
        )

    def update_description(self, w3, collection_address):
        contract = w3.eth.contract(EDITION_METADATA_RENDERER_ADDRESS, abi=EDITION_METADATA_RENDERER_ABI)
        description = self.generate_description()
        self.build_and_send_tx(
            w3,
            contract.functions.updateDescription(collection_address, description),
            action='Update description'
        )

    def update_sale_settings(self, w3, collection_address):
        contract = w3.eth.contract(collection_address, abi=ZORA_ERC721_ABI)
        sale_start = contract.functions.saleDetails().call()[3]
        merkle_root = '0x0000000000000000000000000000000000000000000000000000000000000000'
        price = decimal_to_int(round(random.uniform(MINT_PRICE[0], MINT_PRICE[1]), 6), NATIVE_DECIMALS)
        limit_per_address = random.randint(10, 1000)
        sale_config = (price, limit_per_address, sale_start, 2 ** 64 - 1, 0, 0, to_bytes(merkle_root))
        self.build_and_send_tx(
            w3,
            contract.functions.setSaleConfiguration(*sale_config),
            action='Update sale settings',
        )

    @runner_func('Update ERC721 collection')
    def _update(self, collection_address):
        collection_address = Web3.to_checksum_address(collection_address)
        logger.print(f'Update ERC721: Collection {collection_address}')
        actions = []
        if UPDATE_IMAGE_ERC721:
            actions.append(self.update_image)
        if UPDATE_DESCRIPTION_ERC721:
            actions.append(self.update_description)
        if UPDATE_SALE_SETTINGS_ERC721:
            actions.append(self.update_sale_settings)
        if len(actions) == 0:
            raise Exception('All update features are turned off')

        w3 = self.w3('Zora')

        self.wait_for_eth_gas_price(w3)

        random.choice(actions)(w3, collection_address)
        return Status.SUCCESS

    def update_collection_1155(self, w3, collection_address):
        contract = w3.eth.contract(collection_address, abi=ZORA_ERC1155_ABI)
        name = ' '.join(get_random_words(random.randint(1, 3))).title()
        description = self.generate_description()
        image_uri = self.get_image_uri(name)
        params = f'''{{
  "image": "{image_uri}",
  "content": {{
    "mime": "image/jpg",
    "uri": "{image_uri}"
  }},
  "name": "{name}",
  "description": "{description}",
  "attributes": []
}}'''
        params_uri = self.get_json_uri(params)
        self.build_and_send_tx(
            w3,
            contract.functions.updateContractMetadata(params_uri, name),
            action='Update ERC1155 collection'
        )

    def update_nft_1155(self, w3, collection_address):
        contract = w3.eth.contract(collection_address, abi=ZORA_ERC1155_ABI)
        name = ' '.join(get_random_words(random.randint(1, 3))).title()
        description = self.generate_description()
        image_uri = self.get_image_uri(name)
        params = f'''{{
  "name": "{name}",
  "description": "{description}",
  "image": "{image_uri}",
  "content": {{
    "mime": "image/jpg",
    "uri": "{image_uri}"
  }},
  "attributes": []
}}'''
        tokens_in_collection = contract.functions.nextTokenId().call() - 1
        params_uri = self.get_json_uri(params)
        self.build_and_send_tx(
            w3,
            contract.functions.updateTokenURI(random.randint(1, tokens_in_collection), params_uri),
            action='Update ERC1155 NFT'
        )

    @runner_func('Update ERC1155 Collection')
    def _update_erc_1155(self, collection_address):
        collection_address = Web3.to_checksum_address(collection_address)
        logger.print(f'Update ERC1155: Collection {collection_address}')
        actions = []
        if UPDATE_COLLECTION_ERC1155:
            actions.append(self.update_collection_1155)
        if UPDATE_NFT_ERC1155:
            actions.append(self.update_nft_1155)
        if len(actions) == 0:
            raise Exception('All update features are turned off')

        w3 = self.w3('Zora')

        self.wait_for_eth_gas_price(w3)

        random.choice(actions)(w3, collection_address)
        return Status.SUCCESS

    def update(self, collection_address, is_erc_1155):
        update_func = self._update_erc_1155 if is_erc_1155 else self._update
        return self.zora_action_wrapper(update_func, collection_address)

    @runner_func('Admin mint ERC721')
    def _admin_mint(self, collection_address):
        w3 = self.w3('Zora')
        collection_address = Web3.to_checksum_address(collection_address)
        logger.print(f'Admin mint ERC721: Collection {collection_address}')
        contract = w3.eth.contract(collection_address, abi=ZORA_ERC721_ABI)
        self.wait_for_eth_gas_price(w3)
        self.build_and_send_tx(
            w3,
            contract.functions.adminMint(self.address, 1),
            action='Admin mint ERC721',
        )
        return Status.SUCCESS

    @runner_func('Admin mint ERC1155')
    def _admin_mint_1155(self, collection_address):
        w3 = self.w3('Zora')
        collection_address = Web3.to_checksum_address(collection_address)
        logger.print(f'Admin mint ERC1155: Collection {collection_address}')
        contract = w3.eth.contract(collection_address, abi=ZORA_ERC1155_ABI)
        data = f'0xc238d1ee' \
               f'000000000000000000000000{self.address.lower()[2:]}' \
               f'0000000000000000000000000000000000000000000000000000000000000001' \
               f'0000000000000000000000000000000000000000000000000000000000000001' \
               f'0000000000000000000000000000000000000000000000000000000000000080' \
               f'0000000000000000000000000000000000000000000000000000000000000014' \
               f'0000000000000000000000000000000000000000000000000000000000000000'
        data = [to_bytes(data)]
        self.wait_for_eth_gas_price(w3)
        self.build_and_send_tx(
            w3,
            contract.functions.multicall(data),
            action='Admin mint ERC1155',
        )
        return Status.SUCCESS

    def admin_mint(self, collection_address, is_erc_1155):
        admin_mint_func = self._admin_mint_1155 if is_erc_1155 else self._admin_mint
        return self.zora_action_wrapper(admin_mint_func, collection_address)

    def _claim(self):
        for chain in REWARDS_CHAINS:
            w3 = self.w3(chain)
            for address in PROTOCOL_REWARDS_ADDRESSES[chain]:
                contract = w3.eth.contract(address, abi=PROTOCOL_REWARDS_ABI)
                balance = contract.functions.balanceOf(self.address).call()
                if balance < decimal_to_int(MIN_REWARDS_TO_CLAIM, NATIVE_DECIMALS):
                    continue
                self.wait_for_eth_gas_price(w3)
                self.build_and_send_tx(
                    w3,
                    contract.functions.withdraw(self.address, balance),
                    action='Claim rewards',
                )
                logger.print(f'Claimed {int_to_decimal(balance, NATIVE_DECIMALS)} ETH on {chain}')
                wait_next_tx()
        return Status.SUCCESS

    def claim(self):
        return self.zora_action_wrapper(self._claim)


def wait_next_run(idx, runs_count):
    wait = random.randint(
        int(NEXT_ADDRESS_MIN_WAIT_TIME * 60),
        int(NEXT_ADDRESS_MAX_WAIT_TIME * 60)
    )

    done_msg = f'Done: {idx}/{runs_count}'
    waiting_msg = 'Waiting for next run for {:.2f} minutes'.format(wait / 60)

    cprint('\n#########################################\n#', 'cyan', end='')
    cprint(done_msg.center(39), 'magenta', end='')
    cprint('#\n#########################################', 'cyan', end='')

    tg_msg = done_msg

    cprint('\n# ', 'cyan', end='')
    cprint(waiting_msg, 'magenta', end='')
    cprint(' #\n#########################################\n', 'cyan')
    tg_msg += '. ' + waiting_msg

    logger.send_tg(tg_msg)

    time.sleep(wait)


@runner_func('Get all created collections')
def get_all_created(address, proxy):
    if proxy is not None and len(proxy) > 4 and proxy[:4] != 'http':
        proxy = 'http://' + proxy

    proxies = {'http': proxy, 'https': proxy} if proxy and proxy != '' else {}

    resp_raw = requests.get(f'https://zora.co/api/user/{address}/admin'
                            f'?query=adminCollections'
                            f'&chainId=7777777'
                            f'&direction=desc'
                            f'&limit=1000'
                            f'&includeTokens=true', proxies=proxies)
    if resp_raw.status_code != 200:
        raise Exception(f'status_code = {resp_raw.status_code}, response = {resp_raw.text}')
    try:
        created_list = resp_raw.json()
        created_mints = []
        for created in created_list:
            if created['contractStandard'] == 'ERC721':
                created_mints.append(('Zora', created['address'], None))
            else:
                created_mints.extend([('Zora', created['address'], token_id + 1)
                                     for token_id in range(len(created['tokens']))])
        return created_mints
    except Exception as e:
        raise Exception(f'status_code = {resp_raw.status_code}, response = {resp_raw.text}: {str(e)}')


def main():
    if GET_TELEGRAM_CHAT_ID:
        get_telegram_bot_chat_id()
        exit(0)

    random.seed(int(datetime.now().timestamp()))

    with open('files/wallets.txt', 'r', encoding='utf-8') as file:
        wallets = file.read().splitlines()
    with open('files/proxies.txt', 'r', encoding='utf-8') as file:
        proxies = file.read().splitlines()
    with open('files/mints.txt', 'r', encoding='utf-8') as file:
        mint_links = file.read().splitlines()

    if len(proxies) == 0:
        proxies = [None] * len(wallets)
    if len(proxies) != len(wallets):
        cprint('Proxies count doesn\'t match wallets count. Add proxies or leave proxies file empty', 'red')
        return

    queue = list(zip(wallets, proxies))
    mints = []
    for link in mint_links:
        parsed = parse_mint_link(link)
        if parsed is None:
            continue
        mints.append(parsed)

    idx, runs_count = 0, len(queue)

    created_mints, stats = {}, {}

    for wallet, proxy in queue:
        if wallet.find(';') == -1:
            key = wallet
        else:
            key = wallet.split(';')[1]

        address = Account().from_key(key).address

        created_mints[address] = []
        if MINT_ALREADY_CREATED_PERCENT > 0:
            created_mints[address].extend(get_all_created(address, proxy))

        stats[address] = {chain: 0 for chain in INVOLVED_CHAINS}
        stats[address]['Created'] = 0
        stats[address]['Updated'] = 0
        stats[address]['Admin Mint'] = 0

    random.shuffle(queue)

    while len(queue) != 0:

        if idx != 0:
            logger.send_tg_stored()
            wait_next_run(idx, runs_count)

        account = queue.pop(0)

        wallet, proxy = account

        if wallet.find(';') == -1:
            key = wallet
        else:
            key = wallet.split(';')[1]

        address = Account().from_key(key).address
        logger.print(address)

        try:
            runner = Runner(key, proxy)
        except Exception as e:
            handle_traceback()
            logger.print(f'Failed to init: {str(e)}', color='red')
            continue

        modules = []
        for action, (min_cnt, max_cnt) in MODULES.items():
            modules.extend([action for _ in range(random.randint(min_cnt, max_cnt))])
        modules = [m.capitalize() for m in modules]

        random.shuffle(modules)

        minted_in_run = set()
        auto_bridged_cnt = 0
        auto_created_cnt = 0

        for module in modules:
            logger.print(f'{module}: Started', color='blue')
            try:
                nothing_minted = False
                if module == 'Claim':

                    runner.claim()

                elif module == 'Bridge':

                    if auto_bridged_cnt > 0:
                        auto_bridged_cnt -= 1
                        logger.print(f'{module}: Skipped, because it was done automatically before', color='yellow')
                        continue

                    runner.bridge()

                elif module == 'Create':

                    if auto_created_cnt > 0:
                        auto_created_cnt -= 1
                        logger.print(f'{module}: Skipped, because it was done automatically before', color='yellow')
                        continue

                    wait_next_tx(2.0)
                    timestamp = int(time.time())

                    create_status, bridged = runner.create(USE_NFT_1155)
                    if bridged:
                        auto_bridged_cnt += 1

                    stats[address]['Created'] += 1

                    if type(create_status) is tuple:
                        wait_next_tx()
                        created_nft = runner.save_created_1155_nft(create_status[1])
                        created_mints[address].append(created_nft)
                    else:
                        created_nft = runner.wait_recently_created_collection(USE_NFT_1155, timestamp)
                        if created_nft is None:
                            logger.print(f'{module}: Can\'t get created collection link for 60 seconds', color='red')
                        else:
                            created_mints[address].append(created_nft)

                elif module == 'Update':

                    is_erc_1155 = random.randint(1, 2) == 1

                    collection_addresses = runner.get_created_zora_collections(is_erc_1155)
                    if len(collection_addresses) == 0:
                        collection_addresses = runner.get_created_zora_collections(not is_erc_1155)

                    if len(collection_addresses) == 0 and AUTO_CREATE:

                        logger.print(f'{module}: No collections found. Let\'s create one')

                        wait_next_tx(2.0)
                        timestamp = int(time.time())

                        create_status, bridged = runner.create(USE_NFT_1155)
                        if bridged:
                            auto_bridged_cnt += 1

                        auto_created_cnt += 1
                        stats[address]['Created'] += 1

                        if type(create_status) is tuple:
                            wait_next_tx()
                            created_nft = runner.save_created_1155_nft(create_status[1])
                            created_mints[address].append(created_nft)
                        else:
                            created_nft = runner.wait_recently_created_collection(USE_NFT_1155, timestamp)
                            if created_nft is None:
                                logger.print(f'{module}: Can\'t get created collection link for 60 seconds',
                                             color='red')
                                continue
                            else:
                                created_mints[address].append(created_nft)

                        wait_next_tx()

                        collection_addresses = runner.get_created_zora_collections(USE_NFT_1155)
                        is_erc_1155 = USE_NFT_1155

                    _, bridged = runner.update(random.choice(collection_addresses), is_erc_1155)
                    if bridged:
                        auto_bridged_cnt += 1
                    stats[address]['Updated'] += 1

                elif module == 'Admin':

                    is_erc_1155 = random.randint(1, 2) == 1

                    collection_addresses = runner.get_created_zora_collections(is_erc_1155)
                    if len(collection_addresses) == 0:
                        collection_addresses = runner.get_created_zora_collections(not is_erc_1155)

                    if len(collection_addresses) == 0 and AUTO_CREATE:

                        logger.print(f'{module}: No collections found. Let\'s create one')

                        wait_next_tx(2.0)
                        timestamp = int(time.time())

                        create_status, bridged = runner.create(USE_NFT_1155)
                        if bridged:
                            auto_bridged_cnt += 1

                        auto_created_cnt += 1
                        stats[address]['Created'] += 1

                        if type(create_status) is tuple:
                            wait_next_tx()
                            created_nft = runner.save_created_1155_nft(create_status[1])
                            created_mints[address].append(created_nft)
                        else:
                            created_nft = runner.wait_recently_created_collection(USE_NFT_1155, timestamp)
                            if created_nft is None:
                                logger.print(f'{module}: Can\'t get created collection link for 60 seconds',
                                             color='red')
                                continue
                            else:
                                created_mints[address].append(created_nft)

                        wait_next_tx()

                        collection_addresses = runner.get_created_zora_collections(USE_NFT_1155)
                        is_erc_1155 = USE_NFT_1155

                    _, bridged = runner.admin_mint(random.choice(collection_addresses), is_erc_1155)
                    if bridged:
                        auto_bridged_cnt += 1
                    stats[address]['Admin Mint'] += 1

                else:

                    possible_mints = copy.deepcopy(mints)
                    random.shuffle(possible_mints)
                    was_minted = False

                    while len(possible_mints) != 0:

                        nft = None
                        if random.randint(1, 100) <= MINT_ALREADY_CREATED_PERCENT:
                            created_addresses = list(created_mints.keys())
                            random.shuffle(created_addresses)
                            for created_address in created_addresses:
                                if created_address == address or len(created_mints[created_address]) == 0:
                                    continue
                                nfts = copy.deepcopy(created_mints[created_address])
                                random.shuffle(nfts)
                                for _nft in nfts:
                                    if _nft in minted_in_run:
                                        continue
                                    nft = _nft
                                    break
                                if nft is not None:
                                    break

                        if nft is None:
                            nft = possible_mints.pop(0)
                            if nft in minted_in_run:
                                continue

                        minted_in_run.add(nft)

                        status, bridged = runner.mint(nft)
                        if bridged:
                            auto_bridged_cnt += 1
                        if status == Status.ALREADY:
                            logger.print(f'{module}: Already minted, trying another one', color='yellow')
                            continue

                        mint_chain = nft[0]
                        stats[address][mint_chain] += 1
                        was_minted = True

                        break

                    if not was_minted:
                        logger.print(f'{module}: Every NFT from the list was already minted', color='yellow')
                        nothing_minted = True

                if module != 'Mint' or not nothing_minted:
                    logger.print(f'{module}: Success', color='green')

                wait_next_tx()

            except Exception as e:
                handle_traceback()
                logger.print(f'{module}: Failed: {str(e)}', color='red')

        with open(f'{results_path}/report.csv', 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file)
            csv_data = [['Address', 'Total Created', 'Total Updated', 'Total Admin Minted', 'Total Minted',
                         'Minted Zora', 'Minted Base', 'Minted Optimism', 'Minted Ethereum']]
            for addr in stats:
                stat = stats[addr]
                row = [addr, stat.get('Created', 0), stat.get('Updated', 0), stat.get('Admin Mint', 0), 0]
                for chain in INVOLVED_CHAINS:
                    cnt = stat.get(chain, 0)
                    row[4] += cnt
                    row.append(cnt)
                csv_data.append(row)
            writer.writerows(csv_data)

        idx += 1

    cprint('\n#########################################\n#', 'cyan', end='')
    cprint(f'Finished'.center(39), 'magenta', end='')
    cprint('#\n#########################################', 'cyan')


if __name__ == '__main__':
    cprint('###############################################################', 'cyan')
    cprint('#################', 'cyan', end='')
    cprint(' https://t.me/thelaziestcoder ', 'magenta', end='')
    cprint('################', 'cyan')
    cprint('#################', 'cyan', end='')
    cprint(' https://t.me/thelaziestcoder ', 'magenta', end='')
    cprint('################', 'cyan')
    cprint('#################', 'cyan', end='')
    cprint(' https://t.me/thelaziestcoder ', 'magenta', end='')
    cprint('################', 'cyan')
    cprint('###############################################################\n', 'cyan')

    main()
