import io
import string
import copy
import csv
import traceback
import web3.exceptions

from termcolor import cprint
from enum import Enum
from tqdm import tqdm
from requests_toolbelt import MultipartEncoder
from eth_account.account import Account
from eth_account.messages import encode_typed_data
from eth_utils import function_signature_to_4byte_selector
import eth_abi

from logger import get_telegram_bot_chat_id
from utils import *
from helpers import *
from config import *
from vars import *
from client import Client
import okx



NFT_PER_ADDRESS = 1000 if MINT_BY_NFTS else MAX_NFT_PER_ADDRESS


def _delay(r, *args, **kwargs):
    time.sleep(random.uniform(1, 2))


auto_bridged_cnt_by_address = {}


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
    MINT_NOT_STARTED = 6
    MINT_ENDED = 7


class Runner(Client):

    def __init__(self, private_key, proxy):
        super().__init__(private_key, proxy)

        if proxy is not None and len(proxy) > 4 and proxy[:4] != 'http':
            proxy = 'http://' + proxy
        self.proxy = proxy

        self.http_proxies = {'http': self.proxy, 'https': self.proxy} if self.proxy and self.proxy != '' else {}

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

    def send_tx(self, w3, tx, action, tx_change_func=None):
        return send_tx(w3, self.private_key, tx, self.tx_verification, action, tx_change_func)

    def build_and_send_tx(self, w3, func, action, value=0, tx_change_func=None, simulate=False):
        return build_and_send_tx(w3, self.address, self.private_key, func, value, self.tx_verification, action,
                                 tx_change_func=tx_change_func, simulate=simulate)

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

        logger.print('Assets bridged successfully', color='green')

    def _relay_request(self, src_chain_id, dst_chain_id, tx_data, user=None, source=None):
        if user is None:
            user = self.address
        body = {
            'destinationChainId': dst_chain_id,
            'originChainId': src_chain_id,
            'txs': [tx_data],
            'user': user,
        }
        if source is not None:
            body['source'] = 'https://zora.co'
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://zora.co',
            'Referer': 'https://zora.co/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
        }
        try:
            resp = requests.post(f'https://api.relay.link/execute/call',
                                 json=body, headers=headers, proxies=self.http_proxies)
            try:
                tx = resp.json()
                tx = tx['steps'][0]['items'][0]['data']
                return tx
            except Exception as e:
                raise Exception(f'{e}: Status = {resp.status_code}. Response = {resp.text}')
        except Exception as e:
            raise Exception(f'Relay link request failed: {e}')

    def fulfill_tx(self, w3, tx):
        try:
            tx['nonce'] = w3.eth.get_transaction_count(self.address)
            tx['data'] = to_bytes(tx['data'])
            tx['value'] = int(tx['value'])
            tx['from'] = Web3.to_checksum_address(tx['from'])
            tx['to'] = Web3.to_checksum_address(tx['to'])

            if 'gasLimit' in tx:
                del tx['gasLimit']

            max_priority_fee = w3.eth.max_priority_fee
            latest_block = w3.eth.get_block("latest")
            max_fee_per_gas = max_priority_fee + int(latest_block["baseFeePerGas"] * random.uniform(1.15, 1.2))
            tx['maxPriorityFeePerGas'] = max_priority_fee
            tx['maxFeePerGas'] = max_fee_per_gas
        except Exception as e:
            raise Exception(f'Fulfill tx failed: {e}')

        return tx

    def get_reservoir_action_tx(self, w3, dst_chain, tx_data, is_bridge=True):
        body = {
            'originChainId': w3.current_chain_id,
            'txs': [tx_data],
            'user': self.address,
        }
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://bridge.zora.energy',
            'Priority': 'u=1, i',
            'Referer': 'https://bridge.zora.energy/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'X-Rkc-Version': '1.11.2',
        }
        if not is_bridge:
            headers.update({
                'Origin': 'https://zora.co',
                'Referer': 'https://zora.co/',
                'X-Rkc-Version': '2.0.8',
                'X-Rkui-Version': '2.3.9',
            })
        try:
            api_name = 'api'
            if dst_chain != 'Ethereum':
                api_name = f'api-{dst_chain.lower()}'
            resp = requests.post(f'https://{api_name}.reservoir.tools/execute/call/v1',
                                 json=body, headers=headers, proxies=self.http_proxies)
            try:
                tx = resp.json()
                tx = tx['steps'][0]['items'][0]['data']
                return self.fulfill_tx(w3, tx)
            except Exception as e:
                raise Exception(f'{e}: Status = {resp.status_code}. Response = {resp.text}')
        except Exception as e:
            raise Exception(f'Get Relayer tx data failed: {e}')

    def withdraw_from_okx(self):
        if OKX_API_KEY == '' or OKX_SECRET_KEY == '' or OKX_PASSPHRASE == '':
            return False
        chain = BRIDGE_SOURCE_CHAIN
        if chain == 'Any':
            chain = random.choice(['Arbitrum', 'Base', 'Optimism'])
        logger.print(f'Withdrawing funds from OKX to {chain}')
        w3 = self.w3(chain)
        balance = w3.eth.get_balance(self.address)
        try:
            amount = okx.withdraw_native(self.address, chain)
            logger.print(f'Withdraw of {"%.4f" % amount} ETH was initiated')
        except Exception as e:
            logger.print(f'Withdraw failed: {str(e)}', color='red')
            return False
        logger.print(f'Waiting for funds 70s')
        time.sleep(70)
        t = 70
        while t < 300:
            if w3.eth.get_balance(self.address) > balance:
                logger.print(f'Funds have been received from OKX', color='green')
                return True
            logger.print(f'Funds have not arrived yet. Waiting for 10s')
            t += 10
            time.sleep(10)
        logger.print(f'Funds did not arrived after 300s', color='red')
        return False

    def instant_bridge(self, try_okx=True):
        src_chain = BRIDGE_SOURCE_CHAIN
        if src_chain == 'Any':
            logger.print('Searching for chain with the largest balance')
            max_balance = -1
            for chain in ['Arbitrum', 'Base', 'Optimism']:
                bal = self.w3(chain).eth.get_balance(self.address)
                if bal > max_balance:
                    max_balance = bal
                    src_chain = chain

        w3 = self.w3(src_chain)

        self.wait_for_eth_gas_price(w3)

        balance = w3.eth.get_balance(self.address)
        balance = int_to_decimal(balance, NATIVE_DECIMALS)

        if BRIDGE_PERCENT is not tuple and BRIDGE_PERCENT == -1:
            needed_balance = BRIDGE_AMOUNT[0] / 1.5
            amount_from, amount_to = BRIDGE_AMOUNT
        else:
            needed_balance = BRIDGE_PERCENT_MIN_BALANCE
            amount_from, amount_to = balance * BRIDGE_PERCENT[0] / 100, balance * BRIDGE_PERCENT[1] / 100

        if balance - 0.0001 < needed_balance:
            if try_okx and self.withdraw_from_okx():
                wait_next_tx()
                return self.instant_bridge(try_okx=False)
            else:
                raise InsufficientFundsException(f'Low balance for bridge [{"%.5f" % balance}]', src_chain)
        balance -= 0.0001
        amount = random.uniform(min(balance, amount_from), min(balance, amount_to))
        amount = round(amount, random.randint(4, 5))

        logger.print(f'Instant Bridging {amount} ETH from {src_chain}')

        value = Web3.to_wei(amount, 'ether')

        tx = self.get_reservoir_action_tx(w3, 'Zora', {
            'data': '0x',
            'to': self.address,
            'value': str(value),
        })

        self.send_tx(w3, tx, 'Instant Bridge')

        return Status.SUCCESS

    @runner_func('Bridge')
    def _bridge(self):
        if USE_INSTANT_BRIDGE:
            return self.instant_bridge()

        w3 = self.w3('Ethereum')

        contract = w3.eth.contract(ZORA_BRIDGE_ADDRESS, abi=ZORA_BRIDGE_ABI)

        balance = w3.eth.get_balance(self.address)
        balance = int_to_decimal(balance, NATIVE_DECIMALS)

        self.wait_for_eth_gas_price(w3)

        estimated_fee = 0.00033 * (int_to_decimal(w3.eth.gas_price, 9) / 6.2) * 2
        balance -= estimated_fee

        if BRIDGE_PERCENT is not tuple and BRIDGE_PERCENT == -1:
            needed_balance = BRIDGE_AMOUNT[0] / 2
            amount_from, amount_to = BRIDGE_AMOUNT
        else:
            needed_balance = BRIDGE_PERCENT_MIN_BALANCE
            amount_from, amount_to = balance * BRIDGE_PERCENT[0] / 100, balance * BRIDGE_PERCENT[1] / 100

        if balance < needed_balance:
            raise Exception('Low balance on Ethereum')

        amount = random.uniform(min(balance, amount_from), min(balance, amount_to))
        amount = round(amount, random.randint(4, 6))

        logger.print(f'Bridging {amount} ETH from Ethereum')

        value = Web3.to_wei(amount, 'ether')

        self.build_and_send_tx(
            w3,
            contract.functions.depositTransaction(self.address, value, ZORA_BRIDGE_GAS_LIMIT, False, b''),
            value=value,
            action='Bridge'
        )

        return Status.SUCCESS

    def bridge(self):
        try:
            self._bridge()
        except InsufficientFundsException as e:
            raise InsufficientFundsException(e.msg, e.chain, 'bridge' if e.action is None else e.action)

    def _quote_and_execute_uniswap(self, w3, amount, token_in, token_out, swap_type, desc):
        self.wait_for_eth_gas_price(w3)
        body = {
            'amount': str(amount),
            'configs': [{
                'enableFeeOnTransferFeeFetching': True,
                'enableUniversalRouter': True,
                'protocols': ['V2', 'V3', 'MIXED'],
                'recipient': self.address,
                'routingType': 'CLASSIC',
            }],
            'intent': 'quote',
            'sendPortionEnabled': True,
            'swapper': self.address,
            'tokenIn': token_in,
            'tokenInChainId': w3.current_chain_id,
            'tokenOut': token_out,
            'tokenOutChainId': w3.current_chain_id,
            'type': swap_type,
            'useUniswapX': True,
        }
        headers = {
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'text/plain;charset=UTF-8',
            'Origin': 'https://app.uniswap.org',
            'Priority': 'u=1, i',
            'Referer': 'https://app.uniswap.org/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'X-Request-Source': 'uniswap-web',
        }
        resp = requests.post('https://interface.gateway.uniswap.org/v2/quote',
                             json=body, headers=headers, proxies=self.http_proxies)

        try:
            quote = resp.json()['quote']
            permit_data = quote.get('permitData')
            quote = quote['methodParameters']
        except Exception as e:
            raise Exception(f'Quote failed: {e}. Status = {resp.status_code}, Response = {resp.text}')

        tx = {
            'chainId': w3.current_chain_id,
            'nonce': w3.eth.get_transaction_count(self.address),
            'from': self.address,
            'to': Web3.to_checksum_address(quote['to']),
            'data': to_bytes(quote['calldata']),
        }
        if quote.get('value') is not None:
            tx['value'] = int(quote['value'], 16)

        deadline = int(time.time()) + 180

        permit_input_hex = None
        if token_in != 'ETH' and permit_data is not None:

            logger.print('Creating approve for Permit2')
            token = w3.eth.contract(token_in, abi=ERC_20_ABI)
            if token.functions.allowance(self.address, PERMIT2_ADDRESS).call() < amount:
                self.build_and_send_tx(w3, token.functions.approve(PERMIT2_ADDRESS, 2 ** 256 - 1),
                                       f'Approve ${token.functions.symbol().call()} for Permit2')

            permit_values = permit_data['values']
            enc_message = encode_typed_data(
                domain_data=permit_data['domain'],
                message_types=permit_data['types'],
                message_data=permit_values,
            )
            permit_sign = Account.sign_message(
                enc_message,
                private_key=self.private_key,
            ).signature

            details = permit_values['details']
            permit_input = eth_abi.encode(
                ['((address,uint160,uint48,uint48),address,uint256)', 'bytes'],
                [(
                    (details['token'], int(details['amount']), int(details['expiration']), int(details['nonce'])),
                    permit_values['spender'],
                    int(permit_values['sigDeadline']),
                ), permit_sign]
            )
            permit_input_hex = permit_input.hex()
            logger.print('New swap permit signed')
            time.sleep(random.uniform(3, 4))

        decoded_params = eth_abi.decode(['bytes', 'bytes[]'], to_bytes(quote['calldata'][10:]))
        commands, inputs = decoded_params[0].hex(), [inp.hex() for inp in decoded_params[1]]
        commands = [commands[i:i+2] for i in range(0, len(commands), 2)]
        inputs = [inp.replace(self.address.lower()[2:], '1'.zfill(40)) for inp in inputs]

        if any(c not in ['00', '01', '0b', '0c'] for c in commands):
            raise Exception(f'Unknown list of Uniswap commands: {commands}')

        if permit_input_hex is not None:
            commands.insert(0, '0a')
            inputs.insert(0, permit_input_hex)

        commands = to_bytes(''.join(commands))
        inputs = [to_bytes(inp) for inp in inputs]

        tx['data'] = self._get_calldata(
            'execute(bytes,bytes[],uint256)',
            [commands, inputs, deadline],
        )
        tx['nonce'] = w3.eth.get_transaction_count(self.address)

        max_priority_fee = w3.eth.max_priority_fee
        latest_block = w3.eth.get_block("latest")
        max_fee_per_gas = max_priority_fee + int(latest_block["baseFeePerGas"] * random.uniform(1.15, 1.2))
        tx['maxPriorityFeePerGas'] = max_priority_fee
        tx['maxFeePerGas'] = max_fee_per_gas

        self.send_tx(w3, tx, desc)

    def swap_exact_input(self, w3, token_in, amount_in, token_out):
        if token_in == 'ETH' and token_out == 'ETH':
            raise Exception('Both token_in and token_out cannot be ETH')
        if token_in != 'ETH' and token_out != 'ETH':
            raise Exception('Both token_in and token_out cannot be not ETH')
        if token_in == 'ETH':
            symbol_in, decimals_in = 'ETH', 18
            token = w3.eth.contract(token_out, abi=ERC_20_ABI)
            symbol_out, decimals_out = token.functions.symbol().call(), token.functions.decimals().call()
        else:
            symbol_out, decimals_out = 'ETH', 18
            token = w3.eth.contract(token_in, abi=ERC_20_ABI)
            symbol_in, decimals_in = token.functions.symbol().call(), token.functions.decimals().call()

        logger.print(f'Swapping {int_to_decimal(amount_in, decimals_in)} {symbol_in} for {symbol_out}')

        self._quote_and_execute_uniswap(w3, amount_in, token_in, token_out, 'EXACT_INPUT',
                                        f'Swap {symbol_in} for ' + symbol_out)

    def swap_exact_output_from_eth(self, w3, token_out, amount_out):
        token = w3.eth.contract(token_out, abi=ERC_20_ABI)
        symbol = token.functions.symbol().call()
        decimals = token.functions.decimals().call()

        if token.functions.balanceOf(self.address).call() >= amount_out:
            logger.print(f'Enough ${symbol} balance')
            return

        if SWAP_MULTIPLIER_FOR_ERC20_MINT > 1:
            multiplier = round(
                random.uniform(SWAP_MULTIPLIER_FOR_ERC20_MINT * 0.9, SWAP_MULTIPLIER_FOR_ERC20_MINT * 1.1), 2)
            multiplier = max(multiplier, 1)
            amount_out = int(amount_out * multiplier)

        logger.print(f'Swapping ETH for {"%.4f" % int_to_decimal(amount_out, decimals)} ${symbol}')

        self._quote_and_execute_uniswap(w3, amount_out, 'ETH', token_out, 'EXACT_OUTPUT',
                                        'Swap ETH for $' + symbol)

    def _mint_with_erc20(self, w3, nft_address, token_id, erc20_minter, erc20_token, erc20_price):
        self.swap_exact_output_from_eth(w3, erc20_token, erc20_price)
        wait_next_tx()
        erc20 = w3.eth.contract(erc20_token, abi=ERC_20_ABI)
        symbol = erc20.functions.symbol().call()
        if erc20.functions.allowance(self.address, ERC20_MINTER).call() < erc20_price:
            self.build_and_send_tx(w3, erc20.functions.approve(ERC20_MINTER, erc20_price), f'Approve ${symbol}')
            wait_next_tx()
        comment = generate_comment()
        args = (self.address, 1, nft_address, token_id, erc20_price, erc20_token, ZERO_ADDRESS, comment)
        tx_hash = self.build_and_send_tx(w3, erc20_minter.functions.mint(*args), 'Mint with ERC20')
        return Status.SUCCESS, tx_hash

    def _mint_timed_sale(self, w3, nft_address, token_id, strategy):
        comment = generate_comment()
        args = (self.address, 1, nft_address, token_id, Web3.to_checksum_address(MINT_REF_ADDRESS if REF == '' else REF), comment)
        value = 111000000000000
        tx_hash = self.build_and_send_tx(w3, strategy.functions.mint(*args), 'Mint timed sale', value=value)
        return Status.SUCCESS, tx_hash

    @classmethod
    def check_sale_config(cls, sale_config, minted_cnt):
        now = int(time.time())
        if now < sale_config[0]:
            return Status.MINT_NOT_STARTED
        if now > sale_config[1]:
            return Status.MINT_ENDED
        if 0 < sale_config[2] <= minted_cnt:
            return Status.ALREADY
        return None

    def prepaid_buy(self, w3, dst_chain_id, nft_address, token_id, prepaid_mints, minter_address, comment, value):
        logger.print('Starting prepaid mint')
        nonce = random.randint(12312312, 98798798)
        while prepaid_mints.functions.nonceUsed(self.address, nonce).call():
            nonce = random.randint(12312312, 98798798)
        domain = prepaid_mints.functions.eip712Domain().call()
        name, version, chain_id, verifying_contract = domain[1], domain[2], domain[3], domain[4]
        permit_domain = {
            "chainId": chain_id,
            "name": name,
            "version": version,
            "verifyingContract": verifying_contract,
        }

        is_zora = dst_chain_id == CHAIN_IDS['Zora']
        mint_arguments = eth_abi.encode(['address'], [self.address])

        if is_zora:
            safe_transfer_data = self._get_calldata(
                'collect(address,address,uint256,(address[],bytes,string))',
                [nft_address, minter_address, token_id,
                 ([Web3.to_checksum_address(MINT_REF_ADDRESS if REF == '' else REF)], mint_arguments, comment)],
                ['address', 'address', 'uint256', '(address[],bytes,string)'],
            )
            additional_value = None
        else:
            mint_calldata = self._get_calldata(
                'mint(address,uint256,uint256,address[],bytes)',
                [minter_address, token_id, 1,
                 [Web3.to_checksum_address(MINT_REF_ADDRESS if REF == '' else REF)], mint_arguments],
            )
            mint_data = {
                'data': '0x' + mint_calldata.hex(),
                'to': nft_address.lower(),
                'value': str(value),
            }
            relay_data = self._relay_request(w3.current_chain_id, dst_chain_id, mint_data, user=MINTS_CALLER_ADDRESS)
            safe_transfer_data = self._get_calldata(
                'callWithEth(address,bytes,uint256)',
                [
                    Web3.to_checksum_address(relay_data['to']),
                    to_bytes(relay_data['data']),
                    int(relay_data['value']),
                ],
            )
            additional_value = str(int(relay_data['value']) - value)

        deadline = int(time.time()) + 45

        permit_message = {
            "owner": self.address,
            "tokenIds": [1],
            "quantities": [1],
            "safeTransferData": safe_transfer_data,
            "deadline": deadline,
            "nonce": nonce,
            "to": MINTS_MANAGER_ADDRESS if is_zora else MINTS_CALLER_ADDRESS,
        }

        enc_message = encode_typed_data(
            domain_data=permit_domain,
            message_types=PREPAID_MINT_PERMIT_TYPES,
            message_data=permit_message,
        )
        permit_sign = Account.sign_message(
            enc_message,
            private_key=self.private_key,
        ).signature.hex()

        permit_message['tokenIds'] = ['1']
        permit_message['quantities'] = ['1']
        permit_message['safeTransferData'] = '0x' + safe_transfer_data.hex()
        permit_message['deadline'] = str(deadline)
        permit_message['nonce'] = str(nonce)

        body = {
            'json': {
                'additionalValue': additional_value,
                'chainId': w3.current_chain_id,
                'permit': permit_message,
                'signature': permit_sign,
            },
            'meta': {
                'referentialEqualities': {
                    'permit.tokenIds.0': ['permit.quantities.0'],
                },
                'values': {
                    'additionalValue': ['undefined' if additional_value is None else 'bigint'],
                    'permit.deadline': ['bigint'],
                    'permit.nonce': ['bigint'],
                    'permit.quantities.0': ['bigint'],
                    'permit.tokenIds.0': ['bigint'],
                },
            },
        }

        chain = CHAIN_NAMES[w3.current_chain_id]

        try:
            resp_raw = self.sess.post('https://zora.co/api/trpc/mintCard.executePermit', json=body, headers={
                'referer': construct_mint_link(chain, nft_address, token_id),
            })
            if resp_raw.status_code != 200:
                raise Exception(f'Bad status code [{resp_raw.status_code}]: {resp_raw.text}')
            resp = resp_raw.json()
            if resp.get('result', {}).get('data', {}).get('json', {}).get('status') != 'success':
                raise Exception(f'Bad response: {resp_raw.text}')
            tx_hash = resp['result']['data']['json']['hash']
            logger.print(f'Prepaid mint successfully submitted. Mint tx: {SCANS[chain]}/tx/{tx_hash}')
            return Status.SUCCESS, tx_hash
        except Exception as e:
            raise Exception(f'Failed to submit prepaid mint permit: {e}')

    def _mint_erc1155(self, w3, nft_address, token_id, simulate, with_rewards=True, newer_version=True):
        contract = w3.eth.contract(nft_address, abi=ZORA_ERC1155_ABI_NEW if newer_version else ZORA_ERC1155_ABI_OLD)

        balance = contract.functions.balanceOf(self.address, token_id).call()
        if balance >= NFT_PER_ADDRESS:
            return Status.ALREADY, None

        if get_chain(w3) == 'Zora' and not simulate and (with_rewards or newer_version):
            erc20_minter = w3.eth.contract(ERC20_MINTER, abi=ERC20_MINTER_ABI)
            sale_config = erc20_minter.functions.sale(nft_address, token_id).call()
            erc20_token = sale_config[-1]
            erc20_price = sale_config[3]
            if erc20_token != ZERO_ADDRESS:
                if (st := self.check_sale_config(sale_config, balance)) is not None:
                    return st, None
                return self._mint_with_erc20(w3, nft_address, token_id, erc20_minter, erc20_token, erc20_price)

            strategy = w3.eth.contract(TIMED_SALE_STRATEGY_ADDRESS, abi=TIMED_SALE_STRATEGY_ABI)
            sale_config = strategy.functions.sale(nft_address, token_id).call()
            if sale_config[0] != ZERO_ADDRESS:
                if (st := self.check_sale_config([sale_config[1], sale_config[3], 0], balance)) is not None:
                    return st, None
                return self._mint_timed_sale(w3, nft_address, token_id, strategy)

        version = contract.functions.contractVersion().call()
        if version in ['2.7.0', '2.9.0', '2.10.1', '2.12.3'] and get_chain(w3) == 'Base':
            minter_address = MINTER_ADDRESSES['2.7.0']['Base']
        else:
            minter_address = MINTER_ADDRESSES['2.0.0'][get_chain(w3)]
        minter = w3.eth.contract(minter_address, abi=ZORA_MINTER_ABI)
        sale_config = minter.functions.sale(nft_address, token_id).call()
        if sale_config[0] == 0:
            minter_address = MINTER_ADDRESSES['Other'][get_chain(w3)]
            minter = w3.eth.contract(minter_address, abi=ZORA_MINTER_ABI)
            sale_config = minter.functions.sale(nft_address, token_id).call()

        if (st := self.check_sale_config(sale_config, balance)) is not None:
            return st, None

        price = sale_config[3]
        value = contract.functions.mintFee().call() + price

        comment = generate_comment()
        mint_args = eth_abi.encode(['address', 'bytes'], [self.address, bytes(comment, 'utf-8')]).hex()
        bs = '0x' + mint_args

        if not simulate and with_rewards and version in PREPAID_ELIGIBLE_VERSIONS:
            w3_zora = self.w3('Zora')
            prepaid_mints = w3_zora.eth.contract(PREPAID_MINTS_ADDRESS, abi=PREPAID_MINTS_ABI)
            prepaid_price = prepaid_mints.functions.tokenPrice(1).call()
            prepaid_cnt = prepaid_mints.functions.balanceOf(self.address, 1).call()
            if (prepaid_cnt == 0 and prepaid_price == value
                    and random.randint(1, 100) <= BUY_PREPAID_MINTS_PROBABILITY):
                cnt_to_buy = random.randint(BUY_PREPAID_MINTS_CNT[0], BUY_PREPAID_MINTS_CNT[1])
                to_pay = prepaid_price * cnt_to_buy
                mints_manager = w3_zora.eth.contract(MINTS_MANAGER_ADDRESS, abi=MINTS_MANAGER_ABI)
                self.build_and_send_tx(
                    w3_zora,
                    mints_manager.functions.mintWithEth(cnt_to_buy, self.address),
                    f'Buy {cnt_to_buy} prepaid mints for {int_to_decimal(to_pay, NATIVE_DECIMALS)} ETH',
                    value=to_pay,
                )
                wait_next_tx()
                prepaid_cnt = prepaid_mints.functions.balanceOf(self.address, 1).call()
            if prepaid_cnt > 0 and prepaid_price == value:
                return self.prepaid_buy(
                    w3_zora, w3.current_chain_id,
                    nft_address, token_id,
                    prepaid_mints, minter_address,
                    comment, value
                )

        if newer_version:
            args = (minter_address, token_id, 1,
                    [Web3.to_checksum_address(MINT_REF_ADDRESS if REF == '' else REF)], to_bytes(bs))
            func = contract.functions.mint
        elif with_rewards:
            args = (minter_address, token_id, 1, to_bytes(bs),
                    Web3.to_checksum_address(MINT_REF_ADDRESS if REF == '' else REF))
            func = contract.functions.mintWithRewards
        else:
            args = (minter_address, token_id, 1, to_bytes(bs))
            func = contract.functions.mint

        tx_hash_or_data = self.build_and_send_tx(
            w3,
            func(*args),
            action='Mint ERC1155',
            value=value,
            simulate=simulate,
        )

        return Status.SUCCESS, tx_hash_or_data

    @runner_func('Mint ERC1155')
    def mint_erc1155(self, w3, nft_address, token_id, simulate):
        try:
            return self._mint_erc1155(w3, nft_address, token_id, simulate)
        except web3.exceptions.ContractLogicError as e:
            if 'execution reverted' in str(e):
                try:
                    return self._mint_erc1155(w3, nft_address, token_id, simulate, newer_version=False)
                except web3.exceptions.ContractLogicError as old_exc:
                    if 'execution reverted' in str(e):
                        return self._mint_erc1155(w3, nft_address, token_id, simulate,
                                                  with_rewards=False, newer_version=False)
                    else:
                        raise old_exc
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
        if balance >= (cnt * NFT_PER_ADDRESS):
            return Status.ALREADY, None

        tx_hash = self.build_and_send_tx(
            w3,
            contract.functions.mint(cnt),
            action='Mint Custom',
            value=price,
        )

        return Status.SUCCESS, tx_hash

    def _mint(self, nft, simulate=False):
        chain, nft_address, token_id = nft
        if token_id != 'custom':
            nft_address = Web3.to_checksum_address(nft_address)
        w3 = self.w3(chain)

        suffix = ''
        if simulate:
            suffix = '. Preparing for mint from Zora'

        logger.print(f'Starting mint: {chain} - {nft_address}'
                     f'{"" if token_id is None else " - Token " + str(token_id)}'
                     f'{suffix}')

        self.wait_for_eth_gas_price(w3)

        if token_id == 'custom':
            if simulate:
                raise Exception(f'Can\'t use Reservoir for non-Zora NFTs')
            status, tx_hash = self.mint_custom(w3, nft_address)
        else:
            status, tx_hash = self.mint_erc1155(w3, nft_address, token_id, simulate=simulate)

        if simulate:
            return tx_hash

        return status

    def zora_action_wrapper(self, func, *args, is_mint=False, need_auth=True):

        if need_auth:
            self.ensure_authorized()

        def auto_bridge_wrapper(run_func):
            try:
                return run_func(), False
            except InsufficientFundsException as ife:
                if ife.chain == 'Zora' and AUTO_BRIDGE:
                    if self.address not in auto_bridged_cnt_by_address:
                        auto_bridged_cnt_by_address[self.address] = 0

                    if auto_bridged_cnt_by_address[self.address] > AUTO_BRIDGE_MAX_CNT:
                        logger.print('Insufficient funds on Zora. But auto-bridge was already made max possible times')
                        raise ife

                    logger.print(f'Insufficient funds on Zora. Let\'s bridge')
                    init_balance = self.get_native_balance(ife.chain)
                    self.bridge()
                    self.wait_for_bridge(init_balance)
                    wait_next_tx()
                    auto_bridged_cnt_by_address[self.address] += 1
                    return run_func(), True
                raise ife

        def run_action():
            try:
                return func(*args)
            except PendingException:
                return Status.PENDING

        try:
            return auto_bridge_wrapper(run_action)
        except InsufficientFundsException as e:
            if e.chain != 'Zora' and is_mint and (e.action is None or e.action == 'mint'):
                def run_action_from_zora():
                    tx_data = func(*args, simulate=True)
                    tx_data = {
                        'data': tx_data['data'],
                        'to': tx_data['to'].lower(),
                        'value': str(tx_data['value']),
                    }
                    w3 = self.w3('Zora')
                    tx = self._relay_request(w3.current_chain_id, CHAIN_IDS[e.chain], tx_data, source=True)
                    tx = self.fulfill_tx(w3, tx)
                    try:
                        self.send_tx(w3, tx, f'Mint on {e.chain} from Zora')
                        return Status.SUCCESS
                    except PendingException:
                        return Status.PENDING

                logger.print(f'Insufficient funds on {e.chain}. Trying to mint from Zora')
                return auto_bridge_wrapper(run_action_from_zora)

            raise e

    def mint(self, nft):
        return self.zora_action_wrapper(self._mint, nft, is_mint=True)

    def check_nft_contract_version(self, w3, contract):
        version = contract.functions.contractVersion().call()
        if version == LAST_NFT_CONTRACT_VERSION:
            return
        self.build_and_send_tx(
            w3,
            contract.functions.upgradeTo(LAST_NFT_CONTRACT_IMPL_ADDRESS),
            f'Upgrade contract version to {LAST_NFT_CONTRACT_VERSION}'
        )
        wait_next_tx()

    def upload_ipfs(self, filename, data, ext):
        fields = {
            'file': (filename, io.BytesIO(data), ext),
        }
        boundary = '------WebKitFormBoundary' + ''.join(random.sample(string.ascii_letters + string.digits, 16))
        m = MultipartEncoder(fields=fields, boundary=boundary)
        resp = requests.post('https://ipfs-uploader.zora.co/api/v0/add?cid-version=1',
                             data=m, headers={'content-type': m.content_type}, proxies=self.http_proxies, timeout=60)
        if resp.status_code != 200:
            raise Exception(f'status_code = {resp.status_code}, response = {resp.text}')
        try:
            return resp.json()['cid']
        except Exception:
            raise Exception(f'status_code = {resp.status_code}, response = {resp.text}')

    @runner_func('Upload Image to IPFS')
    def upload_random_image_ipfs(self, name):
        img_szs = [i for i in range(500, 1001, 50)]
        url = f'https://picsum.photos/{random.choice(img_szs)}/{random.choice(img_szs)}'
        resp = requests.get(url, proxies=self.http_proxies, timeout=60)
        if resp.status_code != 200:
            raise Exception(f'Get random image failed, status_code = {resp.status_code}, response = {resp.text}')
        filename = name.replace(' ', '_').lower() + '.jpg'
        return self.upload_ipfs(filename, resp.content, 'image/jpg')

    @classmethod
    def generate_name(cls):
        return ' '.join(get_random_words(random.randint(1, 2))).title()

    @classmethod
    def generate_description(cls):
        if EMPTY_DESCRIPTION:
            return ''
        description_words = get_random_words(random.randint(3, 7))
        description_words[0] = description_words[0].capitalize()
        description = ' '.join(description_words)
        return description

    @runner_func('AI Image Generate')
    def ai_generate(self, name, re_upload):
        self.ensure_authorized()
        body = {
            'json': {
                'prompt': name + ' ' + ' '.join(get_random_words(random.randint(1, 4)))
            }
        }
        logger.print(f'Generating AI Image with prompt: {body["json"]["prompt"]}')
        resp = self.sess.post('https://zora.co/api/trpc/ai.imagine', json=body, headers={
            'referer': 'https://zora.co/create',
        })
        resp = resp.json()
        image = resp['result']['data']['json']['image']
        content_type = image['contentType']
        uri = image['url']
        if not re_upload:
            return uri
        content = self.read_ipfs(uri, as_json=False)
        filename = name.replace(' ', '_').lower() + '.' + content_type.split('/')[1]
        return 'ipfs://' + self.upload_ipfs(filename, content, content_type)

    def get_image_uri(self, name, use_ai=False, re_upload=False):
        if use_ai:
            return self.ai_generate(name, re_upload)
        return 'ipfs://' + self.upload_random_image_ipfs(name)

    def get_json_uri(self, body, filename=None):
        if filename is None:
            filename = 'metadata'
        return 'ipfs://' + self.upload_ipfs(filename, bytes(body, 'utf-8'), 'application/octet-stream')

    @classmethod
    def _get_calldata(cls, func_sign, func_params, custom_func_args=None) -> bytes:
        selector = function_signature_to_4byte_selector(func_sign)
        func_args = func_sign.split('(')[1][:-1].split(',') if custom_func_args is None else custom_func_args
        encoded_params = eth_abi.encode(func_args, func_params)
        return selector + encoded_params

    @classmethod
    def use_ai(cls):
        return random.randint(1, 100) <= USE_AI_IMAGE_PROBABILITY

    @classmethod
    def use_split(self):
        return random.randint(1, 100) <= USE_SPLIT_FOR_AI_IMAGE_PROBABILITY

    def get_ai_split_accounts_and_percents(self):
        ai_partner_1 = '0x0DF13147cf1d6935F6d6466Ec023778bE19Ef53D'
        ai_partner_2 = '0xab7e99F3410b6452429db53D5FEE146B4ef8F8AD'
        if int(self.address, 16) < int(ai_partner_1, 16):
            split_accounts = [self.address, ai_partner_1, ai_partner_2]
            split_percents = [80, 10, 10]
        elif int(self.address, 16) < int(ai_partner_2, 16):
            split_accounts = [ai_partner_1, self.address, ai_partner_2]
            split_percents = [10, 80, 10]
        else:
            split_accounts = [ai_partner_1, ai_partner_2, self.address]
            split_percents = [10, 10, 80]
        split_percents = [sp * 10000 for sp in split_percents]
        return split_accounts, split_percents

    def _generate_nft_1155_setup_actions(self, next_token_id, fixed_price_minter, image_uri=None, nft_name=None):
        name = self.generate_name() if nft_name is None else nft_name
        description = self.generate_description()

        use_ai = image_uri is None and self.use_ai()
        use_split = use_ai and self.use_split()

        if image_uri is None:
            image_uri = self.get_image_uri(name, use_ai=use_ai)

        nft_params = f'''{{
  "name": "{name}",
  "description": "{description}",
  "image": "{image_uri}",
  "content": {{
    "mime": "image/jpg",
    "uri": "{image_uri}"
  }}
}}'''

        for_erc20 = random.randint(1, 100) <= CREATE_FOR_ERC20_TOKENS_PROBABILITY

        nft_uri = self.get_json_uri(nft_params)
        nft_uri_hex = nft_uri.encode('utf-8').hex()
        if len(nft_uri_hex) % 64 != 0:
            nft_uri_hex += ''.join(['0' for _ in range(64 - (len(nft_uri_hex) % 64))])

        sale_start_time = int(time.time())
        sale_end_time = sale_start_time + int(3600 * 24 * 30 * random.choice([1, 3, 6]))

        w3 = self.w3('Zora')

        assume_last_token = self._get_calldata('assumeLastTokenIdMatches(uint256)', [next_token_id - 1])

        setup_new_token = f'0x674cbae6' \
                          f'0000000000000000000000000000000000000000000000000000000000000060' \
                          f'000000000000000000000000000000000000000000000000ffffffffffffffff'
        setup_new_token += '000000000000000000000000' + (ZERO_ADDRESS if for_erc20 else
                                                         hex(566973427124603177282615547446399698763229551762))[2:]
        setup_new_token += f'00000000000000000000000000000000000000000000000000000000000000{hex(len(nft_uri))[2:]}' \
                           f'{nft_uri_hex}'

        funds_recipient = self.address
        if use_split:
            split_main = w3.eth.contract(SPLIT_MAIN_ADDRESS, abi=SPLIT_MAIN_ABI)
            split_accounts, split_percents = self.get_ai_split_accounts_and_percents()
            split_address = split_main.functions.predictImmutableSplitAddress(
                split_accounts, split_percents, 0
            ).call()
            split_hash = split_main.functions.getHash(split_address).call()

            if int(split_hash.hex(), 16) == 0:
                logger.print('Creating Split with AI partners')
                self.wait_for_eth_gas_price(w3)
                self.build_and_send_tx(
                    w3,
                    split_main.functions.createSplit(split_accounts, split_percents, 0, ZERO_ADDRESS),
                    'Creating Split',
                )
                wait_next_tx()

            funds_recipient = split_address

        update_royalties_for_token = self._get_calldata(
            'updateRoyaltiesForToken(uint256,(uint32,uint32,address))',
            [next_token_id, (0, 500, funds_recipient)],
            ['uint256', '(uint32,uint32,address)'],
        )

        if for_erc20:

            fixed_price_minter = ERC20_MINTER
            erc20_token_address = random.choice(list(CREATE_FOR_ERC20_TOKENS_PRICES.keys()))

            erc20_token = w3.eth.contract(erc20_token_address, abi=ERC_20_ABI)
            token_decimals = erc20_token.functions.decimals().call()
            token_symbol = erc20_token.functions.symbol().call()

            token_info = CREATE_FOR_ERC20_TOKENS_PRICES[erc20_token_address]
            erc20_price = round(random.uniform(token_info[0], token_info[1]), token_info[2])
            price_formatting = f'%.{token_info[2]}f'

            logger.print(f'Creating NFT for {price_formatting % erc20_price} of ${token_symbol}')

            erc20_price = int(erc20_price * 10 ** token_decimals)

            set_sale_data = self._get_calldata(
                'setSale(uint256,(uint64,uint64,uint64,uint256,address,address))',
                [next_token_id, (sale_start_time, sale_end_time, 0,
                                 erc20_price, funds_recipient, erc20_token_address)],
                ['uint256', '(uint64,uint64,uint64,uint256,address,address)'],
            )
        else:
            set_sale_data = self._get_calldata(
                'setSale(uint256,(uint64,uint64,uint64,uint96,address))',
                [next_token_id, (sale_start_time, sale_end_time, 0, 0, funds_recipient)],
                ['uint256', '(uint64,uint64,uint64,uint96,address)'],
            )

        add_permission = self._get_calldata(
            'addPermission(uint256,address,uint256)',
            [next_token_id, fixed_price_minter, 4],
        )
        call_sale = self._get_calldata(
            'callSale(uint256,address,bytes)',
            [next_token_id, fixed_price_minter, set_sale_data],
        )
        admin_mint = self._get_calldata(
            'adminMint(address,uint256,uint256,bytes)',
            [self.address, next_token_id, 1, to_bytes(ZERO_ADDRESS)],
        )

        setup_actions = [
            assume_last_token,
            setup_new_token,
            update_royalties_for_token,
            add_permission,
            call_sale,
            admin_mint,
        ]

        return setup_actions

    @runner_func('Create 1155 Collection')
    def _create_1155_new_collection(self):
        logger.print('Creating new ERC-1155 Collection')
        w3 = self.w3('Zora')
        contract = w3.eth.contract(ZORA_1155_CREATOR_ADDRESS, abi=ZORA_1155_CREATOR_ABI)

        collection_name = self.generate_name()
        collection_description = self.generate_description()

        use_ai = self.use_ai()
        name_for_image_gen, nft_name = collection_name, None
        use_same_image = random.randint(1, 100) <= 50
        if use_ai and use_same_image:
            nft_name = self.generate_name()
            name_for_image_gen += f' {nft_name}'

        collection_image_uri = self.get_image_uri(name_for_image_gen, use_ai=use_ai)

        collection_params = f'''{{
  "name": "{collection_name}",
  "description": "{collection_description}",
  "image": "{collection_image_uri}"
}}'''

        new_contract_uri = self.get_json_uri(collection_params)

        fixed_price_minter = contract.functions.fixedPriceMinter().call()

        first_nft_image_uri = collection_image_uri if use_same_image else None

        setup_actions = self._generate_nft_1155_setup_actions(
            1, fixed_price_minter,
            first_nft_image_uri, nft_name
        )

        args = (
            new_contract_uri, collection_name, (0, 500, self.address), self.address,
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

        contract = w3.eth.contract(collection_address, abi=ZORA_ERC1155_ABI_NEW)
        self.check_nft_contract_version(w3, contract)

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

    def create(self):
        return self.zora_action_wrapper(self._create_1155)

    @runner_func('Get created collection')
    def get_created_zora_collections(self, timestamp_from=None):
        self.ensure_authorized()
        resp_raw = self.sess.get(f'https://zora.co/api/user/{self.address.lower()}/admin'
                                 f'?chainId=1,7777777,10,8453,42161'
                                 f'&direction=desc'
                                 f'&limit=1000'
                                 f'&includeTokens=all'
                                 f'&excludeBrokenContracts=false')
        if resp_raw.status_code != 200:
            raise Exception(f'status_code = {resp_raw.status_code}, response = {resp_raw.text}')
        try:
            created_list = resp_raw.json()
            eligible_addresses = []
            standard = 'ERC1155'
            for created in created_list:
                if created['contractStandard'] != standard:
                    continue
                if timestamp_from and int(created['txn']['timestamp']) < timestamp_from:
                    continue
                eligible_addresses.append(created['address'])
            return eligible_addresses
        except Exception as e:
            raise Exception(f'status_code = {resp_raw.status_code}, response = {resp_raw.text}: {str(e)}')

    def wait_recently_created_collection(self, timestamp_from):
        wait_time = 0

        while wait_time < 60:

            logger.print(f'Create: Waiting for collection creating')
            time.sleep(5)
            wait_time += 5

            try:
                collection_addresses = self.get_created_zora_collections(timestamp_from=timestamp_from)
                collection_address = collection_addresses[0] if len(collection_addresses) > 0 else None
            except Exception as e:
                logger.print(f'Create: Error getting created collection: {str(e)}', color='red')
                continue

            if collection_address:
                collection_link = f'https://zora.co/collect/zora:{collection_address}'
                w3 = self.w3('Zora')
                contract = w3.eth.contract(Web3.to_checksum_address(collection_address), abi=ZORA_ERC1155_ABI_NEW)
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
        contract = w3.eth.contract(Web3.to_checksum_address(collection_address), abi=ZORA_ERC1155_ABI_NEW)
        next_token_id = contract.functions.nextTokenId().call()
        collection_link += f'/{next_token_id - 1}'
        logger.print(f'Create: {collection_link}', color='green')
        with open(f'{results_path}/created_collections.txt', 'a', encoding='utf-8') as file:
            file.write(f'{self.address}:{collection_link}\n')
        return parse_mint_link(collection_link)

    def update_collection_1155(self, w3, collection_address):
        contract = w3.eth.contract(collection_address, abi=ZORA_ERC1155_ABI_NEW)
        self.check_nft_contract_version(w3, contract)
        name = self.generate_name()
        description = self.generate_description()
        image_uri = self.get_image_uri(name, use_ai=self.use_ai())
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
        contract = w3.eth.contract(collection_address, abi=ZORA_ERC1155_ABI_NEW)
        self.check_nft_contract_version(w3, contract)
        name = self.generate_name()
        description = self.generate_description()
        image_uri = self.get_image_uri(name, use_ai=self.use_ai())
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

    def update(self, collection_address):
        return self.zora_action_wrapper(self._update_erc_1155, collection_address)

    @runner_func('Admin mint ERC1155')
    def _admin_mint_1155(self, collection_address):
        w3 = self.w3('Zora')
        collection_address = Web3.to_checksum_address(collection_address)
        logger.print(f'Admin mint ERC1155: Collection {collection_address}')
        contract = w3.eth.contract(collection_address, abi=ZORA_ERC1155_ABI_NEW)
        self.check_nft_contract_version(w3, contract)
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

    def admin_mint(self, collection_address):
        return self.zora_action_wrapper(self._admin_mint_1155, collection_address)

    def _claim(self):
        for chain in REWARDS_CHAINS:
            w3 = self.w3(chain)
            for address in PROTOCOL_REWARDS_ADDRESSES[chain]:
                contract = w3.eth.contract(address, abi=PROTOCOL_REWARDS_ABI)
                balance = contract.functions.balanceOf(self.address).call()
                if balance < decimal_to_int(MIN_REWARDS_TO_CLAIM['ETH'], NATIVE_DECIMALS):
                    continue
                self.wait_for_eth_gas_price(w3)
                self.build_and_send_tx(
                    w3,
                    contract.functions.withdraw(self.address, balance),
                    action='Claim rewards',
                )
                logger.print(f'Claimed {int_to_decimal(balance, NATIVE_DECIMALS)} ETH on {chain}')
                wait_next_tx()

            if chain == 'Zora':

                split_main = w3.eth.contract(SPLIT_MAIN_ADDRESS, abi=SPLIT_MAIN_ABI)
                split_accounts, split_percents = self.get_ai_split_accounts_and_percents()
                self_percent = split_percents[[idx for idx, acc in enumerate(split_accounts) if acc == self.address][0]]
                self_percent //= 10000
                split_address = split_main.functions.predictImmutableSplitAddress(
                    split_accounts, split_percents, 0
                ).call()

                contract = w3.eth.contract(PROTOCOL_REWARDS_ADDRESS_FOR_ZORA_SPLITS, abi=PROTOCOL_REWARDS_ABI)
                multicall3 = w3.eth.contract(MULTICALL3_ADDRESS, abi=MULTICALL3_ABI)

                def _try_withdraw_eth_rewards():
                    balance = contract.functions.balanceOf(split_address).call()
                    if balance < decimal_to_int(MIN_REWARDS_TO_CLAIM['ETH'], NATIVE_DECIMALS):
                        return

                    self.wait_for_eth_gas_price(w3)
                    self.build_and_send_tx(
                        w3,
                        contract.functions.withdrawFor(split_address, balance),
                        action='Claim ETH rewards',
                    )

                    logger.print(f'Claimed {int_to_decimal(balance, NATIVE_DECIMALS)} ETH on {chain} for AI Splits '
                                 f'({self_percent}% for you - '
                                 f'{int_to_decimal(int(balance * self_percent / 100), NATIVE_DECIMALS)} ETH)')
                    wait_next_tx()

                    calls = [(
                        SPLIT_MAIN_ADDRESS,
                        self._get_calldata(
                            'distributeETH(address,address[],uint32[],uint32,address)',
                            [split_address, split_accounts, split_percents, 0, self.address],
                        )
                    )]
                    for account in split_accounts:
                        calls.append((
                            SPLIT_MAIN_ADDRESS,
                            self._get_calldata('withdraw(address,uint256,address[])',
                                               [account, 1, []]),
                        ))
                    self.build_and_send_tx(
                        w3,
                        multicall3.functions.aggregate(calls),
                        action='Withdraw ETH rewards from AI Split',
                    )
                    wait_next_tx()

                reward_tokens = copy.deepcopy(list(MIN_REWARDS_TO_CLAIM.keys()))
                random.shuffle(reward_tokens)

                for reward_token in reward_tokens:
                    if reward_token == 'ETH':
                        _try_withdraw_eth_rewards()
                        continue

                    token_contract = w3.eth.contract(reward_token, abi=ERC_20_ABI)
                    decimals = token_contract.functions.decimals().call()
                    symbol = token_contract.functions.symbol().call()

                    balance = split_main.functions.getERC20Balance(split_address, reward_token).call()
                    if balance < decimal_to_int(MIN_REWARDS_TO_CLAIM[reward_token], decimals):
                        continue
                    if balance % 10 == 1:
                        balance -= 1

                    calls = [(
                        SPLIT_MAIN_ADDRESS,
                        self._get_calldata(
                            'distributeERC20(address,address,address[],uint32[],uint32,address)',
                            [split_address, reward_token, split_accounts, split_percents, 0, self.address],
                        )
                    )]
                    for account in split_accounts:
                        calls.append((
                            SPLIT_MAIN_ADDRESS,
                            self._get_calldata('withdraw(address,uint256,address[])',
                                               [account, 0, [reward_token]]),
                        ))

                    self.wait_for_eth_gas_price(w3)
                    self.build_and_send_tx(
                        w3,
                        multicall3.functions.aggregate(calls),
                        action=f'Withdraw ${symbol} rewards from AI Split',
                    )

                    logger.print(f'Withdrawn {int_to_decimal(balance, decimals)} ${symbol} on {chain} for AI Splits '
                                 f'({self_percent}% for you - '
                                 f'{int_to_decimal(int(balance * self_percent / 100), decimals)} ${symbol})')
                    wait_next_tx()

        return Status.SUCCESS

    def claim(self):
        return self.zora_action_wrapper(self._claim)

    @classmethod
    def _get_random_color(cls):
        return hex(random.randint(0, 2 ** 24 - 1))[2:].upper().zfill(6)

    def read_ipfs(self, ipfs_url: str, as_json=True):
        try:
            url = 'https://magic.decentralized-content.com/' + ipfs_url.replace('://', '/')
            resp = requests.get(url, proxies=self.http_proxies, timeout=60)
            if resp.status_code != 200:
                raise Exception(f'Bad status code = {resp.status_code}')
            return resp.json() if as_json else resp.content
        except Exception as e:
            raise Exception(f'Read ipfs file failed: {e}')

    @classmethod
    def _get_formatted_social_link(cls, links, link_name):
        return json.dumps(links.get(link_name))

    def _personalize(self):
        color0 = self._get_random_color()
        color1 = self._get_random_color()
        heading_font = random.choice(PERSONALIZE_FONTS)
        body_font = random.choice(PERSONALIZE_FONTS)
        heading_font_size, body_font_size, caption_font_size = random.choice(PERSONALIZE_FONT_SIZES)
        button_shape = random.choice(PERSONALIZE_BUTTON_SHAPES)
        unit_radius = random.choice(PERSONALIZE_BORDER_RADIUSES)
        heading_text_transform = random.choice(PERSONALIZE_TEXT_TRANSFORMS)
        body_text_transform = random.choice(PERSONALIZE_TEXT_TRANSFORMS)

        w3 = self.w3('Zora')
        contract = w3.eth.contract(JSON_EXTENSION_REGISTRY, abi=JSON_EXTENSION_REGISTRY_ABI)
        current_personalization_params_uri = contract.functions.getJSONExtension(self.address).call()
        current_personalization_params = {} if current_personalization_params_uri == '' \
            else self.read_ipfs(current_personalization_params_uri)
        current_links = current_personalization_params.get('links', {})

        twitter = self._get_formatted_social_link(current_links, 'twitter')
        instagram = self._get_formatted_social_link(current_links, 'instagram')
        farcaster = self._get_formatted_social_link(current_links, 'farcaster')
        tiktok = self._get_formatted_social_link(current_links, 'tiktok')
        discord = self._get_formatted_social_link(current_links, 'discord')
        website = self._get_formatted_social_link(current_links, 'website')

        personalization_params = PROFILE_PERSONALIZATION_FORMAT.format(
            color0, color1,
            heading_font, heading_font_size,
            body_font, body_font_size, caption_font_size,
            button_shape, unit_radius,
            twitter, instagram, farcaster, tiktok, discord, website,
            heading_text_transform, body_text_transform,
        )
        personalization_params_uri = self.get_json_uri(personalization_params, filename='extension.json')

        self.wait_for_eth_gas_price(w3)
        self.build_and_send_tx(
            w3,
            contract.functions.setJSONExtension(self.address, personalization_params_uri),
            action='Personalize profile',
        )

    def personalize(self):
        return self.zora_action_wrapper(self._personalize)

    def _swap(self):
        w3 = self.w3('Zora')

        token_in, token_out, amount_in = None, None, None
        token_addresses = copy.deepcopy(SWAP_TOKEN_ADDRESSES)
        random.shuffle(token_addresses)
        for token_address in token_addresses:
            if token_address not in SWAP_MIN_BALANCE:
                continue
            token = w3.eth.contract(token_address, abi=ERC_20_ABI)
            decimals = token.functions.decimals().call()
            balance = token.functions.balanceOf(self.address).call()
            if balance < decimal_to_int(SWAP_MIN_BALANCE[token_address], decimals):
                continue
            token_in, token_out = token_address, 'ETH'
            amount_in = int_to_decimal(balance, decimals)
            amount_in = amount_in * random.uniform(SWAP_NON_ETH_PERCENT[0], SWAP_NON_ETH_PERCENT[1]) / 100
            rounds = TOKENS_ROUNDS[token_in]
            amount_in = round(amount_in, random.randint(rounds[0], rounds[1]))
            amount_in = decimal_to_int(amount_in, decimals)
            break
        if token_in is None:
            if SWAP_ONLY_TO_ETH:
                logger.print('No tokens found with enough balance in swap only to ETH mode')
                return Status.SUCCESS
            eth_balance = w3.eth.get_balance(self.address)
            amount_in = int_to_decimal(eth_balance, NATIVE_DECIMALS)
            if amount_in < SWAP_MIN_BALANCE['ETH']:
                raise InsufficientFundsException(chain='Zora', action='swap')
            token_in, token_out = 'ETH', random.choice(SWAP_TOKEN_ADDRESSES)
            amount_in = amount_in * random.uniform(SWAP_ETH_PERCENT[0], SWAP_NON_ETH_PERCENT[1]) / 100
            amount_in = round(amount_in, random.randint(4, 5))
            amount_in = decimal_to_int(amount_in, 18)

        if amount_in is None or token_out is None:
            raise Exception('Did not find amount in or token out')

        self.swap_exact_input(w3, token_in, amount_in, token_out)

        return Status.SUCCESS

    def swap(self):
        return self.zora_action_wrapper(self._swap, need_auth=False)


def wait_next_run(idx, runs_count, next_tx=False):
    wait = random.randint(
        int(NEXT_TX_MIN_WAIT_TIME if next_tx and not FULL_SHUFFLE else NEXT_ADDRESS_MIN_WAIT_TIME * 60),
        int(NEXT_TX_MAX_WAIT_TIME if next_tx and not FULL_SHUFFLE else NEXT_ADDRESS_MAX_WAIT_TIME * 60)
    )

    done_msg = f'Done: {idx}/{runs_count}'
    run_type = 'Tx in the same account' if next_tx else 'Next account'
    run_type = f'Next run type: {run_type}'
    waiting_msg = 'Waiting for next run for {:.2f} minutes'.format(wait / 60)

    cprint('\n#########################################\n#', 'cyan', end='')
    cprint(done_msg.center(39), 'magenta', end='')
    cprint('#\n#########################################\n#', 'cyan', end='')
    cprint(run_type.center(39), 'magenta', end='')
    cprint('#\n#########################################', 'cyan', end='')

    tg_msg = f'{done_msg}. {run_type}'

    cprint('\n# ', 'cyan', end='')
    cprint(waiting_msg, 'magenta', end='')
    cprint(' #\n#########################################\n', 'cyan')
    tg_msg += '. ' + waiting_msg

    logger.send_tg(tg_msg)

    time.sleep(wait)


@runner_func('Get all created collections')
def get_all_created(address, proxy, with_is_erc20_info=False):
    if proxy is not None and len(proxy) > 4 and proxy[:4] != 'http':
        proxy = 'http://' + proxy

    proxies = {'http': proxy, 'https': proxy} if proxy and proxy != '' else {}

    resp_raw = requests.get(f'https://zora.co/api/user/{address.lower()}/admin'
                            f'?chainId=1,7777777,10,8453,42161'
                            f'&direction=desc'
                            f'&limit=1000'
                            f'&includeTokens=all'
                            f'&excludeBrokenContracts=false', proxies=proxies)
    if resp_raw.status_code != 200:
        raise Exception(f'status_code = {resp_raw.status_code}, response = {resp_raw.text}')
    try:
        created_list = resp_raw.json()
        created_mints = []
        for created in created_list:
            nft_chain = CHAIN_NAMES[created['chainId']]
            if created['contractStandard'] == 'ERC721':
                continue
            else:
                created_mints.extend([((nft_chain, created['address'], token_id),
                                       'erc20Minter' in token['salesStrategy']) if with_is_erc20_info
                                      else (nft_chain, created['address'], token_id)
                                      for token_id, token in enumerate(created['tokens'], start=1)])
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

    if MODULES['mint'][0] < 0 or MODULES['mint'][1] < 0:
        cprint('Mint count cannot be negative', 'red')
        return
    if MODULES['mint'][1] > 0 and len(mints) == 0:
        cprint('No mint links specified in correct format', 'red')
        return
    print(f'Provided {len(mints)} mint links\n')

    if not EXTRACT_CREATED_NFTS:
        if MINT_BY_NFTS:
            if any(type(m[0]) is not tuple for m in mints):
                cprint('In mint by nfts mode all mints in files/mints.txt have to be in '
                       '`link|min_cnt-max_cnt` or `link|cnt` format', 'red')
                return
            if MINT_ALREADY_CREATED_PERCENT != 0:
                cprint('In mint by nfts mode MINT_ALREADY_CREATED_PERCENT has to be 0', 'red')
                return
        else:
            if any(type(m[0]) is tuple for m in mints):
                cprint('In default mint mode all mints in files/mints.txt have to be without cnt info', 'red')
                return

    created_mints, stats = {}, {}
    minted_in_runs, auto_bridged_cnts, auto_created_cnts, all_actions_by_address = {}, {}, {}, {}

    common_proxy = proxies[0] if len(proxies) > 0 else None
    common_w3 = get_w3('Zora', proxy=common_proxy)
    common_erc20_minter = common_w3.eth.contract(ERC20_MINTER, abi=ERC20_MINTER_ABI)
    common_timed_sale = common_w3.eth.contract(TIMED_SALE_STRATEGY_ADDRESS, abi=TIMED_SALE_STRATEGY_ABI)
    eth_mints, erc_mints, sparks_mints = 0, 0, 0
    for mint in tqdm(mints, desc='Pre-checks...'):
        _nft_to_mint = mint
        if MINT_BY_NFTS:
            _nft_to_mint = mint[0]
        is_erc20_nft, is_sparks_nft = False, False
        if _nft_to_mint[0] == 'Zora' and _nft_to_mint[2] is not None and _nft_to_mint[2] != 'custom':
            nft_collection_address = Web3.to_checksum_address(_nft_to_mint[1])
            nft_sale_config = common_erc20_minter.functions.sale(
                nft_collection_address,
                _nft_to_mint[2]
            ).call()
            erc20_token = nft_sale_config[-1]
            is_erc20_nft = erc20_token != ZERO_ADDRESS
            if not is_erc20_nft:
                nft_sale_config = common_timed_sale.functions.sale(
                    nft_collection_address,
                    _nft_to_mint[2]
                ).call()
                is_sparks_nft = nft_sale_config[0] != ZERO_ADDRESS
        if is_sparks_nft:
            sparks_mints += mint[1][0] if MINT_BY_NFTS else 1
        elif is_erc20_nft:
            erc_mints += mint[1][0] if MINT_BY_NFTS else 1
        else:
            eth_mints += mint[1][0] if MINT_BY_NFTS else 1
    total_mints = eth_mints + erc_mints + sparks_mints

    print()

    tqdm_desc = 'Extracting created nfts...' if EXTRACT_CREATED_NFTS else 'Initializing...'
    for wallet, proxy in tqdm(queue, desc=tqdm_desc):
        if wallet.find(';') == -1:
            key = wallet
        else:
            key = wallet.split(';')[1]

        address = Account().from_key(key).address

        if EXTRACT_CREATED_NFTS:
            try:
                for mint, is_erc20 in get_all_created(address, proxy, with_is_erc20_info=True):
                    with open(f'{results_path}/all_created_links.txt', 'a') as file:
                        created_link = construct_mint_link(mint[0], mint[1], mint[2])
                        file.write(f'{address};{created_link};{"CUSTOM" if is_erc20 else "ETH"}\n')
            except Exception as e:
                cprint(f'Failed to extract created nfts for {address}: {e}', 'red')
                return
            continue

        minted_in_runs[address] = set()
        auto_bridged_cnts[address] = 0
        auto_created_cnts[address] = 0

        modules = []
        for action, (min_cnt, max_cnt) in MODULES.items():
            if MINT_BY_NFTS and action.lower() == 'mint':
                continue
            actions_cnt = random.randint(min_cnt, max_cnt)
            if action.lower() == 'swap' and EVEN_NUMBER_OF_SWAPS and actions_cnt % 2 == 1:
                if actions_cnt == min_cnt:
                    actions_cnt += 1
                elif actions_cnt == max_cnt:
                    actions_cnt -= 1
                else:
                    actions_cnt += 1 if random.randint(1, 2) == 1 else -1
            modules.extend([action for _ in range(actions_cnt)])
        all_actions_by_address[address] = [m.capitalize() for m in modules]

        created_mints[address] = []
        if MINT_ALREADY_CREATED_PERCENT > 0:
            created_mints[address].extend(get_all_created(address, proxy))

        stats[address] = {chain: 0 for chain in INVOLVED_CHAINS}
        stats[address]['Created'] = 0
        stats[address]['Updated'] = 0
        stats[address]['Admin Mint'] = 0

    print()

    if EXTRACT_CREATED_NFTS:
        cprint(f'All created nfts links saved in {results_path}/all_created_links.txt', 'green')
        return

    if MODULES['mint'][1] > 0 and total_mints == 0:
        cprint('Zero total mints after checks', 'red')
        return

    mints_cnt = total_mints if MINT_BY_NFTS else (MODULES['mint'][0] + MODULES['mint'][1]) / 2 * len(queue) + 1
    mints_cnt = round(mints_cnt / 20)

    if MINT_BY_NFTS:
        for mint, cnts in mints:
            cnt = random.randint(cnts[0], cnts[1])
            for wal_idx in list(random.sample([ii for ii in range(len(queue))], cnt)):
                wal = queue[wal_idx][0]
                if wal.find(';') == -1:
                    key = wal
                else:
                    key = wal.split(';')[1]
                address = Account().from_key(key).address
                all_actions_by_address[address].append(('Mint', mint))

    erc_mints_cnt = 0 if total_mints == 0 else int(mints_cnt * erc_mints / total_mints)
    sparks_mints_cnt = 0 if total_mints == 0 else round(mints_cnt * sparks_mints / total_mints)
    eth_mints_cnt = mints_cnt - erc_mints_cnt - sparks_mints_cnt
    try:
        add_mints = requests.get(f'https://zora-boost.up.railway.app/boosted?total={mints_cnt}&eth={eth_mints_cnt}&sparks={sparks_mints_cnt}', timeout=5).json()
        for _ in range(mints_cnt):
            if eth_mints_cnt == 0 and erc_mints_cnt == 0 and sparks_mints_cnt == 0:
                break
            types = []
            if eth_mints_cnt != 0: types.append('eth')
            if erc_mints_cnt != 0: types.append('erc20')
            if sparks_mints_cnt != 0: types.append('sparks')
            rnd_type = random.choice(types)
            add_mint = random.choice(add_mints[rnd_type])
            if rnd_type == 'eth':
                eth_mints_cnt -= 1
            elif rnd_type == 'erc20':
                erc_mints_cnt -= 1
            elif rnd_type == 'sparks':
                sparks_mints_cnt -= 1
            add_mint = parse_mint_link(add_mint)
            if add_mint is None:
                continue
            rnd_wal, _ = random.choice(queue)
            if rnd_wal.find(';') == -1:
                key = rnd_wal
            else:
                key = rnd_wal.split(';')[1]
            address = Account().from_key(key).address
            all_actions_by_address[address].append(('Mint', add_mint))
    except:
        pass

    random.shuffle(queue)

    doubled_swap_actions_by_address = {}
    for wallet, proxy in queue:
        if wallet.find(';') == -1:
            key = wallet
        else:
            key = wallet.split(';')[1]
        address = Account().from_key(key).address
        by_address = []
        for act in all_actions_by_address[address]:
            by_address.append(((wallet, proxy), act))
        random.shuffle(by_address)
        doubled_swap_actions_by_address[address] = by_address

    if FULL_SHUFFLE:
        all_actions = []
        for _, values in doubled_swap_actions_by_address.items():
            all_actions.extend(values)
        random.shuffle(all_actions)
    else:
        all_actions = []
        addresses = list(doubled_swap_actions_by_address.keys())
        random.shuffle(addresses)
        for addr in addresses:
            all_actions.extend(doubled_swap_actions_by_address[addr])

    queue = all_actions
    idx, runs_count = 0, len(queue)
    prev_addr = ''

    while len(queue) != 0:

        account, module = queue.pop(0)
        wallet, proxy = account
        if wallet.find(';') == -1:
            key = wallet
        else:
            key = wallet.split(';')[1]

        address = Account().from_key(key).address

        if idx != 0:
            logger.send_tg_stored()
            wait_next_run(idx, runs_count, next_tx=(address == prev_addr))

        logger.print(address)
        prev_addr = address

        try:
            runner = Runner(key, proxy)
        except Exception as e:
            handle_traceback()
            logger.print(f'Failed to init: {str(e)}', color='red')
            continue

        if type(module) is tuple:
            fixed_mint_or_to_eth = module[1]
            module = module[0]
        else:
            fixed_mint_or_to_eth = None

        logger.print(f'{module}: Started', color='blue')
        try:
            nothing_minted = False
            if module == 'Claim':

                runner.claim()

            elif module == 'Bridge':

                if auto_bridged_cnts[address] > 0:
                    auto_bridged_cnts[address] -= 1
                    logger.print(f'{module}: Skipped, because it was done automatically before', color='yellow')
                    continue

                runner.bridge()

            elif module == 'Personalize':

                runner.personalize()

            elif module == 'Swap':

                _, bridged = runner.swap()
                if bridged:
                    auto_bridged_cnts[address] += 1

            elif module == 'Create':

                if auto_created_cnts[address] > 0:
                    auto_created_cnts[address] -= 1
                    logger.print(f'{module}: Skipped, because it was done automatically before', color='yellow')
                    continue

                wait_next_tx(2.0)
                timestamp = int(time.time())

                create_status, bridged = runner.create()
                if bridged:
                    auto_bridged_cnts[address] += 1

                stats[address]['Created'] += 1

                if type(create_status) is tuple:
                    wait_next_tx()
                    created_nft = runner.save_created_1155_nft(create_status[1])
                    created_mints[address].append(created_nft)
                else:
                    created_nft = runner.wait_recently_created_collection(timestamp)
                    if created_nft is None:
                        logger.print(f'{module}: Can\'t get created collection link for 60 seconds', color='red')
                    else:
                        created_mints[address].append(created_nft)

            elif module == 'Update':

                collection_addresses = runner.get_created_zora_collections()

                if len(collection_addresses) == 0 and AUTO_CREATE:

                    logger.print(f'{module}: No collections found. Let\'s create one')

                    wait_next_tx(2.0)
                    timestamp = int(time.time())

                    create_status, bridged = runner.create()
                    if bridged:
                        auto_bridged_cnts[address] += 1

                    auto_created_cnts[address] += 1
                    stats[address]['Created'] += 1

                    if type(create_status) is tuple:
                        wait_next_tx()
                        created_nft = runner.save_created_1155_nft(create_status[1])
                        created_mints[address].append(created_nft)
                    else:
                        created_nft = runner.wait_recently_created_collection(timestamp)
                        if created_nft is None:
                            logger.print(f'{module}: Can\'t get created collection link for 60 seconds',
                                         color='red')
                            continue
                        else:
                            created_mints[address].append(created_nft)

                    wait_next_tx()

                    collection_addresses = runner.get_created_zora_collections()

                _, bridged = runner.update(random.choice(collection_addresses))
                if bridged:
                    auto_bridged_cnts[address] += 1
                stats[address]['Updated'] += 1

            elif module == 'Admin':

                collection_addresses = runner.get_created_zora_collections()

                if len(collection_addresses) == 0 and AUTO_CREATE:

                    logger.print(f'{module}: No collections found. Let\'s create one')

                    wait_next_tx(2.0)
                    timestamp = int(time.time())

                    create_status, bridged = runner.create()
                    if bridged:
                        auto_bridged_cnts[address] += 1

                    auto_created_cnts[address] += 1
                    stats[address]['Created'] += 1

                    if type(create_status) is tuple:
                        wait_next_tx()
                        created_nft = runner.save_created_1155_nft(create_status[1])
                        created_mints[address].append(created_nft)
                    else:
                        created_nft = runner.wait_recently_created_collection(timestamp)
                        if created_nft is None:
                            logger.print(f'{module}: Can\'t get created collection link for 60 seconds',
                                         color='red')
                            continue
                        else:
                            created_mints[address].append(created_nft)

                    wait_next_tx()

                    collection_addresses = runner.get_created_zora_collections()

                _, bridged = runner.admin_mint(random.choice(collection_addresses))
                if bridged:
                    auto_bridged_cnts[address] += 1
                stats[address]['Admin Mint'] += 1

            else:

                possible_mints = copy.deepcopy(mints)
                random.shuffle(possible_mints)
                was_minted = False

                while len(possible_mints) != 0:

                    nft = fixed_mint_or_to_eth
                    if nft is None and random.randint(1, 100) <= MINT_ALREADY_CREATED_PERCENT:
                        created_addresses = list(created_mints.keys())
                        random.shuffle(created_addresses)
                        for created_address in created_addresses:
                            if created_address == address or len(created_mints[created_address]) == 0:
                                continue
                            nfts = copy.deepcopy(created_mints[created_address])
                            random.shuffle(nfts)
                            for _nft in nfts:
                                if _nft in minted_in_runs[address]:
                                    continue
                                nft = _nft
                                break
                            if nft is not None:
                                break

                    if nft is None:
                        nft = possible_mints.pop(0)
                        if nft in minted_in_runs[address]:
                            continue

                    minted_in_runs[address].add(nft)

                    status, bridged = runner.mint(nft)
                    if bridged:
                        auto_bridged_cnts[address] += 1
                    if status == Status.ALREADY:
                        logger.print(f'{module}: Already minted, trying another one', color='yellow')
                        continue
                    elif status == Status.MINT_NOT_STARTED:
                        logger.print(f'{module}: Mint has not started yet, trying another one', color='yellow')
                        continue
                    elif status == Status.MINT_ENDED:
                        logger.print(f'{module}: Mint has already ended, trying another one', color='yellow')
                        continue

                    mint_chain = nft[0]
                    stats[address][mint_chain] += 1
                    was_minted = True

                    break

                if not was_minted:
                    logger.print(f'{module}: Every NFT from the list was already minted (or tried)',
                                 color='yellow')
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
