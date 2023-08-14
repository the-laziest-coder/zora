import json


INVOLVED_CHAINS = ['Zora', 'Base', 'Optimism', 'Ethereum']

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

EIP1559_CHAINS = ['Ethereum', 'Zora', 'Optimism', 'Base']

NATIVE_TOKEN_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'

NATIVE_DECIMALS = 18

ZORA_BRIDGE_GAS_LIMIT = 100000

ZORA_BRIDGE_ADDRESS = '0x1a0ad011913A150f69f6A19DF447A0CfD9551054'
ZORA_BRIDGE_ABI = json.load(open('abi/zora_bridge.json'))

ZORA_ERC721_ABI = json.load(open('abi/zora_erc721.json'))
ZORA_ERC1155_ABI = json.load(open('abi/zora_erc_1155.json'))
CUSTOM_ERC721_ABI = json.load(open('abi/custom_erc721.json'))

MINTER_ADDRESSES = {
    'Ethereum': '0x8A1DBE9b1CeB1d17f92Bebf10216FCFAb5C3fbA7',
    'Optimism': '0x3678862f04290E565cCA2EF163BAeb92Bb76790C',
    'Zora': '0x169d9147dFc9409AfA4E558dF2C9ABeebc020182',
    'Base': '0xFF8B0f870ff56870Dc5aBd6cB3E6E89c8ba2e062',
}
ZORA_MINTER_ABI = json.load(open('abi/zora_minter.json'))

MINT_REFERRAL_ADDRESSES = {
    'Ethereum': '0xd1d1D4e36117aB794ec5d4c78cBD3a8904E691D0',
    'Optimism': '0x7A810DCd0f8d83B20212326813Db6EF7E9FD030c',
    'Zora': '0xEcfc2ee50409E459c554a2b0376F882Ce916D853',
    'Base': '0x7bf90111Ad7C22bec9E9dFf8A01A44713CC1b1B6',
}

ZORA_NFT_CREATOR_ADDRESS = '0xA2c2A96A232113Dd4993E8b048EEbc3371AE8d85'
ZORA_NFT_CREATOR_ABI = json.load(open('abi/zora_nft_creator.json'))

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
