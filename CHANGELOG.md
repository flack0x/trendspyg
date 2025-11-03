# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Core configuration with 114 countries, 51 US states, 20 categories
- Basic downloader functionality (refactored from existing code)
- Python package setup
- MIT License
- Project documentation (README, roadmaps, guides)

### Project Goals
- Free, open-source alternative to abandoned pytrends
- 188,000+ configuration combinations
- Real-time monitoring capabilities
- Best-in-class documentation

[Unreleased]: https://github.com/flack0x/trendspyg/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/flack0x/trendspyg/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/flack0x/trendspyg/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/flack0x/trendspyg/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/flack0x/trendspyg/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/flack0x/trendspyg/releases/tag/v0.1.0
