"""Tests for the real-time monitoring module (new in 0.7.0).

All offline — the diff/filter core is pure, and the watch loop + webhook are
exercised with mocked fetch/sleep/HTTP. No network, no browser.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

import trendspyg
from trendspyg.monitor import (
    CHANGE_EVENTS,
    MONITOR_SCHEMA_VERSION,
    diff_trends,
    filter_changes,
    post_webhook,
    watch_google_trends_rss,
)

# Two snapshots covering every event type between them:
#   alpha: same volume, rank 1 -> 2      => rank_change
#   beta:  volume 50 -> 80, rank 2 -> 1  => volume_up
#   gamma: present then gone             => dropped
#   delta: absent then present           => new
SNAP_A = [
    {"trend": "alpha", "traffic_min": 100},
    {"trend": "beta", "traffic_min": 50},
    {"trend": "gamma", "traffic_min": 30},
]
SNAP_B = [
    {"trend": "beta", "traffic_min": 80},
    {"trend": "alpha", "traffic_min": 100},
    {"trend": "delta", "traffic_min": 10},
]


def _by_kw(changes):
    return {c["keyword"]: c for c in changes}


class TestDiffTrends:
    def test_detects_all_event_types(self):
        ch = _by_kw(diff_trends(SNAP_A, SNAP_B))
        assert ch["beta"]["event"] == "volume_up"
        assert ch["alpha"]["event"] == "rank_change"
        assert ch["delta"]["event"] == "new"
        assert ch["gamma"]["event"] == "dropped"

    def test_volume_up_fields(self):
        ch = _by_kw(diff_trends(SNAP_A, SNAP_B))["beta"]
        assert ch["prev_volume_min"] == 50 and ch["volume_min"] == 80
        assert ch["rank"] == 1 and ch["prev_rank"] == 2

    def test_volume_down(self):
        ch = diff_trends([{"trend": "x", "traffic_min": 100}], [{"trend": "x", "traffic_min": 40}])
        assert ch[0]["event"] == "volume_down"

    def test_new_has_no_prev(self):
        ch = _by_kw(diff_trends(SNAP_A, SNAP_B))["delta"]
        assert ch["prev_rank"] is None and ch["prev_volume_min"] is None

    def test_dropped_has_no_current(self):
        ch = _by_kw(diff_trends(SNAP_A, SNAP_B))["gamma"]
        assert ch["rank"] is None and ch["volume_min"] is None and ch["prev_volume_min"] == 30

    def test_identical_snapshots_no_change(self):
        assert diff_trends(SNAP_A, SNAP_A) == []

    def test_empty_baseline_all_new(self):
        ch = diff_trends([], SNAP_B)
        assert len(ch) == 3 and all(c["event"] == "new" for c in ch)

    def test_empty_new_all_dropped(self):
        ch = diff_trends(SNAP_A, [])
        assert len(ch) == 3 and all(c["event"] == "dropped" for c in ch)

    def test_accepts_normalized_shape(self):
        ch = diff_trends([{"keyword": "x", "volume_min": 5}], [{"keyword": "x", "volume_min": 9}])
        assert ch[0]["event"] == "volume_up"

    def test_output_is_json_safe(self):
        json.dumps(diff_trends(SNAP_A, SNAP_B))  # must not raise

    def test_rank_change_only(self):
        a = [{"trend": "x", "traffic_min": 5}, {"trend": "y", "traffic_min": 5}]
        b = [{"trend": "y", "traffic_min": 5}, {"trend": "x", "traffic_min": 5}]
        assert {c["keyword"]: c["event"] for c in diff_trends(a, b)} == {
            "x": "rank_change",
            "y": "rank_change",
        }

    def test_ignores_blank_keyword(self):
        ch = diff_trends([], [{"trend": "", "traffic_min": 5}, {"trend": "real", "traffic_min": 5}])
        assert [c["keyword"] for c in ch] == ["real"]

    def test_all_events_in_change_events_constant(self):
        events = {c["event"] for c in diff_trends(SNAP_A, SNAP_B)}
        assert events.issubset(set(CHANGE_EVENTS))


class TestFilterChanges:
    def setup_method(self):
        self.ch = diff_trends(SNAP_A, SNAP_B)

    def test_min_volume(self):
        assert {c["keyword"] for c in filter_changes(self.ch, min_volume=50)} == {"alpha", "beta"}

    def test_events(self):
        assert [c["keyword"] for c in filter_changes(self.ch, events=["new"])] == ["delta"]

    def test_keywords_substring(self):
        assert [c["keyword"] for c in filter_changes(self.ch, keywords=["alph"])] == ["alpha"]

    def test_no_filters_keeps_all(self):
        assert len(filter_changes(self.ch)) == len(self.ch)

    def test_does_not_mutate_input(self):
        n = len(self.ch)
        filter_changes(self.ch, min_volume=999999)
        assert len(self.ch) == n

    def test_min_volume_uses_prev_for_dropped(self):
        assert any(c["keyword"] == "gamma" for c in filter_changes(self.ch, min_volume=25))
        assert not any(c["keyword"] == "gamma" for c in filter_changes(self.ch, min_volume=40))

    def test_combined_filters(self):
        kept = filter_changes(self.ch, events=["volume_up", "rank_change"], min_volume=60)
        assert {c["keyword"] for c in kept} == {"alpha", "beta"}


class TestPostWebhook:
    @patch("requests.post")
    def test_success_2xx_true(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        assert post_webhook("http://hook", {"event": "new"}) is True

    @patch("requests.post")
    def test_non_2xx_false(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        assert post_webhook("http://hook", {"event": "new"}) is False

    @patch("requests.post")
    def test_exception_false(self, mock_post):
        mock_post.side_effect = Exception("boom")
        assert post_webhook("http://hook", {"event": "new"}) is False

    @patch("requests.post")
    def test_posts_change_as_json(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        post_webhook("http://hook", {"event": "new", "keyword": "x"}, timeout=5)
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["keyword"] == "x" and kwargs["timeout"] == 5


class TestWatch:
    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_yields_diff_of_two_polls(self, mock_dl):
        mock_dl.side_effect = [SNAP_A, SNAP_B]
        got = list(watch_google_trends_rss(iterations=2, sleep=lambda _s: None))
        assert {c["keyword"] for c in got} == {"alpha", "beta", "delta", "gamma"}
        assert mock_dl.call_count == 2

    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_baseline_only_no_changes(self, mock_dl):
        mock_dl.side_effect = [SNAP_A]
        assert list(watch_google_trends_rss(iterations=1, sleep=lambda _s: None)) == []
        assert mock_dl.call_count == 1

    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_on_change_callback_and_event_filter(self, mock_dl):
        mock_dl.side_effect = [SNAP_A, SNAP_B]
        seen = []
        got = list(
            watch_google_trends_rss(
                iterations=2, sleep=lambda _s: None, on_change=seen.append, events=["new"]
            )
        )
        assert [c["keyword"] for c in got] == ["delta"]
        assert [c["keyword"] for c in seen] == ["delta"]

    @patch("trendspyg.monitor.post_webhook")
    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_webhook_called_per_change(self, mock_dl, mock_hook):
        mock_dl.side_effect = [SNAP_A, SNAP_B]
        list(watch_google_trends_rss(iterations=2, sleep=lambda _s: None, webhook="http://hook"))
        assert mock_hook.call_count == 4

    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_strips_reserved_kwargs(self, mock_dl):
        mock_dl.side_effect = [SNAP_A, SNAP_B]
        list(
            watch_google_trends_rss(
                iterations=2,
                sleep=lambda _s: None,
                output_format="json",
                normalize=True,
                cache=True,
            )
        )
        for call in mock_dl.call_args_list:
            assert call.kwargs["cache"] is False
            assert call.kwargs["output_format"] == "dict"
            assert "normalize" not in call.kwargs

    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_sleeps_between_polls_not_after_last(self, mock_dl):
        mock_dl.side_effect = [SNAP_A, SNAP_B]
        slept = []
        list(watch_google_trends_rss(iterations=2, interval=42, sleep=slept.append))
        assert slept == [42]


class TestExports:
    def test_schema_version(self):
        assert MONITOR_SCHEMA_VERSION == "1.0"
        assert trendspyg.MONITOR_SCHEMA_VERSION == "1.0"

    def test_change_events_constant(self):
        assert set(CHANGE_EVENTS) == {"new", "dropped", "volume_up", "volume_down", "rank_change"}

    def test_package_level_exports(self):
        for name in ("watch_google_trends_rss", "diff_trends", "filter_changes", "post_webhook"):
            assert hasattr(trendspyg, name)
            assert name in trendspyg.__all__


CLICK_AVAILABLE = True
try:
    from click.testing import CliRunner

    from trendspyg.cli import cli
except ImportError:
    CLICK_AVAILABLE = False


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIWatch:
    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_streams_ndjson(self, mock_dl):
        mock_dl.side_effect = [SNAP_A, SNAP_B]
        result = CliRunner().invoke(
            cli, ["watch", "--iterations", "2", "--interval", "0", "--quiet"]
        )
        assert result.exit_code == 0
        objs = [json.loads(ln) for ln in result.output.splitlines() if ln.strip()]
        assert {o["keyword"] for o in objs} == {"alpha", "beta", "delta", "gamma"}

    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_events_filter(self, mock_dl):
        mock_dl.side_effect = [SNAP_A, SNAP_B]
        result = CliRunner().invoke(
            cli,
            ["watch", "--iterations", "2", "--interval", "0", "--events", "new", "--quiet"],
        )
        objs = [json.loads(ln) for ln in result.output.splitlines() if ln.strip()]
        assert [o["keyword"] for o in objs] == ["delta"]

    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_min_volume_and_keyword_flags(self, mock_dl):
        mock_dl.side_effect = [SNAP_A, SNAP_B]
        result = CliRunner().invoke(
            cli,
            ["watch", "--iterations", "2", "--interval", "0", "-k", "beta", "--quiet"],
        )
        objs = [json.loads(ln) for ln in result.output.splitlines() if ln.strip()]
        assert [o["keyword"] for o in objs] == ["beta"]

    @patch("trendspyg.monitor.download_google_trends_rss")
    def test_quiet_suppresses_banner(self, mock_dl):
        mock_dl.side_effect = [SNAP_A, SNAP_B]
        result = CliRunner().invoke(
            cli, ["watch", "--iterations", "2", "--interval", "0", "--quiet"]
        )
        assert "[watch] Monitoring" not in result.output
