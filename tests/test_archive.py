"""Tests for the archive + disk-cache storage layer (archive.py).

Everything runs offline against tmp_path databases. Platform branches in
_default_db_path are exercised in EVERY cell via monkeypatch, so per-module
coverage stays identical across the CI matrix.
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone

import pytest

import trendspyg.archive as archive
from trendspyg.archive import (
    DB_SCHEMA_VERSION,
    _connect,
    _decode_payload,
    _default_db_path,
    _disk_cache_get,
    _disk_cache_set,
    _encode_payload,
    _store_snapshot,
    get_archive_stats,
    get_keyword_history,
    prune_archive,
    read_archive,
)
from trendspyg.exceptions import ArchiveError, InvalidParameterError


def make_envelope(geo="US", source="rss", fetched_at="2026-08-05T09:00:00+00:00", keywords=None):
    keywords = keywords if keywords is not None else ["bitcoin", "solar eclipse"]
    trends = [
        {
            "keyword": kw,
            "rank": i + 1,
            "volume_text": "500K+",
            "volume_min": 500000,
            "started_at": None,
            "ended_at": None,
            "is_active": True,
            "related_queries": [],
            "news": [],
            "image": None,
            "explore_url": "",
        }
        for i, kw in enumerate(keywords)
    ]
    return {
        "schema_version": "1.0",
        "source": source,
        "geo": geo,
        "fetched_at": fetched_at,
        "count": len(trends),
        "trends": trends,
    }


class TestDefaultDbPath:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("TRENDSPYG_DB", r"X:\custom\my.db")
        assert _default_db_path() == r"X:\custom\my.db"

    def test_windows_uses_localappdata(self, monkeypatch):
        monkeypatch.delenv("TRENDSPYG_DB", raising=False)
        monkeypatch.setattr(archive.sys, "platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\t\AppData\Local")
        path = _default_db_path()
        assert path.startswith(r"C:\Users\t\AppData\Local")
        assert path.endswith("trendspyg.db")

    def test_windows_without_localappdata_falls_back_to_home(self, monkeypatch):
        monkeypatch.delenv("TRENDSPYG_DB", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.setattr(archive.sys, "platform", "win32")
        assert "AppData" in _default_db_path()

    def test_macos_path(self, monkeypatch):
        monkeypatch.delenv("TRENDSPYG_DB", raising=False)
        monkeypatch.setattr(archive.sys, "platform", "darwin")
        assert "Application Support" in _default_db_path()

    def test_linux_xdg_then_fallback(self, monkeypatch):
        monkeypatch.delenv("TRENDSPYG_DB", raising=False)
        monkeypatch.setattr(archive.sys, "platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", "/srv/data")
        assert _default_db_path().startswith("/srv/data")
        monkeypatch.delenv("XDG_DATA_HOME")
        assert ".local" in _default_db_path()


class TestConnect:
    def test_creates_file_and_parent_dirs(self, tmp_path):
        db = tmp_path / "deep" / "nested" / "trendspyg.db"
        conn = _connect(str(db))
        conn.close()
        assert db.exists()

    def test_wal_mode_and_schema_version_recorded(self, tmp_path):
        db = str(tmp_path / "a.db")
        conn = _connect(db)
        try:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            row = conn.execute("SELECT value FROM meta WHERE key='db_schema_version'").fetchone()
            assert row[0] == str(DB_SCHEMA_VERSION)
        finally:
            conn.close()

    def test_corrupt_file_raises_archive_error(self, tmp_path):
        db = tmp_path / "garbage.db"
        db.write_bytes(b"this is definitely not a sqlite database " * 30)
        with pytest.raises(ArchiveError) as exc_info:
            _connect(str(db))
        assert "not a readable trendspyg archive" in str(exc_info.value)

    def test_future_schema_version_raises_actionable_error(self, tmp_path):
        db = str(tmp_path / "future.db")
        conn = _connect(db)
        conn.execute("UPDATE meta SET value='999' WHERE key='db_schema_version'")
        conn.commit()
        conn.close()
        with pytest.raises(ArchiveError) as exc_info:
            _connect(db)
        assert "999" in str(exc_info.value)
        assert "Upgrade trendspyg" in str(exc_info.value)

    def test_unwritable_parent_raises_archive_error(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("x")
        # A path whose "parent directory" is a regular file cannot be created.
        with pytest.raises(ArchiveError) as exc_info:
            _connect(str(blocker / "sub" / "a.db"))
        assert "Cannot open trends archive" in str(exc_info.value)


class TestStoreSnapshot:
    def test_roundtrip_payload_verbatim_and_trend_rows(self, tmp_path):
        db = str(tmp_path / "a.db")
        env = make_envelope()

        sid = _store_snapshot(env, db_path=db)

        conn = _connect(db)
        try:
            snap = conn.execute("SELECT * FROM snapshots WHERE id=?", (sid,)).fetchone()
            assert json.loads(snap["payload_json"]) == env  # nothing lost, nothing changed
            assert snap["source"] == "rss"
            assert snap["geo"] == "US"
            assert snap["trend_count"] == 2
            rows = conn.execute(
                "SELECT keyword, rank, volume_min FROM trends WHERE snapshot_id=? ORDER BY rank",
                (sid,),
            ).fetchall()
            assert [tuple(r) for r in rows] == [
                ("bitcoin", 1, 500000),
                ("solar eclipse", 2, 500000),
            ]
        finally:
            conn.close()

    def test_duplicate_natural_key_is_ignored_and_returns_existing_id(self, tmp_path):
        db = str(tmp_path / "a.db")
        env = make_envelope()

        first = _store_snapshot(env, db_path=db)
        second = _store_snapshot(env, db_path=db)

        assert first == second
        conn = _connect(db)
        try:
            assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0] == 2
        finally:
            conn.close()

    def test_distinct_fetch_times_accumulate(self, tmp_path):
        db = str(tmp_path / "a.db")
        _store_snapshot(make_envelope(fetched_at="2026-08-05T09:00:00+00:00"), db_path=db)
        _store_snapshot(make_envelope(fetched_at="2026-08-05T10:00:00+00:00"), db_path=db)
        conn = _connect(db)
        try:
            assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 2
        finally:
            conn.close()


class TestPayloadCodec:
    def test_datetime_roundtrips_exactly(self):
        published = datetime(2026, 8, 5, 7, 30, tzinfo=timezone.utc)
        payload = [{"trend": "bitcoin", "published": published, "news_articles": []}]

        assert _decode_payload(_encode_payload(payload)) == payload

    def test_non_serializable_object_raises_type_error(self):
        with pytest.raises(TypeError):
            _encode_payload([{"bad": object()}])


class TestDiskCache:
    def test_miss_then_hit_returns_exact_payload(self, tmp_path):
        db = str(tmp_path / "a.db")
        payload = [{"trend": "bitcoin", "published": datetime(2026, 8, 5, tzinfo=timezone.utc)}]

        assert _disk_cache_get("rss:US", ttl=300, db_path=db) is None
        _disk_cache_set("rss:US", payload, ttl=300, db_path=db)
        assert _disk_cache_get("rss:US", ttl=300, db_path=db) == payload

    def test_expired_entry_is_a_miss(self, tmp_path, monkeypatch):
        db = str(tmp_path / "a.db")
        _disk_cache_set("rss:US", ["data"], ttl=300, db_path=db)

        real_time = archive.time.time()
        monkeypatch.setattr(archive.time, "time", lambda: real_time + 301)
        assert _disk_cache_get("rss:US", ttl=300, db_path=db) is None

    def test_set_prunes_stale_entries(self, tmp_path, monkeypatch):
        db = str(tmp_path / "a.db")
        _disk_cache_set("old", ["old"], ttl=300, db_path=db)

        real_time = archive.time.time()
        monkeypatch.setattr(archive.time, "time", lambda: real_time + 301)
        _disk_cache_set("new", ["new"], ttl=300, db_path=db)

        conn = _connect(db)
        try:
            keys = [r[0] for r in conn.execute("SELECT key FROM cache").fetchall()]
        finally:
            conn.close()
        assert keys == ["new"]

    def test_keys_are_isolated(self, tmp_path):
        db = str(tmp_path / "a.db")
        _disk_cache_set("rss:US", ["us"], ttl=300, db_path=db)
        assert _disk_cache_get("rss:GB", ttl=300, db_path=db) is None

    def test_set_overwrites_same_key(self, tmp_path):
        db = str(tmp_path / "a.db")
        _disk_cache_set("rss:US", ["one"], ttl=300, db_path=db)
        _disk_cache_set("rss:US", ["two"], ttl=300, db_path=db)
        assert _disk_cache_get("rss:US", ttl=300, db_path=db) == ["two"]


class TestArchiveAndCacheShareOneFile:
    def test_both_layers_coexist_in_one_db(self, tmp_path):
        db = str(tmp_path / "a.db")
        _store_snapshot(make_envelope(), db_path=db)
        _disk_cache_set("rss:US", ["raw"], ttl=300, db_path=db)

        conn = _connect(db)
        try:
            assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0] == 1
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            conn.close()


@pytest.fixture()
def populated_db(tmp_path):
    """Three US-rss snapshots across three hours, one GB-csv snapshot."""
    db = str(tmp_path / "arch.db")
    _store_snapshot(
        make_envelope(fetched_at="2026-08-05T09:00:00+00:00", keywords=["bitcoin", "cpap"]),
        db_path=db,
    )
    _store_snapshot(
        make_envelope(fetched_at="2026-08-05T10:00:00+00:00", keywords=["bitcoin"]),
        db_path=db,
    )
    _store_snapshot(
        make_envelope(fetched_at="2026-08-05T11:00:00+00:00", keywords=["solar eclipse"]),
        db_path=db,
    )
    _store_snapshot(
        make_envelope(
            geo="GB", source="csv", fetched_at="2026-08-05T09:30:00+00:00", keywords=["wimbledon"]
        ),
        db_path=db,
    )
    return db


class TestReadArchive:
    def test_fresh_archive_reads_empty(self, tmp_path):
        assert read_archive(db_path=str(tmp_path / "new.db")) == []

    def test_returns_full_envelopes_newest_first(self, populated_db):
        envelopes = read_archive(db_path=populated_db)

        assert len(envelopes) == 4
        assert [e["fetched_at"] for e in envelopes] == sorted(
            (e["fetched_at"] for e in envelopes), reverse=True
        )
        assert envelopes[0]["trends"][0]["keyword"] == "solar eclipse"

    def test_geo_and_source_filters(self, populated_db):
        assert len(read_archive(geo="US", db_path=populated_db)) == 3
        gb = read_archive(source="csv", db_path=populated_db)
        assert len(gb) == 1 and gb[0]["geo"] == "GB"

    def test_start_end_are_inclusive(self, populated_db):
        window = read_archive(
            geo="US",
            start="2026-08-05T09:00:00+00:00",
            end="2026-08-05T10:00:00+00:00",
            db_path=populated_db,
        )
        assert len(window) == 2

    def test_datetime_bounds_accepted(self, populated_db):
        result = read_archive(
            start=datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc), db_path=populated_db
        )
        assert len(result) == 1

    def test_keyword_filter_is_case_insensitive(self, populated_db):
        hits = read_archive(keyword="BITCOIN", db_path=populated_db)
        assert len(hits) == 2

    def test_limit_keeps_newest(self, populated_db):
        top = read_archive(geo="US", limit=1, db_path=populated_db)
        assert len(top) == 1
        assert top[0]["fetched_at"] == "2026-08-05T11:00:00+00:00"

    def test_json_format_round_trips(self, populated_db):
        text = read_archive(geo="GB", output_format="json", db_path=populated_db)
        assert isinstance(text, str)
        assert json.loads(text)[0]["geo"] == "GB"

    def test_invalid_output_format_rejected(self, populated_db):
        with pytest.raises(InvalidParameterError) as exc_info:
            read_archive(output_format="parquet", db_path=populated_db)
        assert "Invalid output_format: 'parquet'" in str(exc_info.value)

    def test_bad_start_rejected(self, populated_db):
        with pytest.raises(InvalidParameterError):
            read_archive(start="   ", db_path=populated_db)

    def test_dataframe_format_flattens_one_row_per_trend(self, populated_db):
        pd = pytest.importorskip("pandas")

        df = read_archive(output_format="dataframe", db_path=populated_db)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5  # 2 + 1 + 1 + 1 trends across the 4 snapshots
        assert list(df.columns) == [
            "fetched_at",
            "geo",
            "source",
            "keyword",
            "rank",
            "volume_min",
            "volume_text",
        ]

    def test_dataframe_without_pandas_raises_actionable_error(self, populated_db, monkeypatch):
        monkeypatch.setitem(sys.modules, "pandas", None)
        with pytest.raises(ImportError) as exc_info:
            read_archive(output_format="dataframe", db_path=populated_db)
        assert "trendspyg[analysis]" in str(exc_info.value)


class TestGetKeywordHistory:
    def test_oldest_first_with_all_fields(self, populated_db):
        history = get_keyword_history("bitcoin", db_path=populated_db)

        assert [h["fetched_at"] for h in history] == [
            "2026-08-05T09:00:00+00:00",
            "2026-08-05T10:00:00+00:00",
        ]
        assert history[0] == {
            "fetched_at": "2026-08-05T09:00:00+00:00",
            "geo": "US",
            "source": "rss",
            "rank": 1,
            "volume_min": 500000,
        }

    def test_case_insensitive_and_stripped(self, populated_db):
        assert len(get_keyword_history("  Bitcoin  ".strip(), db_path=populated_db)) == 2
        assert len(get_keyword_history("BITCOIN", db_path=populated_db)) == 2

    def test_geo_filter(self, populated_db):
        assert get_keyword_history("wimbledon", geo="US", db_path=populated_db) == []
        assert len(get_keyword_history("wimbledon", geo="GB", db_path=populated_db)) == 1

    def test_time_window(self, populated_db):
        later = get_keyword_history(
            "bitcoin", start="2026-08-05T09:30:00+00:00", db_path=populated_db
        )
        assert len(later) == 1

    def test_unknown_keyword_returns_empty(self, populated_db):
        assert get_keyword_history("never-trended", db_path=populated_db) == []

    def test_empty_keyword_rejected(self, populated_db):
        with pytest.raises(InvalidParameterError):
            get_keyword_history("   ", db_path=populated_db)


class TestGetArchiveStats:
    def test_fresh_archive_stats(self, tmp_path):
        db = str(tmp_path / "new.db")
        stats = get_archive_stats(db_path=db)

        assert stats["snapshot_count"] == 0
        assert stats["trend_row_count"] == 0
        assert stats["geos"] == [] and stats["sources"] == []
        assert stats["first_fetched_at"] is None and stats["last_fetched_at"] is None
        assert stats["cache_entries"] == 0
        assert stats["db_path"] == str(tmp_path / "new.db")
        assert stats["db_size_bytes"] > 0  # schema pages exist after first touch

    def test_populated_stats(self, populated_db):
        _disk_cache_set("rss:US", ["raw"], ttl=300, db_path=populated_db)

        stats = get_archive_stats(db_path=populated_db)

        assert stats["snapshot_count"] == 4
        assert stats["trend_row_count"] == 5
        assert stats["geos"] == ["GB", "US"]
        assert stats["sources"] == ["csv", "rss"]
        assert stats["first_fetched_at"] == "2026-08-05T09:00:00+00:00"
        assert stats["last_fetched_at"] == "2026-08-05T11:00:00+00:00"
        assert stats["cache_entries"] == 1


SAMPLE_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
  <channel>
    <item>
      <title>bitcoin</title>
      <ht:approx_traffic>500K+</ht:approx_traffic>
      <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
    </item>
    <item>
      <title>ethereum</title>
      <ht:approx_traffic>100K+</ht:approx_traffic>
      <pubDate>Mon, 01 Jan 2024 11:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""


def _mock_rss_response():
    from unittest.mock import MagicMock

    response = MagicMock()
    response.content = SAMPLE_RSS_XML
    response.raise_for_status = MagicMock()
    return response


@pytest.fixture(autouse=True)
def _clean_memory_cache():
    from trendspyg import clear_rss_cache

    clear_rss_cache()
    yield
    clear_rss_cache()


class TestRssArchiveHook:
    def test_archive_true_stores_snapshot_and_returns_raw_output(self, tmp_path):
        from unittest.mock import patch

        from trendspyg import download_google_trends_rss

        db = str(tmp_path / "a.db")
        with patch("trendspyg.rss_downloader.requests.get", return_value=_mock_rss_response()):
            result = download_google_trends_rss(geo="US", cache=False, archive=True, db_path=db)

        assert result[0]["trend"] == "bitcoin"  # returned output unchanged by archiving
        stored = read_archive(db_path=db)
        assert len(stored) == 1
        assert stored[0]["source"] == "rss" and stored[0]["geo"] == "US"
        assert [t["keyword"] for t in stored[0]["trends"]] == ["bitcoin", "ethereum"]

    def test_archive_with_normalize_stores_the_returned_envelope(self, tmp_path):
        from unittest.mock import patch

        from trendspyg import download_google_trends_rss

        db = str(tmp_path / "a.db")
        with patch("trendspyg.rss_downloader.requests.get", return_value=_mock_rss_response()):
            envelope = download_google_trends_rss(
                geo="US", cache=False, normalize=True, archive=True, db_path=db
            )

        assert read_archive(db_path=db)[0] == envelope  # one normalize call, same fetched_at

    def test_cache_hit_is_not_archived(self, tmp_path):
        from unittest.mock import patch

        from trendspyg import download_google_trends_rss

        db = str(tmp_path / "a.db")
        with patch("trendspyg.rss_downloader.requests.get", return_value=_mock_rss_response()):
            download_google_trends_rss(geo="US", cache=True)  # populate the memory cache
            download_google_trends_rss(geo="US", cache=True, archive=True, db_path=db)

        assert read_archive(db_path=db) == []  # served from cache -> no history row

    def test_archive_write_failure_warns_but_download_returns(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        from trendspyg import download_google_trends_rss

        def boom(envelope, db_path=None):
            raise RuntimeError("disk full")

        monkeypatch.setattr(archive, "_store_snapshot", boom)
        with patch("trendspyg.rss_downloader.requests.get", return_value=_mock_rss_response()):
            with pytest.warns(RuntimeWarning, match="archive write failed"):
                result = download_google_trends_rss(
                    geo="US", cache=False, archive=True, db_path=str(tmp_path / "a.db")
                )

        assert result[0]["trend"] == "bitcoin"

    def test_invalid_cache_string_rejected_before_any_fetch(self):
        from unittest.mock import patch

        from trendspyg import download_google_trends_rss

        with patch("trendspyg.rss_downloader.requests.get") as mock_get:
            with pytest.raises(InvalidParameterError) as exc_info:
                download_google_trends_rss(geo="US", cache="dsik")

        assert "Invalid cache: 'dsik'" in str(exc_info.value)
        mock_get.assert_not_called()


class TestRssDiskCache:
    def test_disk_hit_serves_across_process_boundary_simulation(self, tmp_path):
        from unittest.mock import patch

        from trendspyg import clear_rss_cache, download_google_trends_rss

        db = str(tmp_path / "a.db")
        with patch("trendspyg.rss_downloader.requests.get", return_value=_mock_rss_response()):
            fresh = download_google_trends_rss(geo="US", cache="disk", db_path=db)

        clear_rss_cache()  # a new process would start with an empty memory cache
        with patch("trendspyg.rss_downloader.requests.get") as mock_get:
            cached = download_google_trends_rss(geo="US", cache="disk", db_path=db)

        mock_get.assert_not_called()  # served from disk, no network
        assert cached == fresh  # exact shape, including the datetime 'published'
        assert isinstance(cached[0]["published"], datetime)

    def test_disk_read_failure_is_a_miss_not_an_error(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        from trendspyg import download_google_trends_rss

        def boom(key, ttl, db_path=None):
            raise RuntimeError("corrupt")

        monkeypatch.setattr(archive, "_disk_cache_get", boom)
        with patch("trendspyg.rss_downloader.requests.get", return_value=_mock_rss_response()):
            with pytest.warns(RuntimeWarning, match="disk cache read failed"):
                result = download_google_trends_rss(
                    geo="US", cache="disk", db_path=str(tmp_path / "a.db")
                )

        assert result[0]["trend"] == "bitcoin"  # fetched fresh instead

    def test_disk_entry_expires_after_ttl(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        from trendspyg import clear_rss_cache, download_google_trends_rss

        db = str(tmp_path / "a.db")
        with patch("trendspyg.rss_downloader.requests.get", return_value=_mock_rss_response()):
            download_google_trends_rss(geo="US", cache="disk", db_path=db)

        clear_rss_cache()
        real_time = archive.time.time()
        monkeypatch.setattr(archive.time, "time", lambda: real_time + 301)  # default TTL is 300
        with patch(
            "trendspyg.rss_downloader.requests.get", return_value=_mock_rss_response()
        ) as mock_get:
            download_google_trends_rss(geo="US", cache="disk", db_path=db)

        mock_get.assert_called_once()  # stale entry -> real fetch


class _FakeAioResponse:
    def __init__(self, content):
        self._content = content
        self.status = 200

    async def read(self):
        return self._content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeAioSession:
    def get(self, url, timeout=None):
        return _FakeAioResponse(SAMPLE_RSS_XML)


class TestAsyncArchiveHook:
    async def test_async_archive_stores_snapshot(self, tmp_path):
        from trendspyg import download_google_trends_rss_async

        db = str(tmp_path / "a.db")
        result = await download_google_trends_rss_async(
            geo="US", session=_FakeAioSession(), cache=False, archive=True, db_path=db
        )

        assert result[0]["trend"] == "bitcoin"
        stored = read_archive(db_path=db)
        assert len(stored) == 1 and stored[0]["source"] == "rss"

    async def test_async_disk_cache_round_trip(self, tmp_path):
        from trendspyg import clear_rss_cache, download_google_trends_rss_async

        db = str(tmp_path / "a.db")
        fresh = await download_google_trends_rss_async(
            geo="US", session=_FakeAioSession(), cache="disk", db_path=db
        )
        clear_rss_cache()

        class _ExplodingSession:
            def get(self, url, timeout=None):  # pragma: no cover - must never run
                raise AssertionError("disk hit expected; network was touched")

        cached = await download_google_trends_rss_async(
            geo="US", session=_ExplodingSession(), cache="disk", db_path=db
        )
        assert cached == fresh


class TestBatchArchiveHooks:
    def test_sync_batch_forwards_archive_args(self):
        from unittest.mock import patch

        from trendspyg import download_google_trends_rss_batch

        with patch(
            "trendspyg.rss_downloader.download_google_trends_rss", return_value=[]
        ) as mock_single:
            download_google_trends_rss_batch(
                ["US", "GB"], show_progress=False, archive=True, db_path="X"
            )

        assert mock_single.call_count == 2
        for call in mock_single.call_args_list:
            assert call.kwargs["archive"] is True
            assert call.kwargs["db_path"] == "X"

    async def test_async_batch_forwards_archive_args(self):
        from unittest.mock import AsyncMock, patch

        from trendspyg import download_google_trends_rss_batch_async

        with patch(
            "trendspyg.rss_downloader.download_google_trends_rss_async",
            new=AsyncMock(return_value=[]),
        ) as mock_single:
            await download_google_trends_rss_batch_async(
                ["US"], show_progress=False, archive=True, db_path="X"
            )

        assert mock_single.call_args.kwargs["archive"] is True
        assert mock_single.call_args.kwargs["db_path"] == "X"


class TestCsvArchiveHook:
    def _run_csv(self, tmp_path, **kwargs):
        from unittest.mock import MagicMock, patch

        from trendspyg import download_google_trends_csv

        pytest.importorskip("pandas")
        csv_file = tmp_path / "trends.csv"
        csv_file.write_text(
            "Trends,Search volume,Started,Ended,Trend breakdown,Explore link\n"
            'wimbledon,1M+,"May 21, 2026 at 5:50:00 PM UTC+3",,"tennis, finals",https://x\n'
        )
        with patch("trendspyg.downloader.webdriver.Chrome", return_value=MagicMock()):
            with patch("trendspyg.downloader._download_with_retry", return_value=str(csv_file)):
                return download_google_trends_csv(geo="GB", download_dir=str(tmp_path), **kwargs)

    def test_csv_archive_stores_normalized_snapshot(self, tmp_path):
        db = str(tmp_path / "a.db")

        result = self._run_csv(tmp_path, output_format="dict", archive=True, db_path=db)

        assert result[0]["Trends"] == "wimbledon"  # raw output unchanged
        stored = read_archive(db_path=db)
        assert len(stored) == 1
        assert stored[0]["source"] == "csv" and stored[0]["geo"] == "GB"
        assert stored[0]["trends"][0]["keyword"] == "wimbledon"
        assert stored[0]["trends"][0]["related_queries"] == ["tennis", "finals"]

    def test_csv_normalize_and_archive_store_same_envelope(self, tmp_path):
        db = str(tmp_path / "a.db")

        envelope = self._run_csv(tmp_path, normalize=True, archive=True, db_path=db)

        assert read_archive(db_path=db)[0] == envelope


class TestPruneArchive:
    def test_deletes_strictly_older_and_cascades(self, populated_db):
        deleted = prune_archive("2026-08-05T10:00:00+00:00", db_path=populated_db)

        assert deleted == 2  # 09:00 US and 09:30 GB; the 10:00 row is NOT strictly older
        remaining = read_archive(db_path=populated_db)
        assert len(remaining) == 2
        conn = _connect(populated_db)
        try:
            # cascade removed exactly the deleted snapshots' trend rows
            assert conn.execute("SELECT COUNT(*) FROM trends").fetchone()[0] == 2
        finally:
            conn.close()

    def test_geo_scoped_prune(self, populated_db):
        deleted = prune_archive("2026-08-06", geo="GB", db_path=populated_db)
        assert deleted == 1
        assert len(read_archive(db_path=populated_db)) == 3

    def test_datetime_cutoff_accepted(self, populated_db):
        deleted = prune_archive(datetime(2026, 8, 6, tzinfo=timezone.utc), db_path=populated_db)
        assert deleted == 4

    def test_missing_cutoff_rejected(self, populated_db):
        with pytest.raises(InvalidParameterError):
            prune_archive(None, db_path=populated_db)


def make_explore_envelope(keyword="bitcoin", geo="US", fetched_at="2026-08-11T10:00:00+00:00"):
    return {
        "schema_version": "1.0",
        "source": "explore",
        "keyword": keyword,
        "geo": geo,
        "timeframe": "today 12-m",
        "fetched_at": fetched_at,
        "count": 2,
        "interest_over_time": [
            {"date": "2026-08-01T00:00:00+00:00", "value": 40, "is_partial": False},
            {"date": "2026-08-08T00:00:00+00:00", "value": 55, "is_partial": True},
        ],
        "related_queries": {"top": [], "rising": []},
        "interest_by_region": [],
    }


def make_comparison_envelope(keywords=None, geo="US", fetched_at="2026-08-11T11:00:00+00:00"):
    keywords = keywords if keywords is not None else ["bitcoin", "ethereum"]
    return {
        "schema_version": "1.0",
        "source": "explore_comparison",
        "keywords": keywords,
        "geo": geo,
        "timeframe": "today 12-m",
        "fetched_at": fetched_at,
        "count": 1,
        "averages": {kw: 10 for kw in keywords},
        "interest_over_time": [
            {
                "date": "2026-08-08T00:00:00+00:00",
                "values": {kw: 10 for kw in keywords},
                "is_partial": True,
            }
        ],
        "interest_by_region": [],
    }


class TestExploreCache:
    """The explore_cache table: long-TTL entries, separate from the RSS cache."""

    def test_miss_then_hit_roundtrip(self, tmp_path):
        db = str(tmp_path / "a.db")
        entry = {"fetched_at": "2026-08-11T10:00:00+00:00", "data": {"interest_over_time": []}}

        assert archive._explore_cache_get("explore|bitcoin|US", ttl=86400, db_path=db) is None
        archive._explore_cache_set("explore|bitcoin|US", entry, db_path=db)
        assert archive._explore_cache_get("explore|bitcoin|US", ttl=86400, db_path=db) == entry

    def test_expired_entry_is_a_miss(self, tmp_path, monkeypatch):
        db = str(tmp_path / "a.db")
        archive._explore_cache_set("explore|bitcoin|US", {"data": 1}, db_path=db)

        real_time = archive.time.time()
        monkeypatch.setattr(archive.time, "time", lambda: real_time + 3601)
        assert archive._explore_cache_get("explore|bitcoin|US", ttl=3600, db_path=db) is None
        # the caller's ttl decides freshness at READ time — a longer ttl still hits
        assert archive._explore_cache_get("explore|bitcoin|US", ttl=7200, db_path=db) is not None

    def test_set_overwrites_same_key(self, tmp_path):
        db = str(tmp_path / "a.db")
        archive._explore_cache_set("k", {"data": "one"}, db_path=db)
        archive._explore_cache_set("k", {"data": "two"}, db_path=db)
        assert archive._explore_cache_get("k", ttl=3600, db_path=db) == {"data": "two"}

    def test_gc_drops_only_beyond_fixed_horizon(self, tmp_path, monkeypatch):
        db = str(tmp_path / "a.db")
        archive._explore_cache_set("abandoned", {"data": 1}, db_path=db)

        real_time = archive.time.time()
        # 29 days later: a write must KEEP the old key (inside the GC horizon)
        monkeypatch.setattr(archive.time, "time", lambda: real_time + 29 * 86400)
        archive._explore_cache_set("fresh", {"data": 2}, db_path=db)
        conn = _connect(db)
        try:
            keys = {r[0] for r in conn.execute("SELECT key FROM explore_cache").fetchall()}
        finally:
            conn.close()
        assert keys == {"abandoned", "fresh"}

        # 31 days later: the next write garbage-collects it
        monkeypatch.setattr(archive.time, "time", lambda: real_time + 31 * 86400)
        archive._explore_cache_set("fresh2", {"data": 3}, db_path=db)
        conn = _connect(db)
        try:
            keys = {r[0] for r in conn.execute("SELECT key FROM explore_cache").fetchall()}
        finally:
            conn.close()
        assert "abandoned" not in keys

    def test_rss_cache_write_does_not_purge_explore_entries(self, tmp_path, monkeypatch):
        """THE seam this design exists for: RSS writes prune by the RSS ttl
        (minutes) — an Explore entry hours old must survive them."""
        db = str(tmp_path / "a.db")
        archive._explore_cache_set("explore|bitcoin|US", {"data": 1}, db_path=db)

        real_time = archive.time.time()
        monkeypatch.setattr(archive.time, "time", lambda: real_time + 7200)  # 2h later
        _disk_cache_set("rss:US", ["fresh rss"], ttl=300, db_path=db)  # prunes cache > 300s

        assert archive._explore_cache_get("explore|bitcoin|US", ttl=86400, db_path=db) is not None

    def test_explore_write_does_not_purge_rss_entries(self, tmp_path):
        db = str(tmp_path / "a.db")
        _disk_cache_set("rss:US", ["rss"], ttl=300, db_path=db)
        archive._explore_cache_set("explore|bitcoin|US", {"data": 1}, db_path=db)
        assert _disk_cache_get("rss:US", ttl=300, db_path=db) == ["rss"]

    def test_read_failure_is_a_miss_not_an_error(self, tmp_path):
        garbage = tmp_path / "garbage.db"
        garbage.write_bytes(b"not a database " * 40)
        with pytest.warns(RuntimeWarning, match="disk cache read failed"):
            result = archive._explore_cache_get_safely("k", ttl=3600, db_path=str(garbage))
        assert result is None

    def test_write_failure_warns_not_raises(self, tmp_path):
        garbage = tmp_path / "garbage.db"
        garbage.write_bytes(b"not a database " * 40)
        with pytest.warns(RuntimeWarning, match="disk cache write failed"):
            archive._explore_cache_set_safely("k", {"data": 1}, db_path=str(garbage))

    def test_stats_count_explore_cache_entries(self, tmp_path):
        db = str(tmp_path / "a.db")
        archive._explore_cache_set("k1", {"data": 1}, db_path=db)
        archive._explore_cache_set("k2", {"data": 2}, db_path=db)
        stats = get_archive_stats(db_path=db)
        assert stats["explore_cache_entries"] == 2
        assert stats["cache_entries"] == 0


class TestExploreSnapshots:
    """Explore envelopes flow through the SAME snapshot write path as RSS/CSV."""

    def test_explore_envelope_roundtrips_and_indexes_its_keyword(self, tmp_path):
        db = str(tmp_path / "a.db")
        env = make_explore_envelope()
        _store_snapshot(env, db_path=db)

        stored = read_archive(source="explore", db_path=db)
        assert stored == [env]
        # the keyword filter sees it via the derived trends row
        assert read_archive(keyword="BITCOIN", db_path=db) == [env]

        hist = get_keyword_history("bitcoin", db_path=db)
        assert len(hist) == 1
        assert hist[0]["source"] == "explore"
        assert hist[0]["rank"] is None and hist[0]["volume_min"] is None

    def test_comparison_envelope_indexes_all_keywords(self, tmp_path):
        db = str(tmp_path / "a.db")
        _store_snapshot(make_comparison_envelope(["bitcoin", "ethereum"]), db_path=db)

        for kw in ("bitcoin", "ethereum"):
            hist = get_keyword_history(kw, db_path=db)
            assert len(hist) == 1
            assert hist[0]["source"] == "explore_comparison"

    def test_trend_count_is_keyword_row_count(self, tmp_path):
        db = str(tmp_path / "a.db")
        _store_snapshot(make_comparison_envelope(["a", "b", "c"]), db_path=db)
        conn = _connect(db)
        try:
            assert conn.execute("SELECT trend_count FROM snapshots").fetchone()[0] == 3
        finally:
            conn.close()

    def test_keyword_history_source_filter(self, tmp_path):
        db = str(tmp_path / "a.db")
        _store_snapshot(make_envelope(keywords=["bitcoin"]), db_path=db)
        _store_snapshot(make_explore_envelope(keyword="bitcoin"), db_path=db)

        assert len(get_keyword_history("bitcoin", db_path=db)) == 2
        rss_only = get_keyword_history("bitcoin", source="rss", db_path=db)
        assert [p["source"] for p in rss_only] == ["rss"]
        explore_only = get_keyword_history("bitcoin", source="explore", db_path=db)
        assert [p["source"] for p in explore_only] == ["explore"]
