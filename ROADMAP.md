# trendspyg - Development Roadmap

**Current Version:** v0.4.0
**Status:** Active Development

---

## Project Vision

Build a free, open-source Python library for accessing Google Trends data - a modern alternative to the archived pytrends library.

---

## v0.4.0 - Async, Caching & Enhanced Errors (Current Release)

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
- 188,000+ configuration options
- 125 countries + 51 US states
- 20 categories, 4 time periods
- Multiple output formats (CSV, JSON, Parquet, DataFrame)
- Full type hints (PEP 484)
- Input validation with helpful errors
- Retry logic with exponential backoff

---

## v0.5.0 - Monitoring & Reliability (Next)

**Target:** Q1 2026

### Planned Features
- [ ] Real-time monitoring mode
  - Continuous polling with change detection
  - Webhook/callback support
  - Alert thresholds
- [ ] Enhanced retry configuration
  - User-configurable retry attempts
  - Custom backoff strategies

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

**Last Updated:** January 2026
