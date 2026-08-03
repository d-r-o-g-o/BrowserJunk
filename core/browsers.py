"""
browsers.py – Browser registry, detection, and populator dispatch.

Keeps Windows path knowledge and the chrome/edge/brave/firefox dispatch table
in one place so main.py stays thin.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from core.helpers import get_logger

logger = get_logger("browsers")


class DataCategory:
    HISTORY = "history"
    BOOKMARKS = "bookmarks"
    PASSWORDS = "passwords"
    COOKIES = "cookies"
    AUTOFILL = "autofill"
    ALL = {HISTORY, BOOKMARKS, PASSWORDS, COOKIES, AUTOFILL}


def _local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


def _roaming_appdata() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))


BROWSER_REGISTRY = {
    "chrome": {
        "name": "Google Chrome",
        "family": "chromium",
        "user_data_dir": lambda: _local_appdata() / "Google" / "Chrome" / "User Data",
    },
    "edge": {
        "name": "Microsoft Edge",
        "family": "chromium",
        "user_data_dir": lambda: _local_appdata() / "Microsoft" / "Edge" / "User Data",
    },
    "brave": {
        "name": "Brave",
        "family": "chromium",
        "user_data_dir": lambda: _local_appdata() / "BraveSoftware" / "Brave-Browser" / "User Data",
    },
    "firefox": {
        "name": "Mozilla Firefox",
        "family": "firefox",
        "user_data_dir": lambda: _roaming_appdata() / "Mozilla" / "Firefox",
    },
}


def detect_installed_browsers() -> set[str]:
    """Return the set of registry keys whose User Data root exists on disk."""
    found = set()
    for key, meta in BROWSER_REGISTRY.items():
        try:
            if meta["user_data_dir"]().exists():
                found.add(key)
        except Exception:
            continue
    return found


def build_populators(
    browser_keys: Optional[list[str]],
    personas: list,
    categories: Optional[set[str]],
    dry_run: bool,
    demo_profile: str,
    force_create: bool,
) -> list:
    """Resolve requested browsers into ready-to-run populator instances."""
    from core.chromium import ChromiumPopulator
    from core.firefox import FirefoxPopulator

    if browser_keys:
        keys = [k.lower() for k in browser_keys]
    elif force_create:
        keys = list(BROWSER_REGISTRY)
    else:
        keys = list(detect_installed_browsers())
    cats = categories or set(DataCategory.ALL)

    invalid = [k for k in keys if k not in BROWSER_REGISTRY]
    if invalid:
        raise ValueError(f"Unknown browser(s): {', '.join(invalid)}")

    detected = detect_installed_browsers()
    populators = []
    for key in keys:
        meta = BROWSER_REGISTRY[key]
        if key not in detected and not force_create:
            logger.warning(f"{meta['name']} not detected, skipping (use --force-create to override).")
            continue

        user_data_dir = meta["user_data_dir"]()
        if meta["family"] == "chromium":
            populators.append(ChromiumPopulator(
                key=key, name=meta["name"], user_data_dir=user_data_dir,
                personas=personas, categories=cats, dry_run=dry_run,
                demo_profile=demo_profile,
            ))
        else:
            populators.append(FirefoxPopulator(
                key=key, name=meta["name"], root_dir=user_data_dir,
                personas=personas, categories=cats, dry_run=dry_run,
                demo_profile=demo_profile,
            ))
    return populators
