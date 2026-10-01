"""Tests for the direct Explore engine (``trendspyg.explore._http``) and engine selection.

A fake session answers with the raw JSON shapes Google sends, so the direct
engine's results can be compared with what the shared parsers produce. No
network: ``tests/conftest.py`` keeps the real session offline for every test.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from tests.test_compat import (
    CMP_GEO,
    CMP_MULTILINE,
    GEO,
    GEO_DMA,
    GEO_LOW_VOLUME,
    MULTILINE,
    RELATED,
    RELATED_TOP_ONLY,
)
from trendspyg import (
    DownloadError,
    InvalidParameterError,
    ParseError,
    RateLimitError,
    download_google_trends_comparison,
    download_google_trends_explore,
    download_google_trends_interest_over_time,
)
from trendspyg.explore import _http, _run_engine
from trendspyg.explore._parsers import (
    _parse_comparedgeo,
    _parse_comparedgeo_comparison,
    _parse_multiline,
    _parse_multiline_comparison,
    _parse_relatedsearches,
)


def _restriction(keyword):
    return {"complexKeywordsRestriction": {"keyword": [{"type": "BROAD", "value": keyword}]}}


def _widget(widget_id, request):
    return {"id": widget_id, "request": request, "token": "tok-" + widget_id}


SINGLE_WIDGETS = [
    _widget("TIMESERIES", {"time": "2025-10-01 2026-10-01"}),
    _widget("GEO_MAP", {"geo": {"country": "US"}, "resolution": "REGION"}),
    _widget("RELATED_TOPICS", {"restriction": _restriction("coffee"), "keywordType": "ENTITY"}),
    _widget("RELATED_QUERIES", {"restriction": _restriction("coffee"), "keywordType": "QUERY"}),
]

COMPARISON_WIDGETS = [
    _widget("TIMESERIES", {"time": "2025-10-01 2026-10-01"}),
    _widget("GEO_MAP", {"geo": {"country": "US"}, "resolution": "REGION", "combined": True}),
    _widget("TITLE_0", {}),
    _widget("GEO_MAP_0", {"geo": {"country": "US"}, "only": "coffee"}),
    _widget("RELATED_QUERIES_0", {"restriction": _restriction("coffee")}),
    _widget("TITLE_1", {}),
    _widget("GEO_MAP_1", {"geo": {"country": "US"}, "only": "tea"}),
    _widget("RELATED_QUERIES_1", {"restriction": _restriction("tea")}),
]


class _Response:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self.text = text if text is not None else ")]}',\n" + json.dumps(body)


class FakeSession:
    """Routes like Google: explore -> widgets; widgetdata/<name> -> that widget's data."""

    def __init__(self, widgets=SINGLE_WIDGETS, multiline=MULTILINE, geo=GEO, overrides=None):
        self.widgets = widgets
        self.multiline = multiline
        self.geo = geo
        self.overrides = overrides or {}  # endpoint -> _Response, takes precedence
        self.calls = []

    def request(self, method, url, params=None, timeout=None):
        endpoint = url.rsplit("/", 1)[-1]
        self.calls.append(
            {"method": method, "endpoint": endpoint, "params": params, "timeout": timeout}
        )
        if endpoint in self.overrides:
            return self.overrides[endpoint]
        if endpoint == "explore":
            return _Response(body={"widgets": self.widgets})
        req = json.loads(params["req"])
        if endpoint == "multiline":
            return _Response(body=self.multiline)
        if endpoint == "comparedgeo":
            if req.get("resolution") == "DMA":
                return _Response(body=GEO_DMA)
            if req.get("includeLowSearchVolumeGeos"):
                return _Response(body=GEO_LOW_VOLUME)
            return _Response(body=self.geo)
        keyword = req["restriction"]["complexKeywordsRestriction"]["keyword"][0]["value"]
        return _Response(body=RELATED if keyword == "coffee" else RELATED_TOP_ONLY)


@pytest.fixture
def fake(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(_http, "_session", session)
    return session


# --- results match the shared parsers --------------------------------------------- #


class TestDirectResults:
    def test_single_keyword_matches_the_parsers(self, fake):
        out = _http._fetch_explore_http(
            "coffee",
            "US",
            "today 12-m",
            0,
            want_related=True,
            want_geo=True,
            region_variants=[("", True), ("DMA", False)],
        )
        assert out == {
            "interest_over_time": _parse_multiline(MULTILINE),
            "related_queries": _parse_relatedsearches(RELATED),
            "interest_by_region": _parse_comparedgeo(GEO),
            "region_variants": {
                "|1": _parse_comparedgeo(GEO_LOW_VOLUME),
                "DMA|0": _parse_comparedgeo(GEO_DMA),
            },
        }

    def test_explore_request_shape(self, fake):
        _http._fetch_explore_http("coffee", "US", "today 12-m", 71, False, False, gprop="news")
        first = fake.calls[0]
        assert (first["method"], first["endpoint"]) == ("POST", "explore")
        assert first["params"]["hl"] == "en-US" and isinstance(first["params"]["tz"], int)
        assert json.loads(first["params"]["req"]) == {
            "comparisonItem": [{"keyword": "coffee", "time": "today 12-m", "geo": "US"}],
            "category": 71,
            "property": "news",
        }
        assert first["timeout"] == _http._TIMEOUT

    def test_widget_request_carries_token_and_changes(self, fake):
        _http._fetch_explore_http(
            "coffee", "US", "today 12-m", 0, False, True, region_variants=[("DMA", False)]
        )
        dma_call = fake.calls[-1]
        assert (
            dma_call["endpoint"] == "comparedgeo" and dma_call["params"]["token"] == "tok-GEO_MAP"
        )
        assert json.loads(dma_call["params"]["req"]) == {
            "geo": {"country": "US"},
            "resolution": "DMA",
            "includeLowSearchVolumeGeos": False,
        }

    def test_only_what_is_wanted(self, fake):
        out = _http._fetch_explore_http("coffee", "US", "today 12-m", 0, False, False)
        assert set(out) == {"interest_over_time"}
        assert [c["endpoint"] for c in fake.calls] == ["explore", "multiline"]

    def test_comparison_skips_a_related_widget_without_a_keyword(self, monkeypatch):
        widgets = COMPARISON_WIDGETS + [_widget("RELATED_QUERIES_2", {"restriction": {}})]
        session = FakeSession(widgets, CMP_MULTILINE, CMP_GEO)
        monkeypatch.setattr(_http, "_session", session)
        out = _http._fetch_comparison_http(
            ["coffee", "tea"], "US", "today 12-m", 0, False, want_related=True
        )
        assert set(out["related_queries_by_keyword"]) == {"coffee", "tea"}
        assert sum(1 for c in session.calls if c["endpoint"] == "relatedsearches") == 2

    def test_comparison_uses_the_combined_map_and_reads_related_per_keyword(self, monkeypatch):
        session = FakeSession(COMPARISON_WIDGETS, CMP_MULTILINE, CMP_GEO)
        monkeypatch.setattr(_http, "_session", session)
        out = _http._fetch_comparison_http(
            ["coffee", "tea"], "US", "today 12-m", 0, True, want_related=True
        )
        points, averages = _parse_multiline_comparison(CMP_MULTILINE, ["coffee", "tea"])
        assert out["interest_over_time"] == points and out["averages"] == averages
        assert out["interest_by_region"] == _parse_comparedgeo_comparison(
            CMP_GEO, ["coffee", "tea"]
        )
        geo_call = next(c for c in session.calls if c["endpoint"] == "comparedgeo")
        assert geo_call["params"]["token"] == "tok-GEO_MAP"
        assert out["related_queries_by_keyword"] == {
            "coffee": _parse_relatedsearches(RELATED),
            "tea": _parse_relatedsearches(RELATED_TOP_ONLY),
        }

    def test_comparison_minimal_and_variants(self, monkeypatch):
        session = FakeSession(COMPARISON_WIDGETS, CMP_MULTILINE, CMP_GEO)
        monkeypatch.setattr(_http, "_session", session)
        minimal = _http._fetch_comparison_http(["coffee", "tea"], "US", "today 12-m", 0, False)
        assert set(minimal) == {"interest_over_time", "averages"}
        full = _http._fetch_comparison_http(
            ["coffee", "tea"], "US", "today 12-m", 0, True, region_variants=[("", True)]
        )
        assert full["region_variants"]["|1"][0]["geo_name"] == "Wyoming"

    def test_missing_widgets(self, monkeypatch):
        monkeypatch.setattr(_http, "_session", FakeSession(widgets=SINGLE_WIDGETS[:1]))
        out = _http._fetch_explore_http("coffee", "US", "today 12-m", 0, True, True)
        assert out["interest_by_region"] == [] and out["related_queries"] == {
            "top": [],
            "rising": [],
        }
        monkeypatch.setattr(_http, "_session", FakeSession(COMPARISON_WIDGETS[:1], CMP_MULTILINE))
        cmp_out = _http._fetch_comparison_http(["coffee", "tea"], "US", "today 12-m", 0, True)
        assert cmp_out["interest_by_region"] == []
        monkeypatch.setattr(_http, "_session", FakeSession(widgets=SINGLE_WIDGETS[1:]))
        with pytest.raises(DownloadError, match="interest-over-time"):
            _http._fetch_explore_http("coffee", "US", "today 12-m", 0, False, False)


# --- failures and the pause after a refusal -------------------------------------------- #


class TestDirectFailures:
    @pytest.mark.parametrize("status", [429, 403])
    def test_refusal_raises_and_pauses(self, monkeypatch, status):
        session = FakeSession(overrides={"explore": _Response(status, text="")})
        monkeypatch.setattr(_http, "_session", session)
        with pytest.raises(RateLimitError, match=str(status)):
            _http._fetch_explore_http("coffee", "US", "today 12-m", 0, False, False)
        assert not _http._available()
        with pytest.raises(RateLimitError, match="paused"):
            _http._fetch_explore_http("coffee", "US", "today 12-m", 0, False, False)
        assert len(session.calls) == 1  # paused: Google was not asked again
        monkeypatch.setattr(_http, "_paused_until", 0.0)
        session.overrides = {}
        assert _http._fetch_explore_http("coffee", "US", "today 12-m", 0, False, False)

    @pytest.mark.parametrize(
        "response, error",
        [
            (_Response(500, text="oops"), DownloadError),
            (_Response(text="<html>not json</html>"), ParseError),
            (_Response(text="[1, 2]"), ParseError),
            (_Response(body={"no": "widgets"}), ParseError),
        ],
    )
    def test_bad_explore_answers(self, monkeypatch, response, error):
        monkeypatch.setattr(_http, "_session", FakeSession(overrides={"explore": response}))
        with pytest.raises(error):
            _http._fetch_explore_http("coffee", "US", "today 12-m", 0, False, False)
        assert _http._available()  # only refusals pause

    def test_network_failure(self, monkeypatch):
        session = MagicMock()
        session.request.side_effect = requests.ConnectionError("down")
        monkeypatch.setattr(_http, "_session", session)
        with pytest.raises(DownloadError, match="ConnectionError"):
            _http._fetch_explore_http("coffee", "US", "today 12-m", 0, False, False)

    def test_widget_without_token(self, monkeypatch):
        broken = [{"id": "TIMESERIES", "request": {}}]
        monkeypatch.setattr(_http, "_session", FakeSession(widgets=broken))
        with pytest.raises(ParseError, match="token"):
            _http._fetch_explore_http("coffee", "US", "today 12-m", 0, False, False)

    def test_refused_region_view_is_none_and_stops_further_views(self, monkeypatch):
        session = FakeSession()
        monkeypatch.setattr(_http, "_session", session)
        real_request = session.request

        def refuse_dma(method, url, params=None, timeout=None):
            if url.endswith("comparedgeo") and json.loads(params["req"]).get("resolution") == "DMA":
                session.calls.append({"endpoint": "comparedgeo", "refused": True})
                return _Response(429, text="")
            return real_request(method, url, params=params, timeout=timeout)

        session.request = refuse_dma
        out = _http._fetch_explore_http(
            "coffee",
            "US",
            "today 12-m",
            0,
            False,
            True,
            region_variants=[("DMA", False), ("", True)],
        )
        assert out["interest_by_region"] == _parse_comparedgeo(GEO)  # main data kept
        assert out["region_variants"] == {"DMA|0": None, "|1": None}
        assert sum(1 for c in session.calls if c["endpoint"] == "comparedgeo") == 2


# --- session and timezone --------------------------------------------------------------- #


class TestSessionAndTimezone:
    def test_one_session_per_process_with_a_home_page_cookie(self, monkeypatch):
        created = []

        class Session:
            def __init__(self):
                self.headers = {}
                self.got = []
                created.append(self)

            def get(self, url, timeout=None):
                self.got.append(url)

        monkeypatch.setattr(_http, "_session", None)
        monkeypatch.setattr(_http.requests, "Session", Session)
        first = _http._get_session()
        assert _http._get_session() is first and len(created) == 1
        assert first.got == [_http._HOME_URL]
        assert "Chrome" in first.headers["User-Agent"]

    def test_failed_warm_up_is_tolerated(self, monkeypatch):
        class Session:
            def __init__(self):
                self.headers = {}

            def get(self, url, timeout=None):
                raise requests.ConnectionError("offline")

        monkeypatch.setattr(_http, "_session", None)
        monkeypatch.setattr(_http.requests, "Session", Session)
        assert isinstance(_http._get_session(), Session)

    @pytest.mark.parametrize(
        "gmtoff, expected", [(10800, -180), (-18000, 300), (19800, -330), (0, 0)]
    )
    def test_timezone_as_a_browser_reports_it(self, monkeypatch, gmtoff, expected):
        monkeypatch.setattr(_http.time, "localtime", lambda: SimpleNamespace(tm_gmtoff=gmtoff))
        assert _http._tz() == expected


# --- engine selection ------------------------------------------------------------------- #

BROWSER_KWARGS = {
    "keyword": "coffee",
    "geo": "US",
    "timeframe": "today 12-m",
    "category": 0,
    "headless": True,
    "want_related": False,
    "want_geo": False,
    "max_load_attempts": 10,
    "per_attempt_wait": 8.0,
    "gprop": "",
    "cookie_path": None,
}


class TestRunEngine:
    def test_browser_never_asks_directly(self):
        browser, direct = MagicMock(return_value="b"), MagicMock()
        assert _run_engine("browser", browser, direct, **BROWSER_KWARGS) == "b"
        assert not direct.called and browser.call_args.kwargs == BROWSER_KWARGS

    def test_auto_prefers_the_direct_answer(self):
        browser, direct = MagicMock(), MagicMock(return_value="d")
        out = _run_engine(
            "auto", browser, direct, direct_extra={"want_related": True}, **BROWSER_KWARGS
        )
        assert out == "d" and not browser.called
        assert direct.call_args.kwargs == {
            "keyword": "coffee",
            "geo": "US",
            "timeframe": "today 12-m",
            "category": 0,
            "want_related": True,
            "want_geo": False,
            "gprop": "",
        }

    @pytest.mark.parametrize("error", [RateLimitError("429"), DownloadError("x"), ParseError("y")])
    def test_auto_falls_back_to_the_browser(self, error, caplog):
        browser, direct = MagicMock(return_value="b"), MagicMock(side_effect=error)
        with caplog.at_level("INFO", logger="trendspyg.explore"):
            assert _run_engine("auto", browser, direct, **BROWSER_KWARGS) == "b"
        assert browser.call_args.kwargs == BROWSER_KWARGS
        assert "using the browser" in caplog.text

    def test_http_raises_instead_of_falling_back(self):
        browser, direct = MagicMock(), MagicMock(side_effect=RateLimitError("429"))
        with pytest.raises(RateLimitError):
            _run_engine("http", browser, direct, **BROWSER_KWARGS)
        assert not browser.called

    def test_unexpected_errors_are_not_swallowed(self):
        browser, direct = MagicMock(), MagicMock(side_effect=ValueError("bug"))
        with pytest.raises(ValueError):
            _run_engine("auto", browser, direct, **BROWSER_KWARGS)
        assert not browser.called


FAKE_FETCH = {
    "interest_over_time": _parse_multiline(MULTILINE),
    "related_queries": _parse_relatedsearches(RELATED),
    "interest_by_region": _parse_comparedgeo(GEO),
}


class TestPublicEngineOption:
    @pytest.mark.parametrize(
        "call",
        [
            lambda: download_google_trends_interest_over_time("coffee", engine="fast"),
            lambda: download_google_trends_explore("coffee", engine="fast"),
            lambda: download_google_trends_comparison(["coffee", "tea"], engine="fast"),
        ],
    )
    def test_unknown_engine_rejected_before_any_fetch(self, call):
        with patch("trendspyg.explore._fetch_explore") as browser, patch(
            "trendspyg.explore._fetch_comparison"
        ) as cmp_browser:
            with pytest.raises(InvalidParameterError, match="Invalid engine"):
                call()
        assert not browser.called and not cmp_browser.called

    def test_default_is_the_browser(self):
        with patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH) as browser, patch(
            "trendspyg.explore._fetch_explore_http"
        ) as direct:
            download_google_trends_interest_over_time("coffee")
        assert browser.called and not direct.called

    def test_auto_serves_the_explore_envelope_directly(self):
        with patch("trendspyg.explore._fetch_explore") as browser, patch(
            "trendspyg.explore._fetch_explore_http", return_value=FAKE_FETCH
        ) as direct:
            env = download_google_trends_explore("coffee", geo="US", engine="auto")
        assert not browser.called
        assert direct.call_args.kwargs["want_related"] is True
        assert env["interest_over_time"] == FAKE_FETCH["interest_over_time"]
        assert env["related_queries"] == FAKE_FETCH["related_queries"]

    def test_http_comparison(self):
        points, averages = _parse_multiline_comparison(CMP_MULTILINE, ["coffee", "tea"])
        direct_data = {"interest_over_time": points, "averages": averages, "interest_by_region": []}
        with patch("trendspyg.explore._fetch_comparison") as browser, patch(
            "trendspyg.explore._fetch_comparison_http", return_value=direct_data
        ):
            env = download_google_trends_comparison(["coffee", "tea"], engine="http")
        assert not browser.called and env["averages"] == {"coffee": 39, "tea": 7}

    def test_disk_cache_answers_before_either_engine(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRENDSPYG_DB", str(tmp_path / "t.db"))
        with patch("trendspyg.explore._fetch_explore_http", return_value=FAKE_FETCH) as direct:
            for _ in range(2):
                download_google_trends_interest_over_time(
                    "coffee", geo="US", engine="auto", cache="disk"
                )
        assert direct.call_count == 1
