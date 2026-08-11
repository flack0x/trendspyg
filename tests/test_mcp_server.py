"""Tests for the MCP server module.

The tool functions are plain and framework-free, so they are tested on every
Python trendspyg supports. The build_server() layer needs the `mcp` package
(SDK v2 or the v1 line, Python 3.10+) and those tests skip where it is
absent — which is exactly the 3.8/3.9 CI cells.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import trendspyg.mcp_server as mcp_server
from trendspyg.mcp_server import (
    _TOOLS,
    build_server,
    compare_interest_over_time,
    compare_trending,
    get_interest_over_time,
    get_trend_changes,
    get_trending_full,
    get_trending_history,
    get_trending_now,
    list_supported_options,
    main,
)

try:
    import mcp  # noqa: F401

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


ENVELOPE = {
    "schema_version": "1.0",
    "source": "rss",
    "geo": "US",
    "fetched_at": "2026-07-09T00:00:00+00:00",
    "count": 1,
    "trends": [{"keyword": "bitcoin", "rank": 1, "volume_min": 500000}],
}


@pytest.fixture(autouse=True)
def _fresh_snapshots(monkeypatch):
    """Isolate the change-detection state between tests."""
    monkeypatch.setattr(mcp_server, "_last_snapshots", {})


class TestGetTrendingNow:
    @patch("trendspyg.mcp_server.download_google_trends_rss")
    def test_returns_normalized_envelope(self, mock_dl):
        mock_dl.return_value = ENVELOPE

        result = get_trending_now(geo="GB")

        assert result == ENVELOPE
        assert mock_dl.call_args[1]["geo"] == "GB"
        assert mock_dl.call_args[1]["normalize"] is True


class TestCompareTrending:
    @patch("trendspyg.mcp_server.download_google_trends_rss_batch")
    def test_returns_envelope_per_geo(self, mock_batch):
        mock_batch.return_value = {"US": ENVELOPE, "GB": ENVELOPE}

        result = compare_trending(["US", "GB"])

        assert set(result) == {"US", "GB"}
        args, kwargs = mock_batch.call_args
        assert args[0] == ["US", "GB"]
        assert kwargs["normalize"] is True

    def test_empty_geo_list_rejected(self):
        with pytest.raises(ValueError) as exc_info:
            compare_trending([])
        assert "between 1 and 20" in str(exc_info.value)

    def test_oversized_geo_list_rejected(self):
        with pytest.raises(ValueError) as exc_info:
            compare_trending(["US"] * 21)
        assert "between 1 and 20" in str(exc_info.value)


class TestGetTrendChanges:
    @patch("trendspyg.mcp_server.download_google_trends_rss")
    def test_first_call_captures_baseline(self, mock_dl):
        mock_dl.return_value = [{"trend": "bitcoin", "traffic_min": 500000}]

        result = get_trend_changes(geo="US")

        assert result["baseline"] is True
        assert result["trend_count"] == 1
        assert result["changes"] == []
        assert mock_dl.call_args[1]["cache"] is False  # a cached diff would show no changes

    @patch("trendspyg.mcp_server.download_google_trends_rss")
    def test_second_call_reports_real_diff(self, mock_dl):
        mock_dl.side_effect = [
            [{"trend": "bitcoin", "traffic_min": 500000}],
            [
                {"trend": "bitcoin", "traffic_min": 2000000},
                {"trend": "solar eclipse", "traffic_min": 100000},
            ],
        ]

        get_trend_changes(geo="US")
        result = get_trend_changes(geo="US")

        assert result["baseline"] is False
        assert result["previous_count"] == 1
        assert result["current_count"] == 2
        events = {c["keyword"]: c["event"] for c in result["changes"]}
        assert events["bitcoin"] == "volume_up"
        assert events["solar eclipse"] == "new"

    @patch("trendspyg.mcp_server.download_google_trends_rss")
    def test_baselines_are_per_geo(self, mock_dl):
        mock_dl.return_value = [{"trend": "bitcoin", "traffic_min": 500000}]

        get_trend_changes(geo="US")
        result = get_trend_changes(geo="GB")  # different geo -> its own baseline

        assert result["baseline"] is True


class TestListSupportedOptions:
    def test_counts_match_marketing_claims(self):
        options = list_supported_options()

        assert len(options["countries"]) == 125
        assert len(options["us_states"]) == 51
        assert "all" in options["csv_categories"]
        assert options["csv_hours"] == [4, 24, 48, 168]
        assert "today 12-m" in options["explore_timeframe_examples"]


class TestGetInterestOverTime:
    @patch("trendspyg.mcp_server.download_google_trends_interest_over_time")
    def test_passes_through_as_dict_format(self, mock_iot):
        mock_iot.return_value = [{"time": "2026-01-01", "value": 50, "is_partial": False}]

        result = get_interest_over_time("bitcoin", geo="GB", timeframe="today 5-y")

        assert result[0]["value"] == 50
        args, kwargs = mock_iot.call_args
        assert args[0] == "bitcoin"
        assert kwargs["geo"] == "GB"
        assert kwargs["timeframe"] == "today 5-y"
        assert kwargs["output_format"] == "dict"
        # Fail-fast profile: ~40s ceiling so the call fits MCP client timeouts.
        assert kwargs["max_retries"] == 4
        assert kwargs["retry_wait"] == 6.0
        # 1.4.0: identical repeat questions answered from the local disk cache.
        assert kwargs["cache"] == "disk"


class TestCompareInterestOverTime:
    @patch("trendspyg.mcp_server.download_google_trends_comparison")
    def test_returns_envelope_with_fail_fast_profile(self, mock_cmp):
        envelope = {
            "keywords": ["bitcoin", "ethereum"],
            "averages": {"bitcoin": 39, "ethereum": 7},
            "interest_over_time": [],
            "interest_by_region": [],
        }
        mock_cmp.return_value = envelope

        result = compare_interest_over_time(["bitcoin", "ethereum"], geo="GB")

        assert result == envelope
        args, kwargs = mock_cmp.call_args
        assert args[0] == ["bitcoin", "ethereum"]
        assert kwargs["geo"] == "GB"
        assert kwargs["output_format"] == "dict"
        # Fail-fast profile + no region fetch: keeps the call inside MCP timeouts.
        assert kwargs["max_retries"] == 4
        assert kwargs["retry_wait"] == 6.0
        assert kwargs["include_geo"] is False
        # 1.4.0: identical repeat comparisons answered from the local disk cache.
        assert kwargs["cache"] == "disk"

    @patch("trendspyg.mcp_server.download_google_trends_comparison")
    def test_tuple_keywords_coerced_to_list(self, mock_cmp):
        mock_cmp.return_value = {}

        compare_interest_over_time(("bitcoin", "ethereum"))

        assert mock_cmp.call_args[0][0] == ["bitcoin", "ethereum"]


class TestGetTrendingFull:
    @patch("trendspyg.mcp_server.download_google_trends_csv")
    def test_normalized_envelope_and_temp_dir_cleanup(self, mock_csv):
        mock_csv.return_value = ENVELOPE

        result = get_trending_full(geo="US", hours=48, category="sports")

        assert result == ENVELOPE
        kwargs = mock_csv.call_args[1]
        assert kwargs["hours"] == 48
        assert kwargs["category"] == "sports"
        assert kwargs["normalize"] is True
        # The scratch download dir must not outlive the call.
        assert not os.path.exists(kwargs["download_dir"])

    @patch("trendspyg.mcp_server.download_google_trends_csv")
    def test_temp_dir_cleaned_even_on_failure(self, mock_csv):
        mock_csv.side_effect = RuntimeError("Chrome exploded")

        with pytest.raises(RuntimeError):
            get_trending_full()

        assert not os.path.exists(mock_csv.call_args[1]["download_dir"])


ARCHIVED_ENVELOPE = {
    "schema_version": "1.0",
    "source": "rss",
    "geo": "US",
    "fetched_at": "2026-08-01T09:00:00+00:00",
    "count": 1,
    "trends": [
        {
            "keyword": "bitcoin",
            "rank": 1,
            "volume_min": 500000,
            "volume_text": "500K+",
            "news": [{"headline": "big", "url": "x", "source": "y", "image": None}],
            "image": None,
        }
    ],
}


class TestGetTrendingHistory:
    @patch("trendspyg.mcp_server.read_archive")
    def test_returns_compact_snapshots(self, mock_read):
        mock_read.return_value = [ARCHIVED_ENVELOPE]

        result = get_trending_history(geo="US", limit=5)

        assert result["snapshot_count"] == 1
        snap = result["snapshots"][0]
        assert snap["fetched_at"] == "2026-08-01T09:00:00+00:00"
        # Compact: keyword/rank/volume only — no news payload into agent context.
        assert snap["trends"] == [{"keyword": "bitcoin", "rank": 1, "volume_min": 500000}]
        assert "appearances" not in result
        assert mock_read.call_args.kwargs["limit"] == 5
        # Trending-Now sources only — Explore research snapshots stay out.
        assert mock_read.call_args.kwargs["source"] == ("rss", "csv")

    @patch("trendspyg.mcp_server.get_keyword_history")
    @patch("trendspyg.mcp_server.read_archive")
    def test_keyword_adds_appearance_timeline(self, mock_read, mock_history):
        mock_read.return_value = [ARCHIVED_ENVELOPE]
        mock_history.return_value = [
            {
                "fetched_at": "2026-08-01T09:00:00+00:00",
                "geo": "US",
                "source": "rss",
                "rank": 1,
                "volume_min": 500000,
            }
        ]

        result = get_trending_history(keyword="bitcoin")

        assert result["keyword"] == "bitcoin"
        assert len(result["appearances"]) == 1
        assert mock_history.call_args.args[0] == "bitcoin"
        assert mock_history.call_args.kwargs["source"] == ("rss", "csv")

    @patch("trendspyg.mcp_server.read_archive")
    def test_empty_archive_explains_itself(self, mock_read):
        mock_read.return_value = []

        result = get_trending_history(geo="JP")

        assert result["snapshot_count"] == 0
        assert "no retroactive data" in result["note"]

    def test_limit_bounds_enforced(self):
        with pytest.raises(ValueError):
            get_trending_history(limit=0)
        with pytest.raises(ValueError):
            get_trending_history(limit=101)

    def test_explore_snapshots_excluded_against_a_real_db(self, tmp_path, monkeypatch):
        """End-to-end through the real SQL: archived Explore research must not
        appear in the trending history (1.4.0 seam)."""
        from trendspyg.archive import _store_snapshot

        db = str(tmp_path / "mcp.db")
        monkeypatch.setenv("TRENDSPYG_DB", db)
        _store_snapshot(ARCHIVED_ENVELOPE, db_path=db)
        _store_snapshot(
            {
                "schema_version": "1.0",
                "source": "explore",
                "keyword": "bitcoin",
                "geo": "US",
                "timeframe": "today 12-m",
                "fetched_at": "2026-08-02T09:00:00+00:00",
                "count": 0,
                "interest_over_time": [],
                "related_queries": {"top": [], "rising": []},
                "interest_by_region": [],
            },
            db_path=db,
        )

        result = get_trending_history(keyword="bitcoin")

        assert result["snapshot_count"] == 1
        assert result["snapshots"][0]["source"] == "rss"
        assert [a["source"] for a in result["appearances"]] == ["rss"]


class TestBuildServerGuard:
    def test_missing_mcp_raises_actionable_import_error(self, monkeypatch):
        # Poison the exact modules build_server imports (both the v2 and the v1
        # fallback paths): cached submodules are served straight from
        # sys.modules, so poisoning "mcp" alone is not enough.
        for name in (
            "mcp",
            "mcp.server",
            "mcp.server.mcpserver",
            "mcp.server.fastmcp",
            "mcp.types",
            "mcp_types",
        ):
            monkeypatch.setitem(sys.modules, name, None)

        with pytest.raises(ImportError) as exc_info:
            build_server()

        assert "pip install trendspyg[mcp]" in str(exc_info.value)
        assert "3.10" in str(exc_info.value)


class TestMainEntry:
    @patch("trendspyg.mcp_server.build_server")
    def test_main_runs_the_server(self, mock_build):
        server = MagicMock()
        mock_build.return_value = server

        main()

        server.run.assert_called_once()


@pytest.mark.skipif(not MCP_AVAILABLE, reason="mcp not installed (Python 3.10+ only)")
class TestServerIntegration:
    """Exercise the real MCP SDK layer (v2 MCPServer or v1 FastMCP) where available."""

    async def test_all_tools_registered_with_descriptions(self):
        server = build_server()

        tools = await server.list_tools()

        names = {t.name for t in tools}
        assert names == {fn.__name__ for fn in _TOOLS}
        assert len(tools) == 8
        assert "compare_interest_over_time" in names
        assert "get_trending_history" in names
        for tool in tools:
            assert tool.description, f"{tool.name} has no description"
            # SDK v2 exposes snake_case attrs; the v1 line exposed camelCase.
            hint = getattr(
                tool.annotations, "read_only_hint", getattr(tool.annotations, "readOnlyHint", None)
            )
            assert hint is True

    async def test_call_tool_end_to_end(self):
        server = build_server()

        with patch("trendspyg.mcp_server.download_google_trends_rss", return_value=ENVELOPE):
            result = await server.call_tool("get_trending_now", {"geo": "US"})

        assert "bitcoin" in str(result)
