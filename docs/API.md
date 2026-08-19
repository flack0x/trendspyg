# trendspyg API Reference

Complete API documentation for trendspyg v1.5.0.

> Everything documented here is covered by the project's
> [API stability policy](STABILITY.md) — semantic versioning with a written
> definition of the public surface and a deprecation policy.

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
  - [download_google_trends_comparison](#download_google_trends_comparison)
- [Normalized Output](#normalized-output)
- [Cache Functions](#cache-functions)
- [Archive Functions](#archive-functions)
  - [clear_rss_cache](#clear_rss_cache)
  - [clear_explore_cookies](#clear_explore_cookies)
  - [get_rss_cache_stats](#get_rss_cache_stats)
  - [set_rss_cache_ttl](#set_rss_cache_ttl)
- [Exceptions](#exceptions)
- [Configuration](#configuration)
- [Monitoring](#monitoring)
- [MCP Server](#mcp-server)
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
    max_retries: int = 10,      # new in 0.9.0
    retry_wait: float = 8.0,    # new in 0.9.0
    cache: bool | str = False,  # new in 1.4.0 — False or 'disk'
    cache_ttl: float = None,    # new in 1.4.0
    archive: bool = False,      # new in 1.4.0
    db_path: str = None,        # new in 1.4.0
    gprop: str = '',            # new in 1.5.0 — '', 'images', 'news', 'youtube', 'froogle'
    cookies: bool | str = False, # new in 1.6.0 — 'disk' = returning-visitor cookie jar
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
| `max_retries` | `int` | `10` | Chart-load attempts (page reloads) past Google's soft-throttle before `RateLimitError`. Must be ≥ 1. *(new in 0.9.0)* |
| `retry_wait` | `float` | `8.0` | Seconds to watch the chart per attempt before reloading. Must be > 0. Worst-case runtime ≈ `max_retries × (retry_wait + ~2s)` — e.g. `max_retries=2, retry_wait=5` gives a ~15s ceiling for fail-fast use. *(new in 0.9.0)* |
| `cache` | `bool \| str` | `False` | `'disk'` serves an identical recent request from the local archive DB — **no browser launch, no rate-limit exposure**. `True` is rejected (the Explore path has no in-memory cache). *(new in 1.4.0)* Since 1.6.0 a cached *bigger* answer (a full explore) also serves a *smaller* question (interest over time only) for the same keyword/geo/timeframe/category/gprop, trimmed to what was asked. |
| `cache_ttl` | `float` | `None` | Max age in seconds a cached result may be served. Default: 1 hour for `'now *'` timeframes (hourly points), 24 hours otherwise. *(new in 1.4.0)* |
| `archive` | `bool` | `False` | Also record this fetch as a full `ExploreEnvelope` snapshot (`source='explore'`) in the local archive. Fresh fetches only — cache hits are not re-recorded; failed writes warn instead of raising. *(new in 1.4.0)* |
| `db_path` | `str` | `None` | Archive/disk-cache file (default: `TRENDSPYG_DB` env var, else the platform data dir). *(new in 1.4.0)* |
| `gprop` | `str` | `''` | Google property to analyze: `''`/`'web'` (web search), `'images'`, `'news'`, `'youtube'` (YouTube search interest), `'froogle'` (Google Shopping). Validated up-front; part of the cache key. *(new in 1.5.0)* |
| `cookies` | `bool \| str` | `False` | `'disk'` reuses Google's session cookies across Explore calls (a small JSON file beside the archive DB, or `TRENDSPYG_COOKIES`), so each browser session is a *returning visitor*. Measured 2026-08-19: after a burst Google refuses new visitors with its hard 429 page while a session carrying the saved jar is served. A refused jar is dropped automatically; `True` is rejected. Opt-in — it keeps a Google cookie on disk. *(new in 1.6.0)* |

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
    max_retries: int = 10,      # new in 0.9.0
    retry_wait: float = 8.0,    # new in 0.9.0
    cache: bool | str = False,  # new in 1.4.0 — False or 'disk'
    cache_ttl: float = None,    # new in 1.4.0
    archive: bool = False,      # new in 1.4.0
    db_path: str = None,        # new in 1.4.0
    gprop: str = '',            # new in 1.5.0
    cookies: bool | str = False, # new in 1.6.0
) -> Dict[str, Any]   # ExploreEnvelope
```

The full Explore picture for a keyword in a single browser load. `max_retries` /
`retry_wait` tune the soft-throttle retry loop, and `cache` / `cache_ttl` /
`archive` / `db_path` behave exactly as in
`download_google_trends_interest_over_time` above — with one addition: a cache
hit returns the envelope with its **original** `fetched_at`, so the data's real
age is never hidden. `include_related` / `include_geo` are part of the cache
key (exact-match; a full fetch is not sliced to serve a slimmer request).

**Returns** an `ExploreEnvelope`:

```python
{
    "schema_version": "1.2",           # 1.1 since 1.5.0 (gprop); 1.2 since 1.6.0 (is_empty)
    "source": "explore",
    "keyword": "bitcoin",
    "geo": "US",
    "timeframe": "today 12-m",
    "gprop": "",                       # Google property ("" = web) — new in 1.5.0
    "fetched_at": "2026-06-06T...+00:00",
    "count": 53,                       # number of interest_over_time points
    "is_empty": False,                 # True when the series has no non-zero point (Google's no-data answer) — new in 1.6.0
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

### download_google_trends_comparison

*New in 1.1.0.*

```python
def download_google_trends_comparison(
    keywords: Sequence[str],        # 2-5 distinct terms, no commas
    geo: str = 'US',
    timeframe: str = 'today 12-m',
    category: int = 0,
    headless: bool = True,
    output_format: str = 'dict',    # 'dict' | 'json' | 'dataframe' | 'csv'
    include_geo: bool = True,
    max_retries: int = 10,
    retry_wait: float = 8.0,
    cache: bool | str = False,      # new in 1.4.0 — False or 'disk'
    cache_ttl: float = None,        # new in 1.4.0
    archive: bool = False,          # new in 1.4.0 — source 'explore_comparison'
    db_path: str = None,            # new in 1.4.0
    gprop: str = '',                # new in 1.5.0
    cookies: bool | str = False,    # new in 1.6.0
) -> Union[Dict[str, Any], str, pd.DataFrame]   # ComparisonEnvelope for dict/json
```

Compare 2-5 keywords on **one shared 0-100 scale** — the pytrends `kw_list`
use case. Google scales each single-keyword series independently, so fetching
terms one at a time does **not** produce comparable numbers; this function
loads Google's own comparison view (one browser load, not N) and returns its
data.

**Returns** (for `dict`/`json`) a `ComparisonEnvelope`:

```python
{
    "schema_version": "1.1",           # 1.1 since 1.5.0 (added gprop)
    "source": "explore_comparison",
    "keywords": ["bitcoin", "ethereum", "solana"],
    "geo": "US",
    "timeframe": "today 12-m",
    "gprop": "",                       # Google property ("" = web) — new in 1.5.0
    "fetched_at": "2026-07-10T...+00:00",
    "count": 53,
    "averages": {"bitcoin": 39, "ethereum": 7, "solana": 5},        # Google's per-keyword averages
    "interest_over_time": [
        {"date": "2025-07-06T00:00:00+00:00",
         "values": {"bitcoin": 38, "ethereum": 6, "solana": 4},     # keyed by keyword
         "is_partial": False},
        ...
    ],
    "interest_by_region": [
        {"geo_code": "US-WY", "geo_name": "Wyoming",
         "values": {"bitcoin": 68, "ethereum": 16, "solana": 16},
         "top_keyword": "bitcoin"},                                  # the winner in this region
        ...
    ],
}
```

`output_format="dataframe"` / `"csv"` render the interest-over-time series as a
pytrends-style table instead: `date, <kw1>, ..., <kwN>, is_partial`.
`include_geo=False` skips the region fetch (faster) — `interest_by_region` is
then `[]`, the field is always present.

**Limits (Google's, stated honestly):** at most 5 terms; terms containing a
comma cannot be compared (the URL uses commas as separators); duplicates
(case-insensitive) are rejected. Same rate-limit-sensitive path as the other
Explore functions (~10-90s — not for polling).

**Example**

```python
from trendspyg import download_google_trends_comparison

env = download_google_trends_comparison(["bitcoin", "ethereum"], geo="US")
print(env["averages"])                            # {'bitcoin': 39, 'ethereum': 7}
best = max(env["averages"], key=env["averages"].get)
print(f"{best} dominates {env['geo']} search interest")
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

### clear_explore_cookies

Delete the Explore session cookie jar written by `cookies="disk"` *(new in 1.6.0)*.

```python
def clear_explore_cookies(path: Optional[str] = None) -> bool
```

`path` defaults to the `TRENDSPYG_COOKIES` env var, else `explore_cookies.json`
beside the archive DB. Returns `True` if a file was removed.

```python
from trendspyg import clear_explore_cookies

clear_explore_cookies()  # start the next Explore session as a new visitor
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

The TTL also governs the **disk cache** (`cache="disk"`, below).

---

## Archive Functions

*New in 1.3.0; Explore support in 1.4.0.* Google's trending feed is ephemeral —
nothing anywhere tells you "what was trending on date X". Opt in to archiving
and every fetch records a snapshot to **one local SQLite file** (Python stdlib —
no server, no keys, no new dependencies). The same file also holds the
persistent caches: the RSS cache (`cache="disk"`, RSS TTL knob) and, since
1.4.0, the Explore cache (hours-scale freshness, own table).

**Recording** (opt-in kwargs on the download functions):

```python
from trendspyg import download_google_trends_rss, download_google_trends_csv
from trendspyg import download_google_trends_interest_over_time

download_google_trends_rss(geo="US", archive=True)     # archive this fetch
download_google_trends_rss(geo="US", cache="disk")     # persistent cache
download_google_trends_csv(geo="US", archive=True)     # CSV path archives too

# Explore path (1.4.0): all three functions — interest_over_time, explore,
# comparison. The disk cache matters most here: a hit skips a 10-40s
# rate-limited browser run entirely.
download_google_trends_interest_over_time("bitcoin", cache="disk", archive=True)
```

Only fresh fetches are archived (cache hits are not re-recorded), and an
archive/cache **write failure never breaks the download** — it emits a
`RuntimeWarning` and the fetch returns normally. Explore snapshots store the
full envelope with `source` `"explore"` / `"explore_comparison"`; each keyword
is indexed for the query functions below (with `rank`/`volume_min` `None` —
research queries have no trending rank).

Default location: `%LOCALAPPDATA%\trendspyg\trendspyg.db` (Windows),
`~/Library/Application Support/trendspyg/` (macOS), `$XDG_DATA_HOME` or
`~/.local/share/trendspyg/` (Linux). Override per call with `db_path=` or
globally with the `TRENDSPYG_DB` env var. Safe for concurrent processes
(WAL mode; e.g. `trendspyg watch` and CLI calls writing at once).

### `read_archive()`

```python
read_archive(
    geo=None, source=None,          # source: "rss"/"csv"/"explore"/"explore_comparison",
    start=None, end=None,           #   or a sequence like ("rss", "csv") (1.4.0)
    keyword=None,                   # only snapshots containing it (case-insensitive)
    limit=None,                     # newest N
    output_format="dict",           # "dict" | "json" | "dataframe"
    db_path=None,
)
```

Returns archived envelopes **newest first** (`dict` = list of
`NormalizedEnvelope`; `dataframe` = one row per trend, needs `[analysis]`).
A fresh/nonexistent archive reads as empty. Raises `ArchiveError` if the file
is unreadable, `InvalidParameterError` on bad arguments.

### `get_keyword_history()`

```python
get_keyword_history("bitcoin", geo=None, start=None, end=None,
                    source=None,    # single value or sequence (new in 1.4.0)
                    db_path=None)
# -> [{"fetched_at", "geo", "source", "rank", "volume_min"}, ...]  oldest first
```

Every archived appearance of a keyword, answered from an indexed table (no
envelope loading) — "when did X first trend, and how did it move?" The return
shape is the `KeywordHistoryPoint` TypedDict. Explore-path appearances (1.4.0)
show up with `rank`/`volume_min` `None`; pass `source=("rss", "csv")` to keep
the timeline strictly "it trended", or `source="explore"` for "I researched it".

### `get_archive_stats()`

```python
get_archive_stats(db_path=None)
# -> {"db_path", "db_size_bytes", "snapshot_count", "trend_row_count",
#     "geos", "sources", "first_fetched_at", "last_fetched_at",
#     "cache_entries", "explore_cache_entries"}   # explore_cache_entries: 1.4.0
```

### `prune_archive()`

```python
prune_archive("2026-01-01", geo=None, source=None, db_path=None)  # -> deleted count
```

Deletes snapshots fetched **strictly before** the cutoff (datetime or ISO
string; `geo`/`source` narrow it). Nothing in the archive expires on its own —
deletion is always explicit. Sizing: ~15 KB per RSS snapshot (roughly
130-260 MB/year at hourly cadence); ~4-26 KB per Explore snapshot depending on
timeframe and widgets. (Explore *cache* entries are separate and do expire: an
opportunistic 30-day garbage collection reclaims abandoned keys.)

CLI equivalent: `trendspyg history` (see [CLI.md](CLI.md)) — snapshots,
`--timeline -k <kw>`, `--stats`, `--prune-before`.

---

## Exceptions

All exceptions inherit from `TrendspygException`. Since v1.0.0 they are
importable straight from the package root (`trendspyg.exceptions` also remains
valid — both paths are the same classes):

```python
from trendspyg import (
    TrendspygException,      # Base exception
    InvalidParameterError,   # Invalid input parameters
    DownloadError,           # Network/download failures
    RateLimitError,          # Rate limit exceeded (429/403)
    BrowserError,            # Browser automation failures
    ParseError,              # Data parsing failures
    ArchiveError,            # Local archive unreadable (1.3.0; writes warn, never raise)
)
```

**Example:**

```python
from trendspyg import download_google_trends_rss
from trendspyg import InvalidParameterError, RateLimitError

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

## MCP Server

*New in 0.8.0.* Expose trendspyg to Claude and any MCP-compatible client as native
tools — no Python needed on the agent side. Requires Python 3.10+ (the core library
still supports 3.8+); runs on the MCP SDK v2 stable line or v1 (`mcp>=1.27,<3` —
the server detects which is installed).

```bash
pip install trendspyg[mcp]
trendspyg-mcp                                # stdio transport
claude mcp add trendspyg -- trendspyg-mcp    # register in Claude Code
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "trendspyg": { "command": "trendspyg-mcp" }
  }
}
```

| Tool | Speed | Browser | Returns |
|------|-------|---------|---------|
| `get_trending_now(geo)` | ~0.2–2s | No | `NormalizedEnvelope` (~10–20 trends + news) |
| `compare_trending(geos, compact=False)` | ~0.2–2s/geo | No | `{geo: NormalizedEnvelope}`, 1–20 geos; `compact=true` keeps keyword/rank/volume_min/is_active per trend only (~16× smaller) *(1.6.0)* |
| `get_trend_changes(geo)` | ~0.2–2s | No | new/dropped/volume/rank changes since last call |
| `list_supported_options()` | instant | No | geo codes, categories, hours, timeframes |
| `get_interest_over_time(keyword, geo, timeframe, gprop)` | ~10–40s fresh; instant on cached repeats *(1.4.0)* | **Yes** | `[{date, value, is_partial}]` — `gprop` selects web/YouTube/News/Images/Shopping *(1.5.0)* |
| `compare_interest_over_time(keywords, geo, timeframe, gprop)` | ~10–40s fresh; instant on cached repeats *(1.4.0)* | **Yes** | `ComparisonEnvelope` — 2–5 keywords, one shared scale *(new in 1.1.0)* |
| `get_trending_full(geo, hours, category)` | ~10–15s | **Yes** | `NormalizedEnvelope` (480+ trends) |
| `get_trending_history(geo, keyword, start, end, limit)` | instant | No | compact archived snapshots + keyword timeline *(new in 1.3.0; local archive only)* |

All tools are read-only. The browser-backed tools carry explicit latency and
rate-limit warnings in their descriptions so agents prefer the fast RSS tools.
Since 1.4.0 the two interest tools use the Explore disk cache: an identical
repeat question within the freshness window (1h for `"now *"` timeframes, 24h
otherwise) answers instantly, and the cache survives server restarts.
`get_trend_changes` keeps its baseline per geo in server memory — restarting the
server resets it. `get_trending_history` reads only what was archived on this
machine (`archive=True` / `--archive`), and only Trending-Now sources (rss/csv) —
archived Explore research queries never appear as "was trending". An empty
result means nothing was recorded for those filters, not that nothing trended.

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
print(__version__)  # '1.5.0'
```
