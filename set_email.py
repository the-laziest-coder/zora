import random
import imaplib
import email
import time

import requests
from email.header import decode_header
import config
from datetime import datetime
from loguru import logger
from eth_account import Account
from eth_account.messages import encode_defunct
from termcolor import cprint


class Zora:

    def __init__(self, private_key, proxy):
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
        self.cookies = {'wallet_address': self.address}

    def set_wallet_cookie(self, resp):
        wallet_cookie = resp.headers.get('set-cookie')
        wallet_cookie = wallet_cookie[wallet_cookie.find('=') + 1:wallet_cookie.find(';')]
        self.cookies.update({'wallet': wallet_cookie})

    def get_nonce(self):
        resp = self.sess.get('https://zora.co/api/auth/nonce', cookies=self.cookies)
        if resp.status_code != 200:
            raise Exception(f'Get nonce bas status code: {resp.status_code}, response = {resp.text}')
        try:
            nonce = resp.json()['nonce']
            self.set_wallet_cookie(resp)
            return nonce
        except Exception as e:
            raise Exception(f'Get nonce bad response: response = {resp.text}: {str(e)}')

    def sign_in(self):
        issued_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + 'Z'

        nonce = self.get_nonce()

        time.sleep(random.uniform(0.5, 1.5))

        statement = f'Welcome to Zora!\n\n' \
                    f'By proceeding, you accept Zora’s Terms of Service ' \
                    f'(https://support.zora.co/en/articles/6383293-terms-of-service) ' \
                    f'and Privacy Policy (https://support.zora.co/en/articles/6383373-zora-privacy-policy)'

        msg = f'zora.co wants you to sign in with your Ethereum account:\n' \
              f'{self.address}\n\n' \
              f'{statement}\n\n' \
              f'URI: https://zora.co\n' \
              f'Version: 1\n' \
              f'Chain ID: 1\n' \
              f'Nonce: {nonce}\n' \
              f'Issued At: {issued_at}'
        message = encode_defunct(text=msg)
        signature = self.account.sign_message(message).signature.hex()

        resp = self.sess.post('https://zora.co/api/auth/login', json={
            'message': {
                'address': self.address,
                'chainId': 1,
                'domain': 'zora.co',
                'issuedAt': issued_at,
                'nonce': nonce,
                'statement': statement,
                'uri': 'https://zora.co',
                'version': '1',
            },
            'signature': signature,
        }, cookies=self.cookies)
        if resp.status_code != 200:
            raise Exception(f'Sign in bas status code: {resp.status_code}, response = {resp.text}')
        try:
            self.set_wallet_cookie(resp)
            return resp.json()['ok']
        except Exception as e:
            raise Exception(f'Get nonce bad response: response = {resp.text}: {str(e)}')

    def ensure_authorized(self):
        if self.cookies.get('wallet') is None:
            self.sign_in()
            logger.info('Signed in')
            time.sleep(random.uniform(1.5, 3.5))

    def get_existed_email(self):
        self.ensure_authorized()
        resp = self.sess.get('https://zora.co/api/account', cookies=self.cookies)
        if resp.status_code == 404:
            return '', False
        if resp.status_code != 200:
            raise Exception(f'Get account info bas status code: {resp.status_code}, response = {resp.text}')
        try:
            if 'account' not in resp.json():
                return '', False
            return resp.json()['account']['emailAddress'], resp.json()['account']['emailVerified']
        except Exception as e:
            raise Exception(f'Get account info bad response: response = {resp.text}: {str(e)}')

    def set_email(self, email_info):
        self.ensure_authorized()
        email_username, _ = tuple(email_info.split(':'))
        existed_email, already_verified = self.get_existed_email()
        if already_verified and not config.UPDATE_EMAIL_IF_VERIFIED:
            return True, True
        if existed_email == '':
            logger.info('Setting new email')
            resp = self.sess.post('https://zora.co/api/account/new', json={
                'emailAddress': email_username,
                'marketingOptIn': True,
            }, cookies=self.cookies)
        elif existed_email != email_username:
            logger.info('Updating existed email')
            resp = self.sess.post('https://zora.co/api/account/update-email', json={
                'emailAddress': email_username,
            }, cookies=self.cookies)
        else:
            logger.info("This email was already set")
            return True, False
        if resp.status_code != 200:
            raise Exception(f'Set email bad status code: {resp.status_code}, response = {resp.text}')
        try:
            return resp.json()['ok'], False
        except Exception as e:
            raise Exception(f'Set email bad response: response = {resp.text}: {str(e)}')

    def check_folder(self, imap, folder):
        _, messages = imap.select(folder, readonly=True)
        msg_cnt = int(messages[0])
        for i in range(msg_cnt, 0, -1):
            res, msg = imap.fetch(str(i), '(RFC822)')
            raw_email = msg[0][1]
            msg = email.message_from_bytes(raw_email)
            subject, encoding = decode_header(msg['Subject'])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding)
            if subject != 'Verify your Zora account':
                continue
            body = msg.get_payload(decode=True).decode()
            pre_link_message = 'Please activate your account'
            if pre_link_message not in body:
                pre_link_message = 'Please verify your email'
                if pre_link_message not in body:
                    raise Exception(f'Can\'t find verification token in e-mail: body = {body}')
            body = body[body.find(pre_link_message):]
            body = body[body.find('href') + 6:]
            link = body[:body.find('"')]
            token = link[link.rfind('=') + 1:]

            resp = self.sess.post('https://zora.co/api/account/email-verify', json={'token': token},
                                  cookies=self.cookies)
            if resp.status_code != 200:
                raise Exception(f'Verify email bas status code: {resp.status_code}, response = {resp.text}')
            try:
                return resp.json()['ok']
            except Exception as e:
                raise Exception(f'Verify email bad response: response = {resp.text}: {str(e)}')

    def verify_email(self, email_info):
        self.ensure_authorized()
        email_username, email_password = tuple(email_info.split(':'))
        imap = imaplib.IMAP4_SSL(config.IMAP_SERVER)
        imap.login(email_username, email_password)
        for folder in config.EMAIL_FOLDERS:
            if self.check_folder(imap, folder):
                return True
        return False


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

        client = Zora(key, proxy)

        logger.info(f'{idx}) Processing {client.address}')

        try:
            set_success, verified = client.set_email(email_info)
            if verified and not config.UPDATE_EMAIL_IF_VERIFIED:
                logger.success(f'{idx}) Email was already set and verified')
                continue
            if not set_success:
                logger.error(f'{idx}) Can\'t set email')
                continue
        except Exception as e:
            logger.error(f'{idx}) Failed set email: {str(e)}')
            continue

        logger.info(f'{idx}) Email was set')

        time.sleep(random.uniform(9, 11))

        try:
            verified = client.verify_email(email_info)
        except Exception as e:
            verified = False
            logger.error(f'{idx}) Failed to verify email: {str(e)}')
        t = 0
        while not verified and t < 120:
            logger.error(f'{idx}) Can\'t find verify email. Waiting for 10 secs')
            t += 10
            time.sleep(t)
            try:
                verified = client.verify_email(email_info)
            except Exception as e:
                logger.error(f'{idx}) Failed to verify email: {str(e)}')
                break
        if verified:
            logger.success(f'{idx}) Email verified')


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
