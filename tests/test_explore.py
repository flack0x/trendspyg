"""
Tests for the Explore path (interest over time, related queries, regions).

The pure parsers are tested against the REAL widgetdata JSON shapes captured
live from Google. The public functions are tested with the browser engine
(``_fetch_explore``) mocked, so no Chrome launches and no network is touched.
A single live end-to-end test is marked ``network`` and skipped by default.
"""

import json
from unittest.mock import patch

import pytest

from trendspyg.exceptions import InvalidParameterError
from trendspyg.explore import (
    EXPLORE_SCHEMA_VERSION,
    _build_explore_url,
    _epoch_to_iso,
    _format_timeseries,
    _parse_comparedgeo,
    _parse_multiline,
    _parse_relatedsearches,
    _strip_xssi,
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
