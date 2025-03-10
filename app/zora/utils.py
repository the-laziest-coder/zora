import os
import base58
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from eth_account import Account
from eth_account.account import LocalAccount
from mnemonic import Mnemonic


def get_key_hash(b64_key: str) -> str:
    key = base64.b64decode(b64_key)
    if len(key) not in {16, 24, 32}:
        raise ValueError("Invalid key size for AES-GCM")
    aes = algorithms.AES(key)
    digest = hashlib.sha256(aes.key).digest()
    return base64.b64encode(digest).decode('utf-8')


def decrypt_share(b64_enc_data: str, b64_enc_iv: str, b64_key: str) -> bytes:
    key = base64.b64decode(b64_key)
    enc_iv = base64.b64decode(b64_enc_iv)
    enc_data = base64.b64decode(b64_enc_data)
    data = enc_data[:-16]
    tag = enc_data[-16:]
    cipher = Cipher(algorithms.AES(key), modes.GCM(enc_iv, tag), backend=default_backend())
    d = cipher.decryptor()
    decrypted_data = d.update(data) + d.finalize()
    return decrypted_data


def generate_device_id() -> str:
    return base58.b58encode(os.urandom(16)).decode('utf-8')


Account.enable_unaudited_hdwallet_features()
mnemo = Mnemonic("english")


def account_from_entropy(entropy: bytes) -> LocalAccount:
    return Account.from_mnemonic(mnemo.to_mnemonic(entropy))


n = [
    0, 255, 200, 8, 145, 16, 208, 54, 90, 62, 216, 67, 153, 119, 254, 24, 35, 32, 7, 112, 161, 108, 12, 127, 98, 139,
    64, 70, 199, 75, 224, 14,
    235, 22, 232, 173, 207, 205, 57, 83, 106, 39, 53, 147, 212, 78, 72, 195, 43, 121, 84, 40, 9, 120, 15, 33, 144, 135,
    20, 42, 169, 156,
    214, 116, 180, 124, 222, 237, 177, 134, 118, 164, 152, 226, 150, 143, 2, 50, 28, 193, 51, 238, 239, 129, 253, 48,
    92, 19, 157, 41, 23,
    196, 17, 68, 140, 128, 243, 115, 66, 30, 29, 181, 240, 18, 209, 91, 65, 162, 215, 44, 233, 213, 89, 203, 80, 168,
    220, 252, 242, 86,
    114, 166, 101, 47, 159, 155, 61, 186, 125, 194, 69, 130, 167, 87, 182, 163, 122, 117, 79, 174, 63, 55, 109, 71, 97,
    190, 171, 211, 95,
    176, 88, 175, 202, 94, 250, 133, 228, 77, 138, 5, 251, 96, 183, 123, 184, 38, 74, 103, 198, 26, 248, 105, 37, 179,
    219, 189, 102, 221,
    241, 210, 223, 3, 141, 52, 217, 146, 13, 99, 85, 170, 73, 236, 188, 149, 60, 132, 11, 245, 230, 231, 229, 172, 126,
    110, 185, 249, 218,
    142, 154, 201, 36, 225, 10, 21, 107, 58, 160, 81, 244, 234, 178, 151, 158, 93, 34, 136, 148, 206, 25, 1, 113, 76,
    165, 227, 197, 49,
    187, 204, 31, 45, 59, 82, 111, 246, 46, 137, 247, 192, 104, 27, 100, 4, 6, 191, 131, 56
]

a = [
    1, 229, 76, 181, 251, 159, 252, 18, 3, 52, 212, 196, 22, 186, 31, 54, 5, 92, 103, 87, 58, 213, 33, 90, 15, 228, 169,
    249, 78, 100,
    99, 238, 17, 55, 224, 16, 210, 172, 165, 41, 51, 89, 59, 48, 109, 239, 244, 123, 85, 235, 77, 80, 183, 42, 7, 141,
    255, 38, 215,
    240, 194, 126, 9, 140, 26, 106, 98, 11, 93, 130, 27, 143, 46, 190, 166, 29, 231, 157, 45, 138, 114, 217, 241, 39,
    50, 188, 119,
    133, 150, 112, 8, 105, 86, 223, 153, 148, 161, 144, 24, 187, 250, 122, 176, 167, 248, 171, 40, 214, 21, 142, 203,
    242, 19, 230,
    120, 97, 63, 137, 70, 13, 53, 49, 136, 163, 65, 128, 202, 23, 95, 83, 131, 254, 195, 155, 69, 57, 225, 245, 158, 25,
    94, 182,
    207, 75, 56, 4, 185, 43, 226, 193, 74, 221, 72, 12, 208, 125, 61, 88, 222, 124, 216, 20, 107, 135, 71, 232, 121,
    132, 115, 60,
    189, 146, 201, 35, 139, 151, 149, 68, 220, 173, 64, 101, 134, 162, 164, 204, 127, 236, 192, 175, 145, 253, 247, 79,
    129, 47, 91,
    234, 168, 28, 2, 209, 152, 113, 237, 37, 227, 36, 6, 104, 179, 147, 44, 111, 62, 108, 10, 184, 206, 174, 116, 177,
    66, 180, 30,
    211, 73, 233, 156, 200, 198, 199, 34, 110, 219, 32, 191, 67, 81, 82, 102, 178, 118, 96, 218, 197, 243, 246, 170,
    205, 154, 160,
    117, 84, 14, 1
]


def s(e, t):
    r = a[(n[e] + n[t]) % 255]
    return 0 if e == 0 or t == 0 else r


def shamir_split(e: bytes, t: int = 2, r: int = 2) -> list[bytes]:
    nn = []
    aa = len(e)
    h = [tt + 1 for tt in range(255)]
    tt = list(os.urandom(255))
    for rr in range(255):
        i = tt[rr] % 255
        h[rr], h[i] = h[i], h[rr]
    for ee in range(t):
        tt = [0] * (aa + 1)
        tt[aa] = h[ee]
        nn.append(tt)
    c = r - 1
    for rr in range(aa):
        aaa = [0] * (c + 1)
        aaa[0] = e[rr]
        for ee in range(1, c + 1):
            if ee == c:
                while True:
                    eee = os.urandom(1)[0]
                    if eee > 0:
                        aaa[ee] = eee
                        break
            else:
                aaa[ee] = os.urandom(1)[0]
        for ee in range(t):
            if h[ee] == 0:
                tt = aaa[0]
            else:
                tt = aaa[c]
                for nnn in range(c - 1, -1, -1):
                    tt = s(tt, h[ee]) ^ aaa[nnn]
            nn[ee][rr] = tt
    return [bytes(v) for v in nn]



def shamir_combine(e: list[bytes]) -> bytes:
    if not isinstance(e, list):
        raise ValueError("shares must be an Array")
    if not (2 <= len(e) <= 255):
        raise ValueError("shares must have at least 2 and at most 255 elements")
    t = e[0]
    for share in e:
        if not isinstance(share, (bytes, bytearray)):
            raise ValueError("each share must be a Uint8Array")
        if len(share) < 2:
            raise ValueError("each share must be at least 2 bytes")
        if len(share) != len(t):
            raise ValueError("all shares must have the same byte length")
    r = len(e)
    i = len(t)
    h = i - 1
    d = set()
    ll = [0] * r
    for tt in range(r):
        rr = e[tt][i - 1]
        if rr in d:
            raise ValueError("shares must contain unique values but a duplicate was found")
        d.add(rr)
        ll[tt] = rr
    c = [0] * h
    for tt in range(h):
        f = [e[ii][tt] for ii in range(r)]
        if len(ll) != len(f):
            raise ValueError("sample length mistmatch")
        ii, result = len(ll), 0
        for rr in range(ii):
            o = 1
            for ttt in range(ii):
                if rr != ttt:
                    x, y = 0 ^ ll[ttt], ll[rr] ^ ll[ttt]
                    if y == 0:
                        raise ValueError("cannot divide by zero")
                    rrr = a[(n[x] - n[y] + 255) % 255]
                    inter = 0 if x == 0 else rrr
                    o = s(o, inter)
            result = result ^ s(f[rr], o)
        c[tt] = result
    return bytes(c)
