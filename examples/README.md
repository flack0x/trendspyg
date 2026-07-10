# trendspyg Examples

This directory contains example scripts demonstrating various features of trendspyg.

## Examples

### Basic Usage
- **`basic_rss_usage.py`** - Simple RSS feed download
- **`csv_with_filtering.py`** - CSV download with filters
- **`multiple_output_formats.py`** - Using different output formats

### Advanced Features (v0.4.0+)
- **`async_parallel_fetching.py`** - Fetch multiple countries in parallel (50-100x faster)
- **`batch_with_progress.py`** - Batch downloads with progress bar
- **`caching_example.py`** - Built-in caching for repeated requests
- **`normalized_output.py`** - Unified agent-friendly schema with `normalize=True` (v0.5.0+)
- **`interest_over_time.py`** - Keyword analysis: interest over time, related queries, regions (v0.6.0+)
- **`compare_keywords.py`** - Compare 2-5 keywords on one shared 0-100 scale (v1.1.0+)
- **`monitoring.py`** - Real-time monitoring: stream trend changes as they happen (v0.7.0+)

### Real-World Use Cases
- **`journalist_workflow.py`** - Real-world journalism use case
- **`data_analysis.py`** - Data science analysis with pandas

## Running Examples

```bash
# Install trendspyg with all features
pip install trendspyg[cli,analysis,async]

# Run any example
python examples/basic_rss_usage.py
python examples/async_parallel_fetching.py
python examples/caching_example.py
```

## Requirements

| Example | Requirements |
|---------|--------------|
| Basic RSS | `trendspyg` |
| Async/Batch | `trendspyg[async]` (aiohttp) |
| DataFrame | `trendspyg[analysis]` (pandas) |
| CSV Export | Chrome browser |
| Explore / interest over time | Chrome browser |
| Monitoring (`watch`) | `trendspyg` (RSS-only, poll-safe) |

## Quick Reference

```python
# Basic usage
from trendspyg import download_google_trends_rss
trends = download_google_trends_rss(geo='US')

# Async (parallel)
from trendspyg import download_google_trends_rss_async
trends = await download_google_trends_rss_async(geo='US')

# Batch with progress bar
from trendspyg import download_google_trends_rss_batch
results = download_google_trends_rss_batch(['US', 'GB', 'CA'])

# Normalized output - one unified, JSON-safe schema (great for agents)
env = download_google_trends_rss(geo='US', normalize=True)

# Interest over time for a keyword (Explore path, requires Chrome)
from trendspyg import download_google_trends_interest_over_time
series = download_google_trends_interest_over_time('bitcoin', geo='US', timeframe='today 12-m')

# Real-time monitoring - stream changes between RSS snapshots (v0.7.0+)
from trendspyg import watch_google_trends_rss
for change in watch_google_trends_rss(geo='US', interval=60):
    print(change['event'], change['keyword'])

# Caching control
from trendspyg import clear_rss_cache, get_rss_cache_stats
clear_rss_cache()
stats = get_rss_cache_stats()
```
