import asyncio
from loguru import logger
from web3 import Web3
from web3.eth.async_eth import TxReceipt
from web3.exceptions import TransactionNotFound
from web3.middleware import async_geth_poa_middleware
from web3.contract.async_contract import AsyncContractConstructor, AsyncContract

from ..models import AccountInfo
from ..utils import async_retry, get_proxy_url, get_w3, wait_a_bit, to_bytes
from ..config import RPCs

from .constants import SCANS, EIP1559_CHAINS


class EVM:

    def __init__(self, account: AccountInfo, chain: str):
        self.idx = account.idx
        self.account = account
        self.private_key = account.evm_private_key
        self.proxy = get_proxy_url(self.account.proxy)
        self.chain = chain
        self.w3 = get_w3(RPCs[chain], self.proxy)

    async def close(self):
        pass

    async def __aenter__(self) -> "EVM":
        return self

    async def __aexit__(self, *args):
        await self.close()

    @async_retry
    async def _send_tx(self, tx):
        if 'chainId' not in tx:
            tx['chainId'] = await self.w3.eth.chain_id
        if 'from' not in tx:
            tx['from'] = self.account.evm_address
        if 'nonce' not in tx:
            tx['nonce'] = await self.w3.eth.get_transaction_count(self.account.evm_address)
        if 'to' not in tx:
            raise Exception('"to" should be specified in raw tx')

        tx['from'] = Web3.to_checksum_address(tx['from'])
        tx['to'] = Web3.to_checksum_address(tx['to'])

        if 'gasLimit' in tx:
            tx['gas'] = tx['gasLimit']
            del tx['gasLimit']
        if type(tx.get('gas')) is str:
            tx['gas'] = int(tx['gas'])

        if self.chain in EIP1559_CHAINS:
            if 'gasPrice' in tx:
                del tx['gasPrice']
            if 'maxPriorityFeePerGas' not in tx or 'maxFeePerGas' not in tx:
                max_priority_fee = await self.w3.eth.max_priority_fee
                max_priority_fee = int(max_priority_fee * 2)
                base_fee_per_gas = int((await self.w3.eth.get_block("latest"))["baseFeePerGas"])
                max_fee_per_gas = max_priority_fee + int(base_fee_per_gas * 2)
                tx.update({
                    'maxPriorityFeePerGas': max_priority_fee,
                    'maxFeePerGas': max_fee_per_gas,
                })
        else:
            if 'gasPrice' not in tx:
                tx['gasPrice'] = await self.w3.eth.gas_price
        if type(tx.get('gasPrice')) is str:
            value = tx['gasPrice']
            tx['gasPrice'] = int(value, 16) if value.startswith('0x') else int(value)
        if type(tx.get('maxPriorityFeePerGas')) is str:
            tx['maxPriorityFeePerGas'] = int(tx['maxPriorityFeePerGas'])
        if type(tx.get('maxFeePerGas')) is str:
            tx['maxFeePerGas'] = int(tx['maxFeePerGas'])

        if type(tx.get('value')) is str:
            value = tx['value']
            tx['value'] = int(value, 16) if value.startswith('0x') else int(value)
        if type(tx.get('data')) is str:
            tx['data'] = to_bytes(tx['data'])

        try:
            estimate = await self.w3.eth.estimate_gas(tx)
            if 'gas' not in tx:
                tx['gas'] = int(estimate * 1.2)
        except Exception as e:
            raise Exception(f'Tx simulation failed: {str(e)}')

        signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        return tx_hash

    @async_retry
    async def _build_and_send_tx(self, func: AsyncContractConstructor, **tx_vars):
        if self.chain in EIP1559_CHAINS:
            max_priority_fee = await self.w3.eth.max_priority_fee
            max_priority_fee = int(max_priority_fee * 2)
            base_fee_per_gas = int((await self.w3.eth.get_block("latest"))["baseFeePerGas"])
            max_fee_per_gas = max_priority_fee + int(base_fee_per_gas * 2)
            gas_vars = {'maxPriorityFeePerGas': max_priority_fee, 'maxFeePerGas': max_fee_per_gas}
        else:
            gas_vars = {'gasPrice': await self.w3.eth.gas_price}
        tx = await func.build_transaction({
            'from': self.account.evm_address,
            'nonce': await self.w3.eth.get_transaction_count(self.account.evm_address),
            'gas': 0,
            **gas_vars,
            **tx_vars,
        })
        del tx['gas']
        if 'no_send' in tx_vars:
            return tx
        try:
            estimate = await self.w3.eth.estimate_gas(tx)
            tx['gas'] = int(estimate * 1.2)
        except Exception as e:
            raise Exception(f'Tx simulation failed: {str(e)}')

        signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        return tx_hash

    async def tx_verification(self, tx_hash, action, poll_latency=1) -> TxReceipt:
        logger.info(f'{self.idx}) {action} - Tx sent. Waiting for 120s')
        time_passed = 0
        tx_link = f'{SCANS.get(self.chain, "")}/tx/{tx_hash if type(tx_hash) is str else tx_hash.hex()}'
        while time_passed < 120:
            try:
                tx_data = await self.w3.eth.get_transaction_receipt(tx_hash)
                if tx_data is not None:
                    if tx_data.get('status') == 1:
                        logger.success(f'{self.idx}) {action} - Successful tx: {tx_link}')
                        return tx_data
                    msg = f'Failed tx: {tx_link}'
                    logger.error(f'{self.idx}) {msg}')
                    raise Exception(msg)
            except TransactionNotFound:
                pass

            time_passed += poll_latency
            await asyncio.sleep(poll_latency)

        msg = f'{action} - Pending tx: {tx_link}'
        logger.warning(f'{self.idx}) {msg}')
        raise Exception(msg)

    async def _default_send_wrapper(self, send_func, *args, action='', **kwargs) -> str | dict:
        try:
            tx_or_hash = await send_func(*args, **kwargs)
        except Exception as e:
            try:
                if 'you are connected to a POA chain' in str(e):
                    self.w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)
                    tx_or_hash = await send_func(*args, **kwargs)
                else:
                    raise e
            except Exception as inner_exc:
                raise Exception(f'{action} failed: {inner_exc}')
        if type(tx_or_hash) is dict:
            return tx_or_hash
        await self.tx_verification(tx_or_hash, action)
        return tx_or_hash.hex()

    async def build_and_send_tx(self, func: AsyncContractConstructor, action='', **tx_vars) -> str | dict:
        return await self._default_send_wrapper(self._build_and_send_tx, func, action=action, **tx_vars)

    async def send_tx(self, tx: dict, action='') -> str:
        return await self._default_send_wrapper(self._send_tx, tx, action=action)

    async def balance(self) -> int:
        return await self.w3.eth.get_balance(self.account.evm_address)

    # signatures with tuples are not supported
    @classmethod
    def generate_simple_abi(cls, *func_signs, payable=True, erc20=False):
        abi = []
        for func_sign in func_signs:
            func_name = func_sign.split('(')[0]
            args = func_sign[func_sign.find('(') + 1:func_sign.find(')')]
            rets = func_sign[func_sign.find(')') + 1:]
            arg_types = [arg.strip() for arg in args.split(',')] if args else []
            ret_types = [ret.strip() for ret in rets.split(',')] if rets else []
            abi.append({
                "name": func_name,
                "type": "function",
                "inputs": [{"name": "", "type": arg} for arg in arg_types],
                "outputs": [{"name": "", "type": ret} for ret in ret_types],
                "stateMutability": "payable" if payable else "nonpayable",
            })
        if erc20:
            abi.append({
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"},
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            })
            abi.append({
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            })
            abi.append({
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            })
            abi.append({
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "symbol", "type": "string"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            })
            abi.append({
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "decimals", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            })
        return abi

    def contract(self, address, *func_signs, payable=True, erc20=False, abi=None) -> AsyncContract:
        abi = abi or self.generate_simple_abi(*func_signs, payable=payable, erc20=erc20)
        return self.w3.eth.contract(Web3.to_checksum_address(address), abi=abi)

    @async_retry
    async def token_balance(self, token_address, owner: str = None) -> int:
        contract = self.contract(Web3.to_checksum_address(token_address), erc20=True)
        owner = owner or self.account.evm_address
        owner = Web3.to_checksum_address(owner)
        return await contract.functions.balanceOf(owner).call()

    # contract should have `approve` and `allowance` functions
    @async_retry
    async def approve(
            self,
            contract: AsyncContract,
            spender: str,
            amount: int,
            name='',
            light=False,
            infinite=False,
            **tx_vars,
    ) -> int:
        spender = Web3.to_checksum_address(spender)
        allowance = await contract.functions.allowance(self.account.evm_address, spender).call()
        if light and allowance > 0:
            return min(amount, allowance)
        if allowance >= amount:
            return amount
        if infinite:
            amount = 2 ** 256 - 1
        await self.build_and_send_tx(contract.functions.approve(spender, amount), 'Approve ' + name, **tx_vars)
        await wait_a_bit(3)
        return amount
