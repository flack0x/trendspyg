#!/usr/bin/env python3
"""
Google Trends *Explore* path — keyword analysis over time.

This is the third trendspyg data path, alongside the real-time "Trending Now"
paths (``rss_downloader`` and ``downloader``). Where those answer *"what is
trending right now?"*, this answers *"how has interest in THIS keyword moved,
where is it strongest, and what do people search alongside it?"* — the
``interest_over_time`` / ``related_queries`` / ``interest_by_region`` data that
the archived ``pytrends`` was most used for.

How it works (and why it is reliable):
    Google's Explore page renders three data widgets by calling internal
    ``/trends/api/widgetdata/{multiline,relatedsearches,comparedgeo}`` endpoints
    with freshly-minted tokens. Those endpoints aggressively rate-limit raw
    HTTP clients (this is what broke pytrends), but a real browser session mints
    valid tokens and carries the right cookies. So we:

      1. Drive headless Chrome to the Explore page (reusing trendspyg's existing
         anti-bot Chrome flags).
      2. Retry-reload until the time-series chart actually renders — this clears
         the transient "Oops! Something went wrong" soft-throttle.
      3. Read the widget request URLs the page itself issued (from Chrome's
         performance log), then *replay* each one via an in-page ``fetch()`` so
         the response comes back to us with the page's own session — no token
         minting, no fragile download-button hunting.
      4. Strip Google's anti-JSON-hijack prefix and parse the known structures.

The returned data is JSON-safe by construction (ISO dates, int values, plain
lists) — agent-ready without a separate ``normalize`` pass.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Sequence, Union, cast

if TYPE_CHECKING:
    import pandas as pd

from ..archive import _explore_cache_get_safely, _explore_cache_set_safely, _store_snapshot_safely
from ..downloader import validate_geo
from ..exceptions import InvalidParameterError
from ._cookies import _default_cookie_path, _forget_cookies
from ._engine import (  # noqa: F401  — re-exported: tests + backward compatibility
    _await_chart,
    _build_driver,
    _build_explore_url,
    _chart_errored,
    _chart_ready,
    _collect_widget_urls,
    _collect_widget_urls_comparison,
    _dismiss_cookie_banner,
    _fetch_comparison,
    _fetch_explore,
    _page_blocked,
    _raise_for_chart_status,
    _replay_widget,
    _req_comparison_size,
    _warm_up,
)
from ._parsers import (  # noqa: F401  — re-exported: tests + backward compatibility
    _epoch_to_iso,
    _parse_comparedgeo,
    _parse_comparedgeo_comparison,
    _parse_multiline,
    _parse_multiline_comparison,
    _parse_relatedsearches,
    _strip_xssi,
)

# Type aliases
TimeseriesFormat = Literal["dict", "dataframe", "json", "csv"]

#: Bumped when the Explore envelope changes shape so agents can detect drift.
#: 1.1 (trendspyg 1.5.0): added the ``gprop`` field (Google property).
#: 1.2 (trendspyg 1.6.0): added ``is_empty`` — True when the interest series has
#: no non-zero point (Google answers a no-data keyword with zeros; returned as-is).
EXPLORE_SCHEMA_VERSION = "1.2"

#: Bumped when the multi-keyword ComparisonEnvelope changes shape (new in 1.1.0).
#: 1.1 (trendspyg 1.5.0): added the ``gprop`` field (Google property).
COMPARISON_SCHEMA_VERSION = "1.1"

#: Google's Explore UI compares at most 5 terms; the URL format uses ',' as the
#: keyword separator, so terms containing literal commas cannot be compared.
_MAX_COMPARISON_KEYWORDS = 5

_TIMESERIES_FORMATS = ("dict", "dataframe", "json", "csv")

#: Google properties the Explore page supports (verified live 2026-08-11).
#: "" = web search; "froogle" is Google's internal name for Shopping.
_VALID_GPROPS = ("", "images", "news", "youtube", "froogle")

# --------------------------------------------------------------------------- #
# Output formatting (interest-over-time only — already JSON-safe)
# --------------------------------------------------------------------------- #


def _format_timeseries(
    points: List[Dict[str, Any]], output_format: TimeseriesFormat
) -> Union[List[Dict[str, Any]], str, "pd.DataFrame"]:
    """Render the interest-over-time list in the requested output format."""
    if output_format == "dict":
        return points

    if output_format == "json":
        return json.dumps(points, indent=2)

    if output_format == "csv":
        import csv as _csv
        from io import StringIO

        buf = StringIO()
        writer = _csv.DictWriter(buf, fieldnames=["date", "value", "is_partial"])
        writer.writeheader()
        for point in points:
            writer.writerow(point)
        return buf.getvalue()

    if output_format == "dataframe":
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for 'dataframe' format.\n"
                "Install with: pip install trendspyg[analysis]"
            )
        return pd.DataFrame(points)

    raise InvalidParameterError(
        f"Invalid output_format: '{output_format}'. "
        "Must be one of: 'dict', 'dataframe', 'json', 'csv'"
    )


def _format_comparison(
    envelope: Dict[str, Any], output_format: TimeseriesFormat
) -> Union[Dict[str, Any], str, "pd.DataFrame"]:
    """Render a ComparisonEnvelope in the requested output format.

    ``dict``/``json`` return the full envelope. ``dataframe``/``csv`` render
    the interest-over-time series as a table with one column per keyword
    (pytrends-style): ``date, <kw1>, ..., <kwN>, is_partial``.
    """
    if output_format == "dict":
        return envelope

    if output_format == "json":
        return json.dumps(envelope, indent=2)

    keywords: List[str] = list(envelope["keywords"])
    fieldnames = ["date"] + keywords + ["is_partial"]
    table_rows = [
        {"date": p["date"], **p["values"], "is_partial": p["is_partial"]}
        for p in envelope["interest_over_time"]
    ]

    if output_format == "csv":
        import csv as _csv
        from io import StringIO

        buf = StringIO()
        writer = _csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for row in table_rows:
            writer.writerow(row)
        return buf.getvalue()

    if output_format == "dataframe":
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for 'dataframe' format.\n"
                "Install with: pip install trendspyg[analysis]"
            )
        return pd.DataFrame(table_rows, columns=fieldnames)

    raise InvalidParameterError(
        f"Invalid output_format: '{output_format}'. "
        "Must be one of: 'dict', 'dataframe', 'json', 'csv'"
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def _validate_retry_params(max_retries: int, retry_wait: float) -> None:
    """Reject retry settings that would silently produce misleading errors.

    max_retries=0 would mean zero chart-load attempts — the call would always
    end in a confusing BrowserError rather than doing no retries.
    """
    if max_retries < 1:
        raise InvalidParameterError(
            f"max_retries must be >= 1 (got {max_retries}). "
            "Each retry is one chart-load attempt; use max_retries=1 to try only once."
        )
    if retry_wait <= 0:
        raise InvalidParameterError(
            f"retry_wait must be > 0 seconds (got {retry_wait}). "
            "It is how long each attempt watches the chart before reloading."
        )


def _validate_comparison_keywords(keywords: Sequence[str]) -> List[str]:
    """Validate and clean a comparison keyword list; return the stripped terms.

    Enforces what Google's comparison actually supports (verified live):
    2-5 distinct, non-empty terms, none containing a comma (the URL separator).
    A plain string is rejected explicitly — iterating it as characters would
    produce a nonsense comparison.
    """
    if isinstance(keywords, str):
        raise InvalidParameterError(
            "keywords must be a list of 2-5 search terms, not a single string. "
            'Example: download_google_trends_comparison(["bitcoin", "ethereum"]). '
            "For one keyword use download_google_trends_interest_over_time."
        )
    cleaned: List[str] = []
    for item in keywords:
        if not isinstance(item, str) or not item.strip():
            raise InvalidParameterError(
                f"Every comparison keyword must be a non-empty string (got {item!r})."
            )
        term = item.strip()
        if "," in term:
            raise InvalidParameterError(
                f"Keyword {term!r} contains a comma. Google Trends comparisons use "
                "the comma as the keyword separator, so terms with literal commas "
                "cannot be compared."
            )
        cleaned.append(term)
    if not 2 <= len(cleaned) <= _MAX_COMPARISON_KEYWORDS:
        raise InvalidParameterError(
            f"Pass between 2 and {_MAX_COMPARISON_KEYWORDS} keywords to compare "
            f"(got {len(cleaned)}). Google Trends supports at most "
            f"{_MAX_COMPARISON_KEYWORDS} comparison terms; for a single keyword "
            "use download_google_trends_interest_over_time."
        )
    lowered = [term.lower() for term in cleaned]
    if len(set(lowered)) != len(lowered):
        duplicates = sorted({term for term in lowered if lowered.count(term) > 1})
        raise InvalidParameterError(
            f"Duplicate keyword(s) in comparison: {', '.join(duplicates)}. "
            "Google treats comparison terms case-insensitively; list each term once."
        )
    return cleaned


def _validate_explore_cache(cache: Union[bool, str], cache_ttl: Optional[float]) -> bool:
    """Validate the Explore cache args up-front; return whether the disk cache is on.

    ``cache=True`` is rejected on purpose: on the RSS path ``True`` means the
    in-memory cache, which the Explore path does not have — silently treating
    ``True`` as "disk" would make the same value mean different things on
    different paths.
    """
    if cache is True or (isinstance(cache, str) and cache != "disk"):
        raise InvalidParameterError(
            "Invalid cache: %r. The Explore path has no in-memory cache; "
            "use cache='disk' for the persistent disk cache, or cache=False (default)." % (cache,)
        )
    if cache_ttl is not None:
        if not isinstance(cache_ttl, (int, float)) or isinstance(cache_ttl, bool) or cache_ttl <= 0:
            raise InvalidParameterError(
                "cache_ttl must be a positive number of seconds, got %r." % (cache_ttl,)
            )
    return cache == "disk"


def _validate_explore_cookies(cookies: Union[bool, str]) -> Optional[str]:
    """Validate the ``cookies`` arg up-front; return the jar path, or None when off.

    Mirrors ``cache``: ``False`` (default) or ``"disk"``. ``True`` and other
    strings are rejected so the value can never mean different things.
    """
    if cookies is False:
        return None
    if cookies == "disk":
        return _default_cookie_path()
    raise InvalidParameterError(
        "Invalid cookies: %r. Use cookies='disk' to reuse Google's session cookies "
        "across Explore calls (a small file next to the archive DB, or the "
        "TRENDSPYG_COOKIES path), or cookies=False (default)." % (cookies,)
    )


def clear_explore_cookies(path: Optional[str] = None) -> bool:
    """Delete the Explore session cookie jar written by ``cookies="disk"``.

    Args:
        path: The jar file (default: the ``TRENDSPYG_COOKIES`` env var, else
            ``explore_cookies.json`` beside the archive DB).

    Returns:
        ``True`` if a file was removed, ``False`` if there was none.
    """
    return _forget_cookies(path)


def _validate_gprop(gprop: str) -> str:
    """Validate the Google property; returns it normalized (``"web"`` → ``""``).

    Fail-fast like the other Explore validations — a typo'd property must not
    cost a 10-40s browser run before erroring.
    """
    if gprop == "web":
        return ""
    if not isinstance(gprop, str) or gprop not in _VALID_GPROPS:
        raise InvalidParameterError(
            "Invalid gprop: %r. Valid options: '' or 'web' (web search, default), "
            "'images', 'news', 'youtube', 'froogle' (Google Shopping)." % (gprop,)
        )
    return gprop


def _default_cache_ttl(timeframe: str) -> float:
    """Freshness default by data granularity: ``"now *"`` timeframes carry
    hourly points that move all day (1h); everything else is daily/weekly (24h)."""
    return 3600.0 if timeframe.strip().lower().startswith("now ") else 86400.0


def _explore_cache_key(
    keyword: str,
    geo: str,
    timeframe: str,
    category: int,
    want_related: bool,
    want_geo: bool,
    gprop: str = "",
) -> str:
    """Exact-match cache key over every parameter that shapes the payload.

    The keyword is lowercased — Google treats search terms case-insensitively
    (the shipped comparison validation already relies on this).
    """
    return "explore|%s|%s|%s|%s|%s|%s|%s" % (
        keyword.lower(),
        geo,
        timeframe,
        category,
        want_related,
        want_geo,
        gprop,
    )


def _explore_cache_lookup(
    keyword: str,
    geo: str,
    timeframe: str,
    category: int,
    want_related: bool,
    want_geo: bool,
    gprop: str,
    ttl: float,
    db_path: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Disk-cache lookup that lets a bigger cached answer serve a smaller question.

    Exact key first. On a miss, any cached payload for the same keyword / geo /
    timeframe / category / gprop whose widgets are a *superset* of the wanted
    ones is trimmed down and served — a ``--full`` fetch already contains the
    plain interest-over-time series (1.6.0; before, ``explore -k x --full``
    followed by ``explore -k x`` cost a second browser session). The trimmed
    payload equals what a fresh fetch with the wanted flags would return.
    """
    exact = _explore_cache_get_safely(
        _explore_cache_key(keyword, geo, timeframe, category, want_related, want_geo, gprop),
        ttl,
        db_path=db_path,
    )
    if exact is not None:
        return cast(Dict[str, Any], exact)
    for cached_related, cached_geo in ((True, True), (True, False), (False, True)):
        if (cached_related, cached_geo) == (want_related, want_geo):
            continue
        if (want_related and not cached_related) or (want_geo and not cached_geo):
            continue  # not a superset of what is wanted
        hit = _explore_cache_get_safely(
            _explore_cache_key(
                keyword, geo, timeframe, category, cached_related, cached_geo, gprop
            ),
            ttl,
            db_path=db_path,
        )
        if hit is not None:
            data = dict(hit["data"])
            if not want_related:
                data.pop("related_queries", None)
            if not want_geo:
                data.pop("interest_by_region", None)
            return {"fetched_at": hit["fetched_at"], "data": data}
    return None


def _comparison_cache_key(
    keywords: Sequence[str],
    geo: str,
    timeframe: str,
    category: int,
    want_geo: bool,
    gprop: str = "",
) -> str:
    """Comparison cache key; keyword ORDER is part of it (output shape follows it)."""
    return "comparison|%s|%s|%s|%s|%s|%s" % (
        ",".join(kw.lower() for kw in keywords),
        geo,
        timeframe,
        category,
        want_geo,
        gprop,
    )


def _build_explore_envelope(
    keyword: str,
    geo: str,
    timeframe: str,
    fetched_at: str,
    data: Dict[str, Any],
    gprop: str = "",
) -> Dict[str, Any]:
    """One construction for the ExploreEnvelope — fresh fetches, cache hits,
    and archive rows all go through here so the shape cannot drift."""
    series = data["interest_over_time"]
    return {
        "schema_version": EXPLORE_SCHEMA_VERSION,
        "source": "explore",
        "keyword": keyword,
        "geo": geo,
        "timeframe": timeframe,
        "gprop": gprop,
        "fetched_at": fetched_at,
        "count": len(series),
        # Google answers a keyword it has no data for with an all-zero series
        # (observed 2026-08-19); returned as-is, flagged here so agents can tell
        # "no data" from "genuinely flat". Precise meaning: no non-zero point.
        # Google samples, so a noise-floor keyword can come back all-zero on one
        # run and with a lone 100 spike on another (also observed 2026-08-19,
        # same keyword, ~1h apart) — a lone spike with empty related/regions is
        # still "no data" in practice; this flag does not try to guess that.
        "is_empty": not any(point.get("value") for point in series),
        "interest_over_time": series,
        "related_queries": data.get("related_queries", {"top": [], "rising": []}),
        "interest_by_region": data.get("interest_by_region", []),
    }


def _build_comparison_envelope(
    keywords: List[str],
    geo: str,
    timeframe: str,
    fetched_at: str,
    data: Dict[str, Any],
    gprop: str = "",
) -> Dict[str, Any]:
    """One construction for the ComparisonEnvelope (see _build_explore_envelope)."""
    series = data["interest_over_time"]
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "source": "explore_comparison",
        "keywords": keywords,
        "geo": geo,
        "timeframe": timeframe,
        "gprop": gprop,
        "fetched_at": fetched_at,
        "count": len(series),
        "averages": data["averages"],
        "interest_over_time": series,
        "interest_by_region": data.get("interest_by_region", []),
    }


def download_google_trends_interest_over_time(
    keyword: str,
    geo: str = "US",
    timeframe: str = "today 12-m",
    category: int = 0,
    headless: bool = True,
    output_format: TimeseriesFormat = "dict",
    max_retries: int = 10,
    retry_wait: float = 8.0,
    cache: Union[bool, str] = False,
    cache_ttl: Optional[float] = None,
    archive: bool = False,
    db_path: Optional[str] = None,
    gprop: str = "",
    cookies: Union[bool, str] = False,
) -> Union[List[Dict[str, Any]], str, "pd.DataFrame"]:
    """Download a keyword's *interest over time* — the headline Explore metric.

    This is the data the archived ``pytrends`` was most used for: Google's
    0-100 relative-interest index for one search term across a time range.

    Args:
        keyword: The search term to analyze (e.g. ``"bitcoin"``).
        geo: Country / sub-region code (e.g. ``"US"``, ``"GB"``, ``"US-CA"``).
             Empty handling follows the other paths; defaults to ``"US"``.
        timeframe: Google Trends date range string. Common values:
            ``"today 12-m"`` (default, weekly points), ``"today 5-y"``,
            ``"today 3-m"``, ``"now 7-d"`` (hourly), ``"now 1-H"``, ``"all"``,
            or a custom ``"2024-01-01 2024-12-31"``.
        category: Google Trends category id (0 = all categories).
        headless: Run Chrome headless (default True).
        output_format: ``"dict"`` (default), ``"dataframe"``, ``"json"``, ``"csv"``.
        max_retries: How many chart-load attempts (page reloads) to make past
            Google's transient soft-throttle before raising ``RateLimitError``.
            Default 10.
        retry_wait: Seconds to watch the chart per attempt before reloading.
            Default 8.0.
        cache: ``False`` (default) or ``"disk"`` — serve an identical recent
            request from the local archive DB with NO browser launch (new in
            1.4.0). There is no in-memory mode; ``True`` is rejected.
        cache_ttl: Max age in seconds a cached result may be served (default:
            1 hour for ``"now *"`` timeframes, 24 hours otherwise — hourly
            points go stale much faster than weekly ones).
        archive: Also record this fetch (as a full ExploreEnvelope snapshot)
            in the local archive DB. Only fresh fetches are archived — cache
            hits are not re-recorded. A failed write warns instead of raising.
        db_path: Archive/disk-cache file (default: the TRENDSPYG_DB env var,
            else the platform data dir).
        gprop: Google property to analyze (new in 1.5.0): ``""``/``"web"``
            (default, web search), ``"images"``, ``"news"``, ``"youtube"``
            (YouTube search interest), or ``"froogle"`` (Google Shopping).
        cookies: ``False`` (default) or ``"disk"`` (new in 1.6.0) — reuse
            Google's session cookies across calls, so each browser session
            looks like a returning visitor instead of a new one. Measured
            2026-08-19: after a burst, Google refuses *new* visitors with its
            hard 429 page while a session carrying an established jar is still
            served. Stored as a small JSON file beside the archive DB (or at
            ``TRENDSPYG_COOKIES``); a jar Google refuses is forgotten
            automatically; ``clear_explore_cookies()`` deletes it. Opt-in
            because it keeps a Google cookie on disk.

    Returns:
        For ``"dict"``: a list of ``{'date': ISO8601, 'value': int,
        'is_partial': bool}`` points, oldest first. A keyword Google has no
        data for comes back as a series of zeros (that is Google's own answer);
        ``download_google_trends_explore`` flags it as ``is_empty``. Other formats render the
        same data. Every value is JSON-safe.

    Raises:
        InvalidParameterError: If ``keyword`` is empty, ``geo`` or
            ``output_format`` is invalid, ``max_retries`` < 1,
            ``retry_wait`` <= 0, or ``cache``/``cache_ttl``/``cookies`` is invalid.
            Validated up-front, before the browser starts.
        RateLimitError: If Google persistently throttles the Explore data.
        BrowserError: If Chrome cannot start.
        DownloadError: If the data cannot be retrieved after the chart renders.

    Performance:
        ~10-30s per call (drives a real browser, with retries past Google's
        soft-throttle). Worst case ≈ ``max_retries * (retry_wait + ~2s)``.
        Lower both to fail fast (e.g. ``max_retries=2, retry_wait=5`` ≈ 15s
        ceiling); raise them to be more patient with a throttled IP. This path
        is for analysis, not high-frequency polling — use the RSS path for
        fast, frequent real-time checks.

    Examples:
        >>> series = download_google_trends_interest_over_time("bitcoin", geo="US")
        >>> series[-1]
        {'date': '2026-05-31T00:00:00+00:00', 'value': 57, 'is_partial': True}
    """
    if not keyword or not keyword.strip():
        raise InvalidParameterError("keyword must be a non-empty string.")
    _validate_retry_params(max_retries, retry_wait)
    if output_format not in _TIMESERIES_FORMATS:
        # Fail fast — before the ~30s browser run, not after it.
        raise InvalidParameterError(
            f"Invalid output_format: '{output_format}'. "
            "Must be one of: 'dict', 'dataframe', 'json', 'csv'"
        )
    use_disk_cache = _validate_explore_cache(cache, cache_ttl)
    cookie_path = _validate_explore_cookies(cookies)
    gprop = _validate_gprop(gprop)
    geo = validate_geo(geo) if geo else geo

    cache_key = _explore_cache_key(keyword.strip(), geo, timeframe, category, False, False, gprop)
    if use_disk_cache:
        ttl = cache_ttl if cache_ttl is not None else _default_cache_ttl(timeframe)
        hit = _explore_cache_lookup(
            keyword.strip(), geo, timeframe, category, False, False, gprop, ttl, db_path
        )
        if hit is not None:
            return _format_timeseries(hit["data"]["interest_over_time"], output_format)

    data = _fetch_explore(
        keyword=keyword.strip(),
        geo=geo,
        timeframe=timeframe,
        category=category,
        headless=headless,
        want_related=False,
        want_geo=False,
        max_load_attempts=max_retries,
        per_attempt_wait=retry_wait,
        gprop=gprop,
        cookie_path=cookie_path,
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    if use_disk_cache:
        _explore_cache_set_safely(
            cache_key, {"fetched_at": fetched_at, "data": data}, db_path=db_path
        )
    # Only fresh fetches are archived — cache hits never re-record.
    if archive:
        _store_snapshot_safely(
            _build_explore_envelope(keyword.strip(), geo, timeframe, fetched_at, data, gprop),
            db_path=db_path,
        )
    return _format_timeseries(data["interest_over_time"], output_format)


def download_google_trends_explore(
    keyword: str,
    geo: str = "US",
    timeframe: str = "today 12-m",
    category: int = 0,
    headless: bool = True,
    include_related: bool = True,
    include_geo: bool = True,
    max_retries: int = 10,
    retry_wait: float = 8.0,
    cache: Union[bool, str] = False,
    cache_ttl: Optional[float] = None,
    archive: bool = False,
    db_path: Optional[str] = None,
    gprop: str = "",
    cookies: Union[bool, str] = False,
) -> Dict[str, Any]:
    """Download the full Explore picture for a keyword in a single browser load.

    Returns an :class:`~trendspyg.types.ExploreEnvelope` combining interest over
    time, related queries (top + rising), and interest by region — every field
    present and JSON-safe, so an agent learns the shape once.

    Args:
        keyword: The search term to analyze.
        geo: Country / sub-region code (default ``"US"``).
        timeframe: Google Trends date range (default ``"today 12-m"``).
        category: Google Trends category id (0 = all).
        headless: Run Chrome headless (default True).
        include_related: Include related queries (top + rising). Default True.
        include_geo: Include interest by region. Default True.
        max_retries: Chart-load attempts (page reloads) past the soft-throttle
            before raising ``RateLimitError``. Default 10. Worst case runtime
            ≈ ``max_retries * (retry_wait + ~2s)``.
        retry_wait: Seconds to watch the chart per attempt before reloading.
            Default 8.0.
        cache: ``False`` (default) or ``"disk"`` — serve an identical recent
            request from the local archive DB with NO browser launch (new in
            1.4.0). On a hit ``fetched_at`` is the ORIGINAL fetch time, so the
            envelope stays honest about the data's age. ``True`` is rejected
            (no in-memory mode on this path).
        cache_ttl: Max age in seconds a cached result may be served (default:
            1 hour for ``"now *"`` timeframes, 24 hours otherwise).
        archive: Also record this fetch in the local archive DB (fresh fetches
            only — cache hits are not re-recorded; failed writes warn).
        db_path: Archive/disk-cache file (default: TRENDSPYG_DB env var, else
            the platform data dir).
        gprop: Google property to analyze (new in 1.5.0): ``""``/``"web"``
            (default), ``"images"``, ``"news"``, ``"youtube"``, ``"froogle"``
            (Google Shopping).
        cookies: ``False`` (default) or ``"disk"`` (new in 1.6.0) — reuse
            Google's session cookies across calls, so each browser session
            looks like a returning visitor instead of a new one. Measured
            2026-08-19: after a burst, Google refuses *new* visitors with its
            hard 429 page while a session carrying an established jar is still
            served. Stored as a small JSON file beside the archive DB (or at
            ``TRENDSPYG_COOKIES``); a jar Google refuses is forgotten
            automatically; ``clear_explore_cookies()`` deletes it. Opt-in
            because it keeps a Google cookie on disk.

    Returns:
        ``{schema_version, source, keyword, geo, timeframe, gprop, fetched_at,
        interest_over_time, related_queries: {top, rising}, interest_by_region}``.
        ``related_queries`` / ``interest_by_region`` are empty when not requested
        or when Google did not return them (best-effort — the chart is the
        guaranteed payload).

    Raises:
        InvalidParameterError, RateLimitError, BrowserError, DownloadError — see
        :func:`download_google_trends_interest_over_time`.

    Examples:
        >>> env = download_google_trends_explore("bitcoin", geo="US")
        >>> env["count"], len(env["interest_over_time"])
        (53, 53)
        >>> env["related_queries"]["rising"][0]["query"]
        'bitcoin etf price'
    """
    if not keyword or not keyword.strip():
        raise InvalidParameterError("keyword must be a non-empty string.")
    _validate_retry_params(max_retries, retry_wait)
    use_disk_cache = _validate_explore_cache(cache, cache_ttl)
    cookie_path = _validate_explore_cookies(cookies)
    gprop = _validate_gprop(gprop)
    geo = validate_geo(geo) if geo else geo

    cache_key = _explore_cache_key(
        keyword.strip(), geo, timeframe, category, include_related, include_geo, gprop
    )
    if use_disk_cache:
        ttl = cache_ttl if cache_ttl is not None else _default_cache_ttl(timeframe)
        hit = _explore_cache_lookup(
            keyword.strip(),
            geo,
            timeframe,
            category,
            include_related,
            include_geo,
            gprop,
            ttl,
            db_path,
        )
        if hit is not None:
            return _build_explore_envelope(
                keyword.strip(), geo, timeframe, hit["fetched_at"], hit["data"], gprop
            )

    data = _fetch_explore(
        keyword=keyword.strip(),
        geo=geo,
        timeframe=timeframe,
        category=category,
        headless=headless,
        want_related=include_related,
        want_geo=include_geo,
        max_load_attempts=max_retries,
        per_attempt_wait=retry_wait,
        gprop=gprop,
        cookie_path=cookie_path,
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    envelope = _build_explore_envelope(keyword.strip(), geo, timeframe, fetched_at, data, gprop)
    if use_disk_cache:
        _explore_cache_set_safely(
            cache_key, {"fetched_at": fetched_at, "data": data}, db_path=db_path
        )
    # Only fresh fetches are archived — cache hits never re-record.
    if archive:
        _store_snapshot_safely(envelope, db_path=db_path)
    return envelope


def download_google_trends_comparison(
    keywords: Sequence[str],
    geo: str = "US",
    timeframe: str = "today 12-m",
    category: int = 0,
    headless: bool = True,
    output_format: TimeseriesFormat = "dict",
    include_geo: bool = True,
    max_retries: int = 10,
    retry_wait: float = 8.0,
    cache: Union[bool, str] = False,
    cache_ttl: Optional[float] = None,
    archive: bool = False,
    db_path: Optional[str] = None,
    gprop: str = "",
    cookies: Union[bool, str] = False,
) -> Union[Dict[str, Any], str, "pd.DataFrame"]:
    """Compare 2-5 keywords on Google's shared relative-interest scale.

    This is the pytrends ``kw_list`` use case: one browser load returns the
    comparison chart's data — every value on a single 0-100 scale relative to
    the strongest term, so the keywords are directly comparable (unlike
    fetching them one at a time, where each series is scaled independently).

    New in 1.1.0. Behavior verified live against Google's comparison page:
    one combined time-series request, values aligned to keyword order, plus a
    combined per-region breakdown.

    Args:
        keywords: 2-5 distinct search terms, e.g. ``["bitcoin", "ethereum"]``.
            Terms containing a comma cannot be compared (Google's URL format
            uses the comma as the separator).
        geo: Country / sub-region code (e.g. ``"US"``, ``"GB"``, ``"US-CA"``).
        timeframe: Google Trends date range string (default ``"today 12-m"``).
            See :func:`download_google_trends_interest_over_time`.
        category: Google Trends category id (0 = all categories).
        headless: Run Chrome headless (default True).
        output_format: ``"dict"`` (default) and ``"json"`` return the full
            :class:`~trendspyg.types.ComparisonEnvelope`; ``"dataframe"`` and
            ``"csv"`` render the interest-over-time series as a table with one
            column per keyword (``date, <kw1>, ..., <kwN>, is_partial``).
        include_geo: Include the combined interest-by-region breakdown
            (default True). Pass False to skip the extra scroll/fetch.
        max_retries: Chart-load attempts (page reloads) past Google's
            soft-throttle before raising ``RateLimitError``. Default 10.
        retry_wait: Seconds to watch the chart per attempt. Default 8.0.
            Worst-case runtime ≈ ``max_retries * (retry_wait + ~2s)``.
        cache: ``False`` (default) or ``"disk"`` — serve an identical recent
            comparison from the local archive DB with NO browser launch (new
            in 1.4.0). Keyword order is part of the cache key (the output
            shape follows it). ``True`` is rejected (no in-memory mode).
        cache_ttl: Max age in seconds a cached result may be served (default:
            1 hour for ``"now *"`` timeframes, 24 hours otherwise).
        archive: Also record this fetch (source ``"explore_comparison"``) in
            the local archive DB — every compared keyword becomes queryable
            via ``get_keyword_history``. Fresh fetches only; failed writes
            warn instead of raising.
        db_path: Archive/disk-cache file (default: TRENDSPYG_DB env var, else
            the platform data dir).
        gprop: Google property to compare on (new in 1.5.0): ``""``/``"web"``
            (default), ``"images"``, ``"news"``, ``"youtube"``, ``"froogle"``
            (Google Shopping).
        cookies: ``False`` (default) or ``"disk"`` (new in 1.6.0) — reuse
            Google's session cookies across calls, so each browser session
            looks like a returning visitor instead of a new one. Measured
            2026-08-19: after a burst, Google refuses *new* visitors with its
            hard 429 page while a session carrying an established jar is still
            served. Stored as a small JSON file beside the archive DB (or at
            ``TRENDSPYG_COOKIES``); a jar Google refuses is forgotten
            automatically; ``clear_explore_cookies()`` deletes it. Opt-in
            because it keeps a Google cookie on disk.

    Returns:
        For ``"dict"``: ``{schema_version, source, keywords, geo, timeframe,
        gprop, fetched_at, count, averages: {kw: int}, interest_over_time:
        [{date, values: {kw: int}, is_partial}], interest_by_region:
        [{geo_code, geo_name, values: {kw: int}, top_keyword}]}``.
        Every value is JSON-safe.

    Raises:
        InvalidParameterError: If ``keywords`` is not 2-5 distinct comma-free
            non-empty strings, ``geo``/``output_format`` is invalid,
            ``max_retries`` < 1, or ``retry_wait`` <= 0.
        RateLimitError: If Google persistently throttles the Explore data.
        BrowserError: If Chrome cannot start, or the Explore DOM changed.
        DownloadError: If the data cannot be retrieved after the chart renders.

    Performance:
        Same profile as the other Explore functions (~10-90s, drives a real
        browser, rate-limit sensitive — not for polling). One comparison call
        replaces N single-keyword calls *and* returns directly comparable
        numbers, so it is both faster and more correct for comparisons.

    Examples:
        >>> env = download_google_trends_comparison(["bitcoin", "ethereum"])
        >>> env["averages"]
        {'bitcoin': 39, 'ethereum': 7}
        >>> env["interest_over_time"][-1]["values"]
        {'bitcoin': 41, 'ethereum': 6}
        >>> env["interest_by_region"][0]["top_keyword"]
        'bitcoin'
    """
    cleaned = _validate_comparison_keywords(keywords)
    _validate_retry_params(max_retries, retry_wait)
    if output_format not in _TIMESERIES_FORMATS:
        # Fail fast — before the ~30s browser run, not after it.
        raise InvalidParameterError(
            f"Invalid output_format: '{output_format}'. "
            "Must be one of: 'dict', 'dataframe', 'json', 'csv'"
        )
    use_disk_cache = _validate_explore_cache(cache, cache_ttl)
    cookie_path = _validate_explore_cookies(cookies)
    gprop = _validate_gprop(gprop)
    geo = validate_geo(geo) if geo else geo

    cache_key = _comparison_cache_key(cleaned, geo, timeframe, category, include_geo, gprop)
    if use_disk_cache:
        ttl = cache_ttl if cache_ttl is not None else _default_cache_ttl(timeframe)
        hit = _explore_cache_get_safely(cache_key, ttl, db_path=db_path)
        if hit is not None:
            return _format_comparison(
                _build_comparison_envelope(
                    cleaned, geo, timeframe, hit["fetched_at"], hit["data"], gprop
                ),
                output_format,
            )

    data = _fetch_comparison(
        keywords=cleaned,
        geo=geo,
        timeframe=timeframe,
        category=category,
        headless=headless,
        want_geo=include_geo,
        max_load_attempts=max_retries,
        per_attempt_wait=retry_wait,
        gprop=gprop,
        cookie_path=cookie_path,
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    envelope = _build_comparison_envelope(cleaned, geo, timeframe, fetched_at, data, gprop)
    if use_disk_cache:
        _explore_cache_set_safely(
            cache_key, {"fetched_at": fetched_at, "data": data}, db_path=db_path
        )
    # Only fresh fetches are archived — cache hits never re-record.
    if archive:
        _store_snapshot_safely(envelope, db_path=db_path)
    return _format_comparison(envelope, output_format)
