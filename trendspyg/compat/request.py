"""A pytrends-compatible ``TrendReq``, served by trendspyg's engine.

Code written for pytrends 4.9.2 runs after changing its imports::

    # from pytrends.request import TrendReq
    from trendspyg.compat.request import TrendReq

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload(["coffee"], timeframe="today 5-y")
    df = pytrends.interest_over_time()  # same DataFrame shape as pytrends

The method names, arguments and return shapes follow pytrends 4.9.2
(Apache-2.0, General Mills). This module is an independent implementation on
trendspyg's two engines.

Cost model -- the part that differs from pytrends:

* The first data call after ``build_payload`` fetches everything the payload
  can give: interest over time, related queries and every supported region
  view. Later calls on the same payload are answered from memory.
* By default (``engine="auto"``) that fetch asks Google directly, as pytrends
  did -- a few seconds -- and if Google refuses, it opens one browser session
  instead (roughly 10-40 seconds), which Google kept serving when it refused
  direct requests. ``engine="browser"`` always uses the browser;
  ``engine="http"`` never does.
* ``related_queries()`` on a 2-5 keyword payload comes with the direct answer;
  after a browser fallback it runs one more session per keyword, because
  Google's comparison page does not include them.
* Google refuses a machine after a burst: roughly 8-10 fresh browser sessions,
  or around a hundred direct requests in half an hour when measured.
  ``TrendReq(cache="disk", cookies="disk")`` makes repeats free and lets later
  browser sessions arrive as a returning visitor.

What pytrends offered that is served differently or not at all is documented
on each method and in docs/MIGRATING_FROM_PYTRENDS.md.
"""

from __future__ import annotations

import json
import re
import unicodedata
import warnings
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, TypeVar, Union

import requests

from .. import explore as _explore
from .. import keywords as _keywords
from .. import rss_downloader as _rss
from ..archive import _explore_cache_get_safely, _explore_cache_set_safely
from ..config import COUNTRIES, US_STATES
from ..downloader import validate_geo
from ..exceptions import DownloadError, InvalidParameterError, ParseError, RateLimitError
from ..explore._engine import RegionVariant, _region_variant_key
from ..explore._parsers import _strip_xssi
from .exceptions import CompatWarning, ResponseError, TooManyRequestsError

if TYPE_CHECKING:
    import pandas as pd

__all__ = ["TrendReq"]

_T = TypeVar("_T")

_GPROPS = ("", "images", "news", "youtube", "froogle")
_RESOLUTIONS = ("COUNTRY", "REGION", "CITY", "DMA")
_MAX_KEYWORDS = 5
_CATEGORIES_URL = "https://trends.google.com/trends/api/explore/pickers/category"

_NO_PROXIES = (
    "proxies= is not supported by trendspyg.compat: its browser fallback would "
    "NOT go through your proxies. To use a proxy, set the HTTPS_PROXY "
    "environment variable and pass engine='http' (direct requests follow it and "
    "no browser starts). Remove proxies= (and requests_args['proxies']) to continue."
)
_NO_MULTIRANGE = (
    "Different time ranges in one payload (pytrends' multirange) are not "
    "supported. Call build_payload once per range and compare the results."
)
_NO_CITY = (
    "resolution='CITY' is not supported: Google refused city-level data for "
    "the US when tested, and its worldwide city rows carry map coordinates "
    "instead of region codes. Use the default level, or 'DMA' for US metro areas."
)
_NO_RELATED_TOPICS = (
    "related_topics() returns no data: Google serves the related-topics widget "
    "empty to automated browser sessions. Each keyword maps to "
    "{'rising': None, 'top': None}, which is what pytrends returned when "
    "Google had no topics. related_queries() is unaffected."
)


def _slug(name: str) -> str:
    """``"Côte d'Ivoire"`` -> ``"cote_d_ivoire"`` (pytrends' ``pn`` naming)."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", plain.lower()).strip("_")


#: pytrends named countries like ``"united_states"``; built from trendspyg's
#: own country list, plus the names pytrends used that the list spells differently.
_PN_TO_GEO: Dict[str, str] = {_slug(name): code for code, name in COUNTRIES.items()}
_PN_TO_GEO.update({"czech_republic": "CZ", "turkey": "TR", "myanmar": "MM"})


def _geo_for_pn(pn: Any) -> str:
    """Accept a code (``"US"``, ``"US-CA"``) or a pytrends name (``"united_states"``)."""
    if not isinstance(pn, str) or not pn.strip():
        raise InvalidParameterError(
            "pn must be a country such as 'united_states' or a code such as 'US'."
        )
    code = pn.strip().upper()
    if code in COUNTRIES or code in US_STATES:
        return code
    geo = _PN_TO_GEO.get(_slug(pn))
    if geo is None:
        raise InvalidParameterError(
            f"Unknown pn {pn!r}. Use a country name such as 'united_states' or "
            "'japan', or a code such as 'US' or 'JP'."
        )
    return geo


def _pandas() -> Any:
    try:
        import pandas
    except ImportError as exc:
        raise ImportError(
            "trendspyg.compat returns pandas DataFrames, as pytrends did. "
            "Install pandas with: pip install trendspyg[analysis]"
        ) from exc
    return pandas


def _translated(fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    """Run ``fn``, raising pytrends' exception types for Google-side failures.

    Rate limits become :class:`TooManyRequestsError` (also a RateLimitError);
    unusable responses become :class:`ResponseError`. Setup and input errors
    (Chrome missing, a bad argument) keep their trendspyg types.
    """
    try:
        return fn(*args, **kwargs)
    except RateLimitError as exc:
        raise TooManyRequestsError(str(exc)) from exc
    except (DownloadError, ParseError) as exc:
        raise ResponseError(str(exc)) from exc


def _validate_kw_list(kw_list: Any) -> List[str]:
    """Return the cleaned terms; the same rules as trendspyg's Explore functions."""
    if isinstance(kw_list, str) or not isinstance(kw_list, (list, tuple)):
        raise InvalidParameterError(
            "kw_list must be a list of 1-5 search terms, for example ['coffee'] "
            "or ['coffee', 'tea']."
        )
    if len(kw_list) > 1:
        return _explore._validate_comparison_keywords(kw_list)
    if len(kw_list) != 1 or not isinstance(kw_list[0], str) or not kw_list[0].strip():
        raise InvalidParameterError(
            f"kw_list must hold 1-{_MAX_KEYWORDS} non-empty search terms (got {kw_list!r})."
        )
    term = kw_list[0].strip()
    if "," in term:
        raise InvalidParameterError(
            f"Keyword {term!r} contains a comma. trendspyg reads Google's Explore "
            "page, whose address separates keywords with commas, so a term "
            "containing a comma cannot be requested."
        )
    return [term]


def _epoch_seconds(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp() if iso else float("nan")


def _ranked_frame(pandas: Any, items: Sequence[Dict[str, Any]]) -> Optional["pd.DataFrame"]:
    """pytrends' related-queries table: ``query`` and ``value``, or None when empty."""
    if not items:
        return None
    return pandas.DataFrame(
        {"query": [item["query"] for item in items], "value": [item["value"] for item in items]}
    )


def _fetch_categories(hl: str) -> Dict[str, Any]:
    """Google's Explore category tree (one HTTP request, no browser)."""
    try:
        response = requests.get(_CATEGORIES_URL, params={"hl": hl}, timeout=10.0)
    except requests.RequestException as exc:
        raise DownloadError("Could not retrieve the Google Trends category list.") from exc
    if response.status_code in (403, 429):
        raise RateLimitError("Google rate-limited the category list; stop and back off.")
    if not 200 <= response.status_code < 300:
        raise DownloadError(f"Google's category list returned HTTP {response.status_code}.")
    try:
        payload = json.loads(_strip_xssi(response.text))
    except ValueError as exc:
        raise ParseError("Google returned an unexpected category list.") from exc
    if not isinstance(payload, dict) or "children" not in payload:
        raise ParseError("Google returned an unexpected category list.")
    return payload


class TrendReq:
    """pytrends 4.9.2's ``TrendReq``, served by trendspyg's engines.

    Args:
        hl: Language for ``suggestions()`` and ``categories()`` labels. Explore
            data (region names) comes back in English.
        tz: Accepted for compatibility; not applied. The browser reports this
            machine's own timezone to Google.
        geo: Default region code for ``build_payload`` (``""`` = worldwide).
        timeout, retries, backoff_factor: Accepted for compatibility; not
            applied. trendspyg uses its own timeouts and reload ladder.
        proxies: Must be empty. Proxies are refused rather than silently
            ignored, because requests would come from this machine.
        requests_args: Accepted for compatibility and ignored, except that a
            ``proxies`` entry is refused for the same reason.
        cache: ``False`` (default) or ``"disk"``: serve an identical recent
            payload from trendspyg's local cache with no browser session.
        cookies: ``False`` (default) or ``"disk"``: reuse Google's session
            cookies between sessions, so later sessions arrive as a returning
            visitor. Keeps a Google cookie on disk.
        headless: Run Chrome without a window (default True).
        engine: ``"auto"`` (default): ask Google directly, as pytrends did,
            and open a browser session only if Google refuses. ``"browser"``
            always uses the browser; ``"http"`` never starts Chrome and raises
            :class:`TooManyRequestsError` when Google refuses.
    """

    def __init__(
        self,
        hl: str = "en-US",
        tz: int = 360,
        geo: str = "",
        timeout: Any = (2, 5),
        proxies: Any = "",
        retries: int = 0,
        backoff_factor: float = 0,
        requests_args: Optional[Dict[str, Any]] = None,
        *,
        cache: Union[bool, str] = False,
        cookies: Union[bool, str] = False,
        headless: bool = True,
        engine: str = "auto",
    ) -> None:
        _pandas()
        if proxies or (requests_args and "proxies" in requests_args):
            raise InvalidParameterError(_NO_PROXIES)
        if not isinstance(geo, str):
            raise InvalidParameterError(
                "geo must be one region code such as 'US' or '' (worldwide); "
                "several regions at once are not supported."
            )
        self._use_disk_cache = _explore._validate_explore_cache(cache, None)
        self._cookie_path = _explore._validate_explore_cookies(cookies)
        self._engine = _explore._validate_engine(engine)
        self.hl = hl
        self.tz = tz
        self.geo = validate_geo(geo) if geo else ""
        self.kw_list: List[str] = []
        self.timeout = timeout
        self.proxies = proxies
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.requests_args = requests_args or {}
        self.headless = headless
        self._keywords: List[str] = []
        self._cat = 0
        self._timeframe = "today 5-y"
        self._gprop = ""
        self._memo: Dict[Any, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    # Payload
    # ------------------------------------------------------------------ #

    def build_payload(
        self,
        kw_list: List[str],
        cat: int = 0,
        timeframe: Union[str, List[str]] = "today 5-y",
        geo: str = "",
        gprop: str = "",
    ) -> None:
        """Set the keywords, category, time range, region and property to analyze.

        Validated here, before any browser starts. No request is made until a
        data method is called. Differences from pytrends: a list of time ranges
        (multirange) raises NotImplementedError, and a keyword containing a
        comma is refused.
        """
        if gprop not in _GPROPS:
            raise ValueError(
                "gprop must be empty (to indicate web), images, news, youtube, or froogle"
            )
        if isinstance(timeframe, list):
            raise NotImplementedError(_NO_MULTIRANGE)
        if not isinstance(timeframe, str) or not timeframe.strip():
            raise InvalidParameterError("timeframe must be a string such as 'today 5-y'.")
        if isinstance(cat, bool) or not isinstance(cat, int) or cat < 0:
            raise InvalidParameterError(f"cat must be a category id >= 0 (got {cat!r}).")
        if not isinstance(geo, str):
            raise InvalidParameterError(
                "geo must be one region code such as 'US' or '' (worldwide); "
                "several regions in one payload are not supported."
            )
        keywords = _validate_kw_list(kw_list)
        payload_geo = geo or self.geo
        self.geo = validate_geo(payload_geo) if payload_geo else ""
        self.kw_list = list(kw_list)
        self._keywords = keywords
        self._cat = cat
        self._timeframe = timeframe.strip()
        self._gprop = gprop
        self._memo = {}

    def _require_payload(self) -> None:
        if not self.kw_list:
            raise InvalidParameterError("Call build_payload(kw_list=[...]) before requesting data.")

    def _region_variants(self) -> List[RegionVariant]:
        """The extra region views fetched in the same session as the main data."""
        variants: List[RegionVariant] = [("", True)]
        if self.geo == "US":
            variants += [("DMA", False), ("DMA", True)]
        return variants

    def _fetch(
        self,
        keywords: List[str],
        *,
        want_related: bool,
        want_geo: bool,
        variants: Sequence[RegionVariant],
    ) -> Dict[str, Any]:
        """One fetch (direct, a browser session, or a disk-cache hit) for these keywords."""
        cache_key = "compat|" + json.dumps(
            [
                [kw.lower() for kw in keywords],
                self.geo,
                self._timeframe,
                self._cat,
                self._gprop,
                want_related,
                want_geo,
                [list(variant) for variant in variants],
            ]
        )
        if self._use_disk_cache:
            hit = _explore_cache_get_safely(cache_key, _explore._default_cache_ttl(self._timeframe))
            if hit is not None:
                return dict(hit["data"])
        common: Dict[str, Any] = {
            "geo": self.geo,
            "timeframe": self._timeframe,
            "category": self._cat,
            "headless": self.headless,
            "want_geo": want_geo,
            "gprop": self._gprop,
            "cookie_path": self._cookie_path,
            "region_variants": variants,
        }
        if len(keywords) == 1:
            data = _translated(
                _explore._run_engine,
                self._engine,
                _explore._fetch_explore,
                _explore._fetch_explore_http,
                keyword=keywords[0],
                want_related=want_related,
                **common,
            )
        else:
            data = _translated(
                _explore._run_engine,
                self._engine,
                _explore._fetch_comparison,
                _explore._fetch_comparison_http,
                direct_extra={"want_related": want_related},
                keywords=keywords,
                **common,
            )
        if self._use_disk_cache:
            fetched_at = datetime.now(timezone.utc).isoformat()
            _explore_cache_set_safely(cache_key, {"fetched_at": fetched_at, "data": data})
        return data

    def _payload_data(self) -> Dict[str, Any]:
        """Everything one fetch gives for the payload, memoized."""
        if "payload" not in self._memo:
            self._memo["payload"] = self._fetch(
                self._keywords,
                want_related=True,
                want_geo=True,
                variants=self._region_variants(),
            )
        return self._memo["payload"]

    # ------------------------------------------------------------------ #
    # Keyword analysis
    # ------------------------------------------------------------------ #

    def interest_over_time(self) -> "pd.DataFrame":
        """Interest over time: a ``date`` index, one int column per keyword, ``isPartial``.

        Same shape as pytrends. An empty series returns an empty DataFrame.
        """
        pandas = _pandas()
        self._require_payload()
        points = self._payload_data()["interest_over_time"]
        if not points:
            return pandas.DataFrame([])
        if len(self._keywords) == 1:
            columns = {self.kw_list[0]: [point["value"] for point in points]}
        else:
            columns = {
                name: [point["values"][kw] for point in points]
                for name, kw in zip(self.kw_list, self._keywords)
            }
        frame = pandas.DataFrame(columns).astype("int64")
        dates = pandas.to_datetime(
            pandas.Series([_epoch_seconds(point["date"]) for point in points], dtype="float64"),
            unit="s",
        )
        frame.index = pandas.Index(dates, name="date")
        frame["isPartial"] = [bool(point["is_partial"]) for point in points]
        if not any(point["is_partial"] for point in points):
            # pytrends' column labels: inferred when a point is partial (it joins
            # two tables), object dtype when none is (it inserts column by column).
            frame.columns = pandas.Index(list(frame.columns), dtype=object)
        return frame.sort_index()

    def _region_key(self, resolution: str, inc_low_vol: bool) -> str:
        """Map pytrends' region arguments to one of the views fetched, following pytrends' rules.

        pytrends changed the level only for a worldwide payload or for the US
        (DMA/CITY/REGION); for every other region it kept the page's own level.
        """
        if resolution not in _RESOLUTIONS:
            raise InvalidParameterError(
                f"resolution must be one of {', '.join(_RESOLUTIONS)} (got {resolution!r})."
            )
        level = ""
        if self.geo == "" and resolution != "COUNTRY":
            if resolution == "CITY":
                raise NotImplementedError(_NO_CITY)
            raise NotImplementedError(
                f"resolution={resolution!r} for a worldwide payload (geo='') is not "
                "supported. Worldwide data comes by country; pass a geo such as "
                "'US' to see its regions."
            )
        if self.geo == "US" and resolution in ("DMA", "CITY", "REGION"):
            if resolution == "CITY":
                raise NotImplementedError(_NO_CITY)
            level = "DMA" if resolution == "DMA" else ""
        return _region_variant_key(level, bool(inc_low_vol))

    def interest_by_region(
        self,
        resolution: str = "COUNTRY",
        inc_low_vol: bool = False,
        inc_geo_code: bool = False,
    ) -> "pd.DataFrame":
        """Interest by region, as in pytrends: a sorted ``geoName`` index.

        Columns: ``geoCode`` (with ``inc_geo_code=True``), then one int column
        per keyword. ``inc_low_vol=True`` includes regions with little search volume, as in
        pytrends. ``resolution='DMA'`` gives US metro areas (geo ``"US"``);
        ``'CITY'`` raises NotImplementedError. Difference from pytrends: regions
        Google reports as having no data are left out instead of listed with 0.
        """
        pandas = _pandas()
        self._require_payload()
        key = self._region_key(resolution, inc_low_vol)
        data = self._payload_data()
        variants = data.get("region_variants")
        if key == _region_variant_key("", False) or variants is None:
            rows = data.get("interest_by_region", [])
        else:
            rows = variants.get(key)
            if rows is None:
                raise ResponseError(
                    f"Google did not serve this region view (resolution={resolution!r}, "
                    f"inc_low_vol={inc_low_vol!r}) in this session."
                )
        if not rows:
            return pandas.DataFrame([])
        columns: Dict[str, List[Any]] = {}
        if inc_geo_code:
            columns["geoCode"] = [row["geo_code"] for row in rows]
        for name, kw in zip(self.kw_list, self._keywords):
            if len(self._keywords) == 1:
                columns[name] = [row["value"] for row in rows]
            else:
                columns[name] = [row["values"][kw] for row in rows]
        frame = pandas.DataFrame(
            columns, index=pandas.Index([row["geo_name"] for row in rows], name="geoName")
        )
        frame.columns = pandas.Index(list(frame.columns), dtype=object)  # as pytrends builds them
        return frame.sort_index()

    def related_queries(self) -> Dict[str, Dict[str, Optional["pd.DataFrame"]]]:
        """Related queries per keyword: ``{kw: {'top': DataFrame | None, 'rising': ...}}``.

        Each table has ``query`` and ``value`` columns, as in pytrends; None when
        Google lists none. For a 2-5 keyword payload this runs one browser
        session per keyword (Google's comparison page does not include them).
        """
        pandas = _pandas()
        result: Dict[str, Dict[str, Optional["pd.DataFrame"]]] = {}
        if not self.kw_list:
            return result
        by_keyword = self._payload_data().get("related_queries_by_keyword") or {}
        for name, kw in zip(self.kw_list, self._keywords):
            if len(self._keywords) == 1:
                related = self._payload_data().get("related_queries") or {}
            elif kw in by_keyword:  # the direct comparison answer includes them
                related = by_keyword[kw]
            else:
                memo_key = ("related", kw)
                if memo_key not in self._memo:
                    self._memo[memo_key] = self._fetch(
                        [kw], want_related=True, want_geo=False, variants=()
                    )
                related = self._memo[memo_key].get("related_queries") or {}
            result[name] = {
                "top": _ranked_frame(pandas, related.get("top", [])),
                "rising": _ranked_frame(pandas, related.get("rising", [])),
            }
        return result

    def related_topics(self) -> Dict[str, Dict[str, Optional["pd.DataFrame"]]]:
        """Not served: warns :class:`CompatWarning` and returns None tables per keyword."""
        if not self.kw_list:
            return {}
        warnings.warn(_NO_RELATED_TOPICS, CompatWarning, stacklevel=2)
        return {name: {"rising": None, "top": None} for name in self.kw_list}

    def multirange_interest_over_time(self) -> "pd.DataFrame":
        """Not supported; raises NotImplementedError."""
        raise NotImplementedError(_NO_MULTIRANGE)

    def get_historical_interest(self, *args: Any, **kwargs: Any) -> "pd.DataFrame":
        """Not provided; pytrends removed it for incorrectness before its archive."""
        raise NotImplementedError(
            "get_historical_interest() was removed from pytrends itself for "
            "incorrectness, and trendspyg does not provide it."
        )

    # ------------------------------------------------------------------ #
    # Lookups (HTTP, no browser)
    # ------------------------------------------------------------------ #

    def suggestions(self, keyword: str) -> List[Dict[str, str]]:
        """Topic suggestions for a keyword: ``[{'mid', 'title', 'type'}, ...]``."""
        found = _translated(_keywords.get_keyword_suggestions, keyword, language=self.hl)
        return [
            {"mid": item["mid"], "title": item["title"], "type": item["type"]} for item in found
        ]

    def categories(self) -> Dict[str, Any]:
        """Google's category tree (``{'children': [...], 'name', 'id'}``), as in pytrends."""
        return _translated(_fetch_categories, self.hl)

    # ------------------------------------------------------------------ #
    # Trending now (served from Google's Trending Now RSS feed)
    # ------------------------------------------------------------------ #

    def _trending_now(self, geo: str) -> List[Dict[str, Any]]:
        trends = _translated(
            _rss.download_google_trends_rss,
            geo=geo,
            include_images=False,
            include_articles=False,
            cache="disk" if self._use_disk_cache else True,
        )
        return list(trends) if isinstance(trends, list) else []

    def trending_searches(self, pn: str = "united_states") -> "pd.DataFrame":
        """Searches trending now in a country: one column (``0``) of search terms.

        ``pn`` takes pytrends' names (``"united_states"``, ``"japan"``) or a code.
        Served from Google's Trending Now feed (typically 10-20 searches).
        """
        pandas = _pandas()
        return pandas.DataFrame([trend["trend"] for trend in self._trending_now(_geo_for_pn(pn))])

    def today_searches(self, pn: str = "US") -> "pd.Series":
        """Searches trending now: a Series of search terms, from the Trending Now feed."""
        pandas = _pandas()
        return pandas.Series(
            [trend["trend"] for trend in self._trending_now(_geo_for_pn(pn))], name="query"
        )

    def realtime_trending_searches(
        self, pn: str = "US", cat: str = "all", count: int = 300
    ) -> "pd.DataFrame":
        """Trending now: ``title`` and ``entityNames`` columns, at most ``count`` rows.

        Served from the Trending Now feed, which has no entity names: each
        row's ``entityNames`` holds its search term. ``cat`` must be ``"all"``;
        the feed has no category filter.
        """
        pandas = _pandas()
        if cat != "all":
            raise InvalidParameterError(
                "cat must be 'all': the Trending Now feed has no category filter. "
                "For categories use trendspyg.download_google_trends_csv(category=...)."
            )
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise InvalidParameterError(f"count must be a positive integer (got {count!r}).")
        trends = self._trending_now(_geo_for_pn(pn))[:count]
        if not trends:
            return pandas.DataFrame([])
        return pandas.DataFrame(
            {
                "title": [trend["trend"] for trend in trends],
                "entityNames": [[trend["trend"]] for trend in trends],
            }
        )

    def top_charts(
        self, date: Any, hl: str = "en-US", tz: int = 300, geo: str = "GLOBAL"
    ) -> "pd.DataFrame":
        """Not available: Google no longer serves the Year in Search endpoint it used."""
        raise NotImplementedError(
            "top_charts() is not available: Google no longer serves the Year in "
            "Search charts endpoint that pytrends used (it answers HTTP 404)."
        )
