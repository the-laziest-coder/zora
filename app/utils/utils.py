import ssl
import time
import random
import asyncio
import aiofiles
import certifi
from web3 import AsyncWeb3
from faker import Faker
from retry import retry
from loguru import logger
from aiohttp import ClientResponse
from datetime import datetime
from aiohttp_socks import ProxyConnector
from urllib.parse import urlparse, parse_qs

from ..config import MAX_TRIES, DISABLE_SSL

from .async_web3 import AsyncHTTPProviderWithUA


ssl_context = ssl._create_unverified_context() if DISABLE_SSL else ssl.create_default_context(cafile=certifi.where())
if DISABLE_SSL:
    ssl.create_default_context = ssl._create_unverified_context


Faker.seed(int(time.time() * 1000))
faker = Faker()
faker_lock = asyncio.Lock()


async def fake_username():
    async with faker_lock:
        return faker.user_name()


async def fake_filename(extension: str = 'png'):
    async with faker_lock:
        return faker.file_name(extension=extension)


async def fake_name():
    async with faker_lock:
        if random.uniform(0, 100) <= 70:
            nb = 3 if random.uniform(0, 100) <= 15 else random.randint(1, 2)
            return ' '.join(faker.words(nb=nb))
        phrase = faker.catch_phrase()
        nb = 4 if random.uniform(0, 100) <= 10 else random.randint(2, 3)
        return ' '.join(phrase.split()[:nb])


def plural_str(cnt: int, name: str):
    return f'{cnt} {name}{"s" if cnt > 1 else ""}'


def int_to_decimal(i, n=18):
    return i / (10 ** n)


def decimal_to_int(d, n=18):
    return int(d * (10 ** n))


def human_i2d(i, n=18, d=6):
    fmt = f'%.{d}f'
    res = fmt % (int_to_decimal(i, n))
    if '.' in res:
        res = res.rstrip('0')
    if res.endswith('.'):
        res = res[:-1]
    return res


def human_int(x: int) -> int:
    unused = len(str(x)) - random.randint(2, 4)
    if unused < 1:
        return x
    x -= x % (10 ** unused)
    return x


def is_empty(val):
    if val is None:
        return True
    if type(val) == str:
        return val == ''
    return False


def get_proxy_url(proxy):
    if proxy and '|' in proxy:
        proxy = proxy.split('|')[0]
    return None if is_empty(proxy) else proxy


async def wait_a_bit(x=1):
    await asyncio.sleep(random.uniform(0.5, 1) * x)


async def handle_aio_response(resp_raw: ClientResponse, acceptable_statuses=None, resp_handler=None, with_text=False):
    if acceptable_statuses and len(acceptable_statuses) > 0:
        if resp_raw.status not in acceptable_statuses:
            raise Exception(f'Bad status code [{resp_raw.status}]: Response = {await resp_raw.text()}')
    try:
        if resp_handler is not None:
            if with_text:
                return resp_handler(await resp_raw.text())
            else:
                return resp_handler(await resp_raw.json())
        return
    except Exception as e:
        raise Exception(f'{str(e)}: Status = {resp_raw.status}. Response = {await resp_raw.text()}')


def async_retry(async_func):
    async def wrapper(*args, **kwargs):
        tries, delay = MAX_TRIES, 1.5
        while tries > 0:
            try:
                return await async_func(*args, **kwargs)
            except Exception:
                tries -= 1
                if tries <= 0:
                    raise
                await asyncio.sleep(delay)

                delay *= 2
                delay += random.uniform(0, 1)
                delay = min(delay, 10)

    return wrapper


async def log_long_exc(idx, msg, exc, warning=False, to_file=True):
    e_msg = str(exc)
    if e_msg == '':
        e_msg = ' '
    e_msg_lines = e_msg.splitlines()
    if warning:
        logger.warning(f'{idx}) {msg}: {e_msg_lines[0]}')
    else:
        logger.error(f'{idx}) {msg}: {e_msg_lines[0]}')
    if len(e_msg_lines) > 1 and to_file:
        async with aiofiles.open('logs/errors.txt', 'a', encoding='utf-8') as file:
            await file.write(f'{str(datetime.now())} | {idx}) {msg}: {e_msg}\n\n')
            await file.flush()


async def write_to_file(data: str, file_name: str):
    async with aiofiles.open(file_name, 'a', encoding='utf-8') as file:
        await file.write(f'{data}\n')
        await file.flush()


def get_conn(proxy):
    return ProxyConnector.from_url(proxy) if proxy else None


def get_query_param(url: str, name: str):
    values = parse_qs(urlparse(url).query).get(name)
    if values:
        return values[0]
    return None


def to_bytes(hex_str):
    return AsyncWeb3.to_bytes(hexstr=hex_str)


@retry(tries=MAX_TRIES, delay=1.5, max_delay=10, backoff=2, jitter=(0, 1))
def get_w3(rpc_url: str, proxy: str = None):
    proxy = get_proxy_url(proxy)
    req_kwargs = {} if proxy is None else {'proxy': proxy}
    if DISABLE_SSL:
        req_kwargs['ssl'] = False
    return AsyncWeb3(AsyncHTTPProviderWithUA(rpc_url, req_kwargs))
