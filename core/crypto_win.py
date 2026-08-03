"""
crypto_win.py – Chromium "v10" OS-crypt key management and AES-256-GCM
value encryption, matching Chrome/Edge/Brave's Windows DPAPI scheme so
real browser builds can decrypt the data we write (Login Data passwords,
Web Data credit card numbers, Cookies encrypted_value).

Windows-only: imports pywin32 lazily so the module can still be imported
(e.g. for --list-browsers) on non-Windows dev machines.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

_DPAPI_KEY_PREFIX = b"DPAPI"
_V10_PREFIX = b"v10"
_AES_KEY_LEN = 32
_GCM_NONCE_LEN = 12


def _dpapi_protect(data: bytes) -> bytes:
    import win32crypt
    blob = win32crypt.CryptProtectData(data, None, None, None, None, 0)
    return blob


def _dpapi_unprotect(data: bytes) -> bytes:
    import win32crypt
    _, blob = win32crypt.CryptUnprotectData(data, None, None, None, 0)
    return blob


def get_or_create_os_crypt_key(user_data_dir: Path) -> bytes:
    """
    Read the raw AES key from an existing Local State, or mint a new one
    and persist it (DPAPI-wrapped) so it survives a real browser launch.
    """
    local_state_path = user_data_dir / "Local State"
    state = {}
    if local_state_path.exists():
        try:
            state = json.loads(local_state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}

    encrypted_key_b64 = state.get("os_crypt", {}).get("encrypted_key")
    if encrypted_key_b64:
        wrapped = base64.b64decode(encrypted_key_b64)
        if wrapped.startswith(_DPAPI_KEY_PREFIX):
            return _dpapi_unprotect(wrapped[len(_DPAPI_KEY_PREFIX):])

    raw_key = os.urandom(_AES_KEY_LEN)
    wrapped = _DPAPI_KEY_PREFIX + _dpapi_protect(raw_key)
    state.setdefault("os_crypt", {})["encrypted_key"] = base64.b64encode(wrapped).decode("ascii")
    state["os_crypt"].setdefault("audit_enabled", True)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    local_state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return raw_key


def encrypt_v10(key: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM encrypt, framed as Chromium's 'v10' blob: v10 || nonce || ct || tag."""
    from Crypto.Cipher import AES
    nonce = os.urandom(_GCM_NONCE_LEN)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return _V10_PREFIX + nonce + ciphertext + tag
