"""The Explore session cookie jar — make each browser session a returning visitor.

Why this exists (measured 2026-08-19): once an IP has been busy, Google refuses
*new* Explore visitors outright — the hard 429 page on the very first request,
headed or headless, whatever the driver — while a session that carries an
established set of Google cookies (chiefly ``NID``) is still served. Every
trendspyg session starts from a fresh Chrome profile, so without help every
session is a new visitor. With ``cookies="disk"`` the cookies Google issued to
one successful session are saved to a small JSON file and injected into the
next one, so trendspyg looks like one regular instead of a parade of strangers.

Design choices:
- A cookie file, not a Chrome profile directory: no profile locking, so
  concurrent sessions are fine (last successful writer wins); trivial to wipe.
- Only ``google.com`` / ``trends.google.com`` cookies are kept.
- Written atomically (temp file + ``os.replace``) and, where the OS supports
  it, readable by the owner only.
- Opt-in. Storing a Google cookie on disk is a choice the user makes.
- Best-effort everywhere: a missing, corrupt or rejected jar never fails a
  fetch — the session just proceeds as a new visitor.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import WebDriverException

from ..archive import _default_db_path

_KEPT_DOMAIN_SUFFIX = "google.com"
_COOKIE_FIELDS = ("name", "value", "domain", "path", "secure", "httpOnly", "expiry")


def _default_cookie_path() -> str:
    """``TRENDSPYG_COOKIES`` env var, else ``explore_cookies.json`` beside the archive DB."""
    env = os.environ.get("TRENDSPYG_COOKIES")
    if env:
        return env
    return os.path.join(os.path.dirname(_default_db_path()), "explore_cookies.json")


def _load_cookies(path: str) -> List[Dict[str, Any]]:
    """Read the jar; ``[]`` if it is missing, unreadable or not a list of dicts."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [c for c in data if isinstance(c, dict) and "name" in c and "value" in c]


def _save_cookies(driver: webdriver.Chrome, path: str) -> int:
    """Persist the session's Google cookies atomically; return how many were written."""
    try:
        raw = driver.get_cookies()
    except WebDriverException:
        return 0
    kept = [
        {k: c[k] for k in _COOKIE_FIELDS if k in c}
        for c in raw
        if str(c.get("domain", "")).lstrip(".").endswith(_KEPT_DOMAIN_SUFFIX)
    ]
    if not kept:
        return 0
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".explore_cookies-", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(kept, fh)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass  # not supported everywhere (Windows) — best-effort
        os.replace(tmp, path)
    except OSError:
        return 0
    return len(kept)


def _inject_cookies(driver: webdriver.Chrome, cookies: List[Dict[str, Any]]) -> int:
    """Add each saved cookie to the live session (must already be on a Google page).

    Returns how many were accepted; a cookie the driver rejects is skipped.
    """
    added = 0
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
            added += 1
        except (WebDriverException, KeyError, TypeError, ValueError):
            continue
    return added


def _forget_cookies(path: Optional[str] = None) -> bool:
    """Delete the jar. Returns True if a file was removed."""
    target = path or _default_cookie_path()
    try:
        os.remove(target)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
