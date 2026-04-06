"""
Vault session manager for EQ-Creds.

Responsibilities:
- Initialize a new vault (first launch)
- Unlock an existing vault (verify password, derive key)
- Hold the session key in memory only
- Provide encrypt/decrypt helpers for the rest of the app
- Lock (zero and discard the key)
- Re-key (change master password)

The session key is stored as a bytearray so it can be overwritten in-place
before being discarded, reducing the window of exposure in memory.
"""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import List, Optional, Tuple

from cryptography.exceptions import InvalidTag

from .crypto import (
    account_aad,
    decrypt_field,
    derive_key,
    encrypt_field,
    new_salt,
)
from .database import Database
from .errors import VaultLockedError, VaultNotInitializedError, WrongPasswordError
from .models import Account, Character, VaultMeta
from .export_import import (
    ImportPreview,
    build_import_preview,
    decode_bundle,
    encode_bundle,
)

# Re-export for callers that import exceptions from this module
__all__ = [
    "Vault",
    "WrongPasswordError",
    "VaultNotInitializedError",
    "VaultLockedError",
]


class Vault:
    def __init__(self, db_path: Path) -> None:
        self._db = Database(db_path)
        self._key: Optional[bytearray] = None  # None means locked

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        return self._db.has_vault_meta()

    @property
    def is_unlocked(self) -> bool:
        return self._key is not None

    def initialize(self, master_password: str) -> None:
        """Create a new vault with the given master password."""
        if self.is_initialized:
            raise RuntimeError("Vault is already initialized.")
        salt = new_salt()
        meta = VaultMeta(kdf_salt=salt)
        self._db.write_vault_meta(meta)
        key_bytes = derive_key(
            master_password,
            salt,
            meta.kdf_time_cost,
            meta.kdf_memory_cost,
            meta.kdf_parallelism,
        )
        self._key = bytearray(key_bytes)

    def unlock(self, master_password: str) -> None:
        """Derive the key and verify it by decrypting a known-good account."""
        if not self.is_initialized:
            raise VaultNotInitializedError("Vault has not been created yet.")
        meta = self._db.read_vault_meta()
        key_bytes = derive_key(
            master_password,
            meta.kdf_salt,
            meta.kdf_time_cost,
            meta.kdf_memory_cost,
            meta.kdf_parallelism,
        )
        # Verify the key against the first encrypted account row if one exists,
        # otherwise accept (empty vault, any key is "correct" until first account).
        candidate_key = bytearray(key_bytes)
        rows = self._db.list_accounts_for_search()
        if rows:
            first_id = rows[0]["id"]
            raw = self._db.get_account_raw(first_id)
            if raw and raw["username_enc"]:
                try:
                    decrypt_field(
                        bytes(candidate_key),
                        bytes(raw["username_enc"]),
                        bytes(raw["username_nonce"]),
                        account_aad(first_id),
                    )
                except InvalidTag:
                    _zero(candidate_key)
                    raise WrongPasswordError("Incorrect master password.")
        if self._key is not None:
            _zero(self._key)
        self._key = candidate_key

    def lock(self) -> None:
        """Zero the session key and mark the vault as locked."""
        if self._key is not None:
            _zero(self._key)
            self._key = None

    def close(self) -> None:
        self.lock()
        self._db.close()

    # ------------------------------------------------------------------
    # Account operations (require unlocked vault)
    # ------------------------------------------------------------------

    def save_account(self, account: Account) -> None:
        """Encrypt credentials and persist the account (insert or update)."""
        key = self._require_key()
        aad = account_aad(account.id)
        u_enc, u_nonce = encrypt_field(key, account.username or "", aad)
        p_enc, p_nonce = encrypt_field(key, account.password or "", aad)

        raw = self._db.get_account_raw(account.id)
        if raw is None:
            self._db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)
        else:
            self._db.update_account(account, u_enc, u_nonce, p_enc, p_nonce)

        self._db.upsert_characters(account.id, account.characters)
        self._db.set_account_tags(account.id, account.tags)

    def delete_account(self, account_id: str) -> None:
        self._require_key()
        self._db.delete_account(account_id)

    def load_account(self, account_id: str) -> Account:
        """Load and decrypt a full account (including credentials)."""
        key = self._require_key()
        raw = self._db.get_account_raw(account_id)
        if raw is None:
            raise KeyError(f"Account {account_id} not found.")
        aad = account_aad(account_id)

        username = ""
        password = ""
        if raw["username_enc"]:
            username = decrypt_field(
                key, bytes(raw["username_enc"]), bytes(raw["username_nonce"]), aad
            )
        if raw["password_enc"]:
            password = decrypt_field(
                key, bytes(raw["password_enc"]), bytes(raw["password_nonce"]), aad
            )

        characters = self._db.get_characters(account_id)
        tags = self._db.get_account_tags(account_id)

        return Account(
            id=raw["id"],
            label=raw["label"],
            username=username,
            password=password,
            owner=raw["owner"],
            shared_by=raw["shared_by"],
            status=raw["status"],
            role_flag=raw["role_flag"],
            rotate_flag=raw["rotate_flag"],
            notes=raw["notes"],
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            characters=characters,
            tags=tags,
        )

    def list_accounts(self, query: str = "") -> List[Account]:
        """
        Return a list of Account objects for the list view.
        Credentials are NOT decrypted here — username/password will be empty.
        Characters and tags are populated for display.
        """
        self._require_key()
        rows = self._db.search(query)
        account_ids = [r["id"] for r in rows]
        tag_map = self._db.get_tags_for_accounts(account_ids)
        char_map = self._db.get_characters_for_accounts(account_ids)
        return [
            Account(
                id=raw["id"],
                label=raw["label"],
                username=None,
                password=None,
                owner=raw["owner"],
                shared_by=raw["shared_by"],
                status=raw["status"],
                role_flag=raw["role_flag"],
                rotate_flag=raw["rotate_flag"],
                notes=raw["notes"],
                created_at=raw["created_at"],
                updated_at=raw["updated_at"],
                characters=char_map.get(raw["id"], []),
                tags=tag_map.get(raw["id"], []),
            )
            for raw in rows
        ]

    def all_tag_names(self) -> List[str]:
        self._require_key()
        return [t.name for t in self._db.all_tags()]

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export_accounts(self, account_ids: List[str], export_password: str) -> bytes:
        """Decrypt the selected accounts and encode them into an .eqcx bundle."""
        key = self._require_key()
        accounts = []
        for aid in account_ids:
            raw = self._db.get_account_raw(aid)
            if raw is None:
                continue
            aad = account_aad(aid)
            username = ""
            password = ""
            if raw["username_enc"]:
                username = decrypt_field(
                    key, bytes(raw["username_enc"]), bytes(raw["username_nonce"]), aad
                )
            if raw["password_enc"]:
                password = decrypt_field(
                    key, bytes(raw["password_enc"]), bytes(raw["password_nonce"]), aad
                )
            characters = self._db.get_characters(aid)
            tags = self._db.get_account_tags(aid)
            accounts.append(
                Account(
                    id=raw["id"],
                    label=raw["label"],
                    username=username,
                    password=password,
                    owner=raw["owner"],
                    shared_by=raw["shared_by"],
                    status=raw["status"],
                    role_flag=raw["role_flag"],
                    rotate_flag=raw["rotate_flag"],
                    notes=raw["notes"],
                    created_at=raw["created_at"],
                    updated_at=raw["updated_at"],
                    characters=characters,
                    tags=tags,
                )
            )
        return encode_bundle(accounts, export_password)

    def preview_import(self, data: bytes, export_password: str) -> ImportPreview:
        """
        Decode an .eqcx bundle and compare it against the current vault.

        Returns an ImportPreview with clean (no conflict) and conflict lists.
        Does not write anything to the database.
        """
        key = self._require_key()
        incoming = decode_bundle(data, export_password)  # raises on bad pw/file

        all_rows = self._db.list_accounts_for_search()
        existing: List[Account] = []
        for row in all_rows:
            aid = row["id"]
            raw = self._db.get_account_raw(aid)
            aad = account_aad(aid)
            username = ""
            if raw and raw["username_enc"]:
                username = decrypt_field(
                    key, bytes(raw["username_enc"]), bytes(raw["username_nonce"]), aad
                )
            existing.append(
                Account(
                    id=row["id"],
                    label=row["label"],
                    username=username,
                    owner=row["owner"],
                    shared_by=row["shared_by"],
                    status=row["status"],
                    role_flag=row["role_flag"],
                    rotate_flag=row["rotate_flag"],
                    notes=row["notes"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        return build_import_preview(incoming, existing)

    def apply_import(self, preview: ImportPreview) -> int:
        """
        Write all clean accounts and apply conflict resolutions to the vault.

        - MERGE: replace credentials/metadata on the existing row (keeps id + created_at)
        - SKIP:  leave the existing account untouched

        Returns the number of accounts actually written.
        """
        key = self._require_key()
        written = 0

        def _save(account: Account) -> None:
            aad = account_aad(account.id)
            u_enc, u_nonce = encrypt_field(key, account.username or "", aad)
            p_enc, p_nonce = encrypt_field(key, account.password or "", aad)
            raw = self._db.get_account_raw(account.id)
            if raw is None:
                self._db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)
            else:
                self._db.update_account(account, u_enc, u_nonce, p_enc, p_nonce)
            self._db.upsert_characters(account.id, account.characters)
            self._db.set_account_tags(account.id, account.tags)

        for account in preview.clean:
            _save(account)
            written += 1

        from .export_import import ConflictResolution
        for record in preview.conflicts:
            if record.resolution == ConflictResolution.MERGE:
                # Keep the existing row's id and created_at; replace everything else
                merged = record.imported.model_copy(
                    update={
                        "id": record.existing.id,
                        "created_at": record.existing.created_at,
                    }
                )
                _save(merged)
                written += 1

        return written

    # ------------------------------------------------------------------
    # Re-key (master password change)
    # ------------------------------------------------------------------

    def change_password(self, old_password: str, new_password: str) -> None:
        """
        Verify old password, re-derive key with new password,
        re-encrypt all accounts, update vault_meta — all in one atomic tx.
        """
        key = self._require_key()
        meta = self._db.read_vault_meta()
        # Verify old password by re-deriving and comparing (constant-time)
        old_key_bytes = derive_key(
            old_password,
            meta.kdf_salt,
            meta.kdf_time_cost,
            meta.kdf_memory_cost,
            meta.kdf_parallelism,
        )
        if not hmac.compare_digest(old_key_bytes, key):
            raise WrongPasswordError("Incorrect master password.")

        new_salt_ = new_salt()
        new_meta = VaultMeta(
            kdf_salt=new_salt_,
            kdf_time_cost=meta.kdf_time_cost,
            kdf_memory_cost=meta.kdf_memory_cost,
            kdf_parallelism=meta.kdf_parallelism,
        )
        new_key_bytes = derive_key(
            new_password,
            new_salt_,
            new_meta.kdf_time_cost,
            new_meta.kdf_memory_cost,
            new_meta.kdf_parallelism,
        )
        new_key = bytearray(new_key_bytes)

        all_rows = self._db.list_accounts_for_search()
        reencrypted: List[Tuple[str, bytes, bytes, bytes, bytes]] = []
        for row in all_rows:
            aid = row["id"]
            raw = self._db.get_account_raw(aid)
            aad = account_aad(aid)
            username = ""
            password = ""
            if raw["username_enc"]:
                username = decrypt_field(
                    bytes(key), bytes(raw["username_enc"]), bytes(raw["username_nonce"]), aad
                )
            if raw["password_enc"]:
                password = decrypt_field(
                    bytes(key), bytes(raw["password_enc"]), bytes(raw["password_nonce"]), aad
                )
            u_enc, u_nonce = encrypt_field(bytes(new_key), username, aad)
            p_enc, p_nonce = encrypt_field(bytes(new_key), password, aad)
            reencrypted.append((aid, u_enc, u_nonce, p_enc, p_nonce))

        self._db.rekey_accounts(reencrypted, new_meta)

        # Swap in the new key
        _zero(self._key)
        self._key = new_key

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_key(self) -> bytes:
        if self._key is None:
            raise VaultLockedError("Vault is locked.")
        return bytes(self._key)


def _zero(buf: bytearray) -> None:
    """Overwrite a bytearray in-place to reduce key exposure in memory."""
    for i in range(len(buf)):
        buf[i] = 0
