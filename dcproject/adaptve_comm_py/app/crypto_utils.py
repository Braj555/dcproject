# app/crypto_utils.py
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import os

def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32, salt=salt, iterations=100_000, backend=default_backend()
    )
    return kdf.derive(password.encode("utf-8"))

def encrypt_bytes(plain: bytes, password: str):
    salt = os.urandom(16)
    key = derive_key(password, salt)
    iv = os.urandom(12)
    aes = AESGCM(key)
    ct = aes.encrypt(iv, plain, None)
    return iv, salt, ct

def decrypt_bytes(cipher: bytes, password: str, iv: bytes, salt: bytes):
    try:
        key = derive_key(password, salt)
        aes = AESGCM(key)
        pt = aes.decrypt(iv, cipher, None)
        return pt
    except Exception:
        return None
