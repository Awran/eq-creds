import tempfile
from pathlib import Path

import pytest

from core.crypto import account_aad, derive_key, encrypt_field, new_salt
from core.database import Database
from core.models import Account, Character, Tag, VaultMeta


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_vault.db"
        database = Database(db_path)
        yield database
        database.close()


@pytest.fixture
def salt():
    return new_salt()


@pytest.fixture
def key(salt):
    return derive_key("testpass", salt)


def _enc(key, account_id, username="user1", password="pass1"):
    aad = account_aad(account_id)
    u_enc, u_nonce = encrypt_field(key, username, aad)
    p_enc, p_nonce = encrypt_field(key, password, aad)
    return u_enc, u_nonce, p_enc, p_nonce


# ------------------------------------------------------------------
# VaultMeta
# ------------------------------------------------------------------

def test_vault_meta_roundtrip(db, salt):
    assert not db.has_vault_meta()
    meta = VaultMeta(kdf_salt=salt)
    db.write_vault_meta(meta)
    assert db.has_vault_meta()
    loaded = db.read_vault_meta()
    assert loaded.kdf_salt == salt
    assert loaded.schema_version == 1


# ------------------------------------------------------------------
# Accounts
# ------------------------------------------------------------------

def test_insert_and_retrieve_account(db, key):
    account = Account(label="TestAccount", owner="Alice", shared_by="Bob", status="active")
    u_enc, u_nonce, p_enc, p_nonce = _enc(key, account.id)
    db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)

    raw = db.get_account_raw(account.id)
    assert raw is not None
    assert raw["label"] == "TestAccount"
    assert raw["owner"] == "Alice"
    assert raw["shared_by"] == "Bob"


def test_update_account(db, key):
    account = Account(label="Before")
    u_enc, u_nonce, p_enc, p_nonce = _enc(key, account.id)
    db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)

    account.label = "After"
    db.update_account(account, u_enc, u_nonce, p_enc, p_nonce)
    raw = db.get_account_raw(account.id)
    assert raw["label"] == "After"


def test_delete_account(db, key):
    account = Account(label="ToDelete")
    u_enc, u_nonce, p_enc, p_nonce = _enc(key, account.id)
    db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)
    db.delete_account(account.id)
    assert db.get_account_raw(account.id) is None


def test_list_accounts(db, key):
    for label in ("Zach", "Alice", "Bob"):
        acc = Account(label=label)
        u_enc, u_nonce, p_enc, p_nonce = _enc(key, acc.id)
        db.insert_account(acc, u_enc, u_nonce, p_enc, p_nonce)
    rows = db.list_accounts_for_search()
    labels = [r["label"] for r in rows]
    assert labels == sorted(labels, key=str.lower)


# ------------------------------------------------------------------
# Characters
# ------------------------------------------------------------------

def test_characters_one_to_many(db, key):
    account = Account(label="MultiChar")
    u_enc, u_nonce, p_enc, p_nonce = _enc(key, account.id)
    db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)

    chars = [
        Character(account_id=account.id, name="Lahrind", char_class="Enchanter", level=60),
        Character(account_id=account.id, name="Bankertoon", char_class="Warrior", level=1),
        Character(account_id=account.id, name="Druidmule", char_class="Druid", level=50),
    ]
    db.upsert_characters(account.id, chars)

    loaded = db.get_characters(account.id)
    assert len(loaded) == 3
    names = {ch.name for ch in loaded}
    assert names == {"Lahrind", "Bankertoon", "Druidmule"}


def test_characters_cascade_delete(db, key):
    account = Account(label="CascadeTest")
    u_enc, u_nonce, p_enc, p_nonce = _enc(key, account.id)
    db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)
    db.upsert_characters(account.id, [
        Character(account_id=account.id, name="Char1"),
    ])
    db.delete_account(account.id)
    assert db.get_characters(account.id) == []


def test_upsert_characters_replaces(db, key):
    account = Account(label="Replace")
    u_enc, u_nonce, p_enc, p_nonce = _enc(key, account.id)
    db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)
    db.upsert_characters(account.id, [Character(account_id=account.id, name="Old")])
    db.upsert_characters(account.id, [Character(account_id=account.id, name="New")])
    loaded = db.get_characters(account.id)
    assert len(loaded) == 1
    assert loaded[0].name == "New"


# ------------------------------------------------------------------
# Tags
# ------------------------------------------------------------------

def test_tags_roundtrip(db, key):
    account = Account(label="Tagged")
    u_enc, u_nonce, p_enc, p_nonce = _enc(key, account.id)
    db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)
    db.set_account_tags(account.id, ["guild", "raider", "banker"])
    tags = db.get_account_tags(account.id)
    assert set(tags) == {"guild", "raider", "banker"}


def test_tags_cascade_delete(db, key):
    account = Account(label="TagDelete")
    u_enc, u_nonce, p_enc, p_nonce = _enc(key, account.id)
    db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)
    db.set_account_tags(account.id, ["guild"])
    db.delete_account(account.id)
    assert db.get_account_tags(account.id) == []


# ------------------------------------------------------------------
# Search
# ------------------------------------------------------------------

def test_search_by_label(db, key):
    for label in ("GuildMain", "MuleAccount", "BankToon"):
        acc = Account(label=label)
        db.insert_account(acc, *_enc(key, acc.id))
    results = db.search("Guild")
    assert len(results) == 1


def test_search_by_character_name(db, key):
    account = Account(label="SomeAccount")
    db.insert_account(account, *_enc(key, account.id))
    db.upsert_characters(account.id, [
        Character(account_id=account.id, name="Lahrind"),
    ])
    results = db.search("Lahrind")
    assert account.id in results


def test_search_by_tag(db, key):
    account = Account(label="SearchByTag")
    db.insert_account(account, *_enc(key, account.id))
    db.set_account_tags(account.id, ["raidleader"])
    results = db.search("raidleader")
    assert account.id in results


def test_search_empty_returns_all(db, key):
    for label in ("A", "B", "C"):
        acc = Account(label=label)
        db.insert_account(acc, *_enc(key, acc.id))
    results = db.search("")
    assert len(results) == 3


# ------------------------------------------------------------------
# Re-key
# ------------------------------------------------------------------

def test_rekey(db, salt, key):
    meta = VaultMeta(kdf_salt=salt)
    db.write_vault_meta(meta)

    account = Account(label="ReKeyTest")
    u_enc, u_nonce, p_enc, p_nonce = _enc(key, account.id, "user", "pass")
    db.insert_account(account, u_enc, u_nonce, p_enc, p_nonce)

    new_salt_ = new_salt()
    new_key = derive_key("newpass", new_salt_)
    new_meta = VaultMeta(kdf_salt=new_salt_)

    from core.crypto import decrypt_field
    aad = account_aad(account.id)
    raw = db.get_account_raw(account.id)
    username = decrypt_field(key, bytes(raw["username_enc"]), bytes(raw["username_nonce"]), aad)
    password = decrypt_field(key, bytes(raw["password_enc"]), bytes(raw["password_nonce"]), aad)

    new_u_enc, new_u_nonce = encrypt_field(new_key, username, aad)
    new_p_enc, new_p_nonce = encrypt_field(new_key, password, aad)

    db.rekey_accounts(
        [(account.id, new_u_enc, new_u_nonce, new_p_enc, new_p_nonce)],
        new_meta,
    )

    loaded_meta = db.read_vault_meta()
    assert loaded_meta.kdf_salt == new_salt_

    raw2 = db.get_account_raw(account.id)
    recovered = decrypt_field(new_key, bytes(raw2["username_enc"]), bytes(raw2["username_nonce"]), aad)
    assert recovered == "user"
