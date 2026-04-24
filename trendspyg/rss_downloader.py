#!/usr/bin/env python3
"""
Google Trends RSS Feed Downloader - Fast, Rich Media Data

This module provides fast access to Google Trends RSS feed data,
including images, news articles, and headlines. Perfect for:
- Real-time monitoring
- Qualitative research (news context)
- Visual content (images for presentations)
- Fast data collection (0.2s vs 10s for CSV)

Use Cases:
- Journalism: Breaking news validation with sources
- Research: Mixed methods (combine with CSV for complete picture)
- Trading: Fast alerts with news context
- Marketing: Quick trend checks with visual content
"""

import asyncio
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Union, Literal, TYPE_CHECKING, cast

if TYPE_CHECKING:
    import pandas as pd
    import aiohttp

from .config import COUNTRIES, US_STATES, DEFAULT_GEO
from .exceptions import InvalidParameterError, DownloadError, RateLimitError
from .utils import get_rss_cache

# Type aliases
OutputFormat = Literal['csv', 'json', 'dataframe', 'dict']


def _make_cache_key(
    geo: str,
    include_images: bool,
    include_articles: bool,
    max_articles_per_trend: int
) -> str:
    """Generate a cache key from request parameters."""
    return f"{geo}:{include_images}:{include_articles}:{max_articles_per_trend}"


def _handle_http_error(status_code: int, geo: str, url: str) -> None:
    """
    Raise appropriate exception based on HTTP status code.

    Provides specific, actionable error messages for common HTTP errors.
    """
    if status_code == 429 or status_code == 403:
        raise RateLimitError(
            f"Rate limit exceeded (HTTP {status_code})\n\n"
            "Google is temporarily blocking requests. Solutions:\n"
            "• Wait 1-2 minutes before trying again\n"
            "• Reduce request frequency (add delays between calls)\n"
            "• Use caching: results are cached for 5 minutes by default\n"
            "• For batch operations, use max_concurrent=5 or delay=0.5\n\n"
            f"Geo: {geo} | URL: {url}"
        )
    elif status_code == 404:
        raise DownloadError(
            f"RSS feed not found (HTTP 404)\n\n"
            f"The geo code '{geo}' may not have an RSS feed available.\n"
            "Try a different country code or check if the code is correct.\n\n"
            f"URL attempted: {url}"
        )
    elif status_code >= 500:
        raise DownloadError(
            f"Google Trends server error (HTTP {status_code})\n\n"
            "Google's servers are having issues. This is temporary.\n"
            "• Wait a few minutes and try again\n"
            "• Check https://trends.google.com to verify it's working\n\n"
            f"URL: {url}"
        )
    else:
        raise DownloadError(
            f"HTTP error {status_code} when fetching RSS feed\n\n"
            f"Geo: {geo}\n"
            f"URL: {url}\n\n"
            "If this persists, please report at:\n"
            "https://github.com/flack0x/trendspyg/issues"
        )


_TRAFFIC_PATTERN = re.compile(r"([\d,.]+)\s*([KMB]?)", re.IGNORECASE)
_TRAFFIC_SUFFIX = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def _parse_traffic_to_min(traffic: Optional[str]) -> int:
    """Parse a human-readable traffic string (e.g. '1000+', '50,000+', '2K+') into an int.

    Returns the minimum bound. Unparseable input returns 0 rather than raising
    so a malformed feed never breaks a caller sorting by traffic.
    """
    if not traffic or traffic == "N/A":
        return 0
    match = _TRAFFIC_PATTERN.search(traffic)
    if not match:
        return 0
    number_part, suffix = match.group(1), match.group(2).upper()
    try:
        value = float(number_part.replace(",", ""))
    except ValueError:
        return 0
    return int(value * _TRAFFIC_SUFFIX.get(suffix, 1))


def _parse_rss_xml(
    xml_content: bytes,
    geo: str,
    include_images: bool,
    include_articles: bool,
    max_articles_per_trend: int
) -> List[Dict]:
    """
    Parse RSS XML content into list of trend dictionaries.

    Shared parsing logic used by both sync and async downloaders.

    Args:
        xml_content: Raw XML bytes from RSS feed
        geo: Geographic code for explore links
        include_images: Include image URLs and sources
        include_articles: Include news articles data
        max_articles_per_trend: Max news articles per trend

    Returns:
        List of trend dictionaries

    Raises:
        DownloadError: If XML parsing fails
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        raise DownloadError(f"Failed to parse RSS XML: {e}")

    # Define namespace
    ns = {'ht': 'https://trends.google.com/trending/rss'}

    # Extract trend data
    trends = []

    for item in root.findall('.//item'):
        # Basic info
        title = item.find('title')
        trend = title.text if title is not None else 'N/A'

        traffic_elem = item.find('ht:approx_traffic', ns)
        traffic = traffic_elem.text if traffic_elem is not None else 'N/A'

        pub_date_elem = item.find('pubDate')
        pub_date_str = pub_date_elem.text if pub_date_elem is not None else None

        # Parse date to datetime
        published: Union[datetime, str, None] = None
        if pub_date_str:
            try:
                # RFC 2822 format: "Tue, 4 Nov 2025 03:00:00 -0800"
                published = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
            except ValueError:
                # Fallback: keep as string
                published = pub_date_str

        # Build trend dict
        trend_data: Dict = {
            'trend': trend,
            'traffic': traffic,
            'traffic_min': _parse_traffic_to_min(traffic),
            'published': published,
            'explore_link': f"https://trends.google.com/trends/explore?q={trend}&geo={geo}&hl=en-US"
        }

        # Add image if requested
        if include_images:
            picture_elem = item.find('ht:picture', ns)
            picture_source_elem = item.find('ht:picture_source', ns)

            trend_data['image'] = {
                'url': picture_elem.text if picture_elem is not None else None,
                'source': picture_source_elem.text if picture_source_elem is not None else None
            }

        # Add news articles if requested
        if include_articles:
            articles = []
            news_items = item.findall('ht:news_item', ns)[:max_articles_per_trend]

            for news in news_items:
                headline_elem = news.find('ht:news_item_title', ns)
                url_elem = news.find('ht:news_item_url', ns)
                source_elem = news.find('ht:news_item_source', ns)
                image_elem = news.find('ht:news_item_picture', ns)

                article = {
                    'headline': headline_elem.text if headline_elem is not None else None,
                    'url': url_elem.text if url_elem is not None else None,
                    'source': source_elem.text if source_elem is not None else None,
                    'image': image_elem.text if image_elem is not None else None
                }
                articles.append(article)

            trend_data['news_articles'] = articles

        trends.append(trend_data)

    return trends


def _format_output(
    trends: List[Dict],
    output_format: OutputFormat,
    include_images: bool,
    include_articles: bool
) -> Union[List[Dict], str, 'pd.DataFrame']:
    """
    Format trends data into requested output format.

    Shared formatting logic used by both sync and async downloaders.

    Args:
        trends: List of trend dictionaries
        output_format: Output format ('dict', 'dataframe', 'json', 'csv')
        include_images: Whether images were included
        include_articles: Whether articles were included

    Returns:
        Formatted output in requested format

    Raises:
        InvalidParameterError: If output_format is invalid
        ImportError: If pandas not installed for 'dataframe' format
    """
    if output_format == 'dict':
        return trends

    elif output_format == 'dataframe':
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "pandas is required for 'dataframe' format.\n"
                "Install with: pip install trendspyg[analysis]"
            )

        # Flatten nested structures for DataFrame
        flattened = []
        for trend in trends:
            flat = {
                'trend': trend['trend'],
                'traffic': trend['traffic'],
                'traffic_min': trend.get('traffic_min', 0),
                'published': trend['published'],
                'explore_link': trend['explore_link']
            }

            if include_images and 'image' in trend:
                flat['image_url'] = trend['image']['url']
                flat['image_source'] = trend['image']['source']

            if include_articles and 'news_articles' in trend:
                # Add count and first article for main DataFrame
                flat['article_count'] = len(trend['news_articles'])
                if trend['news_articles']:
                    flat['top_article_headline'] = trend['news_articles'][0]['headline']
                    flat['top_article_url'] = trend['news_articles'][0]['url']
                    flat['top_article_source'] = trend['news_articles'][0]['source']

            flattened.append(flat)

        return pd.DataFrame(flattened)

    elif output_format == 'json':
        import json
        # Convert datetime objects to strings for JSON
        json_trends = []
        for trend in trends:
            trend_copy = trend.copy()
            if isinstance(trend_copy.get('published'), datetime):
                trend_copy['published'] = trend_copy['published'].isoformat()
            json_trends.append(trend_copy)

        return json.dumps(json_trends, indent=2)

    elif output_format == 'csv':
        # Simple CSV format
        import csv
        from io import StringIO

        output = StringIO()
        if not trends:
            return ""

        # Determine fields based on options
        fieldnames = ['trend', 'traffic', 'traffic_min', 'published', 'explore_link']
        if include_images:
            fieldnames.extend(['image_url', 'image_source'])
        if include_articles:
            fieldnames.extend(['article_count', 'top_article_headline', 'top_article_url', 'top_article_source'])

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for trend in trends:
            row = {
                'trend': trend['trend'],
                'traffic': trend['traffic'],
                'traffic_min': trend.get('traffic_min', 0),
                'published': trend['published'].isoformat() if isinstance(trend['published'], datetime) else trend['published'],
                'explore_link': trend['explore_link']
            }

            if include_images and 'image' in trend:
                row['image_url'] = trend['image']['url']
                row['image_source'] = trend['image']['source']

            if include_articles and 'news_articles' in trend:
                row['article_count'] = len(trend['news_articles'])
                if trend['news_articles']:
                    row['top_article_headline'] = trend['news_articles'][0]['headline']
                    row['top_article_url'] = trend['news_articles'][0]['url']
                    row['top_article_source'] = trend['news_articles'][0]['source']

            writer.writerow(row)

        return output.getvalue()

    else:
        raise InvalidParameterError(
            f"Invalid output_format: '{output_format}'. "
            "Must be one of: 'dict', 'dataframe', 'json', 'csv'"
        )


def _validate_geo_rss(geo: str) -> str:
    """Validate geo parameter for RSS.

    Args:
        geo: Country code (e.g., 'US', 'GB')

    Returns:
        Validated geo code (uppercase)

    Raises:
        InvalidParameterError: If geo is invalid
    """
    geo = geo.upper()

    if geo in COUNTRIES or geo in US_STATES:
        return geo

    # Suggest similar matches
    similar = [code for code in list(COUNTRIES.keys()) + list(US_STATES.keys())
               if code.startswith(geo[0]) if len(geo) > 0][:5]

    error_msg = f"Invalid geo code '{geo}'."
    if similar:
        error_msg += f" Did you mean: {', '.join(similar)}?"
    error_msg += f"\n\nAvailable: {len(COUNTRIES)} countries, {len(US_STATES)} US states"
    error_msg += "\nSee trendspyg.config.COUNTRIES and trendspyg.config.US_STATES"

    raise InvalidParameterError(error_msg)


def download_google_trends_rss(
    geo: str = DEFAULT_GEO,
    output_format: OutputFormat = 'dict',
    include_images: bool = True,
    include_articles: bool = True,
    max_articles_per_trend: int = 5,
    cache: bool = True
) -> Union[List[Dict], str, 'pd.DataFrame']:
    """
    Download Google Trends RSS feed data with rich media content.

    **Fast alternative to CSV download** (0.2s vs 10s):
    - Returns ~10-20 current trending topics
    - Includes images, news articles, headlines
    - No time filtering (always current trends)
    - Perfect for real-time monitoring and qualitative research

    **Caching:** Results are cached for 5 minutes by default to reduce
    API calls and improve performance for repeated requests. Use `cache=False`
    to bypass the cache and always fetch fresh data.

    **Data Provided (RSS-specific):**
    - ✅ News article headlines and URLs
    - ✅ Article images and sources
    - ✅ Trend image (thumbnail)
    - ✅ Publication timestamp
    - ✅ Traffic volume

    **NOT Provided (use CSV for these):**
    - ❌ Start/end timestamps
    - ❌ Related search breakdown
    - ❌ Time period filtering
    - ❌ Category filtering
    - ❌ Large dataset (480 trends)

    **When to use RSS:**
    - Journalism: Need news articles + sources quickly
    - Research: Qualitative analysis (article content)
    - Monitoring: Real-time alerts (fast, frequent polling)
    - Visual content: Images for presentations/articles

    **When to use CSV instead:**
    - Need >20 trends (CSV has 480)
    - Need time filtering (4h, 24h, 48h, 7d)
    - Need category filtering (sports, tech, etc.)
    - Need historical context (start/end times)
    - Statistical analysis (large dataset)

    Args:
        geo: Country/region code (e.g., 'US', 'GB', 'US-CA')
              Supports 125 countries + 51 US states
        output_format: Output format
            - 'dict' (default): List of dictionaries (Python native)
            - 'dataframe': pandas DataFrame (requires pandas)
            - 'json': JSON string
            - 'csv': CSV string
        include_images: Include image URLs and sources
        include_articles: Include news articles data
        max_articles_per_trend: Max news articles to include per trend (default: 5)
        cache: Use cached results if available (default: True)
               Set to False to always fetch fresh data

    Returns:
        Depending on output_format:
        - 'dict': List[Dict] - List of trend dictionaries
        - 'dataframe': pd.DataFrame - pandas DataFrame
        - 'json': str - JSON string
        - 'csv': str - CSV string

    Raises:
        InvalidParameterError: If parameters are invalid
        DownloadError: If RSS fetch fails

    Examples:
        >>> # Basic usage - Fast data for monitoring
        >>> trends = download_google_trends_rss(geo='US')
        >>> print(f"Found {len(trends)} trending topics")
        >>> print(trends[0]['trend'])  # First trend title

        >>> # For research - Get news articles for qualitative analysis
        >>> trends = download_google_trends_rss(
        ...     geo='US',
        ...     output_format='dataframe',  # pandas for analysis
        ...     include_articles=True
        ... )
        >>> # Access news articles for each trend
        >>> for trend in trends:
        ...     print(f"{trend['trend']}: {len(trend['news_articles'])} articles")

        >>> # For journalism - Quick check with sources
        >>> trends = download_google_trends_rss(geo='US', output_format='json')
        >>> # Use in API or save to file

        >>> # For presentations - Get images
        >>> trends = download_google_trends_rss(geo='US', include_images=True)
        >>> image_url = trends[0]['image']['url']
        >>> image_source = trends[0]['image']['source']

        >>> # Bypass cache for fresh data
        >>> trends = download_google_trends_rss(geo='US', cache=False)

    Performance:
        - Speed: ~0.2 seconds (50x faster than CSV), instant if cached
        - Trends: ~10-20 items
        - Data size: ~50-100KB
        - Update frequency: ~9 times per hour
        - Cache TTL: 5 minutes (configurable via set_rss_cache_ttl)

    Data Structure (dict format):
        {
            'trend': str,              # Search term
            'traffic': str,            # '200+', '2000+', etc.
            'published': datetime,     # Publication time
            'image': {                 # Trend thumbnail (if include_images=True)
                'url': str,
                'source': str
            },
            'news_articles': [         # Related articles (if include_articles=True)
                {
                    'headline': str,
                    'url': str,
                    'source': str,
                    'image': str
                }
            ],
            'explore_link': str        # Google Trends explore URL
        }
    """
    # Validate parameters
    geo = _validate_geo_rss(geo)

    # Check cache first
    cache_key = _make_cache_key(geo, include_images, include_articles, max_articles_per_trend)
    if cache:
        cached_trends = get_rss_cache().get(cache_key)
        if cached_trends is not None:
            # Return cached data in requested format
            return _format_output(cached_trends, output_format, include_images, include_articles)

    # Build RSS URL
    url = f"https://trends.google.com/trending/rss?geo={geo}"

    try:
        # Fetch RSS feed
        response = requests.get(url, timeout=10)
        response.raise_for_status()

    except requests.HTTPError as e:
        # Handle HTTP errors with specific messages
        _handle_http_error(e.response.status_code, geo, url)

    except requests.ConnectionError:
        raise DownloadError(
            "Connection failed - cannot reach Google Trends\n\n"
            "Possible causes:\n"
            "• No internet connection\n"
            "• DNS resolution failed\n"
            "• Firewall blocking the request\n\n"
            "Check your internet connection and try again."
        )

    except requests.Timeout:
        raise DownloadError(
            "Request timed out after 10 seconds\n\n"
            "Possible causes:\n"
            "• Slow internet connection\n"
            "• Google Trends is experiencing delays\n\n"
            "Try again in a moment."
        )

    except requests.RequestException as e:
        raise DownloadError(
            f"Network error: {type(e).__name__}\n\n"
            f"Details: {e}\n"
            f"URL: {url}"
        )

    # Parse XML and extract trends using shared helper
    trends = _parse_rss_xml(
        xml_content=response.content,
        geo=geo,
        include_images=include_images,
        include_articles=include_articles,
        max_articles_per_trend=max_articles_per_trend
    )

    # Store in cache (always store as dict for reuse with different output formats)
    if cache:
        get_rss_cache().set(cache_key, trends)

    # Format and return using shared helper
    return _format_output(trends, output_format, include_images, include_articles)


async def download_google_trends_rss_async(
    geo: str = DEFAULT_GEO,
    output_format: OutputFormat = 'dict',
    include_images: bool = True,
    include_articles: bool = True,
    max_articles_per_trend: int = 5,
    session: Optional['aiohttp.ClientSession'] = None,
    cache: bool = True
) -> Union[List[Dict], str, 'pd.DataFrame']:
    """
    Async version of download_google_trends_rss for concurrent fetching.

    **Why use async?**
    - Fetch multiple countries/regions in parallel
    - 3x-100x faster for batch operations
    - Non-blocking for web applications (FastAPI, Django async)
    - Resource efficient - one thread handles many connections

    **Caching:** Results are cached for 5 minutes by default (shared with sync version).
    Use `cache=False` to bypass the cache and always fetch fresh data.

    **Performance comparison:**
    ```python
    # Sync (sequential) - 125 countries takes ~25 seconds
    for geo in COUNTRIES:
        trends = download_google_trends_rss(geo=geo)

    # Async (parallel) - 125 countries takes ~0.5 seconds
    results = await asyncio.gather(*[
        download_google_trends_rss_async(geo=geo)
        for geo in COUNTRIES
    ])
    ```

    Args:
        geo: Country/region code (e.g., 'US', 'GB', 'US-CA')
              Supports 125 countries + 51 US states
        output_format: Output format
            - 'dict' (default): List of dictionaries (Python native)
            - 'dataframe': pandas DataFrame (requires pandas)
            - 'json': JSON string
            - 'csv': CSV string
        include_images: Include image URLs and sources
        include_articles: Include news articles data
        max_articles_per_trend: Max news articles to include per trend (default: 5)
        session: Optional aiohttp.ClientSession for connection reuse.
                 If not provided, a new session is created per call.
                 For best performance with multiple requests, create and
                 reuse a single session.
        cache: Use cached results if available (default: True)
               Set to False to always fetch fresh data

    Returns:
        Depending on output_format:
        - 'dict': List[Dict] - List of trend dictionaries
        - 'dataframe': pd.DataFrame - pandas DataFrame
        - 'json': str - JSON string
        - 'csv': str - CSV string

    Raises:
        InvalidParameterError: If parameters are invalid
        DownloadError: If RSS fetch fails
        ImportError: If aiohttp is not installed

    Examples:
        >>> # Basic async usage
        >>> import asyncio
        >>> trends = asyncio.run(download_google_trends_rss_async(geo='US'))

        >>> # Fetch multiple countries in parallel (50x faster than sync)
        >>> async def fetch_all():
        ...     countries = ['US', 'GB', 'CA', 'AU', 'DE']
        ...     results = await asyncio.gather(*[
        ...         download_google_trends_rss_async(geo=geo)
        ...         for geo in countries
        ...     ])
        ...     return dict(zip(countries, results))
        >>> all_trends = asyncio.run(fetch_all())

        >>> # With session reuse for better performance
        >>> import aiohttp
        >>> async def fetch_with_session():
        ...     async with aiohttp.ClientSession() as session:
        ...         tasks = [
        ...             download_google_trends_rss_async(geo=geo, session=session)
        ...             for geo in ['US', 'GB', 'JP', 'DE', 'FR']
        ...         ]
        ...         return await asyncio.gather(*tasks)

        >>> # Use with FastAPI
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> @app.get("/trends/{country}")
        ... async def get_trends(country: str):
        ...     return await download_google_trends_rss_async(geo=country)

        >>> # Bypass cache for fresh data
        >>> trends = await download_google_trends_rss_async(geo='US', cache=False)

    Note:
        Requires aiohttp: pip install trendspyg[async]
    """
    try:
        import aiohttp
    except ImportError:
        raise ImportError(
            "aiohttp is required for async operations.\n"
            "Install with: pip install trendspyg[async]"
        )

    # Validate parameters
    geo = _validate_geo_rss(geo)

    # Check cache first
    cache_key = _make_cache_key(geo, include_images, include_articles, max_articles_per_trend)
    if cache:
        cached_trends = get_rss_cache().get(cache_key)
        if cached_trends is not None:
            # Return cached data in requested format
            return _format_output(cached_trends, output_format, include_images, include_articles)

    # Build RSS URL
    url = f"https://trends.google.com/trending/rss?geo={geo}"

    # Determine if we need to create our own session
    close_session = session is None

    try:
        if session is None:
            session = aiohttp.ClientSession()

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    _handle_http_error(response.status, geo, url)
                content = await response.read()

        except aiohttp.ClientResponseError as e:
            _handle_http_error(e.status, geo, url)

        except aiohttp.ClientConnectorError:
            raise DownloadError(
                "Connection failed - cannot reach Google Trends\n\n"
                "Possible causes:\n"
                "• No internet connection\n"
                "• DNS resolution failed\n"
                "• Firewall blocking the request\n\n"
                "Check your internet connection and try again."
            )

        except asyncio.TimeoutError:
            raise DownloadError(
                "Request timed out after 10 seconds\n\n"
                "Possible causes:\n"
                "• Slow internet connection\n"
                "• Google Trends is experiencing delays\n\n"
                "Try again in a moment."
            )

        except aiohttp.ClientError as e:
            raise DownloadError(
                f"Network error: {type(e).__name__}\n\n"
                f"Details: {e}\n"
                f"URL: {url}"
            )

    finally:
        if close_session and session is not None:
            await session.close()

    # Parse XML and extract trends using shared helper
    trends = _parse_rss_xml(
        xml_content=content,
        geo=geo,
        include_images=include_images,
        include_articles=include_articles,
        max_articles_per_trend=max_articles_per_trend
    )

    # Store in cache
    if cache:
        get_rss_cache().set(cache_key, trends)

    # Format and return using shared helper
    return _format_output(trends, output_format, include_images, include_articles)


def download_google_trends_rss_batch(
    geos: List[str],
    include_images: bool = True,
    include_articles: bool = True,
    max_articles_per_trend: int = 5,
    show_progress: bool = True,
    delay: float = 0.0
) -> Dict[str, List[Dict]]:
    """
    Download RSS trends for multiple countries/regions with progress tracking.

    **Use this for batch operations** instead of looping manually.
    Shows a progress bar and returns results as a dictionary.

    Args:
        geos: List of geo codes (e.g., ['US', 'GB', 'CA', 'AU'])
        include_images: Include image URLs and sources
        include_articles: Include news articles data
        max_articles_per_trend: Max news articles per trend (default: 5)
        show_progress: Show tqdm progress bar (default: True)
        delay: Optional delay between requests in seconds (default: 0)
               Use 0.5-1.0 if you're fetching many countries to avoid rate limits

    Returns:
        Dict mapping geo code to list of trends: {'US': [...], 'GB': [...]}

    Raises:
        InvalidParameterError: If any geo code is invalid
        DownloadError: If any RSS fetch fails

    Examples:
        >>> # Fetch 5 countries with progress bar
        >>> results = download_google_trends_rss_batch(['US', 'GB', 'CA', 'AU', 'DE'])
        Fetching trends: 100%|██████████| 5/5 [00:01<00:00, 4.2 geo/s]
        >>> print(f"US has {len(results['US'])} trends")

        >>> # Fetch all countries (with small delay to be safe)
        >>> from trendspyg.config import COUNTRIES
        >>> results = download_google_trends_rss_batch(
        ...     list(COUNTRIES.keys()),
        ...     delay=0.5  # 0.5s between requests
        ... )
        Fetching trends: 100%|██████████| 125/125 [01:05<00:00, 1.9 geo/s]

    Warning:
        Fetching many countries (>50) without delay may trigger Google rate limits.
        If you get blocked, wait a few minutes and add delay=0.5 or delay=1.0.

    Note:
        For maximum speed with many countries, use the async version:
        `download_google_trends_rss_batch_async()` which fetches in parallel.
    """
    try:
        from tqdm import tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False
        if show_progress:
            import sys
            print("Note: Install tqdm for progress bar: pip install trendspyg[cli]",
                  file=sys.stderr)

    results: Dict[str, List[Dict]] = {}

    # Create iterator with optional progress bar
    iterator = geos
    if show_progress and has_tqdm:
        iterator = tqdm(geos, desc="Fetching trends", unit="geo")

    for geo in iterator:
        trends = download_google_trends_rss(
            geo=geo,
            output_format='dict',
            include_images=include_images,
            include_articles=include_articles,
            max_articles_per_trend=max_articles_per_trend
        )
        results[geo] = cast(List[Dict], trends)

        # Optional delay between requests
        if delay > 0:
            import time
            time.sleep(delay)

    return results


async def download_google_trends_rss_batch_async(
    geos: List[str],
    include_images: bool = True,
    include_articles: bool = True,
    max_articles_per_trend: int = 5,
    show_progress: bool = True,
    max_concurrent: int = 10
) -> Dict[str, List[Dict]]:
    """
    Download RSS trends for multiple countries/regions in parallel with progress.

    **Fastest way to fetch multiple countries** - uses async/parallel requests.
    Shows a progress bar and returns results as a dictionary.

    Args:
        geos: List of geo codes (e.g., ['US', 'GB', 'CA', 'AU'])
        include_images: Include image URLs and sources
        include_articles: Include news articles data
        max_articles_per_trend: Max news articles per trend (default: 5)
        show_progress: Show tqdm progress bar (default: True)
        max_concurrent: Maximum concurrent requests (default: 10)
                       Lower this if you get rate limited (try 5 or 3)

    Returns:
        Dict mapping geo code to list of trends: {'US': [...], 'GB': [...]}

    Raises:
        InvalidParameterError: If any geo code is invalid
        DownloadError: If any RSS fetch fails
        ImportError: If aiohttp is not installed

    Examples:
        >>> # Fetch 5 countries in parallel (~0.3s total)
        >>> import asyncio
        >>> results = asyncio.run(
        ...     download_google_trends_rss_batch_async(['US', 'GB', 'CA', 'AU', 'DE'])
        ... )
        Fetching trends: 100%|██████████| 5/5 [00:00<00:00, 15.2 geo/s]

        >>> # Fetch ALL 125 countries in parallel (~2-5 seconds)
        >>> from trendspyg.config import COUNTRIES
        >>> results = asyncio.run(
        ...     download_google_trends_rss_batch_async(
        ...         list(COUNTRIES.keys()),
        ...         max_concurrent=10  # Limit concurrent requests
        ...     )
        ... )
        Fetching trends: 100%|██████████| 125/125 [00:03<00:00, 38.5 geo/s]

    Performance:
        - 5 countries: ~0.3 seconds (vs ~1s sync)
        - 125 countries: ~3-5 seconds (vs ~25s sync)
        - Uses connection pooling for efficiency

    Warning:
        High concurrency (>20) may trigger Google rate limits.
        If you get errors, reduce max_concurrent to 5 or 3.

    Note:
        Requires aiohttp: pip install trendspyg[async]
    """
    try:
        import aiohttp
        import asyncio
    except ImportError:
        raise ImportError(
            "aiohttp is required for async batch operations.\n"
            "Install with: pip install trendspyg[async]"
        )

    try:
        from tqdm.asyncio import tqdm as atqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False
        if show_progress:
            import sys
            print("Note: Install tqdm for progress bar: pip install trendspyg[cli]",
                  file=sys.stderr)

    results: Dict[str, List[Dict]] = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(session: 'aiohttp.ClientSession', geo: str) -> tuple:
        async with semaphore:
            trends = await download_google_trends_rss_async(
                geo=geo,
                output_format='dict',
                include_images=include_images,
                include_articles=include_articles,
                max_articles_per_trend=max_articles_per_trend,
                session=session
            )
            return geo, trends

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_one(session, geo) for geo in geos]

        if show_progress and has_tqdm:
            # Use tqdm async progress bar
            async for result in atqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc="Fetching trends",
                unit="geo"
            ):
                geo, trends = await result
                results[geo] = trends
        else:
            # Without progress bar
            for coro in asyncio.as_completed(tasks):
                geo, trends = await coro
                results[geo] = trends

    return results
