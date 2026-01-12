# trendspyg

[![PyPI version](https://img.shields.io/pypi/v/trendspyg.svg)](https://pypi.org/project/trendspyg/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/flack0x/trendspyg/actions/workflows/tests.yml/badge.svg)](https://github.com/flack0x/trendspyg/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python library for downloading real-time Google Trends data. A modern alternative to the archived pytrends.

## Installation

```bash
pip install trendspyg

# With async support
pip install trendspyg[async]

# With CLI
pip install trendspyg[cli]

# All features
pip install trendspyg[all]
```

## Quick Start

### RSS Feed (Fast - 0.2s)

```python
from trendspyg import download_google_trends_rss

# Get current trends with news articles
trends = download_google_trends_rss(geo='US')

for trend in trends[:3]:
    print(f"{trend['trend']} - {trend['traffic']}")
    if trend['news_articles']:
        print(f"  {trend['news_articles'][0]['headline']}")
```

### CSV Export (Comprehensive - 10s)

```python
from trendspyg import download_google_trends_csv

# Get 480+ trends with filtering (requires Chrome)
df = download_google_trends_csv(
    geo='US',
    hours=168,            # Past 7 days
    category='sports',
    output_format='dataframe'
)
```

### Async (Parallel Fetching)

```python
import asyncio
from trendspyg import download_google_trends_rss_batch_async

async def main():
    results = await download_google_trends_rss_batch_async(
        ['US', 'GB', 'CA', 'DE', 'JP'],
        max_concurrent=5
    )
    for country, trends in results.items():
        print(f"{country}: {len(trends)} trends")

asyncio.run(main())
```

### CLI

```bash
trendspyg rss --geo US
trendspyg csv --geo US-CA --category sports --hours 168
trendspyg list --type countries
```

## Data Sources

| Feature | RSS | CSV |
|---------|-----|-----|
| Speed | 0.2s | ~10s |
| Trends | ~20 | 480+ |
| News articles | Yes | No |
| Time filtering | No | Yes (4h/24h/48h/7d) |
| Category filter | No | Yes (20 categories) |
| Requires Chrome | No | Yes |

## Features

- **125 countries** + 51 US states
- **20 categories** (sports, tech, health, etc.)
- **4 time periods** (4h, 24h, 48h, 7 days)
- **4 output formats** (dict, DataFrame, JSON, CSV)
- **Async support** for parallel fetching
- **Built-in caching** (5-min TTL)
- **CLI** for terminal access

## Caching

```python
from trendspyg import clear_rss_cache, get_rss_cache_stats

# Results are cached for 5 minutes by default
trends = download_google_trends_rss(geo='US')  # Network call
trends = download_google_trends_rss(geo='US')  # From cache

# Bypass cache
trends = download_google_trends_rss(geo='US', cache=False)

# Check cache stats
print(get_rss_cache_stats())

# Clear cache
clear_rss_cache()
```

## Documentation

- [API Reference](docs/API.md)
- [CLI Documentation](CLI.md)
- [Changelog](CHANGELOG.md)
- [Examples](examples/)

## Requirements

- Python 3.8+
- Chrome browser (for CSV export only)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- [GitHub](https://github.com/flack0x/trendspyg)
- [PyPI](https://pypi.org/project/trendspyg/)
- [Issues](https://github.com/flack0x/trendspyg/issues)
