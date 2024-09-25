import json
import random
import aiohttp
import asyncio
import csv

from datetime import datetime
from loguru import logger
from web3 import AsyncWeb3
from pathlib import Path
from eth_account import Account
from termcolor import cprint
from tabulate import tabulate

import config
from vars import NATIVE_DECIMALS


date_path = datetime.now().strftime('%d-%m-%Y-%H-%M-%S')
results_path = 'results/' + date_path
Path(results_path).mkdir(parents=True, exist_ok=True)


wallets_data = {}


def int_to_decimal(i, n):
    return i / (10 ** n)


class ZoraScan:

    def __init__(self, idx, private_key, proxy):
        self.idx = idx
        if proxy is not None and len(proxy) > 4 and proxy[:4] != 'http':
            proxy = 'http://' + proxy
        self.proxy = proxy
        self.private_key = private_key
        self.account = Account().from_key(private_key)
        self.address = self.account.address

    async def get_minted_data(self):
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f'https://explorer.zora.energy/api/v2/addresses/{self.address}/tokens',
                                proxy=self.proxy) as resp_raw:
                resp = await resp_raw.json()
                erc721, erc1155 = 0, 0
                unique_erc721, unique_erc1155 = 0, 0
                for item in resp['items']:
                    token_type = item['token']['type']
                    if token_type == 'ERC-721':
                        erc721 += int(item['value'])
                        unique_erc721 += 1
                    elif token_type == 'ERC-1155':
                        erc1155 += int(item['value'])
                        unique_erc1155 += 1
                return unique_erc721, unique_erc1155, erc721, erc1155

    async def get_created_data(self):
        async with aiohttp.ClientSession() as sess:
            query = {
                'chainId': '1,7777777,10,8453,42161,81457',
                'direction': 'desc',
                'limit': 1000,
                'includeTokens': 'all',
                'excludeBrokenContracts': 'false',
            }
            async with sess.get(f'https://zora.co/api/user/{self.address.lower()}/admin',
                                params=query, proxy=self.proxy) as resp_raw:
                resp = await resp_raw.json()
                collections = len(resp)
                nfts = sum(len(r['tokens']) if r['contractStandard'] == 'ERC1155' else 1 for r in resp)
                return collections, nfts

    async def get_swap_data(self, w3):
        async with aiohttp.ClientSession() as sess:
            volume = 0
            async with sess.get(f'https://explorer.zora.energy/api/v2/addresses/{self.address}/transactions',
                                proxy=self.proxy) as resp_raw:
                resp = await resp_raw.json()
                for item in resp['items']:
                    if item['to']['hash'].lower() != '0x2986d9721A49838ab4297b695858aF7F17f38014'.lower():
                        continue
                    tx_hash = item['hash']
                    receipt = await w3.eth.get_transaction_receipt(tx_hash)
                    for log in receipt['logs']:
                        if len(log.get('topics', [])) == 0:
                            continue
                        if log['topics'][0].hex() != '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef':
                            continue
                        if log['address'] != '0x4200000000000000000000000000000000000006':
                            continue
                        volume += int(log['data'].hex(), 16) / 10 ** 18
            return '%.3f' % volume

    async def get_data(self):
        logger.info(f'{self.idx}) Processing {self.address}')
        data = [None] * 7

        try:
            req_args = {} if self.proxy is None or self.proxy == '' else {
                'proxy': self.proxy,
            }
            w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(config.RPCs['Zora'], request_kwargs=req_args))
            tx_count = await w3.eth.get_transaction_count(self.address)
            balance = await w3.eth.get_balance(self.address)
            balance = int_to_decimal(balance, NATIVE_DECIMALS)
            balance = '%.4f' % balance
            data[0], data[1] = balance, tx_count
        except Exception as e:
            logger.error(f'{self.idx}) Failed to get chain data: {str(e)}')

        try:
            data[2] = await self.get_swap_data(w3)
        except Exception as e:
            logger.error(f'{self.idx}) Failed to get swap data: {e}')

        try:
            unique_erc721, unique_erc1155, erc721, erc1155 = await self.get_minted_data()
            data[3], data[4] = erc1155, unique_erc1155
        except Exception as e:
            logger.error(f'{self.idx}) Failed to get nft data: {str(e)}')

        try:
            data[5], data[6] = await self.get_created_data()
        except Exception as e:
            logger.error(f'{self.idx}) Failed to get created data: {e}')

        wallets_data[self.address] = data
        logger.success(f'{self.idx}) Data filled')


async def fill_batch(batch):
    for idx, (key, proxy) in batch:
        client = ZoraScan(idx, key, proxy)
        await client.get_data()
        await asyncio.sleep(1)


async def fill_data(data):
    tasks = []
    batches = [[] for _ in range(config.CHECKER_THREADS)]
    for i, d in enumerate(data):
        batches[i % config.CHECKER_THREADS].append(d)
    for b in batches:
        tasks.append(asyncio.create_task(fill_batch(b)))
    await asyncio.gather(*tasks)


def main():
    random.seed(int(datetime.now().timestamp()))

    with open('files/wallets.txt', 'r', encoding='utf-8') as file:
        wallets = file.read().splitlines()
    with open('files/proxies.txt', 'r', encoding='utf-8') as file:
        proxies = file.read().splitlines()

    if len(proxies) == 0:
        proxies = [None] * len(wallets)
    if len(proxies) != len(wallets):
        cprint('Proxies count doesn\'t match wallets count. Add proxies or leave proxies file empty', 'red')
        return

    wallets = [w if w.find(';') == -1 else w.split(';')[1] for w in wallets]

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(fill_data(list(enumerate(list(zip(wallets, proxies)), start=1))))

    csv_data = [['#', 'Address', 'Balance', 'Tx Count', 'Swap Volume',
                 'Total NFT', 'Unique NFT',
                 'Created Collections', 'Created NFTs']]
    for idx, w in enumerate(wallets, start=1):
        address = ZoraScan(None, w, None).address
        csv_data.append([idx, address] + list(wallets_data[address]))

    with open(f'{results_path}/stats.csv', 'w') as file:
        writer = csv.writer(file)
        writer.writerows(csv_data)

    print()

    print(tabulate(csv_data, headers='firstrow', tablefmt='fancy_grid'))

    print()
    logger.success(f'Stats saves in {results_path}/stats.csv\n')


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
