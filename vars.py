import json


INVOLVED_CHAINS = ['Zora', 'Base', 'Optimism', 'Ethereum', 'Arbitrum']

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
    'Base': 'https://basescan.org',
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
    'Base': 8453,
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
    8453: 'Base',
}

EIP1559_CHAINS = ['Ethereum', 'Zora', 'Optimism', 'Base', 'Arbitrum']

NATIVE_TOKEN_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'

NATIVE_DECIMALS = 18

ZORA_BRIDGE_GAS_LIMIT = 100000

ZORA_BRIDGE_ADDRESS = '0x1a0ad011913A150f69f6A19DF447A0CfD9551054'
ZORA_BRIDGE_ABI = json.load(open('abi/zora_bridge.json'))

ZORA_ERC721_ABI = json.load(open('abi/zora_erc721.json'))
ZORA_ERC1155_ABI = json.load(open('abi/zora_erc_1155.json'))
CUSTOM_ERC721_ABI = json.load(open('abi/custom_erc721.json'))

MINTER_ADDRESSES = {
    '2.0.0': {
        'Ethereum': '0x04E2516A2c207E84a1839755675dfd8eF6302F0a',
        'Optimism': '0x3678862f04290E565cCA2EF163BAeb92Bb76790C',
        'Zora': '0x04E2516A2c207E84a1839755675dfd8eF6302F0a',
        'Base': '0xFF8B0f870ff56870Dc5aBd6cB3E6E89c8ba2e062',
    },
    'Other': {
        'Ethereum': '0x8A1DBE9b1CeB1d17f92Bebf10216FCFAb5C3fbA7',
        'Optimism': '0x3678862f04290E565cCA2EF163BAeb92Bb76790C',
        'Zora': '0x169d9147dFc9409AfA4E558dF2C9ABeebc020182',
        'Base': '0xFF8B0f870ff56870Dc5aBd6cB3E6E89c8ba2e062',
    }
}

ZORA_MINTER_ABI = json.load(open('abi/zora_minter.json'))

MINT_REF_ADDRESS = '0xc474A9A00E56c3bF947C71EDd1515dAD5706d3D5'

ZORA_NFT_CREATOR_ADDRESS = '0xA2c2A96A232113Dd4993E8b048EEbc3371AE8d85'
ZORA_NFT_CREATOR_ABI = json.load(open('abi/zora_nft_creator.json'))

ZORA_1155_CREATOR_ADDRESS = '0x777777C338d93e2C7adf08D102d45CA7CC4Ed021'
ZORA_1155_CREATOR_ABI = json.load(open('abi/zora_1155_creator.json'))

EDITION_METADATA_RENDERER_ADDRESS = '0xCA7bF48453B72e4E175267127B4Ed7EB12F83b93'
EDITION_METADATA_RENDERER_ABI = json.load(open('abi/edition_metadata_renderer.json'))

ZORA_CHAINS_MAP = {
    'eth': 'Ethereum',
    'oeth': 'Optimism',
    'zora': 'Zora',
    'base': 'Base',
}

MINT_FUN_DATA_SUFFIX = '0021fb3f'
MINT_FUN_PASS_ADDRESS = '0x0000000000664ceffed39244a8312bD895470803'
MINT_FUN_PASS_ABI = json.load(open('abi/mint_fun_pass.json'))

ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'

PROTOCOL_REWARDS_ADDRESSES = {
    'Ethereum': [],
    'Zora': [
        '0x7777777F279eba3d3Ad8F4E708545291A6fDBA8B',
        '0x7777777A456fF23D9b6851184472c08FBDa73e32',
    ],
    'Optimism': [],
    'Base': ['0x7777777F279eba3d3Ad8F4E708545291A6fDBA8B'],
}
PROTOCOL_REWARDS_ABI = json.load(open('abi/protocol_rewards.json'))

LZ_CHAIN_IDS = {
    'Arbitrum': 110,
    'Optimism': 111,
    'Zora': 195,
}

ZERIUS_NFT_ADDRESS = '0x178608fFe2Cca5d36f3Fc6e69426c4D3A5A74A41'
ZERIUS_NFT_ABI = json.load(open('abi/zerius_nft.json'))

ZERIUS_REFUEL_ADDRESSES = {
    'Arbitrum': '0x412aea168aDd34361aFEf6a2e3FC01928Fba1248',
    'Optimism': '0x2076BDd52Af431ba0E5411b3dd9B5eeDa31BB9Eb',
    'Zora': '0x1fe2c567169d39CCc5299727FfAC96362b2Ab90E',
}
ZERIUS_REFUEL_ABI = json.load(open('abi/zerius_refuel.json'))
