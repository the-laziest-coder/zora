import json
from uuid import uuid4
from datetime import datetime
from loguru import logger
from typing import Literal, Optional
from curl_cffi import CurlMime

from ..models import AccountInfo
from ..tls import TLSClient
from ..utils import wait_a_bit, get_query_param, async_retry


class Client:

    def __init__(self, account: AccountInfo):
        self.account = account
        if not self.account.device_id:
            self.account.device_id = str(uuid4())
        if not self.account.privy_ca_id:
            self.account.privy_ca_id = str(uuid4())
        self.tls = TLSClient(self.account, {
            'origin': 'https://zora.co',
            'priority': 'u=1, i',
            'referer': 'https://zora.co/',
        }, {
            'device_id': self.account.device_id,
            'wallet_address': self.account.evm_address,
        })
        self.privy_headers = {
            'privy-app-id': 'clpgf04wn04hnkw0fv1m11mnb',
            'privy-ca-id': self.account.privy_ca_id,
            'privy-client': 'react-auth:1.98.1',
            'privy-client-id': 'client-WY2f8mnC65aGnM2LmXpwBU5GqK3kxYqJoV7pSNRJLWrp6',
        }
        self.has_email = False
        self.embedded_wallet: str = ''

    async def close(self):
        await self.tls.close()

    async def _init(self) -> str:
        try:
            return await self.tls.post(
                'https://privy.zora.co/api/v1/siwe/init',
                [200], lambda r: r['nonce'],
                json={'address': self.account.evm_address},
                headers=self.privy_headers,
            )
        except Exception as e:
            raise Exception(f'Init failed: {e}')

    async def _authenticate(self, msg: str, sign: str):
        try:
            token, linked_accounts = await self.tls.post(
                'https://privy.zora.co/api/v1/siwe/authenticate',
                [200], lambda r: (r['token'], r['user']['linked_accounts']),
                json={
                    'chainId': 'eip155:1',
                    'connectorType': 'injected',
                    'message': msg,
                    'mode': 'login-or-sign-up',
                    'signature': sign,
                    'walletClientType': 'rabby_wallet',
                },
                headers=self.privy_headers,
            )
            self.tls.sess.headers.update({
                'authorization': 'Bearer' + token,
            })
            self.has_email = any(a.get('type') == 'email' and a.get('verified_at') and a.get('address')
                                 for a in linked_accounts)
            self.embedded_wallet = next((a['address'] for a in linked_accounts
                                         if a.get('connector_type') == 'embedded' and
                                         a.get('recovery_method') == 'privy'), '')
        except Exception as e:
            raise Exception(f'Authenticate failed: {e}')

    async def sign_in(self):
        nonce = await self._init()
        issued_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + 'Z'

        await wait_a_bit(5)

        msg = f'zora.co wants you to sign in with your Ethereum account:\n' \
              f'{self.account.evm_address}\n\n' \
              f'By signing, you are proving you own this wallet and logging in. ' \
              f'This does not initiate a transaction or cost any fees.\n\n' \
              f'URI: https://zora.co\n' \
              f'Version: 1\n' \
              f'Chain ID: 1\n' \
              f'Nonce: {nonce}\n' \
              f'Issued At: {issued_at}\n' \
              f'Resources:\n' \
              f'- https://privy.io'
        signature = self.account.sign_message(msg)

        await self._authenticate(msg, signature)

        logger.info(f'{self.account.idx}) Logged in')
        await wait_a_bit(3)

    async def _sessions(self):
        try:
            token = await self.tls.post(
                'https://privy.zora.co/api/v1/sessions',
                [200], lambda r: r['token'],
                json={'refresh_token': 'deprecated'},
                headers=self.privy_headers,
            )
            self.tls.sess.headers.update({
                'authorization': 'Bearer ' + token,
            })
        except Exception as e:
            raise Exception(f'Sessions failed: {e}') from e

    async def ensure_authorized(self, refresh: bool = False):
        if self.tls.sess.headers.get('authorization') is None:
            await self.sign_in()
            refresh = True
        if refresh:
            await self._sessions()

    def _non_bearer_headers(self) -> dict:
        token = self.tls.sess.headers['authorization']
        if token.startswith('Bearer '):
            token = token[7:]
        return {'authorization': token}

    async def get_top_today(self) -> list[dict]:
        await self.ensure_authorized()
        try:
            return await self.tls.post(
                'https://api.zora.co/universal/graphql',
                [200], lambda r: [edge['node'] for edge in r['data']['exploreList']['edges']],
                json={
                    'query': 'query ExplorePageQuery(\n  $listType: ExploreListType!\n  $first: Int!\n  $after: String\n) {\n  ...ExploreList_query_37To9H\n}\n\nfragment Avatar_avatar on GraphQLMediaImage {\n  mimeType\n  downloadableUri\n  height\n  width\n  blurhash\n}\n\nfragment CoinListItem_20Token on GraphQLZora20Token {\n  address\n  chainId\n  creatorProfile {\n    __typename\n    profileId\n    handle\n    avatar {\n      ...Avatar_avatar\n    }\n    id\n  }\n  id\n  name\n  symbol\n  volume(periodHours: 24)\n  uniqueHolders\n  createdAt\n  mediaContent {\n    __typename\n    ...PreviewMediaRenderer_media\n  }\n  ...ExploreCoinMarketCap_20Token\n}\n\nfragment ExploreCoinMarketCap_20Token on GraphQLZora20Token {\n  marketCap\n  marketCapDelta(periodHours: 24)\n}\n\nfragment ExploreList_query_37To9H on Query {\n  exploreList(listType: $listType, first: $first, after: $after) {\n    edges {\n      node {\n        id\n        ...CoinListItem_20Token\n        __typename\n      }\n      cursor\n    }\n    pageInfo {\n      endCursor\n      hasNextPage\n    }\n  }\n}\n\nfragment PreviewMediaRenderer_media on IGraphQLMedia {\n  __isIGraphQLMedia: __typename\n  __typename\n  mimeType\n  originalUri\n  downloadableUri\n  previewImage {\n    __typename\n    mimeType\n    downloadableUri\n    height\n    width\n    blurhash\n  }\n}\n',
                    'variables': {
                        'after': None,
                        'first': 20,
                        'listType': 'TOP_VOLUME_24H',
                    },
                },
            )
        except Exception as e:
            raise Exception(f'Get top today: {e}')

    async def get_following_recommended(self) -> list[dict]:
        await self.ensure_authorized()
        try:
            return await self.tls.get(
                'https://api.zora.co/discover/following_recommended',
                [200], lambda r: r['data'],
            )
        except Exception as e:
            raise Exception(f'Get following recommended: {e}')

    async def follow(self, profile_id: str):
        await self.ensure_authorized()
        try:
            status = await self.tls.post(
                'https://api.zora.co/universal/graphql',
                [200], lambda r: r['data']['follow']['vcFollowingStatus'],
                json={
                    'query': 'mutation FollowActionsFollowMutation(\n  $profileId: String!\n) {\n  follow(followeeId: $profileId) {\n    __typename\n    handle\n    vcFollowingStatus\n    id\n  }\n}\n',
                    'variables': {
                        'profileId': profile_id,
                    },
                },
            )
            if status != 'FOLLOWING':
                raise Exception(f'Status: {status}')
        except Exception as e:
            raise Exception(f'Follow failed: {e}')

    async def get_coin_info(self, chain_id: int, address: str) -> dict:
        await self.ensure_authorized()
        try:
            return await self.tls.post(
                'https://api.zora.co/universal/graphql',
                [200], lambda r: r['data']['zora20Token'],
                json={
                    'query': 'query ContractAddressCoinPageQuery(\n  $chainId: Int!\n  $address: String!\n) {\n  zora20Token(chainId: $chainId, address: $address) {\n    coinName: name\n    coinDescription: description\n    multichainAddress\n    isBlocked\n    coinMedia: media {\n      previewImage {\n        __typename\n        originalUri\n      }\n    }\n    ...CoinMedia_post\n    ...CollectionPanel_collectionOrToken\n    id\n  }\n}\n\nfragment Avatar_avatar on GraphQLMediaImage {\n  mimeType\n  downloadableUri\n  height\n  width\n  blurhash\n}\n\nfragment BuyForm_token on GraphQLZora1155Token {\n  chainId\n  address\n  tokenId\n  name\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n      ... on GraphQLUniswapV3SecondarySale {\n        uniswapV3PoolAddress\n        erc20ZAddress\n      }\n    }\n  }\n  ...TokenField_token\n}\n\nfragment CheckoutButtons_coin on GraphQLZora20Token {\n  chainId\n  address\n  ...CheckoutModal_coin\n}\n\nfragment CheckoutFlow_coin on GraphQLZora20Token {\n  chainId\n  address\n  uniswapPoolAddress\n  creatorProfile {\n    __typename\n    vcFollowingStatus\n    id\n  }\n  vcOwnedCount20: vcOwnedCount\n  mediaContent {\n    __typename\n    preview: previewImage {\n      __typename\n      icon\n    }\n  }\n  ...useSwap_coin\n  ...ShareModal_collectionOrToken\n}\n\nfragment CheckoutModal_coin on GraphQLZora20Token {\n  ...CheckoutFlow_coin\n}\n\nfragment CoinMedia_post on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  chainId\n  address\n  name\n  creatorAddress\n  mediaContent {\n    __typename\n    mimeType\n    downloadableUri\n    previewImage {\n      __typename\n      large\n    }\n  }\n}\n\nfragment CointagButton_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  cointag {\n    coinTagAddress\n    splitPercentage\n    creatorAddress\n    erc20Address\n    id\n  }\n}\n\nfragment CollectionAttributionCreatorProfile_profile on IGraphQLProfile {\n  __isIGraphQLProfile: __typename\n  handle\n  profileId\n  avatar {\n    ...Avatar_avatar\n  }\n}\n\nfragment CollectionDetails_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  __typename\n  address\n  chainId\n  name\n  description\n  media {\n    __typename\n    previewImage {\n      __typename\n      large\n    }\n  }\n  ... on GraphQLZora1155Token {\n    tokenCreationTime\n  }\n  creatorProfile {\n    __typename\n    ...CollectionAttributionCreatorProfile_profile\n    id\n  }\n  ...MoreActionsMenu_collectionOrToken\n  ...EditPostForm_collectionOrToken\n  ...ShareModal_collectionOrToken\n}\n\nfragment CollectionPanel_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  __typename\n  name\n  chainId\n  address\n  media {\n    __typename\n    previewImage {\n      __typename\n      small\n    }\n  }\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    collection {\n      __typename\n      name\n      media {\n        __typename\n        previewImage {\n          __typename\n          small\n        }\n      }\n      id\n    }\n  }\n  ...CollectionDetails_collectionOrToken\n  ...CointagButton_collectionOrToken\n  ...MintActivity_collectionOrToken\n  ...MoreActionsMenu_collectionOrToken\n  ...NFTCheckoutButton_token\n  ...CheckoutFlow_coin\n  ...CheckoutButtons_coin\n}\n\nfragment EditPostForm_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  id\n  address\n  name\n  description\n  tokenUri\n  media {\n    __typename\n    downloadableUri\n    mimeType\n    previewImage {\n      __typename\n      downloadableUri\n      mimeType\n    }\n  }\n  mediaContent {\n    __typename\n    downloadableUri\n    mimeType\n    previewImage {\n      __typename\n      downloadableUri\n      mimeType\n    }\n  }\n  ... on GraphQLZora1155Token {\n    tokenId\n    metadataRaw\n  }\n}\n\nfragment MintActivity_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  __typename\n  id\n  chainId\n  address\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  ...PostActionsBase_collectionOrToken_3daFZa\n}\n\nfragment MintButton_token on GraphQLZora1155Token {\n  chainId\n  address\n  tokenId\n  ...useMint_token\n}\n\nfragment MintCheckoutFlow_token on GraphQLZora1155Token {\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n      price {\n        mintFee\n      }\n    }\n  }\n  ...MintButton_token\n}\n\nfragment MintProgress_token on GraphQLZora1155Token {\n  createdAt\n  totalTokenMints\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n      ... on GraphQLTimedSale {\n        currentMarketEth\n        minimumMarketEth\n        marketCountdown\n      }\n    }\n  }\n}\n\nfragment MoreActionsMenu_DesktopMoreActionsDropdown_collectionOrToken on IGraphQLCollectionOrToken {\n  __isIGraphQLCollectionOrToken: __typename\n  __typename\n  chainName\n  chainId\n  address\n  creatorAddress\n  name\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  ...useRefreshMetadata_collectionOrToken\n  ...EditPostForm_collectionOrToken\n}\n\nfragment MoreActionsMenu_MobileMoreActionsModal_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  __typename\n  chainName\n  chainId\n  address\n  creatorAddress\n  name\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  ...useRefreshMetadata_collectionOrToken\n  ...EditPostForm_collectionOrToken\n}\n\nfragment MoreActionsMenu_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  __typename\n  chainId\n  address\n  mediaContent {\n    __typename\n    downloadableUri\n    mimeType\n  }\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  ... on GraphQLZora20Token {\n    uniswapPoolAddress\n  }\n  ... on GraphQLZora1155Token {\n    salesStrategy {\n      __typename\n      sale {\n        __typename\n        saleType\n        ... on GraphQLUniswapV3SecondarySale {\n          erc20ZAddress\n          state\n          uniswapV3PoolAddress\n        }\n      }\n    }\n  }\n  ...MoreActionsMenu_MobileMoreActionsModal_collectionOrToken\n  ...MoreActionsMenu_DesktopMoreActionsDropdown_collectionOrToken\n  ...EditPostForm_collectionOrToken\n}\n\nfragment NFTCheckoutButton_token on IGraphQLCollectionOrToken {\n  __isIGraphQLCollectionOrToken: __typename\n  tokenStandard\n  multichainAddress\n  chainId\n  address\n  name\n  totalTokenMints\n  ... on GraphQLZora1155Token {\n    tokenId\n    salesStrategy {\n      __typename\n      sale {\n        __typename\n        saleType\n        startTime\n        endTime\n        price {\n          tokenPrice\n        }\n        ... on GraphQLTimedSale {\n          currentMarketEth\n          minimumMarketEth\n          marketCountdown\n        }\n      }\n    }\n  }\n  ...NFTCheckoutModal_token\n}\n\nfragment NFTCheckoutFlow_token on GraphQLZora1155Token {\n  chainId\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n    }\n  }\n  ...MintCheckoutFlow_token\n  ...SwapCheckoutFlow_token\n}\n\nfragment NFTCheckoutModal_token on GraphQLZora1155Token {\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n    }\n  }\n  ...NFTCheckoutFlow_token\n}\n\nfragment PostActionsBase_collectionOrToken_3daFZa on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  zoraComments(first: 20) {\n    count\n  }\n  ... on IGraphQLCollectionOrToken {\n    __isIGraphQLCollectionOrToken: __typename\n    totalTokenMints\n  }\n  ...PostSaleAction_collectionOrToken\n  ...ShareModal_collectionOrToken\n}\n\nfragment PostSaleAction_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  ... on IGraphQLCollectionOrToken {\n    __isIGraphQLCollectionOrToken: __typename\n    totalTokenMints\n  }\n  ... on GraphQLZora1155Token {\n    salesStrategy {\n      __typename\n      sale {\n        __typename\n        endTime\n        price {\n          tokenPrice\n        }\n        ... on GraphQLTimedSale {\n          currentMarketEth\n          minimumMarketEth\n          marketCountdown\n        }\n      }\n    }\n  }\n  ...MintProgress_token\n}\n\nfragment SellForm_token on GraphQLZora1155Token {\n  chainId\n  address\n  tokenId\n  name\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n      ... on GraphQLUniswapV3SecondarySale {\n        uniswapV3PoolAddress\n      }\n    }\n  }\n  ...TokenField_token\n}\n\nfragment ShareModal_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  __typename\n  chainId\n  address\n  name\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  ... on GraphQLZora1155Token {\n    salesStrategy {\n      __typename\n      sale {\n        __typename\n        state\n      }\n    }\n  }\n}\n\nfragment SwapCheckoutFlow_token on GraphQLZora1155Token {\n  chainId\n  address\n  tokenId\n  name\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n      price {\n        tokenPrice\n      }\n    }\n  }\n  ...BuyForm_token\n  ...SellForm_token\n}\n\nfragment TokenField_token on GraphQLZora1155Token {\n  name\n  media {\n    __typename\n    previewImage {\n      __typename\n      small\n    }\n  }\n}\n\nfragment useMintConfig_token on GraphQLZora1155Token {\n  chainId\n  address\n  tokenId\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n      saleType\n      price {\n        mintFee\n      }\n      minterAddress\n    }\n  }\n}\n\nfragment useMint_token on GraphQLZora1155Token {\n  chainId\n  address\n  tokenId\n  name\n  ...useMintConfig_token\n}\n\nfragment useRefreshMetadata_collectionOrToken on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  __typename\n  chainId\n  address\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n}\n\nfragment useSwap_coin on GraphQLZora20Token {\n  address\n  title: name\n  uniswapPoolAddress\n}\n',
                    'variables': {
                        'address': address.lower(),
                        'chainId': chain_id,
                    },
                },
            )
        except Exception as e:
            raise Exception(f'Get coin info: {e}')

    async def get_coin_stats(self, chain_id: int, address: str) -> dict:
        await self.ensure_authorized()
        try:
            return await self.tls.post(
                'https://api.zora.co/universal/graphql',
                [200], lambda r: r['data']['zora20Token'],
                json={
                    'query': 'query CoinStatsQuery(\n  $chainId: Int!\n  $address: String!\n) {\n  zora20Token(chainId: $chainId, address: $address) {\n    id\n    marketCap\n    marketCapDelta\n    volume\n    totalVolume\n    creatorEarnings {\n      amountUsd\n    }\n    chainId\n    address\n    ...useCoinMarketCapDisplay_token\n  }\n}\n\nfragment useCoinMarketCapDisplay_token on GraphQLZora20Token {\n  marketCap\n  marketCapDelta\n}\n',
                    'variables': {
                        'address': address.lower(),
                        'chainId': chain_id,
                    },
                },
            )
        except Exception as e:
            raise Exception(f'Get coin stats: {e}')

    async def get_coin_quote(
            self,
            pool_address: str,
            chain_id: int,
            amount: int,
            quote_type: Literal['buy', 'sell'],
    ) -> dict:
        await self.ensure_authorized()
        try:
            inp = json.dumps({
                'json': {
                    'poolAddress': pool_address.lower(),
                    'chainId': chain_id,
                    'account': self.account.evm_address,
                    'amount': str(amount),
                    'type': quote_type,
                }
            })
            return await self.tls.get(
                'https://zora.co/api/trpc/uniswap.getCoinQuote',
                [200], lambda r: r['result']['data']['json'],
                params={'input': inp},
                headers=self._non_bearer_headers(),
            )
        except Exception as e:
            raise Exception(f'Get coin quote: {e}')

    async def _grid_pagination_query(
            self,
            profile_id: str,
            pagination: dict,
            list_type: Literal['COLLECTED', 'CREATED'] = 'COLLECTED',
    ):
        await self.ensure_authorized()
        try:
            query = 'query ProfileGalleryGridPaginationQuery(\n  $chainIds: [Int!]\n  $cursor: String\n  $first: Int = 12\n  $listType: EProfileListType = CREATED\n  $id: ID!\n) {\n  node(id: $id) {\n    __typename\n    ...ProfileGalleryGrid_profileZoraPosts_RQWMC\n    id\n  }\n}\n\nfragment MintProgress_token on GraphQLZora1155Token {\n  createdAt\n  totalTokenMints\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n      ... on GraphQLTimedSale {\n        currentMarketEth\n        minimumMarketEth\n        marketCountdown\n      }\n    }\n  }\n}\n\nfragment PreviewMediaRenderer_media on IGraphQLMedia {\n  __isIGraphQLMedia: __typename\n  __typename\n  mimeType\n  originalUri\n  downloadableUri\n  previewImage {\n    __typename\n    mimeType\n    downloadableUri\n    height\n    width\n    blurhash\n  }\n}\n\nfragment ProfileGalleryGridItem_post on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  id\n  __typename\n  name\n  address\n  chainId\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  mediaContent {\n    __typename\n    ...PreviewMediaRenderer_media\n  }\n  ...ProfileGalleryPostStats_post\n}\n\nfragment ProfileGalleryGridItem_profile on IGraphQLProfile {\n  __isIGraphQLProfile: __typename\n  ... on GraphQLAccountProfile {\n    publicWallet {\n      walletAddress\n      id\n    }\n  }\n  ... on GraphQLWalletProfile {\n    walletAddress\n  }\n  vcFollowingStatus\n}\n\nfragment ProfileGalleryGrid_profileZoraPosts_RQWMC on IGraphQLProfile {\n  __isIGraphQLProfile: __typename\n  handle\n  profileZoraPosts(listType: $listType, chainIds: $chainIds, first: $first, after: $cursor) {\n    edges {\n      junction {\n        __typename\n        ... on GraphQLProfileToZora20TokenJunction {\n          ownedCount\n        }\n      }\n      node {\n        __typename\n        ...ProfileGalleryGridItem_post\n        media {\n          __typename\n          mimeType\n        }\n        id\n      }\n      cursor\n    }\n    pageInfo {\n      endCursor\n      hasNextPage\n    }\n  }\n  ...ProfileGalleryGridItem_profile\n  id\n}\n\nfragment ProfileGalleryPostStats_post on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  chainId\n  address\n  zoraComments {\n    count\n  }\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  ... on GraphQLZora20Token {\n    __typename\n    id\n    uniqueHolders\n  }\n  ... on GraphQLZora1155Token {\n    __typename\n    salesStrategy {\n      __typename\n      ... on GraphQLZoraSaleStrategyUniswapV3Secondary {\n        __typename\n        sale {\n          price {\n            tokenPrice\n          }\n        }\n      }\n      ... on GraphQLZoraSaleStrategyZoraTimedMinter {\n        __typename\n        sale {\n          endTime\n          minimumMarketEth\n          marketCountdown\n          currentMarketEth\n        }\n      }\n    }\n    totalTokenMints\n    ...MintProgress_token\n  }\n}\n'
            variables = {
                'chainIds': None,
                'cursor': pagination['cursor'],
                'first': 9,
                'id': pagination['id'],
                'listType': list_type,
            }
            posts_info = await self.tls.post(
                'https://api.zora.co/universal/graphql',
                [200], lambda r: r['data']['node']['profileZoraPosts'],
                json={
                    'query': query,
                    'variables': variables,
                },
            )
            posts = [edge['node'] for edge in posts_info['edges']]
            return posts, posts_info['pageInfo']
        except Exception as e:
            raise Exception(f'Grid pagination query failed: {e}') from e

    async def get_holdings(self, profile_id: str, pagination: dict = None) -> tuple[list[dict], dict]:
        await self.ensure_authorized()
        try:
            if pagination:
                return await self._grid_pagination_query(profile_id, pagination)
            query = 'query ProfileGalleryWebCollectedQuery(\n  $profileId: String!\n  $chainIds: [Int!]\n) {\n  profile(identifier: $profileId) {\n    __typename\n    ...ProfileGalleryGrid_profileZoraPosts_1yp2YS\n    id\n  }\n}\n\nfragment MintProgress_token on GraphQLZora1155Token {\n  createdAt\n  totalTokenMints\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n      ... on GraphQLTimedSale {\n        currentMarketEth\n        minimumMarketEth\n        marketCountdown\n      }\n    }\n  }\n}\n\nfragment PreviewMediaRenderer_media on IGraphQLMedia {\n  __isIGraphQLMedia: __typename\n  __typename\n  mimeType\n  originalUri\n  downloadableUri\n  previewImage {\n    __typename\n    mimeType\n    downloadableUri\n    height\n    width\n    blurhash\n  }\n}\n\nfragment ProfileGalleryGridItem_post on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  id\n  __typename\n  name\n  address\n  chainId\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  mediaContent {\n    __typename\n    ...PreviewMediaRenderer_media\n  }\n  ...ProfileGalleryPostStats_post\n}\n\nfragment ProfileGalleryGridItem_profile on IGraphQLProfile {\n  __isIGraphQLProfile: __typename\n  ... on GraphQLAccountProfile {\n    publicWallet {\n      walletAddress\n      id\n    }\n  }\n  ... on GraphQLWalletProfile {\n    walletAddress\n  }\n  vcFollowingStatus\n}\n\nfragment ProfileGalleryGrid_profileZoraPosts_1yp2YS on IGraphQLProfile {\n  __isIGraphQLProfile: __typename\n  handle\n  profileZoraPosts(listType: COLLECTED, chainIds: $chainIds, first: 12) {\n    edges {\n      junction {\n        __typename\n        ... on GraphQLProfileToZora20TokenJunction {\n          ownedCount\n        }\n      }\n      node {\n        __typename\n        ...ProfileGalleryGridItem_post\n        media {\n          __typename\n          mimeType\n        }\n        id\n      }\n      cursor\n    }\n    pageInfo {\n      endCursor\n      hasNextPage\n    }\n  }\n  ...ProfileGalleryGridItem_profile\n  id\n}\n\nfragment ProfileGalleryPostStats_post on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  chainId\n  address\n  zoraComments {\n    count\n  }\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  ... on GraphQLZora20Token {\n    __typename\n    id\n    uniqueHolders\n  }\n  ... on GraphQLZora1155Token {\n    __typename\n    salesStrategy {\n      __typename\n      ... on GraphQLZoraSaleStrategyUniswapV3Secondary {\n        __typename\n        sale {\n          price {\n            tokenPrice\n          }\n        }\n      }\n      ... on GraphQLZoraSaleStrategyZoraTimedMinter {\n        __typename\n        sale {\n          endTime\n          minimumMarketEth\n          marketCountdown\n          currentMarketEth\n        }\n      }\n    }\n    totalTokenMints\n    ...MintProgress_token\n  }\n}\n'
            variables = {
                'chainIds': None,
                'profileId': profile_id,
            }
            posts_info = await self.tls.post(
                'https://api.zora.co/universal/graphql',
                [200], lambda r: r['data']['profile']['profileZoraPosts'],
                json={
                    'query': query,
                    'variables': variables,
                },
            )
            posts = [edge['node'] for edge in posts_info['edges']]
            return posts, posts_info['pageInfo']
        except Exception as e:
            raise Exception(f'Get holdings: {e}')

    async def get_created(self, profile_id: str, pagination: dict = None) -> tuple[list[dict], dict]:
        await self.ensure_authorized()
        try:
            if pagination:
                return await self._grid_pagination_query(profile_id, pagination, list_type='CREATED')
            query = 'query ProfileGalleryWebCreatedQuery(\n  $profileId: String!\n  $chainIds: [Int!]\n) {\n  profile(identifier: $profileId) {\n    __typename\n    ...ProfileGalleryGrid_profileZoraPosts_2PcsgU\n    id\n  }\n}\n\nfragment MintProgress_token on GraphQLZora1155Token {\n  createdAt\n  totalTokenMints\n  salesStrategy {\n    __typename\n    sale {\n      __typename\n      ... on GraphQLTimedSale {\n        currentMarketEth\n        minimumMarketEth\n        marketCountdown\n      }\n    }\n  }\n}\n\nfragment PreviewMediaRenderer_media on IGraphQLMedia {\n  __isIGraphQLMedia: __typename\n  __typename\n  mimeType\n  originalUri\n  downloadableUri\n  previewImage {\n    __typename\n    mimeType\n    downloadableUri\n    height\n    width\n    blurhash\n  }\n}\n\nfragment ProfileGalleryGridItem_post on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  id\n  __typename\n  name\n  address\n  chainId\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  mediaContent {\n    __typename\n    ...PreviewMediaRenderer_media\n  }\n  ...ProfileGalleryPostStats_post\n}\n\nfragment ProfileGalleryGridItem_profile on IGraphQLProfile {\n  __isIGraphQLProfile: __typename\n  ... on GraphQLAccountProfile {\n    publicWallet {\n      walletAddress\n      id\n    }\n  }\n  ... on GraphQLWalletProfile {\n    walletAddress\n  }\n  vcFollowingStatus\n}\n\nfragment ProfileGalleryGridProfileDetails_profile on IGraphQLProfile {\n  __isIGraphQLProfile: __typename\n  vcFollowingStatus\n  handle\n}\n\nfragment ProfileGalleryGrid_profileZoraPosts_2PcsgU on IGraphQLProfile {\n  __isIGraphQLProfile: __typename\n  profileZoraPosts(listType: CREATED, chainIds: $chainIds, first: 12) {\n    edges {\n      junction {\n        __typename\n        ... on GraphQLProfileToZora20TokenJunction {\n          ownedCount\n        }\n      }\n      node {\n        __typename\n        ...ProfileGalleryGridItem_post\n        media {\n          __typename\n          mimeType\n        }\n        id\n      }\n      cursor\n    }\n    pageInfo {\n      endCursor\n      hasNextPage\n    }\n  }\n  ...ProfileGalleryGridProfileDetails_profile\n  ...ProfileGalleryGridItem_profile\n  id\n}\n\nfragment ProfileGalleryPostStats_post on IGraphQLPostBase {\n  __isIGraphQLPostBase: __typename\n  chainId\n  address\n  zoraComments {\n    count\n  }\n  ... on IGraphQLToken {\n    __isIGraphQLToken: __typename\n    tokenId\n  }\n  ... on GraphQLZora20Token {\n    __typename\n    id\n    uniqueHolders\n  }\n  ... on GraphQLZora1155Token {\n    __typename\n    salesStrategy {\n      __typename\n      ... on GraphQLZoraSaleStrategyUniswapV3Secondary {\n        __typename\n        sale {\n          price {\n            tokenPrice\n          }\n        }\n      }\n      ... on GraphQLZoraSaleStrategyZoraTimedMinter {\n        __typename\n        sale {\n          endTime\n          minimumMarketEth\n          marketCountdown\n          currentMarketEth\n        }\n      }\n    }\n    totalTokenMints\n    ...MintProgress_token\n  }\n}\n'
            variables = {
                'chainIds': None,
                'profileId': profile_id,
            }
            posts_info = await self.tls.post(
                'https://api.zora.co/universal/graphql',
                [200], lambda r: r['data']['profile']['profileZoraPosts'],
                json={
                    'query': query,
                    'variables': variables,
                },
            )
            posts = [edge['node'] for edge in posts_info['edges']]
            return posts, posts_info['pageInfo']
        except Exception as e:
            raise Exception(f'Get holdings: {e}')

    async def get_my_profile_ids(self) -> tuple[str, str]:
        await self.ensure_authorized()
        try:
            profile = await self.tls.post(
                'https://api.zora.co/universal/graphql',
                [200], lambda r: r['data']['profile'],
                json={
                    'query': 'query MenuWebQuery(\n  $profileId: String!\n) {\n  profile(identifier: $profileId) {\n    __typename\n    handle\n    avatar {\n      ...Avatar_avatar\n    }\n    id\n  }\n}\n\nfragment Avatar_avatar on GraphQLMediaImage {\n  mimeType\n  downloadableUri\n  height\n  width\n  blurhash\n}\n',
                    'variables': {
                        'profileId': self.account.evm_address.lower(),
                    },
                },
            )
            return profile['id'], profile['handle']
        except Exception as e:
            raise Exception(f'Get my profile id ailed: {e}') from e

    async def get_my_account(self, can_be_not_found: bool = False) -> Optional[dict]:
        await self.ensure_authorized()
        try:
            inp = json.dumps({
                'json': None,
                'meta': {'values': ['undefined']},
            })
            statuses = [200]
            if can_be_not_found:
                statuses.append(404)
            resp = await self.tls.get(
                'https://zora.co/api/trpc/account.getAccount',
                statuses,
                params={'input': inp},
                headers=self._non_bearer_headers(),
            )
            error = resp.get('error', {}).get('json', {}).get('message')
            if can_be_not_found and error == 'NOT_FOUND':
                return None
            try:
                if 'error' in resp:
                    raise Exception()
                return resp['result']['data']['json']
            except Exception as e:
                raise Exception(f'Bad response: {resp}')
        except Exception as e:
            raise Exception(f'Get my account failed: {e}') from e

    async def get_my_profile(self) -> dict:
        await self.ensure_authorized()
        try:
            inp = json.dumps({
                'json': self.account.evm_address,
            })
            return await self.tls.get(
                'https://zora.co/api/trpc/profile.getProfile',
                [200], lambda r: r['result']['data']['json'],
                params={'input': inp},
                headers=self._non_bearer_headers(),
            )
        except Exception as e:
            raise Exception(f'Get my profile failed: {e}') from e

    async def init_set_email(self, email_username: str):
        await self.ensure_authorized(refresh=True)
        try:
            success = await self.tls.post(
                'https://privy.zora.co/api/v1/passwordless/init',
                [200], lambda r: r['success'],
                json={'email': email_username},
                headers=self.privy_headers,
            )
            if not success:
                raise Exception('Not success')
        except Exception as e:
            raise Exception(f'Init set email failed: {e}') from e

    async def link_email(self, email_username: str, code: str):
        await self.ensure_authorized()
        try:
            await self.tls.post(
                'https://privy.zora.co/api/v1/passwordless/link',
                [200],
                json={
                    'code': code,
                    'email': email_username,
                },
                headers=self.privy_headers,
            )
            await self._sessions()
        except Exception as e:
            raise Exception(f'Link email failed: {e}') from e

    async def oauth_init(
            self,
            code_challenge: str,
            provider: str,
            redirect_to: str,
            state_code: str,
    ):
        await self.ensure_authorized()
        try:
            await self.tls.post(
                'https://privy.zora.co/api/v1/oauth/init', [200],
                json={
                    'code_challenge': code_challenge,
                    'provider': provider,
                    'redirect_to': redirect_to,
                    'state_code': state_code,
                },
                headers=self.privy_headers,
            )
        except Exception as e:
            raise Exception(f'Oauth init failed: {e}') from e

    OAUTH_CALLBACK_URL = 'https://auth.privy.io/api/v1/oauth/callback'

    async def oauth_callback(self, state: str, code: str, redirect_to: str) -> str:
        await self.ensure_authorized()
        try:
            resp = await self.tls.get(
                self.OAUTH_CALLBACK_URL, [200], raw=True,
                params={
                    'state': state,
                    'code': code,
                },
                headers={
                    'referer': 'https://x.com/',
                    'sec-fetch-dest': 'document',
                    'sec-fetch-mode': 'navigate',
                    'sec-fetch-site': 'cross-site',
                    'sec-fetch-user': '?1',
                    'upgrade-insecure-requests': '1',
                },
            )
            redirected = resp.url
            if not redirected.startswith(redirect_to):
                raise Exception(f'Bad redirected url: {redirected}')
            privy_code = get_query_param(redirected, 'privy_oauth_code')
            if privy_code is None:
                raise Exception(f'Privy oauth code not found: {redirected}')
            return privy_code
        except Exception as e:
            raise Exception(f'Oauth callback failed: {e}') from e

    async def oauth_link(self, auth_code: str, code_verifier: str, state_code: str):
        await self.ensure_authorized()
        try:
            resp = await self.tls.post(
                'https://privy.zora.co/api/v1/oauth/link', [200],
                json={
                    'authorization_code': auth_code,
                    'code_verifier': code_verifier,
                    'state_code': state_code,
                },
                headers=self.privy_headers,
            )
        except Exception as e:
            raise Exception(f'Oauth link failed: {e}') from e

    async def is_username_available(self, username: str) -> bool:
        await self.ensure_authorized()
        try:
            inp = json.dumps({
                'json': username,
            })
            status = await self.tls.get(
                'https://zora.co/api/trpc/account.checkUsername',
                [200], lambda r: r['result']['data']['json']['status'],
                params={'input': inp},
                headers={
                    'referrer': 'https://zora.co/onboarding',
                    **self._non_bearer_headers(),
                }
            )
            return status == 'available'
        except Exception as e:
            raise Exception(f'Check username available failed: {e}') from e

    @async_retry
    async def ipfs_upload(self, name: str, content: bytes, content_type: str = 'image/png') -> str:
        await self.ensure_authorized(refresh=True)
        try:
            multipart = CurlMime()
            multipart.addpart(name=name, data=content, filename=name, content_type='image/png')
            return await self.tls.post(
                'https://ipfs-uploader.zora.co/api/v0/add?cid-version=1',
                [200], lambda r: r['cid'],
                multipart=multipart,
            )
        except Exception as e:
            raise Exception(f'IPFS upload failed: {e}') from e

    async def create_account(self, username: str, avatar: str):
        await self.ensure_authorized()
        try:
            await self.tls.post(
                'https://zora.co/api/trpc/account.createAccount',
                [200],
                json={
                    "json": {
                        "username": username,
                        "walletAddress": self.account.evm_address,
                        "marketingOptIn": True,
                        "referrer": None,
                        "profile": {
                            "displayName": username,
                            "description": None,
                            "avatarUri": avatar,
                        },
                    },
                    "meta": {
                        "values": {
                            "referrer": ["undefined"],
                            "profile.description": ["undefined"],
                        },
                    },
                },
                headers={
                    'referrer': 'https://zora.co/onboarding',
                    **self._non_bearer_headers(),
                }
            )
            await self._sessions()
        except Exception as e:
            raise Exception(f'Create account failed: {e}') from e

    async def update_profile(self, username: str, avatar: str):
        await self.ensure_authorized()
        try:
            await self.tls.post(
                'https://zora.co/api/trpc/profile.updateProfile',
                [200],
                json={
                    "json": {
                        "avatarUri": avatar,
                        "displayName": username,
                        "description": None,
                        "website": None,
                    },
                    "meta": {
                        "values": {
                            "description": ["undefined"],
                            "website": ["undefined"],
                        },
                    },
                },
                headers={
                    'referrer': 'https://zora.co/settings?tab=profile',
                    **self._non_bearer_headers(),
                }
            )
        except Exception as e:
            raise Exception(f'Update profile failed: {e}') from e

    async def account_update_socials(self, referrer: str):
        await self.ensure_authorized()
        try:
            await self.tls.post(
                'https://zora.co/api/trpc/account.updateSocials',
                [200],
                json={
                    'json': None,
                    'meta': {
                        'values': ['undefined']
                    }
                },
                headers={
                    'referrer': referrer,
                    **self._non_bearer_headers(),
                }
            )
        except Exception as e:
            raise Exception(f'Account update socials failed: {e}') from e

    async def create_smart_wallet(self, chain_id: int) -> str:
        await self.ensure_authorized()
        try:
            return await self.tls.post(
                'https://zora.co/api/trpc/smartWallet.createSmartWallet',
                [200], lambda r: r['result']['data']['json']['smartWalletAddress'],
                json={
                    'json': {
                        'chainId': chain_id,
                    },
                },
                headers=self._non_bearer_headers(),
            )
        except Exception as e:
            raise Exception(f'Create smart wallet failed: {e}') from e

    async def create_erc20_user_operation(self, tx: dict, meta: dict = None) -> tuple[dict, dict]:
        await self.ensure_authorized()
        try:
            body = {
                'json': tx,
                'meta': {
                    'values': {
                        'createSplitCalldata': ['undefined'],
                        'value': ['bigint'],
                    },
                } if meta is None else meta,
            }
            return await self.tls.post(
                'https://zora.co/api/trpc/create.createCreateERC20UserOperation',
                [200], lambda r: (r['result']['data']['json'], r['result']['data']['meta']),
                json=body,
                headers=self._non_bearer_headers(),
            )
        except Exception as e:
            raise Exception(f'Create ERC20 user operation failed: {e}') from e

    async def submit_user_operation(self, tx: dict, meta: dict) -> str:
        await self.ensure_authorized()
        try:
            body = {
                'json': tx,
                'meta': meta,
            }
            resp = await self.tls.post(
                'https://zora.co/api/trpc/smartWallet.submitUserOperation',
                [200], lambda r: r['result']['data']['json'],
                json=body,
                headers=self._non_bearer_headers(),
            )
            if not resp.get('success') or not resp.get('hash'):
                raise Exception(f'Bad response: {resp}')
            return resp['hash']
        except Exception as e:
            raise Exception(f'Submit user operation failed: {e}') from e

    async def recovery_key_material(self, wallet: str) -> tuple[str, str]:
        await self.ensure_authorized()
        try:
            return await self.tls.post(
                f'https://privy.zora.co/api/v1/embedded_wallets/{wallet}/recovery/key_material',
                [200], lambda r: (r['recovery_key'], r['recovery_type']),
                json={'chain_type': 'ethereum'},
                headers=self.privy_headers,
            )
        except Exception as e:
            raise Exception(f'Recovery key material failed: {e}') from e

    async def recovery_auth_share(self, wallet: str) -> str:
        await self.ensure_authorized()
        try:
            return await self.tls.post(
                f'https://privy.zora.co/api/v1/embedded_wallets/{wallet}/recovery/auth_share',
                [200], lambda r: r['share'],
                json={'chain_type': 'ethereum'},
                headers=self.privy_headers,
            )
        except Exception as e:
            raise Exception(f'Recovery auth share failed: {e}') from e

    async def recovery_shares(self, wallet: str, recovery_key_hash: str) -> tuple[str, str, bool]:
        await self.ensure_authorized()
        try:
            return await self.tls.post(
                f'https://privy.zora.co/api/v1/embedded_wallets/{wallet}/recovery/shares',
                [200], lambda r: (
                    r['encrypted_recovery_share'], r['encrypted_recovery_share_iv'], r['imported']
                ),
                json={
                    'chain_type': 'ethereum',
                    'recovery_key_hash': recovery_key_hash,
                },
                headers=self.privy_headers,
            )
        except Exception as e:
            raise Exception(f'Recovery shares failed: {e}') from e

    async def recovery_device(self, wallet: str, device_auth_share: str, device_id: str):
        await self.ensure_authorized()
        try:
            resp = await self.tls.post(
                f'https://privy.zora.co/api/v1/embedded_wallets/{wallet}/recovery/device',
                [200], lambda r: r,
                json={
                    'chain_type': 'ethereum',
                    'device_auth_share': device_auth_share,
                    'device_id': device_id,
                },
                headers=self.privy_headers,
            )
            if not resp.get('success'):
                raise Exception(f'Bad response: {resp}')
        except Exception as e:
            raise Exception(f'Recovery device failed: {e}') from e

    async def embedded_share(self, wallet: str, device_id: str):
        await self.ensure_authorized()
        try:
            await self.tls.post(
                f'https://privy.zora.co/api/v1/embedded_wallets/{wallet}/share',
                [200], lambda r: (r['imported'], r['share']),
                json={
                    'chain_type': 'ethereum',
                    'device_id': device_id,
                },
                headers=self.privy_headers,
            )
        except Exception as e:
            raise Exception(f'Embedded share failed: {e}') from e
