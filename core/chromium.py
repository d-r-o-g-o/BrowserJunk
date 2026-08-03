"""
chromium.py – Populator for Chrome/Edge/Brave (all share the same on-disk
profile format). Writes real SQLite/JSON stores so a genuine browser
install opens the profile and decrypts passwords/cookies/cards normally.
"""
from __future__ import annotations

import json
import random
import sqlite3
import uuid
from pathlib import Path

from core.browsers import DataCategory
from core.crypto_win import encrypt_v10, get_or_create_os_crypt_key
from core.helpers import ensure_dir, get_logger, now_chrome_ts, random_past_chrome_ts

logger = get_logger("chromium")

_DEMO_SITES = [
    ("https://news.ycombinator.com/", "Hacker News"),
    ("https://en.wikipedia.org/wiki/Main_Page", "Wikipedia"),
    ("https://www.python.org/", "Python.org"),
    ("https://stackoverflow.com/", "Stack Overflow"),
    ("https://www.bbc.com/news", "BBC News"),
    ("https://www.nytimes.com/", "The New York Times"),
    ("https://github.com/", "GitHub"),
    ("https://www.reddit.com/", "Reddit"),
    ("https://www.youtube.com/", "YouTube"),
    ("https://weather.com/", "Weather.com"),
    ("https://www.linkedin.com/", "LinkedIn"),
    ("https://www.amazon.com/", "Amazon"),
    ("https://mail.google.com/", "Gmail"),
    ("https://docs.google.com/", "Google Docs"),
    ("https://www.spotify.com/", "Spotify"),
    ("https://www.netflix.com/", "Netflix"),
    ("https://www.twitch.tv/", "Twitch"),
    ("https://www.microsoft.com/", "Microsoft"),
]


class ChromiumPopulator:
    def __init__(self, key, name, user_data_dir: Path, personas, categories, dry_run, demo_profile):
        self.key = key
        self.name = name
        self.user_data_dir = user_data_dir
        self.personas = personas
        self.categories = categories
        self.dry_run = dry_run
        self.demo_profile = demo_profile

    def run(self) -> dict[str, dict[str, int]]:
        profile_dir = self.user_data_dir / self.demo_profile
        label = f"{self.name} / {self.demo_profile}"

        if self.dry_run:
            logger.info(f"[dry-run] {self.name}: would create profile at {profile_dir}")
            return {label: {cat: self._estimate(cat) for cat in self.categories}}

        ensure_dir(profile_dir)
        ensure_dir(profile_dir / "Network")
        self._write_preferences(profile_dir)
        self._register_in_profile_picker()

        raw_key = None
        if self.categories & {DataCategory.PASSWORDS, DataCategory.COOKIES, DataCategory.AUTOFILL}:
            raw_key = get_or_create_os_crypt_key(self.user_data_dir)

        counts: dict[str, int] = {}
        if DataCategory.HISTORY in self.categories:
            counts[DataCategory.HISTORY] = self._populate_history(profile_dir)
        if DataCategory.BOOKMARKS in self.categories:
            counts[DataCategory.BOOKMARKS] = self._populate_bookmarks(profile_dir)
        if DataCategory.COOKIES in self.categories:
            counts[DataCategory.COOKIES] = self._populate_cookies(profile_dir, raw_key)
        if DataCategory.PASSWORDS in self.categories:
            counts[DataCategory.PASSWORDS] = self._populate_passwords(profile_dir, raw_key)
        if DataCategory.AUTOFILL in self.categories:
            counts[DataCategory.AUTOFILL] = self._populate_autofill(profile_dir, raw_key)

        logger.info(f"{self.name}: populated profile at {profile_dir}")
        return {label: counts}

    def _estimate(self, cat: str) -> int:
        n = len(self.personas)
        if cat == DataCategory.HISTORY:
            return n * len(_DEMO_SITES)
        if cat == DataCategory.BOOKMARKS:
            return n * (len(_DEMO_SITES) // 2)
        if cat == DataCategory.COOKIES:
            return n * len(_DEMO_SITES)
        if cat == DataCategory.PASSWORDS:
            return sum(len(p.passwords) for p in self.personas)
        if cat == DataCategory.AUTOFILL:
            return sum(7 + len(p.cards) for p in self.personas)
        return 0

    def _register_in_profile_picker(self) -> None:
        """Add the demo profile to Local State's info_cache so it shows up
        in the browser's own profile-switcher menu (top-right avatar).
        Without this the browser has no idea the folder is a profile and
        opening the browser normally will just show the Default profile."""
        path = self.user_data_dir / "Local State"
        state = {}
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                state = {}

        display_name = self.personas[0].full_name if self.personas else self.demo_profile
        profile_block = state.setdefault("profile", {})
        info_cache = profile_block.setdefault("info_cache", {})
        info_cache[self.demo_profile] = {
            "name": display_name,
            "user_name": "",
            "is_using_default_avatar": True,
            "is_using_default_name": False,
            "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_0",
        }
        order = profile_block.setdefault("profiles_order", [])
        if self.demo_profile not in order:
            order.append(self.demo_profile)

        path.write_text(json.dumps(state), encoding="utf-8")

    def _write_preferences(self, profile_dir: Path) -> None:
        path = profile_dir / "Preferences"
        prefs = {}
        if path.exists():
            try:
                prefs = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                prefs = {}
        display_name = self.personas[0].full_name if self.personas else self.demo_profile
        prefs.setdefault("profile", {})["name"] = display_name
        path.write_text(json.dumps(prefs), encoding="utf-8")

    def _populate_history(self, profile_dir: Path) -> int:
        conn = sqlite3.connect(str(profile_dir / "History"))
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta(key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR);
                CREATE TABLE IF NOT EXISTS urls(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, url LONGVARCHAR, title LONGVARCHAR,
                    visit_count INTEGER DEFAULT 0 NOT NULL, typed_count INTEGER DEFAULT 0 NOT NULL,
                    last_visit_time INTEGER NOT NULL, hidden INTEGER DEFAULT 0 NOT NULL
                );
                CREATE TABLE IF NOT EXISTS visits(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, url INTEGER NOT NULL,
                    visit_time INTEGER NOT NULL, from_visit INTEGER,
                    transition INTEGER DEFAULT 0 NOT NULL, segment_id INTEGER,
                    visit_duration INTEGER DEFAULT 0 NOT NULL,
                    incremented_omnibox_typed_score BOOLEAN DEFAULT 0 NOT NULL,
                    opener_visit INTEGER
                );
                """
            )
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('version', '40')")
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('last_compatible_version', '16')")

            count = 0
            for _persona in self.personas:
                for url, title in _DEMO_SITES:
                    visits = random.randint(1, 6)
                    cur = conn.execute(
                        "INSERT INTO urls (url, title, visit_count, typed_count, last_visit_time, hidden) "
                        "VALUES (?, ?, ?, ?, ?, 0)",
                        (url, title, visits, random.randint(0, 2), now_chrome_ts()),
                    )
                    url_id = cur.lastrowid
                    for _v in range(visits):
                        conn.execute(
                            "INSERT INTO visits (url, visit_time, from_visit, transition) VALUES (?, ?, 0, ?)",
                            (url_id, random_past_chrome_ts(), 805306368),
                        )
                    count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def _populate_bookmarks(self, profile_dir: Path) -> int:
        chosen = random.sample(_DEMO_SITES, len(_DEMO_SITES) // 2)
        next_id = 3
        children = []
        for url, title in chosen:
            children.append({
                "date_added": str(now_chrome_ts()), "guid": str(uuid.uuid4()),
                "id": str(next_id), "name": title, "type": "url", "url": url,
            })
            next_id += 1

        data = {
            "checksum": "",
            "roots": {
                "bookmark_bar": {
                    "children": children, "date_added": str(now_chrome_ts()),
                    "date_modified": str(now_chrome_ts()), "id": "1",
                    "name": "Bookmarks bar", "type": "folder",
                },
                "other": {
                    "children": [], "date_added": str(now_chrome_ts()),
                    "date_modified": "0", "id": "2", "name": "Other bookmarks", "type": "folder",
                },
                "synced": {
                    "children": [], "date_added": str(now_chrome_ts()),
                    "date_modified": "0", "id": str(next_id), "name": "Mobile bookmarks", "type": "folder",
                },
            },
            "version": 1,
        }
        (profile_dir / "Bookmarks").write_text(json.dumps(data), encoding="utf-8")
        return len(chosen)

    def _populate_cookies(self, profile_dir: Path, raw_key: bytes) -> int:
        count = 0
        for db_path in (profile_dir / "Cookies", profile_dir / "Network" / "Cookies"):
            conn = sqlite3.connect(str(db_path))
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS meta(key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR);
                    CREATE TABLE IF NOT EXISTS cookies(
                        creation_utc INTEGER NOT NULL, host_key TEXT NOT NULL,
                        top_frame_site_key TEXT NOT NULL DEFAULT '', name TEXT NOT NULL,
                        value TEXT NOT NULL, encrypted_value BLOB DEFAULT '',
                        path TEXT NOT NULL, expires_utc INTEGER NOT NULL,
                        is_secure INTEGER NOT NULL, is_httponly INTEGER NOT NULL,
                        last_access_utc INTEGER NOT NULL, has_expires INTEGER NOT NULL DEFAULT 1,
                        is_persistent INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL DEFAULT 1,
                        samesite INTEGER NOT NULL DEFAULT -1, source_scheme INTEGER NOT NULL DEFAULT 0,
                        source_port INTEGER NOT NULL DEFAULT -1, last_update_utc INTEGER NOT NULL,
                        UNIQUE (host_key, top_frame_site_key, name, path)
                    );
                    """
                )
                conn.execute("INSERT OR IGNORE INTO meta VALUES ('version', '24')")
                conn.execute("INSERT OR IGNORE INTO meta VALUES ('last_compatible_version', '24')")

                for url, _title in _DEMO_SITES:
                    host = url.split("//", 1)[1].split("/", 1)[0]
                    enc = encrypt_v10(raw_key, f"demo_session_{uuid.uuid4().hex[:16]}".encode())
                    now = now_chrome_ts()
                    conn.execute(
                        "INSERT OR REPLACE INTO cookies "
                        "(creation_utc, host_key, name, value, encrypted_value, path, expires_utc, "
                        "is_secure, is_httponly, last_access_utc, last_update_utc) "
                        "VALUES (?, ?, 'session_id', '', ?, '/', ?, 1, 1, ?, ?)",
                        (now, host, enc, now + 30 * 86_400 * 1_000_000, now, now),
                    )
                    if db_path.name == "Cookies" and db_path.parent == profile_dir:
                        count += 1
                conn.commit()
            finally:
                conn.close()
        return count

    def _populate_passwords(self, profile_dir: Path, raw_key: bytes) -> int:
        conn = sqlite3.connect(str(profile_dir / "Login Data"))
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta(key VARCHAR NOT NULL UNIQUE PRIMARY KEY, value VARCHAR);
                CREATE TABLE IF NOT EXISTS logins(
                    origin_url VARCHAR NOT NULL, action_url VARCHAR,
                    username_element VARCHAR, username_value VARCHAR,
                    password_element VARCHAR, password_value BLOB,
                    submit_element VARCHAR, signon_realm VARCHAR NOT NULL,
                    date_created INTEGER NOT NULL, blacklisted_by_user INTEGER NOT NULL,
                    scheme INTEGER NOT NULL, password_type INTEGER, times_used INTEGER,
                    form_data BLOB, date_synced INTEGER, display_name VARCHAR,
                    icon_url VARCHAR, federation_url VARCHAR, skip_zero_click INTEGER,
                    generation_upload_status INTEGER,
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date_last_used INTEGER NOT NULL DEFAULT 0,
                    date_password_modified INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (origin_url, username_element, username_value, password_element, signon_realm)
                );
                """
            )
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('version', '35')")
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('last_compatible_version', '35')")

            count = 0
            now = now_chrome_ts()
            for persona in self.personas:
                for pw in persona.passwords:
                    enc = encrypt_v10(raw_key, pw.password.encode())
                    conn.execute(
                        "INSERT OR IGNORE INTO logins "
                        "(origin_url, action_url, username_element, username_value, password_element, "
                        "password_value, submit_element, signon_realm, date_created, blacklisted_by_user, "
                        "scheme, times_used, skip_zero_click, generation_upload_status, date_last_used, "
                        "date_password_modified) "
                        "VALUES (?, ?, '', ?, '', ?, '', ?, ?, 0, 0, 1, 1, 0, ?, ?)",
                        (pw.site_url, pw.site_url, pw.username, enc, pw.signon_realm, now, now, now),
                    )
                    count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def _populate_autofill(self, profile_dir: Path, raw_key: bytes) -> int:
        conn = sqlite3.connect(str(profile_dir / "Web Data"))
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta(key VARCHAR NOT NULL UNIQUE PRIMARY KEY, value VARCHAR);
                CREATE TABLE IF NOT EXISTS autofill(
                    name VARCHAR, value VARCHAR, value_lower VARCHAR,
                    date_created INTEGER DEFAULT 0, date_last_used INTEGER DEFAULT 0,
                    count INTEGER DEFAULT 1, PRIMARY KEY (name, value)
                );
                CREATE TABLE IF NOT EXISTS credit_cards(
                    guid VARCHAR PRIMARY KEY, name_on_card VARCHAR,
                    expiration_month INTEGER, expiration_year INTEGER,
                    card_number_encrypted BLOB, date_modified INTEGER NOT NULL DEFAULT 0,
                    origin VARCHAR DEFAULT '', use_count INTEGER NOT NULL DEFAULT 1,
                    use_date INTEGER NOT NULL DEFAULT 0, billing_address_id VARCHAR, nickname VARCHAR
                );
                """
            )
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('version', '92')")
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('last_compatible_version', '92')")

            count = 0
            now_s = int(now_chrome_ts() / 1_000_000)
            now = now_chrome_ts()
            for persona in self.personas:
                fields = {
                    "email": persona.email, "name": persona.full_name,
                    "phone": persona.phone, "address": persona.address.street,
                    "city": persona.address.city, "zip": persona.address.zip_code,
                    "search": "demo query",
                }
                for field, value in fields.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO autofill (name, value, value_lower, date_created, date_last_used, count) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (field, value, value.lower(), now_s, now_s, random.randint(1, 5)),
                    )
                    count += 1
                for card in persona.cards:
                    enc = encrypt_v10(raw_key, card.number.encode())
                    conn.execute(
                        "INSERT OR IGNORE INTO credit_cards "
                        "(guid, name_on_card, expiration_month, expiration_year, card_number_encrypted, "
                        "date_modified, use_count, use_date, nickname) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), card.cardholder_name, card.expiry_month, card.expiry_year,
                         enc, now, random.randint(1, 4), now, f"{card.card_type} demo"),
                    )
                    count += 1
            conn.commit()
            return count
        finally:
            conn.close()
