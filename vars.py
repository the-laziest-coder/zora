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
ZORA_ERC1155_ABI = json.load(open('abi/zora_erc_1155.json'))
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
    'Arbitrum': ['0x7777777F279eba3d3Ad8F4E708545291A6fDBA8B'],
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

ERC_20_ABI = json.load(open('abi/erc20_token.json'))

ERC20_MINTER = '0x777777E8850d8D6d98De2B5f64fae401F96eFF31'
ERC20_MINTER_ABI = json.load(open('abi/erc20_minter.json'))

JSON_EXTENSION_REGISTRY = '0xABCDEFEd93200601e1dFe26D6644758801D732E8'
JSON_EXTENSION_REGISTRY_ABI = json.load(open('abi/json_extension_registry.json'))

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
