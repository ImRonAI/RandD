"""Envelope encryption for property secrets (door codes, Wi-Fi passwords).

NFR (AGENTS.md): door codes and Wi-Fi passwords must be encrypted at rest.
Scheme: AES-256-GCM with a master key from ``STRQC_MASTER_KEY`` (base64, 32 bytes).
Ciphertext format (all base64, dot-separated): ``v1.<nonce>.<ciphertext+tag>``.

Plaintext values must never be logged or stored raw. The schema's
``*_ciphertext`` columns store the output of :func:`encrypt_secret`.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PREFIX = "v1"


class SecretCipherError(Exception):
    """Raised when encryption/decryption fails or the key is missing/invalid."""


def _load_key(master_key_b64: str) -> bytes:
    if not master_key_b64:
        raise SecretCipherError(
            "STRQC_MASTER_KEY is not set. Generate one with: "
            "python -c \"import os,base64;print(base64.b64encode(os.urandom(32)).decode())\""
        )
    try:
        key = base64.b64decode(master_key_b64)
    except Exception as exc:  # noqa: BLE001
        raise SecretCipherError("STRQC_MASTER_KEY is not valid base64") from exc
    if len(key) != 32:
        raise SecretCipherError("STRQC_MASTER_KEY must decode to exactly 32 bytes")
    return key


def encrypt_secret(plaintext: str, master_key_b64: str, *, aad: str = "") -> str:
    """Encrypt a secret value. ``aad`` binds ciphertext to a context (e.g. unit code)."""
    key = _load_key(master_key_b64)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8") or None)
    return ".".join(
        (_PREFIX, base64.b64encode(nonce).decode("ascii"), base64.b64encode(ct).decode("ascii"))
    )


def decrypt_secret(token: str, master_key_b64: str, *, aad: str = "") -> str:
    """Decrypt a value produced by :func:`encrypt_secret`."""
    key = _load_key(master_key_b64)
    try:
        version, nonce_b64, ct_b64 = token.split(".")
        if version != _PREFIX:
            raise ValueError(f"unsupported ciphertext version {version!r}")
        nonce = base64.b64decode(nonce_b64)
        ct = base64.b64decode(ct_b64)
        pt = AESGCM(key).decrypt(nonce, ct, aad.encode("utf-8") or None)
    except SecretCipherError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SecretCipherError("failed to decrypt secret (wrong key, AAD, or corrupt data)") from exc
    return pt.decode("utf-8")


def mask_secret(value: str | None) -> str:
    """Displayable mask — used by API/UI; never reveals length beyond a hint."""
    if not value:
        return ""
    return "••••" + value[-1] if len(value) > 4 else "••••"
