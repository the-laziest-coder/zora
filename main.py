import random
import time
import traceback
import web3.exceptions

from termcolor import cprint
from enum import Enum
from pathlib import Path
from datetime import datetime
from retry import retry
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


def decimal_to_int(d, n):
    return int(d * (10 ** n))


def int_to_decimal(i, n):
    return i / (10 ** n)


def readable_amount_int(i, n, d=2):
    return round(int_to_decimal(i, n), d)


def wait_next_tx():
    time.sleep(random.uniform(NEXT_TX_MIN_WAIT_TIME, NEXT_TX_MAX_WAIT_TIME))


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

    def __init__(self, private_key, proxy, nft_address):
        if proxy is not None and len(proxy) > 4 and proxy[:4] != 'http':
            proxy = 'http://' + proxy
        self.proxy = proxy

        self.w3s = {chain: get_w3(chain, proxy=self.proxy) for chain in INVOLVED_CHAINS}

        self.private_key = private_key
        self.address = Account().from_key(private_key).address

        self.nft_address = nft_address

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
            raise PendingException(chain, tx_hash, action_print[:-3])

    def get_native_balance(self, chain):
        return self.w3(chain).eth.get_balance(self.address)

    def build_and_send_tx(self, w3, func, action, value=0):
        return build_and_send_tx(w3, self.address, self.private_key, func, value, self.tx_verification, action)

    @classmethod
    def wait_for_eth_gas_price(cls, w3):
        t = 0
        while w3.eth.gas_price > Web3.to_wei(MAX_ETH_GAS_PRICE, 'gwei'):
            logger.print(f'Gas price is too high. Waiting for {WAIT_GAS_TIME}s')
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

    def mint_erc721(self, w3, cnt):
        contract = w3.eth.contract(self.nft_address, abi=ZORA_ERC721_ABI)

        if contract.functions.balanceOf(self.address).call() > 0:
            return Status.ALREADY

        value = contract.functions.zoraFeeForAmount(cnt).call()[1]

        self.build_and_send_tx(
            w3,
            contract.functions.purchase(cnt),
            action='Mint ERC721',
            value=value,
        )

        return Status.SUCCESS

    def mint_erc1155(self, w3, cnt):
        contract = w3.eth.contract(self.nft_address, abi=ZORA_ERC1155_ABI)

        if contract.functions.balanceOf(self.address, TOKEN_ID).call() > 0:
            return Status.ALREADY

        value = contract.functions.mintFee().call() * cnt

        bs = '0x' + ('0' * 24) + self.address.lower()[2:]
        args = (MINTER_ADDRESS, TOKEN_ID, cnt, to_bytes(bs))

        self.build_and_send_tx(
            w3,
            contract.functions.mint(*args),
            action='Mint ERC1155',
            value=value,
        )

        return Status.SUCCESS

    @runner_func('Mint')
    def mint(self, cnt):
        w3 = self.w3('Zora')

        if NFT_STANDARD == 'ERC721':
            return self.mint_erc721(w3, cnt)
        else:
            return self.mint_erc1155(w3, cnt)

    def run(self):
        logger.print(self.address)

        if MODE == 0:
            return self.bridge()
        elif MODE == 1:
            return self.mint(1)
        elif MODE == 2:

            try:
                return self.mint(1)
            except InsufficientFundsException:
                logger.print('Insufficient funds to mint. Let\'s bridge')

            init_balance = self.get_native_balance('Zora')
            self.bridge()
            self.wait_for_bridge(init_balance)
            return self.mint(1)

        return Status.SUCCESS


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


def write_result(filename, account):
    with open(f'{results_path}/{filename}', 'a') as file:
        file.write(f'{"|".join([str(a) for a in list(account)])}\n')


def log_run(address, account, status, exc=None, msg=''):
    exc_msg = '' if exc is None else str(exc)

    account = (address,) + account

    if status == Status.ALREADY:
        summary_msg = 'Already minted'
        color = 'green'
        write_result('already.txt', account)
    elif status == Status.PENDING:
        summary_msg = 'Tx in pending: ' + exc_msg
        color = 'yellow'
        write_result('pending.txt', account)
    elif status == Status.SUCCESS:
        summary_msg = 'Run success'
        color = 'green'
        write_result('success.txt', account)
    else:
        summary_msg = 'Run failed: ' + exc_msg
        color = 'red'
        write_result('failed.txt', account)

    logger.print(summary_msg, color=color)

    if msg != '':
        logger.print(msg, color=color)

    logger.send_tg_stored()


def main():
    if GET_TELEGRAM_CHAT_ID:
        get_telegram_bot_chat_id()
        exit(0)

    random.seed(int(datetime.now().timestamp()))

    with open('files/wallets.txt', 'r') as file:
        wallets = file.read().splitlines()
    with open('files/proxies.txt', 'r') as file:
        proxies = file.read().splitlines()

    if len(proxies) == 0:
        proxies = [None] * len(wallets)
    if len(proxies) != len(wallets):
        cprint('Proxies count doesn\'t match wallets count. Add proxies or leave proxies file empty', 'red')
        return

    queue = list(zip(wallets, proxies))
    random.shuffle(queue)

    nft_address = Web3.to_checksum_address(NFT_ADDRESS)

    idx, runs_count = 0, len(queue)

    while len(queue) != 0:

        if idx != 0:
            wait_next_run(idx, runs_count)

        account = queue.pop(0)

        wallet, proxy = account

        if wallet.find(';') == -1:
            key = wallet
        else:
            key = wallet.split(';')[1]

        runner = Runner(key, proxy, nft_address)

        address = runner.address

        exc = None

        try:
            status = runner.run()
        except PendingException as e:
            status = Status.PENDING
            exc = e
        except RunnerException as e:
            status = Status.FAILED
            exc = e
        except Exception as e:
            handle_traceback()
            status = Status.FAILED
            exc = e

        log_run(address, account, status, exc=exc)

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
