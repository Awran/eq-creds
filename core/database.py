"""
SQLite database layer for EQ-Creds.

All writes that touch encrypted fields receive raw ciphertext/nonce bytes
from the vault layer — this module never holds plaintext credentials.

PRAGMA foreign_keys = ON is set on every connection to enforce cascade deletes.
PRAGMA journal_mode = DELETE avoids WAL sidecar files that would contain
unencrypted metadata pages.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Tuple
from uuid import uuid4

from .models import Account, Character, Tag, VaultMeta

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS vault_meta (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    kdf_salt          BLOB    NOT NULL,
    kdf_time_cost     INTEGER NOT NULL DEFAULT 3,
    kdf_memory_cost   INTEGER NOT NULL DEFAULT 65536,
    kdf_parallelism   INTEGER NOT NULL DEFAULT 1,
    schema_version    INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id            TEXT PRIMARY KEY,
    label         TEXT NOT NULL,
    username_enc  BLOB,
    username_nonce BLOB,
    password_enc  BLOB,
    password_nonce BLOB,
    owner         TEXT,
    shared_by     TEXT,
    status        TEXT NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active','archived')),
    role_flag     TEXT CHECK (role_flag IN ('main','banker','mule','utility')),
    rotate_flag   TEXT CHECK (rotate_flag IN ('rotate','no_rotate','shared')),
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id         TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    char_class TEXT,
    level      INTEGER,
    notes      TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS account_tags (
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    tag_id     TEXT NOT NULL REFERENCES tags(id)     ON DELETE CASCADE,
    PRIMARY KEY (account_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_characters_account ON characters(account_id);
CREATE INDEX IF NOT EXISTS idx_characters_name    ON characters(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_accounts_label     ON accounts(label COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_accounts_owner     ON accounts(owner COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_accounts_shared_by ON accounts(shared_by COLLATE NOCASE);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = DELETE")
    return conn


@contextmanager
def _tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Cursor]:
    """Context manager that commits on success or rolls back on exception."""
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------


class Database:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = _connect(db_path)
        self._apply_schema()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _apply_schema(self) -> None:
        with _tx(self._conn) as cur:
            for statement in _DDL.strip().split(";"):
                statement = statement.strip()
                if statement:
                    cur.execute(statement)

    # ------------------------------------------------------------------
    # Vault meta
    # ------------------------------------------------------------------

    def has_vault_meta(self) -> bool:
        row = self._conn.execute("SELECT id FROM vault_meta WHERE id = 1").fetchone()
        return row is not None

    def write_vault_meta(self, meta: VaultMeta) -> None:
        with _tx(self._conn) as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO vault_meta
                    (id, kdf_salt, kdf_time_cost, kdf_memory_cost,
                     kdf_parallelism, schema_version, created_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meta.kdf_salt,
                    meta.kdf_time_cost,
                    meta.kdf_memory_cost,
                    meta.kdf_parallelism,
                    meta.schema_version,
                    meta.created_at,
                ),
            )

    def read_vault_meta(self) -> Optional[VaultMeta]:
        row = self._conn.execute("SELECT * FROM vault_meta WHERE id = 1").fetchone()
        if row is None:
            return None
        return VaultMeta(
            kdf_salt=bytes(row["kdf_salt"]),
            kdf_time_cost=row["kdf_time_cost"],
            kdf_memory_cost=row["kdf_memory_cost"],
            kdf_parallelism=row["kdf_parallelism"],
            schema_version=row["schema_version"],
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------
    # Accounts — raw encrypted writes
    # ------------------------------------------------------------------

    def insert_account(
        self,
        account: Account,
        username_enc: bytes,
        username_nonce: bytes,
        password_enc: bytes,
        password_nonce: bytes,
    ) -> None:
        with _tx(self._conn) as cur:
            cur.execute(
                """
                INSERT INTO accounts
                    (id, label, username_enc, username_nonce,
                     password_enc, password_nonce,
                     owner, shared_by, status, role_flag, rotate_flag,
                     notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    account.id,
                    account.label,
                    username_enc,
                    username_nonce,
                    password_enc,
                    password_nonce,
                    account.owner,
                    account.shared_by,
                    account.status,
                    account.role_flag,
                    account.rotate_flag,
                    account.notes,
                    account.created_at,
                    account.updated_at,
                ),
            )

    def update_account(
        self,
        account: Account,
        username_enc: bytes,
        username_nonce: bytes,
        password_enc: bytes,
        password_nonce: bytes,
    ) -> None:
        with _tx(self._conn) as cur:
            cur.execute(
                """
                UPDATE accounts SET
                    label          = ?,
                    username_enc   = ?,
                    username_nonce = ?,
                    password_enc   = ?,
                    password_nonce = ?,
                    owner          = ?,
                    shared_by      = ?,
                    status         = ?,
                    role_flag      = ?,
                    rotate_flag    = ?,
                    notes          = ?,
                    updated_at     = ?
                WHERE id = ?
                """,
                (
                    account.label,
                    username_enc,
                    username_nonce,
                    password_enc,
                    password_nonce,
                    account.owner,
                    account.shared_by,
                    account.status,
                    account.role_flag,
                    account.rotate_flag,
                    account.notes,
                    _now(),
                    account.id,
                ),
            )

    def delete_account(self, account_id: str) -> None:
        with _tx(self._conn) as cur:
            cur.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    def get_account_raw(self, account_id: str) -> Optional[sqlite3.Row]:
        """Return the raw DB row including encrypted blobs (for decryption)."""
        return self._conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()

    def list_accounts_for_search(self) -> List[sqlite3.Row]:
        """
        Return all account rows with plaintext fields only — no encrypted blobs.
        Used by the search/list view; credentials are never loaded until requested.
        """
        return self._conn.execute(
            """
            SELECT id, label, owner, shared_by, status, role_flag, rotate_flag,
                   notes, created_at, updated_at
            FROM accounts
            ORDER BY label COLLATE NOCASE
            """
        ).fetchall()

    # ------------------------------------------------------------------
    # Characters
    # ------------------------------------------------------------------

    def upsert_characters(self, account_id: str, characters: List[Character]) -> None:
        """Replace all characters for an account atomically."""
        with _tx(self._conn) as cur:
            cur.execute("DELETE FROM characters WHERE account_id = ?", (account_id,))
            for ch in characters:
                cur.execute(
                    """
                    INSERT INTO characters
                        (id, account_id, name, char_class, level, notes, created_at)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        ch.id,
                        account_id,
                        ch.name,
                        ch.char_class,
                        ch.level,
                        ch.notes,
                        ch.created_at,
                    ),
                )

    def get_characters(self, account_id: str) -> List[Character]:
        rows = self._conn.execute(
            "SELECT * FROM characters WHERE account_id = ? ORDER BY name COLLATE NOCASE",
            (account_id,),
        ).fetchall()
        return [
            Character(
                id=r["id"],
                account_id=r["account_id"],
                name=r["name"],
                char_class=r["char_class"],
                level=r["level"],
                notes=r["notes"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get_characters_for_accounts(self, account_ids: List[str]) -> dict:
        """Return {account_id: [Character, ...]} for a list of account ids."""
        if not account_ids:
            return {}
        placeholders = ",".join("?" * len(account_ids))
        rows = self._conn.execute(
            f"SELECT * FROM characters WHERE account_id IN ({placeholders})"
            " ORDER BY name COLLATE NOCASE",
            account_ids,
        ).fetchall()
        result: dict = {aid: [] for aid in account_ids}
        for r in rows:
            result[r["account_id"]].append(Character(
                id=r["id"],
                account_id=r["account_id"],
                name=r["name"],
                char_class=r["char_class"],
                level=r["level"],
                notes=r["notes"],
                created_at=r["created_at"],
            ))
        return result

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def get_or_create_tag(self, name: str) -> str:
        """Return the tag id, creating the tag if it doesn't exist."""
        row = self._conn.execute(
            "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if row:
            return row["id"]
        tag_id = str(uuid4())
        with _tx(self._conn) as cur:
            cur.execute("INSERT INTO tags (id, name) VALUES (?,?)", (tag_id, name))
        return tag_id

    def all_tags(self) -> List[Tag]:
        rows = self._conn.execute("SELECT * FROM tags ORDER BY name COLLATE NOCASE").fetchall()
        return [Tag(id=r["id"], name=r["name"]) for r in rows]

    def set_account_tags(self, account_id: str, tag_names: List[str]) -> None:
        """Replace all tags for an account atomically."""
        with _tx(self._conn) as cur:
            cur.execute("DELETE FROM account_tags WHERE account_id = ?", (account_id,))
            for name in tag_names:
                cur.execute(
                    "INSERT OR IGNORE INTO tags (id, name) VALUES (?,?)",
                    (str(uuid4()), name),
                )
                row = cur.execute(
                    "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)
                ).fetchone()
                cur.execute(
                    "INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?,?)",
                    (account_id, row["id"]),
                )

    def get_account_tags(self, account_id: str) -> List[str]:
        rows = self._conn.execute(
            """
            SELECT t.name FROM tags t
            JOIN account_tags at ON at.tag_id = t.id
            WHERE at.account_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (account_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def get_tags_for_accounts(self, account_ids: List[str]) -> dict:
        """Return {account_id: [tag_name, ...]} for a list of account ids."""
        if not account_ids:
            return {}
        placeholders = ",".join("?" * len(account_ids))
        rows = self._conn.execute(
            f"""
            SELECT at.account_id, t.name FROM account_tags at
            JOIN tags t ON t.id = at.tag_id
            WHERE at.account_id IN ({placeholders})
            ORDER BY t.name COLLATE NOCASE
            """,
            account_ids,
        ).fetchall()
        result: dict = {aid: [] for aid in account_ids}
        for r in rows:
            result[r["account_id"]].append(r["name"])
        return result

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[sqlite3.Row]:
        """
        Return account rows matching the query against plaintext fields.
        Searches: label, owner, shared_by, character names, tag names.
        Returns rows ordered by label.
        """
        if not query.strip():
            return self.list_accounts_for_search()

        pattern = f"%{query.strip()}%"
        return self._conn.execute(
            """
            SELECT DISTINCT a.id, a.label, a.owner, a.shared_by, a.status,
                   a.role_flag, a.rotate_flag, a.notes, a.created_at, a.updated_at
            FROM accounts a
            LEFT JOIN characters c ON c.account_id = a.id
            LEFT JOIN account_tags at ON at.account_id = a.id
            LEFT JOIN tags t ON t.id = at.tag_id
            WHERE
                a.label     LIKE ? COLLATE NOCASE OR
                a.owner     LIKE ? COLLATE NOCASE OR
                a.shared_by LIKE ? COLLATE NOCASE OR
                c.name      LIKE ? COLLATE NOCASE OR
                t.name      LIKE ? COLLATE NOCASE
            ORDER BY a.label COLLATE NOCASE
            """,
            (pattern, pattern, pattern, pattern, pattern),
        ).fetchall()

    # ------------------------------------------------------------------
    # Re-key (master password change)
    # ------------------------------------------------------------------

    def rekey_accounts(
        self,
        reencrypted: List[Tuple[str, bytes, bytes, bytes, bytes]],
        new_meta: VaultMeta,
    ) -> None:
        """
        Atomically replace all encrypted fields and vault_meta.
        reencrypted: list of (account_id, username_enc, username_nonce,
                               password_enc, password_nonce)
        """
        with _tx(self._conn) as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO vault_meta
                    (id, kdf_salt, kdf_time_cost, kdf_memory_cost,
                     kdf_parallelism, schema_version, created_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_meta.kdf_salt,
                    new_meta.kdf_time_cost,
                    new_meta.kdf_memory_cost,
                    new_meta.kdf_parallelism,
                    new_meta.schema_version,
                    new_meta.created_at,
                ),
            )
            for account_id, u_enc, u_nonce, p_enc, p_nonce in reencrypted:
                cur.execute(
                    """
                    UPDATE accounts SET
                        username_enc   = ?,
                        username_nonce = ?,
                        password_enc   = ?,
                        password_nonce = ?,
                        updated_at     = ?
                    WHERE id = ?
                    """,
                    (u_enc, u_nonce, p_enc, p_nonce, _now(), account_id),
                )
