"""The browser engine: drive Chrome to the Explore page, replay widget requests.

Everything that touches Selenium lives here. The parsers are pure
(:mod:`._parsers`); the public API and its validation live in the package
``__init__``.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from ..exceptions import BrowserError, DownloadError, RateLimitError
from ._cookies import _forget_cookies, _inject_cookies, _load_cookies, _save_cookies
from ._parsers import (
    _parse_comparedgeo,
    _parse_comparedgeo_comparison,
    _parse_multiline,
    _parse_multiline_comparison,
    _parse_relatedsearches,
    _strip_xssi,
)

_BASE_URL = "https://trends.google.com/trends/explore"
_HOME_URL = "https://trends.google.com/"
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


def _warm_up(driver: webdriver.Chrome) -> None:
    """Visit the Trends home page once so the session carries Google's cookies.

    Google answers a *cookieless* ``/trends/explore`` load from an IP it has
    flagged with the hard 429 page at once — headed or headless, whatever the
    driver — while the very same load succeeds after one visit to the home page,
    which sets the ``NID`` cookie (verified 2026-08-19 on an IP that had been
    "blocked" for three days). This is the classic pytrends warm-up. Best-effort:
    a failure here is ignored — the Explore load itself decides.
    """
    try:
        driver.get(_HOME_URL)
    except WebDriverException:
        pass


def _remember_session(
    driver: webdriver.Chrome, cookie_path: str, chart_status: str, had_jar: bool
) -> None:
    """Cookie-jar bookkeeping once the chart settled (``cookies="disk"`` only).

    A session that rendered the chart is a session Google trusts — keep its
    cookies for next time (Google may have rotated them). A saved jar that was
    answered with the hard block page is burned — forget it so the next call
    starts as a new visitor instead of re-presenting a refused jar. Any other
    outcome (soft-throttle, timeout) leaves the jar as it is.
    """
    if chart_status == "ready":
        _save_cookies(driver, cookie_path)
    elif chart_status == "blocked" and had_jar:
        _forget_cookies(cookie_path)


def _build_explore_url(
    keyword: str, geo: str, timeframe: str, category: int, gprop: str = ""
) -> str:
    """Assemble the Explore URL with proper encoding for spaces in keyword/date.

    ``gprop`` selects the Google property (``""`` = web search; ``"images"``,
    ``"news"``, ``"youtube"``, ``"froogle"``). Verified live 2026-08-11: the
    URL param propagates into every widget request the page mints
    (``requestOptions.property``), so no per-widget handling is needed.
    """
    params = {"q": keyword, "geo": geo, "hl": "en-US", "date": timeframe}
    if category:
        params["cat"] = str(category)
    if gprop:
        params["gprop"] = gprop
    return _BASE_URL + "?" + urllib.parse.urlencode(params)


def _chart_ready(driver: webdriver.Chrome) -> bool:
    """True once the interest-over-time chart has actually drawn (has data)."""
    return len(driver.find_elements(By.CSS_SELECTOR, "[widget-name='TIMESERIES'] svg")) > 0


def _chart_errored(driver: webdriver.Chrome) -> bool:
    """True when Google is showing its soft-throttle 'Oops / try again' state."""
    source = driver.page_source.lower()
    return "something went wrong" in source or "try again in a bit" in source


# Google's HARD block replaces the whole Explore page. Observed live 2026-08-16
# after ~9 fresh sessions in ~10 minutes: <title>Error 429 (Too Many
# Requests)!!1</title> + "We're sorry, but you have sent too many requests to us
# recently. Please try again later." The "/sorry/" interstitial ("Our systems
# have detected unusual traffic from your computer network") is Google's other
# block form (known page; not observed in that session). Neither contains the
# soft-throttle phrases, so before 1.5.1 both fell through to "timeout" and were
# reported as a DOM change — after reloading the block page ~10 times.
_BLOCK_PAGE_MARKERS = (
    "error 429 (too many requests)",  # the block page's <title>, verbatim
    "sent too many requests",
    "unusual traffic from your computer network",
)


def _page_blocked(driver: webdriver.Chrome) -> bool:
    """True when Google replaced the Explore page with a hard block (429/sorry)."""
    source = driver.page_source.lower()
    return any(marker in source for marker in _BLOCK_PAGE_MARKERS)


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
        ``"ready"`` if the interest-over-time chart rendered; ``"blocked"`` if
        Google replaced the page with its hard 429 / "unusual traffic" block
        (returned at once — reloading a block page only deepens the block);
        ``"throttled"`` if Google's soft-throttle ('try again') state was seen
        while waiting; or ``"timeout"`` if none of these happened — which
        usually means the Explore DOM changed rather than a rate-limit (so the
        caller should not tell the user to "wait and retry").
    """
    saw_throttle = False
    for _ in range(attempts):
        waited = 0.0
        while waited < per_attempt:
            if _chart_ready(driver):
                return "ready"
            if _page_blocked(driver):
                return "blocked"
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
    if _page_blocked(driver):
        return "blocked"
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


def _req_keyword_type(widget_url: str) -> str:
    """The ``req`` param's keywordType: ``"QUERY"`` (related queries) or
    ``"ENTITY"`` (related topics); empty string if unparseable."""
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(widget_url).query)
        req = json.loads(query["req"][0])
    except (KeyError, IndexError, ValueError):
        return ""
    return str(req.get("keywordType", "")) if isinstance(req, dict) else ""


def _collect_widget_urls(driver: webdriver.Chrome) -> Dict[str, str]:
    """Read the widgetdata request URLs the page issued, from the perf log.

    The page issues TWO ``relatedsearches`` requests — related *queries*
    (``keywordType: QUERY``) and related *topics* (``ENTITY``) — verified live
    2026-08-11. The queries slot is pinned to the QUERY-kind request so it can
    never silently pick up topic-shaped data on a page reorder (before 1.5.0
    this relied on request ordering). An ENTITY request is never used as a
    fallback; an unknown kind is (defensive: if Google drops keywordType, the
    pre-1.5.0 behavior is preserved rather than losing related queries).
    """
    wanted = ("multiline", "relatedsearches", "comparedgeo")
    urls: Dict[str, str] = {}
    related_fallback = None
    for entry in driver.get_log("performance"):
        try:
            message = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue
        if message.get("method") != "Network.requestWillBeSent":
            continue
        url = message.get("params", {}).get("request", {}).get("url", "")
        for key in wanted:
            if f"widgetdata/{key}" not in url:
                continue
            if key == "relatedsearches":
                kind = _req_keyword_type(url)
                if kind == "QUERY":
                    urls[key] = url  # keep the most recent QUERY-kind request
                elif kind != "ENTITY":
                    related_fallback = url
            else:
                urls[key] = url  # keep the most recent successful request
    if "relatedsearches" not in urls and related_fallback is not None:
        urls["relatedsearches"] = related_fallback
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

    ``blocked`` → RateLimitError (Google's hard 429 / "unusual traffic" block —
    a per-IP cooldown, not a transient); ``throttled`` → RateLimitError
    (Google's soft-throttle persisted); ``timeout`` → BrowserError (chart never
    rendered *and* no throttle message — the Explore DOM likely changed, so
    "wait and retry" would be bad advice).
    """
    if chart_status == "ready":
        return
    if chart_status == "blocked":
        raise RateLimitError(
            "Google Trends is blocking Explore requests from this IP "
            "(HTTP 429 'too many requests' / 'unusual traffic' page).\n\n"
            "This is a hard, per-IP cooldown, not a transient glitch — the "
            "Explore endpoints allow roughly 8-10 fresh browser sessions per "
            "hour before blocking. Solutions:\n"
            "• Wait 30+ minutes before trying again (retrying sooner extends the block)\n"
            "• Reuse results: cache='disk' answers identical repeat requests without a session\n"
            "• Use the RSS path for fast, frequent real-time checks\n\n" + context
        )
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
    gprop: str = "",
    cookie_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Drive one browser session and return the requested Explore widgets.

    Always returns ``interest_over_time``. Returns ``related_queries`` /
    ``interest_by_region`` only when requested (they need a scroll to load).
    With ``cookie_path`` the session presents the saved cookie jar (a returning
    visitor) and refreshes it on success — see :mod:`._cookies`.

    Raises:
        RateLimitError: if Google serves its hard 429 / "unusual traffic" block
            page (detected at once, no reload ladder), or the chart never
            renders because the soft-throttle persisted.
        BrowserError: if Chrome cannot start.
        DownloadError: if the chart renders but its data cannot be retrieved.
    """
    url = _build_explore_url(keyword, geo, timeframe, category, gprop)
    driver = _build_driver(headless)
    try:
        _warm_up(driver)
        jar = _load_cookies(cookie_path) if cookie_path else []
        if jar:
            _inject_cookies(driver, jar)
        driver.get(url)
        time.sleep(3)
        _dismiss_cookie_banner(driver)

        chart_status = _await_chart(
            driver, url, attempts=max_load_attempts, per_attempt=per_attempt_wait
        )
        if cookie_path:
            _remember_session(driver, cookie_path, chart_status, bool(jar))
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
    gprop: str = "",
    cookie_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Drive one browser session for a multi-keyword comparison.

    Always returns ``interest_over_time`` + ``averages``. Returns
    ``interest_by_region`` (the combined per-region comparison) only when
    requested — that widget lazy-loads on scroll.

    Raises:
        RateLimitError: if Google serves its hard 429 / "unusual traffic" block
            page (detected at once, no reload ladder), or the chart never
            renders because the soft-throttle persisted.
        BrowserError: if Chrome cannot start, or the Explore DOM changed.
        DownloadError: if the chart renders but its data cannot be retrieved.
    """
    url = _build_explore_url(",".join(keywords), geo, timeframe, category, gprop)
    driver = _build_driver(headless)
    try:
        _warm_up(driver)
        jar = _load_cookies(cookie_path) if cookie_path else []
        if jar:
            _inject_cookies(driver, jar)
        driver.get(url)
        time.sleep(3)
        _dismiss_cookie_banner(driver)

        chart_status = _await_chart(
            driver, url, attempts=max_load_attempts, per_attempt=per_attempt_wait
        )
        if cookie_path:
            _remember_session(driver, cookie_path, chart_status, bool(jar))
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
