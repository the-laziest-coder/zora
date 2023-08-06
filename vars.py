import json


INVOLVED_CHAINS = ['Ethereum', 'Zora', 'Optimism']

SCANS = {
    'Ethereum': 'https://etherscan.io',
    'Optimism': 'https://optimistic.etherscan.io',
    'BSC': 'https://bscscan.com',
    'Gnosis': 'https://gnosisscan.io',
    'Polygon': 'https://polygonscan.com',
    'Fantom': 'https://ftmscan.com',
    'Arbitrum': 'https://arbiscan.io',
    'Avalanche': 'https://snowtrace.io',
    'zkSync': 'https://explorer.zksync.io',
    'zkEVM': 'https://zkevm.polygonscan.com',
    'Zora': 'https://explorer.zora.energy',
}

CHAIN_IDS = {
    'Ethereum': 1,
    'Optimism': 10,
    'BSC': 56,
    'Gnosis': 100,
    'Polygon': 137,
    'Fantom': 250,
    'Arbitrum': 42161,
    'Avalanche': 43114,
    'zkSync': 324,
    'zkEVM': 1101,
    'Zora': 7777777,
}

CHAIN_NAMES = {
    1: 'Ethereum',
    10: 'Optimism',
    56: 'BSC',
    100: 'Gnosis',
    137: 'Polygon',
    250: 'Fantom',
    42161: 'Arbitrum',
    43114: 'Avalanche',
    1313161554: 'Aurora',
    324: 'zkSync',
    1101: 'zkEVM',
    7777777: 'Zora',
}

EIP1559_CHAINS = ['Ethereum', 'Zora', 'Optimism']

NATIVE_TOKEN_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'

NATIVE_DECIMALS = 18

ZORA_BRIDGE_GAS_LIMIT = 100000

ZORA_BRIDGE_ADDRESS = '0x1a0ad011913A150f69f6A19DF447A0CfD9551054'
ZORA_BRIDGE_ABI = json.load(open('abi/zora_bridge.json'))

ZORA_ERC721_ABI = json.load(open('abi/zora_erc721.json'))
ZORA_ERC1155_ABI = json.load(open('abi/zora_erc_1155.json'))

MINTER_ADDRESSES = {
    'Ethereum': '0x8A1DBE9b1CeB1d17f92Bebf10216FCFAb5C3fbA7',
    'Optimism': '0x3678862f04290E565cCA2EF163BAeb92Bb76790C',
    'Zora': '0x169d9147dFc9409AfA4E558dF2C9ABeebc020182',
}
ZORA_MINTER_ABI = json.load(open('abi/zora_minter.json'))

ZORA_NFT_CREATOR_ADDRESS = '0xA2c2A96A232113Dd4993E8b048EEbc3371AE8d85'
ZORA_NFT_CREATOR_ABI = json.load(open('abi/zora_nft_creator.json'))

ZORA_CHAINS_MAP = {
    'eth': 'Ethereum',
    'oeth': 'Optimism',
    'zora': 'Zora',
}
