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

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Union, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from .config import COUNTRIES, US_STATES, DEFAULT_GEO
from .exceptions import InvalidParameterError, DownloadError

# Type aliases
OutputFormat = Literal['csv', 'json', 'dataframe', 'dict']


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
    max_articles_per_trend: int = 5
) -> Union[List[Dict], str, 'pd.DataFrame']:
    """
    Download Google Trends RSS feed data with rich media content.

    **Fast alternative to CSV download** (0.2s vs 10s):
    - Returns ~10-20 current trending topics
    - Includes images, news articles, headlines
    - No time filtering (always current trends)
    - Perfect for real-time monitoring and qualitative research

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

    Performance:
        - Speed: ~0.2 seconds (50x faster than CSV)
        - Trends: ~10-20 items
        - Data size: ~50-100KB
        - Update frequency: ~9 times per hour

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

    # Build RSS URL
    url = f"https://trends.google.com/trending/rss?geo={geo}"

    try:
        # Fetch RSS feed
        response = requests.get(url, timeout=10)
        response.raise_for_status()

    except requests.RequestException as e:
        raise DownloadError(
            f"Failed to fetch RSS feed: {e}\n\n"
            "Possible causes:\n"
            "- No internet connection\n"
            "- Google Trends is down\n"
            "- Network firewall blocking access\n\n"
            f"URL attempted: {url}"
        )

    # Parse XML
    try:
        root = ET.fromstring(response.content)
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
        published = None
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

    # Return in requested format
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
        fieldnames = ['trend', 'traffic', 'published', 'explore_link']
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
