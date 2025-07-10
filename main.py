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
                        ONLY_CHECK_STATS, COINS, ACTIONS, SETUP_PROFILE, DELAY_BETWEEN_ACTIONS, WANT_ONLY)
from app.utils import async_retry, wait_a_bit, log_long_exc 
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


async def process_account(account_data: Tuple[int, Tuple[str, str, str, str]],
                          storage: AccountStorage):

    idx, (evm_wallet, proxy, twitter_token, email) = account_data

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
                                   proxy=proxy, twitter_auth_token=twitter_token,
                                   email_username=email_username, email_password=email_password)
    else:
        account_info.proxy = proxy
        account_info.twitter_auth_token = twitter_token
        account_info.email_username = email_username
        account_info.email_password = email_password
        logger.info(f'{idx}) Saved account info restored')

    account_info.idx = idx
    account_info.twitter_error = False

    if '|' in account_info.proxy:
        change_link = account_info.proxy.split('|')[1]
        await change_ip(idx, change_link)

    exc: Optional[Exception] = None

    try:
        buy_links = random.randint(*ACTIONS.get('BUY_LINKS', (0, 0)))
        buy_top = random.randint(*ACTIONS.get('BUY_TOP', (0, 0)))
        sells = random.randint(*ACTIONS.get('SELLS', (0, 0)))
        follows = random.randint(*ACTIONS.get('FOLLOW', (0, 0)))
        creates = random.randint(*ACTIONS.get('CREATES', (0, 0)))
        logger.info(f'{idx}) Will do:\n'
                    f'\t{buy_links} buys from coins.txt\n'
                    f'\t{buy_top} buys from top today\n'
                    f'\t{sells} sells\n'
                    f'\t{creates} creates\n'
                    f'\t{follows} follows\n')

        actions = (
            ['buy_link'] * buy_links +
            ['buy_top'] * buy_top +
            ['follow'] * follows +
            ['create'] * creates
        )
        random.shuffle(actions)

        i, sells_left = 0, sells
        while i < len(actions) and sells_left > 0:
            i += 1
            if actions[i - 1] not in ('buy_link', 'buy_top'):
                continue
            sell_index = random.randint(i, len(actions))
            actions.insert(sell_index, 'sell')
            sells_left -= 1
        if sells_left > 0:
            last_buy_index = -1
            for i, a in enumerate(actions):
                if a in ('buy_link', 'buy_top'):
                    last_buy_index = i
            for _ in range(sells_left):
                sell_index = random.randint(last_buy_index + 1, len(actions))
                actions.insert(sell_index, 'sell')

        async with Zora(account_info) as zora:
            if SETUP_PROFILE:
                try:
                    await zora.setup_profile()
                except Exception as e:
                    logger.warning(f'{idx}) Setting up profile failed: {e}')
                await wait_a_bit(10)
            coins = copy.deepcopy(COINS)
            random.shuffle(coins)
            coin_idx = 0
            for action_id, action in enumerate(actions, start=1):
                if action_id != 1:
                    delay = random.uniform(*DELAY_BETWEEN_ACTIONS)
                    logger.info(f'{idx}) Sleeping {round(delay)}s before next action')
                    await asyncio.sleep(delay)
                action_name = action.replace('_', ' ').strip().title()
                logger.info(f'{idx}) Starting action#{action_id} {action_name}')
                try:
                    match action:
                        case 'buy_link':
                            if coin_idx >= len(coins):
                                raise Exception('No coins left')
                            coin_idx += 1
                            coin = ZoraCoin.from_link(coins[coin_idx - 1])
                            await zora.buy(coin)
                        case 'buy_top':
                            await zora.buy_random_top()
                        case 'sell':
                            await zora.sell_random()
                        case 'follow':
                            await zora.follow_random()
                        case 'create':
                            await zora.create()
                        case unexpected:
                            raise Exception(f'Action "{unexpected}" not supported')
                except Exception as e:
                    logger.warning(f'{idx}) Action#{action_id} {action_name} failed: {e}')

                await storage.set_account_info(evm_address, account_info)
                await storage.async_save()

            try:
                await zora.calc_portfolio()
                await storage.set_account_info(evm_address, account_info)
                await storage.async_save()
            except Exception as e:
                logger.warning(f'{idx}) Calculating portfolio failed: {e}')

            if STORE_CREATED:
                logger.info(f'{idx}) Storing created coins')
                try:
                    await zora.store_created(CREATED_FILE)
                except Exception as e:
                    logger.warning(f'{idx}) Store created coins failed: {e}')

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

    if len(evm_wallets) > len(proxies):
        logger.error('Proxies count does not match wallets count')
        return
    if len(twitters) < len(evm_wallets):
        twitters.extend(['' for _ in range(len(evm_wallets) - len(twitters))])
    if len(emails) < len(evm_wallets):
        emails.extend(['' for _ in range(len(evm_wallets) - len(emails))])

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
        _data = list(enumerate(list(zip(evm_wallets, proxies, twitters, emails)), start=1))
        exclude = []
        if skip is not None:
            _data = _data[skip:]
            _data = [d for d in _data if d[0] not in exclude]
        if skip is not None and len(want_only) > 0:
            _data = [d for d in enumerate(list(zip(evm_wallets, proxies, twitters, emails)), start=1)
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

    csv_data = [['#', 'EVM Address', 'Airdrop', 'Volume', 'PNL', 'Portfolio', 'Buys', 'Sells', 'Creates', 'Profile Completed']]
    total_drop = 0
    for idx, w in enumerate(evm_wallets, start=1):
        evm_address = EthAccount().from_key(w).address
        account = storage.get_final_account_info(evm_address)
        if account is None:
            csv_data.append([idx, evm_address])
            continue
        total_drop += account.airdrop

        csv_data.append([idx, evm_address,
                         round(account.airdrop),
                         '%.3f' % account.volume, '%.3f' % account.pnl, '%.3f' % account.portfolio,
                         account.buys, account.sells, account.creates,
                         account.profile_completed])

    csv_data.append(['#', 'EVM Address', 'Airdrop', 'Volume', 'PNL', 'Portfolio', 'Buys', 'Sells', 'Creates', 'Profile Completed'])

    print(tabulate(csv_data, headers='firstrow', tablefmt='fancy_grid'))

    with open('results/stats.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerows(csv_data)

    print()
    logger.info('Stats are stored in results/stats.csv')
    print()
    logger.info(f'Total airdrop: {round(total_drop)} $ZORA')
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
