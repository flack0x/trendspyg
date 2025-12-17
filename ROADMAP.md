# trendspyg - Development Roadmap

**Current Version:** v0.2.0
**Status:** Active Development - Focused Scope

---

## 🎯 Project Vision

Build a free, open-source Python library for accessing Google Trends data - a modern alternative to the archived pytrends library.

---

## ✅ v0.2.0 - Focused Scope (Current Release)

**Status:** Released - November 4, 2025

### Changes
- ✅ **Refocused on real-time data** - Removed Explore page functionality
- ✅ **Streamlined codebase** - Deleted experimental features
- ✅ **Simplified API** - Single core function `download_google_trends_csv()`
- ✅ **Removed Playwright dependency** - Selenium only for "Trending Now"
- ✅ **Updated documentation** - Clear focus on real-time trends

### Rationale
Focusing on what trendspyg does best: **real-time "Trending Now" data**. This makes the library simpler, more maintainable, and easier to use.

---

## ✅ v0.1.4 - Type Safety & Output Formats

**Status:** Released - November 3, 2025

### Features
- ✅ Complete type hints across codebase (PEP 484 compliant)
- ✅ Multiple output formats: CSV, JSON, Parquet, DataFrame
- ✅ Optional dependencies for analysis features
- ✅ Mypy strict mode configuration

---

## ✅ v0.1.0 - v0.1.3 - Foundation

**Status:** Released - November 3, 2025

### Features
- ✅ "Trending now" data downloads (Google Trends RSS feed)
- ✅ 188,000+ configuration options
  - 125 countries supported
  - 51 US states + sub-regions
  - 20 categories
  - 4 time periods (4h, 24h, 48h, 7 days)
- ✅ Active trends filtering
- ✅ 4 sort options (relevance, title, volume, recency)
- ✅ Input validation with helpful error messages
- ✅ Retry logic with exponential backoff
- ✅ Custom exception hierarchy

### Technical
- Python 3.8+ support
- Selenium-based browser automation
- Headless mode support
- Automatic file naming with timestamps

---

## 🚧 v0.3.0 - Enhanced Features (Coming Soon)

**Target:** Q1 2026
**Focus:** Usability & Monitoring

### Planned Features
- [ ] CLI tool (`trendspyg download --geo US-CA --category sports`)
- [ ] Real-time monitoring mode
  - Continuous polling
  - Change detection
  - Automatic notifications
- [ ] Batch downloads
  - Multiple countries at once
  - Scheduled downloads
  - Parallel processing

### Quality Improvements
- [ ] CI/CD pipeline
- [ ] Code coverage > 80%
- [ ] Performance optimizations
- [ ] More comprehensive test suite

---

## 🔮 v0.4.0 - Advanced Features (Future)

**Target:** Q2 2026
**Focus:** Performance & Developer Experience

### Planned Features
- [ ] Caching layer
  - Local cache for repeated queries
  - Configurable cache duration
  - Cache invalidation strategies
- [ ] Async support
  - asyncio-compatible API
  - Concurrent downloads
  - Better performance for batch operations
- [ ] Additional export formats
  - Excel/XLSX export
  - SQLite export
  - Direct database integration

### Developer Experience
- [ ] Plugin system
- [ ] Custom data processors
- [ ] Hooks for pre/post download
- [ ] Extensive examples library
- [ ] Data analysis helpers (built on top of DataFrame output)

---

## 🌟 v1.0.0 - Stable Release (Long-term Goal)

**Target:** 2026
**Focus:** Production Stability

### Goals
- [ ] API stability guarantee
- [ ] Full test coverage
- [ ] Comprehensive documentation
- [ ] Performance benchmarks
- [ ] Security audit
- [ ] Extensive real-world testing

### Advanced Features
- [ ] Data visualization helpers
- [ ] Trend analysis utilities
- [ ] Machine learning integration
- [ ] Historical data archiving
- [ ] Advanced filtering options

---

## 📊 Success Metrics

### Adoption
- PyPI downloads: Track monthly growth
- GitHub stars: Community engagement
- Contributors: Open-source collaboration
- Issues resolved: Responsiveness

### Quality
- Test coverage: Target 85%+
- Documentation: Complete API reference
- Performance: < 10 second downloads
- Stability: < 1% error rate

---

## 🤝 Contributing

We welcome contributions! Areas where you can help:

### Development
- Implement planned features
- Fix bugs
- Improve performance
- Add tests

### Documentation
- Improve README
- Write tutorials
- Add examples
- Translate docs

### Community
- Answer questions
- Report bugs
- Suggest features
- Share use cases

---

## 📝 Release Schedule

- **Minor releases (0.x.0):** Every 2-3 months
- **Patch releases (0.0.x):** As needed for bugs
- **Major releases (x.0.0):** When API changes required

---

## 🔗 Links

- **GitHub:** https://github.com/flack0x/trendspyg
- **PyPI:** https://pypi.org/project/trendspyg/ (coming soon)
- **Documentation:** https://github.com/flack0x/trendspyg#readme
- **Issues:** https://github.com/flack0x/trendspyg/issues

---

## 📢 Stay Updated

- Watch the GitHub repository for releases
- Check CHANGELOG.md for detailed version history
- Follow project discussions for announcements

---

**Last Updated:** November 3, 2025
