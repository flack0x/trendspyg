# trendspyg - Development Roadmap

**Current Version:** v1.5.0
**Status:** Stable — actively developed

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

## v1.5.0 - Google Properties + Hardened Collector + Docs Site

**Released:** 2026-08-11

Built from a competitive-gap research pass (the industry compares tools on five
data types; the official Google Trends API remains application-gated alpha).

### Shipped
- [x] **`gprop=` on all three Explore functions** (CLI `--gprop`, both MCP
  interest tools) — YouTube/News/Images/Shopping search interest, the pytrends
  `gprop` use case. Live-verified; envelopes record the property
  (schema constants 1.0 → 1.1, additive).
- [x] **Related-queries collector hardened** — pinned to the QUERY-kind widget
  request instead of page request order.
- [x] **Documentation site** — https://flack0x.github.io/trendspyg/
  (mkdocs-material; site pages include the canonical repo markdown, no drift).
- [x] `trendspyg/explore` package split (internal); `examples/` under the CI
  lint gate.

### Investigated, not shipped (recorded honestly)
- **Related Topics** (the fifth data type): Google currently serves the ENTITY
  widget empty to automated sessions — the Explore page itself shows "doesn't
  have enough data" while related queries load fine (4/4 sessions, headless
  and visible). Shipping a parser that returns nothing would be noise; the
  hardened collector is the groundwork if Google's serving changes.

---

## v1.4.0 - Explore Archiving + Long-TTL Disk Cache

**Released:** 2026-08-11

The deferred half of 1.3.0's archive story, built after its own design pass
(the Explore envelope shapes and staleness semantics differ from Trending-Now;
1.3.0-wheel tolerance of the new cache table was spike-verified first).

### Shipped
- [x] **Explore disk cache (opt-in)** — `cache="disk"` / `--cache disk` on all
  three Explore functions serves identical recent requests from the local DB:
  no 10-40s browser run, no rate-limit exposure. Smart freshness defaults
  (1h for `"now *"` timeframes, 24h otherwise), per-call `cache_ttl=` override,
  original `fetched_at` preserved on hits. Separate `explore_cache` table so
  the RSS cache's minutes-scale pruning can't purge day-scale entries.
- [x] **Explore archiving (opt-in)** — `archive=True` / `--archive` records
  full Explore/Comparison envelopes (`source` `"explore"`/`"explore_comparison"`)
  with every keyword indexed for `get_keyword_history` / `history -k`.
- [x] **MCP tools answer repeats instantly** — `get_interest_over_time` +
  `compare_interest_over_time` use the disk cache (survives server restarts);
  `get_trending_history` filters to rss/csv so research queries stay out of
  "what was trending". Still 8 tools; public API stays 46 names.

Honest limits: a cache hit can be up to 1h/24h old by design (override with
`cache_ttl`); archiving remains opt-in everywhere; ~4-26 KB per Explore
snapshot depending on timeframe and widgets.

---

## v1.3.0 - Historical Archiving + Disk Cache

**Released:** 2026-08-05

The last big planned 1.x feature — deferred from 1.0 scoping, built after its
own design pass (SQLite storage spike-verified for concurrent processes on
Windows before any code).

### Shipped
- [x] **Historical archiving (opt-in)** — `archive=True` / `--archive` records
  any RSS/CSV fetch as a normalized snapshot in ONE local SQLite file (stdlib,
  zero new deps, no server). Google offers "what was trending on date X"
  nowhere — the archive turns the ephemeral feed into a dataset you own.
- [x] **Query surface:** `read_archive`, `get_keyword_history` ("when did X
  first trend?"), `get_archive_stats`, `prune_archive` + `ArchiveError` +
  `KeywordHistoryPoint` (public API 40 → 46 names); CLI `trendspyg history`
  (--timeline/--stats/--prune-before); **8th MCP tool `get_trending_history`**
  (instant, compact, no network).
- [x] **Disk-backed RSS cache (opt-in)** — `cache="disk"` / `--cache disk`
  persists the response cache across processes; repeated CLI/MCP calls within
  the TTL skip the network entirely. Same TTL knob as the memory cache.

Honest limits: history exists only from the moment archiving is enabled (no
retroactive data); archive writes warn-not-raise by design; ~15 KB/snapshot
(~130-260 MB/year at hourly cadence) — pruning is explicit. Explore-path
archiving deferred (different envelope + staleness semantics).

---

## v1.2.0 - MCP SDK v2 Support

**Released:** 2026-08-05

### Shipped
- [x] **MCP server runs on the MCP SDK v2 stable line** (released 2026-07-28) as
  well as v1: `build_server()` tries the v2 API and falls back to v1, and the
  `[mcp]` extra pin widened from `mcp>=1.27,<2` to `mcp>=1.27,<3`. Fresh
  installs resolve v2; environments held on 1.x by other packages keep working.
  Internal only — the seven tools, their names and behavior are unchanged.

---

## v1.1.0 - Multi-Keyword Comparison

**Released:** 2026-07-10

### Shipped
- [x] **`download_google_trends_comparison(keywords, ...)`** — 2-5 keywords on one
  shared 0-100 scale (the pytrends `kw_list` use case): keyword-keyed values,
  Google's averages, combined interest-by-region with the winning keyword per
  region. Mechanism verified by live spikes before building.
- [x] CLI: repeatable `-k` on `trendspyg explore` (2-5 → comparison mode).
- [x] MCP: seventh tool `compare_interest_over_time` (fail-fast profile).

Honest limits: max 5 terms (Google's cap), no commas in terms (URL separator),
same rate-limit-sensitive Explore path (~10-90s — not for polling).

---

## v1.0.0 - Stable Release

**Released:** 2026-07-09

The stability declaration: no behavior changes, the implicit made explicit.

### Shipped
- [x] **API stability guarantee** — [STABILITY.md](STABILITY.md) defines the covered
  surface (every exported name, exception types, CLI commands/flags, MCP tools, the
  versioned data schemas), the semver rules, and the deprecation policy. Enforced by
  an API-lock test that pins `trendspyg.__all__` exactly.
- [x] **Full test coverage (>90%)** — exceeded before release: 98% aggregate, every
  module ≥89%, CI-gated (aggregate 95%, per-module 80%).
- [x] **Performance benchmarks** — runnable `benchmarks/` suite (offline library
  overhead + opt-in live end-to-end); measured numbers recorded per release in
  [benchmarks/README.md](benchmarks/README.md).
- [x] Exceptions importable from the package root; development status → Production/Stable.

### Scoping decisions (recorded honestly)
- **Data visualization helpers — CUT.** The `dataframe` output feeds
  pandas/matplotlib directly; a plotting module would lock a wide new surface into
  the 1.0 contract for little gain.
- **Historical data archiving — DEFERRED to a 1.x feature release** (pairs with the
  deferred disk-backed cache; deserves its own design pass, not a rider on a
  declaration release).

---

## Post-1.0 candidates (unordered)

- (none queued right now — the 1.0-era list is fully shipped as of 1.4.0;
  proposals welcome via GitHub issues)

---

## v0.9.0 - Explore Tuning & Coverage

**Released:** 2026-07-09

### Shipped
- [x] **User-configurable retry/backoff on the Explore path** — `max_retries` / `retry_wait`
  on both Explore functions; worst-case runtime ≈ `max_retries × (retry_wait + ~2s)`;
  defaults unchanged (non-breaking).
- [x] explore.py raised to 100% test coverage — every module now 89%+, aggregate 98%.
  CI gates tightened: per-module floor 80%, aggregate floor 95%.

---

## v0.8.0 - MCP Server

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
- [x] Fully user-configurable retry/backoff on the Explore path — shipped in 0.9.0
- [x] Per-module coverage floor in CI — shipped in 0.8.0
- [x] MCP server — shipped in 0.8.0
- [ ] Multi-keyword Explore comparison; disk-backed cache

---

## Success Metrics

### Quality
- Test coverage: 98% aggregate, CI-gated (95% aggregate / 80% per module)
- Documentation: Complete API reference + written stability contract
- Performance: measured per release in [benchmarks/](benchmarks/README.md)
  (network-dominated; the library's own overhead is sub-millisecond)

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
