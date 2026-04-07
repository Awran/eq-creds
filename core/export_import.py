"""
Secure export / import for EQ-Creds.

File format  (.eqcx)
--------------------
Byte layout (all fields concatenated, no padding):

  [4 bytes]  magic        b'EQCX'
  [1 byte]   version      0x01
  [16 bytes] Argon2id salt
  [12 bytes] AES-GCM nonce
  [N bytes]  AES-256-GCM ciphertext (includes 16-byte GCM tag at tail)

AAD for the GCM cipher = magic + version byte (bytes 0-4).
This authenticates the header so tampering the version byte is detected.

The plaintext is UTF-8 encoded JSON:
  {
    "version": 1,
    "exported_at": "<ISO-8601>",
    "accounts": [ { ...Account fields... } ]
  }

Account objects are serialised with plaintext username/password; they are
never written to disk in plaintext — the whole payload is AES-256-GCM
encrypted under a key derived from the caller-supplied export password.

No runtime dependencies beyond those already in requirements.txt.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List

from cryptography.exceptions import InvalidTag

from .crypto import decrypt_field, derive_key, encrypt_field, new_salt
from .errors import WrongPasswordError
from .models import Account, Character

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAGIC = b"EQCX"
_VERSION = 0x01
_HEADER_AAD = _MAGIC + struct.pack("B", _VERSION)   # 5 bytes
_SALT_LEN = 16
_NONCE_LEN = 12
_HEADER_LEN = len(_MAGIC) + 1 + _SALT_LEN + _NONCE_LEN  # 33 bytes

# Argon2id params (same defaults as vault for consistency)
_TIME_COST = 3
_MEMORY_COST = 65536
_PARALLELISM = 1

# Sentinel AAD used for the bundle (not per-account)
_BUNDLE_AAD = b"eqcreds:bundle:v1"


# ---------------------------------------------------------------------------
# Conflict resolution types
# ---------------------------------------------------------------------------

class ConflictResolution(Enum):
    MERGE = "merge"
    SKIP = "skip"


@dataclass
class ConflictRecord:
    imported: Account
    existing: Account
    resolution: ConflictResolution = ConflictResolution.SKIP


@dataclass
class ImportPreview:
    clean: List[Account] = field(default_factory=list)
    conflicts: List[ConflictRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _account_to_dict(account: Account) -> dict:
    return {
        "id": account.id,
        "label": account.label,
        "username": account.username,
        "password": account.password,
        "owner": account.owner,
        "shared_by": account.shared_by,
        "status": account.status,
        "role_flag": account.role_flag,
        "rotate_flag": account.rotate_flag,
        "notes": account.notes,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
        "tags": account.tags,
        "characters": [
            {
                "id": ch.id,
                "account_id": ch.account_id,
                "name": ch.name,
                "char_class": ch.char_class,
                "level": ch.level,
                "notes": ch.notes,
                "created_at": ch.created_at,
            }
            for ch in account.characters
        ],
    }


def _account_from_dict(d: dict) -> Account:
    characters = [
        Character(
            id=ch["id"],
            account_id=ch["account_id"],
            name=ch["name"],
            char_class=ch.get("char_class"),
            level=ch.get("level"),
            notes=ch.get("notes"),
            created_at=ch["created_at"],
        )
        for ch in d.get("characters", [])
    ]
    return Account(
        id=d["id"],
        label=d["label"],
        username=d.get("username"),
        password=d.get("password"),
        owner=d.get("owner"),
        shared_by=d.get("shared_by"),
        status=d.get("status", "active"),
        role_flag=d.get("role_flag"),
        rotate_flag=d.get("rotate_flag"),
        notes=d.get("notes"),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        characters=characters,
        tags=d.get("tags", []),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encode_bundle(accounts: List[Account], export_password: str) -> bytes:
    """
    Encrypt a list of accounts into a portable .eqcx bundle.

    Returns raw bytes ready to write to disk.
    The accounts must have plaintext username/password populated.
    """
    salt = new_salt()
    key = derive_key(export_password, salt, _TIME_COST, _MEMORY_COST, _PARALLELISM)

    payload = json.dumps(
        {
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "accounts": [_account_to_dict(a) for a in accounts],
        },
        ensure_ascii=False,
    ).encode("utf-8")

    ciphertext, nonce = encrypt_field(key, payload.decode("utf-8"), _BUNDLE_AAD)

    return _HEADER_AAD + salt + nonce + ciphertext


def decode_bundle(data: bytes, export_password: str) -> List[Account]:
    """
    Decrypt and deserialise a .eqcx bundle.

    Raises:
      ValueError        — wrong magic bytes or unsupported version
      WrongPasswordError — authentication tag mismatch (wrong password or tampered data)
    """
    if len(data) < _HEADER_LEN:
        raise ValueError("File is too short to be a valid .eqcx bundle.")

    magic = data[:4]
    version = data[4]
    salt = data[5:21]
    nonce = data[21:33]
    ciphertext = data[33:]

    if magic != _MAGIC:
        raise ValueError(f"Not a valid EQ-Creds export file (bad magic: {magic!r}).")
    if version != _VERSION:
        raise ValueError(f"Unsupported .eqcx format version: {version}.")

    key = derive_key(export_password, salt, _TIME_COST, _MEMORY_COST, _PARALLELISM)

    try:
        plaintext = decrypt_field(key, ciphertext, nonce, _BUNDLE_AAD)
    except InvalidTag:
        raise WrongPasswordError("Incorrect export password or file is corrupted.")

    payload = json.loads(plaintext)
    return [_account_from_dict(a) for a in payload.get("accounts", [])]


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def build_import_preview(
    incoming: List[Account],
    existing: List[Account],
) -> ImportPreview:
    """
    Compare incoming accounts against existing ones to find conflicts.

    Conflict anchor:
      - Primary:  case-sensitive username match (when username is non-empty)
      - Fallback: case-insensitive label match  (when username is blank)
    """
    preview = ImportPreview()

    # Build lookup maps from existing accounts
    by_username: dict[str, Account] = {}
    by_label: dict[str, Account] = {}
    for acc in existing:
        if acc.username:
            by_username[acc.username] = acc
        by_label[acc.label.lower()] = acc

    for acc in incoming:
        match: Account | None = None
        if acc.username:
            match = by_username.get(acc.username)
        else:
            match = by_label.get(acc.label.lower())

        if match is not None:
            preview.conflicts.append(ConflictRecord(imported=acc, existing=match))
        else:
            preview.clean.append(acc)

    return preview
