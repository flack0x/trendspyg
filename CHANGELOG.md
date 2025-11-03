# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/flack0x/trendspyg/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/flack0x/trendspyg/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/flack0x/trendspyg/releases/tag/v0.1.0
