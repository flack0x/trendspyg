# trendspyg API Reference

Complete API documentation for trendspyg v0.7.0.

---

## Table of Contents

- [RSS Functions](#rss-functions)
  - [download_google_trends_rss](#download_google_trends_rss)
  - [download_google_trends_rss_async](#download_google_trends_rss_async)
  - [download_google_trends_rss_batch](#download_google_trends_rss_batch)
  - [download_google_trends_rss_batch_async](#download_google_trends_rss_batch_async)
- [CSV Functions](#csv-functions)
  - [download_google_trends_csv](#download_google_trends_csv)
- [Explore Functions](#explore-functions)
  - [download_google_trends_interest_over_time](#download_google_trends_interest_over_time)
  - [download_google_trends_explore](#download_google_trends_explore)
- [Normalized Output](#normalized-output)
- [Cache Functions](#cache-functions)
  - [clear_rss_cache](#clear_rss_cache)
  - [get_rss_cache_stats](#get_rss_cache_stats)
  - [set_rss_cache_ttl](#set_rss_cache_ttl)
- [Exceptions](#exceptions)
- [Configuration](#configuration)
- [Type Aliases](#type-aliases)

---

## RSS Functions

### download_google_trends_rss

Fast RSS feed download with rich media content.

```python
def download_google_trends_rss(
    geo: str = 'US',
    output_format: Literal['dict', 'dataframe', 'json', 'csv'] = 'dict',
    include_images: bool = True,
    include_articles: bool = True,
    max_articles_per_trend: int = 5,
    cache: bool = True,
    normalize: bool = False
) -> Union[List[Dict], str, pd.DataFrame, Dict]
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `geo` | `str` | `'US'` | Country code (e.g., 'US', 'GB') or US state (e.g., 'US-CA') |
| `output_format` | `str` | `'dict'` | Output format: 'dict', 'dataframe', 'json', 'csv' |
| `include_images` | `bool` | `True` | Include image URLs and sources |
| `include_articles` | `bool` | `True` | Include news articles data |
| `max_articles_per_trend` | `int` | `5` | Maximum news articles per trend |
| `cache` | `bool` | `True` | Use cached results if available |
| `normalize` | `bool` | `False` | Return a unified `NormalizedEnvelope` (see [Normalized Output](#normalized-output)); `output_format` is ignored |

**Returns:**

- `List[Dict]` when `output_format='dict'`
- `pd.DataFrame` when `output_format='dataframe'`
- `str` (JSON) when `output_format='json'`
- `str` (CSV) when `output_format='csv'`

**Raises:**

- `InvalidParameterError` - Invalid geo code or output format
- `DownloadError` - Network or parsing error
- `RateLimitError` - Rate limit exceeded (HTTP 429/403)

**Example:**

```python
from trendspyg import download_google_trends_rss

# Basic usage
trends = download_google_trends_rss(geo='US')

# Get as DataFrame
df = download_google_trends_rss(geo='GB', output_format='dataframe')

# Minimal data (faster)
trends = download_google_trends_rss(
    geo='US',
    include_images=False,
    include_articles=False
)

# Bypass cache for fresh data
trends = download_google_trends_rss(geo='US', cache=False)
```

**Return Data Structure (dict format):**

```python
{
    'trend': 'bitcoin',              # Trend keyword
    'traffic': '500K+',              # Search volume tier (human-readable)
    'traffic_min': 500000,           # Parsed lower bound as int (always present)
    'published': datetime(...),       # Publication timestamp
    'explore_link': 'https://...',   # Google Trends explore URL
    'image': {                        # Only if include_images=True
        'url': 'https://...',
        'source': 'CNN'
    },
    'news_articles': [                # Only if include_articles=True
        {
            'headline': 'Bitcoin surges...',
            'url': 'https://...',
            'source': 'Reuters',
            'image': 'https://...'
        }
    ]
}
```

---

### download_google_trends_rss_async

Async version for parallel fetching. 50-100x faster for batch operations.

```python
async def download_google_trends_rss_async(
    geo: str = 'US',
    output_format: Literal['dict', 'dataframe', 'json', 'csv'] = 'dict',
    include_images: bool = True,
    include_articles: bool = True,
    max_articles_per_trend: int = 5,
    session: Optional[aiohttp.ClientSession] = None,
    cache: bool = True,
    normalize: bool = False
) -> Union[List[Dict], str, pd.DataFrame, Dict]
```

**Additional Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session` | `aiohttp.ClientSession` | `None` | Shared session for connection pooling |

**Requires:** `pip install trendspyg[async]`

**Example:**

```python
import asyncio
from trendspyg import download_google_trends_rss_async

# Single country
async def main():
    trends = await download_google_trends_rss_async(geo='US')
    print(f"Got {len(trends)} trends")

asyncio.run(main())

# Multiple countries in parallel
async def fetch_all():
    countries = ['US', 'GB', 'CA', 'AU', 'DE']
    tasks = [download_google_trends_rss_async(geo=c) for c in countries]
    results = await asyncio.gather(*tasks)
    return dict(zip(countries, results))

all_trends = asyncio.run(fetch_all())
```

---

### download_google_trends_rss_batch

Synchronous batch fetching with progress bar.

```python
def download_google_trends_rss_batch(
    geos: List[str],
    include_images: bool = True,
    include_articles: bool = True,
    max_articles_per_trend: int = 5,
    show_progress: bool = True,
    delay: float = 0.0,
    normalize: bool = False
) -> Dict[str, Union[List[Dict], Dict]]
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `geos` | `List[str]` | required | List of geo codes to fetch |
| `show_progress` | `bool` | `True` | Show tqdm progress bar |
| `delay` | `float` | `0.0` | Delay between requests (seconds) |
| `normalize` | `bool` | `False` | Each geo maps to a `NormalizedEnvelope` instead of a trend list |

**Returns:** `Dict[str, List[Dict]]` - Dictionary mapping geo codes to trends (or geo to `NormalizedEnvelope` when `normalize=True`)

**Example:**

```python
from trendspyg import download_google_trends_rss_batch

# Fetch multiple countries with progress bar
results = download_google_trends_rss_batch(
    ['US', 'GB', 'CA', 'AU'],
    delay=0.5  # Be nice to Google
)
# Output: Fetching trends: 100%|██████████| 4/4

for country, trends in results.items():
    print(f"{country}: {len(trends)} trends")
```

---

### download_google_trends_rss_batch_async

Async batch fetching - fastest option for multiple countries.

```python
async def download_google_trends_rss_batch_async(
    geos: List[str],
    include_images: bool = True,
    include_articles: bool = True,
    max_articles_per_trend: int = 5,
    show_progress: bool = True,
    max_concurrent: int = 10,
    normalize: bool = False
) -> Dict[str, Union[List[Dict], Dict]]
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `geos` | `List[str]` | required | List of geo codes to fetch |
| `show_progress` | `bool` | `True` | Show tqdm progress bar |
| `max_concurrent` | `int` | `10` | Maximum concurrent requests |
| `normalize` | `bool` | `False` | Each geo maps to a `NormalizedEnvelope` instead of a trend list |

**Example:**

```python
import asyncio
from trendspyg import download_google_trends_rss_batch_async

async def main():
    results = await download_google_trends_rss_batch_async(
        ['US', 'GB', 'CA', 'AU', 'DE', 'FR', 'JP'],
        max_concurrent=5  # Limit to avoid rate limits
    )
    return results

all_trends = asyncio.run(main())
```

---

## CSV Functions

### download_google_trends_csv

Full-featured CSV download with filtering (requires Chrome).

```python
def download_google_trends_csv(
    geo: str = 'US',
    hours: int = 24,
    category: str = 'all',
    active_only: bool = False,
    sort_by: str = 'relevance',
    headless: bool = True,
    download_dir: Optional[str] = None,
    output_format: Literal['csv', 'json', 'parquet', 'dataframe', 'dict'] = 'csv',
    normalize: bool = False
) -> Union[str, pd.DataFrame, List[Dict], Dict, None]
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `geo` | `str` | `'US'` | Country or US state code |
| `hours` | `int` | `24` | Time period: 4, 24, 48, or 168 (7 days) |
| `category` | `str` | `'all'` | Category filter (see Configuration) |
| `active_only` | `bool` | `False` | Only show active/rising trends |
| `sort_by` | `str` | `'relevance'` | Sort: 'relevance', 'title', 'volume', 'recency' |
| `headless` | `bool` | `True` | Run Chrome in headless mode |
| `download_dir` | `str` | `None` | Download directory (default: ./downloads/) |
| `output_format` | `str` | `'csv'` | Output: 'csv', 'json', 'parquet', 'dataframe', 'dict' |
| `normalize` | `bool` | `False` | Return a unified `NormalizedEnvelope` (see [Normalized Output](#normalized-output)); `output_format` is ignored |

**Returns:**

- `str` - File path when `output_format` is 'csv', 'json', or 'parquet'
- `pd.DataFrame` when `output_format='dataframe'`
- `List[Dict]` when `output_format='dict'`
- `Dict` (`NormalizedEnvelope`) when `normalize=True`

**Requires:** Chrome browser installed

**Example:**

```python
from trendspyg import download_google_trends_csv

# Basic usage
csv_path = download_google_trends_csv(geo='US')

# With filters
df = download_google_trends_csv(
    geo='US-CA',
    hours=168,  # 7 days
    category='sports',
    active_only=True,
    output_format='dataframe'
)
```

---

## Explore Functions

Keyword analysis over time — interest over time, related queries, and interest by region.
This is the data the archived `pytrends` was most used for. **New in 0.6.0.**

> These functions drive a real (headless) Chrome browser against Google's Explore page.
> Google defends the Explore endpoints aggressively, so expect **~10–90s per call with
> retries**, and a `RateLimitError` when Google persistently throttles. Use them for
> analysis, **not** high-frequency polling — use the RSS path for fast real-time checks.
> Requires Chrome (installed via the same setup as the CSV path).

### download_google_trends_interest_over_time

```python
download_google_trends_interest_over_time(
    keyword: str,
    geo: str = 'US',
    timeframe: str = 'today 12-m',
    category: int = 0,
    headless: bool = True,
    output_format: str = 'dict',
) -> Union[List[Dict], str, pd.DataFrame]
```

Google's 0-100 relative-interest time series for a single search term.

**Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `keyword` | `str` | *(required)* | Search term to analyze (e.g. `"bitcoin"`). |
| `geo` | `str` | `'US'` | Country/region code (`'US'`, `'GB'`, `'US-CA'`). |
| `timeframe` | `str` | `'today 12-m'` | Date range. Common: `'today 12-m'` (weekly), `'today 5-y'`, `'today 3-m'`, `'now 7-d'` (hourly), `'now 1-H'`, `'all'`, or custom `'2024-01-01 2024-12-31'`. |
| `category` | `int` | `0` | Google Trends category id (`0` = all). |
| `headless` | `bool` | `True` | Run Chrome headless. |
| `output_format` | `str` | `'dict'` | `'dict'`, `'dataframe'`, `'json'`, or `'csv'`. |

**Returns** (dict format): a list of points, oldest first:

```python
[
    {"date": "2025-06-01T00:00:00+00:00", "value": 27, "is_partial": False},
    ...
    {"date": "2026-05-31T00:00:00+00:00", "value": 35, "is_partial": True},
]
```

`value` is Google's 0-100 relative-interest index; `is_partial` flags the still-in-progress
final period. Every value is JSON-safe (no `datetime` objects).

**Example**

```python
from trendspyg import download_google_trends_interest_over_time

series = download_google_trends_interest_over_time("bitcoin", geo="US", timeframe="today 5-y")
peak = max(series, key=lambda p: p["value"])
print(peak["date"], peak["value"])
```

### download_google_trends_explore

```python
download_google_trends_explore(
    keyword: str,
    geo: str = 'US',
    timeframe: str = 'today 12-m',
    category: int = 0,
    headless: bool = True,
    include_related: bool = True,
    include_geo: bool = True,
) -> Dict[str, Any]   # ExploreEnvelope
```

The full Explore picture for a keyword in a single browser load.

**Returns** an `ExploreEnvelope`:

```python
{
    "schema_version": "1.0",
    "source": "explore",
    "keyword": "bitcoin",
    "geo": "US",
    "timeframe": "today 12-m",
    "fetched_at": "2026-06-06T...+00:00",
    "count": 53,                       # number of interest_over_time points
    "interest_over_time": [ {"date", "value", "is_partial"}, ... ],
    "related_queries": {
        "top":    [ {"query", "value", "formatted_value", "link"}, ... ],
        "rising": [ {"query", "value", "formatted_value", "link"}, ... ],  # formatted_value e.g. "+3,650%", "Breakout"
    },
    "interest_by_region": [ {"geo_code", "geo_name", "value"}, ... ],   # sorted strongest first
}
```

`related_queries` / `interest_by_region` are empty lists when not requested
(`include_related=False` / `include_geo=False`) or when Google did not return them — the
`interest_over_time` series is the guaranteed payload. The envelope is JSON-safe throughout,
so no `normalize` pass is needed.

**Example**

```python
from trendspyg import download_google_trends_explore

env = download_google_trends_explore("taylor swift", geo="US")
for q in env["related_queries"]["rising"][:5]:
    print(q["query"], q["formatted_value"])
```

---

## Normalized Output

Pass `normalize=True` to `download_google_trends_rss`, `download_google_trends_rss_async`,
or `download_google_trends_csv` to receive a **`NormalizedEnvelope`** — one JSON-native
schema identical across both data paths, so a consumer (or AI agent) learns one shape.
`output_format` is ignored when `normalize=True`.

```python
from trendspyg import download_google_trends_rss

env = download_google_trends_rss(geo='US', normalize=True)
```

**Envelope structure:**

```python
{
    'schema_version': '1.0',
    'source': 'rss',                          # or 'csv'
    'geo': 'US',
    'fetched_at': '2026-05-22T01:00:00+00:00',
    'count': 10,
    'trends': [ ... ]                          # list of NormalizedTrend
}
```

**`NormalizedTrend` — every field is always present and JSON-safe:**

| Field | Type | Description |
|-------|------|-------------|
| `keyword` | `str` | Search term, verbatim from the source |
| `rank` | `int` | 1-based position in source ordering |
| `volume_text` | `str` | Raw human-readable volume, e.g. `'5M+'` |
| `volume_min` | `int` | Parsed lower bound of `volume_text` |
| `started_at` | `str \| None` | ISO 8601 start time |
| `ended_at` | `str \| None` | ISO 8601 end time (`None` if still active) |
| `is_active` | `bool` | `True` when `ended_at` is `None` |
| `related_queries` | `list[str]` | Related searches (CSV path); `[]` for RSS |
| `news` | `list` | News articles (RSS path); `[]` for CSV |
| `image` | `obj \| None` | Trend image |
| `explore_url` | `str` | Google Trends Explore URL |

TypedDicts are importable: `from trendspyg import NormalizedEnvelope, NormalizedTrend`.

---

## Cache Functions

### clear_rss_cache

Clear all cached RSS data.

```python
def clear_rss_cache() -> None
```

**Example:**

```python
from trendspyg import clear_rss_cache

clear_rss_cache()  # Clear all cached data
```

---

### get_rss_cache_stats

Get cache statistics.

```python
def get_rss_cache_stats() -> Dict[str, Any]
```

**Returns:**

```python
{
    'hits': 10,          # Cache hits
    'misses': 5,         # Cache misses
    'size': 8,           # Current entries
    'max_size': 256,     # Maximum entries
    'ttl': 300.0,        # TTL in seconds
    'hit_rate': '66.7%'  # Hit rate percentage
}
```

**Example:**

```python
from trendspyg import get_rss_cache_stats

stats = get_rss_cache_stats()
print(f"Cache hit rate: {stats['hit_rate']}")
```

---

### set_rss_cache_ttl

Set cache TTL (Time-To-Live).

```python
def set_rss_cache_ttl(ttl: float) -> None
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `ttl` | `float` | TTL in seconds (0 to disable caching) |

**Example:**

```python
from trendspyg import set_rss_cache_ttl

set_rss_cache_ttl(600)  # 10 minutes
set_rss_cache_ttl(0)    # Disable caching
set_rss_cache_ttl(300)  # Reset to default (5 min)
```

---

## Exceptions

All exceptions inherit from `TrendspygException`.

```python
from trendspyg.exceptions import (
    TrendspygException,      # Base exception
    InvalidParameterError,   # Invalid input parameters
    DownloadError,           # Network/download failures
    RateLimitError,          # Rate limit exceeded (429/403)
    BrowserError,            # Browser automation failures
    ParseError,              # Data parsing failures
)
```

**Example:**

```python
from trendspyg import download_google_trends_rss
from trendspyg.exceptions import InvalidParameterError, RateLimitError

try:
    trends = download_google_trends_rss(geo='INVALID')
except InvalidParameterError as e:
    print(f"Invalid parameter: {e}")
except RateLimitError as e:
    print(f"Rate limited: {e}")
```

---

## Configuration

### Countries (125 total)

```python
from trendspyg.config import COUNTRIES

# Example: {'US': 'United States', 'GB': 'United Kingdom', ...}
print(list(COUNTRIES.keys())[:10])
# ['US', 'GB', 'CA', 'AU', 'IN', 'DE', 'FR', 'BR', 'MX', 'JP']
```

### US States (51 total)

```python
from trendspyg.config import US_STATES

# Example: {'US-CA': 'California', 'US-NY': 'New York', ...}
print(list(US_STATES.keys())[:5])
# ['US-AL', 'US-AK', 'US-AZ', 'US-AR', 'US-CA']
```

### Categories (20 total)

```python
from trendspyg.config import CATEGORIES

# Available categories:
# 'all', 'sports', 'entertainment', 'business', 'politics',
# 'technology', 'health', 'science', 'games', 'shopping',
# 'food', 'travel', 'beauty', 'hobbies', 'climate',
# 'jobs', 'law', 'pets', 'autos', 'other'
```

### Time Periods

| Hours | Description |
|-------|-------------|
| `4` | Past 4 hours |
| `24` | Past 24 hours (default) |
| `48` | Past 48 hours |
| `168` | Past 7 days |

---

## Monitoring

Real-time monitoring built on the RSS path (new in 0.7.0). The diff core is pure
and JSON-safe (no network, no browser).

### watch_google_trends_rss

```python
watch_google_trends_rss(
    geo="US", interval=60, iterations=None, *,
    on_change=None, min_volume=None, events=None, keywords=None,
    webhook=None, **rss_kwargs
) -> Iterator[TrendChange]
```

Polls `download_google_trends_rss(geo, cache=False)` every `interval` seconds and
yields each change between consecutive snapshots. The first poll is the baseline
(yields nothing). `iterations=None` runs until the caller stops iterating; otherwise
it stops after N polls. Filters: `min_volume`, `events`, `keywords` (see
`filter_changes`). `webhook` POSTs each change as JSON (fire-and-forget). RSS-only —
safe for continuous polling.

### diff_trends / filter_changes / post_webhook

```python
diff_trends(old, new) -> list[TrendChange]       # pure, no network
filter_changes(changes, *, min_volume=None, events=None, keywords=None) -> list[TrendChange]
post_webhook(url, change, timeout=10.0) -> bool  # 2xx -> True; never raises
```

`TrendChange` = `{event, keyword, rank, prev_rank, volume_min, prev_volume_min}`,
`event ∈ {new, dropped, volume_up, volume_down, rank_change}`. `rank`/`volume_min`
are `None` for a `dropped` trend; `prev_*` are `None` for a `new` one.

### CLI

```bash
trendspyg watch --geo US --interval 60 --events new,volume_up --min-volume 50000
```

Streams one NDJSON change per line (stdout stays pipe-clean).

---

## Type Aliases

```python
from typing import Literal

# CSV path (download_google_trends_csv)
OutputFormat = Literal['csv', 'json', 'parquet', 'dataframe', 'dict']

# RSS path (download_google_trends_rss / _async / _batch) accepts the same
# names minus 'parquet' — i.e. 'dict', 'dataframe', 'json', 'csv'.

SortOption = Literal['relevance', 'title', 'volume', 'recency']  # CSV sort_by
```

---

## Performance Tips

### 1. Use Caching

```python
# Results cached for 5 minutes by default
trends = download_google_trends_rss(geo='US')  # Network call
trends = download_google_trends_rss(geo='US')  # Instant (cached)
```

### 2. Use Async for Multiple Countries

```python
# Sequential: ~5 seconds for 10 countries
# Parallel: ~0.5 seconds for 10 countries
results = await download_google_trends_rss_batch_async(countries)
```

### 3. Minimize Data When Possible

```python
# Faster if you don't need images/articles
trends = download_google_trends_rss(
    geo='US',
    include_images=False,
    include_articles=False
)
```

### 4. Use Shared Sessions

```python
import aiohttp

async with aiohttp.ClientSession() as session:
    tasks = [
        download_google_trends_rss_async(geo=c, session=session)
        for c in countries
    ]
    results = await asyncio.gather(*tasks)
```

---

## Version

```python
from trendspyg import __version__
print(__version__)  # '0.7.0'
```
