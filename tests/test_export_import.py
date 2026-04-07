"""
Tests for secure export / import (core layer only — no UI).

Coverage:
  - encode_bundle / decode_bundle roundtrip
  - Wrong password rejected with WrongPasswordError
  - Tampered ciphertext rejected with WrongPasswordError
  - Bad magic / version rejected with ValueError
  - Empty account list roundtrip
  - build_import_preview: username anchor (no conflict)
  - build_import_preview: username conflict detected
  - build_import_preview: label fallback (blank username) no conflict
  - build_import_preview: label fallback conflict
  - Vault.export_accounts / preview_import / apply_import integration
  - apply_import MERGE: fields replaced, id/created_at preserved
  - apply_import SKIP: existing account unchanged
  - apply_import clean accounts written with new id
"""

import tempfile
from pathlib import Path

import pytest

from core.crypto import derive_key, new_salt
from core.database import Database
from core.export_import import (
    ConflictResolution,
    ImportPreview,
    ConflictRecord,
    build_import_preview,
    decode_bundle,
    encode_bundle,
)
from core.models import Account, Character
from core.vault import Vault, WrongPasswordError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_vault(tmp_path):
    db_path = tmp_path / "vault.db"
    vault = Vault(db_path)
    vault.initialize("masterpass")
    yield vault
    vault.close()


def _make_account(label: str = "Test", username: str = "user", password: str = "pass") -> Account:
    return Account(label=label, username=username, password=password)


# ---------------------------------------------------------------------------
# encode_bundle / decode_bundle
# ---------------------------------------------------------------------------

def test_roundtrip_single_account():
    account = _make_account("GuildBank", "guilduser", "s3cr3t")
    account.characters = [
        Character(account_id=account.id, name="Lahrind", char_class="Enchanter", level=60)
    ]
    account.tags = ["guild", "main"]

    bundle = encode_bundle([account], "exportpass")
    recovered = decode_bundle(bundle, "exportpass")

    assert len(recovered) == 1
    r = recovered[0]
    assert r.label == "GuildBank"
    assert r.username == "guilduser"
    assert r.password == "s3cr3t"
    assert r.tags == ["guild", "main"]
    assert len(r.characters) == 1
    assert r.characters[0].name == "Lahrind"
    assert r.characters[0].char_class == "Enchanter"
    assert r.characters[0].level == 60


def test_roundtrip_multiple_accounts():
    accounts = [_make_account(f"Account{i}", f"user{i}", f"pass{i}") for i in range(5)]
    bundle = encode_bundle(accounts, "pw")
    recovered = decode_bundle(bundle, "pw")
    assert len(recovered) == 5
    labels = {a.label for a in recovered}
    assert labels == {f"Account{i}" for i in range(5)}


def test_roundtrip_empty_list():
    bundle = encode_bundle([], "pw")
    recovered = decode_bundle(bundle, "pw")
    assert recovered == []


def test_wrong_password_raises():
    bundle = encode_bundle([_make_account()], "correct")
    with pytest.raises(WrongPasswordError):
        decode_bundle(bundle, "wrong")


def test_tampered_ciphertext_raises():
    bundle = encode_bundle([_make_account()], "pw")
    # Flip a byte in the ciphertext region (after 33-byte header)
    tampered = bytearray(bundle)
    tampered[33] ^= 0xFF
    with pytest.raises(WrongPasswordError):
        decode_bundle(bytes(tampered), "pw")


def test_bad_magic_raises():
    bundle = bytearray(encode_bundle([_make_account()], "pw"))
    bundle[0] = ord("X")
    with pytest.raises(ValueError, match="bad magic"):
        decode_bundle(bytes(bundle), "pw")


def test_bad_version_raises():
    bundle = bytearray(encode_bundle([_make_account()], "pw"))
    bundle[4] = 0xFF  # version byte
    with pytest.raises(ValueError, match="version"):
        decode_bundle(bytes(bundle), "pw")


def test_too_short_raises():
    with pytest.raises(ValueError, match="too short"):
        decode_bundle(b"short", "pw")


def test_unicode_credentials():
    account = _make_account("Intl", "ünïcödé", "pässwørd_🔐")
    bundle = encode_bundle([account], "pw")
    recovered = decode_bundle(bundle, "pw")[0]
    assert recovered.username == "ünïcödé"
    assert recovered.password == "pässwørd_🔐"


def test_none_credentials():
    account = Account(label="NoPass")  # username/password both None
    bundle = encode_bundle([account], "pw")
    recovered = decode_bundle(bundle, "pw")[0]
    assert recovered.username is None
    assert recovered.password is None


# ---------------------------------------------------------------------------
# build_import_preview — conflict detection
# ---------------------------------------------------------------------------

def test_no_conflict_different_username():
    incoming = [_make_account("A", "alice", "pw")]
    existing = [_make_account("B", "bob", "pw")]
    preview = build_import_preview(incoming, existing)
    assert len(preview.clean) == 1
    assert len(preview.conflicts) == 0


def test_username_conflict_detected():
    incoming = [_make_account("New Label", "shared_user", "newpw")]
    existing = [_make_account("Old Label", "shared_user", "oldpw")]
    preview = build_import_preview(incoming, existing)
    assert len(preview.conflicts) == 1
    assert preview.conflicts[0].imported.label == "New Label"
    assert preview.conflicts[0].existing.label == "Old Label"
    assert len(preview.clean) == 0


def test_username_conflict_is_case_sensitive():
    """Username matching is case-sensitive."""
    incoming = [_make_account("A", "User", "pw")]
    existing = [_make_account("B", "user", "pw")]
    preview = build_import_preview(incoming, existing)
    # "User" != "user" → no conflict
    assert len(preview.clean) == 1
    assert len(preview.conflicts) == 0


def test_label_fallback_no_conflict():
    """Blank username falls back to label; different label = no conflict."""
    incoming = [Account(label="Alpha", username=None)]
    existing = [Account(label="Beta", username=None)]
    preview = build_import_preview(incoming, existing)
    assert len(preview.clean) == 1
    assert len(preview.conflicts) == 0


def test_label_fallback_conflict():
    """Blank username falls back to label; same label (case-insensitive) = conflict."""
    incoming = [Account(label="GuildBank", username=None)]
    existing = [Account(label="guildbank", username=None)]
    preview = build_import_preview(incoming, existing)
    assert len(preview.conflicts) == 1


def test_mixed_clean_and_conflicts():
    incoming = [
        _make_account("A", "alice", "pw"),
        _make_account("B", "bob", "pw"),
        _make_account("C", "carol", "pw"),
    ]
    existing = [_make_account("B_old", "bob", "oldpw")]
    preview = build_import_preview(incoming, existing)
    assert len(preview.clean) == 2
    assert len(preview.conflicts) == 1


# ---------------------------------------------------------------------------
# Vault integration — export_accounts / preview_import / apply_import
# ---------------------------------------------------------------------------

def _add_account_to_vault(vault: Vault, label: str, username: str, password: str) -> Account:
    accounts = vault.list_accounts()
    acc = Account(label=label, username=username, password=password)
    vault.save_account(acc)
    return acc


def test_vault_export_and_reimport(tmp_path):
    """Export from one vault, import into a fresh second vault."""
    db1 = tmp_path / "v1.db"
    v1 = Vault(db1)
    v1.initialize("masterpass1")
    acc = _add_account_to_vault(v1, "GuildMain", "gmuser", "gmpw")
    acc = v1.load_account(acc.id)  # ensure chars/tags loaded

    bundle = v1.export_accounts([acc.id], "exportpw")
    v1.close()

    db2 = tmp_path / "v2.db"
    v2 = Vault(db2)
    v2.initialize("masterpass2")

    preview = v2.preview_import(bundle, "exportpw")
    assert len(preview.clean) == 1
    assert len(preview.conflicts) == 0

    count = v2.apply_import(preview)
    assert count == 1

    # Verify credentials decrypted correctly in v2
    loaded = v2.load_account(preview.clean[0].id)
    assert loaded.label == "GuildMain"
    assert loaded.username == "gmuser"
    assert loaded.password == "gmpw"
    v2.close()


def test_apply_import_merge(tmp_path):
    """MERGE replaces updatable fields but preserves existing id and created_at."""
    db = tmp_path / "v.db"
    v = Vault(db)
    v.initialize("pw")

    # Existing account in the vault
    existing = Account(label="Existing", username="shareduser", password="oldpass")
    v.save_account(existing)

    # Incoming with same username but updated label and password
    incoming = Account(
        label="Updated Label",
        username="shareduser",
        password="newpass",
        notes="now with notes",
    )
    existing_full = v.load_account(existing.id)

    from core.export_import import ConflictRecord, ConflictResolution, ImportPreview
    record = ConflictRecord(
        imported=incoming,
        existing=existing_full,
        resolution=ConflictResolution.MERGE,
    )
    preview = ImportPreview(clean=[], conflicts=[record])
    count = v.apply_import(preview)
    assert count == 1

    merged = v.load_account(existing.id)
    assert merged.id == existing.id
    assert merged.created_at == existing.created_at
    assert merged.label == "Updated Label"
    assert merged.password == "newpass"
    assert merged.notes == "now with notes"
    v.close()


def test_apply_import_skip(tmp_path):
    """SKIP leaves the existing account completely unchanged."""
    db = tmp_path / "v.db"
    v = Vault(db)
    v.initialize("pw")

    existing = Account(label="Keep Me", username="keepuser", password="keeppass")
    v.save_account(existing)
    original = v.load_account(existing.id)

    incoming = Account(label="Keep Me", username="keepuser", password="SHOULD_NOT_APPLY")
    from core.export_import import ConflictRecord, ConflictResolution, ImportPreview
    record = ConflictRecord(
        imported=incoming,
        existing=original,
        resolution=ConflictResolution.SKIP,
    )
    preview = ImportPreview(clean=[], conflicts=[record])
    count = v.apply_import(preview)
    assert count == 0

    unchanged = v.load_account(existing.id)
    assert unchanged.password == "keeppass"
    v.close()


def test_wrong_export_password_on_preview(tmp_path):
    db1 = tmp_path / "v1.db"
    v1 = Vault(db1)
    v1.initialize("pw")
    acc = _add_account_to_vault(v1, "A", "u", "p")
    bundle = v1.export_accounts([acc.id], "correct")
    v1.close()

    db2 = tmp_path / "v2.db"
    v2 = Vault(db2)
    v2.initialize("pw")
    with pytest.raises(WrongPasswordError):
        v2.preview_import(bundle, "wrong")
    v2.close()
