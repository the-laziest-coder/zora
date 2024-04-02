import ccxt
import random

from config import OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE, OKX_WITHDRAW_ETH_AMOUNT


exchange = ccxt.okx({
    'apiKey': OKX_API_KEY,
    'secret': OKX_SECRET_KEY,
    'password': OKX_PASSPHRASE,
    'enableRateLimit': True,
})


CHAIN_NATIVE_MAPPING = {
    'Arbitrum': 'ETH-Arbitrum One',
    'Optimism': 'ETH-Optimism',
    'Base': 'ETH-Base',
}

SIGNIFICANT_DECIMALS = {
    'ETH-Arbitrum One': 4,
    'ETH-Optimism': 4,
    'ETH-Base': 4,
}

OKX_FEES = {
    'Arbitrum': 0.0001,
    'Optimism': 0.00004,
    'Base': 0.00004,
}


def withdraw_native(address, chain):
    token_chain = CHAIN_NATIVE_MAPPING[chain]
    symbol_withdraw, network = token_chain[:token_chain.find('-')], token_chain[token_chain.find('-') + 1:]
    fee = OKX_FEES[chain]

    amounts = OKX_WITHDRAW_ETH_AMOUNT[0], OKX_WITHDRAW_ETH_AMOUNT[1]
    amount_to_withdraw = random.uniform(amounts[0], amounts[1])
    sigs = SIGNIFICANT_DECIMALS[token_chain], SIGNIFICANT_DECIMALS[token_chain] + 2
    amount_to_withdraw = round(amount_to_withdraw, random.randint(sigs[0], sigs[1]))

    exchange.withdraw(symbol_withdraw, amount_to_withdraw, address, params={
        "toAddress": address,
        "chainName": token_chain,
        "dest": 4,
        "fee": fee,
        "pwd": '-',
        "amt": amount_to_withdraw,
        "network": network,
    })

    return amount_to_withdraw
