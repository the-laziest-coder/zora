import copy
import json
import random
from dataclasses import dataclass
from loguru import logger
from web3 import Web3
import eth_abi


from ..config import BUY_AMOUNT, MAX_TOP, SELL_PERCENT, SELL_IF_BALANCE_VALUE_GREATER_THAN
from ..email import Email
from ..models import AccountInfo
from ..onchain import EVM, CHAIN_IDS, ZERO_ADDRESS, CHAIN_NAMES, SCANS
from ..tls import TLSClient
from ..twitter import Twitter
from ..utils import (wait_a_bit, human_int, decimal_to_int, int_to_decimal, human_i2d,
                     get_query_param, fake_username, fake_filename, fake_name, write_to_file)
from .client import Client
from .utils import *


def _is_address(address: str) -> bool:
    if not address:
        return False
    if not address.startswith('0x') or len(address) != 42:
        return False
    try:
        _ = int(address, 16)
        return True
    except:
        return False


@dataclass
class ZoraCoin:
    chain: str
    address: str
    referrer: str = ''
    top: int = 0

    @classmethod
    def from_link(cls, link: str) -> "ZoraCoin":
        try:
            if not link.startswith('https://zora.co/coin/'):
                raise Exception(f'Link should starts with "https://zora.co/coin/"')
            link = link[21:]
            referrer = ''
            if '?' in link:
                referrer = get_query_param(link, 'referrer')
                if not _is_address(referrer):
                    raise Exception('Wrong referrer')
                link = link[:link.find('?')]
            chain, address = tuple(link.split(':'))
            if chain not in ['base', 'zora']:
                raise Exception(f'Unsupported chain: {chain}')
            if not _is_address(address):
                raise Exception('Wrong address')
            return ZoraCoin(chain=chain.capitalize(), address=address, referrer=referrer)
        except Exception as e:
            raise Exception(f'Wrong coin link "{link}": {e}')

    def to_link(self) -> str:
        link = f'https://zora.co/coin/{self.chain.lower()}:{self.address.lower()}'
        if self.referrer:
            link += f'?referrer={self.referrer}'
        return link


class Zora:

    def __init__(self, account: AccountInfo):
        self.idx = account.idx
        self.account = account
        self.client = Client(self.account)
        self.sold_in_session = []

    async def close(self):
        await self.client.close()

    async def __aenter__(self) -> "Zora":
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def buy(self, coin: ZoraCoin):
        chain_id = CHAIN_IDS[coin.chain]
        info = await self.client.get_coin_info(chain_id, coin.address)
        stats = await self.client.get_coin_stats(chain_id, coin.address)

        market_cap = float(stats['marketCap'])
        market_cap = ('%.1f' % (market_cap / 1000)) + 'k'

        top_msg = f' (Top-{coin.top} today)' if coin.top > 0 else ''

        logger.info(f'{self.idx}) Coin "{info["name"]}" with mc {market_cap}{top_msg}')

        await wait_a_bit(3)

        pool_address = info['uniswapPoolAddress']
        amount = human_int(decimal_to_int(random.uniform(*BUY_AMOUNT)))
        quote = await self.client.get_coin_quote(pool_address, chain_id, amount, 'buy')

        amount_out = int(quote['amountOut'])
        min_amount_out = int(amount_out * 0.9)
        price_limit = int(quote['priceLimit'])

        referrer = coin.referrer
        referrer = referrer if referrer else ZERO_ADDRESS

        async with EVM(self.account, coin.chain) as evm:
            contract = evm.contract(
                coin.address,
                'buy(address,uint256,uint256,uint160,address)',
            )
            await evm.build_and_send_tx(
                contract.functions.buy(
                    self.account.evm_address,
                    amount,
                    min_amount_out,
                    price_limit,
                    referrer,
                ),
                action=f'Buying at least {human_i2d(min_amount_out)} ${info["coinName"]} '
                       f'for {human_i2d(amount)} ETH',
                value=amount,
            )
            self.account.buys += 1
            self.account.volume += int_to_decimal(amount)

    async def buy_random_top(self):
        coins = await self.client.get_top_today()
        coins = list(enumerate(coins, start=1))
        top, coin = random.choice(coins[:MAX_TOP])
        await self.buy(ZoraCoin(
            chain=CHAIN_NAMES[coin['chainId']],
            address=coin['address'],
            top=top,
        ))

    async def sell(self, coin: ZoraCoin):
        chain_id = CHAIN_IDS[coin.chain]
        info = await self.client.get_coin_info(chain_id, coin.address)
        stats = await self.client.get_coin_stats(chain_id, coin.address)

        market_cap = float(stats['marketCap'])
        market_cap = '%.1f' % (market_cap / 1000) + 'k'

        top_msg = f' (Top-{coin.top} today)' if coin.top > 0 else ''

        logger.info(f'{self.idx}) Coin "{info["name"]}" with mc {market_cap}{top_msg}')

        await wait_a_bit(3)

        pool_address = info['uniswapPoolAddress']

        async with EVM(self.account, coin.chain) as evm:
            token = evm.contract(coin.address, erc20=True)
            balance = await token.functions.balanceOf(self.account.evm_address).call()

            percent = random.uniform(*SELL_PERCENT)
            if percent < 100:
                amount = human_int(int(balance * percent / 100))
            else:
                amount = balance

            await evm.approve(
                token,
                coin.address,
                amount,
                name=info['coinName'],
            )

            quote = await self.client.get_coin_quote(pool_address, chain_id, amount, 'sell')

            amount_out = int(quote['amountOut'])
            min_amount_out = int(amount_out * 0.9)
            price_limit = int(quote['priceLimit'])

            referrer = coin.referrer
            referrer = referrer if referrer else self.account.evm_address

            contract = evm.contract(
                coin.address,
                'sell(address,uint256,uint256,uint160,address)',
            )
            await evm.build_and_send_tx(
                contract.functions.sell(
                    self.account.evm_address,
                    amount,
                    min_amount_out,
                    price_limit,
                    referrer,
                ),
                action=f'Selling {human_i2d(amount)} ${info["coinName"]} '
                       f'for at least {human_i2d(min_amount_out)} ETH',
            )
            self.account.sells += 1
            self.account.volume += int_to_decimal(min_amount_out)
            self.sold_in_session.append((coin.chain.lower(), coin.address.lower()))

    async def link_email(self):
        logger.info(f'{self.idx}) Linking email')
        async with Email.from_account(self.account) as email:
            await email.login()
            email_username = email.username()
            if not email_username:
                raise Exception('Email not provided')
            await self.client.init_set_email(email_username)
            logger.info(f'{self.idx}) Email {email_username} submitted')
            subj, _ = await email.wait_for_email(lambda s: ' is your login code for Zora' in s and len(s) == 34)
            code = subj.split()[0]
            logger.info(f'{self.idx}) Verification code found: {code}')
            await self.client.link_email(email_username, code)
            logger.success(f'{self.idx}) Email verified')
            await wait_a_bit(6)

    async def _get_random_avatar(self) -> bytes:
        size = random.choice([s for s in range(150, 801, 50)])
        url = f'https://i.pravatar.cc/{size}'
        tls = TLSClient(self.account)
        try:
            resp = await tls.get(url, [200], raw=True)
            return resp.content
        except Exception as e:
            raise Exception(f'Get random avatar failed: {e}') from e
        finally:
            await tls.close()

    async def _get_ipfs_avatar(self) -> str:
        avatar_bs = await self._get_random_avatar()
        name = await fake_filename()
        ipfs = await self.client.ipfs_upload(name, avatar_bs)
        return 'ipfs://' + ipfs

    async def init_account(self):
        logger.info(f'{self.idx}) Creating new Zora account')
        username = await fake_username()
        while not await self.client.is_username_available(username):
            username = await fake_username()
        avatar = await self._get_ipfs_avatar()
        await self.client.create_account(username, avatar)
        logger.success(f'{self.idx}) Created account with username {username}')

    async def update_username(self):
        logger.info(f'{self.idx}) Updating username')
        username = await fake_username()
        while not await self.client.is_username_available(username):
            username = await fake_username()
        await self.client.change_username(username)
        logger.success(f'{self.idx}) Updated username: {username}')

    async def setup_avatar(self, username: str):
        logger.info(f'{self.idx}) Adding avatar')
        avatar = await self._get_ipfs_avatar()
        await self.client.update_profile(username, avatar)
        logger.success(f'{self.idx}) Profile avatar updated')

    @classmethod
    def _b64safe(cls, value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b'=').decode('utf-8')

    @classmethod
    def _random_string(cls) -> str:
        random_bytes = os.urandom(36)
        return cls._b64safe(random_bytes)

    @classmethod
    def _sha256(cls, value: str) -> str:
        h = hashlib.sha256(value.encode('utf-8')).digest()
        return cls._b64safe(h)

    async def link_twitter(self, on_creating: bool = False):
        logger.info(f'{self.idx}) Linking Twitter')
        if not self.account.twitter_auth_token:
            raise Exception('No twitter provided')
        twitter = Twitter(self.account)
        await twitter.start()
        code_verifier = self._random_string()
        state_code = self._random_string()
        code_challenge = self._sha256(code_verifier)
        redirect_to = 'https://zora.co/settings?tab=profile'
        if on_creating:
            redirect_to = 'https://zora.co/onboarding?step=socials'
        await self.client.oauth_init(
            code_challenge,
            'twitter',
            redirect_to,
            state_code,
        )
        auth_code = await twitter.oauth2(
            client_id='YlJMT0QtbzB1RU1kaDd6Q2xPem06MTpjaQ',
            code_challenge=code_challenge,
            state=state_code,
            redirect_uri=self.client.OAUTH_CALLBACK_URL,
            code_challenge_method='S256',
            scope='users.read tweet.read',
            response_type='code',
        )
        privy_code = await self.client.oauth_callback(state_code, auth_code, redirect_to)
        await self.client.oauth_link(privy_code, code_verifier, state_code)
        await wait_a_bit(2)
        await self.client.account_update_socials(redirect_to)
        logger.success(f'{self.idx}) Twitter linked')

    async def setup_profile(self):
        logger.info(f'{self.idx}) Setting up profile')
        account = await self.client.get_my_account(can_be_not_found=True)
        if account is None or not account.get('emailVerified'):
            if self.client.has_email:
                logger.info(f'{self.idx}) Already linked email')
            else:
                await self.link_email()
        if account is None:
            await self.init_account()
            await wait_a_bit(3)
            account = await self.client.get_my_account()
            await self.link_twitter(on_creating=True)
            await wait_a_bit(3)
        if account.get('username', '').lower() == self.account.evm_address.lower():
            await wait_a_bit(3)
            await self.update_username()
            await wait_a_bit(10)
            account = await self.client.get_my_account()
        profile = await self.client.get_my_profile()
        if not profile.get('avatarUri'):
            display_name = profile.get('displayName')
            if display_name is None:
                display_name = account['username']
            await self.setup_avatar(display_name)
            profile = await self.client.get_my_profile()
        if profile.get('socialAccounts', {}).get('twitter') is None:
            await self.link_twitter()
            profile = await self.client.get_my_profile()
        self.account.profile_completed = True
        logger.success(f'{self.idx}) Profile completed')

    async def follow_random(self):
        users = await self.client.get_following_recommended()
        users = [u for u in users if u['following_status'] == 'NOT_FOLLOWING' and u['username']]
        user = random.choice(users)
        logger.info(f'{self.idx}) Following @{user["username"]}')
        await self.client.follow(user['username'])

    async def _get_holdings(self) -> list[dict]:
        profile_id, profile_handle = await self.client.get_my_profile_ids()
        coins = []
        profile, pagination, has_next_page = profile_handle, None, True
        while has_next_page:
            posts, page_info = await self.client.get_holdings(profile, pagination)
            coins.extend([p for p in posts if 'uniqueHolders' in p])
            has_next_page = page_info['hasNextPage']
            pagination = {
                'cursor': page_info['endCursor'],
                'id': profile_id,
            }
            profile = profile_id
        return coins

    async def _get_creates(self) -> list[dict]:
        profile_id, profile_handle = await self.client.get_my_profile_ids()
        coins = []
        profile, pagination, has_next_page = profile_handle, None, True
        while has_next_page:
            posts, page_info = await self.client.get_created(profile, pagination)
            coins.extend([p for p in posts if 'uniqueHolders' in p])
            has_next_page = page_info['hasNextPage']
            pagination = {
                'cursor': page_info['endCursor'],
                'id': profile_id,
            }
            profile = profile_id
        return coins

    async def sell_random(self):
        coins = await self._get_holdings()
        if len(coins) == 0:
            raise Exception('Nothing to sell')
        random.shuffle(coins)
        for coin in coins:
            chain_id, address, name = coin['chainId'], coin['address'], coin['name']
            if (CHAIN_NAMES[chain_id].lower(), address.lower()) in self.sold_in_session:
                continue
            async with EVM(self.account, CHAIN_NAMES[chain_id]) as evm:
                token = evm.contract(
                    address,
                    'poolAddress()address',
                    erc20=True,
                )
                pool_address = await token.functions.poolAddress().call()
                balance = await token.functions.balanceOf(self.account.evm_address).call()
                quote = await self.client.get_coin_quote(pool_address, chain_id, balance, 'sell')
                amount_out = int(quote['amountOut'])
                if amount_out >= decimal_to_int(SELL_IF_BALANCE_VALUE_GREATER_THAN):
                    await self.sell(ZoraCoin(chain=CHAIN_NAMES[chain_id], address=address))
                    return
                logger.info(f'{self.idx}) Will not sell {name}, because it\'s balance value is too low '
                            f'({human_i2d(amount_out)} ETH)')
        raise Exception('Nothing to sell')

    def _get_device_id(self) -> str:
        if not self.account.b58_device_id:
            self.account.b58_device_id = generate_device_id()
        return self.account.b58_device_id

    async def _get_random_image(self) -> bytes:
        if random.uniform(0, 100) <= 90:
            img_szs = [i for i in range(400, 1001, 50)]
            url = f'https://picsum.photos/{random.choice(img_szs)}/{random.choice(img_szs)}'
        else:
            url = 'https://random.danielpetrica.com/api/random'
        tls = TLSClient(self.account)
        try:
            resp = await tls.get(url, [200], raw=True)
            return resp.content
        except Exception as e:
            raise Exception(f'Get random image failed: {e}') from e
        finally:
            await tls.close()

    async def _get_ipfs_image(self) -> str:
        image_bs = await self._get_random_image()
        name = await fake_filename()
        ipfs = await self.client.ipfs_upload(name, image_bs)
        return 'ipfs://' + ipfs

    async def _get_ipfs_metadata(self, name: str, image_uri: str) -> str:
        metadata = json.dumps({
            'name': name,
            'description': '',
            'symbol': name,
            'image': image_uri,
            'content': {
                'uri': image_uri,
                'mime': 'image/png',
            },
        }, indent=2)
        metadata_bs = bytes(metadata, 'utf-8')
        ipfs = await self.client.ipfs_upload('metadata.json', metadata_bs, content_type='application/json')
        return 'ipfs://' + ipfs

    async def create(self):
        logger.info(f'{self.idx}) Creating coin')
        await self.client.ensure_authorized()
        embedded = self.client.embedded_wallet
        if not embedded:
            raise Exception('No embedded wallet found')

        logger.info(f'{self.idx}) Generating image...')

        name = await fake_name()
        image_uri = await self._get_ipfs_image()
        contract_uri = await self._get_ipfs_metadata(name, image_uri)

        chain_id = CHAIN_IDS['Base']

        logger.info(f'{self.idx}) Requesting tx data...')

        smart_wallet = await self.client.create_smart_wallet(chain_id)
        create_tx = {
            'adminAddressess': [embedded, self.account.evm_address, smart_wallet],
            'chainId': chain_id,
            'contractURI': contract_uri,
            'createReferral': ZERO_ADDRESS,
            'createSplitCalldata': None,
            'creatorRewardRecipient': self.account.evm_address,
            'name': name,
            'ownerAddress': smart_wallet,
            'ticker': name,
            'value': '0',
        }
        user_op, meta = await self.client.create_erc20_user_operation(create_tx)

        embedded_pk = await self._get_embedded_wallet_pk()

        logger.info(f'{self.idx}) Signing tx with embedded wallet')

        signature = self._sign_user_operation(user_op, meta, chain_id, pk=embedded_pk)

        logger.info(f'{self.idx}) Submitting signed tx')

        tx_hash = await self.client.submit_user_operation({
            'chainId': chain_id,
            'signature': signature,
            'userOperation': user_op,
        }, {
            'values': {'userOperation.' + k: v for k, v in meta.get('values', {}).items()},
        })

        async with EVM(self.account, 'Base') as evm:
            receipt = await evm.tx_verification(tx_hash, f'Creating "{name}" coin')
            try:
                event_topic = '0x3d1462491f7fa8396808c230d95c3fa60fd09ef59506d0b9bd1cf072d2a03f56'
                coin_created_log = None
                for log in receipt.logs:
                    if log.topics[0].hex() == event_topic:
                        coin_created_log = log
                        break
                if not coin_created_log:
                    raise Exception('CoinCreated event not found')
                data_types = ['address', 'string', 'string', 'string', 'address', 'address', 'string']
                decoded_data = eth_abi.decode(data_types, coin_created_log.data)
                coin_address = decoded_data[4]
                coin = ZoraCoin(chain='Base', address=coin_address.lower())
                logger.success(f'{self.idx}) Created coin: {coin.to_link()}')
            except Exception as e:
                logger.warning(f'{self.idx}) Failed to parse tx logs to fetch coin address: {e}')

        self.account.creates += 1

    async def _get_embedded_wallet_pk(self) -> str:
        embedded = self.client.embedded_wallet

        if self.account.embedded_pk:
            await self.client.embedded_share(embedded, self._get_device_id())
            return self.account.embedded_pk

        logger.info(f'{self.idx}) Recovering embedded wallet...')

        r_key, r_type = await self.client.recovery_key_material(embedded)
        if r_type != 'privy_generated_recovery_key':
            raise Exception('Unsupported recovery key type')
        auth_share = await self.client.recovery_auth_share(embedded)
        recovery_key_hash = get_key_hash(r_key)

        enc_r_share, enc_r_share_iv, imported = await self.client.recovery_shares(embedded, recovery_key_hash)
        if imported:
            raise Exception('Imported recovery not supported')

        shares = [decrypt_share(enc_r_share, enc_r_share_iv, r_key), base64.b64decode(auth_share)]
        entropy = shamir_combine(shares)

        acc = account_from_entropy(entropy)

        if acc.address.lower() != embedded.lower():
            raise Exception('Failed to recover the expected wallet')

        splits = shamir_split(entropy)
        device_auth_share = base64.b64encode(splits[1]).decode('utf-8')

        device_id = self._get_device_id()

        await self.client.recovery_device(embedded, device_auth_share, device_id)

        self.account.embedded_pk = acc.key.hex()
        return self.account.embedded_pk

    def _sign_user_operation(self, user_operation_raw: dict, meta: dict, chain_id: int, pk: str | bytes = None):
        user_operation = copy.deepcopy(user_operation_raw)

        for param, value in meta.get('values', {}).items():
            if param not in user_operation:
                raise Exception(f'Unknown user operation meta param: {param}')
            if type(value) is not list or len(value) != 1 or value[0] != 'bigint':
                raise Exception(f'Unsupported user operation meta value: {param} = {value}')
            if type(user_operation[param]) is str:
                user_operation[param] = int(user_operation[param])
        user_operation['sender'] = Web3.to_checksum_address(user_operation['sender'])

        sender = user_operation['sender']
        nonce = user_operation['nonce']
        init_code = user_operation['initCode']
        call_data = user_operation['callData']
        call_gas_limit = user_operation['callGasLimit']
        verification_gas_limit = user_operation['verificationGasLimit']
        pre_verification_gas = user_operation['preVerificationGas']
        max_fee_per_gas = user_operation['maxFeePerGas']
        max_priority_fee_per_gas = user_operation['maxPriorityFeePerGas']
        paymaster_and_data = user_operation['paymasterAndData']

        init_code_hash = Web3.solidity_keccak(['bytes'], [init_code])
        call_data_hash = Web3.solidity_keccak(['bytes'], [call_data])
        paymaster_and_data_hash = Web3.solidity_keccak(['bytes'], [paymaster_and_data])

        user_op_hash = eth_abi.encode(
            ['address', 'uint256', 'bytes32', 'bytes32', 'uint256', 'uint256',
             'uint256', 'uint256', 'uint256', 'bytes32'],
            [sender, nonce, init_code_hash, call_data_hash, call_gas_limit, verification_gas_limit,
             pre_verification_gas, max_fee_per_gas, max_priority_fee_per_gas, paymaster_and_data_hash]
        )
        user_op_hash = Web3.solidity_keccak(['bytes'], [user_op_hash])

        bundle_hash = eth_abi.encode(
            ['bytes32', 'address', 'uint256'],
            [user_op_hash, ENTRYPOINT_ADDRESS, chain_id]
        )
        bundle_hash = Web3.solidity_keccak(['bytes'], [bundle_hash])

        pk = pk or self.account.evm_private_key
        signature = Account.signHash(bundle_hash, pk).signature
        return signature.hex()

    async def store_created(self, file_name: str):
        created = await self._get_creates()
        coins = [ZoraCoin(chain=CHAIN_NAMES[c['chainId']], address=c['address'])
                 for c in created]
        coins = [f'{self.account.evm_address};{c.to_link()}' for c in coins]
        coins = '\n'.join(coins)
        await write_to_file(coins, file_name)


ENTRYPOINT_ADDRESS = '0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789'
