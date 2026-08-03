"""
nss.py – Encrypts Firefox login values through the real libnss3.dll so the
resulting logins.json matches what Firefox itself would have written
(same key4.db, same PK11SDR_Encrypt blob format).

Windows-only. ctypes bindings modeled on the well-known firefox_decrypt
approach, run in reverse (encrypt instead of decrypt).
"""
from __future__ import annotations

import base64
import ctypes
import os
from pathlib import Path
from typing import Optional


class SECItem(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint),
        ("data", ctypes.c_char_p),
        ("len", ctypes.c_uint),
    ]


def _find_nss_dir() -> Optional[Path]:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Mozilla Firefox",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Mozilla Firefox",
    ]
    for c in candidates:
        if (c / "nss3.dll").exists():
            return c
    return None


class NSSSession:
    """Open once per Firefox profile, encrypt N strings, then close()."""

    def __init__(self, profile_dir: Path):
        nss_dir = _find_nss_dir()
        if nss_dir is None:
            raise RuntimeError("nss3.dll not found; is Firefox installed?")

        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(nss_dir))
        # mozglue must load before nss3 on Windows.
        ctypes.CDLL(str(nss_dir / "mozglue.dll"))
        self._nss = ctypes.CDLL(str(nss_dir / "nss3.dll"))

        profile_dir.mkdir(parents=True, exist_ok=True)
        init_arg = f"sql:{profile_dir}".encode("utf-8")
        if self._nss.NSS_Init(init_arg) != 0:
            raise RuntimeError("NSS_Init failed")

        self._slot = self._nss.PK11_GetInternalKeySlot()
        if not self._slot:
            raise RuntimeError("PK11_GetInternalKeySlot failed")
        # Empty/no primary password -> authenticate succeeds immediately.
        self._nss.PK11_Authenticate(self._slot, True, None)

    def encrypt(self, plaintext: str) -> str:
        data_item = SECItem(0, plaintext.encode("utf-8"), len(plaintext.encode("utf-8")))
        result_item = SECItem(0, None, 0)
        rv = self._nss.PK11SDR_Encrypt(None, ctypes.byref(data_item), ctypes.byref(result_item), None)
        if rv != 0:
            raise RuntimeError("PK11SDR_Encrypt failed")
        raw = ctypes.string_at(result_item.data, result_item.len)
        self._nss.SECITEM_FreeItem(ctypes.byref(result_item), False)
        return base64.b64encode(raw).decode("ascii")

    def close(self) -> None:
        try:
            self._nss.PK11_FreeSlot(self._slot)
            self._nss.NSS_Shutdown()
        except Exception:
            pass

    def __enter__(self) -> "NSSSession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
