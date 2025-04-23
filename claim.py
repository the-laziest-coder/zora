import copy
import sys
import csv
import random
import aiohttp
import asyncio

from termcolor import cprint
from loguru import logger
from tabulate import tabulate
from typing import Tuple, Optional
from eth_account import Account as EthAccount

from app.config import (WAIT_BETWEEN_ACCOUNTS, THREADS_NUM, SKIP_FIRST_ACCOUNTS, RANDOM_ORDER, STORE_CREATED,
                        ONLY_CHECK_STATS, COINS, WANT_ONLY)
from app.utils import async_retry, log_long_exc
from app.zora import Zora, ZoraCoin
from app.models import AccountInfo
from app.storage import AccountStorage


logger.remove()
logger.add(sys.stderr, format='<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
                              '<level>{level: <7}</level> | '
                              '<level>{message}</level>')


CREATED_FILE = 'results/created.csv'


@async_retry
async def change_ip(idx, link: str):
    async with aiohttp.ClientSession() as sess:
        async with sess.get(link) as resp:
            if resp.status != 200:
                raise Exception(f'Failed to change ip: Status = {resp.status}. Response = {await resp.text()}')
            logger.info(f'{idx}) Successfully changed ip: {await resp.text()}')


async def process_account(account_data: Tuple[int, Tuple[str, str, str, str, str]],
                          storage: AccountStorage):

    idx, (evm_wallet, proxy, twitter_token, email, withdraw_address) = account_data

    evm_address = EthAccount().from_key(evm_wallet).address

    logger.info(f'{idx}) Processing: {evm_address}')

    if ':' in email:
        email_username, email_password = tuple(email.split(':'))
    else:
        email_username, email_password = email, ''

    account_info = await storage.get_account_info(evm_address)
    if account_info is None:
        logger.info(f'{idx}) Account info was not saved before')
        account_info = AccountInfo(idx=idx, evm_address=evm_address, evm_private_key=evm_wallet,
                                   proxy=proxy, twitter_auth_token=twitter_token, withdraw_address=withdraw_address,
                                   email_username=email_username, email_password=email_password)
    else:
        account_info.proxy = proxy
        account_info.twitter_auth_token = twitter_token
        account_info.email_username = email_username
        account_info.email_password = email_password
        account_info.withdraw_address = withdraw_address
        logger.info(f'{idx}) Saved account info restored')

    account_info.idx = idx
    account_info.twitter_error = False

    if '|' in account_info.proxy:
        change_link = account_info.proxy.split('|')[1]
        await change_ip(idx, change_link)

    exc: Optional[Exception] = None

    try:

        async with Zora(account_info, claim=True) as zora:
            await zora.claim_airdrop()

    except Exception as zora_exc:
        exc = Exception(f'Zora error: {zora_exc}')

    logger.info(f'{idx}) Account stats:\n{account_info.str_stats()}')

    await storage.set_account_info(evm_address, account_info)
    await storage.async_save()

    if exc is not None:
        raise exc


async def process_batch(bid: int, batch, storage: AccountStorage, async_func, sleep):
    if len(batch) == 0:
        return []
    failed = []
    for idx, d in enumerate(batch):
        human = dict({1: "st", 2: "nd", 3: "rd"}).get(idx + 1, "th")
        if sleep:
            if idx == 0:
                delay = sum(WAIT_BETWEEN_ACCOUNTS) / 2 * 60
                delay = random.uniform(delay * 0.8, delay * 1.2)
                delay = delay / THREADS_NUM * bid
            else:
                delay = random.uniform(*WAIT_BETWEEN_ACCOUNTS) * 60
            logger.info(f'Waiting {round(delay)}s before {idx + 1}{human} account in thread#{bid + 1}')
            await asyncio.sleep(delay)
        logger.info(f'Starting {idx + 1}{human} account in thread#{bid + 1}')
        try:
            await async_func(d, storage)
        except Exception as e:
            failed.append(d)
            await log_long_exc(d[0], 'Process account error', e)
        print()
    return failed


async def process(batches, storage: AccountStorage, async_func, sleep=True):
    tasks = []
    for idx, b in enumerate(batches):
        tasks.append(asyncio.create_task(process_batch(idx, b, storage, async_func, sleep)))
    return await asyncio.gather(*tasks)


def main():
    with open('files/evm_keys.txt', 'r', encoding='utf-8') as file:
        evm_wallets = file.read().splitlines()
        evm_wallets = [w.strip() for w in evm_wallets]
    with open('files/proxies.txt', 'r', encoding='utf-8') as file:
        proxies = file.read().splitlines()
        proxies = [p.strip() for p in proxies]
        proxies = [p if '://' in p.split('|')[0] or p == '' else 'http://' + p for p in proxies]
    with open('files/twitters.txt', 'r', encoding='utf-8') as file:
        twitters = file.read().splitlines()
        twitters = [t.strip() for t in twitters]
    with open('files/emails.txt', 'r', encoding='utf-8') as file:
        emails = file.read().splitlines()
        emails = [e.strip() for e in emails]
    with open('files/withdraw_addresses.txt', 'r', encoding='utf-8') as file:
        withdraw_addresses = file.read().splitlines()
        withdraw_addresses = [wa.strip() for wa in withdraw_addresses]

    if len(evm_wallets) > len(proxies):
        logger.error('Proxies count does not match wallets count')
        return
    if len(twitters) < len(evm_wallets):
        twitters.extend(['' for _ in range(len(evm_wallets) - len(twitters))])
    if len(emails) < len(evm_wallets):
        emails.extend(['' for _ in range(len(evm_wallets) - len(emails))])
    if len(withdraw_addresses) < len(evm_wallets):
        withdraw_addresses.extend(['' for _ in range(len(evm_wallets) - len(withdraw_addresses))])

    for idx, w in enumerate(evm_wallets, start=1):
        try:
            _ = EthAccount().from_key(w).address
        except Exception as e:
            logger.error(f'Wrong EVM private key #{idx}: {str(e)}')
            return

    for idx, link in enumerate(COINS, start=1):
        try:
            _ = ZoraCoin.from_link(link)
        except Exception as e:
            logger.error(f'Wrong link#{idx}: {e}')
            return

    want_only = WANT_ONLY

    def get_batches(skip: int = None, threads: int = THREADS_NUM):
        _data = list(enumerate(list(zip(evm_wallets, proxies, twitters, emails, withdraw_addresses)), start=1))
        exclude = []
        if skip is not None:
            _data = _data[skip:]
            _data = [d for d in _data if d[0] not in exclude]
        if skip is not None and len(want_only) > 0:
            _data = [d for d in enumerate(list(zip(evm_wallets, proxies, twitters, emails, withdraw_addresses)), start=1)
                     if d[0] in want_only]
        if RANDOM_ORDER:
            random.shuffle(_data)
        _batches = [[] for _ in range(threads)]
        for _idx, d in enumerate(_data):
            _batches[_idx % threads].append(d)
        return _batches

    storage = AccountStorage('storage/data.json')
    storage.init()

    if STORE_CREATED:
        open(CREATED_FILE, 'w').close()

    if not ONLY_CHECK_STATS:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(process(get_batches(SKIP_FIRST_ACCOUNTS), storage, process_account))

        failed = [f[0] for r in results for f in r]

        storage.save()

        print()
        logger.info('Finished')
        logger.info(f'Failed cnt: {len(failed)}')
        logger.info(f'Failed ids: {sorted(failed)}')
        print()

    csv_data = [['#', 'EVM Address', 'Airdrop', 'Claimed', 'Zora Balance', 'Volume']]
    total_drop, total_claimed, total_zora_balance = 0, 0, 0
    for idx, w in enumerate(evm_wallets, start=1):
        evm_address = EthAccount().from_key(w).address
        account = storage.get_final_account_info(evm_address)
        if account is None:
            csv_data.append([idx, evm_address])
            continue
        total_drop += account.airdrop
        total_claimed += account.claimed
        total_zora_balance += account.zora_balance

        csv_data.append([idx, evm_address,
                         round(account.airdrop), round(account.claimed), round(account.zora_balance),
                         '%.3f' % account.volume])

    csv_data.append(['#', 'EVM Address', 'Airdrop', 'Claimed', 'Zora Balance', 'Volume'])

    print(tabulate(csv_data, headers='firstrow', tablefmt='fancy_grid'))

    with open('results/stats.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerows(csv_data)

    print()
    logger.info('Stats are stored in results/stats.csv')
    print()
    logger.info(f'Total airdrop: {round(total_drop)} $ZORA')
    logger.info(f'Total claimed: {round(total_claimed)} $ZORA')
    logger.info(f'Total $ZORA balance: {round(total_zora_balance)} $ZORA')
    print()


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
