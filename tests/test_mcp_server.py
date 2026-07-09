"""Tests for the MCP server module.

The tool functions are plain and framework-free, so they are tested on every
Python trendspyg supports. The build_server()/FastMCP layer needs the `mcp`
package (Python 3.10+) and those tests skip where it is absent — which is
exactly the 3.8/3.9 CI cells.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import trendspyg.mcp_server as mcp_server
from trendspyg.mcp_server import (
    _TOOLS,
    build_server,
    compare_trending,
    get_interest_over_time,
    get_trend_changes,
    get_trending_full,
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


class TestBuildServerGuard:
    def test_missing_mcp_raises_actionable_import_error(self, monkeypatch):
        # Poison the exact modules build_server imports: cached submodules are
        # served straight from sys.modules, so poisoning "mcp" alone is not enough.
        for name in ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.types"):
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
    """Exercise the real FastMCP layer where the SDK is available."""

    async def test_all_tools_registered_with_descriptions(self):
        server = build_server()

        tools = await server.list_tools()

        names = {t.name for t in tools}
        assert names == {fn.__name__ for fn in _TOOLS}
        assert len(tools) == 6
        for tool in tools:
            assert tool.description, f"{tool.name} has no description"
            assert tool.annotations.readOnlyHint is True

    async def test_call_tool_end_to_end(self):
        server = build_server()

        with patch("trendspyg.mcp_server.download_google_trends_rss", return_value=ENVELOPE):
            result = await server.call_tool("get_trending_now", {"geo": "US"})

        assert "bitcoin" in str(result)
