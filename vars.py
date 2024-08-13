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
    'Blast': 'https://blastscan.io',
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
    'Blast': 81457,
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
    81457: 'Blast',
}

EIP1559_CHAINS = ['Ethereum', 'Zora', 'Optimism', 'Base', 'Arbitrum', 'Blast']

NATIVE_TOKEN_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'

NATIVE_DECIMALS = 18

ZORA_BRIDGE_GAS_LIMIT = 100000

ZORA_BRIDGE_ADDRESS = '0x1a0ad011913A150f69f6A19DF447A0CfD9551054'
ZORA_BRIDGE_ABI = json.load(open('abi/zora_bridge.json'))

ZORA_ERC721_ABI = json.load(open('abi/zora_erc721.json'))
ZORA_ERC1155_ABI_OLD = json.load(open('abi/zora_erc_1155_old.json'))
ZORA_ERC1155_ABI_NEW = json.load(open('abi/zora_erc_1155_new.json'))
CUSTOM_ERC721_ABI = json.load(open('abi/custom_erc721.json'))

MINTER_ADDRESSES = {
    '2.7.0': {
        'Base': '0x04E2516A2c207E84a1839755675dfd8eF6302F0a',
    },
    '2.0.0': {
        'Ethereum': '0x04E2516A2c207E84a1839755675dfd8eF6302F0a',
        'Optimism': '0x3678862f04290E565cCA2EF163BAeb92Bb76790C',
        'Zora': '0x04E2516A2c207E84a1839755675dfd8eF6302F0a',
        'Base': '0xFF8B0f870ff56870Dc5aBd6cB3E6E89c8ba2e062',
        'Arbitrum': '0x1Cd1C1f3b8B779B50Db23155F2Cb244FCcA06B21',
    },
    'Other': {
        'Ethereum': '0x8A1DBE9b1CeB1d17f92Bebf10216FCFAb5C3fbA7',
        'Optimism': '0x3678862f04290E565cCA2EF163BAeb92Bb76790C',
        'Zora': '0x169d9147dFc9409AfA4E558dF2C9ABeebc020182',
        'Base': '0xFF8B0f870ff56870Dc5aBd6cB3E6E89c8ba2e062',
    }
}

ZORA_MINTER_ABI = json.load(open('abi/zora_minter.json'))

MINT_REF_ADDRESS = hex(1121563853965062973585180572913477719124829721557)

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
    'arb': 'Arbitrum',
}
ZORA_CHAINS_REVERSE_MAP = {
    'Ethereum': 'eth',
    'Optimism': 'oeth',
    'Zora': 'zora',
    'Base': 'base',
    'Arbitrum': 'arb',
}

ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'

PROTOCOL_REWARDS_ADDRESSES = {
    'Ethereum': [],
    'Zora': [
        '0x7777777F279eba3d3Ad8F4E708545291A6fDBA8B',
        '0x7777777A456fF23D9b6851184472c08FBDa73e32',
    ],
    'Optimism': [],
    'Base': ['0x7777777F279eba3d3Ad8F4E708545291A6fDBA8B'],
    'Arbitrum': ['0x7777777F279eba3d3Ad8F4E708545291A6fDBA8B'],
}
PROTOCOL_REWARDS_ADDRESS_FOR_ZORA_SPLITS = '0x7777777F279eba3d3Ad8F4E708545291A6fDBA8B'
PROTOCOL_REWARDS_ABI = json.load(open('abi/protocol_rewards.json'))

MINTS_CALLER_ADDRESS = '0xb0994EB9520C98C97e1F3953a5964535C2bd271A'
MINTS_CALLER_ABI = json.load(open('abi/mints_caller.json'))

PREPAID_MINTS_ADDRESS = '0x7777777d57c1C6e472fa379b7b3B6c6ba3835073'
PREPAID_MINTS_ABI = json.load(open('abi/prepaid_mints.json'))

PREPAID_ELIGIBLE_VERSIONS = ['2.9.0', '2.10.1', '2.12.3']

PREPAID_MINT_PERMIT_TYPES = {
    "Permit": [
        {
            "name": "owner",
            "type": "address"
        },
        {
            "name": "to",
            "type": "address"
        },
        {
            "name": "tokenIds",
            "type": "uint256[]"
        },
        {
            "name": "quantities",
            "type": "uint256[]"
        },
        {
            "name": "safeTransferData",
            "type": "bytes"
        },
        {
            "name": "nonce",
            "type": "uint256"
        },
        {
            "name": "deadline",
            "type": "uint256"
        }
    ]
}

MINTS_MANAGER_ADDRESS = '0x77777770cA269366c7208aFcF36FE2C6F7f7608B'
MINTS_MANAGER_ABI = json.load(open('abi/mints_manager.json'))

LAST_NFT_CONTRACT_VERSION = '2.12.2'
LAST_NFT_CONTRACT_IMPL_ADDRESS = '0xD860dA58fDcC98ceDF6aA16d7F38b1bfdC8Ca2d9'

LAST_TIMED_SALE_NFT_CONTRACT_VERSION = '2.12.3'

TIMED_SALE_STRATEGY_ADDRESS = '0x777777722D078c97c6ad07d9f36801e653E356Ae'
TIMED_SALE_STRATEGY_ABI = json.load(open('abi/timed_sale_strategy.json'))

SECONDARY_SWAP_ADDRESS = '0x4db6Ae59fb795969086C3F31216a2cd9B82bFa71'
SECONDARY_SWAP_ABI = json.load(open('abi/secondary_swap.json'))

SPLIT_MAIN_ADDRESS = '0x2ed6c4B5dA6378c7897AC67Ba9e43102Feb694EE'
SPLIT_MAIN_ABI = json.load(open('abi/split_main.json'))

MULTICALL3_ADDRESS = '0xcA11bde05977b3631167028862bE2a173976CA11'
MULTICALL3_ABI = json.load(open('abi/multicall3.json'))

ERC_20_ABI = json.load(open('abi/erc20_token.json'))

ERC20_MINTER = '0x777777E8850d8D6d98De2B5f64fae401F96eFF31'
ERC20_MINTER_ABI = json.load(open('abi/erc20_minter.json'))

JSON_EXTENSION_REGISTRY = '0xABCDEFEd93200601e1dFe26D6644758801D732E8'
JSON_EXTENSION_REGISTRY_ABI = json.load(open('abi/json_extension_registry.json'))

PERMIT2_ADDRESS = '0x000000000022D473030F116dDEE9F6B43aC78BA3'
PERMIT2_ABI = json.load(open('abi/permit2.json'))

TOKENS_ROUNDS = {
    '0xa6B280B42CB0b7c4a4F789eC6cCC3a7609A1Bc39': (0, 0),  # ENJOY
    '0x078540eECC8b6d89949c9C7d5e8E91eAb64f6696': (0, 0),  # IMAGINE
    '0xCccCCccc7021b32EBb4e8C08314bD62F7c653EC4': (1, 2),  # USDzC
}

PROFILE_PERSONALIZATION_FORMAT = '''{{
  "theme": {{
    "color": {{
      "background": "#{0}",
      "text": "#{1}",
      "accent": "#{1}",
      "accentText": "#{0}",
      "border": "#{1}"
    }},
    "font": {{
      "heading": {{
        "fontFamily": "{2}",
        "fontSize": "{3}px",
        "lineHeight": "1.1"
      }},
      "body": {{
        "fontFamily": "{4}",
        "fontSize": "{5}px",
        "lineHeight": "1.3"
      }},
      "caption": {{
        "fontFamily": "{4}",
        "fontSize": "{6}px",
        "lineHeight": "1.3"
      }}
    }},
    "button": {{
      "shape": "{7}"
    }},
    "unit": {{
      "radius": "{8}px",
      "base": "6px"
    }}
  }},
  "links": {{
    "twitter": {9},
    "instagram": {10},
    "farcaster": {11},
    "tiktok": {12},
    "discord": {13},
    "website": {14}
  }},
  "options": {{
    "showMetadataHistories": false,
    "useBorders": null,
    "textTransform": {{
      "heading": "{15}",
      "body": "{16}",
      "caption": "{16}"
    }},
    "backgroundImage": {{
      "image": null,
      "title": null,
      "blur": 0,
      "opacity": 1,
      "size": 300,
      "repeat": false,
      "style": "fill"
    }},
    "dropShadow": {{
      "spreadRadius": 0,
      "blurRadius": 0,
      "color": "#000000",
      "opacity": 0
    }},
    "textStyling": {{
      "styleType": "none",
      "horizontalLength": 0,
      "verticalLength": 0,
      "blurRadius": 0,
      "color": "#000000",
      "opacity": 0
    }}
  }},
  "profile": {{
    "displayOptions": {{
      "initialView": null
    }}
  }},
  "template": "Default"
}}'''


PERSONALIZE_FONTS = ['Aboreto', 'Archivo', 'Arimo', 'Freckle Face', 'Gaegu',
                     'IBM Plex Mono', 'Inconsolata', 'Inter', 'Karla',
                     'Libre Baskerville', 'Londrina Solid', 'Michroma',
                     'Nunito', 'Poppins', 'Press Start 2P', 'Rubik',
                     'Silkscreen', 'Source Sans Pro', 'Space Mono', 'Zen Dots']
PERSONALIZE_FONT_SIZES = [(32, 15, 12), (48, 18, 14), (48, 14, 12), (59, 17, 12)]
PERSONALIZE_BUTTON_SHAPES = ['inherit', 'pill', 'square']
PERSONALIZE_BORDER_RADIUSES = [4, 16, 12, 10, 0]
PERSONALIZE_TEXT_TRANSFORMS = ['none', 'uppercase', 'lowercase']


MINT_DURATION_MAP = {
    '1 hour': 3600,
    '4 hours': 3600 * 4,
    '24 hours': 3600 * 24,
    '3 days': 3600 * 24 * 3,
    '1 week': 3600 * 24 * 7,
    '1 month': 3600 * 24 * 30,
    '3 months': 3600 * 24 * 30 * 3,
    '6 months': 3600 * 24 * 30 * 6,
}
