"""Mã hóa secret bằng AES-256-GCM. Khóa chủ lấy từ OMNITEST_MASTER_KEY, không lưu trong DB hay source."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = b"\x01"
_NONCE_LEN = 12


class SecretCipherError(Exception):
    pass


def _decode_key(raw: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(raw.encode() + b"=" * (-len(raw) % 4))
    except Exception as exc:
        raise SecretCipherError("OMNITEST_MASTER_KEY không phải base64 hợp lệ") from exc
    if len(key) != 32:
        raise SecretCipherError("OMNITEST_MASTER_KEY phải là 32 byte (256 bit) mã hóa base64")
    return key


def generate_master_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


class SecretCipher:
    def __init__(self, master_key: str) -> None:
        self._aes = AESGCM(_decode_key(master_key))

    def encrypt(self, plaintext: str, context: str) -> bytes:
        """context (VD id biến) được gắn làm AAD: bản mã chép sang bản ghi khác sẽ không giải mã được."""
        nonce = os.urandom(_NONCE_LEN)
        return _VERSION + nonce + self._aes.encrypt(nonce, plaintext.encode(), context.encode())

    def decrypt(self, blob: bytes, context: str) -> str:
        if not blob or blob[:1] != _VERSION:
            raise SecretCipherError("Định dạng bản mã không hỗ trợ")
        nonce, ct = blob[1 : 1 + _NONCE_LEN], blob[1 + _NONCE_LEN :]
        try:
            return self._aes.decrypt(nonce, ct, context.encode()).decode()
        except Exception as exc:
            raise SecretCipherError("Không giải mã được secret") from exc
