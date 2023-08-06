from datetime import datetime
from termcolor import cprint
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
import telebot
import requests
import re


private_key_regex = re.compile('(?<!0x)[0-9a-f]{64}')


bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN != '' and TELEGRAM_CHAT_ID != 0 else None


def get_telegram_bot_chat_id():
    resp = requests.get(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates').json()
    if not resp['ok']:
        cprint('Telegram API response not OK: ' + str(resp), 'red')
    elif len(resp['result']) == 0:
        cprint('Can\'t find interaction. Send /start to Bot', 'red')
    elif len(resp['result']) != 1:
        cprint('Security check failed! Bot has more than 1 user. Create a new one', 'red')
    else:
        print('Telegram Bot Chat ID:', resp['result'][0]['message']['chat']['id'])


def replace_private_key(msg):
    return private_key_regex.sub('<PROBABLY-PRIVATE-KEY-HERE>', msg)


class Logger:
    def __init__(self, to_console=True, to_file=True, default_file=None, address=None):
        self.to_console = to_console
        self.to_file = to_file
        self.default_file = default_file
        self.address = address
        self.additional = ''
        self.tg_stored_messages = []

    def set_additional(self, additional):
        self.additional = additional

    def __get_prefix(self):
        prefix = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        if self.address is not None and self.address != '':
            prefix += f' | {self.address}'
        if self.additional is not None and self.additional != '':
            prefix += f' | {self.additional}'
        prefix += ' |'
        return prefix

    def print(self, msg, filename='', to_console=True, send_tg=False, store_tg=True, color=None):
        prefix = self.__get_prefix()
        message = f'{prefix} {msg}'
        if self.to_console and to_console:
            cprint(message, color=color)
        if self.to_file:
            file = filename if filename != '' else self.default_file
            if file != '':
                with open(file, 'a', encoding='utf-8') as f:
                    f.write(f'{message}\n')
        if bot is not None and (send_tg or store_tg):
            self.tg_stored_messages.append(message)
            if send_tg:
                self.send_tg_stored()

    def send_tg(self, msg):
        msg = str(msg)
        if bot is not None:
            msg = replace_private_key(msg)
            start = 0
            while start < len(msg):
                stop = start + 4096
                with_last_newline = stop
                if stop < len(msg):
                    for i in range(min(stop - 1, len(msg) - 1), start - 1, -1):
                        if msg[i] == '\n':
                            with_last_newline = i + 1
                            break
                try:
                    bot.send_message(TELEGRAM_CHAT_ID, msg[start:with_last_newline])
                except Exception:
                    return
                start = with_last_newline

    def send_tg_stored(self):
        if bot is not None:
            self.send_tg('\n'.join(self.tg_stored_messages))
            self.tg_stored_messages = []
