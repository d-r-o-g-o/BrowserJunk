"""
firefox.py – Populator for Mozilla Firefox. History/bookmarks/cookies/
autofill go straight into places.sqlite / cookies.sqlite / formhistory.sqlite.
Passwords go through core.nss.NSSSession so logins.json is encrypted with
the same key4.db a real Firefox install would create and read.
"""
from __future__ import annotations

import configparser
import json
import random
import sqlite3
import uuid
from pathlib import Path

from core.browsers import DataCategory
from core.helpers import ensure_dir, firefox_random_us, get_logger, url_hash

logger = get_logger("firefox")

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


class FirefoxPopulator:
    def __init__(self, key, name, root_dir: Path, personas, categories, dry_run, demo_profile):
        self.key = key
        self.name = name
        self.root_dir = root_dir
        self.personas = personas
        self.categories = categories
        self.dry_run = dry_run
        self.demo_profile = demo_profile

    def run(self) -> dict[str, dict[str, int]]:
        profile_name = f"{self.demo_profile}.default-release"
        profile_dir = self.root_dir / "Profiles" / profile_name
        label = f"{self.name} / {self.demo_profile}"

        if self.dry_run:
            logger.info(f"[dry-run] {self.name}: would create profile at {profile_dir}")
            return {label: {cat: self._estimate(cat) for cat in self.categories}}

        ensure_dir(profile_dir)
        self._register_profile(profile_name)

        counts: dict[str, int] = {}
        if DataCategory.HISTORY in self.categories or DataCategory.BOOKMARKS in self.categories:
            hist, marks = self._populate_places(profile_dir)
            if DataCategory.HISTORY in self.categories:
                counts[DataCategory.HISTORY] = hist
            if DataCategory.BOOKMARKS in self.categories:
                counts[DataCategory.BOOKMARKS] = marks
        if DataCategory.COOKIES in self.categories:
            counts[DataCategory.COOKIES] = self._populate_cookies(profile_dir)
        if DataCategory.AUTOFILL in self.categories:
            counts[DataCategory.AUTOFILL] = self._populate_form_history(profile_dir)
        if DataCategory.PASSWORDS in self.categories:
            counts[DataCategory.PASSWORDS] = self._populate_passwords(profile_dir)

        logger.info(f"{self.name}: populated profile at {profile_dir}")
        return {label: counts}

    def _estimate(self, cat: str) -> int:
        n = len(self.personas)
        if cat in (DataCategory.HISTORY, DataCategory.COOKIES):
            return n * len(_DEMO_SITES)
        if cat == DataCategory.BOOKMARKS:
            return n * (len(_DEMO_SITES) // 2)
        if cat == DataCategory.AUTOFILL:
            return n * 7
        if cat == DataCategory.PASSWORDS:
            return sum(len(p.passwords) for p in self.personas)
        return 0

    def _register_profile(self, profile_name: str) -> None:
        ini_path = self.root_dir / "profiles.ini"
        config = configparser.ConfigParser()
        if ini_path.exists():
            config.read(ini_path, encoding="utf-8")

        existing = {config[s].get("Path") for s in config.sections() if s.startswith("Profile")}
        if f"Profiles/{profile_name}" in existing:
            return

        idx = sum(1 for s in config.sections() if s.startswith("Profile"))
        config[f"Profile{idx}"] = {
            "Name": self.demo_profile, "IsRelative": "1", "Path": f"Profiles/{profile_name}",
        }
        if "General" not in config.sections():
            config["General"] = {"StartWithLastProfile": "1", "Version": "2"}

        ensure_dir(self.root_dir)
        with open(ini_path, "w", encoding="utf-8") as fh:
            config.write(fh, space_around_delimiters=False)

    def _populate_places(self, profile_dir: Path) -> tuple[int, int]:
        conn = sqlite3.connect(str(profile_dir / "places.sqlite"))
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS moz_places(
                    id INTEGER PRIMARY KEY, url LONGVARCHAR, title LONGVARCHAR,
                    rev_host LONGVARCHAR, visit_count INTEGER DEFAULT 0,
                    hidden INTEGER DEFAULT 0 NOT NULL, typed INTEGER DEFAULT 0 NOT NULL,
                    frecency INTEGER DEFAULT -1 NOT NULL, last_visit_date INTEGER,
                    guid TEXT UNIQUE, foreign_count INTEGER DEFAULT 0 NOT NULL,
                    url_hash INTEGER DEFAULT 0 NOT NULL
                );
                CREATE TABLE IF NOT EXISTS moz_historyvisits(
                    id INTEGER PRIMARY KEY, from_visit INTEGER, place_id INTEGER,
                    visit_date INTEGER, visit_type INTEGER, session INTEGER
                );
                CREATE TABLE IF NOT EXISTS moz_bookmarks(
                    id INTEGER PRIMARY KEY, type INTEGER, fk INTEGER, parent INTEGER,
                    position INTEGER, title LONGVARCHAR, dateAdded INTEGER,
                    lastModified INTEGER, guid TEXT UNIQUE
                );
                """
            )
            hist_count = 0
            mark_count = 0
            for _persona in self.personas:
                bookmarked = {u for u, _t in random.sample(_DEMO_SITES, len(_DEMO_SITES) // 2)}
                for url, title in _DEMO_SITES:
                    host = url.split("//", 1)[1].split("/", 1)[0]
                    rev_host = "." + host[::-1] + "."
                    visits = random.randint(1, 6)
                    cur = conn.execute(
                        "INSERT INTO moz_places (url, title, rev_host, visit_count, last_visit_date, guid, url_hash) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (url, title, rev_host, visits, firefox_random_us(1), uuid.uuid4().hex[:12], url_hash(url)),
                    )
                    place_id = cur.lastrowid
                    for _v in range(visits):
                        conn.execute(
                            "INSERT INTO moz_historyvisits (place_id, visit_date, visit_type, session) "
                            "VALUES (?, ?, 1, 0)",
                            (place_id, firefox_random_us(365)),
                        )
                    hist_count += 1
                    if url in bookmarked:
                        conn.execute(
                            "INSERT INTO moz_bookmarks (type, fk, parent, position, title, dateAdded, lastModified, guid) "
                            "VALUES (1, ?, 1, ?, ?, ?, ?, ?)",
                            (place_id, mark_count, title, firefox_random_us(1), firefox_random_us(1), uuid.uuid4().hex[:12]),
                        )
                        mark_count += 1
            conn.commit()
            return hist_count, mark_count
        finally:
            conn.close()

    def _populate_cookies(self, profile_dir: Path) -> int:
        conn = sqlite3.connect(str(profile_dir / "cookies.sqlite"))
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS moz_cookies(
                    id INTEGER PRIMARY KEY, originAttributes TEXT NOT NULL DEFAULT '',
                    name TEXT, value TEXT, host TEXT, path TEXT, expiry INTEGER,
                    lastAccessed INTEGER, creationTime INTEGER, isSecure INTEGER,
                    isHttpOnly INTEGER, sameSite INTEGER DEFAULT 0,
                    UNIQUE (name, host, path, originAttributes)
                );
                """
            )
            count = 0
            for url, _title in _DEMO_SITES:
                host = url.split("//", 1)[1].split("/", 1)[0]
                now = firefox_random_us(0)
                conn.execute(
                    "INSERT OR REPLACE INTO moz_cookies "
                    "(name, value, host, path, expiry, lastAccessed, creationTime, isSecure, isHttpOnly) "
                    "VALUES ('session_id', ?, ?, '/', ?, ?, ?, 1, 1)",
                    (f"demo_session_{uuid.uuid4().hex[:16]}", host, int(now / 1_000_000) + 30 * 86_400, now, now),
                )
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def _populate_form_history(self, profile_dir: Path) -> int:
        conn = sqlite3.connect(str(profile_dir / "formhistory.sqlite"))
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS moz_formhistory(
                    id INTEGER PRIMARY KEY, fieldname TEXT NOT NULL, value TEXT NOT NULL,
                    timesUsed INTEGER, firstUsed INTEGER, lastUsed INTEGER, guid TEXT
                );
                """
            )
            count = 0
            for persona in self.personas:
                fields = {
                    "email": persona.email, "name": persona.full_name,
                    "phone": persona.phone, "address": persona.address.street,
                    "city": persona.address.city, "zip": persona.address.zip_code,
                    "search": "demo query",
                }
                for field, value in fields.items():
                    now = firefox_random_us(0)
                    conn.execute(
                        "INSERT INTO moz_formhistory (fieldname, value, timesUsed, firstUsed, lastUsed, guid) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (field, value, random.randint(1, 5), firefox_random_us(365), now, uuid.uuid4().hex[:12]),
                    )
                    count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def _populate_passwords(self, profile_dir: Path) -> int:
        from core.nss import NSSSession

        try:
            session = NSSSession(profile_dir)
        except (RuntimeError, OSError) as exc:
            logger.warning(f"{self.name}: skipping passwords — {exc}")
            return 0

        entries = []
        next_id = 1
        with session:
            for persona in self.personas:
                for pw in persona.passwords:
                    now_ms = firefox_random_us(0) // 1000
                    entries.append({
                        "id": next_id,
                        "hostname": pw.signon_realm.rstrip("/"),
                        "httpRealm": None,
                        "formSubmitURL": pw.signon_realm.rstrip("/"),
                        "usernameField": "",
                        "passwordField": "",
                        "encryptedUsername": session.encrypt(pw.username),
                        "encryptedPassword": session.encrypt(pw.password),
                        "guid": "{" + str(uuid.uuid4()) + "}",
                        "encType": 1,
                        "timeCreated": now_ms,
                        "timeLastUsed": now_ms,
                        "timePasswordChanged": now_ms,
                        "timesUsed": random.randint(1, 5),
                    })
                    next_id += 1

        data = {
            "nextId": next_id,
            "logins": entries,
            "potentiallyVulnerablePasswords": [],
            "dismissedBridgedAccounts": [],
            "version": 3,
        }
        (profile_dir / "logins.json").write_text(json.dumps(data), encoding="utf-8")
        return len(entries)
