"""Tests for the envelope-encryption helpers."""

from __future__ import annotations

import base64
import os

import pytest

from strqc_shared.crypto import SecretCipherError, decrypt_secret, encrypt_secret, mask_secret

KEY = base64.b64encode(os.urandom(32)).decode()


def test_round_trip():
    token = encrypt_secret("1234#", KEY, aad="BBL-014")
    assert token.startswith("v1.")
    assert decrypt_secret(token, KEY, aad="BBL-014") == "1234#"


def test_wrong_aad_fails():
    token = encrypt_secret("hunter2", KEY, aad="BBL-014")
    with pytest.raises(SecretCipherError):
        decrypt_secret(token, KEY, aad="BBL-027")


def test_wrong_key_fails():
    other = base64.b64encode(os.urandom(32)).decode()
    token = encrypt_secret("hunter2", KEY)
    with pytest.raises(SecretCipherError):
        decrypt_secret(token, other)


def test_missing_key_message():
    with pytest.raises(SecretCipherError, match="STRQC_MASTER_KEY"):
        encrypt_secret("x", "")


def test_bad_key_length():
    short = base64.b64encode(b"short").decode()
    with pytest.raises(SecretCipherError):
        encrypt_secret("x", short)


def test_mask_never_reveals():
    assert mask_secret(None) == ""
    assert mask_secret("12") == "••••"
    assert mask_secret("123456") == "••••6"
