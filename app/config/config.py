import sys
import toml
import platform
import subprocess
from importlib.metadata import version


with open('config.toml', 'r', encoding='utf-8') as file:
    cfg = toml.load(file)


WAIT_BETWEEN_ACCOUNTS = cfg.get('WAIT_BETWEEN_ACCOUNTS')
MAX_TRIES = cfg.get('MAX_TRIES')
THREADS_NUM = cfg.get('THREADS_NUM')
DISABLE_SSL = cfg.get('DISABLE_SSL')
WANT_ONLY = cfg.get('WANT_ONLY', [])
SKIP_FIRST_ACCOUNTS = cfg.get('SKIP_FIRST_ACCOUNTS')
RANDOM_ORDER = cfg.get('RANDOM_ORDER')
RPCs = cfg.get('RPCs')

ONLY_CHECK_STATS = cfg.get('ONLY_CHECK_STATS')

SWAP_ZORA_TO_ETH = cfg.get('SWAP_ZORA_TO_ETH')

BUY_AMOUNT = cfg.get('BUY_AMOUNT')
BUY_FROM_ZORA_CHANCE = cfg.get('BUY_FROM_ZORA_CHANCE', 0)
SELL_PERCENT = cfg.get('SELL_PERCENT')
SELL_IF_BALANCE_VALUE_GREATER_THAN = cfg.get('SELL_IF_BALANCE_VALUE_GREATER_THAN')
MAX_TOP = cfg.get('MAX_TOP')

SETUP_PROFILE = cfg.get('SETUP_PROFILE')
STORE_CREATED = cfg.get('STORE_CREATED')

DELAY_BETWEEN_ACTIONS = cfg.get('DELAY_BETWEEN_ACTIONS')
ACTIONS = cfg.get('ACTIONS')

with open('files/coins.txt', 'r', encoding='utf-8') as file:
    COINS = [line.strip() for line in file.read().splitlines()]


if ACTIONS.get('BUY_LINKS', (0, 0))[1] > len(COINS):
    print('\nBUY_LINKS max actions more than links number in coins.txt\n')
    exit(0)


if len(sys.argv) > 1:
    if sys.argv[1] == 'stats':
        ONLY_CHECK_STATS = True
