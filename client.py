import time
import uuid
import copy
import random
from datetime import datetime
from tls_client import Session
from eth_account import Account
from eth_account.messages import encode_defunct
from helpers import logger


DEFAULT_HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'origin': 'https://zora.co',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'referer': 'https://zora.co/',
    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

saved_auth_details = {}


class Client:

    PRIVY_APP_ID = 'clpgf04wn04hnkw0fv1m11mnb'
    PRIVY_CLIENT = 'react-auth:1.75.0-beta-20240715213704'

    def __init__(self, private_key, proxy):
        if proxy is not None and len(proxy) > 4 and proxy[:4] != 'http':
            proxy = 'http://' + proxy
        self.proxy = proxy
        self.sess = Session()
        self.sess.proxies = {
            'http': proxy,
            'https': proxy,
        }
        self.private_key = private_key
        self.account = Account().from_key(private_key)
        self.address = self.account.address
        auth_details = copy.deepcopy(saved_auth_details.get(self.address))
        if auth_details is None:
            auth_details = (0, {'device_id': str(uuid.uuid4()), 'wallet_address': self.address},
                            str(uuid.uuid4()), None)
        if auth_details[0] + 3600 < int(time.time()):
            auth_details = (auth_details[0],
                            {'device_id': auth_details[1]['device_id'], 'wallet_address': self.address},
                            auth_details[2], None)
        else:
            logger.print(f'Restored logging info [Signed in '
                         f'{"%.1f" % ((int(time.time()) - auth_details[0]) / 60)} mins ago]')
        saved_auth_details[self.address] = copy.deepcopy(auth_details)
        self.cookies = copy.deepcopy(auth_details[1])
        self.privy_ca_id = auth_details[2]
        self.privy_headers = {
            'privy-app-id': self.PRIVY_APP_ID,
            'privy-ca-id': self.privy_ca_id,
            'privy-client': self.PRIVY_CLIENT,
            'accept': 'application/json',
            'sec-fetch-site': 'same-site',
            'referer': 'https://zora.co/',
        }
        self.sess.headers = copy.deepcopy(DEFAULT_HEADERS)
        if auth_details[3] is not None:
            self.sess.headers.update({'authorization': auth_details[3]})

    def get_nonce(self):
        resp = self.sess.post('https://privy.zora.co/api/v1/siwe/init', json={
            'address': self.address,
        }, headers=self.privy_headers, cookies=self.cookies)
        if resp.status_code != 200:
            raise Exception(f'Get nonce bad status code: {resp.status_code}, response = {resp.text}')
        try:
            nonce = resp.json()['nonce']
            return nonce
        except Exception as e:
            raise Exception(f'Get nonce bad response: response = {resp.text}: {str(e)}')

    def sign_in(self):
        nonce = self.get_nonce()
        issued_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + 'Z'

        time.sleep(random.uniform(0.5, 1.5))

        msg = f'zora.co wants you to sign in with your Ethereum account:\n' \
              f'{self.address}\n\n' \
              f'By signing, you are proving you own this wallet and logging in. ' \
              f'This does not initiate a transaction or cost any fees.\n\n' \
              f'URI: https://zora.co\n' \
              f'Version: 1\n' \
              f'Chain ID: 1\n' \
              f'Nonce: {nonce}\n' \
              f'Issued At: {issued_at}\n' \
              f'Resources:\n' \
              f'- https://privy.io'
        message = encode_defunct(text=msg)
        signature = self.account.sign_message(message).signature.hex()

        resp = self.sess.post('https://privy.zora.co/api/v1/siwe/authenticate', json={
            'chainId': 'eip155:1',
            'connectorType': 'injected',
            'message': msg,
            'signature': signature,
            'walletClientType': 'metamask',
        }, headers=self.privy_headers, cookies=self.cookies)
        if resp.status_code != 200:
            raise Exception(f'Sign in bad status code: {resp.status_code}, response = {resp.text}')
        try:
            token = resp.json()['token']
            self.cookies.update({n: v for n, v in resp.cookies.items()})
            self.sess.headers.update({'authorization': token})
            auth_details = copy.deepcopy(saved_auth_details.get(self.address))
            auth_details = (int(time.time()), copy.deepcopy(self.cookies), auth_details[2], token)
            saved_auth_details[self.address] = copy.deepcopy(auth_details)
        except Exception as e:
            raise Exception(f'Sign in bad response: response = {resp.text}: {str(e)}')

    def ensure_authorized(self):
        if self.sess.headers.get('authorization') is None:
            self.sign_in()
            logger.print('Logged in')
            time.sleep(random.uniform(1.5, 3.5))
