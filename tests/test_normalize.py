"""Tests for the normalization layer (normalize=True / NormalizedEnvelope).

All non-network — they exercise the pure transform functions with sample
raw dicts shaped exactly like the RSS and CSV paths produce.
"""
import json
from datetime import datetime, timezone

import pytest

from trendspyg.normalize import (
    SCHEMA_VERSION,
    _parse_csv_datetime,
    normalize_csv,
    normalize_rss,
)


class TestParseCsvDatetime:
    """Google's localized CSV timestamps -> ISO 8601."""

    def test_pm_timestamp(self):
        assert _parse_csv_datetime("May 21, 2026 at 5:50:00 PM UTC+3") == \
            "2026-05-21T17:50:00+03:00"

    def test_am_timestamp(self):
        assert _parse_csv_datetime("May 22, 2026 at 3:40:00 AM UTC+3") == \
            "2026-05-22T03:40:00+03:00"

    def test_narrow_no_break_space(self):
        """The real feed uses U+202F before AM/PM - must still parse."""
        raw = "May 21, 2026 at 5:50:00 PM UTC+3"
        assert _parse_csv_datetime(raw) == "2026-05-21T17:50:00+03:00"

    def test_negative_offset(self):
        assert _parse_csv_datetime("Jan 02, 2026 at 9:00:00 AM UTC-5") == \
            "2026-01-02T09:00:00-05:00"

    def test_half_hour_offset(self):
        assert _parse_csv_datetime("Jan 02, 2026 at 9:00:00 AM UTC+5:30") == \
            "2026-01-02T09:00:00+05:30"

    @pytest.mark.parametrize("bad", ["", "   ", "not a date", "May 2026"])
    def test_unparseable_returns_none(self, bad):
        assert _parse_csv_datetime(bad) is None

    def test_non_string_returns_none(self):
        assert _parse_csv_datetime(float("nan")) is None
        assert _parse_csv_datetime(None) is None
        assert _parse_csv_datetime(12345) is None


class TestNormalizeCsv:
    """Raw CSV rows -> NormalizedEnvelope."""

    def _rows(self):
        return [
            {
                "Trends": "kyle busch",
                "Search volume": "5M+",
                "Started": "May 21, 2026 at 5:50:00 PM UTC+3",
                "Ended": float("nan"),
                "Trend breakdown": "kyle busch,kyle busch news,nascar",
                "Explore link": "https://trends.google.com/trends/explore?q=kyle%20busch",
            },
            {
                "Trends": "knicks",
                "Search volume": "200K+",
                "Started": "May 22, 2026 at 3:40:00 AM UTC+3",
                "Ended": "May 22, 2026 at 6:00:00 AM UTC+3",
                "Trend breakdown": "knicks,knicks game",
                "Explore link": "https://trends.google.com/trends/explore?q=knicks",
            },
        ]

    def test_envelope_shape(self):
        env = normalize_csv(self._rows(), "US")
        assert env["schema_version"] == SCHEMA_VERSION
        assert env["source"] == "csv"
        assert env["geo"] == "US"
        assert env["count"] == 2
        assert len(env["trends"]) == 2
        assert isinstance(env["fetched_at"], str)

    def test_volume_parsed_to_int(self):
        env = normalize_csv(self._rows(), "US")
        assert env["trends"][0]["volume_text"] == "5M+"
        assert env["trends"][0]["volume_min"] == 5_000_000
        assert env["trends"][1]["volume_min"] == 200_000

    def test_dates_iso_and_active_flag(self):
        env = normalize_csv(self._rows(), "US")
        active, ended = env["trends"][0], env["trends"][1]
        assert active["started_at"] == "2026-05-21T17:50:00+03:00"
        assert active["ended_at"] is None
        assert active["is_active"] is True
        assert ended["ended_at"] == "2026-05-22T06:00:00+03:00"
        assert ended["is_active"] is False

    def test_breakdown_is_a_list(self):
        env = normalize_csv(self._rows(), "US")
        related = env["trends"][0]["related_queries"]
        assert isinstance(related, list)
        assert related == ["kyle busch", "kyle busch news", "nascar"]

    def test_rank_is_one_based(self):
        env = normalize_csv(self._rows(), "US")
        assert [t["rank"] for t in env["trends"]] == [1, 2]

    def test_csv_has_no_news_or_image(self):
        env = normalize_csv(self._rows(), "US")
        assert env["trends"][0]["news"] == []
        assert env["trends"][0]["image"] is None

    def test_json_serializable(self):
        env = normalize_csv(self._rows(), "US")
        json.dumps(env)  # must not raise

    def test_empty_input(self):
        env = normalize_csv([], "US")
        assert env["count"] == 0
        assert env["trends"] == []


class TestNormalizeRss:
    """Raw RSS trend dicts -> NormalizedEnvelope."""

    def _trends(self):
        return [
            {
                "trend": "timothee chalamet",
                "traffic": "2000+",
                "traffic_min": 2000,
                "published": datetime(2026, 5, 21, 18, 30, 0, tzinfo=timezone.utc),
                "explore_link": "https://trends.google.com/trends/explore?q=x",
                "image": {"url": "https://img/x.png", "source": "The Cut"},
                "news_articles": [
                    {
                        "headline": "A headline",
                        "url": "https://news/x",
                        "source": "The Cut",
                        "image": "https://news/x.png",
                    }
                ],
            }
        ]

    def test_envelope_shape(self):
        env = normalize_rss(self._trends(), "US")
        assert env["schema_version"] == SCHEMA_VERSION
        assert env["source"] == "rss"
        assert env["count"] == 1

    def test_fields_mapped(self):
        trend = normalize_rss(self._trends(), "US")["trends"][0]
        assert trend["keyword"] == "timothee chalamet"
        assert trend["rank"] == 1
        assert trend["volume_text"] == "2000+"
        assert trend["volume_min"] == 2000
        assert trend["started_at"] == "2026-05-21T18:30:00+00:00"
        assert trend["ended_at"] is None
        assert trend["is_active"] is True

    def test_news_and_image_structured(self):
        trend = normalize_rss(self._trends(), "US")["trends"][0]
        assert trend["image"] == {"url": "https://img/x.png", "source": "The Cut"}
        assert len(trend["news"]) == 1
        assert trend["news"][0]["headline"] == "A headline"

    def test_rss_has_empty_related_queries(self):
        trend = normalize_rss(self._trends(), "US")["trends"][0]
        assert trend["related_queries"] == []

    def test_missing_optional_fields(self):
        """A trend with no image / no articles still yields a fixed shape."""
        env = normalize_rss([{"trend": "x", "traffic": "100+", "traffic_min": 100}], "US")
        trend = env["trends"][0]
        assert trend["image"] is None
        assert trend["news"] == []
        assert trend["started_at"] is None
        assert trend["explore_url"] == ""

    def test_json_serializable(self):
        env = normalize_rss(self._trends(), "US")
        json.dumps(env)  # must not raise
