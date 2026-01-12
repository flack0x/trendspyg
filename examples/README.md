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

# Caching control
from trendspyg import clear_rss_cache, get_rss_cache_stats
clear_rss_cache()
stats = get_rss_cache_stats()
```
