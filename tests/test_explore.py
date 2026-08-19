"""
Tests for the Explore path (interest over time, related queries, regions).

The pure parsers are tested against the REAL widgetdata JSON shapes captured
live from Google. The public functions are tested with the browser engine
(``_fetch_explore``) mocked, so no Chrome launches and no network is touched.
A single live end-to-end test is marked ``network`` and skipped by default.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import WebDriverException

from trendspyg.archive import _explore_cache_get, get_keyword_history, read_archive
from trendspyg.exceptions import (
    BrowserError,
    DownloadError,
    InvalidParameterError,
    RateLimitError,
)
from trendspyg.explore import (
    EXPLORE_SCHEMA_VERSION,
    _await_chart,
    _build_driver,
    _build_explore_url,
    _collect_widget_urls,
    _default_cache_ttl,
    _dismiss_cookie_banner,
    _epoch_to_iso,
    _fetch_explore,
    _format_timeseries,
    _page_blocked,
    _parse_comparedgeo,
    _parse_multiline,
    _parse_relatedsearches,
    _raise_for_chart_status,
    _replay_widget,
    _strip_xssi,
    _warm_up,
    download_google_trends_explore,
    download_google_trends_interest_over_time,
)

# --- Real captured widget shapes (XSSI-prefixed, as Google sends them) ------ #

MULTILINE_RAW = ")]}',\n" + json.dumps(
    {
        "default": {
            "timelineData": [
                {
                    "time": "1748736000",
                    "formattedTime": "Jun 1 – 7, 2025",
                    "value": [66],
                    "hasData": [True],
                    "formattedValue": ["66"],
                },
                {"time": "1749340800", "value": [29], "hasData": [True], "formattedValue": ["29"]},
                {
                    "time": "1780185600",
                    "value": [57],
                    "hasData": [True],
                    "formattedValue": ["57"],
                    "isPartial": True,
                },
            ],
            "averages": [],
        }
    }
)

COMPAREDGEO_RAW = ")]}',\n" + json.dumps(
    {
        "default": {
            "geoMapData": [
                {
                    "geoCode": "US-WY",
                    "geoName": "Wyoming",
                    "value": [100],
                    "formattedValue": ["100"],
                    "maxValueIndex": 0,
                    "hasData": [True],
                },
                {
                    "geoCode": "US-MT",
                    "geoName": "Montana",
                    "value": [88],
                    "formattedValue": ["88"],
                    "maxValueIndex": 0,
                    "hasData": [True],
                },
                {"geoCode": "US-XX", "geoName": "NoData", "value": [0], "hasData": [False]},
            ]
        }
    }
)

RELATED_RAW = ")]}',\n" + json.dumps(
    {
        "default": {
            "rankedList": [
                {
                    "rankedKeyword": [
                        {
                            "query": "what is python",
                            "value": 100,
                            "formattedValue": "100",
                            "hasData": True,
                            "link": "/trends/explore?q=what+is+python",
                        }
                    ]
                },
                {
                    "rankedKeyword": [
                        {
                            "query": "python tutorial",
                            "value": 3650,
                            "formattedValue": "+3,650%",
                            "hasData": True,
                            "link": "/trends/explore?q=python+tutorial&date=today+12-m&geo=US",
                        },
                        {
                            "query": "learn python",
                            "value": 0,
                            "formattedValue": "Breakout",
                            "hasData": True,
                            "link": "/trends/explore?q=learn+python",
                        },
                    ]
                },
            ]
        }
    }
)


class TestStripXssi:
    def test_strips_google_prefix(self):
        assert _strip_xssi(')]}\',\n{"a": 1}') == '{"a": 1}'

    def test_passthrough_when_no_prefix(self):
        assert _strip_xssi('{"a": 1}') == '{"a": 1}'

    def test_empty(self):
        assert _strip_xssi("") == ""


class TestEpochToIso:
    def test_known_epoch(self):
        assert _epoch_to_iso("1748736000") == "2025-06-01T00:00:00+00:00"

    def test_accepts_int_like_string(self):
        # always UTC, never local-tz dependent
        assert _epoch_to_iso("0") == "1970-01-01T00:00:00+00:00"


class TestParseMultiline:
    def test_parses_points(self):
        points = _parse_multiline(json.loads(_strip_xssi(MULTILINE_RAW)))
        assert len(points) == 3
        assert points[0] == {"date": "2025-06-01T00:00:00+00:00", "value": 66, "is_partial": False}

    def test_partial_flag_on_last(self):
        points = _parse_multiline(json.loads(_strip_xssi(MULTILINE_RAW)))
        assert points[-1]["is_partial"] is True
        assert points[-1]["value"] == 57

    def test_values_are_ints(self):
        points = _parse_multiline(json.loads(_strip_xssi(MULTILINE_RAW)))
        assert all(isinstance(p["value"], int) for p in points)

    def test_empty_payload(self):
        assert _parse_multiline({"default": {"timelineData": []}}) == []

    def test_missing_keys_safe(self):
        # a malformed entry must not raise
        out = _parse_multiline({"default": {"timelineData": [{"time": "1748736000"}]}})
        assert out[0]["value"] == 0

    def test_json_safe(self):
        points = _parse_multiline(json.loads(_strip_xssi(MULTILINE_RAW)))
        json.dumps(points)  # must not raise


class TestParseComparedGeo:
    def test_parses_rows(self):
        rows = _parse_comparedgeo(json.loads(_strip_xssi(COMPAREDGEO_RAW)))
        # the hasData=False row is dropped
        assert len(rows) == 2
        assert rows[0] == {"geo_code": "US-WY", "geo_name": "Wyoming", "value": 100}

    def test_preserves_order(self):
        rows = _parse_comparedgeo(json.loads(_strip_xssi(COMPAREDGEO_RAW)))
        assert [r["value"] for r in rows] == [100, 88]

    def test_empty(self):
        assert _parse_comparedgeo({"default": {"geoMapData": []}}) == []


class TestParseRelatedSearches:
    def test_top_and_rising_buckets(self):
        rel = _parse_relatedsearches(json.loads(_strip_xssi(RELATED_RAW)))
        assert set(rel) == {"top", "rising"}
        assert rel["top"][0]["query"] == "what is python"
        assert rel["top"][0]["value"] == 100

    def test_rising_keeps_formatted_value(self):
        rel = _parse_relatedsearches(json.loads(_strip_xssi(RELATED_RAW)))
        assert rel["rising"][0]["formatted_value"] == "+3,650%"
        assert rel["rising"][1]["formatted_value"] == "Breakout"

    def test_relative_link_is_absolutized(self):
        rel = _parse_relatedsearches(json.loads(_strip_xssi(RELATED_RAW)))
        assert rel["top"][0]["link"].startswith("https://trends.google.com/")

    def test_empty_lists(self):
        rel = _parse_relatedsearches({"default": {"rankedList": []}})
        assert rel == {"top": [], "rising": []}


class TestFormatTimeseries:
    @property
    def points(self):
        return _parse_multiline(json.loads(_strip_xssi(MULTILINE_RAW)))

    def test_dict_is_passthrough(self):
        assert (
            _format_timeseries(self.points, "dict") is self.points
            or _format_timeseries(self.points, "dict") == self.points
        )

    def test_json_parses_back(self):
        out = _format_timeseries(self.points, "json")
        assert isinstance(out, str)
        assert json.loads(out)[0]["value"] == 66

    def test_csv_header_and_rows(self):
        out = _format_timeseries(self.points, "csv")
        lines = out.strip().splitlines()
        assert lines[0] == "date,value,is_partial"
        assert len(lines) == 4  # header + 3 points

    def test_invalid_format_raises(self):
        with pytest.raises(InvalidParameterError):
            _format_timeseries(self.points, "xml")


class TestBuildUrl:
    def test_encodes_spaces(self):
        url = _build_explore_url("taylor swift", "US", "today 12-m", 0)
        assert "q=taylor+swift" in url
        assert "date=today+12-m" in url
        assert "geo=US" in url

    def test_category_omitted_when_zero(self):
        assert "cat=" not in _build_explore_url("python", "US", "today 12-m", 0)

    def test_category_included_when_set(self):
        assert "cat=5" in _build_explore_url("python", "US", "today 12-m", 5)


# --- Public API with the browser engine mocked ----------------------------- #

FAKE_FETCH = {
    "interest_over_time": [
        {"date": "2025-06-01T00:00:00+00:00", "value": 66, "is_partial": False},
        {"date": "2025-06-08T00:00:00+00:00", "value": 57, "is_partial": True},
    ],
    "related_queries": {
        "top": [
            {
                "query": "python tutorial",
                "value": 100,
                "formatted_value": "100",
                "link": "https://trends.google.com/x",
            }
        ],
        "rising": [],
    },
    "interest_by_region": [
        {"geo_code": "US-WY", "geo_name": "Wyoming", "value": 100},
    ],
}


class TestInterestOverTimeApi:
    def test_function_exported(self):
        from trendspyg import download_google_trends_interest_over_time as fn

        assert callable(fn)

    def test_empty_keyword_raises(self):
        with pytest.raises(InvalidParameterError):
            download_google_trends_interest_over_time("   ")

    def test_invalid_geo_raises(self):
        with pytest.raises(InvalidParameterError):
            download_google_trends_interest_over_time("python", geo="NOPE")

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_returns_series_dict(self, _mock):
        out = download_google_trends_interest_over_time("python", geo="US")
        assert isinstance(out, list)
        assert out[0]["value"] == 66

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_csv_output(self, _mock):
        out = download_google_trends_interest_over_time("python", output_format="csv")
        assert out.splitlines()[0] == "date,value,is_partial"

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_only_requests_timeseries(self, mock):
        download_google_trends_interest_over_time("python")
        # the headline function must NOT ask for related/geo (keeps it fast)
        _, kwargs = mock.call_args
        assert kwargs["want_related"] is False
        assert kwargs["want_geo"] is False

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_invalid_output_format_fails_before_browser(self, mock):
        with pytest.raises(InvalidParameterError, match="Invalid output_format"):
            download_google_trends_interest_over_time("python", output_format="xml")
        mock.assert_not_called()


class TestExploreApi:
    def test_function_exported(self):
        from trendspyg import download_google_trends_explore as fn

        assert callable(fn)

    def test_empty_keyword_raises(self):
        with pytest.raises(InvalidParameterError):
            download_google_trends_explore("")

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_envelope_shape(self, _mock):
        env = download_google_trends_explore("python", geo="US")
        assert env["schema_version"] == EXPLORE_SCHEMA_VERSION
        assert env["source"] == "explore"
        assert env["keyword"] == "python"
        assert env["geo"] == "US"
        assert env["count"] == 2
        assert env["count"] == len(env["interest_over_time"])
        assert set(env) == {
            "schema_version",
            "source",
            "keyword",
            "geo",
            "timeframe",
            "gprop",
            "fetched_at",
            "count",
            "interest_over_time",
            "related_queries",
            "interest_by_region",
        }

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_envelope_json_safe(self, _mock):
        env = download_google_trends_explore("python")
        json.dumps(env)  # must not raise

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_requests_related_and_geo_by_default(self, mock):
        download_google_trends_explore("python")
        _, kwargs = mock.call_args
        assert kwargs["want_related"] is True
        assert kwargs["want_geo"] is True


@pytest.mark.network
class TestExploreLive:
    """Real browser hit against Google. Run with: pytest -m network"""

    def test_interest_over_time_live(self):
        series = download_google_trends_interest_over_time("python", geo="US")
        assert isinstance(series, list) and len(series) > 10
        assert all(isinstance(p["value"], int) for p in series)
        json.dumps(series)


def _perf_entry(url):
    """A Chrome performance-log entry for a Network.requestWillBeSent to `url`."""
    return {
        "message": json.dumps(
            {
                "message": {
                    "method": "Network.requestWillBeSent",
                    "params": {"request": {"url": url}},
                }
            }
        )
    }


class TestExploreEngineOffline:
    """Fake-driver tests for the Selenium engine — no Chrome, no network."""

    def test_collect_widget_urls(self):
        driver = MagicMock()
        driver.get_log.return_value = [
            _perf_entry("https://trends.google.com/trends/api/widgetdata/multiline?req=1"),
            _perf_entry("https://example.com/noise"),
            _perf_entry("https://trends.google.com/trends/api/widgetdata/relatedsearches?req=2"),
            _perf_entry("https://trends.google.com/trends/api/widgetdata/comparedgeo?req=3"),
        ]
        urls = _collect_widget_urls(driver)
        assert set(urls) == {"multiline", "relatedsearches", "comparedgeo"}
        assert "widgetdata/multiline" in urls["multiline"]

    def test_collect_widget_urls_skips_malformed_entries(self):
        driver = MagicMock()
        driver.get_log.return_value = [
            {"message": "not json"},
            _perf_entry("https://trends.google.com/trends/api/widgetdata/multiline?a"),
        ]
        assert "multiline" in _collect_widget_urls(driver)

    def test_replay_widget_success(self):
        driver = MagicMock()
        driver.execute_async_script.return_value = MULTILINE_RAW
        parsed = _replay_widget(driver, "url", tries=1)
        assert parsed is not None and "default" in parsed

    def test_replay_widget_err_returns_none(self):
        driver = MagicMock()
        driver.execute_async_script.return_value = "ERR:network down"
        assert _replay_widget(driver, "url", tries=1) is None

    def test_replay_widget_html_returns_none(self):
        driver = MagicMock()
        driver.execute_async_script.return_value = "<html><body>consent</body></html>"
        assert _replay_widget(driver, "url", tries=1) is None

    def test_replay_widget_bad_json_returns_none(self):
        driver = MagicMock()
        driver.execute_async_script.return_value = ")]}',\nnot valid json"
        assert _replay_widget(driver, "url", tries=1) is None

    @patch("trendspyg.explore._engine.time.sleep")
    def test_await_chart_ready(self, _sleep):
        driver = MagicMock()
        driver.find_elements.return_value = [object()]  # TIMESERIES svg present
        assert _await_chart(driver, "url", attempts=1) == "ready"

    @patch("trendspyg.explore._engine.time.sleep")
    def test_await_chart_throttled(self, _sleep):
        driver = MagicMock()
        driver.find_elements.return_value = []
        driver.page_source = "Oops! Something went wrong. Try again in a bit."
        assert _await_chart(driver, "url", attempts=1, per_attempt=1.0) == "throttled"

    @patch("trendspyg.explore._engine.time.sleep")
    def test_await_chart_timeout_is_not_throttle(self, _sleep):
        driver = MagicMock()
        driver.find_elements.return_value = []
        driver.page_source = "a normal page that simply has no chart element"
        assert _await_chart(driver, "url", attempts=1, per_attempt=1.0) == "timeout"

    # --- 1.5.1: Google's HARD block page (observed live 2026-08-16) ----------
    # Before 1.5.1 this page matched neither soft-throttle phrase, so the engine
    # reloaded it attempts× (~100s at defaults) and then blamed a DOM change.

    _BLOCK_PAGE_429 = (
        "<html><head><title>Error 429 (Too Many Requests)!!1</title></head><body>"
        "<p><b>429.</b> That's an error.</p><p>We're sorry, but you have sent too "
        "many requests to us recently. Please try again later. That's all we know."
        "</p></body></html>"
    )
    _BLOCK_PAGE_SORRY = (
        "<html><body>Our systems have detected unusual traffic from your computer "
        "network. This page checks to see if it's really you.</body></html>"
    )

    def test_page_blocked_recognises_429_and_sorry_pages(self):
        driver = MagicMock()
        driver.page_source = self._BLOCK_PAGE_429
        assert _page_blocked(driver) is True
        driver.page_source = self._BLOCK_PAGE_SORRY
        assert _page_blocked(driver) is True

    def test_page_blocked_false_on_normal_and_soft_throttle_pages(self):
        driver = MagicMock()
        driver.page_source = "<html>Explore page, chart still loading</html>"
        assert _page_blocked(driver) is False
        driver.page_source = "Oops! Something went wrong. Try again in a bit."
        assert _page_blocked(driver) is False  # soft-throttle is a different state

    @patch("trendspyg.explore._engine.time.sleep")
    def test_await_chart_blocked_returns_at_once_without_reloading(self, mock_sleep):
        driver = MagicMock()
        driver.find_elements.return_value = []  # no chart
        driver.page_source = self._BLOCK_PAGE_429
        status = _await_chart(driver, "url", attempts=10, per_attempt=8.0)
        assert status == "blocked"
        driver.get.assert_not_called()  # never reloads a block page
        mock_sleep.assert_not_called()  # and never sits out the ladder

    @patch("trendspyg.explore._engine.time.sleep")
    def test_await_chart_block_seen_after_a_reload_is_still_blocked(self, _sleep):
        # Soft-throttle first (triggers one reload), then the reload lands on the
        # hard block page — must report "blocked", not "throttled".
        driver = MagicMock()
        driver.find_elements.return_value = []
        driver.page_source = "Oops! Something went wrong. Try again in a bit."

        def _reload(_url):
            driver.page_source = self._BLOCK_PAGE_429

        driver.get.side_effect = _reload
        assert _await_chart(driver, "url", attempts=1, per_attempt=1.0) == "blocked"
        assert driver.get.call_count == 1

    def test_raise_for_chart_status_blocked_is_ratelimit_with_hard_block_advice(self):
        with pytest.raises(RateLimitError) as exc_info:
            _raise_for_chart_status("blocked", "Keyword: 'x'")
        msg = str(exc_info.value)
        assert "429" in msg and "blocking" in msg.lower()
        assert "30+ minutes" in msg  # hard cooldown, not the soft "1-2 minutes"
        assert "Keyword: 'x'" in msg  # context preserved

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._await_chart", return_value="blocked")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_fetch_explore_blocked_raises_ratelimit_not_browsererror(self, _bd, _dc, _aw, _sleep):
        with pytest.raises(RateLimitError):
            _fetch_explore("bitcoin", "US", "today 12-m", 0, True, False, False)

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._await_chart", return_value="throttled")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_fetch_explore_throttled_raises_ratelimit(self, _bd, _dc, _aw, _sleep):
        with pytest.raises(RateLimitError):
            _fetch_explore("bitcoin", "US", "today 12-m", 0, True, False, False)

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._await_chart", return_value="timeout")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_fetch_explore_dom_change_raises_browsererror(self, _bd, _dc, _aw, _sleep):
        # A "timeout" (no throttle seen) must NOT be reported as a rate-limit.
        with pytest.raises(BrowserError):
            _fetch_explore("bitcoin", "US", "today 12-m", 0, True, False, False)

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._collect_widget_urls", return_value={})
    @patch("trendspyg.explore._engine._await_chart", return_value="ready")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_fetch_explore_missing_multiline_raises_downloaderror(self, _bd, _dc, _aw, _cw, _sleep):
        with pytest.raises(DownloadError):
            _fetch_explore("bitcoin", "US", "today 12-m", 0, True, True, True)

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._replay_widget")
    @patch("trendspyg.explore._engine._collect_widget_urls")
    @patch("trendspyg.explore._engine._await_chart", return_value="ready")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_fetch_explore_success_returns_all_widgets(
        self, _bd, _dc, _aw, mock_collect, mock_replay, _sleep
    ):
        mock_collect.return_value = {
            "multiline": "u1",
            "relatedsearches": "u2",
            "comparedgeo": "u3",
        }
        mock_replay.side_effect = [
            json.loads(_strip_xssi(MULTILINE_RAW)),
            json.loads(_strip_xssi(RELATED_RAW)),
            json.loads(_strip_xssi(COMPAREDGEO_RAW)),
        ]
        out = _fetch_explore("bitcoin", "US", "today 12-m", 0, True, True, True)
        assert out["interest_over_time"]  # non-empty series
        assert "top" in out["related_queries"] and "rising" in out["related_queries"]
        assert isinstance(out["interest_by_region"], list)


class TestRetryParams:
    """max_retries / retry_wait: forwarded, validated, defaults unchanged."""

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_iot_defaults_pin_current_behavior(self, mock_fetch):
        # Non-breaking guarantee: no args -> the pre-0.9.0 hardcoded values.
        download_google_trends_interest_over_time("bitcoin")
        kwargs = mock_fetch.call_args[1]
        assert kwargs["max_load_attempts"] == 10
        assert kwargs["per_attempt_wait"] == 8.0

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_iot_forwards_retry_params(self, mock_fetch):
        download_google_trends_interest_over_time("bitcoin", max_retries=2, retry_wait=5.0)
        kwargs = mock_fetch.call_args[1]
        assert kwargs["max_load_attempts"] == 2
        assert kwargs["per_attempt_wait"] == 5.0

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_explore_forwards_retry_params(self, mock_fetch):
        download_google_trends_explore("bitcoin", max_retries=3, retry_wait=1.5)
        kwargs = mock_fetch.call_args[1]
        assert kwargs["max_load_attempts"] == 3
        assert kwargs["per_attempt_wait"] == 1.5

    def test_max_retries_below_one_rejected(self):
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_interest_over_time("bitcoin", max_retries=0)
        assert "max_retries must be >= 1" in str(exc_info.value)
        with pytest.raises(InvalidParameterError):
            download_google_trends_explore("bitcoin", max_retries=-1)

    def test_retry_wait_nonpositive_rejected(self):
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_interest_over_time("bitcoin", retry_wait=0)
        assert "retry_wait must be > 0" in str(exc_info.value)
        with pytest.raises(InvalidParameterError):
            download_google_trends_explore("bitcoin", retry_wait=-2.0)

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._await_chart", return_value="throttled")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_engine_forwards_per_attempt_to_await_chart(self, _bd, _dc, mock_await, _sleep):
        with pytest.raises(RateLimitError):
            _fetch_explore(
                "bitcoin",
                "US",
                "today 12-m",
                0,
                True,
                False,
                False,
                max_load_attempts=3,
                per_attempt_wait=2.5,
            )
        kwargs = mock_await.call_args[1]
        assert kwargs["attempts"] == 3
        assert kwargs["per_attempt"] == 2.5


class TestParserEdgeCases:
    """Malformed widget entries degrade to safe defaults, never raise."""

    def test_multiline_bad_value_defaults_zero(self):
        data = {"default": {"timelineData": [{"time": "1700000000", "value": ["xx"]}]}}
        points = _parse_multiline(data)
        assert points[0]["value"] == 0

    def test_multiline_bad_epoch_gives_empty_date(self):
        data = {"default": {"timelineData": [{"time": "garbage", "value": [5]}]}}
        points = _parse_multiline(data)
        assert points[0]["date"] == ""
        assert points[0]["value"] == 5

    def test_comparedgeo_bad_value_defaults_zero(self):
        data = {
            "default": {
                "geoMapData": [
                    {
                        "geoCode": "US-CA",
                        "geoName": "California",
                        "value": ["xx"],
                        "hasData": [True],
                    }
                ]
            }
        }
        rows = _parse_comparedgeo(data)
        assert rows[0]["value"] == 0
        assert rows[0]["geo_code"] == "US-CA"


class TestBuildDriver:
    """Driver construction: flags, stealth, and failure modes — no real Chrome."""

    @patch("trendspyg.explore._engine.webdriver.Chrome")
    def test_headless_flags_and_stealth(self, mock_chrome):
        driver = _build_driver(headless=True)

        assert driver is mock_chrome.return_value
        options = mock_chrome.call_args[1]["options"]
        assert "--headless=new" in options.arguments
        assert "--disable-blink-features=AutomationControlled" in options.arguments
        assert options.experimental_options["useAutomationExtension"] is False
        driver.execute_cdp_cmd.assert_called_once()  # navigator.webdriver hidden

    @patch("trendspyg.explore._engine.webdriver.Chrome")
    def test_headed_skips_headless_flags_keeps_stealth(self, mock_chrome):
        _build_driver(headless=False)

        options = mock_chrome.call_args[1]["options"]
        assert "--headless=new" not in options.arguments
        assert "--disable-blink-features=AutomationControlled" in options.arguments

    @patch(
        "trendspyg.explore._engine.webdriver.Chrome",
        side_effect=WebDriverException("no chrome"),
    )
    def test_chrome_start_failure_raises_browsererror(self, _mock):
        with pytest.raises(BrowserError) as exc_info:
            _build_driver(headless=True)
        assert "Chrome is installed" in str(exc_info.value)

    @patch("trendspyg.explore._engine.webdriver.Chrome")
    def test_cdp_stealth_failure_is_nonfatal(self, mock_chrome):
        mock_chrome.return_value.execute_cdp_cmd.side_effect = WebDriverException("no cdp")

        driver = _build_driver(headless=True)

        assert driver is mock_chrome.return_value


class TestAwaitChartFinalCheck:
    @patch("trendspyg.explore._engine.time.sleep")
    def test_ready_after_final_reload(self, _sleep):
        driver = MagicMock()
        # Not ready during the attempt; ready on the post-reload final check.
        driver.find_elements.side_effect = [[], ["svg"]]
        driver.page_source = "a normal page"

        assert _await_chart(driver, "url", attempts=1, per_attempt=1.0) == "ready"
        driver.get.assert_called_once_with("url")


class TestDismissCookieBanner:
    @patch("trendspyg.explore._engine.time.sleep")
    def test_clicks_first_matching_button(self, _sleep):
        driver = MagicMock()

        _dismiss_cookie_banner(driver)

        driver.find_element.return_value.click.assert_called_once()

    @patch("trendspyg.explore._engine.time.sleep")
    def test_absent_banner_tries_all_labels_and_moves_on(self, _sleep):
        driver = MagicMock()
        driver.find_element.side_effect = WebDriverException("not found")

        _dismiss_cookie_banner(driver)  # must not raise

        assert driver.find_element.call_count == 4


class TestWarmUp:
    """The session must carry Google's cookies before the Explore URL loads.

    2026-08-19: a cookieless ``/trends/explore`` GET from an IP Google has
    flagged is answered with the hard 429 page at once (any driver, headed or
    headless); the same GET after one visit to the Trends home page succeeds.
    """

    def test_visits_home_page(self):
        driver = MagicMock()

        _warm_up(driver)

        driver.get.assert_called_once_with("https://trends.google.com/")

    def test_driver_error_is_swallowed(self):
        driver = MagicMock()
        driver.get.side_effect = WebDriverException("net down")

        _warm_up(driver)  # best-effort: must not raise

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._await_chart", return_value="blocked")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver")
    def test_fetch_explore_warms_up_before_explore_url(self, bd, _dc, _aw, _sleep):
        driver = bd.return_value
        with pytest.raises(RateLimitError):
            _fetch_explore("bitcoin", "US", "today 12-m", 0, True, False, False)

        urls = [c.args[0] for c in driver.get.call_args_list]
        assert urls[0] == "https://trends.google.com/"
        assert urls[1].startswith("https://trends.google.com/trends/explore?")
        assert "bitcoin" in urls[1]

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._await_chart", return_value="blocked")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver")
    def test_fetch_comparison_warms_up_before_explore_url(self, bd, _dc, _aw, _sleep):
        from trendspyg.explore import _fetch_comparison

        driver = bd.return_value
        with pytest.raises(RateLimitError):
            _fetch_comparison(["bitcoin", "ethereum"], "US", "today 12-m", 0, True, False)

        urls = [c.args[0] for c in driver.get.call_args_list]
        assert urls[0] == "https://trends.google.com/"
        assert urls[1].startswith("https://trends.google.com/trends/explore?")

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._await_chart", return_value="blocked")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver")
    def test_fetch_explore_survives_failed_warm_up(self, bd, _dc, _aw, _sleep):
        driver = bd.return_value
        calls = {"n": 0}

        def _get(url):
            calls["n"] += 1
            if calls["n"] == 1:
                raise WebDriverException("home page unreachable")

        driver.get.side_effect = _get
        # Reaches the Explore load: the warm-up failure was not fatal.
        with pytest.raises(RateLimitError):
            _fetch_explore("bitcoin", "US", "today 12-m", 0, True, False, False)
        assert calls["n"] == 2


class TestCollectWidgetUrlsFiltering:
    def test_skips_non_request_events(self):
        driver = MagicMock()
        driver.get_log.return_value = [
            {
                "message": json.dumps(
                    {"message": {"method": "Network.responseReceived", "params": {}}}
                )
            }
        ]
        assert _collect_widget_urls(driver) == {}


class TestFetchExploreFallbacks:
    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._replay_widget", return_value=None)
    @patch("trendspyg.explore._engine._collect_widget_urls", return_value={"multiline": "u1"})
    @patch("trendspyg.explore._engine._await_chart", return_value="ready")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_replay_failure_after_render_raises_downloaderror(
        self, _bd, _dc, _aw, _cw, _rw, _sleep
    ):
        with pytest.raises(DownloadError) as exc_info:
            _fetch_explore("bitcoin", "US", "today 12-m", 0, True, False, False)
        assert "after the chart" in str(exc_info.value)

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._replay_widget")
    @patch("trendspyg.explore._engine._collect_widget_urls", return_value={"multiline": "u1"})
    @patch("trendspyg.explore._engine._await_chart", return_value="ready")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_missing_optional_widget_urls_fall_back_empty(
        self, _bd, _dc, _aw, _cw, mock_replay, _sleep
    ):
        # Only the multiline request was captured — related/geo were requested
        # but never issued by the page. Best-effort: empty, not an error.
        mock_replay.return_value = json.loads(_strip_xssi(MULTILINE_RAW))

        out = _fetch_explore("bitcoin", "US", "today 12-m", 0, True, True, True)

        assert out["interest_over_time"]
        assert out["related_queries"] == {"top": [], "rising": []}
        assert out["interest_by_region"] == []


class TestFormatTimeseriesDataframe:
    def test_dataframe_output(self):
        points = [{"date": "2026-01-01T00:00:00+00:00", "value": 5, "is_partial": False}]

        df = _format_timeseries(points, "dataframe")

        assert list(df.columns) == ["date", "value", "is_partial"]
        assert len(df) == 1

    def test_dataframe_without_pandas_raises_import_error(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "pandas", None)

        with pytest.raises(ImportError) as exc_info:
            _format_timeseries([], "dataframe")
        assert "pandas is required" in str(exc_info.value)


def _widget_perf_entry(kind, req):
    """A Chrome perf-log entry for a widgetdata request carrying ``req``."""
    url = (
        f"https://trends.google.com/trends/api/widgetdata/{kind}"
        f"?hl=en-US&req={json.dumps(req)}&token=ABC"
    )
    return {
        "message": json.dumps(
            {
                "message": {
                    "method": "Network.requestWillBeSent",
                    "params": {"request": {"url": url}},
                }
            }
        )
    }


class TestCollectorHardening:
    """1.5.0: related_queries pinned to the QUERY-kind request, never ENTITY.

    The Explore page issues TWO relatedsearches requests (related queries +
    related topics); before 1.5.0 the collector kept whichever came last."""

    def test_query_kind_wins_even_when_entity_comes_later(self):
        from trendspyg.explore._engine import _collect_widget_urls

        driver = MagicMock()
        driver.get_log.return_value = [
            _widget_perf_entry("relatedsearches", {"keywordType": "QUERY"}),
            _widget_perf_entry("relatedsearches", {"keywordType": "ENTITY"}),
        ]

        urls = _collect_widget_urls(driver)
        assert '"QUERY"' in urls["relatedsearches"]
        assert '"ENTITY"' not in urls["relatedsearches"]

    def test_entity_only_yields_no_relatedsearches(self):
        from trendspyg.explore._engine import _collect_widget_urls

        driver = MagicMock()
        driver.get_log.return_value = [
            _widget_perf_entry("relatedsearches", {"keywordType": "ENTITY"}),
            _widget_perf_entry("multiline", {"comparisonItem": [{}]}),
        ]

        urls = _collect_widget_urls(driver)
        assert "relatedsearches" not in urls  # topics data must never pose as queries
        assert "multiline" in urls

    def test_unknown_kind_falls_back_to_old_behavior(self):
        from trendspyg.explore._engine import _collect_widget_urls

        driver = MagicMock()
        driver.get_log.return_value = [
            _widget_perf_entry("relatedsearches", {"restriction": {}}),  # no keywordType
        ]

        urls = _collect_widget_urls(driver)
        assert "relatedsearches" in urls  # defensive: Google dropping the field

    def test_req_keyword_type_parses_and_survives_garbage(self):
        from trendspyg.explore._engine import _req_keyword_type

        good = (
            "https://trends.google.com/trends/api/widgetdata/relatedsearches"
            f"?req={json.dumps({'keywordType': 'ENTITY'})}&token=T"
        )
        assert _req_keyword_type(good) == "ENTITY"
        assert _req_keyword_type("https://x.test/widgetdata/relatedsearches?token=T") == ""
        assert _req_keyword_type("not a url at all") == ""


class TestGprop:
    """gprop= (new in 1.5.0): YouTube/News/Images/Shopping properties."""

    def test_url_carries_gprop_only_when_set(self):
        assert "gprop=youtube" in _build_explore_url("bitcoin", "US", "today 12-m", 0, "youtube")
        assert "gprop" not in _build_explore_url("bitcoin", "US", "today 12-m", 0, "")

    @pytest.mark.parametrize("bad", ["utube", "shopping", "YOUTUBE", 7, None])
    def test_invalid_gprop_rejected_before_browser(self, bad):
        with patch("trendspyg.explore._fetch_explore") as mock_fetch:
            with pytest.raises(InvalidParameterError, match="gprop"):
                download_google_trends_interest_over_time("bitcoin", gprop=bad)
        mock_fetch.assert_not_called()

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_web_alias_normalizes_to_empty(self, mock_fetch):
        download_google_trends_interest_over_time("bitcoin", gprop="web")
        assert mock_fetch.call_args[1]["gprop"] == ""

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_gprop_threads_to_the_engine(self, mock_fetch):
        download_google_trends_interest_over_time("bitcoin", gprop="youtube")
        assert mock_fetch.call_args[1]["gprop"] == "youtube"

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_gprop_is_part_of_the_cache_key(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        download_google_trends_interest_over_time("bitcoin", cache="disk", db_path=db)
        download_google_trends_interest_over_time(
            "bitcoin", cache="disk", db_path=db, gprop="youtube"
        )
        assert mock_fetch.call_count == 2  # web and youtube must never share entries

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_envelope_carries_gprop_and_bumped_schema(self, mock_fetch):
        env = download_google_trends_explore("bitcoin", gprop="youtube")
        assert env["gprop"] == "youtube"
        assert env["schema_version"] == EXPLORE_SCHEMA_VERSION == "1.1"

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_default_envelope_gprop_is_web(self, mock_fetch):
        env = download_google_trends_explore("bitcoin")
        assert env["gprop"] == ""


class TestDefaultCacheTtl:
    """Smart TTL split: hourly-point timeframes 1h, daily/weekly ones 24h."""

    @pytest.mark.parametrize("timeframe", ["now 1-H", "now 4-H", "now 1-d", "now 7-d", " NOW 7-d"])
    def test_now_timeframes_get_one_hour(self, timeframe):
        assert _default_cache_ttl(timeframe) == 3600.0

    @pytest.mark.parametrize(
        "timeframe", ["today 12-m", "today 3-m", "today 5-y", "all", "2024-01-01 2024-12-31"]
    )
    def test_everything_else_gets_a_day(self, timeframe):
        assert _default_cache_ttl(timeframe) == 86400.0


class TestIotCacheHooks:
    """cache= / cache_ttl= / archive= / db_path= on interest_over_time."""

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_cache_off_by_default_no_db_touched(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        download_google_trends_interest_over_time("bitcoin", db_path=db)
        assert not (tmp_path / "a.db").exists()

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_disk_miss_fetches_then_hit_skips_browser(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        first = download_google_trends_interest_over_time("bitcoin", cache="disk", db_path=db)
        assert mock_fetch.call_count == 1

        second = download_google_trends_interest_over_time("bitcoin", cache="disk", db_path=db)
        assert mock_fetch.call_count == 1  # served from disk — no second fetch
        assert second == first == FAKE_FETCH["interest_over_time"]

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_hit_renders_any_output_format(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        download_google_trends_interest_over_time("bitcoin", cache="disk", db_path=db)

        as_json = download_google_trends_interest_over_time(
            "bitcoin", cache="disk", output_format="json", db_path=db
        )
        assert json.loads(as_json) == FAKE_FETCH["interest_over_time"]
        as_csv = download_google_trends_interest_over_time(
            "bitcoin", cache="disk", output_format="csv", db_path=db
        )
        assert as_csv.startswith("date,value,is_partial")
        assert mock_fetch.call_count == 1

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_key_is_case_insensitive_but_param_sensitive(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        download_google_trends_interest_over_time("Bitcoin", cache="disk", db_path=db)
        download_google_trends_interest_over_time("BITCOIN", cache="disk", db_path=db)
        assert mock_fetch.call_count == 1  # same key — Google is case-insensitive

        download_google_trends_interest_over_time(
            "bitcoin", timeframe="now 7-d", cache="disk", db_path=db
        )
        assert mock_fetch.call_count == 2  # different timeframe — different key

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_cache_ttl_zero_age_boundary(self, mock_fetch, tmp_path, monkeypatch):
        import trendspyg.archive as archive_mod

        db = str(tmp_path / "a.db")
        download_google_trends_interest_over_time("bitcoin", cache="disk", db_path=db)

        real_time = archive_mod.time.time()
        monkeypatch.setattr(archive_mod.time, "time", lambda: real_time + 100)
        download_google_trends_interest_over_time("bitcoin", cache="disk", cache_ttl=50, db_path=db)
        assert mock_fetch.call_count == 2  # 100s old > 50s ttl — refetched

    def test_cache_true_rejected_before_browser(self):
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_interest_over_time("bitcoin", cache=True)
        assert "no in-memory cache" in str(exc_info.value)

    def test_bad_cache_string_rejected(self):
        with pytest.raises(InvalidParameterError):
            download_google_trends_interest_over_time("bitcoin", cache="memory")

    @pytest.mark.parametrize("bad_ttl", [0, -5, "1h", True])
    def test_bad_cache_ttl_rejected(self, bad_ttl):
        with pytest.raises(InvalidParameterError):
            download_google_trends_interest_over_time("bitcoin", cache="disk", cache_ttl=bad_ttl)

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_archive_stores_full_envelope_with_null_ranks(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        download_google_trends_interest_over_time("bitcoin", archive=True, db_path=db)

        envs = read_archive(source="explore", db_path=db)
        assert len(envs) == 1
        env = envs[0]
        assert env["keyword"] == "bitcoin"
        assert env["schema_version"] == EXPLORE_SCHEMA_VERSION
        assert env["interest_over_time"] == FAKE_FETCH["interest_over_time"]

        hist = get_keyword_history("bitcoin", db_path=db)
        assert len(hist) == 1
        assert hist[0]["source"] == "explore" and hist[0]["rank"] is None

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_cache_hit_is_not_archived(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        download_google_trends_interest_over_time("bitcoin", cache="disk", archive=True, db_path=db)
        download_google_trends_interest_over_time("bitcoin", cache="disk", archive=True, db_path=db)
        assert len(read_archive(source="explore", db_path=db)) == 1  # hit not re-archived

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_archive_write_failure_warns_but_returns_data(self, mock_fetch, tmp_path, monkeypatch):
        import trendspyg.explore as explore_mod

        def boom(envelope, db_path=None):
            raise RuntimeError("disk full")

        monkeypatch.setattr(explore_mod, "_store_snapshot", boom, raising=False)
        monkeypatch.setattr("trendspyg.archive._store_snapshot", boom)
        with pytest.warns(RuntimeWarning, match="archive write failed"):
            series = download_google_trends_interest_over_time(
                "bitcoin", archive=True, db_path=str(tmp_path / "a.db")
            )
        assert series == FAKE_FETCH["interest_over_time"]

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_cached_entry_preserves_original_fetched_at(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        download_google_trends_interest_over_time("bitcoin", cache="disk", db_path=db)

        entry = _explore_cache_get(
            "explore|bitcoin|US|today 12-m|0|False|False|", ttl=86400, db_path=db
        )
        assert entry is not None
        assert entry["data"] == FAKE_FETCH
        assert entry["fetched_at"].endswith("+00:00")  # real UTC stamp rides with the data


class TestExploreEnvelopeCacheHooks:
    """cache= / archive= on download_google_trends_explore (the envelope fn)."""

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_hit_returns_identical_envelope_with_original_fetched_at(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        fresh = download_google_trends_explore("bitcoin", cache="disk", db_path=db)
        hit = download_google_trends_explore("bitcoin", cache="disk", db_path=db)

        assert mock_fetch.call_count == 1
        assert hit == fresh  # byte-identical, INCLUDING the original fetched_at

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_include_flags_are_part_of_the_key(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        download_google_trends_explore("bitcoin", cache="disk", db_path=db)
        download_google_trends_explore("bitcoin", include_related=False, cache="disk", db_path=db)
        assert mock_fetch.call_count == 2  # exact-match keys: no subset-serving

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_archive_roundtrips_the_returned_envelope(self, mock_fetch, tmp_path):
        db = str(tmp_path / "a.db")
        env = download_google_trends_explore("bitcoin", archive=True, db_path=db)
        assert read_archive(source="explore", db_path=db) == [env]

    def test_cache_true_rejected(self):
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_explore("bitcoin", cache=True)
        assert "no in-memory cache" in str(exc_info.value)
