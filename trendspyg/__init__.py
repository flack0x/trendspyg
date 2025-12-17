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

__version__ = "0.2.0"
__author__ = "flack0x"
__license__ = "MIT"

# Import core downloaders
from .downloader import download_google_trends_csv
from .rss_downloader import download_google_trends_rss

# Export public API
__all__ = [
    "__version__",
    "download_google_trends_csv",      # Full-featured CSV download (480 trends, filtering)
    "download_google_trends_rss",      # Fast RSS download (rich media, news articles)
]
