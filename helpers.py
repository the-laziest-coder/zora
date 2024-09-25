import random
import colorama
from pathlib import Path
from datetime import datetime
from web3 import Web3
from logger import Logger
from config import MINT_ONLY_CUSTOM, MINT_WITH_COMMENT, COMMENT_PROBABILITY, COMMENT_WORDS, COMMENT_MAX_NUMBER_OF_WORDS
from vars import ZORA_CHAINS_MAP, ZORA_CHAINS_REVERSE_MAP


colorama.init()

date_path = datetime.now().strftime('%d-%m-%Y-%H-%M-%S')
results_path = 'results/' + date_path
logs_root = 'logs/'
logs_path = logs_root + date_path
Path(results_path).mkdir(parents=True, exist_ok=True)
Path(logs_path).mkdir(parents=True, exist_ok=True)

logger = Logger(to_console=True, to_file=True, default_file=f'{logs_path}/console_output.txt')


common_1_or_2_letters = ['a', 'i', 'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in', 'is',
                         'it', 'me', 'my', 'no', 'of', 'ok', 'on', 'or', 'so', 'to', 'up', 'us', 'we']
with open('files/english_words.txt', 'r', encoding='utf-8') as words_file:
    english_words = words_file.read().splitlines()
    english_words = [ew.strip() for ew in english_words]
    english_words = [ew for ew in english_words if len(ew) > 2 or ew in common_1_or_2_letters]


def _parse_mint_link_without_cnt(link):
    link = link.strip()
    if link == '' or link[0] == '#':
        return None
    if link.startswith('custom'):
        chain = link.split(':')[1]
        token_id = 'custom'
        nft_info = link[7 + len(chain) + 1:]
        chain = ZORA_CHAINS_MAP[chain]
        return chain, nft_info, token_id
    if MINT_ONLY_CUSTOM:
        return None
    if link.startswith('https://'):
        link = link[8:]
    if link.startswith('zora.co/collect/'):
        link = link[16:]
    chain, nft_info = tuple(link.split(':'))
    if '/' in nft_info:
        nft_address, token_id = tuple(nft_info.split('/'))
    else:
        return None
    chain = ZORA_CHAINS_MAP[chain]
    nft_address = Web3.to_checksum_address(nft_address)
    token_id = int(token_id) if token_id else None
    return chain, nft_address, token_id


def parse_mint_link(link):
    if link is None:
        return None
    link = link.strip()
    if link == '' or link[0] == '#':
        return None
    if '|' in link:
        cnt = link.split('|')[1]
        if '-' in cnt:
            cnt = (int(cnt.split('-')[0]), int(cnt.split('-')[1]))
        else:
            cnt = (int(cnt), int(cnt))
        link = link.split('|')[0]
    else:
        cnt = None
    parsed = _parse_mint_link_without_cnt(link)
    if parsed is None:
        return None
    return parsed if cnt is None else (parsed, cnt)


def construct_mint_link(chain, address, token_id=None):
    created_link = f'https://zora.co/collect/'
    created_link += ZORA_CHAINS_REVERSE_MAP[chain] + ':'
    created_link += address.lower()
    if token_id is not None:
        created_link += '/' + str(token_id)
    return created_link


def get_random_words(n: int):
    words = [random.choice(english_words) for _ in range(n)]
    return ['I' if w == 'i' else w for w in words]


def generate_comment():
    if not MINT_WITH_COMMENT or random.randint(1, 100) > COMMENT_PROBABILITY:
        logger.print('[No comment]')
        return ''
    words = []
    for w in random.sample(COMMENT_WORDS, random.randint(1, min(COMMENT_MAX_NUMBER_OF_WORDS, 3))):
        word = w
        rnd = random.randint(1, 3)
        if rnd == 1:
            word = word.capitalize()
        elif rnd == 2:
            if random.randint(1, 3) == 1:
                word = word.upper()
        else:
            word = word.lower()
        words.append(word)
    comment = ' '.join(words)
    if random.randint(1, 5) <= 1:
        comment += '!'
        if random.randint(1, 4) == 1:
            comment += '!!'
    logger.print('Comment: ' + comment)
    return comment
