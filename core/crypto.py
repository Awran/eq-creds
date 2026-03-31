"""
Cryptographic primitives for EQ-Creds.

Key derivation : Argon2id via argon2-cffi
Encryption     : AES-256-GCM via cryptography (PyCA)

Design notes:
- A fresh 12-byte nonce is generated for every encryption call.
- AAD (Additional Authenticated Data) is bound to each ciphertext so
  ciphertexts cannot be swapped between rows without detection.
- The derived key lives only in memory; this module never writes it to disk.
"""

from __future__ import annotations

import os
from typing import Tuple

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KEY_LEN = 32       # 256-bit AES key
_NONCE_LEN = 12     # 96-bit GCM nonce (NIST recommended)
_SALT_LEN = 16      # Salt for Argon2id
_TAG_LEN = 16       # GCM authentication tag length (implicit in AESGCM)

# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def new_salt() -> bytes:
    """Generate a new random Argon2id salt."""
    return os.urandom(_SALT_LEN)


def derive_key(
    password: str,
    salt: bytes,
    time_cost: int = 3,
    memory_cost: int = 65536,
    parallelism: int = 1,
) -> bytes:
    """
    Derive a 32-byte AES key from the master password using Argon2id.

    Parameters match VaultMeta so callers can pass them through directly.
    Returns raw key bytes — caller is responsible for keeping this in memory
    only and zeroing when done (see vault.py).
    """
    if not password:
        raise ValueError("Master password must not be empty.")
    if len(salt) != _SALT_LEN:
        raise ValueError(f"Salt must be exactly {_SALT_LEN} bytes.")
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=_KEY_LEN,
        type=Type.ID,
    )


# ---------------------------------------------------------------------------
# Field encryption / decryption
# ---------------------------------------------------------------------------


def encrypt_field(key: bytes, plaintext: str, aad: bytes) -> Tuple[bytes, bytes]:
    """
    Encrypt a single string field with AES-256-GCM.

    Returns (ciphertext, nonce).  Both must be stored; nonce is NOT secret.
    AAD (e.g. the account UUID as bytes) is authenticated but not encrypted.
    """
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
    return ciphertext, nonce


def decrypt_field(key: bytes, ciphertext: bytes, nonce: bytes, aad: bytes) -> str:
    """
    Decrypt a single AES-256-GCM ciphertext back to a string.

    Raises cryptography.exceptions.InvalidTag if authentication fails
    (wrong key, wrong AAD, or tampered data).
    """
    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, aad)
    return plaintext_bytes.decode("utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def account_aad(account_id: str) -> bytes:
    """
    Build the AAD bytes for a given account.

    Binding AAD to account_id prevents swapping encrypted username/password
    blobs between different account rows without detection.
    """
    return f"eqcreds:account:{account_id}".encode("utf-8")
