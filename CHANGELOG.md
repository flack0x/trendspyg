# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **CI: per-module coverage floor (70%).** The aggregate `--cov-fail-under=80` gate could hide
  a single weak module behind a healthy average (explore.py once sat at 47% while the total
  showed 82%). A new `scripts/check_coverage_floor.py` gate now fails CI if any individual
  module drops below 70%. Runnable locally:
  `pytest tests/ --cov=trendspyg --cov-report=json -m "not network" && python scripts/check_coverage_floor.py`

## [0.7.0] - 2026-07-07

Real-time monitoring, plus a reliability and hygiene pass.

### Added
- **Real-time monitoring (RSS-only).** Poll the fast RSS feed and stream the changes between
  consecutive snapshots:
  - `watch_google_trends_rss(geo, interval=60, iterations=None, ...)` — a generator that yields
    `TrendChange` events (`new`, `dropped`, `volume_up`, `volume_down`, `rank_change`), with
    `min_volume` / `events` / `keywords` filters and an optional fire-and-forget `webhook`.
  - `diff_trends(old, new)` — a **pure, JSON-safe** diff of two RSS snapshots → `list[TrendChange]`
    (no network, no browser — fully unit-testable).
  - `filter_changes(...)` and `post_webhook(...)` helpers, a new `TrendChange` TypedDict, and
    `MONITOR_SCHEMA_VERSION`.
  - CLI: **`trendspyg watch`** streams one NDJSON change per line (stdout stays pipe-clean; pipe
    it into `jq`, a file, or a webhook).
  - Built entirely on the durable, browser-free RSS path — safe for continuous polling, unlike
    the CSV/Explore paths.
- **Schema-version constants exported from the package root** — `SCHEMA_VERSION`,
  `EXPLORE_SCHEMA_VERSION`, `MONITOR_SCHEMA_VERSION` — so agents can detect shape drift.
- `download_google_trends_csv` gained `timeout` and `max_retries` parameters.

### Changed
- **CSV path hardening.** Ported the Explore path's anti-detection kit (disable
  `AutomationControlled` / `useAutomationExtension`, hide `navigator.webdriver`), pinned the UI
  language with `&hl=en-US`, capped the page-load hang with a timeout, and **wired the
  previously-dead retry wrapper** so transient scrape failures auto-retry (browser-start
  failures are not retried).
- Bumped the `requests` floor to `>=2.32.0` (cert-verification fix).

### Fixed
- **RSS `output_format` is validated up front**, before any network fetch — an invalid format
  no longer makes a request to Google first.
- **Explore distinguishes a throttle from a changed page.** When the chart never renders and no
  rate-limit message appears, it now raises a clear `BrowserError` ("the Explore UI may have
  changed") instead of a misleading `RateLimitError` telling you to wait and retry.
- Corrected `docs/API.md`: the advertised `sort` values (`traffic`/`started`) do not exist — the
  real values are `volume`/`recency`. Added the missing `dict` output format and the
  always-present `traffic_min` field; removed a non-existent `RSSOutputFormat` symbol.
- Refreshed `SECURITY.md`: supported-versions table now reflects a latest-release policy,
  replaced a broken `safety check -r requirements.txt` instruction with `pip-audit`, and stated
  the RSS XML trust assumption honestly.
- Repaired 5 CSV validation tests that silently skipped forever on a bad import. Fixed stale doc
  counts (`~360+` → `~480+` CSV trends; `114` → `125` countries comment) and a
  `trendspy`→`trendspyg` typo.

### Internal / CI
- CI enforces a **lint + type-check gate** (black, isort, flake8, mypy — pinned so an upstream
  linter release can't break the gate) plus a coverage floor, on every push and pull request.
- CI test matrix covers **Python 3.8–3.13** (added 3.13).
- Added a **PyPI Trusted Publishing** workflow (`publish.yml`, OIDC — no stored token); requires
  a one-time trusted-publisher setup on PyPI to take effect.
- Added **Dependabot** (pip + GitHub Actions) and merged the initial batch of CI action bumps.
- Added offline fake-driver tests for the Explore browser engine (coverage 47% → 78%); the
  package test suite now sits at ~86%.

## [0.6.1] - 2026-06-08

Metadata, packaging, and code-quality hardening only — **no runtime or API changes**.

### Changed
- **Expanded PyPI keywords** for discoverability: added `google-trends-api`,
  `pytrends-alternative`, `interest-over-time`, `related-queries`, `trending`, and
  `web-scraping` (dropped low-value generic terms).

### Internal
- Applied **black + isort** formatting across the codebase and made it **flake8/mypy
  clean** (added `.flake8` config; fixed unused imports, placeholder-less f-strings, and
  type annotations). No behavior change.
- Added **Dependabot** (pip + GitHub Actions) for automated dependency updates.
- Removed a stale, orphaned options-reference doc.

## [0.6.0] - 2026-06-06

### Added
- **Explore path — keyword analysis over time.** Two new functions bring back the data the
  archived `pytrends` was most used for, which trendspyg previously did not offer:
  - `download_google_trends_interest_over_time(keyword, geo='US', timeframe='today 12-m', ...)`
    — Google's 0-100 relative-interest time series for a search term. Returns a list of
    `{date (ISO 8601), value (int), is_partial (bool)}`, oldest first. Supports
    `output_format` `dict`/`json`/`csv`/`dataframe`.
  - `download_google_trends_explore(keyword, ...)` — the full picture in a single browser
    load: `interest_over_time` + `related_queries` (`top` + `rising`) + `interest_by_region`,
    returned as an `ExploreEnvelope`.
  - **CLI:** new `trendspyg explore` command (`-k/--keyword`, `--timeframe`, `--output`,
    `--full`, `--quiet`).
  - **Typed shapes:** `InterestPoint`, `RelatedQuery`, `RegionInterest`, `ExploreEnvelope`
    exported from the package root. The Explore output is JSON-safe by construction (ISO
    dates, int values, plain lists) — no `normalize` pass needed.
- How it works: drives headless Chrome to the Explore page (reusing the existing anti-bot
  setup + new stealth flags), retries past Google's transient "try again in a bit"
  soft-throttle, then reads the widget data the page itself fetched. More durable than the
  raw reverse-engineered endpoints that break pytrends/`trendspy`.

### Notes
- The Explore path is **rate-limit sensitive** by nature (Google defends the Explore
  endpoints far more than the Trending Now feed). Expect ~10-90s per call with retries; a
  clear `RateLimitError` is raised when Google persistently throttles. It is for analysis,
  **not** high-frequency polling — use the RSS path for fast, frequent real-time checks.
- Added the `Programming Language :: Python :: 3.13` classifier (already tested on 3.13).

## [0.5.1] - 2026-05-22

### Added
- **`normalize=True` on the batch RSS functions.** `download_google_trends_rss_batch` and
  `download_google_trends_rss_batch_async` now accept `normalize=True` — each geo maps to its
  own `NormalizedEnvelope` instead of a raw trend list. This completes `normalize` coverage
  across every RSS entry point (0.5.0 covered the single-geo RSS, async, and CSV functions).

## [0.5.0] - 2026-05-22

### Added
- **`normalize=True` — unified, agent-friendly output.** `download_google_trends_rss`,
  `download_google_trends_rss_async`, and `download_google_trends_csv` accept a new opt-in
  `normalize=True` argument. When set, they return a `NormalizedEnvelope` — a single
  JSON-native schema **identical across the RSS and CSV paths**, so a consumer (or AI agent)
  learns one shape instead of two. Also on the CLI: `--normalize` on the `rss` and `csv`
  commands prints the envelope as JSON (pipe-clean — no banner).
  - Envelope: `{schema_version, source, geo, fetched_at, count, trends: [...]}`.
  - Each trend: `keyword`, `rank`, `volume_text`, `volume_min` (int), `started_at`
    (ISO 8601 | null), `ended_at` (ISO 8601 | null), `is_active` (bool), `related_queries`
    (list[str]), `news` (list), `image` (obj | null), `explore_url`.
  - The CSV path's raw quirks are fixed in the normalized output: `Search volume` `"5M+"`
    becomes a real `volume_min` int; the localized `Started` string (with its U+202F narrow
    no-break space) becomes an ISO 8601 timestamp; the comma-joined `Trend breakdown`
    becomes a real `related_queries` list; empty `Ended` (`NaN`) becomes `null`.
  - **Non-breaking** — default output of every function is unchanged; `normalize` is opt-in.
- **`NormalizedTrend` and `NormalizedEnvelope` TypedDicts** — exported from the package root
  for static typing and coding-agent autocomplete.

### Changed
- `_parse_traffic_to_min` moved from `rss_downloader` to `utils` — it is now shared by the
  RSS path and the CSV normalization layer. Still importable from `rss_downloader` for
  backward compatibility.

## [0.4.5] - 2026-05-22

### Fixed
- **CSV path contaminated piped stdout** - `download_google_trends_csv()` printed all
  `[INFO]` / `[OK]` / `[WARN]` progress messages to **stdout**, so `trendspyg csv ... --quiet`
  was not pipe-safe despite the `--quiet` flag (added in 0.4.3 for exactly this purpose).
  All progress output now goes to **stderr**; stdout carries only the requested data payload.
  Found by running the CSV path live — the unit suite missed it because CSV tests are
  network-marked and deselected by default.

### Added
- **`dict` output format for the CSV path** - `download_google_trends_csv(output_format='dict')`
  now returns a list of row dicts, matching the RSS path and the README's stated formats.
  Previously it raised `InvalidParameterError: Unsupported output format: dict` *after* a full
  ~15s browser run. Also exposed on the CLI as `trendspyg csv --output dict`.

### Changed
- `trendspyg info` now reports the CSV path as `~480+ trends` (was `~360+`), matching the
  README and observed live volume.

## [0.4.4] - 2026-05-22

### Fixed
- **Broken documentation links on PyPI** - README doc links were relative (`docs/API.md`,
  `CLI.md`, `AGENTS.md`, `CHANGELOG.md`, `examples/`, `LICENSE`). They resolved on GitHub but
  404'd on the PyPI project page (e.g. `pypi.org/project/trendspyg/docs/API.md`). All converted
  to absolute `github.com/flack0x/trendspyg` URLs so they work everywhere.

### Added
- **Agent header in README** - A one-line pointer under the badges directing coding agents to
  `AGENTS.md`.
- **`Agent Reference` PyPI URL** - Added to `[project.urls]`; surfaces in the PyPI sidebar so
  agents that read package metadata find the agent reference faster.

## [0.4.3] - 2026-04-24

### Added
- **Numeric traffic field** - Every RSS trend now includes `traffic_min: int` alongside the
  human-readable `traffic: str`. Parses `"1000+"` → `1000`, `"50,000+"` → `50000`, `"2.5K+"` → `2500`,
  `"1.5M+"` → `1500000`. Unparseable input safely returns `0` instead of crashing.
  Use `traffic_min` for sorting and filtering without writing a parser yourself.
- **Typed return shapes** - New `trendspyg.types` module exports `Trend`, `NewsArticle`,
  `TrendImage`, `TrendEnvelope` as `TypedDict`s. Runtime values are still plain dicts (no
  behavior change); IDEs and coding agents now get autocomplete and type checking.
  Import from the package root: `from trendspyg import Trend, NewsArticle, ...`.
- **`--envelope` CLI flag** - `trendspyg rss --envelope` wraps output in
  `{fetched_at, geo, count, trends: [...]}`. Opt-in; default output shape is unchanged.
  Useful for pipelines and archives that need the snapshot timestamp alongside the data.
- **`[all]` install extra** - `pip install trendspyg[all]` now works (matches the README).
  Bundles `cli`, `async`, and `analysis` extras.
- **`AGENTS.md`** - Concise one-pager for coding agents (Claude Code, Codex, Gemini CLI)
  so they can produce correct code in one pass without scanning the repo.

### Fixed
- **CLI version drift** - `trendspyg info` showed `0.3.0` and `__init__.py` hardcoded `0.4.0`
  despite the package being `0.4.2`. All three now read from `trendspyg/version.py`.
- **Windows console encoding** - `trendspyg rss` headlines rendered non-ASCII as `�` on
  Windows (e.g. `Noël`, curly quotes). The CLI now forces UTF-8 on stdout/stderr at entry.
- **Pipe-safe CLI output** - Added `--quiet` / `-q` to `rss` and `csv` to suppress human
  banners and the `[OK] Success!` line. `trendspyg rss --output json --quiet | jq .` now works.
- **CSV path failed in headless mode** - Google Trends serves a stripped page to detectably-
  headless Chrome (no Export button in the expected location), causing the default CSV
  download to time out. Added realistic `--window-size=1920,1080` and a Chrome 131 user-agent
  to the headless options. Headed mode (`headless=False`) was unaffected.
- **`traffic_min` column missing from `csv` and `dataframe` outputs** - the new `traffic_min`
  field landed on `dict` and `json` paths but was dropped by `_format_output()` when flattening
  to the tabular formats. Added it to both the DataFrame flatten dict and the CSV
  fieldnames/row dict. Regression test covers all three non-dict formats.

### Internal
- Added `_parse_traffic_to_min()` helper in `rss_downloader.py` (unit-verified, 13 cases).
- Added `_configure_stdout_encoding()` helper in `cli.py`; fails open on older Pythons.

## [0.4.0] - 2026-01-12

### Added
- **Async Support** - New `download_google_trends_rss_async()` function for parallel fetching
  - 50-100x faster for batch operations (fetch 125 countries in ~0.5s vs ~25s)
  - Non-blocking for web applications (FastAPI, Django async views)
  - Optional session reuse for connection pooling
  - Full feature parity with sync version (all output formats supported)
  - Requires `pip install trendspyg[async]` (aiohttp dependency)
- **Batch Functions with Progress Bar** - New batch download functions
  - `download_google_trends_rss_batch()` - Sync batch with tqdm progress bar
  - `download_google_trends_rss_batch_async()` - Async batch with progress bar (fastest)
  - Shows real-time progress: `Fetching trends: 45/125 [=====>    ] 36%`
  - Optional delay parameter to avoid rate limits
  - Configurable max_concurrent for async version
- **Built-in Caching** - Thread-safe TTL cache for RSS results
  - 5-minute default TTL to reduce API calls (configurable)
  - Cache control functions: `clear_rss_cache()`, `get_rss_cache_stats()`, `set_rss_cache_ttl()`
  - `cache=False` parameter to bypass cache and fetch fresh data
  - Max 256 entries with LRU-style eviction
  - Shared between sync and async functions
  - Performance: ~60,000x speedup on cache hits
- **Enhanced Error Messages** - Better error context with actionable suggestions
  - HTTP status code detection (429/403 = rate limit, 404 = not found, 5xx = server error)
  - `RateLimitError` with specific recovery steps
  - Connection and timeout errors with troubleshooting tips
  - Invalid parameter errors suggest similar valid values
- pytest-asyncio for async test support
- Comprehensive async, batch, cache, and error handling test suites

### Changed
- Refactored RSS downloader to use shared parsing and formatting helpers
- Updated all documentation with async examples, batch examples, caching examples, and rate limit warnings
- Updated roadmap to reflect async support and caching completion

### Internal
- Added `TTLCache` class in utils.py for thread-safe caching
- Added `_parse_rss_xml()` helper for shared XML parsing logic
- Added `_format_output()` helper for shared output formatting
- Added `_make_cache_key()` helper for consistent cache key generation
- Added `_handle_http_error()` helper for HTTP status code handling
- Reduced code duplication between sync and async implementations

## [0.3.0] - 2025-12-17

### Added
- **Command-Line Interface (CLI)** - Full-featured terminal interface
  - `trendspyg rss` - Fast RSS downloads from terminal with comprehensive output
  - `trendspyg csv` - Comprehensive CSV downloads from terminal with detailed display
  - `trendspyg list` - List available options (countries, states, categories)
  - `trendspyg info` - Package information and statistics
  - All API features accessible via CLI
  - Requires `pip install trendspyg[cli]`
  - Shows all trends with traffic, news articles, images, and explore links
- CLI documentation (CLI.md) with usage examples and tips

### Changed
- **Verified all 125 countries** return actual trends data (tested both RSS + CSV)
- **Verified all 4 time periods** work correctly (4h: 75 trends, 24h: 364, 48h: 687, 7d: 2,737)
- Updated country count documentation from 114 to 125 across all files
- Enhanced CLI output to show comprehensive trend details instead of summaries
- Updated package description to mention CLI

### Fixed
- Country count in documentation (was 114, now correctly shows 125)

## [0.2.0] - 2025-11-04

### Added
- **RSS Feed Support** - New `download_google_trends_rss()` function for fast, rich media data access
  - 50x faster than CSV (0.2s vs 10s)
  - News articles with headlines, URLs, and sources (3-5 per trend)
  - Trend images with attribution
  - 4 output formats: dict, dataframe, json, csv
  - Perfect for real-time monitoring, journalism, and qualitative research
- Comprehensive documentation comparing RSS vs CSV data sources
- Research use cases and workflow examples for both data sources

### Changed
- **Focused scope** - Removed Explore page functionality to focus exclusively on real-time "Trending Now" data
- Streamlined codebase by removing experimental features
- Updated API surface - now provides TWO core functions: `download_google_trends_csv()` and `download_google_trends_rss()`
- Updated all documentation to reflect dual data source approach
- Cleaner project structure

### Removed
- Explore page historical data functionality (experimental)
- `download_explore_data()` function
- `trendspyg/explorer.py` and `trendspyg/explorer_v2.py` modules
- Playwright optional dependency
- Explore-specific configuration constants (`EXPLORE_TIME_PERIODS`, `SEARCH_TYPES`, `DATA_SECTIONS`)

### Why This Change?
This release refocuses the library on its core strength: **real-time trending data**. The Explore page functionality was experimental and added significant complexity. Users needing historical trends can access Google Trends directly or use specialized tools.

**RSS Addition:** Researchers need both fast monitoring (RSS) and comprehensive datasets (CSV) for different research methodologies. RSS provides qualitative data (news context, visual content) while CSV provides quantitative data (large datasets, statistical analysis). Together they form a complete toolkit.

## [0.1.4] - 2025-11-03

### Added
- **Complete type hints** across entire codebase (PEP 484 compliant)
  - All function signatures fully typed
  - Type aliases for `OutputFormat` and `SortOption`
  - Better IDE support with IntelliSense/autocomplete
- **Multiple output format support**: CSV, JSON, Parquet, DataFrame
  - `output_format='csv'` - Default CSV format (backward compatible)
  - `output_format='json'` - JSON format for APIs and web applications
  - `output_format='parquet'` - Efficient columnar storage (50-80% smaller files)
  - `output_format='dataframe'` - Direct pandas DataFrame (no file I/O)
- **Mypy strict mode** configuration for type safety
- **Optional dependencies**: `pip install trendspyg[analysis]` for JSON/Parquet/DataFrame support

### Changed
- Updated `download_google_trends_csv()` signature with type hints
- Enhanced error messages for missing dependencies (pandas, pyarrow)
- Improved type safety throughout codebase
- Updated mypy configuration from Python 3.8 to 3.9 minimum

### Fixed
- Type consistency in elapsed_time variable (int → float)
- Minor type errors discovered by mypy strict mode

### Internal
- Added `_convert_csv_to_format()` helper function
- Added pandas and pyarrow to analysis extras
- Improved code maintainability with comprehensive type annotations
- Added automated tests for all output formats

## [0.1.3] - 2025-11-03

### Added
- **Input validation**: All parameters (geo, hours, category) are now validated with helpful error messages
- **Retry logic**: Automatic retry with exponential backoff (3 attempts: 1s, 2s, 4s delays)
- **Smart file detection**: Dynamic file checking (0.5s intervals, max 10s) instead of fixed 5-second wait
- **Custom exceptions**: Detailed exception classes with troubleshooting guidance
- **Prerequisites section** in README with Chrome installation requirements
- **Comprehensive Troubleshooting guide** in README with common issues and solutions

### Fixed
- **Helpful error messages**: Specific exceptions (TimeoutException, NoSuchElementException) with actionable solutions
- **Invalid input detection**: Suggests similar valid options when user provides invalid geo/category
- **Better error context**: All errors now include possible causes and solutions
- **CLI claim**: Removed non-existent CLI tool from pyproject.toml (coming in v0.2.0)

### Improved
- **Download speed**: File detection completes in 0.5s (previously waited fixed 5s)
- **Error handling**: Browser initialization errors caught with installation guidance
- **User experience**: Clear error messages guide users to solutions instead of cryptic stacktraces
- **Reliability**: Automatic retries handle temporary network issues

### Performance
- **10x faster file detection**: From 5s fixed wait to 0.5s average detection time
- **Automatic recovery**: 3 retries with backoff prevents failures from temporary issues

## [0.1.2] - 2025-11-03

### Fixed
- **Active-only filter**: Fixed broken UI selectors for "Active trends only" toggle. Now uses correct CSS selectors (`button[aria-label*='select trend status']` and `button[role='switch']`).
- **Menu closing**: Fixed element click intercepted error by using ESC key to properly close filter menus before clicking Export button.

### Changed
- **Sort parameter**: Documented that sort parameter only affects UI display, not CSV export order. CSV always exports in relevance order regardless of sort selection.
- **Improved selectors**: Switched from fragile XPath selectors to more reliable CSS selectors using aria-label attributes.

## [0.1.1] - 2025-11-03

### Fixed
- **Download path**: Fixed default download directory to use current working directory (`os.getcwd()`) instead of package installation directory. Files now save to `./downloads/` by default.
- **Performance**: Improved page load waiting by replacing `time.sleep()` calls with proper `WebDriverWait` for Export button and sort button.
- **Package naming**: Fixed remaining "trendspy" references to "trendspyg" in all files.

### Changed
- Increased timeout for sort button from 5s to 10s for better reliability.

## [0.1.0] - 2025-11-03

### Added
- Initial project structure
- Core configuration with 125 countries, 51 US states, 20 categories
- Basic downloader functionality (refactored from existing code)
- Python package setup
- MIT License
- Project documentation (README, roadmaps, guides)

### Project Goals
- Free, open-source alternative to abandoned pytrends
- 188,000+ configuration combinations
- Real-time monitoring capabilities
- Best-in-class documentation

[Unreleased]: https://github.com/flack0x/trendspyg/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/flack0x/trendspyg/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/flack0x/trendspyg/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/flack0x/trendspyg/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/flack0x/trendspyg/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/flack0x/trendspyg/compare/v0.4.5...v0.5.0
[0.4.5]: https://github.com/flack0x/trendspyg/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/flack0x/trendspyg/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/flack0x/trendspyg/compare/v0.4.2...v0.4.3
[0.4.0]: https://github.com/flack0x/trendspyg/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/flack0x/trendspyg/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/flack0x/trendspyg/compare/v0.1.4...v0.2.0
[0.1.4]: https://github.com/flack0x/trendspyg/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/flack0x/trendspyg/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/flack0x/trendspyg/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/flack0x/trendspyg/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/flack0x/trendspyg/releases/tag/v0.1.0
