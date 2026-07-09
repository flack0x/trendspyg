# trendspyg CLI Documentation

Command-line interface for downloading Google Trends data.

## Installation

```bash
# Install with CLI support
pip install trendspyg[cli]

# Or install all features
pip install trendspyg[cli,analysis]
```

## Quick Start

```bash
# Show help
trendspyg --help

# Show package info
trendspyg info

# Download US trends via RSS (fast)
trendspyg rss --geo US

# Download US trends via CSV (comprehensive)
trendspyg csv --geo US
```

## Commands

### `trendspyg rss` - Fast RSS Download

Download trends via RSS feed (0.2s, rich media, ~10-20 trends)

**Options:**
- `--geo TEXT` - Country/region code (default: US)
- `--output [dict|dataframe|json|csv]` - Output format (default: dict)
- `--no-images` - Exclude images
- `--no-articles` - Exclude news articles
- `--max-articles INTEGER` - Max articles per trend (default: 5)

**Examples:**
```bash
# Basic usage
trendspyg rss --geo US

# Get UK trends as JSON
trendspyg rss --geo GB --output json

# Get Japan trends without media
trendspyg rss --geo JP --no-images --no-articles

# California trends with 3 articles max
trendspyg rss --geo US-CA --max-articles 3
```

### `trendspyg csv` - Comprehensive CSV Download

Download trends via CSV export (10s, filtered, ~480+ trends)

**Options:**
- `--geo TEXT` - Country/region code (default: US)
- `--hours [4|24|48|168]` - Time period (default: 24)
- `--category TEXT` - Category filter (default: all)
- `--output [csv|json|dataframe|parquet]` - Output format (default: csv)
- `--active-only` - Show only active/rising trends
- `--sort [relevance|title|volume|recency]` - Sort order (default: relevance)
- `--output-dir PATH` - Output directory (default: ./downloads)
- `--timeout INTEGER` - Page-load timeout in seconds (default: 10) *(new in 0.9.0)*
- `--max-retries INTEGER` - Scrape attempts on transient failure (default: 3) *(new in 0.9.0)*

**Examples:**
```bash
# Basic usage
trendspyg csv --geo US

# California, past 7 days, sports only
trendspyg csv --geo US-CA --hours 168 --category sports

# Active trends only, as DataFrame
trendspyg csv --geo GB --active-only --output dataframe

# Germany, health trends, past 48h
trendspyg csv --geo DE --hours 48 --category health
```

### `trendspyg explore` - Keyword Analysis Over Time

Analyze a keyword's interest over time, related queries, and interest by region.
**New in 0.6.0.** Drives a real browser against Google's Explore page — it is rate-limit
sensitive (~10–90s, may retry). Use it for analysis, not high-frequency polling.

**Options:**
- `-k, --keyword TEXT` - Search term to analyze (required)
- `--geo TEXT` - Country/region code (default: US)
- `--timeframe TEXT` - Date range, e.g. `'today 12-m'`, `'today 5-y'`, `'now 7-d'`, `'all'` (default: today 12-m)
- `--category INTEGER` - Google Trends category id, 0 = all (default: 0)
- `--output [dict|json|csv|dataframe]` - Output format for the interest-over-time series (default: json)
- `--full` - Output the full Explore envelope (interest + related queries + regions) as JSON
- `--visible` - Run the browser in visible (non-headless) mode
- `-q, --quiet` - Suppress banners; print only the data (pipe-safe)
- `--max-retries INTEGER` - Chart-load attempts past Google's soft-throttle (default: 10) *(new in 0.9.0)*
- `--retry-wait FLOAT` - Seconds to watch the chart per attempt; worst case ≈ max-retries × (retry-wait + 2s) (default: 8.0) *(new in 0.9.0)*

**Examples:**
```bash
# Interest over time as JSON
trendspyg explore --keyword bitcoin

# Past 5 years, as CSV
trendspyg explore -k "taylor swift" --timeframe "today 5-y" --output csv

# Full envelope (interest + related + regions), pipe-clean for jq
trendspyg explore -k bitcoin --full --quiet | jq '.related_queries.rising[0]'
```

### `trendspyg watch` - Real-Time Monitoring

Poll the RSS feed and stream each change between snapshots as NDJSON (one JSON
object per line). **New in 0.7.0.** Built on the fast RSS path, so it is safe for
continuous polling (unlike `csv`/`explore`). stdout carries only NDJSON.

**Options:**
- `--geo TEXT` - Country/region code (default: US)
- `--interval INTEGER` - Seconds between polls (default: 60)
- `--iterations INTEGER` - Number of polls before stopping (default: run until Ctrl-C)
- `--min-volume INTEGER` - Only report changes at/above this `traffic_min`
- `--events TEXT` - Comma-separated events: `new,dropped,volume_up,volume_down,rank_change`
- `-k, --keyword TEXT` - Watchlist term (repeatable); case-insensitive substring match
- `--webhook TEXT` - POST each change as JSON to this URL (fire-and-forget)
- `-q, --quiet` - Suppress the startup banner; stream only NDJSON

**Examples:**
```bash
# Watch US trends, print every change
trendspyg watch --geo US --interval 60

# Only new or surging trends above a volume floor
trendspyg watch --geo US --events new,volume_up --min-volume 50000

# Watch a keyword list and POST changes to a webhook
trendspyg watch -k bitcoin -k ethereum --webhook https://example.com/hook

# Five polls, pipe-clean for jq
trendspyg watch --geo US --iterations 5 --quiet | jq .
```

### `trendspyg list` - List Available Options

Show available countries, states, categories, or time periods.

**Options:**
- `--type [countries|states|categories|hours]` - Type of list (required)

**Examples:**
```bash
# List all countries
trendspyg list --type countries

# List US states
trendspyg list --type states

# List categories
trendspyg list --type categories

# List time periods
trendspyg list --type hours
```

### `trendspyg info` - Package Information

Show package version, statistics, and capabilities.

**Example:**
```bash
trendspyg info
```

## Common Use Cases

### Real-time Monitoring
```bash
# Quick check - what's trending now
trendspyg rss --geo US --no-images --no-articles
```

### Research Data Collection
```bash
# Download comprehensive dataset
trendspyg csv --geo US --hours 168 --output dataframe
```

### Category-Specific Trends
```bash
# Sports trends in California
trendspyg csv --geo US-CA --category sports --hours 24

# Technology trends in India
trendspyg csv --geo IN --category technology --hours 48
```

### Multiple Countries
```bash
# US trends
trendspyg csv --geo US --output json > us_trends.json

# UK trends
trendspyg csv --geo GB --output json > gb_trends.json

# Japan trends
trendspyg csv --geo JP --output json > jp_trends.json
```

### Active/Rising Trends Only
```bash
# Show only currently rising trends
trendspyg csv --geo US --active-only
```

## Output Formats

### RSS Formats
- **dict** (default) - Python dictionaries, displayed in terminal
- **dataframe** - pandas DataFrame preview
- **json** - JSON output to stdout
- **csv** - CSV output to stdout

### CSV Formats
- **csv** (default) - CSV file saved to downloads/
- **json** - JSON file saved to downloads/
- **parquet** - Parquet file saved to downloads/
- **dataframe** - DataFrame preview in terminal

## Tips

1. **Fast Checks**: Use `rss` for quick trend checks
2. **Research**: Use `csv` for comprehensive datasets
3. **JSON Output**: Pipe to files for later processing
   ```bash
   trendspyg rss --geo US --output json > trends.json
   ```
4. **Automation**: Use in shell scripts or cron jobs
5. **Help**: Use `--help` on any command for details
   ```bash
   trendspyg rss --help
   trendspyg csv --help
   ```

## Supported Options

- **125 countries** - See `trendspyg list --type countries`
- **51 US states** - See `trendspyg list --type states`
- **20 categories** - See `trendspyg list --type categories`
- **4 time periods** - See `trendspyg list --type hours`

## Troubleshooting

**"click is required for CLI functionality"**
```bash
pip install trendspyg[cli]
```

**"pandas is required for 'dataframe' format"**
```bash
pip install trendspyg[analysis]
```

**CSV download requires Chrome browser**
- Install from: https://www.google.com/chrome/

## See Also

- [README.md](README.md) - Full documentation
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [GitHub Issues](https://github.com/flack0x/trendspyg/issues) - Bug reports
