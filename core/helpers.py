"""
helpers.py – Shared utilities: logging, timestamps, SQLite, filesystem, reporting.

This single module replaces the previous utils/ sub-package. Everything that
other modules import lives here.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# ──────────────────────────────────────────────────────────────────────────────
# Project paths  (auto-created on import)
# ──────────────────────────────────────────────────────────────────────────────

ROOT_DIR   = Path(__file__).resolve().parents[1]
LOG_DIR    = ROOT_DIR / "logs"
OUTPUT_DIR = ROOT_DIR / "output"

LOG_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# Rich console & logger
# ──────────────────────────────────────────────────────────────────────────────

_THEME = Theme({
    "info": "bold cyan", "warning": "bold yellow",
    "error": "bold red", "success": "bold green",
    "browser": "bold magenta",
})
console = Console(theme=_THEME)

_loggers: dict[str, logging.Logger] = {}


def get_logger(name: str = "populator") -> logging.Logger:
    """Return a named logger with Rich console + rotating file handler."""
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Console
    rh = RichHandler(
        console=console, rich_tracebacks=True, markup=True,
        show_path=False, log_time_format="[%H:%M:%S]",
    )
    rh.setLevel(logging.DEBUG)

    # File
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fh = logging.FileHandler(LOG_DIR / f"run_{ts}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    logger.addHandler(rh)
    logger.addHandler(fh)
    _loggers[name] = logger
    return logger


# ──────────────────────────────────────────────────────────────────────────────
# Chromium timestamp helpers  (µs since 1601-01-01 UTC)
# ──────────────────────────────────────────────────────────────────────────────

_CHROME_EPOCH_OFFSET_US = 11_644_473_600_000_000


def now_chrome_ts() -> int:
    return int(time.time() * 1_000_000) + _CHROME_EPOCH_OFFSET_US


def random_past_chrome_ts(days_back: int = 365) -> int:
    offset = random.randint(0, days_back * 86_400)
    return int((time.time() - offset) * 1_000_000) + _CHROME_EPOCH_OFFSET_US


# ──────────────────────────────────────────────────────────────────────────────
# Firefox timestamp helpers  (µs since Unix epoch)
# ──────────────────────────────────────────────────────────────────────────────

def firefox_now_us() -> int:
    return int(time.time() * 1_000_000)


def firefox_random_us(days_back: int = 365) -> int:
    offset = random.randint(0, days_back * 86_400)
    return int((time.time() - offset) * 1_000_000)


# ──────────────────────────────────────────────────────────────────────────────
# Generic time helpers
# ──────────────────────────────────────────────────────────────────────────────

def random_past_unix_s(days_back: int = 365) -> int:
    return int(time.time()) - random.randint(0, days_back * 86_400)


def url_hash(url: str) -> int:
    """Approximate Firefox moz_places.url_hash (lower 40 bits)."""
    sha = hashlib.sha256(url.encode()).digest()
    return int.from_bytes(sha[:8], "little") & 0x00FF_FFFF_FFFF


# ──────────────────────────────────────────────────────────────────────────────
# SQLite context manager
# ──────────────────────────────────────────────────────────────────────────────

class SafeDB:
    """Open an SQLite database safely with auto-commit/rollback."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.conn:
            self.conn.commit() if exc_type is None else self.conn.rollback()
            self.conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Filesystem helpers
# ──────────────────────────────────────────────────────────────────────────────

def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(f".bak_{ts}")
    shutil.copy2(path, bak)
    return bak


# ──────────────────────────────────────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────────────────────────────────────

def save_reports(results: dict, personas: list, browsers_run: list[str]) -> tuple[Path, Path]:
    """Generate JSON + HTML run reports. Returns (json_path, html_path)."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── JSON ──────────────────────────────────────────────────────────────
    report = {
        "generated_at": datetime.now().isoformat(),
        "browsers_targeted": browsers_run,
        "personas": [p.full_name for p in personas],
        "results": results,
    }
    json_path = OUTPUT_DIR / f"report_{ts}.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # ── HTML ──────────────────────────────────────────────────────────────
    rows = ""
    for profile, cats in results.items():
        for cat, count in sorted(cats.items()):
            clr = "#22c55e" if count > 0 else "#94a3b8"
            rows += (
                f"<tr><td>{profile}</td><td>{cat}</td>"
                f"<td style='color:{clr};font-weight:600'>{count}</td></tr>\n"
            )

    persona_rows = "".join(
        f"<tr><td>{p.full_name}</td><td>{p.email}</td>"
        f"<td>{len(p.passwords)} pw / {len(p.cards)} cards</td></tr>"
        for p in personas
    )

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>BrowserVault – Run Report</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:2rem}}
h1{{color:#818cf8}} h2{{color:#94a3b8;border-bottom:1px solid #1e293b;padding-bottom:.5rem}}
table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}
th{{background:#1e293b;color:#818cf8;padding:.6rem 1rem;text-align:left}}
td{{padding:.5rem 1rem;border-bottom:1px solid #1e293b}}
tr:hover td{{background:#1e293b}}
.meta{{color:#64748b;font-size:.85rem;margin-bottom:2rem}}
</style></head><body>
<h1>🛡 BrowserVault Demo Populator – Report</h1>
<p class="meta">Generated: {datetime.now():%Y-%m-%d %H:%M:%S} &middot; {", ".join(browsers_run)}</p>
<h2>Personas</h2>
<table><tr><th>Name</th><th>Email</th><th>Credentials</th></tr>{persona_rows}</table>
<h2>Results</h2>
<table><tr><th>Profile</th><th>Category</th><th>Items</th></tr>{rows}</table>
</body></html>"""

    html_path = OUTPUT_DIR / f"report_{ts}.html"
    html_path.write_text(html, encoding="utf-8")

    return json_path, html_path
