"""
trendspyg - Free, open-source Python library for Google Trends data

A modern, actively-maintained alternative to the archived pytrends.
Supports 125 countries, 51 US states, 20 categories, and multiple output formats.

Three data paths:
- **RSS Feed** (fast path): current trending topics with images & news (~0.2s)
- **CSV Export** (full path): ~480 current trends with time/category filtering (~10s)
- **Explore** (keyword path): interest over time, related queries, and interest
  by region for a specific term — the data pytrends was most used for

Choose your data source:
- Use RSS for: real-time monitoring, news context, images, qualitative research
- Use CSV for: large trending datasets, time filtering, statistical analysis
- Use Explore for: how interest in a keyword moves over time and where it peaks
"""

from .version import __version__

__author__ = "flack0x"
__license__ = "MIT"

# Import core downloaders
from .downloader import download_google_trends_csv

# Import Explore path (keyword analysis: interest over time, related, geo)
from .explore import (
    EXPLORE_SCHEMA_VERSION,
    download_google_trends_explore,
    download_google_trends_interest_over_time,
)

# Import monitoring (real-time change detection, built on the RSS path — new in 0.7.0)
from .monitor import (
    MONITOR_SCHEMA_VERSION,
    diff_trends,
    filter_changes,
    post_webhook,
    watch_google_trends_rss,
)
from .normalize import SCHEMA_VERSION
from .rss_downloader import (
    download_google_trends_rss,
    download_google_trends_rss_async,
    download_google_trends_rss_batch,
    download_google_trends_rss_batch_async,
)

# Import typed return shapes (static hints; runtime values are plain dicts)
from .types import (
    ExploreEnvelope,
    InterestPoint,
    NewsArticle,
    NormalizedEnvelope,
    NormalizedTrend,
    RegionInterest,
    RelatedQuery,
    Trend,
    TrendChange,
    TrendEnvelope,
    TrendImage,
)

# Import cache utilities
from .utils import (
    clear_rss_cache,
    get_rss_cache_stats,
    set_rss_cache_ttl,
)

# Export public API
__all__ = [
    "__version__",
    # Core downloaders
    "download_google_trends_csv",  # Full-featured CSV download (480 trends, filtering)
    "download_google_trends_rss",  # Fast RSS download (rich media, news articles)
    "download_google_trends_rss_async",  # Async RSS download for parallel fetching
    "download_google_trends_rss_batch",  # Batch RSS download with progress bar
    "download_google_trends_rss_batch_async",  # Async batch RSS with progress bar (fastest)
    # Explore path (keyword analysis over time)
    "download_google_trends_interest_over_time",  # Keyword interest over time (pytrends core)
    "download_google_trends_explore",  # Full Explore: interest + related + geo
    # Monitoring (real-time change detection, RSS-only — new in 0.7.0)
    "watch_google_trends_rss",  # Poll the RSS feed and yield TrendChange events
    "diff_trends",  # Pure diff of two RSS snapshots -> list[TrendChange]
    "filter_changes",  # Filter changes by volume / event / watchlist
    "post_webhook",  # Fire-and-forget POST of a change as JSON
    # Cache control
    "clear_rss_cache",  # Clear all cached RSS data
    "get_rss_cache_stats",  # Get cache statistics (hits, misses, size)
    "set_rss_cache_ttl",  # Set cache TTL (0 to disable)
    # Schema-version constants (detect envelope/shape drift)
    "SCHEMA_VERSION",  # normalize=True NormalizedEnvelope schema
    "EXPLORE_SCHEMA_VERSION",  # ExploreEnvelope schema
    "MONITOR_SCHEMA_VERSION",  # TrendChange schema
    # Typed return shapes
    "Trend",  # TypedDict: single trend record
    "NewsArticle",  # TypedDict: news article on a trend
    "TrendImage",  # TypedDict: image on a trend
    "TrendEnvelope",  # TypedDict: {fetched_at, geo, count, trends}
    "NormalizedTrend",  # TypedDict: unified agent-friendly trend (normalize=True)
    "NormalizedEnvelope",  # TypedDict: unified envelope (normalize=True)
    "InterestPoint",  # TypedDict: one interest-over-time point
    "RelatedQuery",  # TypedDict: a related search query (top/rising)
    "RegionInterest",  # TypedDict: interest for one region
    "ExploreEnvelope",  # TypedDict: full Explore result for a keyword
    "TrendChange",  # TypedDict: one change between two RSS snapshots (monitoring)
]
