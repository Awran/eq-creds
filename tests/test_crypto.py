import pytest
from core.crypto import (
    account_aad,
    decrypt_field,
    derive_key,
    encrypt_field,
    new_salt,
)
from cryptography.exceptions import InvalidTag


def test_salt_length():
    salt = new_salt()
    assert len(salt) == 16


def test_derive_key_deterministic():
    salt = new_salt()
    k1 = derive_key("mypassword", salt)
    k2 = derive_key("mypassword", salt)
    assert k1 == k2
    assert len(k1) == 32


def test_derive_key_different_passwords():
    salt = new_salt()
    k1 = derive_key("password1", salt)
    k2 = derive_key("password2", salt)
    assert k1 != k2


def test_derive_key_different_salts():
    k1 = derive_key("password", new_salt())
    k2 = derive_key("password", new_salt())
    assert k1 != k2


def test_derive_key_empty_password_raises():
    with pytest.raises(ValueError):
        derive_key("", new_salt())


def test_encrypt_decrypt_roundtrip():
    key = derive_key("testpass", new_salt())
    aad = account_aad("acct-123")
    plaintext = "MySecretPassword!"
    ciphertext, nonce = encrypt_field(key, plaintext, aad)
    recovered = decrypt_field(key, ciphertext, nonce, aad)
    assert recovered == plaintext


def test_encrypt_produces_unique_nonces():
    key = derive_key("testpass", new_salt())
    aad = account_aad("acct-123")
    _, nonce1 = encrypt_field(key, "hello", aad)
    _, nonce2 = encrypt_field(key, "hello", aad)
    assert nonce1 != nonce2


def test_decrypt_wrong_key_raises():
    key1 = derive_key("pass1", new_salt())
    key2 = derive_key("pass2", new_salt())
    aad = account_aad("acct-xyz")
    ct, nonce = encrypt_field(key1, "secret", aad)
    with pytest.raises(InvalidTag):
        decrypt_field(key2, ct, nonce, aad)


def test_decrypt_wrong_aad_raises():
    key = derive_key("pass", new_salt())
    aad1 = account_aad("acct-1")
    aad2 = account_aad("acct-2")
    ct, nonce = encrypt_field(key, "secret", aad1)
    with pytest.raises(InvalidTag):
        decrypt_field(key, ct, nonce, aad2)


def test_decrypt_tampered_ciphertext_raises():
    key = derive_key("pass", new_salt())
    aad = account_aad("acct-test")
    ct, nonce = encrypt_field(key, "secret", aad)
    tampered = bytes([ct[0] ^ 0xFF]) + ct[1:]
    with pytest.raises(InvalidTag):
        decrypt_field(key, tampered, nonce, aad)


def test_empty_string_encrypt_decrypt():
    key = derive_key("pass", new_salt())
    aad = account_aad("acct-empty")
    ct, nonce = encrypt_field(key, "", aad)
    assert decrypt_field(key, ct, nonce, aad) == ""


def test_unicode_encrypt_decrypt():
    key = derive_key("pass", new_salt())
    aad = account_aad("acct-uni")
    plaintext = "pässwørd_🔐"
    ct, nonce = encrypt_field(key, plaintext, aad)
    assert decrypt_field(key, ct, nonce, aad) == plaintext
