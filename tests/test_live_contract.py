"""Live contract — does Google still look the way our fixtures assume?

The rest of the suite runs offline against captured shapes. That proves the
code matches the fixtures — not that the fixtures match Google. (1.5.1's
full-month-name bug passed 600+ offline tests for three releases because every
fixture was written in May, the one month where ``%b`` and ``%B`` coincide.)

These tests hit the real feeds and assert only *format* facts we depend on:
"if Google gives us a timestamp string, we can parse it", "the Explore
envelope still carries the widgets we replay". They are:

* marked ``network`` — excluded from CI's ``-m "not network"`` runs, so a
  Google change or a rate-limited runner can never redden the Tests badge;
* marked ``contract`` — run weekly by ``.github/workflows/live-contract.yml``;
* runnable locally: ``pytest tests/test_live_contract.py -m contract -o addopts=""``.

A failure here means "Google drifted — look", not "the code is broken".
The Explore check reports *inconclusive* (skip) if the runner IP is
rate-limited, because that is Google's mood, not drift.
"""

from datetime import datetime

import pytest

from trendspyg import (
    download_google_trends_csv,
    download_google_trends_explore,
    download_google_trends_rss,
)
from trendspyg.exceptions import RateLimitError
from trendspyg.normalize import _parse_csv_datetime, normalize_csv, normalize_rss

pytestmark = [pytest.mark.network, pytest.mark.contract]

# Google's CSV export headers (verified live 2026-08-16). normalize_csv reads
# exactly these; a rename would silently empty every normalized field.
_CSV_HEADERS = {"Trends", "Search volume", "Started", "Ended", "Trend breakdown", "Explore link"}


class TestRssContract:
    def test_rss_feed_shape_and_timestamps(self):
        trends = download_google_trends_rss(geo="US", cache=False)
        assert isinstance(trends, list) and len(trends) >= 1, "RSS feed returned no trends"

        for t in trends:
            assert {"trend", "traffic", "traffic_min", "published", "explore_link"} <= set(t)
            assert isinstance(
                t["published"], datetime
            ), f"published not a datetime: {t['published']!r}"
            assert isinstance(t["traffic_min"], int)

        # traffic text still parses to a positive minimum on essentially every item
        parsed = sum(1 for t in trends if t["traffic_min"] > 0)
        assert parsed >= 0.9 * len(trends), f"traffic parsed on only {parsed}/{len(trends)}"

        env = normalize_rss(trends, "US")
        assert all(x["started_at"] for x in env["trends"]), "normalize_rss lost started_at"


class TestCsvContract:
    def test_csv_export_headers_and_timestamps_parse(self, tmp_path):
        rows = download_google_trends_csv(
            geo="US", hours=24, output_format="dict", download_dir=str(tmp_path)
        )
        assert isinstance(rows, list) and len(rows) >= 100, f"CSV returned {len(rows)} rows"
        assert _CSV_HEADERS <= set(rows[0]), f"CSV headers changed: {sorted(rows[0])}"

        started = [r["Started"] for r in rows if isinstance(r.get("Started"), str)]
        ended = [r["Ended"] for r in rows if isinstance(r.get("Ended"), str)]
        assert len(started) >= 100, "Started column is empty — export shape changed?"

        # THE contract: every timestamp string Google emits must parse.
        bad_started = [s for s in started if _parse_csv_datetime(s) is None]
        bad_ended = [s for s in ended if _parse_csv_datetime(s) is None]
        assert (
            not bad_started
        ), f"{len(bad_started)}/{len(started)} Started unparsed, e.g. {bad_started[:2]!r}"
        assert (
            not bad_ended
        ), f"{len(bad_ended)}/{len(ended)} Ended unparsed, e.g. {bad_ended[:2]!r}"

        # And the normalized schema must reflect that, end to end.
        env = normalize_csv(rows, "US")
        assert sum(1 for x in env["trends"] if x["started_at"]) == len(started)
        assert sum(1 for x in env["trends"] if x["ended_at"]) == len(ended)
        assert sum(1 for x in env["trends"] if not x["is_active"]) == len(ended)


class TestExploreContract:
    def test_explore_envelope_widgets_still_replay(self):
        # One browser session, three widgets — the whole Explore contract in one hit.
        try:
            env = download_google_trends_explore(
                "bitcoin", geo="US", timeframe="today 12-m", max_retries=3, retry_wait=6.0
            )
        except RateLimitError as exc:
            pytest.skip(f"Explore inconclusive — Google rate-limited this IP: {str(exc)[:80]}")

        series = env["interest_over_time"]
        assert len(series) >= 40, f"12-month series has {len(series)} points (expect ~53 weekly)"
        for p in series:
            assert set(p) >= {"date", "value", "is_partial"}
            assert 0 <= p["value"] <= 100
            datetime.fromisoformat(p["date"])  # ISO 8601 or raise
        assert series[0]["date"] < series[-1]["date"], "series not chronological"

        related = env["related_queries"]
        assert isinstance(related.get("top"), list) and isinstance(related.get("rising"), list)
        assert related["top"], "related queries TOP list is empty for 'bitcoin'"

        regions = env["interest_by_region"]
        assert len(regions) >= 40, f"US interest_by_region has {len(regions)} rows (expect ~51)"
        assert {"geo_code", "geo_name", "value"} <= set(regions[0])
