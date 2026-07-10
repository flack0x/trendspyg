"""MCP server exposing trendspyg as tools for AI agents.

Lets any MCP client (Claude Desktop, Claude Code, Cursor, ...) query Google
Trends through trendspyg — no Python required on the agent side.

Install and run::

    pip install trendspyg[mcp]     # needs Python 3.10+
    trendspyg-mcp                  # stdio transport

The tool functions below are plain, framework-free functions so they import
and test on every Python trendspyg supports (3.8+); only ``build_server()``
touches the ``mcp`` SDK, which requires Python 3.10+.
"""

import shutil
import tempfile
from typing import Any, Dict, List, cast

from .config import CATEGORIES, COUNTRIES, TIME_PERIODS, US_STATES
from .downloader import download_google_trends_csv
from .explore import download_google_trends_comparison, download_google_trends_interest_over_time
from .monitor import diff_trends
from .rss_downloader import (
    download_google_trends_rss,
    download_google_trends_rss_batch,
)

SERVER_NAME = "trendspyg"

_INSTRUCTIONS = (
    "Live Google Trends data. Prefer get_trending_now / compare_trending / "
    "get_trend_changes — they answer in under a second. get_interest_over_time, "
    "compare_interest_over_time (~10-40s) and get_trending_full (~10-15s) drive "
    "a real Chrome browser: they need Chrome installed on this machine and are "
    "rate-limited by Google — never call them in a loop."
)

_MAX_COMPARE_GEOS = 20

# Fail-fast retry profile for the Explore-backed tool: ~40s worst case
# (4 x (6s watch + ~2s reload) + page load) instead of the library default's
# ~100s, so the call fits typical MCP client tool timeouts. If Google is
# throttling hard enough to exhaust this, the agent should back off anyway.
_EXPLORE_MAX_RETRIES = 4
_EXPLORE_RETRY_WAIT = 6.0

# Last raw snapshot per geo, so get_trend_changes can diff against the
# previous call within this server process's lifetime.
_last_snapshots: Dict[str, List[Dict[str, Any]]] = {}


def get_trending_now(geo: str = "US") -> Dict[str, Any]:
    """Get what is trending on Google right now for a country or US state.

    Fast (~0.2s, no browser). Returns a normalized envelope with ~10-20
    trends: keyword, rank, search volume (text + numeric minimum), start
    time, related queries, news articles with sources, and an image.
    geo examples: "US", "GB", "JP", "US-CA". Use list_supported_options
    for the full list.
    """
    # normalize=True always returns the envelope dict; the annotation is a wide Union.
    envelope = cast(Dict[str, Any], download_google_trends_rss(geo=geo, normalize=True))
    return envelope


def compare_trending(geos: List[str]) -> Dict[str, Any]:
    """Get current Google trends for several countries/states in one call.

    Fast (~0.2s per geo, no browser). Returns {geo: envelope} with the same
    normalized shape as get_trending_now. Accepts 1-20 geo codes, e.g.
    ["US", "GB", "DE"].
    """
    if not geos or len(geos) > _MAX_COMPARE_GEOS:
        raise ValueError(
            f"Pass between 1 and {_MAX_COMPARE_GEOS} geo codes (got {len(geos)}). "
            "For a broad sweep, call this tool several times with smaller batches."
        )
    results = download_google_trends_rss_batch(list(geos), show_progress=False, normalize=True)
    return dict(results)


def get_trend_changes(geo: str = "US") -> Dict[str, Any]:
    """Report what changed in Google trends for a geo since this tool was last called.

    Fast (~0.2s, no browser). The first call for a geo captures a baseline
    and reports no changes; each later call returns events diffed against
    the previous call: new, dropped, volume_up, volume_down, rank_change.
    Useful for monitoring a topic over a conversation or scheduled runs.
    """
    current = cast(
        List[Dict[str, Any]],
        download_google_trends_rss(geo=geo, output_format="dict", cache=False),
    )
    previous = _last_snapshots.get(geo)
    _last_snapshots[geo] = current

    if previous is None:
        return {
            "geo": geo,
            "baseline": True,
            "trend_count": len(current),
            "changes": [],
            "message": (
                "Baseline captured for this geo in this session. "
                "Call again later to see what changed."
            ),
        }

    changes = diff_trends(previous, current)
    return {
        "geo": geo,
        "baseline": False,
        "previous_count": len(previous),
        "current_count": len(current),
        "change_count": len(changes),
        "changes": list(changes),
    }


def list_supported_options() -> Dict[str, Any]:
    """List every supported geo code plus the filters get_trending_full accepts.

    Instant (no network). Returns 125 country codes, 51 US state codes,
    the category keys and hour windows for get_trending_full, and
    timeframe examples for get_interest_over_time.
    """
    return {
        "countries": dict(COUNTRIES),
        "us_states": dict(US_STATES),
        "csv_categories": sorted(CATEGORIES),
        "csv_hours": sorted(TIME_PERIODS),
        "explore_timeframe_examples": ["now 7-d", "today 1-m", "today 12-m", "today 5-y", "all"],
    }


def get_interest_over_time(
    keyword: str, geo: str = "US", timeframe: str = "today 12-m"
) -> List[Dict[str, Any]]:
    """Get Google's 0-100 relative search interest for a keyword over time.

    SLOW: drives a real Chrome browser against Google's Explore page —
    typically 10-40 seconds (capped at roughly 40s: this server uses a
    fail-fast retry profile, so a persistent throttle errors out instead of
    hanging). Requires Chrome on this machine; Google rate-limits it
    aggressively. Call it once for analysis; NEVER poll it or call it in a
    loop — if it fails with a rate-limit error, wait a few minutes.
    Returns [{date, value, is_partial}, ...]. timeframe examples:
    "now 7-d", "today 12-m", "today 5-y", "all".
    """
    points = download_google_trends_interest_over_time(
        keyword,
        geo=geo,
        timeframe=timeframe,
        output_format="dict",
        max_retries=_EXPLORE_MAX_RETRIES,
        retry_wait=_EXPLORE_RETRY_WAIT,
    )
    return list(points)


def compare_interest_over_time(
    keywords: List[str], geo: str = "US", timeframe: str = "today 12-m"
) -> Dict[str, Any]:
    """Compare 2-5 keywords' search interest on ONE shared 0-100 scale.

    Use this (not repeated get_interest_over_time calls) to compare terms:
    Google scales each single-keyword series independently, so only this
    comparison returns directly comparable numbers. SLOW: drives a real
    Chrome browser — typically 10-40 seconds (fail-fast retry profile, so a
    persistent throttle errors out instead of hanging). Requires Chrome on
    this machine; rate-limited by Google — NEVER poll it or call it in a
    loop. Returns {keywords, averages: {kw: 0-100}, interest_over_time:
    [{date, values: {kw: 0-100}, is_partial}], ...}. keywords: 2-5 distinct
    terms, no commas. timeframe examples: "now 7-d", "today 12-m", "today 5-y".
    """
    envelope = cast(
        Dict[str, Any],
        download_google_trends_comparison(
            list(keywords),
            geo=geo,
            timeframe=timeframe,
            output_format="dict",
            include_geo=False,  # keep the call inside the fail-fast time budget
            max_retries=_EXPLORE_MAX_RETRIES,
            retry_wait=_EXPLORE_RETRY_WAIT,
        ),
    )
    return envelope


def get_trending_full(geo: str = "US", hours: int = 24, category: str = "all") -> Dict[str, Any]:
    """Get the full trending list (480+ trends) with time and category filters.

    SLOW: drives a real Chrome browser (~10-15 seconds, requires Chrome on
    this machine). Use only when get_trending_now's ~20 trends are not
    enough or you need category/time filtering. hours: 4, 24, 48 or 168.
    category examples: "all", "sports", "entertainment" — see
    list_supported_options. Returns the same normalized envelope shape as
    get_trending_now.
    """
    tmp_dir = tempfile.mkdtemp(prefix="trendspyg_mcp_")
    try:
        envelope = cast(
            Dict[str, Any],
            download_google_trends_csv(
                geo=geo, hours=hours, category=category, download_dir=tmp_dir, normalize=True
            ),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return envelope


_TOOLS = (
    get_trending_now,
    compare_trending,
    get_trend_changes,
    list_supported_options,
    get_interest_over_time,
    compare_interest_over_time,
    get_trending_full,
)


def build_server() -> Any:
    """Build the FastMCP server with all trendspyg tools registered."""
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise ImportError(
            "The 'mcp' package is required to run the trendspyg MCP server.\n"
            "Install with: pip install trendspyg[mcp] (requires Python 3.10+)"
        ) from exc

    server = FastMCP(SERVER_NAME, instructions=_INSTRUCTIONS)
    annotations = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
    for fn in _TOOLS:
        server.tool(annotations=annotations)(fn)
    return server


def main() -> None:
    """Entry point for the ``trendspyg-mcp`` console script (stdio transport)."""
    build_server().run()


if __name__ == "__main__":
    main()
