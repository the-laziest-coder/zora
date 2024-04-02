import random
import imaplib
import email
import uuid
import time
import ua_generator

import requests
from email.header import decode_header
from datetime import datetime
from retry import retry
from loguru import logger
from eth_account import Account
from eth_account.messages import encode_defunct
from termcolor import cprint

import config


address2ua = {}


def get_headers(address, additional_headers=None):
    if address not in address2ua:
        address2ua[address] = ua_generator.generate(device='desktop', browser='chrome')
    ua = address2ua[address]
    headers = {
        'accept': 'application/json, text/plain, */*',
        'origin': 'https://zora.co',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'referer': 'https://zora.co/',
        'sec-ch-ua': f'"{ua.ch.brands[2:]}"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': f'"{ua.platform.title()}"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': ua.text,
    }
    if additional_headers is not None:
        headers.update(additional_headers)
    return headers


class Zora:

    PRIVY_APP_ID = 'clpgf04wn04hnkw0fv1m11mnb'
    PRIVY_CLIENT = 'react-auth:1.59.4'

    def __init__(self, idx, private_key, proxy):
        self.idx = idx
        if proxy is not None and len(proxy) > 4 and proxy[:4] != 'http':
            proxy = 'http://' + proxy
        self.proxy = proxy
        self.sess = requests.Session()
        self.sess.proxies = {
            'http': proxy,
            'https': proxy,
        }
        self.private_key = private_key
        self.account = Account().from_key(private_key)
        self.address = self.account.address
        self.cookies = {
            'wallet_address': self.address,
            'device_id': str(uuid.uuid4()),
        }
        self.privy_ca_id = str(uuid.uuid4())
        self.privy_headers = {
            'privy-app-id': self.PRIVY_APP_ID,
            'privy-ca-id': self.privy_ca_id,
            'privy-client': self.PRIVY_CLIENT,
            'accept': 'application/json',
            'sec-fetch-site': 'same-site',
            'referer': 'https://zora.co/',
        }
        self.sess.headers = get_headers(self.address)

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
            self.cookies.update({n: v for n, v in resp.cookies.items()})
            self.sess.headers.update({'authorization': resp.json()['token']})
        except Exception as e:
            raise Exception(f'Sign in bad response: response = {resp.text}: {str(e)}')

    def ensure_authorized(self):
        if self.sess.headers.get('authorization') is None:
            self.sign_in()
            logger.info(f'{self.idx}) Signed in')
            time.sleep(random.uniform(1.5, 3.5))

    def get_existed_email(self):
        self.ensure_authorized()
        url = 'https://zora.co/api/trpc/account.getAccount?batch=1&input=%7B%220%22%3A%7B%22json%22%3Anull%2C%22meta%22%3A%7B%22values%22%3A%5B%22undefined%22%5D%7D%7D%7D'
        resp = self.sess.get(url, cookies=self.cookies)
        if resp.status_code == 404:
            return '', False, True
        if resp.status_code != 200:
            raise Exception(f'Get account info bad status code: {resp.status_code}, response = {resp.text}')
        try:
            res = resp.json()
            res = res[0]['result']['data']['json']
            return res['emailAddress'], res['emailVerified'], False
        except Exception as e:
            raise Exception(f'Get account info bad response: response = {resp.text}: {str(e)}')

    def set_email(self, email_info):
        self.ensure_authorized()
        email_username, _ = tuple(email_info.split(':'))
        existed_email, already_verified, is_new_acc = self.get_existed_email()
        if already_verified and not config.UPDATE_EMAIL_IF_VERIFIED:
            return True, True, is_new_acc
        if existed_email == '':
            logger.info(f'{self.idx}) Setting new email')
            resp = self.sess.post('https://privy.zora.co/api/v1/passwordless/init', json={
                'email': email_username,
            }, headers=self.privy_headers, cookies=self.cookies)
        else:
            logger.info(f"{self.idx}) Email was already set")
            return True, False, is_new_acc
        if resp.status_code != 200:
            raise Exception(f'Set email bad status code: {resp.status_code}, response = {resp.text}')
        try:
            return resp.json()['success'], False, is_new_acc
        except Exception as e:
            raise Exception(f'Set email bad response: response = {resp.text}: {str(e)}')

    def check_folder(self, email_username, imap, folder):
        _, messages = imap.select(folder, readonly=True)
        msg_cnt = int(messages[0])
        for i in range(msg_cnt, 0, -1):
            res, msg = imap.fetch(str(i), '(RFC822)')
            raw_email = msg[0][1]
            msg = email.message_from_bytes(raw_email)
            subject, encoding = decode_header(msg['Subject'])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else 'utf-8')

            if ' is your login code for Zora' not in subject or len(subject) != 34:
                continue

            code = subject.split(' ')[0]

            resp = self.sess.post('https://privy.zora.co/api/v1/passwordless/link', json={
                'code': code,
                'email': email_username,
            }, headers=self.privy_headers, cookies=self.cookies)
            if resp.status_code != 200:
                raise Exception(f'Verify email bad status code: {resp.status_code}, response = {resp.text}')
            return True
        return False

    @retry(tries=5, delay=1)
    def imap_login(self, email_username, email_password):
        imap = imaplib.IMAP4_SSL(config.IMAP_SERVER)
        imap.login(email_username, email_password)
        return imap

    def verify_email(self, email_info):
        self.ensure_authorized()
        email_username, email_password = tuple(email_info.split(':'))
        imap = self.imap_login(email_username, email_password)
        for folder in config.EMAIL_FOLDERS:
            if self.check_folder(email_username, imap, folder):
                return True
        return False

    @retry(tries=config.MAX_TRIES, delay=1.5, backoff=2, jitter=(0, 1))
    def link_email(self, email_info):
        try:
            set_success, verified, is_new_acc = self.set_email(email_info)
            if verified:
                logger.success(f'{self.idx}) Email was already set and verified')
                return True, is_new_acc
            if not set_success:
                raise Exception(f'Can\'t set email')
        except Exception as e:
            raise Exception(f'Failed set email: {str(e)}')

        logger.info(f'{self.idx}) Email was set')

        time.sleep(random.uniform(9, 11))

        try:
            verified = self.verify_email(email_info)
        except Exception as e:
            verified = False
            logger.error(f'{self.idx}) Failed to verify email: {str(e)}')

        t = 0
        while not verified and t < 50:
            logger.warning(f'{self.idx}) Can\'t find verify email. Waiting for 10 secs')
            t += 10
            time.sleep(10)
            try:
                verified = self.verify_email(email_info)
            except Exception as e:
                logger.error(f'{self.idx}) Failed to verify email: {str(e)}')
                break

        if not verified:
            raise Exception(f'Failed to verify email')

        return False, is_new_acc

    @retry(tries=config.MAX_TRIES, delay=1.5, backoff=2, jitter=(0, 1))
    def init_account(self, email_info):
        self.ensure_authorized()

        logger.info(f'{self.idx}) Init new Zora account')

        name = email_info.split(':')[0].split('@')[0]
        url = 'https://zora.co/api/trpc/account.createAccount?batch=1'
        body = {
            0: {
                'json': {
                    'marketingOptIn': True,
                    'profile': {
                        'avatarUri': None,
                        'description': None,
                        'displayName': name.capitalize(),
                    },
                    'referrer': None,
                    'username': name,
                    'walletAddress': self.address,
                },
                'meta': {
                    'values': {
                        'profile.avatarUri': ['undefined'],
                        'profile.description': ['undefined'],
                        'referrer': ['undefined'],
                    }
                },
            }
        }
        resp = self.sess.post(url, json=body, headers={
            'referrer': 'https://zora.co/onboarding',
        }, cookies=self.cookies)
        if resp.status_code != 200:
            raise Exception(f'Failed to create Zora account. Status = {resp.status_code}. Response = {resp.text}')


def main():
    random.seed(int(datetime.now().timestamp()))

    with open('files/wallets.txt', 'r', encoding='utf-8') as file:
        wallets = file.read().splitlines()
    with open('files/proxies.txt', 'r', encoding='utf-8') as file:
        proxies = file.read().splitlines()
    with open('files/emails.txt', 'r', encoding='utf-8') as file:
        emails = file.read().splitlines()

    if len(proxies) == 0:
        proxies = [None] * len(wallets)
    if len(proxies) != len(wallets):
        cprint('Proxies count doesn\'t match wallets count. Add proxies or leave proxies file empty', 'red')
        return
    if len(emails) != len(wallets):
        cprint('Emails count doesn\'t match wallets count', 'red')
        return

    idx = 0

    for wallet, proxy, email_info in zip(wallets, proxies, emails):
        idx += 1

        if idx > 1:
            wait = random.randint(
                int(config.NEXT_ADDRESS_MIN_WAIT_TIME * 60),
                int(config.NEXT_ADDRESS_MAX_WAIT_TIME * 60)
            )
            waiting_msg = 'Waiting for next run for {:.2f} minutes'.format(wait / 60)
            logger.info(waiting_msg)
            time.sleep(wait)

        if wallet.find(';') == -1:
            key = wallet
        else:
            key = wallet.split(';')[1]

        client = Zora(idx, key, proxy)
        logger.info(f'{idx}) Processing {client.address}')

        try:
            already_verified, is_new_acc = client.link_email(email_info)
            if not already_verified:
                logger.success(f'{idx}) Email verified')
        except Exception as e:
            logger.error(f'{idx}) {str(e)}')
            continue

        if not is_new_acc:
            logger.success(f'{idx}) Zora account was already created')
            continue
        try:
            client.init_account(email_info)
            logger.success(f'{idx}) Zora profile created')
        except Exception as e:
            logger.error(f'{idx}) Failed to create Zora profile: {str(e)}')


if __name__ == '__main__':
    cprint('###############################################################', 'cyan')
    cprint('#################', 'cyan', end='')
    cprint(' https://t.me/thelaziestcoder ', 'magenta', end='')
    cprint('################', 'cyan')
    cprint('#################', 'cyan', end='')
    cprint(' https://t.me/thelaziestcoder ', 'magenta', end='')
    cprint('################', 'cyan')
    cprint('#################', 'cyan', end='')
    cprint(' https://t.me/thelaziestcoder ', 'magenta', end='')
    cprint('################', 'cyan')
    cprint('###############################################################\n', 'cyan')

    main()
