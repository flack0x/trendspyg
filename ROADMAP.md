# trendspyg - Development Roadmap

**Current Version:** v0.8.0
**Status:** Active Development

---

## Project Vision

Build a free, open-source Python library for accessing Google Trends data - a modern alternative to the archived pytrends library.

---

## v0.6.0 - Explore: Keyword Analysis Over Time

**Status:** Released - June 2026

### Features
- **Explore path** - the data pytrends was most used for, re-added (dropped in 0.2.0):
  - `download_google_trends_interest_over_time()` - Google's 0-100 relative-interest time series
  - `download_google_trends_explore()` - full picture in one load: interest over time +
    related queries (top + rising) + interest by region
  - `trendspyg explore` CLI command
  - Typed shapes: `InterestPoint`, `RelatedQuery`, `RegionInterest`, `ExploreEnvelope`
- Robust mechanism: drives headless Chrome with stealth flags, retries past Google's
  transient soft-throttle, reads the widget data the page itself fetched. More durable than
  the raw reverse-engineered endpoints that break pytrends/trendspy.
- Honest limitation: the Explore endpoints are rate-limit sensitive (~10–90s per call, may
  retry); for analysis, not high-frequency polling.

---

## v0.5.x - Normalized Output

**Status:** Released - May 2026

### Features
- `normalize=True` on every RSS/CSV entry point - one JSON-native `NormalizedEnvelope`
  schema, identical across paths (agent-friendly).
- Stderr-routed CSV progress, `dict` output format, agent metadata + doc-link fixes.

---

## v0.4.0 - Async, Caching & Enhanced Errors

**Status:** Released - January 2026

### Features
- **Async Support** - `download_google_trends_rss_async()` for parallel fetching
  - 50-100x faster for batch operations
  - Non-blocking for web applications
  - Session reuse for connection pooling
- **Batch Functions** - Progress bar for bulk operations
  - `download_google_trends_rss_batch()` - Sync with tqdm
  - `download_google_trends_rss_batch_async()` - Async with tqdm
- **Built-in Caching** - TTL cache for RSS results
  - 5-minute default TTL (configurable)
  - Cache control: `clear_rss_cache()`, `get_rss_cache_stats()`, `set_rss_cache_ttl()`
  - ~60,000x speedup on cache hits
- **Enhanced Error Messages** - Better error context
  - HTTP status code detection (rate limits, server errors)
  - Actionable suggestions in error messages

---

## v0.3.0 - CLI and Enhanced Features

**Status:** Released - December 2025

### Features
- **Command-Line Interface** - Full terminal access
  - `trendspyg rss` - Fast RSS downloads
  - `trendspyg csv` - Comprehensive CSV downloads
  - `trendspyg list` - List available options
  - `trendspyg info` - Package information
- Verified all 125 countries return actual data
- Verified all 4 time periods work correctly

---

## v0.2.0 - RSS Feed Support

**Status:** Released - November 2025

### Features
- **RSS Feed** - Fast, rich media data access
  - 50x faster than CSV (0.2s vs 10s)
  - News articles with headlines and URLs
  - Trend images with attribution
  - 4 output formats: dict, dataframe, json, csv

---

## v0.1.x - Foundation

**Status:** Released - November 2025

### Features
- Core CSV downloader with browser automation
- 125 countries + 51 US states
- 20 categories, 4 time periods
- Multiple output formats (CSV, JSON, Parquet, DataFrame)
- Full type hints (PEP 484)
- Input validation with helpful errors
- Retry logic with exponential backoff

---

## v0.8.0 - MCP Server (Latest release)

**Released:** 2026-07-09

### Shipped
- [x] **MCP server** (`trendspyg-mcp`, `pip install trendspyg[mcp]`, Python 3.10+) — six
  read-only tools for Claude and any MCP client: trending now, multi-geo compare,
  change detection since last call, supported options, interest over time, full CSV export.
  Built on the stable MCP v1 SDK line (`mcp>=1.27,<2`).
- [x] Per-module coverage floor in CI (75%) via `scripts/check_coverage_floor.py`
- [x] cli.py and rss_downloader.py raised to 100% test coverage; aggregate 86% → 95%,
  aggregate CI gate 80% → 90%

---

## v0.7.0 - Monitoring & Reliability

**Released:** 2026-07-07

### Shipped
- [x] Real-time monitoring mode (RSS-only)
  - Continuous polling with change detection (`watch_google_trends_rss`, `diff_trends`)
  - Fire-and-forget webhook support
  - Threshold / event / watchlist filters; CLI `trendspyg watch` streaming NDJSON
- [x] CSV path retry wiring + configurable `timeout` / `max_retries`
- [x] Explore hardening: rate-limit vs DOM-change errors split; offline engine tests (coverage 47% → 78%)

### Deferred to a later release
- [ ] Fully user-configurable retry/backoff on the Explore path
- [x] Per-module coverage floor in CI — shipped in 0.8.0
- [x] MCP server — shipped in 0.8.0
- [ ] Multi-keyword Explore comparison; disk-backed cache

---

## v1.0.0 - Stable Release (Future)

**Target:** 2026

### Goals
- [ ] API stability guarantee
- [ ] Full test coverage (>90%)
- [ ] Performance benchmarks
- [ ] Data visualization helpers
- [ ] Historical data archiving

---

## Success Metrics

### Quality
- Test coverage: Target 90%+
- Documentation: Complete API reference
- Performance: RSS <0.5s, CSV <15s
- Stability: <1% error rate

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Links

- **GitHub:** https://github.com/flack0x/trendspyg
- **PyPI:** https://pypi.org/project/trendspyg/
- **Documentation:** https://github.com/flack0x/trendspyg#readme

---

**Last Updated:** July 2026
