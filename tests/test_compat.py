"""Tests for ``trendspyg.compat`` -- the pytrends-compatible front door.

No Chrome and no network: the browser engine is mocked. Its outputs are built
from raw Google widget JSON through trendspyg's real parsers, so the same raw
JSON can be fed to pytrends 4.9.2 itself (``TestPytrendsEquivalence``, which
runs only where pytrends is installed -- it is not a dependency).
"""

import copy
import inspect
import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

import trendspyg.compat as compat
from tests.test_rss_mocked import SAMPLE_RSS_XML
from trendspyg import (
    BrowserError,
    DownloadError,
    InvalidParameterError,
    RateLimitError,
    TrendspygException,
    clear_rss_cache,
)
from trendspyg.compat import CompatWarning, ResponseError, TooManyRequestsError, TrendReq
from trendspyg.explore._engine import (
    _fetch_comparison,
    _fetch_explore,
    _region_variant_key,
    _replay_region_variants,
    _rewrite_region_request,
)
from trendspyg.explore._parsers import (
    _parse_comparedgeo,
    _parse_comparedgeo_comparison,
    _parse_multiline,
    _parse_multiline_comparison,
    _parse_relatedsearches,
)

# --- Raw Google widget JSON (the shapes captured live) ---------------------- #

MULTILINE = {
    "default": {
        "timelineData": [
            {"time": "1748736000", "value": [66], "hasData": [True], "formattedValue": ["66"]},
            {"time": "1749340800", "value": [29], "hasData": [True], "formattedValue": ["29"]},
            {
                "time": "1749945600",
                "value": [57],
                "hasData": [True],
                "formattedValue": ["57"],
                "isPartial": True,
            },
        ],
        "averages": [],
    }
}

GEO = {
    "default": {
        "geoMapData": [
            {"geoCode": "US-WY", "geoName": "Wyoming", "value": [100], "hasData": [True]},
            {"geoCode": "US-CA", "geoName": "California", "value": [39], "hasData": [True]},
            {"geoCode": "US-HI", "geoName": "Hawaii", "value": [50], "hasData": [True]},
            {"geoCode": "US-ZZ", "geoName": "Nodata", "value": [0], "hasData": [False]},
        ]
    }
}

GEO_LOW_VOLUME = {
    "default": {
        "geoMapData": [
            {"geoCode": "US-WY", "geoName": "Wyoming", "value": [100], "hasData": [True]},
            {"geoCode": "US-HI", "geoName": "Hawaii", "value": [51], "hasData": [True]},
            {"geoCode": "US-ZZ", "geoName": "Nodata", "value": [3], "hasData": [True]},
        ]
    }
}

GEO_DMA = {
    "default": {
        "geoMapData": [
            {
                "geoCode": "759",
                "geoName": "Cheyenne WY-Scottsbluff NE",
                "value": [100],
                "hasData": [True],
            },
            {
                "geoCode": "678",
                "geoName": "Wichita-Hutchinson KS",
                "value": [31],
                "hasData": [True],
            },
        ]
    }
}

RELATED = {
    "default": {
        "rankedList": [
            {
                "rankedKeyword": [
                    {
                        "query": "coffee near me",
                        "value": 100,
                        "formattedValue": "100",
                        "link": "/x",
                    },
                    {"query": "coffee shop", "value": 48, "formattedValue": "48", "link": "/y"},
                ]
            },
            {
                "rankedKeyword": [
                    {"query": "coffee tariff", "value": 3650, "formattedValue": "+3,650%"},
                    {"query": "matcha latte", "value": 251450, "formattedValue": "Breakout"},
                ]
            },
        ]
    }
}

#: No rising queries: Google sends the second list empty. (A missing second
#: list crashes pytrends 4.9.2 with IndexError; trendspyg returns None for it.)
RELATED_TOP_ONLY = {
    "default": {"rankedList": [RELATED["default"]["rankedList"][0], {"rankedKeyword": []}]}
}

CMP_MULTILINE = {
    "default": {
        "timelineData": [
            {"time": "1748736000", "value": [38, 7], "hasData": [True, True]},
            {"time": "1749340800", "value": [41, 6], "hasData": [True, True], "isPartial": True},
        ],
        "averages": [39, 7],
    }
}

CMP_GEO = {
    "default": {
        "geoMapData": [
            {
                "geoCode": "US-WA",
                "geoName": "Washington",
                "value": [80, 20],
                "hasData": [True, True],
            },
            {"geoCode": "US-NY", "geoName": "New York", "value": [60, 40], "hasData": [True, True]},
            {"geoCode": "US-ZZ", "geoName": "Nodata", "value": [0, 0], "hasData": [False, False]},
        ]
    }
}

DATES = pd.to_datetime(pd.Series([1748736000, 1749340800, 1749945600], dtype="float64"), unit="s")


def single_fetch(related=RELATED, variants=True):
    """What the engine returns for one keyword, built with the real parsers."""
    data = {
        "interest_over_time": _parse_multiline(MULTILINE),
        "related_queries": _parse_relatedsearches(related),
        "interest_by_region": _parse_comparedgeo(GEO),
    }
    if variants:
        data["region_variants"] = {
            "|1": _parse_comparedgeo(GEO_LOW_VOLUME),
            "DMA|0": _parse_comparedgeo(GEO_DMA),
            "DMA|1": None,  # a variant Google refused
        }
    return data


def comparison_fetch(keywords=("coffee", "tea")):
    points, averages = _parse_multiline_comparison(CMP_MULTILINE, list(keywords))
    return {
        "interest_over_time": points,
        "averages": averages,
        "interest_by_region": _parse_comparedgeo_comparison(CMP_GEO, list(keywords)),
        "region_variants": {"|1": _parse_comparedgeo_comparison(CMP_GEO, list(keywords))},
    }


@pytest.fixture
def engine():
    """Mock both engine entry points; record every call's keyword arguments."""
    calls = []

    def fake_explore(**kwargs):
        calls.append(("explore", kwargs))
        return copy.deepcopy(single_fetch())

    def fake_comparison(**kwargs):
        calls.append(("comparison", kwargs))
        return copy.deepcopy(comparison_fetch(kwargs["keywords"]))

    with patch("trendspyg.explore._fetch_explore", side_effect=fake_explore), patch(
        "trendspyg.explore._fetch_comparison", side_effect=fake_comparison
    ):
        yield calls


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point the disk cache and cookie jar at a temporary folder."""
    monkeypatch.setenv("TRENDSPYG_DB", str(tmp_path / "trends.db"))
    monkeypatch.setenv("TRENDSPYG_COOKIES", str(tmp_path / "cookies.json"))
    return tmp_path


# --- Construction ---------------------------------------------------------- #


class TestConstruction:
    def test_pytrends_defaults(self):
        t = TrendReq()
        assert (t.hl, t.tz, t.geo, t.kw_list) == ("en-US", 360, "", [])
        assert (t.timeout, t.proxies, t.retries, t.backoff_factor) == ((2, 5), "", 0, 0)
        assert t.requests_args == {}

    def test_readme_style_arguments_accepted(self):
        t = TrendReq(hl="en-US", tz=360, timeout=(10, 25), retries=2, backoff_factor=0.1,
                     requests_args={"verify": False})  # fmt: skip
        assert t.retries == 2 and t.requests_args == {"verify": False}

    def test_geo_validated_and_uppercased(self):
        assert TrendReq(geo="us").geo == "US"
        with pytest.raises(InvalidParameterError):
            TrendReq(geo="NOPE")

    def test_geo_list_rejected(self):
        with pytest.raises(InvalidParameterError, match="one region code"):
            TrendReq(geo=["US", "GB"])

    @pytest.mark.parametrize(
        "kwargs",
        [{"proxies": ["https://34.203.233.13:80"]}, {"requests_args": {"proxies": {"https": "x"}}}],
    )
    def test_proxies_refused_not_ignored(self, kwargs):
        with pytest.raises(InvalidParameterError, match="would NOT go through your proxies"):
            TrendReq(**kwargs)

    def test_bad_cache_and_cookie_values_rejected(self):
        with pytest.raises(InvalidParameterError):
            TrendReq(cache=True)
        with pytest.raises(InvalidParameterError):
            TrendReq(cookies="yes")

    def test_missing_pandas_explains_the_extra(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "pandas", None)
        with pytest.raises(ImportError, match=r"trendspyg\[analysis\]"):
            TrendReq()

    def test_import_trendspyg_does_not_load_compat(self):
        code = "import sys, trendspyg; print('trendspyg.compat' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert out.stdout.strip() == "False", out.stderr


# --- build_payload ---------------------------------------------------------- #


class TestBuildPayload:
    def test_invalid_gprop_matches_pytrends_error(self):
        with pytest.raises(ValueError, match="gprop must be empty"):
            TrendReq().build_payload(["coffee"], gprop="maps")

    def test_multirange_timeframe_not_supported(self):
        with pytest.raises(NotImplementedError, match="multirange"):
            TrendReq().build_payload(["a", "b"], timeframe=["2024-01-01 2024-02-01"] * 2)

    @pytest.mark.parametrize("timeframe", ["", "   ", 5])
    def test_bad_timeframe(self, timeframe):
        with pytest.raises(InvalidParameterError):
            TrendReq().build_payload(["coffee"], timeframe=timeframe)

    @pytest.mark.parametrize("cat", [-1, True, "7"])
    def test_bad_category(self, cat):
        with pytest.raises(InvalidParameterError):
            TrendReq().build_payload(["coffee"], cat=cat)

    @pytest.mark.parametrize(
        "kw_list",
        [
            "coffee",
            [],
            ["   "],
            [7],
            ["a", "b", "c", "d", "e", "f"],
            ["latte, mocha"],
            ["tea", "TEA"],
        ],
    )
    def test_bad_keyword_lists(self, kw_list):
        with pytest.raises(InvalidParameterError):
            TrendReq().build_payload(kw_list)

    def test_geo_list_rejected(self):
        with pytest.raises(InvalidParameterError, match="one region code"):
            TrendReq().build_payload(["coffee"], geo=["US"])

    def test_invalid_geo_fails_before_any_fetch(self, engine):
        with pytest.raises(InvalidParameterError):
            TrendReq().build_payload(["coffee"], geo="NOPE")
        assert engine == []

    def test_geo_falls_back_and_sticks_like_pytrends(self, engine):
        t = TrendReq(geo="US")
        t.build_payload(["coffee"])
        assert t.geo == "US"
        t.build_payload(["coffee"], geo="GB")
        t.build_payload(["coffee"])
        assert t.geo == "GB"
        t.interest_over_time()
        assert engine[0][1]["geo"] == "GB"

    def test_no_request_until_data_is_asked_for(self, engine):
        TrendReq().build_payload(["coffee"], cat=71, timeframe="today 3-m", gprop="youtube")
        assert engine == []

    def test_payload_forwarded_to_engine(self, engine):
        t = TrendReq()
        t.build_payload([" coffee "], cat=71, timeframe=" today 3-m ", geo="US", gprop="youtube")
        t.interest_over_time()
        kind, kwargs = engine[0]
        assert kind == "explore"
        assert kwargs["keyword"] == "coffee"
        assert (kwargs["geo"], kwargs["timeframe"], kwargs["category"], kwargs["gprop"]) == (
            "US",
            "today 3-m",
            71,
            "youtube",
        )
        assert kwargs["want_related"] is True and kwargs["want_geo"] is True
        assert kwargs["headless"] is True and kwargs["cookie_path"] is None

    def test_rebuild_forgets_the_old_payload(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"])
        t.interest_over_time()
        t.build_payload(["coffee"])
        t.interest_over_time()
        assert len(engine) == 2

    def test_data_before_payload_explains(self):
        with pytest.raises(InvalidParameterError, match="build_payload"):
            TrendReq().interest_over_time()
        with pytest.raises(InvalidParameterError, match="build_payload"):
            TrendReq().interest_by_region()


# --- interest_over_time ----------------------------------------------------- #


class TestInterestOverTime:
    def test_single_keyword_shape(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"])
        df = t.interest_over_time()
        expected = pd.DataFrame({"coffee": [66, 29, 57]}).astype("int64")
        expected.index = pd.Index(DATES, name="date")
        expected["isPartial"] = [False, False, True]
        pd.testing.assert_frame_equal(df, expected)

    def test_column_labels_follow_pytrends_when_nothing_is_partial(self):
        complete = single_fetch()
        for point in complete["interest_over_time"]:
            point["is_partial"] = False
        with patch("trendspyg.explore._fetch_explore", return_value=complete):
            t = TrendReq()
            t.build_payload(["coffee"])
            df = t.interest_over_time()
        assert df.columns.dtype == object and df["isPartial"].tolist() == [False] * 3

    def test_comparison_keeps_given_names_and_order(self, engine):
        t = TrendReq()
        t.build_payload([" coffee", "tea"], geo="US")
        df = t.interest_over_time()
        assert list(df.columns) == [" coffee", "tea", "isPartial"]
        assert df[" coffee"].tolist() == [38, 41] and df["tea"].tolist() == [7, 6]
        assert df["isPartial"].tolist() == [False, True]
        assert str(df[" coffee"].dtype) == "int64" and df.index.name == "date"
        kind, kwargs = engine[0]
        assert kind == "comparison" and kwargs["keywords"] == ["coffee", "tea"]

    def test_one_session_serves_every_later_call(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"])
        t.interest_over_time()
        t.interest_over_time()
        t.related_queries()
        t.interest_by_region(inc_low_vol=True)
        assert len(engine) == 1

    def test_empty_series_returns_empty_frame(self):
        with patch("trendspyg.explore._fetch_explore", return_value={"interest_over_time": []}):
            t = TrendReq()
            t.build_payload(["coffee"])
            df = t.interest_over_time()
        assert df.empty and list(df.columns) == []


# --- interest_by_region ----------------------------------------------------- #


class TestInterestByRegion:
    def test_default_sorted_by_name_without_no_data_rows(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"], geo="US")
        df = t.interest_by_region()
        expected = pd.DataFrame(
            {"coffee": [39, 50, 100]},
            index=pd.Index(["California", "Hawaii", "Wyoming"], name="geoName"),
        )
        expected.columns = pd.Index(["coffee"], dtype=object)  # pytrends' labels
        pd.testing.assert_frame_equal(df, expected)

    def test_geo_code_column_comes_first(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"], geo="US")
        df = t.interest_by_region(inc_geo_code=True)
        assert list(df.columns) == ["geoCode", "coffee"]
        assert df.loc["Hawaii", "geoCode"] == "US-HI"

    def test_low_volume_view(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"], geo="US")
        df = t.interest_by_region(resolution="COUNTRY", inc_low_vol=True, inc_geo_code=False)
        assert df.to_dict()["coffee"] == {"Hawaii": 51, "Nodata": 3, "Wyoming": 100}

    def test_us_dma_view(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"], geo="US")
        df = t.interest_by_region(resolution="DMA", inc_geo_code=True)
        assert df.loc["Wichita-Hutchinson KS"].tolist() == ["678", 31]

    def test_refused_view_raises_response_error(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"], geo="US")
        with pytest.raises(ResponseError, match="did not serve this region view"):
            t.interest_by_region(resolution="DMA", inc_low_vol=True)

    def test_us_region_is_the_default_level(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"], geo="US")
        pd.testing.assert_frame_equal(
            t.interest_by_region(resolution="REGION"), t.interest_by_region()
        )

    def test_other_geos_ignore_resolution_like_pytrends(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"], geo="GB")
        pd.testing.assert_frame_equal(
            t.interest_by_region(resolution="DMA"), t.interest_by_region()
        )

    def test_variants_requested_per_geo(self, engine):
        for geo, expected in (
            ("US", [("", True), ("DMA", False), ("DMA", True)]),
            ("GB", [("", True)]),
        ):
            t = TrendReq()
            t.build_payload(["coffee"], geo=geo)
            t.interest_over_time()
            assert list(engine[-1][1]["region_variants"]) == expected

    @pytest.mark.parametrize(
        "geo, resolution, message",
        [
            ("", "CITY", "CITY"),
            ("US", "CITY", "CITY"),
            ("", "REGION", "worldwide"),
            ("", "DMA", "worldwide"),
        ],
    )
    def test_unsupported_levels_raise_not_implemented(self, engine, geo, resolution, message):
        t = TrendReq()
        t.build_payload(["coffee"], geo=geo)
        with pytest.raises(NotImplementedError, match=message):
            t.interest_by_region(resolution=resolution)
        assert engine == []  # refused before any browser session

    def test_unknown_resolution_rejected(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"])
        with pytest.raises(InvalidParameterError, match="resolution must be one of"):
            t.interest_by_region(resolution="STATE")

    def test_comparison_regions(self, engine):
        t = TrendReq()
        t.build_payload(["coffee", "tea"], geo="US")
        df = t.interest_by_region(inc_geo_code=True)
        assert list(df.index) == ["New York", "Washington"]
        assert df.loc["Washington"].tolist() == ["US-WA", 80, 20]
        assert t.interest_by_region(inc_low_vol=True).shape == (2, 2)

    def test_missing_region_widget_gives_empty_frame(self):
        with patch("trendspyg.explore._fetch_explore", return_value={"interest_over_time": []}):
            t = TrendReq()
            t.build_payload(["coffee"], geo="US")
            assert t.interest_by_region().empty
            assert t.interest_by_region(resolution="DMA").empty


# --- related queries / topics ---------------------------------------------- #


class TestRelated:
    def test_single_keyword_tables(self, engine):
        t = TrendReq()
        t.build_payload(["coffee"])
        result = t.related_queries()
        assert list(result) == ["coffee"] and list(result["coffee"]) == ["top", "rising"]
        pd.testing.assert_frame_equal(
            result["coffee"]["top"],
            pd.DataFrame({"query": ["coffee near me", "coffee shop"], "value": [100, 48]}),
        )
        assert result["coffee"]["rising"]["value"].tolist() == [3650, 251450]

    @pytest.mark.parametrize(
        "related",
        [RELATED_TOP_ONLY, {"default": {"rankedList": [RELATED["default"]["rankedList"][0]]}}],
    )
    def test_empty_or_missing_list_is_none_like_pytrends(self, related):
        with patch("trendspyg.explore._fetch_explore", return_value=single_fetch(related=related)):
            t = TrendReq()
            t.build_payload(["coffee"])
            assert t.related_queries()["coffee"]["rising"] is None

    def test_browser_comparison_adds_one_session_per_keyword_once(self, engine):
        # The direct engine is offline in tests, so "auto" falls back to the browser,
        # whose comparison page carries no related queries.
        t = TrendReq()
        t.build_payload(["coffee", "tea"])
        first = t.related_queries()
        t.related_queries()
        assert list(first) == ["coffee", "tea"]
        assert [(kind, kw.get("keyword")) for kind, kw in engine] == [
            ("comparison", None),
            ("explore", "coffee"),
            ("explore", "tea"),
        ]
        assert all(kw["want_geo"] is False and kw["region_variants"] == () for _, kw in engine[1:])

    def test_direct_comparison_answer_includes_related_queries(self, engine):
        direct = comparison_fetch()
        direct["related_queries_by_keyword"] = {
            "coffee": _parse_relatedsearches(RELATED),
            "tea": _parse_relatedsearches(RELATED_TOP_ONLY),
        }
        with patch("trendspyg.explore._fetch_comparison_http", return_value=direct) as http:
            t = TrendReq()
            t.build_payload(["coffee", "tea"], geo="US")
            result = t.related_queries()
        assert engine == []  # no browser session at all
        assert http.call_args.kwargs["want_related"] is True
        assert result["coffee"]["top"]["query"].tolist() == ["coffee near me", "coffee shop"]
        assert result["tea"]["rising"] is None

    def test_no_payload_returns_empty_dict(self):
        assert TrendReq().related_queries() == {}
        assert TrendReq().related_topics() == {}

    def test_related_topics_warns_and_returns_none_tables(self, engine):
        t = TrendReq()
        t.build_payload(["coffee", "tea"])
        with pytest.warns(CompatWarning, match="related-topics widget"):
            result = t.related_topics()
        assert result == {
            "coffee": {"rising": None, "top": None},
            "tea": {"rising": None, "top": None},
        }
        assert engine == []  # no session spent on data Google will not serve


# --- engines ------------------------------------------------------------------ #


class TestEngines:
    def test_auto_uses_the_direct_answer_without_a_browser(self, engine):
        with patch("trendspyg.explore._fetch_explore_http", return_value=single_fetch()) as http:
            t = TrendReq()
            t.build_payload(["coffee"], cat=71, timeframe="today 3-m", geo="US", gprop="news")
            df = t.interest_over_time()
            regions = t.interest_by_region(resolution="DMA")
        assert engine == [] and df["coffee"].tolist() == [66, 29, 57] and len(regions) == 2
        assert http.call_args.kwargs == {
            "keyword": "coffee",
            "geo": "US",
            "timeframe": "today 3-m",
            "category": 71,
            "want_related": True,
            "want_geo": True,
            "gprop": "news",
            "region_variants": [("", True), ("DMA", False), ("DMA", True)],
        }

    def test_browser_engine_never_asks_directly(self, engine):
        with patch("trendspyg.explore._fetch_explore_http", side_effect=AssertionError) as http:
            t = TrendReq(engine="browser")
            t.build_payload(["coffee"])
            t.interest_over_time()
        assert not http.called and [kind for kind, _ in engine] == ["explore"]

    def test_http_engine_never_starts_a_browser(self, engine):
        with patch("trendspyg.explore._fetch_explore_http", side_effect=RateLimitError("refused")):
            t = TrendReq(engine="http")
            t.build_payload(["coffee"])
            with pytest.raises(TooManyRequestsError):
                t.interest_over_time()
        assert engine == []

    def test_unknown_engine_rejected(self):
        with pytest.raises(InvalidParameterError, match="Invalid engine"):
            TrendReq(engine="fast")


# --- disk cache and cookies -------------------------------------------------- #


class TestDiskCacheAndCookies:
    def test_disk_cache_makes_a_repeat_free(self, engine, isolated_store):
        for _ in range(2):
            t = TrendReq(cache="disk")
            t.build_payload(["coffee"], geo="US")
            df = t.interest_over_time()
        assert len(engine) == 1
        assert df["coffee"].tolist() == [66, 29, 57]

    def test_cache_key_separates_payloads(self, engine, isolated_store):
        for geo in ("US", "GB"):
            t = TrendReq(cache="disk")
            t.build_payload(["coffee"], geo=geo)
            t.interest_over_time()
        assert len(engine) == 2

    def test_cookie_jar_path_forwarded(self, engine, isolated_store):
        t = TrendReq(cookies="disk")
        t.build_payload(["coffee"])
        t.interest_over_time()
        assert engine[0][1]["cookie_path"] == str(isolated_store / "cookies.json")


# --- exceptions --------------------------------------------------------------- #


class TestExceptions:
    def _payload_raising(self, error):
        with patch("trendspyg.explore._fetch_explore", side_effect=error):
            t = TrendReq()
            t.build_payload(["coffee"])
            t.interest_over_time()

    def test_rate_limit_becomes_too_many_requests(self):
        original = RateLimitError("blocked")
        with pytest.raises(TooManyRequestsError) as info:
            self._payload_raising(original)
        err = info.value
        assert isinstance(err, RateLimitError) and isinstance(err, ResponseError)
        assert isinstance(err, TrendspygException)
        assert err.response is None and err.__cause__ is original

    @pytest.mark.parametrize("error", [DownloadError("x"), compat.request.ParseError("x")])
    def test_bad_data_becomes_response_error(self, error):
        with pytest.raises(ResponseError) as info:
            self._payload_raising(error)
        assert not isinstance(info.value, TooManyRequestsError)

    def test_setup_errors_keep_their_type(self):
        with pytest.raises(BrowserError):
            self._payload_raising(BrowserError("no chrome"))

    def test_exceptions_module_mirrors_pytrends(self):
        from trendspyg.compat import exceptions

        assert issubclass(exceptions.TooManyRequestsError, exceptions.ResponseError)
        assert exceptions.ResponseError("m", "resp").response == "resp"


# --- lookups ------------------------------------------------------------------ #


def _http(status=200, text=""):
    response = MagicMock()
    response.status_code = status
    response.text = text
    return response


class TestLookups:
    def test_suggestions_use_hl_and_keep_pytrends_keys(self):
        body = (
            ')]}\',\n{"default":{"topics":[{"mid":"/m/02vqfm","title":"Coffee","type":"Drink"}]}}'
        )
        with patch("trendspyg.keywords.requests.get", return_value=_http(text=body)) as get:
            found = TrendReq(hl="fr").suggestions("compat-coffee-unique")
        assert found == [{"mid": "/m/02vqfm", "title": "Coffee", "type": "Drink"}]
        assert get.call_args.kwargs["params"] == {"hl": "fr"}

    def test_suggestions_rate_limit(self):
        with patch("trendspyg.keywords.requests.get", return_value=_http(429)):
            with pytest.raises(TooManyRequestsError):
                TrendReq().suggestions("compat-rate-limit-unique")

    def test_categories_tree(self):
        tree_json = '{"children":[{"name":"Arts","id":3}],"name":"All categories","id":0}'
        body = ")]}'\n" + tree_json
        with patch("trendspyg.compat.request.requests.get", return_value=_http(text=body)) as get:
            tree = TrendReq(hl="de").categories()
        assert tree["children"][0]["id"] == 3 and tree["id"] == 0
        assert get.call_args.kwargs["params"] == {"hl": "de"}

    @pytest.mark.parametrize(
        "response, error",
        [
            (_http(429), TooManyRequestsError),
            (_http(403), TooManyRequestsError),
            (_http(500), ResponseError),
            (_http(text="<html>nope</html>"), ResponseError),
            (_http(text='{"id": 0}'), ResponseError),
        ],
    )
    def test_categories_failures(self, response, error):
        with patch("trendspyg.compat.request.requests.get", return_value=response):
            with pytest.raises(error):
                TrendReq().categories()

    def test_categories_network_failure(self):
        with patch(
            "trendspyg.compat.request.requests.get",
            side_effect=requests.ConnectionError("down"),
        ):
            with pytest.raises(ResponseError):
                TrendReq().categories()


# --- trending now (RSS) ------------------------------------------------------- #


@pytest.fixture
def rss():
    clear_rss_cache()
    response = MagicMock()
    response.content = SAMPLE_RSS_XML
    response.raise_for_status = MagicMock()
    with patch("trendspyg.rss_downloader.requests.get", return_value=response) as get:
        yield get
    clear_rss_cache()


class TestTrendingNow:
    @pytest.mark.parametrize(
        "pn, geo",
        [
            ("united_states", "US"),
            ("japan", "JP"),
            ("turkey", "TR"),
            ("czech_republic", "CZ"),
            ("cote_d_ivoire", "CI"),
            ("United Kingdom", "GB"),
            ("gb", "GB"),
            ("US-CA", "US-CA"),
        ],
    )
    def test_pn_names_and_codes(self, rss, pn, geo):
        df = TrendReq().trending_searches(pn=pn)
        assert df[0].tolist() == ["bitcoin", "ethereum"]
        assert f"geo={geo}" in rss.call_args.args[0]

    @pytest.mark.parametrize("pn", ["atlantis", "", 5])
    def test_unknown_pn(self, rss, pn):
        with pytest.raises(InvalidParameterError):
            TrendReq().trending_searches(pn=pn)

    def test_today_searches_series(self, rss):
        series = TrendReq().today_searches()
        assert isinstance(series, pd.Series) and series.name == "query"
        assert series.tolist() == ["bitcoin", "ethereum"]

    def test_realtime_columns_and_count(self, rss):
        df = TrendReq().realtime_trending_searches(pn="US", count=1)
        assert list(df.columns) == ["title", "entityNames"]
        assert df.to_dict("records") == [{"title": "bitcoin", "entityNames": ["bitcoin"]}]

    @pytest.mark.parametrize("kwargs", [{"cat": "e"}, {"count": 0}, {"count": True}])
    def test_realtime_bad_arguments(self, rss, kwargs):
        with pytest.raises(InvalidParameterError):
            TrendReq().realtime_trending_searches(**kwargs)

    def test_empty_feed(self):
        with patch("trendspyg.rss_downloader.download_google_trends_rss", return_value=[]):
            t = TrendReq()
            assert t.trending_searches().empty
            assert t.realtime_trending_searches().empty

    def test_rss_rate_limit(self):
        with patch(
            "trendspyg.rss_downloader.download_google_trends_rss",
            side_effect=RateLimitError("slow down"),
        ):
            with pytest.raises(TooManyRequestsError):
                TrendReq().today_searches()

    def test_disk_cache_mode_reaches_rss(self, isolated_store):
        with patch("trendspyg.rss_downloader.download_google_trends_rss", return_value=[]) as rss:
            TrendReq(cache="disk").today_searches()
            TrendReq().today_searches()
        assert [c.kwargs["cache"] for c in rss.call_args_list] == ["disk", True]


# --- not provided ---------------------------------------------------------------- #


class TestNotProvided:
    def test_top_charts(self):
        with pytest.raises(NotImplementedError, match="404"):
            TrendReq().top_charts(2023, hl="en-US", tz=300, geo="GLOBAL")

    def test_multirange(self):
        with pytest.raises(NotImplementedError, match="multirange"):
            TrendReq().multirange_interest_over_time()

    def test_historical_interest(self):
        with pytest.raises(NotImplementedError, match="removed from pytrends"):
            TrendReq().get_historical_interest(["coffee"], year_start=2020)


# --- the compatibility surface, pinned -------------------------------------------- #


class TestSurface:
    def test_compat_all(self):
        assert set(compat.__all__) == {
            "TrendReq",
            "ResponseError",
            "TooManyRequestsError",
            "CompatWarning",
        }

    def test_trendreq_methods(self):
        public = {name for name in vars(TrendReq) if not name.startswith("_")}
        assert public == {
            "build_payload",
            "interest_over_time",
            "interest_by_region",
            "related_queries",
            "related_topics",
            "multirange_interest_over_time",
            "get_historical_interest",
            "suggestions",
            "categories",
            "trending_searches",
            "today_searches",
            "realtime_trending_searches",
            "top_charts",
        }

    @pytest.mark.parametrize(
        "method, expected",
        [
            (
                "__init__",
                "(self, hl='en-US', tz=360, geo='', timeout=(2, 5), proxies='', retries=0, "
                "backoff_factor=0, requests_args=None, *, cache=False, cookies=False, "
                "headless=True, engine='auto')",
            ),
            ("build_payload", "(self, kw_list, cat=0, timeframe='today 5-y', geo='', gprop='')"),
            (
                "interest_by_region",
                "(self, resolution='COUNTRY', inc_low_vol=False, inc_geo_code=False)",
            ),
            ("trending_searches", "(self, pn='united_states')"),
            ("today_searches", "(self, pn='US')"),
            ("realtime_trending_searches", "(self, pn='US', cat='all', count=300)"),
            ("top_charts", "(self, date, hl='en-US', tz=300, geo='GLOBAL')"),
            ("suggestions", "(self, keyword)"),
        ],
    )
    def test_signatures_match_pytrends(self, method, expected):
        sig = inspect.signature(getattr(TrendReq, method))
        plain = sig.replace(
            parameters=[
                p.replace(annotation=inspect.Parameter.empty) for p in sig.parameters.values()
            ],
            return_annotation=inspect.Signature.empty,
        )
        assert str(plain) == expected


# --- engine: region variants ------------------------------------------------------- #

PAGE_GEO_URL = (
    "https://trends.google.com/trends/api/widgetdata/comparedgeo?hl=en-US&tz=-180&req="
    + requests.utils.quote(
        json.dumps({"geo": {"country": "US"}, "resolution": "REGION", "locale": "en-US"}), safe=""
    )
    + "&token=APP6_UEAAAAA"
)


class TestRegionVariantsEngine:
    def _query(self, url):
        from urllib.parse import parse_qs, urlsplit

        return parse_qs(urlsplit(url).query)

    def test_rewrite_changes_only_the_two_fields(self):
        url = _rewrite_region_request(PAGE_GEO_URL, "DMA", True)
        query = self._query(url)
        req = json.loads(query["req"][0])
        assert req == {
            "geo": {"country": "US"},
            "resolution": "DMA",
            "locale": "en-US",
            "includeLowSearchVolumeGeos": True,
        }
        assert query["token"] == ["APP6_UEAAAAA"] and query["tz"] == ["-180"]
        assert url.startswith("https://trends.google.com/trends/api/widgetdata/comparedgeo?")

    def test_empty_resolution_keeps_the_page_level(self):
        req = json.loads(self._query(_rewrite_region_request(PAGE_GEO_URL, "", True))["req"][0])
        assert req["resolution"] == "REGION" and req["includeLowSearchVolumeGeos"] is True

    def test_variant_keys(self):
        assert _region_variant_key("", True) == "|1"
        assert _region_variant_key("DMA", False) == "DMA|0"

    @patch("trendspyg.explore._engine._replay_widget")
    def test_refused_or_failed_variants_become_none(self, replay):
        replay.side_effect = [GEO_DMA, RateLimitError("403"), BrowserError("budget"), None]
        out = _replay_region_variants(
            MagicMock(),
            PAGE_GEO_URL,
            [("DMA", False), ("DMA", True), ("", True), ("", False)],
            _parse_comparedgeo,
            deadline=None,
        )
        assert out["DMA|0"][0]["geo_code"] == "759"
        assert out["DMA|1"] is None and out["|1"] is None and out["|0"] is None

    def test_unparseable_url_variant_is_none(self):
        bad = "https://trends.google.com/trends/api/widgetdata/comparedgeo?req=notjson&token=t"
        with patch("trendspyg.explore._engine._replay_widget") as replay:
            out = _replay_region_variants(
                MagicMock(), bad, [("DMA", False)], _parse_comparedgeo, None
            )
        assert out == {"DMA|0": None} and not replay.called

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._replay_widget")
    @patch("trendspyg.explore._engine._collect_widget_urls")
    @patch("trendspyg.explore._engine._await_chart", return_value="ready")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_fetch_explore_collects_variants_after_main_data(
        self, _bd, _dc, _aw, collect, replay, _sleep
    ):
        collect.return_value = {"multiline": "u1", "comparedgeo": PAGE_GEO_URL}
        replay.side_effect = [MULTILINE, GEO, GEO_DMA]
        out = _fetch_explore(
            "coffee", "US", "today 12-m", 0, True, False, True, region_variants=[("DMA", False)]
        )
        assert [row["geo_name"] for row in out["interest_by_region"]][0] == "Wyoming"
        assert out["region_variants"]["DMA|0"][1]["geo_code"] == "678"
        assert "DMA" in replay.call_args_list[2].args[1]

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._replay_widget")
    @patch("trendspyg.explore._engine._collect_widget_urls")
    @patch("trendspyg.explore._engine._await_chart", return_value="ready")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_fetch_explore_without_variants_is_unchanged(
        self, _bd, _dc, _aw, collect, replay, _sleep
    ):
        collect.return_value = {"multiline": "u1", "comparedgeo": PAGE_GEO_URL}
        replay.side_effect = [MULTILINE, GEO]
        out = _fetch_explore("coffee", "US", "today 12-m", 0, True, False, True)
        assert set(out) == {"interest_over_time", "interest_by_region"}
        assert replay.call_count == 2

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._replay_widget")
    @patch("trendspyg.explore._engine._collect_widget_urls_comparison")
    @patch("trendspyg.explore._engine._await_chart", return_value="ready")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver", return_value=MagicMock())
    def test_fetch_comparison_collects_variants(self, _bd, _dc, _aw, collect, replay, _sleep):
        collect.return_value = {"multiline": "u1", "comparedgeo": PAGE_GEO_URL}
        replay.side_effect = [CMP_MULTILINE, CMP_GEO, CMP_GEO]
        out = _fetch_comparison(
            ["coffee", "tea"], "US", "today 12-m", 0, True, True, region_variants=[("", True)]
        )
        assert out["region_variants"]["|1"][0]["values"] == {"coffee": 80, "tea": 20}


# --- equivalence with pytrends 4.9.2 itself ------------------------------------------- #


@pytest.fixture
def pytrends_on(request):
    """A real pytrends TrendReq whose Google calls return the raw JSON above."""
    request_mod = pytest.importorskip("pytrends.request")

    def make(kw_list, geo, related_by_kw, multiline, geo_raw):
        widgets = [
            {"id": "TIMESERIES", "request": {}, "token": "t"},
            {"id": "GEO_MAP", "request": {}, "token": "t"},
        ] + [
            {
                "id": "RELATED_QUERIES" if i == 0 else f"RELATED_QUERIES_{i}",
                "request": {
                    "restriction": {"complexKeywordsRestriction": {"keyword": [{"value": kw}]}}
                },
                "token": "t",
            }
            for i, kw in enumerate(kw_list)
        ]

        def fake_get_data(self, url, method="get", trim_chars=0, **kwargs):
            if url == request_mod.TrendReq.GENERAL_URL:
                return {"widgets": copy.deepcopy(widgets)}
            if url == request_mod.TrendReq.INTEREST_OVER_TIME_URL:
                return copy.deepcopy(multiline)
            if url == request_mod.TrendReq.INTEREST_BY_REGION_URL:
                return copy.deepcopy(geo_raw)
            req = json.loads(kwargs["params"]["req"])
            kw = req["restriction"]["complexKeywordsRestriction"]["keyword"][0]["value"]
            return copy.deepcopy(related_by_kw[kw])

        patches = [
            patch.object(request_mod.TrendReq, "GetGoogleCookie", return_value={}),
            patch.object(request_mod.TrendReq, "_get_data", fake_get_data),
        ]
        for p in patches:
            p.start()
            request.addfinalizer(p.stop)
        py = request_mod.TrendReq(hl="en-US", tz=360)
        py.build_payload(kw_list, geo=geo)
        return py

    return make


class TestPytrendsEquivalence:
    """Same raw JSON in, same DataFrames out -- checked against pytrends 4.9.2 itself."""

    def test_single_keyword(self, pytrends_on, engine):
        py = pytrends_on(["coffee"], "US", {"coffee": RELATED}, MULTILINE, GEO)
        ours = TrendReq(hl="en-US", tz=360)
        ours.build_payload(["coffee"], geo="US")
        pd.testing.assert_frame_equal(ours.interest_over_time(), py.interest_over_time())
        for geo_code in (False, True):
            theirs = py.interest_by_region(inc_geo_code=geo_code).drop(index=["Nodata"])
            pd.testing.assert_frame_equal(ours.interest_by_region(inc_geo_code=geo_code), theirs)
        for kind in ("top", "rising"):
            pd.testing.assert_frame_equal(
                ours.related_queries()["coffee"][kind], py.related_queries()["coffee"][kind]
            )

    def test_no_partial_point(self, pytrends_on):
        complete = copy.deepcopy(MULTILINE)
        del complete["default"]["timelineData"][-1]["isPartial"]
        py = pytrends_on(["coffee"], "", {"coffee": RELATED}, complete, GEO)
        data = single_fetch()
        data["interest_over_time"] = _parse_multiline(complete)
        with patch("trendspyg.explore._fetch_explore", return_value=data):
            ours = TrendReq()
            ours.build_payload(["coffee"])
            pd.testing.assert_frame_equal(ours.interest_over_time(), py.interest_over_time())

    def test_comparison(self, pytrends_on, engine):
        related = {"coffee": RELATED, "tea": RELATED_TOP_ONLY}
        py = pytrends_on(["coffee", "tea"], "US", related, CMP_MULTILINE, CMP_GEO)
        ours = TrendReq(hl="en-US", tz=360)
        ours.build_payload(["coffee", "tea"], geo="US")
        pd.testing.assert_frame_equal(ours.interest_over_time(), py.interest_over_time())
        theirs = py.interest_by_region(inc_geo_code=True).drop(index=["Nodata"])
        pd.testing.assert_frame_equal(ours.interest_by_region(inc_geo_code=True), theirs)
        with patch(
            "trendspyg.explore._fetch_explore",
            side_effect=lambda **kw: single_fetch(
                related={"coffee": RELATED, "tea": RELATED_TOP_ONLY}[kw["keyword"]]
            ),
        ):
            mine = ours.related_queries()
        theirs_related = py.related_queries()
        pd.testing.assert_frame_equal(mine["coffee"]["rising"], theirs_related["coffee"]["rising"])
        assert mine["tea"]["rising"] is None and theirs_related["tea"]["rising"] is None
