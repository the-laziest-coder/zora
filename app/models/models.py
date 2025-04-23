from typing import Tuple, Optional
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from eth_account import Account as EvmAccount
from eth_account.messages import encode_defunct

from ..utils import plural_str


STATUS_BY_BOOL = {
    False: '❌',
    True: '✅',
}


@dataclass_json
@dataclass
class AccountInfo:
    idx: int = 0
    evm_address: str = ''
    evm_private_key: str = ''
    proxy: str = ''
    twitter_auth_token: str = ''
    twitter_ct0: str = ''
    email_username: str = ''
    email_password: str = ''
    withdraw_address: str = ''
    twitter_error: bool = False
    device_id: str = ''
    privy_ca_id: str = ''
    b58_device_id: str = ''
    embedded_pk: str = ''
    buys: int = 0
    sells: int = 0
    creates: int = 0
    volume: float = 0
    total_buys_amount: float = 0
    total_sells_amount: float = 0
    portfolio: float = 0
    profile_completed: bool = False
    airdrop: float = 0
    claimed: float = 0
    zora_balance: float = 0

    def sign_message(self, msg) -> str:
        return EvmAccount().sign_message(encode_defunct(text=msg), self.evm_private_key).signature.hex()

    def str_stats(self) -> str:
        return (f'\tIdx: {self.idx}\n'
                f'\tProfile completed: {self.profile_completed}\n'
                f'\tBuys: {self.buys}\n'
                f'\tSells: {self.sells}\n'
                f'\tCreates: {self.creates}\n'
                f'\tVolume: {round(self.volume, 4)} ETH\n'
                f'\tPNL: {round(self.pnl, 4)} ETH\n'
                f'\tPortfolio: {round(self.portfolio, 4)} ETH\n'
                f'\tAirdrop: {round(self.airdrop)} $ZORA\n'
                f'\tClaimed: {round(self.claimed)} $ZORA\n'
                f'\t$ZORA balance on main wallet: {round(self.zora_balance)}\n')

    @property
    def twitter_error_s(self):
        return '🔴' if self.twitter_error else ''

    @property
    def pnl(self) -> float:
        return self.total_sells_amount - self.total_buys_amount
