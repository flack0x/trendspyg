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
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Sequence, Tuple, Union

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

if TYPE_CHECKING:
    import pandas as pd

from .downloader import validate_geo
from .exceptions import BrowserError, DownloadError, InvalidParameterError, RateLimitError

# Type aliases
TimeseriesFormat = Literal["dict", "dataframe", "json", "csv"]

#: Bumped when the Explore envelope changes shape so agents can detect drift.
EXPLORE_SCHEMA_VERSION = "1.0"

#: Bumped when the multi-keyword ComparisonEnvelope changes shape (new in 1.1.0).
COMPARISON_SCHEMA_VERSION = "1.0"

#: Google's Explore UI compares at most 5 terms; the URL format uses ',' as the
#: keyword separator, so terms containing literal commas cannot be compared.
_MAX_COMPARISON_KEYWORDS = 5

_TIMESERIES_FORMATS = ("dict", "dataframe", "json", "csv")

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


def _parse_multiline_comparison(
    data: Dict[str, Any], keywords: List[str]
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Parse a multi-keyword ``widgetdata/multiline`` payload.

    Google returns one ``value`` array per point, aligned to the comparison's
    keyword order (verified live 2026-07-10). Returns ``(points, averages)``:
    each point ``{'date': ISO8601, 'values': {keyword: int}, 'is_partial': bool}``,
    and ``averages`` as ``{keyword: int}`` from the payload's ``averages`` array.
    Missing/short arrays fill with 0 rather than raising — the shape stays fixed.
    """
    points: List[Dict[str, Any]] = []
    for entry in data.get("default", {}).get("timelineData", []) or []:
        raw_values = entry.get("value") or []
        values: Dict[str, int] = {}
        for i, kw in enumerate(keywords):
            try:
                values[kw] = int(raw_values[i])
            except (TypeError, ValueError, IndexError):
                values[kw] = 0
        epoch = entry.get("time")
        try:
            date_iso = _epoch_to_iso(epoch) if epoch is not None else ""
        except (TypeError, ValueError):
            date_iso = ""
        points.append(
            {
                "date": date_iso,
                "values": values,
                "is_partial": bool(entry.get("isPartial", False)),
            }
        )
    raw_averages = data.get("default", {}).get("averages") or []
    averages: Dict[str, int] = {}
    for i, kw in enumerate(keywords):
        try:
            averages[kw] = int(raw_averages[i])
        except (TypeError, ValueError, IndexError):
            averages[kw] = 0
    return points, averages


def _parse_comparedgeo_comparison(
    data: Dict[str, Any], keywords: List[str]
) -> List[Dict[str, Any]]:
    """Parse a *combined* multi-keyword ``widgetdata/comparedgeo`` payload.

    Each row: ``{'geo_code', 'geo_name', 'values': {keyword: int},
    'top_keyword': str}``. ``top_keyword`` comes from Google's
    ``maxValueIndex`` (falling back to our own argmax if absent). Regions
    where Google reports no data for any keyword are skipped.
    """
    rows: List[Dict[str, Any]] = []
    for entry in data.get("default", {}).get("geoMapData", []) or []:
        has_data = entry.get("hasData") or []
        if not any(has_data):
            continue
        raw_values = entry.get("value") or []
        values: Dict[str, int] = {}
        for i, kw in enumerate(keywords):
            try:
                values[kw] = int(raw_values[i])
            except (TypeError, ValueError, IndexError):
                values[kw] = 0
        max_idx = entry.get("maxValueIndex")
        if not isinstance(max_idx, int) or not 0 <= max_idx < len(keywords):
            max_idx = max(range(len(keywords)), key=lambda i: values[keywords[i]])
        rows.append(
            {
                "geo_code": entry.get("geoCode", "") or "",
                "geo_name": entry.get("geoName", "") or "",
                "values": values,
                "top_keyword": keywords[max_idx],
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
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
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
            {"source": "Object.defineProperty(navigator,'webdriver'," "{get:()=>undefined});"},
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
) -> str:
    """Load the Explore chart, reloading past Google's transient soft-throttle.

    Polls responsively (1s) instead of sleeping in fixed blocks: it returns the
    instant the chart renders, and reloads the instant the 'Oops' state shows —
    so a fast success costs a few seconds, not a minute.

    Returns:
        ``"ready"`` if the interest-over-time chart rendered; ``"throttled"`` if
        Google's soft-throttle ('try again') state was seen while waiting; or
        ``"timeout"`` if neither happened — which usually means the Explore DOM
        changed rather than a rate-limit (so the caller should not tell the user
        to "wait and retry").
    """
    saw_throttle = False
    for _ in range(attempts):
        waited = 0.0
        while waited < per_attempt:
            if _chart_ready(driver):
                return "ready"
            if _chart_errored(driver):
                saw_throttle = True
                break  # don't keep waiting on an errored widget — reload now
            time.sleep(1.0)
            waited += 1.0
        driver.get(url)
        time.sleep(2.0)
    # one final check after the last reload settles
    if _chart_ready(driver):
        return "ready"
    return "throttled" if saw_throttle else "timeout"


def _dismiss_cookie_banner(driver: webdriver.Chrome) -> None:
    """Click through Google's cookie/consent banner if it is present."""
    for label in ("OK, got it", "Accept all", "I agree", "Got it"):
        try:
            driver.find_element(By.XPATH, f"//button[contains(., '{label}')]").click()
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


def _req_comparison_size(widget_url: str) -> int:
    """How many comparison items a widgetdata request covers (0 if unparseable).

    Every widgetdata URL embeds a ``req`` JSON param. Comparison-scoped widgets
    carry ``comparisonItem`` (one entry per compared keyword); single-keyword
    widgets (e.g. per-keyword relatedsearches) carry ``restriction`` instead.
    """
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(widget_url).query)
        req = json.loads(query["req"][0])
    except (KeyError, IndexError, ValueError):
        return 0
    items = req.get("comparisonItem")
    if isinstance(items, list):
        return len(items)
    return 1 if "restriction" in req else 0


def _collect_widget_urls_comparison(driver: webdriver.Chrome, n_keywords: int) -> Dict[str, str]:
    """Read the multiline + *combined* comparedgeo URLs for an N-keyword comparison.

    With N compared keywords the page issues (verified live 2026-07-10): one
    multiline request covering all keywords, one combined comparedgeo carrying
    N comparison items PLUS one comparedgeo per keyword, and one
    relatedsearches per keyword. We want the multiline and the combined
    comparedgeo only — the per-keyword ones are filtered out by their
    ``req`` item count.
    """
    urls: Dict[str, str] = {}
    for entry in driver.get_log("performance"):
        try:
            message = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue
        if message.get("method") != "Network.requestWillBeSent":
            continue
        url = message.get("params", {}).get("request", {}).get("url", "")
        if "widgetdata/multiline" in url:
            urls["multiline"] = url
        elif "widgetdata/comparedgeo" in url and _req_comparison_size(url) == n_keywords:
            urls["comparedgeo"] = url
    return urls


def _raise_for_chart_status(chart_status: str, context: str) -> None:
    """Translate a non-``ready`` :func:`_await_chart` status into the right error.

    ``throttled`` → RateLimitError (Google's soft-throttle persisted);
    ``timeout`` → BrowserError (chart never rendered *and* no throttle message —
    the Explore DOM likely changed, so "wait and retry" would be bad advice).
    """
    if chart_status == "ready":
        return
    if chart_status == "throttled":
        raise RateLimitError(
            "Google Trends did not return Explore data (persistent "
            "rate-limit / 'try again in a bit').\n\n"
            "The Explore endpoints throttle aggressively. Solutions:\n"
            "• Wait 1-2 minutes before trying again\n"
            "• Space out requests (this path is not for high-frequency polling)\n"
            "• Use the RSS path for fast, frequent real-time checks\n\n" + context
        )
    raise BrowserError(
        "Google Trends Explore did not render the interest-over-time "
        "chart, and no rate-limit message was shown — the page structure "
        "may have changed.\n\n"
        "This usually means Google updated the Explore UI. Solutions:\n"
        "• Update trendspyg: pip install --upgrade trendspyg\n"
        "• Run with headless=False (CLI: --visible) to see the page\n"
        "• Report it: https://github.com/flack0x/trendspyg/issues\n\n" + context
    )


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
    per_attempt_wait: float = 8.0,
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

        chart_status = _await_chart(
            driver, url, attempts=max_load_attempts, per_attempt=per_attempt_wait
        )
        _raise_for_chart_status(
            chart_status, f"Keyword: {keyword!r} | Geo: {geo} | Timeframe: {timeframe}"
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
            result["interest_by_region"] = _parse_comparedgeo(geo_data) if geo_data else []
        elif want_geo:
            result["interest_by_region"] = []

        return result
    finally:
        driver.quit()


def _fetch_comparison(
    keywords: List[str],
    geo: str,
    timeframe: str,
    category: int,
    headless: bool,
    want_geo: bool,
    max_load_attempts: int = 10,
    per_attempt_wait: float = 8.0,
) -> Dict[str, Any]:
    """Drive one browser session for a multi-keyword comparison.

    Always returns ``interest_over_time`` + ``averages``. Returns
    ``interest_by_region`` (the combined per-region comparison) only when
    requested — that widget lazy-loads on scroll.

    Raises:
        RateLimitError: if the chart never renders (persistent soft-throttle).
        BrowserError: if Chrome cannot start, or the Explore DOM changed.
        DownloadError: if the chart renders but its data cannot be retrieved.
    """
    url = _build_explore_url(",".join(keywords), geo, timeframe, category)
    driver = _build_driver(headless)
    try:
        driver.get(url)
        time.sleep(3)
        _dismiss_cookie_banner(driver)

        chart_status = _await_chart(
            driver, url, attempts=max_load_attempts, per_attempt=per_attempt_wait
        )
        _raise_for_chart_status(
            chart_status, f"Keywords: {keywords!r} | Geo: {geo} | Timeframe: {timeframe}"
        )

        # The combined by-region widget lazy-loads on scroll into view.
        if want_geo:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(4)

        widget_urls = _collect_widget_urls_comparison(driver, len(keywords))

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

        points, averages = _parse_multiline_comparison(multiline, keywords)
        result: Dict[str, Any] = {
            "interest_over_time": points,
            "averages": averages,
        }

        if want_geo and "comparedgeo" in widget_urls:
            geo_data = _replay_widget(driver, widget_urls["comparedgeo"])
            result["interest_by_region"] = (
                _parse_comparedgeo_comparison(geo_data, keywords) if geo_data else []
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


def download_google_trends_interest_over_time(
    keyword: str,
    geo: str = "US",
    timeframe: str = "today 12-m",
    category: int = 0,
    headless: bool = True,
    output_format: TimeseriesFormat = "dict",
    max_retries: int = 10,
    retry_wait: float = 8.0,
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

    Returns:
        For ``"dict"``: a list of ``{'date': ISO8601, 'value': int,
        'is_partial': bool}`` points, oldest first. Other formats render the
        same data. Every value is JSON-safe.

    Raises:
        InvalidParameterError: If ``keyword`` is empty, ``geo`` or
            ``output_format`` is invalid, ``max_retries`` < 1, or
            ``retry_wait`` <= 0. Validated up-front, before the browser starts.
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
    geo = validate_geo(geo) if geo else geo

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
    _validate_retry_params(max_retries, retry_wait)
    geo = validate_geo(geo) if geo else geo

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

    Returns:
        For ``"dict"``: ``{schema_version, source, keywords, geo, timeframe,
        fetched_at, count, averages: {kw: int}, interest_over_time:
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
    geo = validate_geo(geo) if geo else geo

    data = _fetch_comparison(
        keywords=cleaned,
        geo=geo,
        timeframe=timeframe,
        category=category,
        headless=headless,
        want_geo=include_geo,
        max_load_attempts=max_retries,
        per_attempt_wait=retry_wait,
    )
    series = data["interest_over_time"]
    envelope: Dict[str, Any] = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "source": "explore_comparison",
        "keywords": cleaned,
        "geo": geo,
        "timeframe": timeframe,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(series),
        "averages": data["averages"],
        "interest_over_time": series,
        "interest_by_region": data.get("interest_by_region", []),
    }
    return _format_comparison(envelope, output_format)
