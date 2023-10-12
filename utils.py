import requests
from retry import retry
from web3 import Web3
from config import RPCs, ZORA_LOW_GAS, BASE_LOW_GAS, MAX_TRIES
from vars import CHAIN_NAMES, EIP1559_CHAINS


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


@retry(tries=MAX_TRIES, delay=1.5, backoff=2, jitter=(0, 1))
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

    def __init__(self, prefix='', chain=None):
        super().__init__(prefix + 'Insufficient funds on ' + str(chain))
        self.chain = chain


def send_tx(w3, private_key, tx, verify_func, action, tx_change_func=None):
    try:
        estimate = w3.eth.estimate_gas(tx)
        tx['gas'] = int(estimate * 1.2)

        if tx_change_func:
            tx_change_func(tx)

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        verify_func(get_chain(w3), tx_hash, action=action)

        return tx_hash.hex()
    except Exception as e:
        if 'insufficient funds' in str(e) or 'gas required exceeds allowance' in str(e):
            raise InsufficientFundsException(chain=get_chain(w3))
        raise e


def build_and_send_tx(w3, address, private_key, func, value, verify_func, action, tx_change_func=None):
    tx_data = {
        'from': address,
        'nonce': w3.eth.get_transaction_count(address),
        'value': value,
    }

    gas_price = w3.eth.gas_price
    chain = get_chain(w3)

    max_priority_fee, max_fee_per_gas = None, None
    if chain in EIP1559_CHAINS:
        if (chain == 'Zora' and ZORA_LOW_GAS) or (chain == 'Base' and BASE_LOW_GAS):
            max_priority_fee, max_fee_per_gas = 5000000, 5000000
        else:
            max_priority_fee = w3.eth.max_priority_fee
            max_fee_per_gas = max_priority_fee + int(w3.eth.get_block("latest")["baseFeePerGas"] * 1.4)

    if max_priority_fee and max_fee_per_gas:
        tx_data['maxPriorityFeePerGas'] = max_priority_fee
        tx_data['maxFeePerGas'] = max_fee_per_gas
    else:
        tx_data['gasPrice'] = gas_price

    try:
        tx = func.build_transaction(tx_data)
    except Exception as e:
        if 'insufficient funds' in str(e) or 'gas required exceeds allowance' in str(e):
            raise InsufficientFundsException(chain=chain)
        raise e

    return send_tx(w3, private_key, tx, verify_func, action, tx_change_func=tx_change_func)
