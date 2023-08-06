import io
import string
import copy
import csv
import random
import time
import traceback
import web3.exceptions

from termcolor import cprint
from enum import Enum
from pathlib import Path
from datetime import datetime
from retry import retry
from requests_toolbelt import MultipartEncoder
from eth_account.account import Account

from logger import Logger, get_telegram_bot_chat_id
from utils import *
from config import *
from vars import *

date_path = datetime.now().strftime('%d-%m-%Y-%H-%M-%S')
results_path = 'results/' + date_path
logs_root = 'logs/'
logs_path = logs_root + date_path
Path(results_path).mkdir(parents=True, exist_ok=True)
Path(logs_path).mkdir(parents=True, exist_ok=True)

logger = Logger(to_console=True, to_file=True, default_file=f'{logs_path}/console_output.txt')

with open('files/english_words.txt', 'r', encoding='utf-8') as words_file:
    english_words = words_file.read().splitlines()


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
    FAILED = 4


class Runner:

    def __init__(self, private_key, proxy):
        if proxy is not None and len(proxy) > 4 and proxy[:4] != 'http':
            proxy = 'http://' + proxy
        self.proxy = proxy

        self.w3s = {chain: get_w3(chain, proxy=self.proxy) for chain in INVOLVED_CHAINS}

        self.private_key = private_key
        self.address = Account().from_key(private_key).address

    def w3(self, chain):
        return self.w3s[chain]

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

    def build_and_send_tx(self, w3, func, action, value=0):
        return build_and_send_tx(w3, self.address, self.private_key, func, value, self.tx_verification, action)

    @classmethod
    def wait_for_eth_gas_price(cls, w3):
        t = 0
        while w3.eth.gas_price > Web3.to_wei(MAX_ETH_GAS_PRICE, 'gwei'):
            gas_price = int_to_decimal(w3.eth.gas_price, 9)
            gas_price = round(gas_price, 2)
            logger.print(f'Gas price is too high - {gas_price}. Waiting for {WAIT_GAS_TIME}s')
            t += WAIT_GAS_TIME
            if t >= TOTAL_WAIT_GAS_TIME:
                break
            time.sleep(WAIT_GAS_TIME)

        if w3.eth.gas_price > Web3.to_wei(MAX_ETH_GAS_PRICE, 'gwei'):
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

        amount = random.uniform(BRIDGE_AMOUNT[0], BRIDGE_AMOUNT[1])
        amount = round(amount, random.randint(5, 8))

        value = Web3.to_wei(amount, 'ether')

        self.wait_for_eth_gas_price(w3)

        self.build_and_send_tx(
            w3,
            contract.functions.depositTransaction(self.address, value, ZORA_BRIDGE_GAS_LIMIT, False, b''),
            value=value,
            action='Bridge'
        )

        return Status.SUCCESS

    @runner_func('Mint ERC721')
    def mint_erc721(self, w3, nft_address, cnt):
        contract = w3.eth.contract(nft_address, abi=ZORA_ERC721_ABI)

        balance = contract.functions.balanceOf(self.address).call()
        if balance >= cnt:
            return Status.ALREADY
        cnt -= balance

        price = contract.functions.salesConfig().call()[0]

        value = contract.functions.zoraFeeForAmount(cnt).call()[1] + price * cnt

        self.build_and_send_tx(
            w3,
            contract.functions.purchase(cnt),
            action='Mint ERC721',
            value=value,
        )

        return Status.SUCCESS

    @runner_func('Mint ERC1155')
    def mint_erc1155(self, w3, nft_address, token_id, cnt):
        contract = w3.eth.contract(nft_address, abi=ZORA_ERC1155_ABI)

        balance = contract.functions.balanceOf(self.address, token_id).call()
        if balance >= cnt:
            return Status.ALREADY
        cnt -= balance

        minter_address = MINTER_ADDRESSES[get_chain(w3)]

        minter = w3.eth.contract(minter_address, abi=ZORA_MINTER_ABI)

        sale_config = minter.functions.sale(nft_address, token_id).call()
        price = sale_config[3]

        value = (contract.functions.mintFee().call() + price) * cnt

        bs = '0x' + ('0' * 24) + self.address.lower()[2:]
        args = (minter_address, token_id, cnt, to_bytes(bs))

        self.build_and_send_tx(
            w3,
            contract.functions.mint(*args),
            action='Mint ERC1155',
            value=value,
        )

        return Status.SUCCESS

    def _mint(self, nft):
        cnt = 1
        chain, nft_address, token_id = nft
        w3 = self.w3(chain)
        logger.print(f'Starting mint: {chain} - {nft_address}')

        def mint_func():
            if token_id is None:
                return self.mint_erc721(w3, nft_address, cnt)
            else:
                return self.mint_erc1155(w3, nft_address, token_id, cnt)

        try:
            return mint_func()
        except InsufficientFundsException as e:
            if chain == 'Zora' and AUTO_BRIDGE:
                logger.print(f'Insufficient funds on Zora. Let\'s bridge')
                init_balance = self.get_native_balance(chain)
                self.bridge()
                self.wait_for_bridge(init_balance)
                wait_next_tx()
                return mint_func()
            else:
                raise e

    def mint(self, nft):
        try:
            return self._mint(nft)
        except PendingException:
            return Status.PENDING

    @runner_func('Upload IPFS')
    def upload_ipfs(self, name):
        img_szs = [i for i in range(250, 651, 50)]
        url = f'https://picsum.photos/{random.choice(img_szs)}/{random.choice(img_szs)}'
        resp = requests.get(url)
        if resp.status_code != 200:
            raise Exception(f'Get random image failed, status_code = {resp.status_code}, response = {resp.text}')
        filename = name.replace(' ', '_').lower() + '.jpg'
        fields = {
            'file': (filename, io.BytesIO(resp.content), 'image/jpg'),
        }
        boundary = '------WebKitFormBoundary' + ''.join(random.sample(string.ascii_letters + string.digits, 16))
        m = MultipartEncoder(fields=fields, boundary=boundary)
        proxies = {'http': self.proxy, 'https': self.proxy} if self.proxy and self.proxy != '' else {}
        resp = requests.post('https://ipfs-uploader.zora.co/api/v0/add?'
                             'stream-channels=true&cid-version=1&progress=false',
                             data=m, headers={'content-type': m.content_type}, proxies=proxies, timeout=60)
        if resp.status_code != 200:
            raise Exception(f'status_code = {resp.status_code}, response = {resp.text}')
        try:
            return resp.json()['Hash']
        except Exception:
            raise Exception(f'status_code = {resp.status_code}, response = {resp.text}')

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
        symbol = symbol.upper()

        description_words = get_random_words(random.randint(3, 10))
        description_words[0] = description_words[0].capitalize()
        description = ' '.join(description_words)

        edition_size = 2 ** 64 - 1
        royalty = random.randint(0, 10) * 100
        merkle_root = '0x0000000000000000000000000000000000000000000000000000000000000000'
        sale_config = (0, 2 ** 32 - 1, int(time.time()), 2 ** 64 - 1, 0, 0, Web3.to_bytes(hexstr=merkle_root))

        image_uri = 'ipfs://' + self.upload_ipfs(name)

        args = (
            name, symbol,
            edition_size, royalty,
            self.address, self.address,
            sale_config, description, '', image_uri
        )

        self.build_and_send_tx(
            w3,
            contract.functions.createEdition(*args),
            action='Create Edition',
        )

        return Status.SUCCESS

    def _create_with_bridge(self):
        try:
            return self._create()
        except InsufficientFundsException as e:
            if AUTO_BRIDGE:
                logger.print(f'Insufficient funds on Zora. Let\'s bridge')
                init_balance = self.get_native_balance('Zora')
                self.bridge()
                self.wait_for_bridge(init_balance)
                wait_next_tx()
                return self._create()
            else:
                raise e

    @runner_func('Create Edition')
    def create(self):
        try:
            return self._create_with_bridge()
        except PendingException:
            return Status.PENDING


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
        mints = file.read().splitlines()

    if len(proxies) == 0:
        proxies = [None] * len(wallets)
    if len(proxies) != len(wallets):
        cprint('Proxies count doesn\'t match wallets count. Add proxies or leave proxies file empty', 'red')
        return

    queue = list(zip(wallets, proxies))

    for i in range(len(mints)):
        link = mints[i]
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
        nft_address = Web3.to_checksum_address(nft_address)
        token_id = int(token_id) if token_id else None
        mints[i] = (chain, nft_address, token_id)

    idx, runs_count = 0, len(queue)

    stats = {}

    for wallet, proxy in queue:
        if wallet.find(';') == -1:
            key = wallet
        else:
            key = wallet.split(';')[1]

        runner = Runner(key, proxy)
        stats[runner.address] = {'Zora': 0, 'Optimism': 0, 'Ethereum': 0, 'Created': 0}

    random.shuffle(queue)

    while len(queue) != 0:

        if idx != 0:
            wait_next_run(idx, runs_count)

        account = queue.pop(0)

        wallet, proxy = account

        if wallet.find(';') == -1:
            key = wallet
        else:
            key = wallet.split(';')[1]

        runner = Runner(key, proxy)
        address = runner.address

        logger.print(address)

        modules = copy.deepcopy(MODULES)
        modules = [m.capitalize() for m in modules]
        if MODULES_RANDOM_ORDER:
            random.shuffle(modules)

        for module in modules:
            logger.print(f'{module} started', color='blue')
            try:
                nothing_minted = False
                if module == 'Bridge':
                    runner.bridge()
                elif module == 'Create':
                    runner.create()
                    stats[address]['Created'] += 1
                else:
                    possible_mints = copy.deepcopy(mints)
                    random.shuffle(possible_mints)
                    was_minted = False
                    while len(possible_mints) != 0:
                        nft = possible_mints[0]
                        status = runner.mint(nft)
                        if status == Status.ALREADY:
                            logger.print(f'Already minted, trying another one', color='yellow')
                            possible_mints.pop(0)
                            continue
                        mint_chain = nft[0]
                        stats[address][mint_chain] += 1
                        was_minted = True
                        break
                    if not was_minted:
                        logger.print(f'{module} every NFT from the list was already minted', color='yellow')
                        nothing_minted = True
                if module != 'Mint' or not nothing_minted:
                    logger.print(f'{module} success', color='green')
                wait_next_tx()
            except Exception as e:
                handle_traceback()
                logger.print(f'{module} failed: {str(e)}', color='red')

        logger.send_tg_stored()

        with open(f'{results_path}/report.csv', 'w', encoding='utf-8', newline='') as file:
            writer = csv.writer(file)
            csv_data = [
                ['Address', 'Total created', 'Total Minted', 'Minted Zora', 'Minted Optimism', 'Minted Ethereum']]
            for addr in stats:
                stat = stats[addr]
                zc, oc, ec = stat.get('Zora', 0), stat.get('Optimism', 0), stat.get('Ethereum', 0)
                created_cnt = stat.get('Created', 0)
                csv_data.append([addr, created_cnt, zc + oc + ec, zc, oc, ec])
            writer.writerows(csv_data)

        idx += 1

    cprint('\n#########################################\n#', 'cyan', end='')
    cprint(f'Finished'.center(39), 'magenta', end='')
    cprint('#\n#########################################', 'cyan')


if __name__ == '__main__':
    cprint('###########################################################', 'cyan')
    cprint('#######################', 'cyan', end='')
    cprint(' By @timfame ', 'magenta', end='')
    cprint('#######################', 'cyan')
    cprint('###########################################################\n', 'cyan')

    main()
