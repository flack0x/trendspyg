"""The direct engine: Explore data over HTTP, without a browser (new in 1.9.0).

Google's Explore page fetches its data in two steps, and so does this module:
one ``api/explore`` request returns the page's widgets, each carrying a token,
then one ``api/widgetdata/<name>`` request per widget returns its data. These
are the requests pytrends made. Results have exactly the shape of the browser
engine's ``_fetch_explore`` / ``_fetch_comparison`` and go through the same
parsers.

Measured 2026-10-02 from one machine: 11 of 11 varied questions answered in
0.9-7 s each with every widget (median request 0.26 s), against 16-33 s for a
browser session, with the browser's dates and regions and 23-25 of its 25
related queries. Google refused (HTTP 429) when several new sessions arrived
within seconds, while the browser engine kept answering. Hence: one session
per process carrying Google's cookie, a pause after a refusal, and the browser
as the fallback (``engine="auto"`` in :mod:`trendspyg.explore`). Requests
follow the ``HTTPS_PROXY`` / ``HTTP_PROXY`` environment variables, as
``requests`` does.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

import requests

from ..exceptions import DownloadError, ParseError, RateLimitError
from ._engine import _USER_AGENT, RegionVariant, _region_variant_key
from ._parsers import (
    _parse_comparedgeo,
    _parse_comparedgeo_comparison,
    _parse_multiline,
    _parse_multiline_comparison,
    _parse_relatedsearches,
    _strip_xssi,
)

_HOME_URL = "https://trends.google.com/"
_EXPLORE_URL = "https://trends.google.com/trends/api/explore"
_WIDGET_URL = "https://trends.google.com/trends/api/widgetdata/"
_TIMEOUT = (5.0, 20.0)
#: Seconds direct requests stay unused after Google refuses one, so a refusing
#: endpoint is not asked again on every call (the browser answers meanwhile).
_REFUSAL_PAUSE = 300.0

_session: Optional[requests.Session] = None
_paused_until = 0.0

RegionRows = List[Dict[str, Any]]


def _tz() -> int:
    """This machine's UTC offset as a browser reports it (minutes behind UTC: UTC+3 -> -180)."""
    return -(time.localtime().tm_gmtoff // 60)


def _get_session() -> requests.Session:
    """One session per process, carrying the cookie Google sets on its home page."""
    global _session
    if _session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        try:
            session.get(_HOME_URL, timeout=_TIMEOUT)
        except requests.RequestException:
            pass  # the data request that follows reports its own failure
        _session = session
    return _session


def _available() -> bool:
    """False during the pause that follows a refusal."""
    return time.monotonic() >= _paused_until


def _request(method: str, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    global _paused_until
    try:
        response = _get_session().request(method, url, params=params, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise DownloadError(f"Direct Google Trends request failed ({type(exc).__name__}).") from exc
    if response.status_code in (403, 429):
        _paused_until = time.monotonic() + _REFUSAL_PAUSE
        raise RateLimitError(
            f"Google refused a direct Trends request (HTTP {response.status_code})."
        )
    if response.status_code != 200:
        raise DownloadError(f"Direct Google Trends request returned HTTP {response.status_code}.")
    try:
        data = json.loads(_strip_xssi(response.text))
    except ValueError as exc:
        raise ParseError("Google returned unexpected data to a direct Trends request.") from exc
    if not isinstance(data, dict):
        raise ParseError("Google returned unexpected data to a direct Trends request.")
    return data


def _widgets(
    keywords: Sequence[str], geo: str, timeframe: str, category: int, gprop: str
) -> List[Dict[str, Any]]:
    """The page's widgets for these keywords, each with its request and token."""
    if not _available():
        raise RateLimitError("Direct Trends requests are paused after a recent refusal.")
    req = {
        "comparisonItem": [{"keyword": kw, "time": timeframe, "geo": geo} for kw in keywords],
        "category": category,
        "property": gprop,
    }
    params = {"hl": "en-US", "tz": _tz(), "req": json.dumps(req)}
    widgets = _request("POST", _EXPLORE_URL, params).get("widgets")
    if not isinstance(widgets, list):
        raise ParseError("Google's Explore answer had no widgets.")
    return [widget for widget in widgets if isinstance(widget, dict)]


def _widget_data(
    widget: Dict[str, Any], endpoint: str, changes: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """One widget's data; ``changes`` edits its request (e.g. another region level)."""
    try:
        request = dict(widget["request"])
        token = widget["token"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ParseError("A Google Explore widget had no request or token.") from exc
    request.update(changes or {})
    params = {"req": json.dumps(request), "token": token, "tz": _tz()}
    return _request("GET", _WIDGET_URL + endpoint, params)


def _find(widgets: List[Dict[str, Any]], widget_id: str) -> Optional[Dict[str, Any]]:
    return next((widget for widget in widgets if widget.get("id") == widget_id), None)


def _related_widgets(widgets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """``RELATED_QUERIES`` (one keyword) or ``RELATED_QUERIES_<i>`` (one per compared keyword)."""
    return [widget for widget in widgets if str(widget.get("id", "")).startswith("RELATED_QUERIES")]


def _restriction_keyword(widget: Dict[str, Any]) -> str:
    try:
        restriction = widget["request"]["restriction"]["complexKeywordsRestriction"]
        return str(restriction["keyword"][0]["value"])
    except (KeyError, IndexError, TypeError):
        return ""


def _interest_over_time(widgets: List[Dict[str, Any]]) -> Dict[str, Any]:
    widget = _find(widgets, "TIMESERIES")
    if widget is None:
        raise DownloadError("Google's Explore answer had no interest-over-time widget.")
    return _widget_data(widget, "multiline")


def _region_views(
    widget: Dict[str, Any],
    variants: Sequence[RegionVariant],
    parse: Callable[[Dict[str, Any]], RegionRows],
) -> Dict[str, Optional[RegionRows]]:
    """Extra region views; a view Google refuses is ``None``, as in the browser engine."""
    out: Dict[str, Optional[RegionRows]] = {}
    for resolution, include_low_volume in variants:
        key = _region_variant_key(resolution, include_low_volume)
        changes: Dict[str, Any] = {"includeLowSearchVolumeGeos": include_low_volume}
        if resolution:
            changes["resolution"] = resolution
        try:
            out[key] = parse(_widget_data(widget, "comparedgeo", changes)) if _available() else None
        except (RateLimitError, DownloadError, ParseError):
            out[key] = None
    return out


def _fetch_explore_http(
    keyword: str,
    geo: str,
    timeframe: str,
    category: int,
    want_related: bool,
    want_geo: bool,
    gprop: str = "",
    region_variants: Sequence[RegionVariant] = (),
) -> Dict[str, Any]:
    """The direct counterpart of ``_engine._fetch_explore``: the same result shape.

    Raises:
        RateLimitError: Google refused (HTTP 403/429), or requests are paused
            after a recent refusal.
        DownloadError: network failure, another HTTP status, or no
            interest-over-time widget.
        ParseError: Google's answer was not the expected JSON.
    """
    widgets = _widgets([keyword], geo, timeframe, category, gprop)
    result: Dict[str, Any] = {"interest_over_time": _parse_multiline(_interest_over_time(widgets))}
    if want_related:
        related = _related_widgets(widgets)
        result["related_queries"] = (
            _parse_relatedsearches(_widget_data(related[0], "relatedsearches"))
            if related
            else {"top": [], "rising": []}
        )
    if want_geo:
        geo_widget = _find(widgets, "GEO_MAP")
        if geo_widget is None:
            result["interest_by_region"] = []
        else:
            regions = _widget_data(geo_widget, "comparedgeo")
            result["interest_by_region"] = _parse_comparedgeo(regions)
            if region_variants:
                result["region_variants"] = _region_views(
                    geo_widget, region_variants, _parse_comparedgeo
                )
    return result


def _fetch_comparison_http(
    keywords: List[str],
    geo: str,
    timeframe: str,
    category: int,
    want_geo: bool,
    gprop: str = "",
    region_variants: Sequence[RegionVariant] = (),
    want_related: bool = False,
) -> Dict[str, Any]:
    """The direct counterpart of ``_engine._fetch_comparison``: the same result shape.

    ``want_related`` adds ``related_queries_by_keyword`` (``{keyword: {"top",
    "rising"}}``), which Google's answer includes per compared keyword; the
    browser engine has no equivalent. Raises as :func:`_fetch_explore_http`.
    """
    widgets = _widgets(keywords, geo, timeframe, category, gprop)
    points, averages = _parse_multiline_comparison(_interest_over_time(widgets), keywords)
    result: Dict[str, Any] = {"interest_over_time": points, "averages": averages}

    def parse(data: Dict[str, Any]) -> RegionRows:
        return _parse_comparedgeo_comparison(data, keywords)

    if want_geo:
        geo_widget = _find(widgets, "GEO_MAP")  # the combined map; per-keyword maps are suffixed
        if geo_widget is None:
            result["interest_by_region"] = []
        else:
            result["interest_by_region"] = parse(_widget_data(geo_widget, "comparedgeo"))
            if region_variants:
                result["region_variants"] = _region_views(geo_widget, region_variants, parse)
    if want_related:
        by_keyword: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for widget in _related_widgets(widgets):
            keyword = _restriction_keyword(widget)
            if keyword in keywords:
                by_keyword[keyword] = _parse_relatedsearches(
                    _widget_data(widget, "relatedsearches")
                )
        result["related_queries_by_keyword"] = by_keyword
    return result
