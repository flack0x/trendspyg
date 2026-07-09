# trendspyg

[![PyPI version](https://img.shields.io/pypi/v/trendspyg.svg)](https://pypi.org/project/trendspyg/)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/trendspyg?period=total&units=none&left_color=black&right_color=green&left_text=downloads)](https://pepy.tech/projects/trendspyg)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/flack0x/trendspyg/actions/workflows/tests.yml/badge.svg)](https://github.com/flack0x/trendspyg/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python library for Google Trends data — real-time trending topics **and** keyword analysis over time (interest over time, related queries, interest by region). A modern, actively-maintained alternative to the archived pytrends.

> **Using this library from a coding agent?** See [AGENTS.md](https://github.com/flack0x/trendspyg/blob/main/AGENTS.md) for a concise, agent-ready reference.

## Installation

```bash
pip install trendspyg

# With async support
pip install trendspyg[async]

# With CLI
pip install trendspyg[cli]

# With the MCP server (use trendspyg from Claude & other AI agents; Python 3.10+)
pip install trendspyg[mcp]

# All features
pip install trendspyg[all]
```

## Quick Start

### RSS Feed (Fast, no browser)

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

### Explore — interest over time (the pytrends use case)

```python
from trendspyg import download_google_trends_interest_over_time

# Google's 0-100 relative-interest time series for a keyword (requires Chrome)
series = download_google_trends_interest_over_time("bitcoin", geo="US", timeframe="today 12-m")
for point in series[-3:]:
    print(point["date"], point["value"])   # {'date': '2026-05-31T00:00:00+00:00', 'value': 57, 'is_partial': True}
```

```python
from trendspyg import download_google_trends_explore

# Full picture in one call: interest over time + related queries + interest by region
env = download_google_trends_explore("bitcoin", geo="US")
print(env["interest_over_time"][-1])
print(env["related_queries"]["rising"][0])     # {'query': '...', 'formatted_value': 'Breakout', ...}
print(env["interest_by_region"][0])            # {'geo_code': 'US-..', 'geo_name': '..', 'value': 100}
```

> The Explore path drives a real browser against Google's Explore page and is **rate-limit
> sensitive** (~10–90s per call, with retries). Use it for analysis, not high-frequency
> polling — use the RSS path for fast, frequent real-time checks.

### Watch — real-time monitoring (new in 0.7.0)

```python
from trendspyg import watch_google_trends_rss

# Stream changes between RSS snapshots (safe for continuous polling — RSS only)
for change in watch_google_trends_rss(geo="US", interval=60, events=["new", "volume_up"]):
    print(change["event"], change["keyword"], change["volume_min"])
    # {'event': 'new', 'keyword': '...', 'rank': 3, 'prev_rank': None, 'volume_min': 50000, ...}
```

> Monitoring is built on the fast RSS path, so it is safe to poll continuously (the CSV and
> Explore paths are not). The pure `diff_trends(old, new)` helper is also exported if you
> manage snapshots yourself.

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
trendspyg explore --keyword bitcoin --output csv
trendspyg watch --geo US --interval 60 --events new,volume_up
trendspyg list --type countries
```

### MCP server — use trendspyg from Claude & AI agents (new in 0.8.0)

Give any MCP client (Claude Desktop, Claude Code, Cursor, ...) live Google Trends
tools — free, local, no API key. Requires Python 3.10+.

```bash
pip install trendspyg[mcp]

# Claude Code — one command:
claude mcp add trendspyg -- trendspyg-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "trendspyg": { "command": "trendspyg-mcp" }
  }
}
```

Six tools: `get_trending_now`, `compare_trending`, `get_trend_changes` (what changed
since the last check), `list_supported_options` — all fast and browser-free — plus
`get_interest_over_time` and `get_trending_full` (drive Chrome; slower, described
honestly to the agent).

## Data Sources

| | RSS | CSV | Explore |
|---|-----|-----|---------|
| Answers | "what's trending now?" | "what's trending now?" | "how is interest in *X* moving?" |
| Speed | sub-second\* | ~10s | ~10–90s (rate-limit sensitive) |
| Output | 10–20 current trends | 480+ current trends | interest over time, related queries, regions |
| News articles | Yes | No | No |
| Time filtering | No | Yes (4h/24h/48h/7d) | Yes (any timeframe) |
| Category filter | No | Yes (20 categories) | Yes |
| Requires Chrome | No | Yes | Yes |

\* Network-dominated: ~0.2s on low-latency links, ~1.4s measured on a high-RTT
connection; cache hits are instant. Honest measured numbers per path live in
[benchmarks/](https://github.com/flack0x/trendspyg/tree/main/benchmarks).

> **Monitoring:** `trendspyg watch` / `watch_google_trends_rss(...)` polls the RSS path and streams
> changes (new / dropped / volume / rank) as they happen — built on RSS, so it is safe for
> continuous polling.

## Features

- **Real-time trending** topics (RSS + CSV paths) and **keyword analysis over time** (Explore path)
- **Real-time monitoring** — `watch` streams trend changes as NDJSON (RSS-only, poll-safe)
- **Interest over time, related queries, and interest by region** for any keyword — the core pytrends use case
- **125 countries** + 51 US states, **20 categories**, **4 trending time periods** (4h, 24h, 48h, 7 days)
- **Output formats**: dict, DataFrame, JSON, CSV (+ Parquet on the CSV path)
- **Async support** for parallel fetching
- **Built-in caching** (5-min TTL)
- **Agent-ready**: typed shapes, `normalize=True`, and a JSON-native Explore schema
- **MCP server** — `trendspyg-mcp` exposes 6 tools to Claude and any MCP client (no API key)
- **CLI** for terminal access
- **Stable API** — semantic versioning with a written contract: [STABILITY.md](https://github.com/flack0x/trendspyg/blob/main/STABILITY.md)

## Normalized output (for agents & pipelines)

Pass `normalize=True` to get one **unified, JSON-native schema** that is identical
for both the RSS and CSV paths — no need to learn two different shapes.

```python
from trendspyg import download_google_trends_rss

env = download_google_trends_rss(geo='US', normalize=True)
# {'schema_version': '1.0', 'source': 'rss', 'geo': 'US',
#  'fetched_at': '2026-05-22T...Z', 'count': 10, 'trends': [...]}

for t in env['trends']:
    print(t['rank'], t['keyword'], t['volume_min'])  # volume_min is a real int
```

Every trend has a fixed, JSON-safe shape: `keyword`, `rank`, `volume_text`,
`volume_min` (int), `started_at` / `ended_at` (ISO 8601 or `None`), `is_active`,
`related_queries` (list), `news` (list), `image`, `explore_url`. `normalize=True`
works on every entry point — RSS, CSV, async, and the batch functions (each geo
then maps to its own envelope) — and on the CLI (`trendspyg rss --geo US --normalize`).
It is opt-in — default output is unchanged.

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

- [API Reference](https://github.com/flack0x/trendspyg/blob/main/docs/API.md)
- [CLI Documentation](https://github.com/flack0x/trendspyg/blob/main/CLI.md)
- [Coding-agent quick reference](https://github.com/flack0x/trendspyg/blob/main/AGENTS.md)
- [API stability policy](https://github.com/flack0x/trendspyg/blob/main/STABILITY.md)
- [Benchmarks](https://github.com/flack0x/trendspyg/tree/main/benchmarks)
- [Changelog](https://github.com/flack0x/trendspyg/blob/main/CHANGELOG.md)
- [Examples](https://github.com/flack0x/trendspyg/tree/main/examples)

## Stability

trendspyg is **1.0** — the public API follows [semantic versioning](https://semver.org/spec/v2.0.0.html)
under a written contract: what's covered (every exported name, the exception types,
CLI commands and flags, MCP tools, the versioned data schemas), what a breaking
change is, and how deprecations work. The honest boundary: Google's side of the
wire is not ours to guarantee — upstream changes are fixed in patch releases.
Details in [STABILITY.md](https://github.com/flack0x/trendspyg/blob/main/STABILITY.md).

## Requirements

- Python 3.8+
- Chrome browser (for the CSV and Explore paths; the RSS path needs no browser)

## License

MIT License - see [LICENSE](https://github.com/flack0x/trendspyg/blob/main/LICENSE) for details.

## Links

- [GitHub](https://github.com/flack0x/trendspyg)
- [PyPI](https://pypi.org/project/trendspyg/)
- [Issues](https://github.com/flack0x/trendspyg/issues)
