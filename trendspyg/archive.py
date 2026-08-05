"""Historical archive + disk-backed cache — the SQLite storage layer.

Google's "Trending Now" data is ephemeral: once a trend drops off the feed, no
one — including Google — can tell you what was trending at that moment. This
module records normalized snapshots to a single SQLite file on the user's own
machine so a history accumulates as trendspyg is used. The same file also
persists the RSS response cache across processes, so CLI invocations and MCP
server restarts stop re-fetching what was just fetched.

Storage is one file (default: the platform data directory, override with the
``TRENDSPYG_DB`` env var or a ``db_path=`` argument). SQLite is embedded — no
server, no service, no new dependencies.

Layout (``db_schema_version`` 1):

* ``snapshots``/``trends`` — the archive: full normalized envelopes verbatim
  (``payload_json``) plus flattened per-keyword rows for indexed queries.
* ``cache`` — the disk cache: the same raw payloads the in-memory TTLCache
  holds, keyed identically, with datetimes round-tripped exactly.

Failure policy: WRITE failures never break a download (callers warn and carry
on); READ failures raise :class:`~trendspyg.exceptions.ArchiveError`.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from .exceptions import ArchiveError, InvalidParameterError

#: Bumped when the on-disk table layout changes shape.
DB_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS snapshots (
    id             INTEGER PRIMARY KEY,
    source         TEXT NOT NULL,
    geo            TEXT NOT NULL,
    fetched_at     TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    trend_count    INTEGER NOT NULL,
    payload_json   TEXT NOT NULL,
    UNIQUE(source, geo, fetched_at)
);
CREATE TABLE IF NOT EXISTS trends (
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    keyword     TEXT NOT NULL,
    rank        INTEGER,
    volume_min  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_snapshots_geo_time ON snapshots(geo, fetched_at);
CREATE INDEX IF NOT EXISTS idx_trends_keyword ON trends(keyword);
CREATE TABLE IF NOT EXISTS cache (
    key          TEXT PRIMARY KEY,
    stored_at    REAL NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def _default_db_path() -> str:
    """Resolve the archive path: ``TRENDSPYG_DB`` env var, else platform data dir."""
    env = os.environ.get("TRENDSPYG_DB")
    if env:
        return env
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    elif sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, "trendspyg", "trendspyg.db")


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open (creating on first touch) the archive DB with the designed pragmas.

    One connection per operation is the access pattern throughout this module:
    write rates are low, and the spike proved it safe for concurrent processes
    (WAL mode + busy_timeout).
    """
    path = db_path or _default_db_path()
    parent = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(path, timeout=8.0)
    except (OSError, sqlite3.Error) as exc:
        raise ArchiveError("Cannot open trends archive at '%s': %s" % (path, exc)) from exc
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 8000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _ensure_schema(conn, path)
        return conn
    except sqlite3.Error as exc:
        conn.close()
        raise ArchiveError(
            "'%s' is not a readable trendspyg archive (%s). If the file is "
            "corrupted, delete it and the archive will be recreated empty." % (path, exc)
        ) from exc
    except ArchiveError:
        conn.close()
        raise


def _ensure_schema(conn: sqlite3.Connection, path: str) -> None:
    """Create tables on first touch; refuse a DB written by a different layout."""
    conn.executescript(_SCHEMA)
    row = conn.execute("SELECT value FROM meta WHERE key = 'db_schema_version'").fetchone()
    if row is None:
        conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('db_schema_version', ?)",
            (str(DB_SCHEMA_VERSION),),
        )
        conn.commit()
    elif row[0] != str(DB_SCHEMA_VERSION):
        raise ArchiveError(
            "Archive at '%s' uses db schema version %s but this trendspyg "
            "supports version %s. Upgrade trendspyg, or point db_path/TRENDSPYG_DB "
            "at a different file." % (path, row[0], DB_SCHEMA_VERSION)
        )


def _encode_payload(obj: Any) -> str:
    """JSON-encode a raw payload, round-tripping datetimes exactly."""

    def _default(o: Any) -> Any:
        if isinstance(o, datetime):
            return {"__dt__": o.isoformat()}
        raise TypeError("Object of type %s is not JSON serializable" % type(o).__name__)

    return json.dumps(obj, default=_default)


def _decode_payload(text: str) -> Any:
    """Inverse of :func:`_encode_payload` — restores the exact in-memory shape."""

    def _hook(d: Dict[str, Any]) -> Any:
        if set(d) == {"__dt__"}:
            return datetime.fromisoformat(d["__dt__"])
        return d

    return json.loads(text, object_hook=_hook)


def _store_snapshot(envelope: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """Append one normalized envelope to the archive; returns its snapshot id.

    Duplicate (source, geo, fetched_at) inserts are ignored and return the
    existing row's id, so re-archiving the same envelope is harmless.
    """
    trends = envelope.get("trends") or []
    conn = _connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO snapshots"
                " (source, geo, fetched_at, schema_version, trend_count, payload_json)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    envelope["source"],
                    envelope["geo"],
                    envelope["fetched_at"],
                    str(envelope.get("schema_version", "")),
                    len(trends),
                    json.dumps(envelope),
                ),
            )
            if cur.rowcount == 0:  # already archived
                row = conn.execute(
                    "SELECT id FROM snapshots WHERE source = ? AND geo = ? AND fetched_at = ?",
                    (envelope["source"], envelope["geo"], envelope["fetched_at"]),
                ).fetchone()
                return int(row[0])
            snapshot_id = int(cur.lastrowid)  # type: ignore[arg-type]
            conn.executemany(
                "INSERT INTO trends (snapshot_id, keyword, rank, volume_min)"
                " VALUES (?, ?, ?, ?)",
                [
                    (snapshot_id, t.get("keyword", ""), t.get("rank"), t.get("volume_min"))
                    for t in trends
                ],
            )
            return snapshot_id
    finally:
        conn.close()


def _disk_cache_get(key: str, ttl: float, db_path: Optional[str] = None) -> Optional[Any]:
    """Return the cached payload for ``key`` if newer than ``ttl`` seconds, else None."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT payload_json FROM cache WHERE key = ? AND stored_at >= ?",
            (key, time.time() - ttl),
        ).fetchone()
        return _decode_payload(row[0]) if row is not None else None
    finally:
        conn.close()


def _disk_cache_set(key: str, payload: Any, ttl: float, db_path: Optional[str] = None) -> None:
    """Store ``payload`` under ``key`` and opportunistically drop stale entries."""
    conn = _connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, stored_at, payload_json) VALUES (?, ?, ?)",
                (key, time.time(), _encode_payload(payload)),
            )
            conn.execute("DELETE FROM cache WHERE stored_at < ?", (time.time() - ttl,))
    finally:
        conn.close()


def _store_snapshot_safely(envelope: Dict[str, Any], db_path: Optional[str] = None) -> None:
    """Archive hook for the download paths — a write failure never breaks a fetch."""
    try:
        _store_snapshot(envelope, db_path=db_path)
    except Exception as exc:  # deliberate blanket catch: this module's failure policy
        warnings.warn(
            "trendspyg archive write failed (%s); the download itself is unaffected" % exc,
            RuntimeWarning,
            stacklevel=3,
        )


def _disk_cache_get_safely(key: str, ttl: float, db_path: Optional[str] = None) -> Optional[Any]:
    """Disk-cache read hook — an unreadable cache is a miss, never an error."""
    try:
        return _disk_cache_get(key, ttl, db_path=db_path)
    except Exception as exc:  # deliberate blanket catch: this module's failure policy
        warnings.warn(
            "trendspyg disk cache read failed (%s); fetching fresh instead" % exc,
            RuntimeWarning,
            stacklevel=3,
        )
        return None


def _disk_cache_set_safely(
    key: str, payload: Any, ttl: float, db_path: Optional[str] = None
) -> None:
    """Disk-cache write hook — a write failure never breaks a fetch."""
    try:
        _disk_cache_set(key, payload, ttl, db_path=db_path)
    except Exception as exc:  # deliberate blanket catch: this module's failure policy
        warnings.warn(
            "trendspyg disk cache write failed (%s); the download itself is unaffected" % exc,
            RuntimeWarning,
            stacklevel=3,
        )


def _iso_arg(value: Union[str, datetime], name: str) -> str:
    """Accept a datetime or ISO 8601 string; return TEXT comparable to fetched_at."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise InvalidParameterError(
        "%s must be a datetime or a non-empty ISO 8601 string, got %r" % (name, value)
    )


def _snapshot_filters(
    geo: Optional[str],
    source: Optional[str],
    start: Optional[Union[str, datetime]],
    end: Optional[Union[str, datetime]],
) -> "tuple[List[str], List[Any]]":
    """Shared WHERE-clause builder for the archive read functions."""
    where: List[str] = []
    params: List[Any] = []
    if geo is not None:
        where.append("s.geo = ?")
        params.append(geo)
    if source is not None:
        where.append("s.source = ?")
        params.append(source)
    if start is not None:
        where.append("s.fetched_at >= ?")
        params.append(_iso_arg(start, "start"))
    if end is not None:
        where.append("s.fetched_at <= ?")
        params.append(_iso_arg(end, "end"))
    return where, params


def read_archive(
    geo: Optional[str] = None,
    source: Optional[str] = None,
    start: Optional[Union[str, datetime]] = None,
    end: Optional[Union[str, datetime]] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    output_format: str = "dict",
    db_path: Optional[str] = None,
) -> Any:
    """Read archived snapshots (newest first), optionally filtered.

    Args:
        geo: Only snapshots for this region code (exact match).
        source: Only this data path: ``"rss"`` or ``"csv"``.
        start: Only snapshots fetched at or after this time (datetime or ISO string).
        end: Only snapshots fetched at or before this time.
        keyword: Only snapshots that contain this keyword (case-insensitive).
        limit: At most this many snapshots (the newest ones).
        output_format: ``"dict"`` (list of envelopes), ``"json"`` (JSON string),
            or ``"dataframe"`` (one row per trend, needs the ``[analysis]`` extra).
        db_path: Archive file to read (default: TRENDSPYG_DB or the platform data dir).

    Returns:
        The archived envelopes, newest first, in the requested format. An
        archive that does not exist yet reads as empty.

    Raises:
        InvalidParameterError: On an unknown ``output_format`` or bad ``start``/``end``.
        ArchiveError: If the archive file cannot be read.
        ImportError: If pandas is missing for ``"dataframe"``.
    """
    if output_format not in ("dict", "json", "dataframe"):
        raise InvalidParameterError(
            "Invalid output_format: '%s'. Valid options: dict, json, dataframe" % output_format
        )

    where, params = _snapshot_filters(geo, source, start, end)
    if keyword is not None:
        where.append(
            "EXISTS (SELECT 1 FROM trends t WHERE t.snapshot_id = s.id"
            " AND t.keyword = ? COLLATE NOCASE)"
        )
        params.append(keyword)

    sql = "SELECT s.payload_json FROM snapshots s"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.fetched_at DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))

    conn = _connect(db_path)
    try:
        envelopes = [json.loads(row[0]) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    if output_format == "json":
        return json.dumps(envelopes, indent=2)
    if output_format == "dataframe":
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for 'dataframe' format.\n"
                "Install with: pip install trendspyg[analysis]"
            )
        rows = []
        for env in envelopes:
            for trend in env.get("trends", []):
                rows.append(
                    {
                        "fetched_at": env.get("fetched_at"),
                        "geo": env.get("geo"),
                        "source": env.get("source"),
                        "keyword": trend.get("keyword"),
                        "rank": trend.get("rank"),
                        "volume_min": trend.get("volume_min"),
                        "volume_text": trend.get("volume_text"),
                    }
                )
        return pd.DataFrame(rows)
    return envelopes


def get_keyword_history(
    keyword: str,
    geo: Optional[str] = None,
    start: Optional[Union[str, datetime]] = None,
    end: Optional[Union[str, datetime]] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Every archived appearance of a keyword, oldest first.

    Answers "when did X first trend, and how did it move?" straight from the
    indexed ``trends`` table — no envelopes are loaded.

    Args:
        keyword: The keyword to look up (case-insensitive, exact match).
        geo: Only appearances in this region code.
        start: Only appearances at or after this time (datetime or ISO string).
        end: Only appearances at or before this time.
        db_path: Archive file to read.

    Returns:
        ``[{"fetched_at", "geo", "source", "rank", "volume_min"}, ...]``
        ordered oldest first; empty list if the keyword never appeared.

    Raises:
        InvalidParameterError: On an empty keyword or bad ``start``/``end``.
        ArchiveError: If the archive file cannot be read.
    """
    if not isinstance(keyword, str) or not keyword.strip():
        raise InvalidParameterError("keyword must be a non-empty string, got %r" % (keyword,))

    where, params = _snapshot_filters(geo, None, start, end)
    where.insert(0, "t.keyword = ? COLLATE NOCASE")
    params.insert(0, keyword.strip())

    sql = (
        "SELECT s.fetched_at, s.geo, s.source, t.rank, t.volume_min"
        " FROM trends t JOIN snapshots s ON s.id = t.snapshot_id"
        " WHERE " + " AND ".join(where) + " ORDER BY s.fetched_at ASC"
    )
    conn = _connect(db_path)
    try:
        return [
            {
                "fetched_at": row["fetched_at"],
                "geo": row["geo"],
                "source": row["source"],
                "rank": row["rank"],
                "volume_min": row["volume_min"],
            }
            for row in conn.execute(sql, params).fetchall()
        ]
    finally:
        conn.close()


def get_archive_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Row counts, date range, geos/sources, file size and path of the archive.

    Returns:
        ``{"db_path", "db_size_bytes", "snapshot_count", "trend_row_count",
        "geos", "sources", "first_fetched_at", "last_fetched_at",
        "cache_entries"}`` — an archive that does not exist yet reads as empty.

    Raises:
        ArchiveError: If the archive file cannot be read.
    """
    path = db_path or _default_db_path()
    conn = _connect(path)
    try:
        snapshot_count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        trend_count = conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0]
        first, last = conn.execute(
            "SELECT MIN(fetched_at), MAX(fetched_at) FROM snapshots"
        ).fetchone()
        geos = [r[0] for r in conn.execute("SELECT DISTINCT geo FROM snapshots ORDER BY geo")]
        sources = [
            r[0] for r in conn.execute("SELECT DISTINCT source FROM snapshots ORDER BY source")
        ]
        cache_entries = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
    finally:
        conn.close()
    return {
        "db_path": os.path.abspath(path),
        "db_size_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
        "snapshot_count": snapshot_count,
        "trend_row_count": trend_count,
        "geos": geos,
        "sources": sources,
        "first_fetched_at": first,
        "last_fetched_at": last,
        "cache_entries": cache_entries,
    }


def prune_archive(
    before: Union[str, datetime],
    geo: Optional[str] = None,
    source: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    """Delete archived snapshots fetched before ``before``; returns the deleted count.

    Deleting is always explicit — nothing in the archive expires on its own.
    Trend rows of deleted snapshots are removed with them.

    Args:
        before: Cutoff (datetime or ISO string); snapshots strictly older go.
        geo: Only prune this region code.
        source: Only prune this data path.
        db_path: Archive file to prune.

    Raises:
        InvalidParameterError: If ``before`` is missing or not datetime/ISO string.
        ArchiveError: If the archive file cannot be read.
    """
    cutoff = _iso_arg(before, "before")
    where = ["fetched_at < ?"]
    params: List[Any] = [cutoff]
    if geo is not None:
        where.append("geo = ?")
        params.append(geo)
    if source is not None:
        where.append("source = ?")
        params.append(source)

    conn = _connect(db_path)
    try:
        with conn:
            cur = conn.execute("DELETE FROM snapshots WHERE " + " AND ".join(where), params)
            return int(cur.rowcount)
    finally:
        conn.close()
