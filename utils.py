import requests
from web3 import Web3
from config import RPCs
from vars import CHAIN_NAMES, EIP1559_CHAINS, ZORA_GWEI


def get_coin_price(coin, currency):
    resp = requests.get(
        f'https://api.coingecko.com/api/v3/coins/{coin}?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false')
    return float(resp.json()['market_data']['current_price'][currency])


class Web3WithChain(Web3):

    current_chain_id: int

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_chain_id = self.eth.chain_id
        self.current_chain_id = current_chain_id


def get_w3(chain, proxy=None):
    req_args = {} if proxy is None or proxy == '' else {
        'proxies': {'https': proxy, 'http': proxy},
    }
    return Web3WithChain(Web3.HTTPProvider(RPCs[chain], request_kwargs=req_args))


def get_chain(w3):
    return CHAIN_NAMES[w3.current_chain_id]


def to_bytes(hex_str):
    return Web3.to_bytes(hexstr=hex_str)


class InsufficientFundsException(Exception):
    pass


def send_tx(w3, private_key, tx, verify_func, action):
    try:
        estimate = w3.eth.estimate_gas(tx)
        tx['gas'] = int(estimate * 1.2)

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        verify_func(get_chain(w3), tx_hash, action=action)

        return tx_hash
    except Exception as e:
        if 'insufficient funds' in str(e):
            raise InsufficientFundsException()
        raise e


def build_and_send_tx(w3, address, private_key, func, value, verify_func, action):
    tx_data = {
        'from': address,
        'nonce': w3.eth.get_transaction_count(address),
        'value': value,
    }

    gas_price = w3.eth.gas_price
    chain = get_chain(w3)

    if chain in EIP1559_CHAINS:
        if chain == 'Zora':
            gas_price = Web3.to_wei(ZORA_GWEI, 'gwei')
            tx_data['maxPriorityFeePerGas'] = gas_price
            tx_data['maxFeePerGas'] = gas_price + int(w3.eth.get_block("latest")["baseFeePerGas"] * 1.2)
    else:
        tx_data['gasPrice'] = gas_price

    try:
        tx = func.build_transaction(tx_data)
    except Exception as e:
        if 'insufficient funds' in str(e):
            raise InsufficientFundsException()
        raise e

    return send_tx(w3, private_key, tx, verify_func, action)
