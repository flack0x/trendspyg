# trendspyg

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Free, open-source Python library for Google Trends data** - a modern alternative to the archived pytrends with **188,000+ configuration options**.

> **Note:** pytrends was archived on April 17, 2025 with no replacement. trendspyg is built to fill this gap with enhanced features and active maintenance.

---

## ✨ Features

- 🔥 **"Trending now" data** - Real-time trending searches from Google Trends
- 🌍 **114 countries** supported
- 🗺️ **51 US states** + sub-regions
- 📊 **20 categories** (sports, entertainment, technology, etc.)
- ⏰ **4 time periods** (4h, 24h, 48h, 7 days)
- 📈 **Frequent updates** - RSS updates ~9 times/hour, CSV exports ~every minute
- 🎯 **Active trends filtering** - Show only rising trends
- 🔄 **4 sort options** (relevance, title, volume, recency)
- 💾 **4 output formats** - CSV, JSON, Parquet, DataFrame (v0.1.4+)
- 🎨 **Full type hints** - Complete IDE support with IntelliSense (v0.1.4+)
- 📦 **Easy installation** - just `pip install trendspyg`
- 🆓 **100% free** and open-source

**Total combinations: 188,000+**

---

## 🚀 Quick Start

### Installation

```bash
pip install trendspyg
```

### Prerequisites

**Required:**
- **Chrome Browser** must be installed on your system
  - Download: [https://www.google.com/chrome/](https://www.google.com/chrome/)
  - ChromeDriver is automatically managed by Selenium
  - trendspyg uses browser automation to access Google Trends data

**System Requirements:**
- Python 3.8 or higher
- Active internet connection
- Permissions to download files

### Basic Usage

```python
from trendspyg.downloader import download_google_trends_csv

# Download trends (default: US, past 24 hours, all categories)
file_path = download_google_trends_csv()
# Returns: "trends_US_24h_all_20251103-041108.csv"
```

### Advanced Usage

```python
from trendspyg.downloader import download_google_trends_csv

# California, past 7 days, sports only, sorted by volume
file_path = download_google_trends_csv(
    geo='US-CA',          # State-level support!
    hours=168,            # 7 days
    category='sports',    # Filter by category
    active_only=True,     # Only rising trends
    sort_by='volume'      # Sort by popularity
)
# Returns path to downloaded CSV file
```

### Multiple Output Formats (v0.1.4+)

Choose from **4 output formats** to match your workflow:

```python
from trendspyg.downloader import download_google_trends_csv

# CSV (default) - Universal compatibility
csv_file = download_google_trends_csv(geo='US', output_format='csv')

# JSON - Perfect for APIs and web apps
json_file = download_google_trends_csv(geo='US', output_format='json')

# Parquet - Efficient storage (50-80% smaller than CSV)
parquet_file = download_google_trends_csv(geo='US', output_format='parquet')

# DataFrame - Immediate analysis, no file I/O
import pandas as pd
df = download_google_trends_csv(geo='US', output_format='dataframe')
print(df.head())
```

**Installation for all formats:**
```bash
pip install trendspyg[analysis]  # Includes pandas + pyarrow
```

| Format | Best For | File Size | Requires |
|--------|----------|-----------|----------|
| **CSV** | Excel, universal compatibility | Medium | Built-in |
| **JSON** | APIs, JavaScript, NoSQL | Large | pandas |
| **Parquet** | Big data, data lakes | Small (50-80% less) | pandas + pyarrow |
| **DataFrame** | In-memory analysis | N/A | pandas |

---

## 📊 Data Format & Output

### What Data Source?

trendspyg fetches data from Google Trends **"Trending now"** page (trends.google.com/trending) - NOT the "Explore" page.

**Technical Details:**
- **Data Source:** Google Trends RSS feed
- **Page:** "Trending now" tab on Google Trends
- **RSS Update Frequency:** ~9 times per hour (approximately every 5-7 minutes)
- **CSV Export Frequency:** Updates almost every minute (when Google publishes new data)

> **Note:** This package accesses the real-time "Trending now" page data. Support for the "Explore" page (historical trends, comparison charts, interest over time) is planned for v0.2.0+.

### CSV Output Format

Each download returns a CSV file with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| **Trends** | Main search keyword | "bills", "vikings vs lions" |
| **Search volume** | Popularity tier | 50K+, 100K+, 200K+, 500K+, 1M+ |
| **Started** | When trend started | "November 2, 2025 at 11:00:00 PM UTC+2" |
| **Ended** | When trend ended (if applicable) | Usually empty for active trends |
| **Trend breakdown** | Related search terms (comma-separated) | "buffalo bills,bills chiefs,josh allen,..." |
| **Explore link** | Direct Google Trends URL | https://trends.google.com/trends/explore?q=... |

### Example Output

```csv
"Trends","Search volume","Started","Ended","Trend breakdown","Explore link"
"bills","1M+","November 2, 2025 at 11:00:00 PM UTC+2",,"buffalo bills,kansas city chiefs vs buffalo bills,bills chiefs,josh allen,...","https://trends.google.com/trends/explore?q=bills&geo=US&hl=en-US"
"vikings vs lions","1M+","November 2, 2025 at 3:20:00 PM UTC+2",,"lions vs vikings,detroit lions,lions game,vikings game,...","https://trends.google.com/trends/explore?q=vikings%20vs%20lions&geo=US&hl=en-US"
```

### Why This Data is Valuable

- **Real-time insights** - See what's trending RIGHT NOW
- **Search volume tiers** - Gauge popularity at a glance
- **Related keywords** - Discover content ideas and variations (perfect for SEO)
- **Direct exploration** - Click through to deep-dive any trend
- **Easy analysis** - CSV format works with Excel, Python, R, or any data tool

---

## 📖 Why trendspyg?

| Feature | trendspyg | pytrends | Commercial APIs |
|---------|-----------|----------|-----------------|
| **Status** | ✅ Active | ❌ Archived (April 2025) | ✅ Active |
| **Price** | **FREE** | FREE | $0.003-$0.015/request |
| **Countries** | **114** | ~50 | All |
| **US States** | **51** | ❌ None | Some |
| **Categories** | **20** | Limited | All |
| **Configurations** | **188,000+** | ~1,000 | Many |
| **Real-time Monitoring** | ✅ Every ~1 min | ❌ | ❌ |
| **Maintained** | ✅ Yes | ❌ No | ✅ Yes |

---

## 🌍 Supported Options

### Countries (114 total)
US, CA, UK, AU, IN, JP, DE, FR, BR, MX, ES, IT, RU, KR, and 100+ more

### US States (51 total)
US-AL, US-AK, US-AZ, US-AR, US-CA, US-CO, US-CT, US-DE, US-DC, US-FL, US-GA, US-HI, US-ID, US-IL, US-IN, US-IA, US-KS, US-KY, US-LA, US-ME, US-MD, US-MA, US-MI, US-MN, US-MS, US-MO, US-MT, US-NE, US-NV, US-NH, US-NJ, US-NM, US-NY, US-NC, US-ND, US-OH, US-OK, US-OR, US-PA, US-RI, US-SC, US-SD, US-TN, US-TX, US-UT, US-VT, US-VA, US-WA, US-WV, US-WI, US-WY

### Categories (20 total)
all, sports, entertainment, business, politics, technology, health, science, games, shopping, food, travel, beauty, hobbies, climate, jobs, law, pets, autos, other

### Time Periods
- **4 hours** - Breaking trends
- **24 hours** - Daily summary (default)
- **48 hours** - 2-day overview
- **7 days** - Weekly trends

---

## 📚 Documentation

- **[Complete Options Reference](COMPLETE_OPTIONS_REFERENCE.md)** - All 188K+ configurations
- **[Changelog](CHANGELOG.md)** - Version history
- **[Roadmap](ROADMAP.md)** - Public feature roadmap

---

## 🤝 Contributing

Contributions are welcome! This project was born from the need to replace the archived pytrends.

**Ways to contribute:**
- Report bugs
- Suggest features
- Submit pull requests
- Improve documentation
- Share your use cases

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📊 Use Cases

- **Marketing & SEO** - Keyword research, trend analysis
- **Journalism** - Breaking news validation, public sentiment
- **Academic Research** - Economic forecasting, social trends
- **Trading & Finance** - Market sentiment analysis
- **Data Analysis** - Dashboards, visualizations

---

## 🔧 Troubleshooting

### Common Issues

**"Chrome browser not found" or "WebDriver error"**
```
Solution:
1. Install Chrome browser: https://www.google.com/chrome/
2. Ensure Chrome is in your PATH
3. Update trendspyg: pip install --upgrade trendspyg
```

**"Invalid geo code" error**
```python
# ❌ Wrong
download_google_trends_csv(geo="USA")  # Should be "US"

# ✅ Correct
download_google_trends_csv(geo="US")   # Two-letter country code
```
See all valid codes: `from trendspyg.config import COUNTRIES, US_STATES`

**"Invalid hours value" error**
```python
# ❌ Wrong
download_google_trends_csv(hours=12)  # Not supported

# ✅ Correct - Use one of: 4, 24, 48, 168
download_google_trends_csv(hours=24)  # Past 24 hours
```

**"No such element" or UI changed**
```
This means Google Trends changed their website layout.

Solution:
1. Update trendspyg: pip install --upgrade trendspyg
2. Check GitHub issues: https://github.com/flack0x/trendspyg/issues
3. Report the issue if not already reported
```

**Download timeout or slow connection**
- The library automatically retries 3 times with exponential backoff
- Increase wait time if on slow connection (this is automatic)
- Check if trends.google.com is accessible in your browser

**File not downloading**
```
Check:
- Download directory permissions
- Antivirus/firewall not blocking
- Disk space available
- Default: ./downloads/ folder
```

### Getting Help

1. **Check Error Message** - Error messages include specific solutions
2. **Search Issues** - [GitHub Issues](https://github.com/flack0x/trendspyg/issues)
3. **Report Bug** - Include full error message and code snippet
4. **Ask Community** - [GitHub Discussions](https://github.com/flack0x/trendspyg/discussions)

---

## 🗺️ Roadmap

### v0.1.0 (Current)
- ✅ "Trending now" data downloads (RSS feed)
- ✅ 188,000+ configuration options
- ✅ Python package structure
- ✅ 114 countries + 51 US states
- ✅ CSV output format

### v0.2.0 (Coming Soon)
- [ ] CLI tool (`trendspyg download --geo US-CA`)
- [ ] Google Trends "Explore" page data (historical trends, comparisons)
- [ ] Real-time monitoring mode
- [ ] Batch downloads
- [ ] Enhanced error handling

### v0.3.0 (Future)
- [ ] Pandas integration
- [ ] Export formats (JSON, Excel, Parquet)
- [ ] Caching layer
- [ ] Async support
- [ ] Data visualization helpers

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Built as a successor to **pytrends** (GeneralMills/pytrends) which was archived April 17, 2025
- Inspired by the 200,000+ monthly users who need reliable Google Trends data access
- Thanks to the open-source community for making this possible

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/flack0x/trendspyg/issues)
- **Discussions:** [GitHub Discussions](https://github.com/flack0x/trendspyg/discussions)
- **Documentation:** [GitHub Wiki](https://github.com/flack0x/trendspyg/wiki)

---

## ⭐ Star History

If you find trendspyg useful, please consider starring the repository!

[![Star History Chart](https://api.star-history.com/svg?repos=flack0x/trendspyg&type=Date)](https://star-history.com/#flack0x/trendspyg&Date)

---

**Built with ❤️ for the data community**

*trendspyg - Spy on trends, not on users. Free forever.*
