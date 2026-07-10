"""
Tests for the multi-keyword comparison feature (new in 1.1.0).

The pure parsers are tested against the REAL multi-keyword widgetdata shapes
captured live from Google (2026-07-10 spike). The public function is tested
with the browser engine (``_fetch_comparison``) mocked — no Chrome, no
network. A single live end-to-end test is marked ``network``.
"""

import json
import urllib.parse
from unittest.mock import MagicMock, patch

import pytest

from trendspyg.exceptions import (
    BrowserError,
    DownloadError,
    InvalidParameterError,
    RateLimitError,
)
from trendspyg.explore import (
    COMPARISON_SCHEMA_VERSION,
    _collect_widget_urls_comparison,
    _fetch_comparison,
    _parse_comparedgeo_comparison,
    _parse_multiline_comparison,
    _req_comparison_size,
    _validate_comparison_keywords,
    download_google_trends_comparison,
)

COMPARISON_KEYWORDS = ["bitcoin", "ethereum", "solana"]

# Real multi-keyword multiline shape, captured live 2026-07-10: one value
# array per point, aligned to the comparison's keyword order, plus averages.
COMPARISON_MULTILINE = {
    "default": {
        "timelineData": [
            {
                "time": "1751760000",
                "formattedTime": "Jul 6 - 12, 2025",
                "value": [38, 6, 4],
                "hasData": [True, True, True],
                "formattedValue": ["38", "6", "4"],
            },
            {
                "time": "1752364800",
                "value": [100, 9, 5],
                "hasData": [True, True, True],
                "formattedValue": ["100", "9", "5"],
            },
            {
                "time": "1782000000",
                "value": [41, 6, 4],
                "hasData": [True, True, True],
                "formattedValue": ["41", "6", "4"],
                "isPartial": True,
            },
        ],
        "averages": [39, 7, 5],
    }
}

# Real combined comparedgeo shape, captured live 2026-07-10.
COMPARISON_GEO = {
    "default": {
        "geoMapData": [
            {
                "geoCode": "US-WY",
                "geoName": "Wyoming",
                "value": [68, 16, 16],
                "formattedValue": ["68%", "16%", "16%"],
                "maxValueIndex": 0,
                "hasData": [True, True, True],
            },
            {
                "geoCode": "US-CA",
                "geoName": "California",
                "value": [20, 50, 30],
                "maxValueIndex": 1,
                "hasData": [True, True, True],
            },
            {
                "geoCode": "US-XX",
                "geoName": "NoData",
                "value": [0, 0, 0],
                "hasData": [False, False, False],
            },
        ]
    }
}


class TestParseMultilineComparison:
    def test_values_keyed_by_keyword_in_order(self):
        points, _ = _parse_multiline_comparison(COMPARISON_MULTILINE, COMPARISON_KEYWORDS)

        assert len(points) == 3
        assert points[0]["values"] == {"bitcoin": 38, "ethereum": 6, "solana": 4}
        assert points[1]["values"]["bitcoin"] == 100

    def test_averages_keyed_by_keyword(self):
        _, averages = _parse_multiline_comparison(COMPARISON_MULTILINE, COMPARISON_KEYWORDS)

        assert averages == {"bitcoin": 39, "ethereum": 7, "solana": 5}

    def test_is_partial_flag(self):
        points, _ = _parse_multiline_comparison(COMPARISON_MULTILINE, COMPARISON_KEYWORDS)

        assert [p["is_partial"] for p in points] == [False, False, True]

    def test_dates_are_iso(self):
        points, _ = _parse_multiline_comparison(COMPARISON_MULTILINE, COMPARISON_KEYWORDS)

        assert points[0]["date"] == "2025-07-06T00:00:00+00:00"

    def test_short_value_array_fills_zero(self):
        data = {"default": {"timelineData": [{"time": "1751760000", "value": [38]}]}}

        points, averages = _parse_multiline_comparison(data, COMPARISON_KEYWORDS)

        assert points[0]["values"] == {"bitcoin": 38, "ethereum": 0, "solana": 0}
        assert averages == {"bitcoin": 0, "ethereum": 0, "solana": 0}

    def test_empty_payload(self):
        points, averages = _parse_multiline_comparison({}, COMPARISON_KEYWORDS)

        assert points == []
        assert averages == {"bitcoin": 0, "ethereum": 0, "solana": 0}

    def test_json_safe(self):
        points, averages = _parse_multiline_comparison(COMPARISON_MULTILINE, COMPARISON_KEYWORDS)

        json.dumps({"points": points, "averages": averages})  # must not raise


class TestParseComparedGeoComparison:
    def test_row_shape_and_top_keyword(self):
        rows = _parse_comparedgeo_comparison(COMPARISON_GEO, COMPARISON_KEYWORDS)

        assert rows[0] == {
            "geo_code": "US-WY",
            "geo_name": "Wyoming",
            "values": {"bitcoin": 68, "ethereum": 16, "solana": 16},
            "top_keyword": "bitcoin",
        }
        assert rows[1]["top_keyword"] == "ethereum"  # maxValueIndex 1

    def test_skips_rows_with_no_data_for_any_keyword(self):
        rows = _parse_comparedgeo_comparison(COMPARISON_GEO, COMPARISON_KEYWORDS)

        assert len(rows) == 2
        assert all(r["geo_code"] != "US-XX" for r in rows)

    def test_missing_max_value_index_falls_back_to_argmax(self):
        data = {
            "default": {
                "geoMapData": [
                    {"geoCode": "GB", "geoName": "UK", "value": [10, 90, 5], "hasData": [True] * 3}
                ]
            }
        }

        rows = _parse_comparedgeo_comparison(data, COMPARISON_KEYWORDS)

        assert rows[0]["top_keyword"] == "ethereum"

    def test_out_of_range_max_value_index_falls_back_to_argmax(self):
        data = {
            "default": {
                "geoMapData": [
                    {
                        "geoCode": "GB",
                        "geoName": "UK",
                        "value": [10, 5, 90],
                        "maxValueIndex": 7,
                        "hasData": [True] * 3,
                    }
                ]
            }
        }

        rows = _parse_comparedgeo_comparison(data, COMPARISON_KEYWORDS)

        assert rows[0]["top_keyword"] == "solana"

    def test_empty_payload(self):
        assert _parse_comparedgeo_comparison({}, COMPARISON_KEYWORDS) == []


def _widget_url(kind, req):
    """A widgetdata URL carrying the given req payload, as Google builds them."""
    return (
        f"https://trends.google.com/trends/api/widgetdata/{kind}"
        f"?hl=en-US&tz=-120&req={urllib.parse.quote(json.dumps(req))}&token=ABC"
    )


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


class TestReqComparisonSize:
    def test_comparison_req_counts_items(self):
        url = _widget_url("comparedgeo", {"comparisonItem": [{}, {}, {}]})

        assert _req_comparison_size(url) == 3

    def test_restriction_req_is_single(self):
        url = _widget_url("relatedsearches", {"restriction": {"geo": {}}})

        assert _req_comparison_size(url) == 1

    def test_missing_req_param_is_zero(self):
        assert _req_comparison_size("https://trends.google.com/x?a=1") == 0

    def test_malformed_req_json_is_zero(self):
        assert _req_comparison_size("https://x.com/widgetdata/comparedgeo?req=%7Bnope") == 0


class TestCollectWidgetUrlsComparison:
    def test_picks_multiline_and_combined_comparedgeo_only(self):
        combined = _widget_url("comparedgeo", {"comparisonItem": [{}, {}, {}]})
        per_kw = _widget_url("comparedgeo", {"comparisonItem": [{}]})
        multiline = _widget_url("multiline", {"comparisonItem": [{}, {}, {}]})
        related = _widget_url("relatedsearches", {"restriction": {}})
        driver = MagicMock()
        driver.get_log.return_value = [
            _perf_entry(per_kw),
            _perf_entry(multiline),
            _perf_entry(combined),
            _perf_entry(related),
            _perf_entry(per_kw),
        ]

        urls = _collect_widget_urls_comparison(driver, n_keywords=3)

        assert urls == {"multiline": multiline, "comparedgeo": combined}

    def test_empty_log(self):
        driver = MagicMock()
        driver.get_log.return_value = []

        assert _collect_widget_urls_comparison(driver, n_keywords=3) == {}


class TestValidateComparisonKeywords:
    def test_plain_string_rejected(self):
        with pytest.raises(InvalidParameterError) as exc_info:
            _validate_comparison_keywords("bitcoin,ethereum")
        assert "list" in str(exc_info.value)

    def test_one_keyword_rejected(self):
        with pytest.raises(InvalidParameterError) as exc_info:
            _validate_comparison_keywords(["bitcoin"])
        assert "between 2 and 5" in str(exc_info.value)

    def test_six_keywords_rejected(self):
        with pytest.raises(InvalidParameterError):
            _validate_comparison_keywords(["a", "b", "c", "d", "e", "f"])

    def test_two_and_five_accepted(self):
        assert _validate_comparison_keywords(["a", "b"]) == ["a", "b"]
        assert len(_validate_comparison_keywords(["a", "b", "c", "d", "e"])) == 5

    def test_strips_whitespace(self):
        assert _validate_comparison_keywords([" bitcoin ", "ethereum"]) == [
            "bitcoin",
            "ethereum",
        ]

    def test_empty_item_rejected(self):
        with pytest.raises(InvalidParameterError):
            _validate_comparison_keywords(["bitcoin", "   "])

    def test_non_string_item_rejected(self):
        with pytest.raises(InvalidParameterError):
            _validate_comparison_keywords(["bitcoin", 42])

    def test_comma_keyword_rejected(self):
        with pytest.raises(InvalidParameterError) as exc_info:
            _validate_comparison_keywords(["bitcoin", "one,two"])
        assert "comma" in str(exc_info.value)

    def test_case_insensitive_duplicate_rejected(self):
        with pytest.raises(InvalidParameterError) as exc_info:
            _validate_comparison_keywords(["Bitcoin", "bitcoin"])
        assert "Duplicate" in str(exc_info.value)


FAKE_COMPARISON_FETCH = {
    "interest_over_time": [
        {
            "date": "2025-07-06T00:00:00+00:00",
            "values": {"bitcoin": 38, "ethereum": 6},
            "is_partial": False,
        },
        {
            "date": "2025-07-13T00:00:00+00:00",
            "values": {"bitcoin": 41, "ethereum": 7},
            "is_partial": True,
        },
    ],
    "averages": {"bitcoin": 39, "ethereum": 7},
    "interest_by_region": [
        {
            "geo_code": "US-WY",
            "geo_name": "Wyoming",
            "values": {"bitcoin": 68, "ethereum": 16},
            "top_keyword": "bitcoin",
        }
    ],
}


class TestComparisonApi:
    def test_function_exported(self):
        from trendspyg import download_google_trends_comparison as fn

        assert callable(fn)

    def test_schema_constant_exported(self):
        from trendspyg import COMPARISON_SCHEMA_VERSION as exported

        assert exported == COMPARISON_SCHEMA_VERSION

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON_FETCH)
    def test_envelope_shape(self, _mock):
        env = download_google_trends_comparison(["bitcoin", "ethereum"], geo="US")

        assert env["schema_version"] == COMPARISON_SCHEMA_VERSION
        assert env["source"] == "explore_comparison"
        assert env["keywords"] == ["bitcoin", "ethereum"]
        assert env["count"] == 2 == len(env["interest_over_time"])
        assert env["averages"] == {"bitcoin": 39, "ethereum": 7}
        assert set(env) == {
            "schema_version",
            "source",
            "keywords",
            "geo",
            "timeframe",
            "fetched_at",
            "count",
            "averages",
            "interest_over_time",
            "interest_by_region",
        }

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON_FETCH)
    def test_envelope_json_safe(self, _mock):
        env = download_google_trends_comparison(["bitcoin", "ethereum"])

        json.dumps(env)  # must not raise

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON_FETCH)
    def test_keywords_stripped_in_envelope(self, _mock):
        env = download_google_trends_comparison([" bitcoin ", "ethereum "])

        assert env["keywords"] == ["bitcoin", "ethereum"]

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON_FETCH)
    def test_geo_requested_by_default(self, mock):
        download_google_trends_comparison(["bitcoin", "ethereum"])

        _, kwargs = mock.call_args
        assert kwargs["want_geo"] is True

    @patch("trendspyg.explore._fetch_comparison")
    def test_include_geo_false(self, mock):
        mock.return_value = {
            "interest_over_time": FAKE_COMPARISON_FETCH["interest_over_time"],
            "averages": FAKE_COMPARISON_FETCH["averages"],
        }

        env = download_google_trends_comparison(["bitcoin", "ethereum"], include_geo=False)

        _, kwargs = mock.call_args
        assert kwargs["want_geo"] is False
        assert env["interest_by_region"] == []  # field still present — fixed shape

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON_FETCH)
    def test_retry_knobs_forwarded(self, mock):
        download_google_trends_comparison(["bitcoin", "ethereum"], max_retries=3, retry_wait=5.0)

        _, kwargs = mock.call_args
        assert kwargs["max_load_attempts"] == 3
        assert kwargs["per_attempt_wait"] == 5.0

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON_FETCH)
    def test_json_output(self, _mock):
        out = download_google_trends_comparison(["bitcoin", "ethereum"], output_format="json")

        assert isinstance(out, str)
        assert json.loads(out)["averages"]["bitcoin"] == 39

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON_FETCH)
    def test_csv_output_one_column_per_keyword(self, _mock):
        out = download_google_trends_comparison(["bitcoin", "ethereum"], output_format="csv")

        lines = out.splitlines()
        assert lines[0] == "date,bitcoin,ethereum,is_partial"
        assert lines[1].startswith("2025-07-06T00:00:00+00:00,38,6,")

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON_FETCH)
    def test_dataframe_output(self, _mock):
        df = download_google_trends_comparison(["bitcoin", "ethereum"], output_format="dataframe")

        assert list(df.columns) == ["date", "bitcoin", "ethereum", "is_partial"]
        assert len(df) == 2

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON_FETCH)
    def test_invalid_output_format_fails_before_fetch(self, mock):
        with pytest.raises(InvalidParameterError):
            download_google_trends_comparison(["bitcoin", "ethereum"], output_format="xml")

        mock.assert_not_called()  # no 30s browser run for a bad argument

    def test_invalid_geo_raises(self):
        with pytest.raises(InvalidParameterError):
            download_google_trends_comparison(["bitcoin", "ethereum"], geo="NOPE")

    def test_bad_retry_params_raise(self):
        with pytest.raises(InvalidParameterError):
            download_google_trends_comparison(["bitcoin", "ethereum"], max_retries=0)


class TestFetchComparisonEngine:
    @patch("trendspyg.explore.time.sleep")
    @patch("trendspyg.explore._await_chart", return_value="throttled")
    @patch("trendspyg.explore._dismiss_cookie_banner")
    @patch("trendspyg.explore._build_driver", return_value=MagicMock())
    def test_throttled_raises_rate_limit_with_keywords_context(self, _bd, _dc, _aw, _sleep):
        with pytest.raises(RateLimitError) as exc_info:
            _fetch_comparison(["bitcoin", "ethereum"], "US", "today 12-m", 0, True, True)
        assert "Keywords:" in str(exc_info.value)

    @patch("trendspyg.explore.time.sleep")
    @patch("trendspyg.explore._await_chart", return_value="timeout")
    @patch("trendspyg.explore._dismiss_cookie_banner")
    @patch("trendspyg.explore._build_driver", return_value=MagicMock())
    def test_timeout_raises_browser_error(self, _bd, _dc, _aw, _sleep):
        with pytest.raises(BrowserError):
            _fetch_comparison(["bitcoin", "ethereum"], "US", "today 12-m", 0, True, True)

    @patch("trendspyg.explore.time.sleep")
    @patch("trendspyg.explore._collect_widget_urls_comparison", return_value={})
    @patch("trendspyg.explore._await_chart", return_value="ready")
    @patch("trendspyg.explore._dismiss_cookie_banner")
    @patch("trendspyg.explore._build_driver", return_value=MagicMock())
    def test_missing_multiline_url_raises_download_error(self, _bd, _dc, _aw, _cw, _sleep):
        with pytest.raises(DownloadError):
            _fetch_comparison(["bitcoin", "ethereum"], "US", "today 12-m", 0, True, True)

    @patch("trendspyg.explore.time.sleep")
    @patch("trendspyg.explore._replay_widget", return_value=None)
    @patch(
        "trendspyg.explore._collect_widget_urls_comparison",
        return_value={"multiline": "http://ml"},
    )
    @patch("trendspyg.explore._await_chart", return_value="ready")
    @patch("trendspyg.explore._dismiss_cookie_banner")
    @patch("trendspyg.explore._build_driver", return_value=MagicMock())
    def test_multiline_replay_failure_raises_download_error(
        self, _bd, _dc, _aw, _cw, _replay, _sleep
    ):
        with pytest.raises(DownloadError):
            _fetch_comparison(["bitcoin", "ethereum"], "US", "today 12-m", 0, True, True)

    @patch("trendspyg.explore.time.sleep")
    @patch("trendspyg.explore._replay_widget")
    @patch("trendspyg.explore._collect_widget_urls_comparison")
    @patch("trendspyg.explore._await_chart", return_value="ready")
    @patch("trendspyg.explore._dismiss_cookie_banner")
    @patch("trendspyg.explore._build_driver")
    def test_happy_path_parses_both_widgets(self, mock_bd, _dc, _aw, mock_cw, mock_replay, _sleep):
        driver = MagicMock()
        mock_bd.return_value = driver
        mock_cw.return_value = {"multiline": "http://ml", "comparedgeo": "http://cg"}
        mock_replay.side_effect = [COMPARISON_MULTILINE, COMPARISON_GEO]

        out = _fetch_comparison(COMPARISON_KEYWORDS, "US", "today 12-m", 0, True, True)

        assert out["interest_over_time"][0]["values"]["bitcoin"] == 38
        assert out["averages"] == {"bitcoin": 39, "ethereum": 7, "solana": 5}
        assert out["interest_by_region"][0]["top_keyword"] == "bitcoin"
        driver.quit.assert_called_once()

    @patch("trendspyg.explore.time.sleep")
    @patch("trendspyg.explore._replay_widget")
    @patch(
        "trendspyg.explore._collect_widget_urls_comparison",
        return_value={"multiline": "http://ml"},
    )
    @patch("trendspyg.explore._await_chart", return_value="ready")
    @patch("trendspyg.explore._dismiss_cookie_banner")
    @patch("trendspyg.explore._build_driver")
    def test_geo_wanted_but_widget_missing_gives_empty_list(
        self, mock_bd, _dc, _aw, _cw, mock_replay, _sleep
    ):
        mock_bd.return_value = MagicMock()
        mock_replay.return_value = COMPARISON_MULTILINE

        out = _fetch_comparison(["bitcoin", "ethereum"], "US", "today 12-m", 0, True, True)

        assert out["interest_by_region"] == []

    @patch("trendspyg.explore.time.sleep")
    @patch("trendspyg.explore._replay_widget", return_value=COMPARISON_MULTILINE)
    @patch(
        "trendspyg.explore._collect_widget_urls_comparison",
        return_value={"multiline": "http://ml"},
    )
    @patch("trendspyg.explore._await_chart", return_value="ready")
    @patch("trendspyg.explore._dismiss_cookie_banner")
    @patch("trendspyg.explore._build_driver")
    def test_no_geo_skips_scroll(self, mock_bd, _dc, _aw, _cw, _replay, _sleep):
        driver = MagicMock()
        mock_bd.return_value = driver

        out = _fetch_comparison(["bitcoin", "ethereum"], "US", "today 12-m", 0, True, False)

        driver.execute_script.assert_not_called()  # no scroll without want_geo
        assert "interest_by_region" not in out


@pytest.mark.network
class TestComparisonLive:
    """Real browser hit against Google. Run with: pytest -m network"""

    def test_comparison_live(self):
        env = download_google_trends_comparison(["bitcoin", "ethereum"], geo="US")

        assert env["keywords"] == ["bitcoin", "ethereum"]
        assert len(env["interest_over_time"]) > 10
        first = env["interest_over_time"][0]["values"]
        assert set(first) == {"bitcoin", "ethereum"}
        assert all(isinstance(v, int) for v in first.values())
        json.dumps(env)
