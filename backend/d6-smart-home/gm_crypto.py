#!/usr/bin/env python3
"""
国密双层加密模块 · 纯标准库实现
SM2 (数字签名/密钥协商) + SM3 (哈希) + SM4 (对称加密)

双层加密架构:
  传输层: SM4-CBC 加密整个 HTTP Body (防窃听/防篡改)
  应用层: SM2 签名 + SM3 摘要 (身份认证/防重放/防抵赖)

部署位置: /data/A9/smart_home/gm_crypto.py
运行环境: HarmonyOS ARM32 + Python 3.14 (纯标准库)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
import time
from typing import Optional

# ═══════════════════════════════════════════════════════════════
# SM3 哈希 (优先使用 hashlib 内置, 回退纯 Python)
# ═══════════════════════════════════════════════════════════════

def sm3_hash(data: bytes) -> bytes:
    """SM3 哈希, 返回 32 字节摘要"""
    try:
        h = hashlib.new('sm3')
        h.update(data)
        return h.digest()
    except ValueError:
        # 回退: 纯 Python SM3 实现
        return _sm3_pure(data)


# ═══════════════════════════════════════════════════════════════
# SM4 对称加密 (纯 Python 实现, GB/T 32907-2016)
# ═══════════════════════════════════════════════════════════════

_SM4_SBOX = [
    0xD6,0x90,0xE9,0xFE,0xCC,0xE1,0x3D,0xB7,0x16,0xB6,0x14,0xC2,0x28,0xFB,0x2C,0x05,
    0x2B,0x67,0x9A,0x76,0x2A,0xBE,0x04,0xC3,0xAA,0x44,0x13,0x26,0x49,0x86,0x06,0x99,
    0x9C,0x42,0x50,0xF4,0x91,0xEF,0x98,0x7A,0x33,0x54,0x0B,0x43,0xED,0xCF,0xAC,0x62,
    0xE4,0xB3,0x1C,0xA9,0xC9,0x08,0xE8,0x95,0x80,0xDF,0x94,0xFA,0x75,0x8F,0x3F,0xA6,
    0x47,0x07,0xA7,0xFC,0xF3,0x73,0x17,0xBA,0x83,0x59,0x3C,0x19,0xE6,0x85,0x4F,0xA8,
    0x68,0x6B,0x81,0xB2,0x71,0x64,0xDA,0x8B,0xF8,0xEB,0x0F,0x4B,0x70,0x56,0x9D,0x35,
    0x1E,0x24,0x0E,0x5E,0x63,0x58,0xD1,0xA2,0x25,0x22,0x7C,0x3B,0x01,0x21,0x78,0x87,
    0xD4,0x00,0x46,0x57,0x9F,0xD3,0x27,0x52,0x4C,0x36,0x02,0xE7,0xA0,0xC4,0xC8,0x9E,
    0xEA,0xBF,0x8A,0xD2,0x40,0xC7,0x38,0xB5,0xA3,0xF7,0xF2,0xCE,0xF9,0x61,0x15,0xA1,
    0xE0,0xAE,0x5D,0xA4,0x9B,0x34,0x1A,0x55,0xAD,0x93,0x32,0x30,0xF5,0x8C,0xB1,0xE3,
    0x1D,0xF6,0xE2,0x2E,0x82,0x66,0xCA,0x60,0xC0,0x29,0x23,0xAB,0x0D,0x53,0x4E,0x6F,
    0xD5,0xDB,0x37,0x45,0xDE,0xFD,0x8E,0x2F,0x03,0xFF,0x6A,0x72,0x6D,0x6C,0x5B,0x51,
    0x8D,0x1B,0xAF,0x92,0xBB,0xDD,0xBC,0x7F,0x11,0xD9,0x5C,0x41,0x1F,0x10,0x5A,0x20,
    0xAB,0xBD,0xE6,0x4F,0xBC,0xC5,0x33,0x0B,0xFC,0x6B,0x55,0x23,0x63,0xE8,0x7A,0x45,
    0x8C,0x1D,0x44,0x21,0xC1,0x03,0x12,0xD0,0x9E,0x8F,0x40,0x0A,0xF1,0x35,0x78,0x2D,
    0x66,0xBA,0x18,0x5E,0x93,0x4A,0x87,0xE5,0x1C,0xF9,0x7B,0x58,0x19,0x61,0xA7,0x92,
]

_SM4_CK = [
    0x00070E15,0x1C232A31,0x383F464D,0x545B6269,
    0x70777E85,0x8C939AA1,0xA8AFB6BD,0xC4CBD2D9,
    0xE0E7EEF5,0xFC030A11,0x181F262D,0x343B4249,
    0x50575E65,0x6C737A81,0x888F969D,0xA4ABB2B9,
    0xC0C7CED5,0xDCE3EAF1,0xF8FF060D,0x141B2229,
    0x30373E45,0x4C535A61,0x686F767D,0x848B9299,
    0xA0A7AEB5,0xBCC3CAD1,0xD8DFE6ED,0xF4FB0209,
    0x10171E25,0x2C333A41,0x484F565D,0x646B7279,
]

_SM4_FK = [0xA3B1BAC6, 0x56AA3350, 0x677D9197, 0xB27022DC]


def _rotl32(x: int, n: int) -> int:
    """32位循环左移"""
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _sm4_sbox_lookup(x: int) -> int:
    """S盒替换, 输入32位, 输出32位"""
    return (_SM4_SBOX[(x >> 24) & 0xFF] << 24 |
            _SM4_SBOX[(x >> 16) & 0xFF] << 16 |
            _SM4_SBOX[(x >> 8) & 0xFF] << 8 |
            _SM4_SBOX[x & 0xFF])


def _sm4_l(x: int) -> int:
    """线性变换 L"""
    return x ^ _rotl32(x, 2) ^ _rotl32(x, 10) ^ _rotl32(x, 18) ^ _rotl32(x, 24)


def _sm4_l_prime(x: int) -> int:
    """线性变换 L' (密钥扩展用)"""
    return x ^ _rotl32(x, 13) ^ _rotl32(x, 23)


def _sm4_tau(x: int) -> int:
    """非线性变换 τ = L ∘ S"""
    return _sm4_l(_sm4_sbox_lookup(x))


def _sm4_tau_prime(x: int) -> int:
    """密钥扩展用非线性变换 τ' = L' ∘ S"""
    return _sm4_l_prime(_sm4_sbox_lookup(x))


def _sm4_key_expand(key: bytes) -> list:
    """SM4 密钥扩展, 生成 32 个轮密钥"""
    if len(key) != 16:
        raise ValueError("SM4 key must be 16 bytes")

    mk = struct.unpack('>IIII', key)
    k = [mk[i] ^ _SM4_FK[i] for i in range(4)]
    rk = []

    for i in range(32):
        tmp = k[1] ^ k[2] ^ k[3] ^ _SM4_CK[i]
        tmp = _sm4_tau_prime(tmp)
        tmp = k[0] ^ tmp
        if i == 0:
            rk.append(tmp)
        else:
            rk.append(tmp)
        k = k[1:] + [tmp]

    return rk


def _sm4_encrypt_block(rk: list, block: bytes) -> bytes:
    """SM4 单块加密 (16字节)"""
    x = list(struct.unpack('>IIII', block))

    for i in range(32):
        tmp = x[1] ^ x[2] ^ x[3] ^ rk[i]
        tmp = _sm4_tau(tmp)
        tmp = x[0] ^ tmp
        if i < 31:
            x = x[1:] + [tmp]
        else:
            x = [tmp, x[3], x[2], x[1]]

    return struct.pack('>IIII', x[0], x[1], x[2], x[3])


def _sm4_decrypt_block(rk: list, block: bytes) -> bytes:
    """SM4 单块解密 (轮密钥逆序)"""
    return _sm4_encrypt_block(rk[::-1], block)


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    """PKCS7 填充"""
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    """PKCS7 去填充"""
    if not data:
        raise ValueError("Empty data")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError(f"Invalid padding length: {pad_len}")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("Invalid padding")
    return data[:-pad_len]


def sm4_encrypt(key: bytes, plaintext: bytes, iv: Optional[bytes] = None) -> bytes:
    """
    SM4-CBC 加密

    Args:
        key: 16字节密钥
        plaintext: 明文
        iv: 16字节初始向量, None则随机生成

    Returns:
        iv + ciphertext (iv前缀16字节)
    """
    if len(key) != 16:
        raise ValueError("SM4 key must be 16 bytes")
    if iv is None:
        iv = os.urandom(16)
    if len(iv) != 16:
        raise ValueError("IV must be 16 bytes")

    rk = _sm4_key_expand(key)
    padded = _pkcs7_pad(plaintext)
    ciphertext = b''
    prev = iv

    for i in range(0, len(padded), 16):
        block = padded[i:i+16]
        # CBC: XOR with previous ciphertext block
        xored = bytes(a ^ b for a, b in zip(block, prev))
        encrypted = _sm4_encrypt_block(rk, xored)
        ciphertext += encrypted
        prev = encrypted

    return iv + ciphertext


def sm4_decrypt(key: bytes, ciphertext: bytes) -> bytes:
    """
    SM4-CBC 解密

    Args:
        key: 16字节密钥
        ciphertext: iv + 密文 (前16字节为IV)

    Returns:
        明文
    """
    if len(key) != 16:
        raise ValueError("SM4 key must be 16 bytes")
    if len(ciphertext) < 32:
        raise ValueError("Ciphertext too short (need at least 32 bytes: 16 IV + 16 data)")

    iv = ciphertext[:16]
    data = ciphertext[16:]

    if len(data) % 16 != 0:
        raise ValueError("Ciphertext length (minus IV) must be multiple of 16")

    rk = _sm4_key_expand(key)
    plaintext = b''
    prev = iv

    for i in range(0, len(data), 16):
        block = data[i:i+16]
        decrypted = _sm4_decrypt_block(rk, block)
        # CBC: XOR with previous ciphertext block
        xored = bytes(a ^ b for a, b in zip(decrypted, prev))
        plaintext += xored
        prev = block

    return _pkcs7_unpad(plaintext)


# ═══════════════════════════════════════════════════════════════
# SM2 椭圆曲线数字签名 (纯 Python, GM/T 0003-2012)
# ═══════════════════════════════════════════════════════════════

# SM2 推荐曲线参数 (素数域 Fp)
_SM2_P = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF
_SM2_A = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC
_SM2_B = 0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93
_SM2_N = 0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123
_SM2_GX = 0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7
_SM2_GY = 0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0
_SM2_H = 1  # 辅因子


def _mod_inv(a: int, m: int) -> int:
    """模逆元 (扩展欧几里得算法)"""
    if a < 0:
        a = a % m
    g, x, _ = _extended_gcd(a, m)
    if g != 1:
        raise ValueError("Modular inverse does not exist")
    return x % m


def _extended_gcd(a: int, b: int):
    """扩展欧几里得算法"""
    if a == 0:
        return b, 0, 1
    g, x, y = _extended_gcd(b % a, a)
    return g, y - (b // a) * x, x


def _ec_point_add(p1, p2):
    """椭圆曲线点加法 (雅可比坐标优化版, 这里用仿射坐标)"""
    if p1 is None:
        return p2
    if p2 is None:
        return p1

    x1, y1 = p1
    x2, y2 = p2
    p = _SM2_P

    if x1 == x2:
        if y1 != y2:
            return None  # 点在无穷远
        # 倍点
        lam = (3 * x1 * x1 + _SM2_A) * _mod_inv(2 * y1, p) % p
    else:
        lam = (y2 - y1) * _mod_inv(x2 - x1, p) % p

    x3 = (lam * lam - x1 - x2) % p
    y3 = (lam * (x1 - x3) - y1) % p
    return (x3, y3)


def _ec_point_mul(k: int, point):
    """椭圆曲线标量乘法 (二进制展开法)"""
    if k == 0 or point is None:
        return None
    if k < 0:
        k = -k
        point = (point[0], (-point[1]) % _SM2_P)

    result = None
    addend = point

    while k:
        if k & 1:
            result = _ec_point_add(result, addend)
        addend = _ec_point_add(addend, addend)
        k >>= 1

    return result


class SM2KeyPair:
    """SM2 密钥对"""

    def __init__(self, private_key: Optional[int] = None):
        """生成 SM2 密钥对, 或从私钥恢复"""
        if private_key is not None:
            self.d = private_key % _SM2_N
        else:
            self.d = int.from_bytes(os.urandom(32), 'big') % (_SM2_N - 1) + 1

        G = (_SM2_GX, _SM2_GY)
        self.P = _ec_point_mul(self.d, G)

    @property
    def public_key_bytes(self) -> bytes:
        """未压缩公钥 (04 || X || Y), 65 字节"""
        x = self.P[0].to_bytes(32, 'big')
        y = self.P[1].to_bytes(32, 'big')
        return b'\x04' + x + y

    @property
    def private_key_bytes(self) -> bytes:
        """私钥, 32 字节"""
        return self.d.to_bytes(32, 'big')

    @property
    def public_key_hex(self) -> str:
        return self.public_key_bytes.hex()

    @property
    def private_key_hex(self) -> str:
        return self.private_key_bytes.hex()


def _sm2_z_value(public_key_bytes: bytes, user_id: bytes = b"1234567812345678") -> bytes:
    """计算 SM2 签名的 Z 值 (用户ID哈希)"""
    # ENTL = len(user_id) * 8
    entl = len(user_id) * 8
    z_input = struct.pack('>H', entl) + user_id
    z_input += _SM2_A.to_bytes(32, 'big')
    z_input += _SM2_B.to_bytes(32, 'big')
    z_input += _SM2_GX.to_bytes(32, 'big')
    z_input += _SM2_GY.to_bytes(32, 'big')
    # 公钥: 04 || X || Y
    if public_key_bytes[0] == 0x04:
        z_input += public_key_bytes
    else:
        z_input += b'\x04' + public_key_bytes

    return sm3_hash(z_input)


def sm2_sign(keypair: SM2KeyPair, message: bytes, user_id: bytes = b"1234567812345678") -> bytes:
    """
    SM2 数字签名

    Args:
        keypair: SM2 密钥对
        message: 待签名消息
        user_id: 用户ID (默认 "1234567812345678")

    Returns:
        签名值 r || s, 64 字节
    """
    z = _sm2_z_value(keypair.public_key_bytes, user_id)
    e_hash = sm3_hash(z + message)
    e = int.from_bytes(e_hash, 'big')

    while True:
        k = int.from_bytes(os.urandom(32), 'big') % (_SM2_N - 1) + 1
        G = (_SM2_GX, _SM2_GY)
        x1, y1 = _ec_point_mul(k, G)
        r = (e + x1) % _SM2_N
        if r == 0 or r + k == _SM2_N:
            continue
        s = (_mod_inv(1 + keypair.d, _SM2_N) * (k - r * keypair.d)) % _SM2_N
        if s == 0:
            continue
        break

    return r.to_bytes(32, 'big') + s.to_bytes(32, 'big')


def sm2_verify(public_key_bytes: bytes, message: bytes, signature: bytes,
               user_id: bytes = b"1234567812345678") -> bool:
    """
    SM2 签名验证

    Args:
        public_key_bytes: 未压缩公钥 (04 || X || Y)
        message: 原始消息
        signature: 签名值 r || s, 64 字节
        user_id: 用户ID

    Returns:
        验证是否通过
    """
    if len(signature) != 64:
        return False
    if len(public_key_bytes) != 65 or public_key_bytes[0] != 0x04:
        return False

    r = int.from_bytes(signature[:32], 'big')
    s = int.from_bytes(signature[32:], 'big')

    if r < 1 or r >= _SM2_N or s < 1 or s >= _SM2_N:
        return False

    z = _sm2_z_value(public_key_bytes, user_id)
    e_hash = sm3_hash(z + message)
    e = int.from_bytes(e_hash, 'big')

    t = (r + s) % _SM2_N
    if t == 0:
        return False

    # 解析公钥点
    px = int.from_bytes(public_key_bytes[1:33], 'big')
    py = int.from_bytes(public_key_bytes[33:65], 'big')
    pub_point = (px, py)

    G = (_SM2_GX, _SM2_GY)
    point1 = _ec_point_mul(s, G)
    point2 = _ec_point_mul(t, pub_point)
    point = _ec_point_add(point1, point2)

    if point is None:
        return False

    v = (e + point[0]) % _SM2_N
    return v == r


# ═══════════════════════════════════════════════════════════════
# 双层加密协议封装
# ═══════════════════════════════════════════════════════════════

class SecureEnvelope:
    """
    安全信封: 双层加密协议

    传输层 (外层): SM4-CBC 加密整个 payload
    应用层 (内层): SM2 签名 + SM3 摘要 + 时间戳/nonce 防重放

    信封格式 (JSON):
    {
        "version": 1,
        "timestamp": 1700000000,
        "nonce": "随机16字节hex",
        "sm4_iv": "SM4-CBC IV (hex, 16字节)",
        "payload": "SM4加密后的密文 (hex)",
        "signature": "SM2签名 (hex, 64字节)",
        "signer_pubkey": "SM2签名者公钥 (hex, 65字节)"
    }
    """

    VERSION = 1
    NONCE_SIZE = 16

    def __init__(self, sm4_key: bytes, sm2_keypair: SM2KeyPair):
        """
        Args:
            sm4_key: 16字节 SM4 对称密钥
            sm2_keypair: SM2 密钥对 (用于签名)
        """
        if len(sm4_key) != 16:
            raise ValueError("SM4 key must be 16 bytes")
        self.sm4_key = sm4_key
        self.sm2_keypair = sm2_keypair

    def seal(self, payload: dict) -> dict:
        """
        封装: 双层加密 + 签名

        Args:
            payload: 原始业务数据 (dict)

        Returns:
            安全信封 (dict)
        """
        timestamp = int(time.time())
        nonce = os.urandom(self.NONCE_SIZE).hex()

        # 应用层: 添加时间戳和 nonce
        inner = {
            "timestamp": timestamp,
            "nonce": nonce,
            "data": payload,
        }

        # 序列化内层
        inner_bytes = json.dumps(inner, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

        # 应用层: SM2 签名 (对内层明文签名)
        signature = sm2_sign(self.sm2_keypair, inner_bytes)

        # 传输层: SM4-CBC 加密
        iv_and_ct = sm4_encrypt(self.sm4_key, inner_bytes)
        iv = iv_and_ct[:16]
        ciphertext = iv_and_ct[16:]

        # 组装信封
        envelope = {
            "version": self.VERSION,
            "timestamp": timestamp,
            "nonce": nonce,
            "sm4_iv": iv.hex(),
            "payload": ciphertext.hex(),
            "signature": signature.hex(),
            "signer_pubkey": self.sm2_keypair.public_key_hex,
        }

        return envelope

    def unseal(self, envelope: dict, verify_signature: bool = True,
               max_age_seconds: int = 300, check_nonce: bool = True) -> dict:
        """
        解封: 解密 + 验签

        Args:
            envelope: 安全信封 (dict)
            verify_signature: 是否验证 SM2 签名
            max_age: 最大允许时间偏移 (秒), 0=不检查
            check_nonce: 是否检查 nonce 重放

        Returns:
            解密后的业务数据 (dict)

        Raises:
            ValueError: 验签失败/解密失败/过期/重放
        """
        if envelope.get("version") != self.VERSION:
            raise ValueError(f"Unsupported envelope version: {envelope.get('version')}")

        timestamp = envelope.get("timestamp", 0)
        nonce = envelope.get("nonce", "")

        # 时间检查
        if max_age_seconds > 0:
            now = int(time.time())
            if abs(now - timestamp) > max_age_seconds:
                raise ValueError(f"Envelope expired: age={abs(now - timestamp)}s, max={max_age_seconds}s")

        # Nonce 重放检查
        if check_nonce:
            _nonce_check(nonce)

        # 传输层: SM4-CBC 解密
        iv = bytes.fromhex(envelope["sm4_iv"])
        ciphertext = bytes.fromhex(envelope["payload"])
        inner_bytes = sm4_decrypt(self.sm4_key, iv + ciphertext)

        # 应用层: SM2 签名验证
        if verify_signature:
            signature = bytes.fromhex(envelope["signature"])
            signer_pubkey = bytes.fromhex(envelope["signer_pubkey"])
            if not sm2_verify(signer_pubkey, inner_bytes, signature):
                raise ValueError("SM2 signature verification failed")

        # 解析内层
        inner = json.loads(inner_bytes.decode('utf-8'))

        # 内层时间戳一致性检查
        if inner.get("timestamp") != timestamp:
            raise ValueError("Inner timestamp mismatch")
        if inner.get("nonce") != nonce:
            raise ValueError("Inner nonce mismatch")

        return inner.get("data", {})


# ═══════════════════════════════════════════════════════════════
# Nonce 重放防护
# ═══════════════════════════════════════════════════════════════

_NONCE_CACHE = {}
_NONCE_LOCK = __import__('threading').Lock()
_NONCE_MAX_SIZE = 10000
_NONCE_TTL = 600  # 10分钟


def _nonce_check(nonce: str) -> None:
    """检查 nonce 是否已被使用, 并记录"""
    import threading
    now = time.time()

    with _NONCE_LOCK:
        # 清理过期 nonce
        expired = [k for k, t in _NONCE_CACHE.items() if now - t > _NONCE_TTL]
        for k in expired:
            del _NONCE_CACHE[k]

        if nonce in _NONCE_CACHE:
            raise ValueError(f"Nonce replay detected: {nonce[:16]}...")

        # 容量保护
        if len(_NONCE_CACHE) >= _NONCE_MAX_SIZE:
            # 删除最旧的 10%
            sorted_keys = sorted(_NONCE_CACHE, key=_NONCE_CACHE.get)
            for k in sorted_keys[:_NONCE_MAX_SIZE // 10]:
                del _NONCE_CACHE[k]

        _NONCE_CACHE[nonce] = now


# ═══════════════════════════════════════════════════════════════
# Token 认证
# ═══════════════════════════════════════════════════════════════

def generate_token(user_id: str, secret: bytes, expiry_seconds: int = 86400) -> str:
    """
    生成认证 Token

    Token 格式: base64(json({uid, exp, sig}))
    sig = SM3(uid + exp + secret)
    """
    import base64
    exp = int(time.time()) + expiry_seconds
    sig_input = f"{user_id}:{exp}".encode('utf-8') + secret
    sig = sm3_hash(sig_input).hex()
    token_data = json.dumps({"uid": user_id, "exp": exp, "sig": sig}, separators=(',', ':'))
    return base64.urlsafe_b64encode(token_data.encode('utf-8')).decode('ascii')


def verify_token(token: str, secret: bytes) -> dict:
    """
    验证认证 Token

    Returns:
        {"uid": str, "exp": int}

    Raises:
        ValueError: Token 无效/过期/签名不匹配
    """
    import base64
    try:
        token_data = base64.urlsafe_b64decode(token.encode('ascii')).decode('utf-8')
        payload = json.loads(token_data)
    except Exception:
        raise ValueError("Invalid token format")

    uid = payload.get("uid", "")
    exp = payload.get("exp", 0)
    sig = payload.get("sig", "")

    # 过期检查
    if time.time() > exp:
        raise ValueError("Token expired")

    # 签名验证
    sig_input = f"{uid}:{exp}".encode('utf-8') + secret
    expected_sig = sm3_hash(sig_input).hex()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Token signature mismatch")

    return {"uid": uid, "exp": exp}


# ═══════════════════════════════════════════════════════════════
# 密钥派生 (SM3-HKDF)
# ═══════════════════════════════════════════════════════════════

def sm3_hkdf(ikm: bytes, salt: bytes = b"", info: bytes = b"", length: int = 16) -> bytes:
    """
    SM3-HKDF 密钥派生

    Args:
        ikm: 输入密钥材料
        salt: 盐值
        info: 上下文信息
        length: 输出长度

    Returns:
        派生密钥
    """
    if not salt:
        salt = b'\x00' * 32

    # Extract
    prk = hmac.new(salt, ikm, 'sm3').digest() if 'sm3' in hashlib.algorithms_available else sm3_hash(salt + ikm)

    # Expand
    n = (length + 31) // 32
    okm = b""
    t = b""
    for i in range(1, n + 1):
        t = sm3_hash(prk + t + info + bytes([i]))
        okm += t

    return okm[:length]


# ═══════════════════════════════════════════════════════════════
# 纯 Python SM3 回退实现 (GB/T 32950-2016)
# ═══════════════════════════════════════════════════════════════

def _sm3_pure(message: bytes) -> bytes:
    """纯 Python SM3 实现 (仅在 hashlib 无 sm3 时使用)"""
    # SM3 常量
    T = [0x79CC4519 if i < 16 else 0x7A879D8A for i in range(64)]

    def _ff(x, y, z, j):
        if j < 16: return x ^ y ^ z
        if j < 32: return (x & y) | (x & z) | (y & z)
        return (x & y) | (~x & z) & 0xFFFFFFFF

    def _gg(x, y, z, j):
        if j < 16: return x ^ y ^ z
        if j < 32: return (x & y) | (~x & z)
        return (x & y) | (~x & z)

    def _p0(x): return x ^ _rotl32(x, 9) ^ _rotl32(x, 17)
    def _p1(x): return x ^ _rotl32(x, 15) ^ _rotl32(x, 23)

    # 填充
    msg_len = len(message)
    message += b'\x80'
    while len(message) % 64 != 56:
        message += b'\x00'
    message += struct.pack('>Q', msg_len * 8)

    # 初始值
    V = [0x7380166F, 0x4914B2B9, 0x172442D7, 0xDA8A0600,
         0xA96F30BC, 0x163138AA, 0xE38DEE4D, 0xB0FB0E4E]

    for i in range(0, len(message), 64):
        block = message[i:i+64]
        W = list(struct.unpack('>16I', block))
        for j in range(16, 68):
            W.append(_p1(W[j-16] ^ W[j-9] ^ _rotl32(W[j-3], 15)) ^ _rotl32(W[j-13], 7) ^ W[j-6])
        W1 = [W[j] ^ W[j+4] for j in range(64)]

        A, B, C, D, E, F, G, H = V

        for j in range(64):
            ss1 = _rotl32((_rotl32(A, 12) + E + _rotl32(T[j], j % 32)) & 0xFFFFFFFF, 7)
            ss2 = ss1 ^ _rotl32(A, 12)
            tt1 = (_ff(A, B, C, j) + D + ss2 + W1[j]) & 0xFFFFFFFF
            tt2 = (_gg(E, F, G, j) + H + ss1 + W[j]) & 0xFFFFFFFF
            D = C
            C = _rotl32(B, 9)
            B = A
            A = tt1
            H = G
            G = _rotl32(F, 19)
            F = E
            E = _p0(tt2)

        V = [(V[i] ^ [A, B, C, D, E, F, G, H][i]) & 0xFFFFFFFF for i in range(8)]

    return struct.pack('>8I', *V)


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def generate_sm4_key() -> bytes:
    """生成随机 SM4 密钥 (16字节)"""
    return os.urandom(16)


def generate_sm2_keypair() -> SM2KeyPair:
    """生成 SM2 密钥对"""
    return SM2KeyPair()


def quick_encrypt(key: bytes, data: dict) -> str:
    """快速加密: SM4 加密 JSON 数据, 返回 hex 字符串"""
    plaintext = json.dumps(data, ensure_ascii=False).encode('utf-8')
    ct = sm4_encrypt(key, plaintext)
    return ct.hex()


def quick_decrypt(key: bytes, hex_ciphertext: str) -> dict:
    """快速解密: SM4 解密 hex 字符串, 返回 dict"""
    ct = bytes.fromhex(hex_ciphertext)
    pt = sm4_decrypt(key, ct)
    return json.loads(pt.decode('utf-8'))


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════

def self_test() -> dict:
    """运行加密模块自检"""
    results = {}

    # SM3 测试
    try:
        h = sm3_hash(b"abc")
        expected = "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
        results["sm3"] = h.hex() == expected
    except Exception as e:
        results["sm3"] = f"error: {e}"

    # SM4 测试 (国标测试向量)
    try:
        key = bytes.fromhex("0123456789abcdeffedcba9876543210")
        plaintext = bytes.fromhex("0123456789abcdeffedcba9876543210")
        rk = _sm4_key_expand(key)
        ct = _sm4_encrypt_block(rk, plaintext)
        expected_ct = "681edf34d206965e86b3e94f536e4246"
        results["sm4_block"] = ct.hex() == expected_ct
    except Exception as e:
        results["sm4_block"] = f"error: {e}"

    # SM4-CBC 测试
    try:
        key = os.urandom(16)
        data = {"test": "hello", "num": 42}
        encrypted = quick_encrypt(key, data)
        decrypted = quick_decrypt(key, encrypted)
        results["sm4_cbc"] = decrypted == data
    except Exception as e:
        results["sm4_cbc"] = f"error: {e}"

    # SM2 签名测试
    try:
        kp = SM2KeyPair(private_key=0x3945208416DCFD2E5F9C4A1D6B0E2C5A3B1F4D7E8C6A9B0D3E5F7C2A4B6D8E0F2)
        msg = b"test message for SM2"
        sig = sm2_sign(kp, msg)
        verified = sm2_verify(kp.public_key_bytes, msg, sig)
        results["sm2_sign_verify"] = verified
    except Exception as e:
        results["sm2_sign_verify"] = f"error: {e}"

    # 双层信封测试
    try:
        sm4_key = generate_sm4_key()
        sm2_kp = generate_sm2_keypair()
        envelope = SecureEnvelope(sm4_key, sm2_kp)
        payload = {"action": "toggle", "device_id": "light_01", "is_on": True}
        sealed = envelope.seal(payload)
        unsealed = envelope.unseal(sealed)
        results["envelope"] = unsealed == payload
    except Exception as e:
        results["envelope"] = f"error: {e}"

    # Token 测试
    try:
        secret = os.urandom(32)
        token = generate_token("user001", secret, 3600)
        verified = verify_token(token, secret)
        results["token"] = verified["uid"] == "user001"
    except Exception as e:
        results["token"] = f"error: {e}"

    return results


if __name__ == "__main__":
    import sys
    print("GM Crypto Module Self-Test")
    print("=" * 40)
    results = self_test()
    all_pass = True
    for name, result in results.items():
        status = "PASS" if result is True else "FAIL"
        if result is not True:
            all_pass = False
        print(f"  {name}: {status} {'' if result is True else result}")
    print("=" * 40)
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    sys.exit(0 if all_pass else 1)
