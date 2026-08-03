# BrowserVault Demo Data Populator

Populates real Chrome / Edge / Brave / Firefox profiles with synthetic,
non-sensitive demo data — history, bookmarks, cookies, saved passwords,
autofill, and credit cards — for demos, QA, and training environments.

Data is written using each browser's actual on-disk format (real SQLite
schemas, real DPAPI/NSS encryption), so the resulting profile opens and
behaves like a normal browser profile — not a mockup.

**Platform:** Windows only (current release).

---

## Quick start

```
run.bat
```

That's it. One command:

1. Checks Python 3.10+ is installed.
2. Creates/reuses a local `.venv` and installs dependencies.
3. Creates `logs/` and `output/` if missing.
4. Runs the populator using `config.json` as defaults.
5. Prints a summary and saves a JSON + HTML run report to `output/`.

No manual venv setup, no running individual modules — `run.bat` is the
only thing you ever need to execute.

---

## What it does

For every targeted browser it creates a **brand-new profile** (never
overwrites an existing one — see [Repeated runs](#repeated-runs) below)
and populates:

| Category    | Chrome / Edge / Brave                          | Firefox                          |
|-------------|-------------------------------------------------|-----------------------------------|
| `history`   | `History` (urls + visits)                        | `places.sqlite`                   |
| `bookmarks` | `Bookmarks` (JSON)                               | `places.sqlite` (moz_bookmarks)   |
| `cookies`   | `Cookies` / `Network/Cookies` (DPAPI-encrypted)  | `cookies.sqlite` (plaintext, matches real Firefox behavior) |
| `passwords` | `Login Data` (DPAPI-encrypted via `crypto_win.py`) | `logins.json` (NSS-encrypted via real `nss3.dll`, see caveat below) |
| `autofill`  | `Web Data` (form fields + credit cards)           | `formhistory.sqlite`              |

Synthetic personas (name, email, phone, address, passwords, cards) are
generated with [Faker](https://faker.readthedocs.io/); credit card
numbers are Luhn-valid but not real cards.

### Firefox password caveat

Firefox encrypts saved logins with a key stored in `key4.db`, generated
by NSS. The tool talks to the **real `nss3.dll`** from your Firefox
install (`core/nss.py`) to produce a compatible `logins.json`. If
Firefox isn't installed (`nss3.dll` not found), password population is
skipped for Firefox with a warning in the log — history, bookmarks,
cookies, and autofill are unaffected.

---

## Usage

```
python main.py [OPTIONS]
```

| Option | Default (config.json) | Description |
|---|---|---|
| `-b, --browsers` | auto-detect | Target specific browsers. Repeatable: `-b chrome -b firefox`. Choices: `chrome`, `edge`, `brave`, `firefox`. |
| `-c, --categories` | all | Target specific data categories. Repeatable: `-c history -c passwords`. Choices: `history`, `bookmarks`, `cookies`, `passwords`, `autofill`. |
| `-n, --personas` | `2` | Number of synthetic personas to generate (1–10). |
| `-s, --seed` | random | Integer seed for reproducible personas/data. |
| `--profile-name` | `BVaultDemo` | Base profile name. A run timestamp is always appended (see below). |
| `--dry-run` | `false` | Log what would happen, write nothing. |
| `--force-create` | off | Create a browser's profile dir even if that browser isn't detected as installed. |
| `--list-browsers` | — | Show detection status for all supported browsers and exit. |
| `--no-report` | off | Skip writing the JSON/HTML run report. |
| `-h, --help` | — | Full option reference. |

Examples:

```
python main.py                              # auto-detect, all categories, config.json defaults
python main.py -b chrome -b firefox          # only Chrome + Firefox
python main.py -c history -c passwords       # only these two categories
python main.py -n 5 -s 42                    # 5 personas, reproducible
python main.py --dry-run                     # preview without writing
python main.py --list-browsers               # what's installed?
python main.py -b edge --force-create        # create an Edge profile even if Edge isn't detected
```

---

## Configuration

Everything the tool needs is in **`config.json`** — edit this one file,
no code changes needed:

```json
{
    "personas": 2,
    "seed": null,

    "profile_name": "BVaultDemo",

    "browsers": "auto",
    "categories": "all",

    "dry_run": false
}
```

- `"browsers": "auto"` → auto-detect installed browsers. Replace with a
  list (`["chrome", "firefox"]`) to always target specific ones.
- `"categories": "all"` → every category. Replace with a list
  (`["history", "bookmarks"]`) to restrict.
- Any CLI flag overrides its matching config value for that run.

---

## Repeated runs

Every run automatically appends a timestamp to the profile name
(`BVaultDemo_20260803_180944`), so running the tool twice creates **two
separate profiles** per browser instead of overwriting the first one.
Old demo profiles are never touched or deleted — clean them up manually
from each browser's `User Data` (or Firefox `Profiles`) folder if you no
longer need them.

---

## Finding the generated profile

New profiles are registered so the browser knows about them, but you
still need to **switch to them** — they won't show up in your everyday
browsing session:

**Chrome / Edge / Brave**
1. Fully close the browser first (check Task Manager for lingering
   `chrome.exe`/`msedge.exe`/`brave.exe` — a running instance will
   overwrite the profile registration on exit).
2. Reopen the browser → click the profile avatar (top-right) → the demo
   profile appears there, named after the first generated persona.
3. Or skip the picker and launch it directly:
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="BVaultDemo_20260803_180944"
   ```

**Firefox**
Launch the profile manager directly:
```
"C:\Program Files\Mozilla Firefox\firefox.exe" -P
```
Pick the demo profile from the list (registered in `profiles.ini`
automatically).

---

## Output

- **Logs:** `logs/run_<timestamp>.log` — full detail of every action taken.
- **Reports:** `output/report_<timestamp>.json` and `.html` — per-browser,
  per-category counts and the generated personas, for handing off as a
  run summary.

---

## Requirements

Installed automatically by `run.bat` into `.venv`:

- `click`, `rich`, `faker`
- `pycryptodome` (Chromium AES-GCM encryption)
- `pywin32` (Windows DPAPI access)

Python 3.10+, Windows only.

---

## Scope & intent

This tool writes only synthetic, generated-on-the-fly data (fake names,
fake emails, Luhn-valid but non-real card numbers). It's built for
demo/QA/training environments — populating throwaway profiles that look
realistic without using or exposing any real personal or financial data.
