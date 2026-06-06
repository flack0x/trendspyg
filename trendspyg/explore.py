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
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal, Union, TYPE_CHECKING

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

if TYPE_CHECKING:
    import pandas as pd

from .downloader import validate_geo
from .exceptions import BrowserError, RateLimitError, DownloadError, InvalidParameterError

# Type aliases
TimeseriesFormat = Literal["dict", "dataframe", "json", "csv"]

#: Bumped when the Explore envelope changes shape so agents can detect drift.
EXPLORE_SCHEMA_VERSION = "1.0"

_BASE_URL = "https://trends.google.com/trends/explore"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Replays a same-origin widgetdata URL from inside the page so it carries the
# page's freshly-minted token + cookies. Returns the raw text (or 'ERR:...').
_REPLAY_JS = """
const url = arguments[0]; const cb = arguments[arguments.length - 1];
fetch(url, {credentials: 'include'}).then(r => r.text()).then(t => cb(t))
  .catch(e => cb('ERR:' + e));
"""


# --------------------------------------------------------------------------- #
# Pure parsing helpers (no browser, no network — unit-testable in isolation)
# --------------------------------------------------------------------------- #

def _strip_xssi(text: str) -> str:
    """Drop Google's ``)]}',`` anti-JSON-hijack prefix, returning clean JSON."""
    brace = text.find("{")
    return text[brace:] if brace != -1 else text


def _epoch_to_iso(epoch: str) -> str:
    """Convert a Trends unix-seconds string to an ISO 8601 UTC string."""
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()


def _parse_multiline(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse ``widgetdata/multiline`` JSON into a list of interest points.

    Each point: ``{'date': ISO8601, 'value': int, 'is_partial': bool}``.
    ``value`` is Google's 0-100 relative interest index. The most recent point
    is usually flagged ``is_partial`` (the current period is still in progress).
    """
    points: List[Dict[str, Any]] = []
    for entry in data.get("default", {}).get("timelineData", []) or []:
        values = entry.get("value") or [0]
        try:
            value = int(values[0])
        except (TypeError, ValueError, IndexError):
            value = 0
        epoch = entry.get("time")
        try:
            date_iso = _epoch_to_iso(epoch) if epoch is not None else ""
        except (TypeError, ValueError):
            date_iso = ""
        points.append(
            {
                "date": date_iso,
                "value": value,
                "is_partial": bool(entry.get("isPartial", False)),
            }
        )
    return points


def _parse_relatedsearches(data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Parse ``widgetdata/relatedsearches`` into ``{'top': [...], 'rising': [...]}``.

    Google returns up to two ranked lists: index 0 is *top* (0-100 relative),
    index 1 is *rising* (growth — ``value`` is a percent, or a sentinel for
    "Breakout"). Each item: ``{'query', 'value', 'formatted_value', 'link'}``.
    """
    out: Dict[str, List[Dict[str, Any]]] = {"top": [], "rising": []}
    ranked_lists = data.get("default", {}).get("rankedList", []) or []
    for idx, bucket in enumerate(("top", "rising")):
        if idx >= len(ranked_lists):
            break
        for kw in ranked_lists[idx].get("rankedKeyword", []) or []:
            link = kw.get("link", "") or ""
            if link and link.startswith("/"):
                link = "https://trends.google.com" + link
            out[bucket].append(
                {
                    "query": kw.get("query", "") or "",
                    "value": int(kw.get("value", 0) or 0),
                    "formatted_value": kw.get("formattedValue", "") or "",
                    "link": link,
                }
            )
    return out


def _parse_comparedgeo(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse ``widgetdata/comparedgeo`` into a list of regional interest rows.

    Each row: ``{'geo_code', 'geo_name', 'value': int}`` (0-100 relative),
    already sorted by Google from strongest to weakest interest.
    """
    rows: List[Dict[str, Any]] = []
    for entry in data.get("default", {}).get("geoMapData", []) or []:
        values = entry.get("value") or [0]
        try:
            value = int(values[0])
        except (TypeError, ValueError, IndexError):
            value = 0
        # Skip regions Google reports with no data
        has_data = entry.get("hasData") or [False]
        if not has_data[0]:
            continue
        rows.append(
            {
                "geo_code": entry.get("geoCode", "") or "",
                "geo_name": entry.get("geoName", "") or "",
                "value": value,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Browser engine
# --------------------------------------------------------------------------- #

def _build_driver(headless: bool) -> webdriver.Chrome:
    """Create a Chrome driver with the anti-bot flags + performance logging.

    The user-agent / window-size flags mirror the working CSV path: Google
    serves a stripped page to detectably-headless Chrome. Performance logging is
    how we read the widget request URLs the page issues.
    """
    options = Options()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"--user-agent={_USER_AGENT}")
    # Stealth: Google's Explore endpoints throttle detectable automation harder.
    # These reduce the webdriver fingerprint and measurably help on a fresh IP.
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--log-level=3")
    options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    options.add_experimental_option("useAutomationExtension", False)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    try:
        driver = webdriver.Chrome(options=options)
    except WebDriverException as exc:
        raise BrowserError(
            f"Failed to start Chrome browser: {exc}\n\n"
            "The Explore path needs Chrome installed (ChromeDriver is "
            "auto-managed by Selenium). Ensure Chrome is installed and on PATH."
        )
    # Hide navigator.webdriver before any page script runs.
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator,'webdriver',"
                       "{get:()=>undefined});"},
        )
    except WebDriverException:
        pass  # non-fatal — stealth is best-effort
    return driver


def _build_explore_url(keyword: str, geo: str, timeframe: str, category: int) -> str:
    """Assemble the Explore URL with proper encoding for spaces in keyword/date."""
    params = {"q": keyword, "geo": geo, "hl": "en-US", "date": timeframe}
    if category:
        params["cat"] = str(category)
    return _BASE_URL + "?" + urllib.parse.urlencode(params)


def _chart_ready(driver: webdriver.Chrome) -> bool:
    """True once the interest-over-time chart has actually drawn (has data)."""
    return len(driver.find_elements(By.CSS_SELECTOR, "[widget-name='TIMESERIES'] svg")) > 0


def _chart_errored(driver: webdriver.Chrome) -> bool:
    """True when Google is showing its soft-throttle 'Oops / try again' state."""
    source = driver.page_source.lower()
    return "something went wrong" in source or "try again in a bit" in source


def _await_chart(
    driver: webdriver.Chrome,
    url: str,
    attempts: int,
    per_attempt: float = 8.0,
) -> bool:
    """Load the Explore chart, reloading past Google's transient soft-throttle.

    Polls responsively (1s) instead of sleeping in fixed blocks: it returns the
    instant the chart renders, and reloads the instant the 'Oops' state shows —
    so a fast success costs a few seconds, not a minute.
    """
    for _ in range(attempts):
        waited = 0.0
        while waited < per_attempt:
            if _chart_ready(driver):
                return True
            if _chart_errored(driver):
                break  # don't keep waiting on an errored widget — reload now
            time.sleep(1.0)
            waited += 1.0
        driver.get(url)
        time.sleep(2.0)
    # one final check after the last reload settles
    return _chart_ready(driver)


def _dismiss_cookie_banner(driver: webdriver.Chrome) -> None:
    """Click through Google's cookie/consent banner if it is present."""
    for label in ("OK, got it", "Accept all", "I agree", "Got it"):
        try:
            driver.find_element(
                By.XPATH, f"//button[contains(., '{label}')]"
            ).click()
            time.sleep(1.5)
            return
        except WebDriverException:
            continue


def _collect_widget_urls(driver: webdriver.Chrome) -> Dict[str, str]:
    """Read the widgetdata request URLs the page issued, from the perf log."""
    wanted = ("multiline", "relatedsearches", "comparedgeo")
    urls: Dict[str, str] = {}
    for entry in driver.get_log("performance"):
        try:
            message = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue
        if message.get("method") != "Network.requestWillBeSent":
            continue
        url = message.get("params", {}).get("request", {}).get("url", "")
        for key in wanted:
            if f"widgetdata/{key}" in url:
                urls[key] = url  # keep the most recent successful request
    return urls


def _replay_widget(driver: webdriver.Chrome, url: str, tries: int = 3) -> Optional[Dict[str, Any]]:
    """Replay a widgetdata URL in-page and return the parsed JSON, or None."""
    raw = ""
    for _ in range(tries):
        raw = driver.execute_async_script(_REPLAY_JS, url)
        if raw and not raw.startswith("ERR:") and "<html" not in raw[:200].lower():
            try:
                parsed = json.loads(_strip_xssi(raw))
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
        time.sleep(2)
    return None


def _fetch_explore(
    keyword: str,
    geo: str,
    timeframe: str,
    category: int,
    headless: bool,
    want_related: bool,
    want_geo: bool,
    max_load_attempts: int = 10,
) -> Dict[str, Any]:
    """Drive one browser session and return the requested Explore widgets.

    Always returns ``interest_over_time``. Returns ``related_queries`` /
    ``interest_by_region`` only when requested (they need a scroll to load).

    Raises:
        RateLimitError: if the chart never renders (persistent soft-throttle).
        BrowserError: if Chrome cannot start.
        DownloadError: if the chart renders but its data cannot be retrieved.
    """
    url = _build_explore_url(keyword, geo, timeframe, category)
    driver = _build_driver(headless)
    try:
        driver.get(url)
        time.sleep(3)
        _dismiss_cookie_banner(driver)

        if not _await_chart(driver, url, attempts=max_load_attempts):
            raise RateLimitError(
                "Google Trends did not return Explore data (persistent "
                "rate-limit / 'try again in a bit').\n\n"
                "The Explore endpoints throttle aggressively. Solutions:\n"
                "• Wait 1-2 minutes before trying again\n"
                "• Space out requests (this path is not for high-frequency polling)\n"
                "• Use the RSS path for fast, frequent real-time checks\n\n"
                f"Keyword: {keyword!r} | Geo: {geo} | Timeframe: {timeframe}"
            )

        # Related/geo widgets lazy-load on scroll into view.
        if want_related or want_geo:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(4)

        widget_urls = _collect_widget_urls(driver)

        if "multiline" not in widget_urls:
            raise DownloadError(
                "Interest-over-time chart rendered but its data request was not "
                "found. Google may have changed the Explore page structure.\n"
                "Please report at https://github.com/flack0x/trendspyg/issues"
            )

        multiline = _replay_widget(driver, widget_urls["multiline"])
        if multiline is None:
            raise DownloadError(
                "Failed to retrieve interest-over-time data after the chart "
                "rendered (the widget request was rate-limited on replay). "
                "Try again in a moment."
            )

        result: Dict[str, Any] = {
            "interest_over_time": _parse_multiline(multiline),
        }

        if want_related and "relatedsearches" in widget_urls:
            related = _replay_widget(driver, widget_urls["relatedsearches"])
            result["related_queries"] = (
                _parse_relatedsearches(related) if related else {"top": [], "rising": []}
            )
        elif want_related:
            result["related_queries"] = {"top": [], "rising": []}

        if want_geo and "comparedgeo" in widget_urls:
            geo_data = _replay_widget(driver, widget_urls["comparedgeo"])
            result["interest_by_region"] = (
                _parse_comparedgeo(geo_data) if geo_data else []
            )
        elif want_geo:
            result["interest_by_region"] = []

        return result
    finally:
        driver.quit()


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


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def download_google_trends_interest_over_time(
    keyword: str,
    geo: str = "US",
    timeframe: str = "today 12-m",
    category: int = 0,
    headless: bool = True,
    output_format: TimeseriesFormat = "dict",
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

    Returns:
        For ``"dict"``: a list of ``{'date': ISO8601, 'value': int,
        'is_partial': bool}`` points, oldest first. Other formats render the
        same data. Every value is JSON-safe.

    Raises:
        InvalidParameterError: If ``keyword`` is empty or ``geo`` is invalid.
        RateLimitError: If Google persistently throttles the Explore data.
        BrowserError: If Chrome cannot start.
        DownloadError: If the data cannot be retrieved after the chart renders.

    Performance:
        ~10-30s per call (drives a real browser, with retries past Google's
        soft-throttle). This path is for analysis, not high-frequency polling —
        use the RSS path for fast, frequent real-time checks.

    Examples:
        >>> series = download_google_trends_interest_over_time("bitcoin", geo="US")
        >>> series[-1]
        {'date': '2026-05-31T00:00:00+00:00', 'value': 57, 'is_partial': True}
    """
    if not keyword or not keyword.strip():
        raise InvalidParameterError("keyword must be a non-empty string.")
    geo = validate_geo(geo) if geo else geo

    data = _fetch_explore(
        keyword=keyword.strip(),
        geo=geo,
        timeframe=timeframe,
        category=category,
        headless=headless,
        want_related=False,
        want_geo=False,
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

    Returns:
        ``{schema_version, source, keyword, geo, timeframe, fetched_at,
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
    geo = validate_geo(geo) if geo else geo

    data = _fetch_explore(
        keyword=keyword.strip(),
        geo=geo,
        timeframe=timeframe,
        category=category,
        headless=headless,
        want_related=include_related,
        want_geo=include_geo,
    )
    series = data["interest_over_time"]
    return {
        "schema_version": EXPLORE_SCHEMA_VERSION,
        "source": "explore",
        "keyword": keyword.strip(),
        "geo": geo,
        "timeframe": timeframe,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(series),
        "interest_over_time": series,
        "related_queries": data.get("related_queries", {"top": [], "rising": []}),
        "interest_by_region": data.get("interest_by_region", []),
    }
