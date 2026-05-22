"""
trendspyg - Free, open-source Python library for Google Trends data

A modern alternative to pytrends with 188,000+ configuration options.
Download real-time Google Trends data with support for 125 countries,
51 US states, 20 categories, and multiple output formats.

Core functionality:
- **RSS Feed** (fast path): Rich media data with images & news articles (0.2s)
- **CSV Export** (full path): Comprehensive trend data with filtering (10s)
- Multiple output formats (CSV, JSON, Parquet, DataFrame)
- Active trends filtering and sorting options

Choose your data source:
- Use RSS for: Real-time monitoring, news context, images, qualitative research
- Use CSV for: Large datasets, time filtering, statistical analysis, quantitative research
"""

from .version import __version__

__author__ = "flack0x"
__license__ = "MIT"

# Import core downloaders
from .downloader import download_google_trends_csv
from .rss_downloader import (
    download_google_trends_rss,
    download_google_trends_rss_async,
    download_google_trends_rss_batch,
    download_google_trends_rss_batch_async,
)

# Import cache utilities
from .utils import (
    clear_rss_cache,
    get_rss_cache_stats,
    set_rss_cache_ttl,
)

# Import typed return shapes (static hints; runtime values are plain dicts)
from .types import (
    NewsArticle,
    NormalizedEnvelope,
    NormalizedTrend,
    Trend,
    TrendEnvelope,
    TrendImage,
)

# Export public API
__all__ = [
    "__version__",
    # Core downloaders
    "download_google_trends_csv",              # Full-featured CSV download (480 trends, filtering)
    "download_google_trends_rss",              # Fast RSS download (rich media, news articles)
    "download_google_trends_rss_async",        # Async RSS download for parallel fetching
    "download_google_trends_rss_batch",        # Batch RSS download with progress bar
    "download_google_trends_rss_batch_async",  # Async batch RSS with progress bar (fastest)
    # Cache control
    "clear_rss_cache",                         # Clear all cached RSS data
    "get_rss_cache_stats",                     # Get cache statistics (hits, misses, size)
    "set_rss_cache_ttl",                       # Set cache TTL (0 to disable)
    # Typed return shapes
    "Trend",                                   # TypedDict: single trend record
    "NewsArticle",                             # TypedDict: news article on a trend
    "TrendImage",                              # TypedDict: image on a trend
    "TrendEnvelope",                           # TypedDict: {fetched_at, geo, count, trends}
    "NormalizedTrend",                         # TypedDict: unified agent-friendly trend (normalize=True)
    "NormalizedEnvelope",                      # TypedDict: unified envelope (normalize=True)
]
