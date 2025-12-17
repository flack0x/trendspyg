# trendspyg

[![PyPI version](https://img.shields.io/pypi/v/trendspyg.svg)](https://pypi.org/project/trendspyg/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/flack0x/trendspyg/actions/workflows/tests.yml/badge.svg)](https://github.com/flack0x/trendspyg/actions)
[![PyPI Downloads](https://static.pepy.tech/badge/trendspyg)](https://pepy.tech/project/trendspyg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Free, open-source Python library for real-time Google Trends data** - a modern alternative to the archived pytrends with **188,000+ configuration options**.

> **Note:** pytrends was archived on April 17, 2025 with no replacement. trendspyg is built to fill this gap with enhanced features and active maintenance.

---

## ✨ Features

### Trending Now (Real-time Data)
- 🔥 **"Trending now" data** - Real-time trending searches from Google Trends
- 🌍 **125 countries** supported
- 🗺️ **51 US states** + sub-regions
- 📊 **20 categories** (sports, entertainment, technology, etc.)
- ⏰ **4 time periods** (4h, 24h, 48h, 7 days)
- 📈 **Frequent updates** - RSS updates ~9 times/hour, CSV exports ~every minute
- 🎯 **Active trends filtering** - Show only rising trends
- 🔄 **4 sort options** (relevance, title, volume, recency)
- 💾 **4 output formats** - CSV, JSON, Parquet, DataFrame
- 🎨 **Full type hints** - Complete IDE support with IntelliSense
- 📦 **Easy installation** - just `pip install trendspyg`
- 🆓 **100% free** and open-source

**Total combinations: 188,000+**

---

## 🚀 Quick Start

### Installation

```bash
pip install trendspyg
```

### Two Data Sources - Choose Your Path

trendspyg provides **two complementary ways** to access Google Trends data:

#### 🚀 **Fast Path: RSS Feed** (Recommended for most users)
- ⚡ **0.2 seconds** - 50x faster than CSV
- 📰 **Rich media**: News articles, headlines, images
- 🔄 **Perfect for**: Real-time monitoring, journalism, qualitative research
- ⚠️ **Limitation**: ~10-20 trends, no filtering

#### 📊 **Full Path: CSV Export**
- 📈 **480 trends** - Comprehensive dataset
- ⏱️ **Time filtering**: 4h, 24h, 48h, 7 days
- 🎯 **Category filtering**: Sports, tech, etc.
- 🕐 **~10 seconds** - Requires browser automation
- 🎓 **Perfect for**: Statistical analysis, research papers, large datasets

---

### Quick Examples

#### RSS - Fast & Rich Media (0.2s)

```python
from trendspyg import download_google_trends_rss

# Get current trends with news articles & images
trends = download_google_trends_rss(geo='US')

# Access rich data
for trend in trends[:3]:
    print(f"\n{trend['trend']} ({trend['traffic']})")
    print(f"  📰 {len(trend['news_articles'])} news articles")
    print(f"  📸 Image: {trend['image']['source']}")
    if trend['news_articles']:
        print(f"  Headline: {trend['news_articles'][0]['headline']}")
```

**Output:**
```
christine donohue (500+)
  📰 3 news articles
  📸 Image: Fox News
  Headline: What to expect for the Nov. 4 election in Pennsylvania

spot stock (200+)
  📰 3 news articles
  📸 Image: Yahoo Finance
  Headline: SPOT Stock Alert: Why Shares of Spotify Are Moving Today
```

#### CSV - Comprehensive & Filtered (10s)

```python
from trendspyg import download_google_trends_csv

# California, past 7 days, sports only, DataFrame format
df = download_google_trends_csv(
    geo='US-CA',          # State-level support!
    hours=168,            # 7 days
    category='sports',    # Filter by category
    active_only=True,     # Only rising trends
    output_format='dataframe'  # pandas DataFrame
)

print(f"Found {len(df)} sports trends in California")
# Found 480 sports trends in California
```

---

### Prerequisites

**For RSS (Fast Path):**
- ✅ Python 3.8+
- ✅ Internet connection
- ✅ That's it!

**For CSV (Full Path) - Additionally Requires:**
- 🌐 **Chrome Browser** - [Download here](https://www.google.com/chrome/)
- 📦 ChromeDriver (auto-managed by Selenium)

### Multiple Output Formats

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

## 📊 Data Sources Explained

### Choose Your Data Source

trendspyg provides **both RSS and CSV** - they're complementary, not competing!

| Feature | RSS Feed 🚀 | CSV Export 📊 |
|---------|-------------|---------------|
| **Speed** | 0.2 seconds | ~10 seconds |
| **Trends Count** | ~10-20 | 480 |
| **News Articles** | ✅ 3-5 per trend | ❌ No |
| **Article Headlines** | ✅ Yes | ❌ No |
| **Article URLs** | ✅ Yes | ❌ No |
| **Images** | ✅ Trend images | ❌ No |
| **News Sources** | ✅ Yes (e.g., "CNN", "BBC") | ❌ No |
| **Start/End Times** | ❌ No | ✅ Yes |
| **Related Searches** | ❌ No | ✅ Yes (comma-separated) |
| **Time Filtering** | ❌ No (current only) | ✅ Yes (4h/24h/48h/7d) |
| **Category Filter** | ❌ No | ✅ Yes (20 categories) |
| **Active-Only Filter** | ❌ No | ✅ Yes |
| **Sort Options** | ❌ No | ✅ Yes (4 options) |
| **Chrome Required** | ❌ No | ✅ Yes |
| **Best For** | Journalism, monitoring | Research, statistics |

---

### What Data Each Source Provides

#### 📰 RSS Feed Data Structure

```python
{
    "trend": "xrp",
    "traffic": "200+",
    "published": "2025-11-04 04:00:00",
    "image": {
        "url": "https://encrypted-tbn0.gstatic.com/...",
        "source": "CoinDesk"  # Image source
    },
    "news_articles": [
        {
            "headline": "XRP Price News: Ripple-Linked Token Approaches 'Death Cross'",
            "url": "https://www.coindesk.com/markets/2025/11/04/xrp-nears-death-cross",
            "source": "CoinDesk",
            "image": "https://encrypted-tbn0.gstatic.com/..."
        },
        {
            "headline": "Why XRP Is Going Down? Crypto Falls Today...",
            "url": "https://www.financemagnates.com/...",
            "source": "Finance Magnates",
            "image": "https://..."
        }
        // ... 3-5 articles per trend
    ],
    "explore_link": "https://trends.google.com/trends/explore?q=xrp"
}
```

**Why RSS is Valuable for Researchers:**
- ✅ **Qualitative Analysis**: Read actual news articles explaining trends
- ✅ **Source Validation**: Verify trends with credible news sources
- ✅ **Visual Content**: Images for presentations/papers
- ✅ **Fast Data Collection**: 0.2s enables frequent polling (every 5 min)
- ✅ **Citation Material**: Article URLs as references

---

#### 📈 CSV Export Data Structure

```csv
"Trends","Search volume","Started","Ended","Trend breakdown","Explore link"
"cowboys","2M+","November 4, 2025 at 1:50:00 AM UTC+2",,"cowboys,dallas cowboys,cowboys game,jacoby brissett,...","https://..."
```

**CSV Columns:**
- **Trends**: Main search keyword
- **Search volume**: Popularity tier (50K+, 100K+, 200K+, 500K+, 1M+, 2M+)
- **Started**: When trend began trending (timestamp)
- **Ended**: When trend stopped (usually empty for active trends)
- **Trend breakdown**: Related search terms (comma-separated list)
- **Explore link**: Direct Google Trends analysis URL

**Why CSV is Valuable for Researchers:**
- ✅ **Quantitative Analysis**: 480 trends for statistical significance
- ✅ **Historical Context**: Start/end times for temporal analysis
- ✅ **Time-based Studies**: Filter by 4h/24h/48h/7d periods
- ✅ **Semantic Analysis**: Related searches reveal topic clusters
- ✅ **Large Datasets**: Sufficient N for statistical tests

---

### 🎓 Research Use Cases - When to Use Each

#### Use RSS When You Need:

**1. Journalism & Breaking News**
```python
# Monitor trends every 5 minutes for breaking stories
trends = download_google_trends_rss('US')
for trend in trends:
    if trend['traffic'].startswith('1M'):  # Major spike
        print(f"🚨 ALERT: {trend['trend']}")
        print(f"   Source: {trend['news_articles'][0]['source']}")
        print(f"   Read: {trend['news_articles'][0]['url']}")
```

**2. Qualitative Research - Content Analysis**
```python
# Collect news articles about trending topics for discourse analysis
import pandas as pd

trends = download_google_trends_rss('US', output_format='dataframe')

# Analyze news sources
for idx, row in trends.iterrows():
    articles = row['news_articles']
    sources = [a['source'] for a in articles]
    print(f"{row['trend']}: Coverage by {', '.join(sources)}")
```

**3. Visual Presentations**
```python
# Get images for your research presentation
trends = download_google_trends_rss('US')

# Download trend images
for trend in trends[:5]:
    image_url = trend['image']['url']
    image_source = trend['image']['source']
    # Use in slides with proper attribution
```

---

#### Use CSV When You Need:

**1. Statistical Analysis - Academic Papers**
```python
# Large dataset for statistical significance
df = download_google_trends_csv(
    geo='US',
    hours=168,  # Past week
    output_format='dataframe'
)

print(f"N = {len(df)} trends")  # N = 480

# Analyze search volume distribution
import matplotlib.pyplot as plt
df['search_volume'].value_counts().plot(kind='bar')
plt.title('Search Volume Distribution (n=480)')
plt.show()
```

**2. Time-Series Studies**
```python
# Study how trends change over different time periods
periods = [4, 24, 48, 168]  # 4h, 1d, 2d, 7d

for period in periods:
    df = download_google_trends_csv(
        geo='US',
        hours=period,
        category='health',
        output_format='dataframe'
    )
    print(f"{period}h: {len(df)} health trends")
    # Analyze temporal patterns
```

**3. Semantic Network Analysis**
```python
# Build topic networks from related searches
df = download_google_trends_csv('US', output_format='dataframe')

# Extract related terms
for idx, row in df.iterrows():
    main_term = row['Trends']
    related = row['Trend breakdown'].split(',')
    # Build graph: main_term -> related terms
    # Use for network visualization
```

---

#### Use BOTH for Mixed-Methods Research

**Example: "Why did Bitcoin spike?"**

```python
# Step 1: RSS - Get qualitative context (fast)
trends = download_google_trends_rss('US')
bitcoin_trend = [t for t in trends if 'bitcoin' in t['trend'].lower()][0]

print("Qualitative Context:")
for article in bitcoin_trend['news_articles']:
    print(f"- {article['headline']}")
    print(f"  Source: {article['source']}")

# Step 2: CSV - Get quantitative data (comprehensive)
df = download_google_trends_csv(
    geo='US',
    hours=168,
    category='all',
    output_format='dataframe'
)

crypto_trends = df[df['Trends'].str.contains('bitcoin|crypto|btc', case=False)]
print(f"\nQuantitative Data: {len(crypto_trends)} crypto-related trends")
print(f"Related searches: {crypto_trends.iloc[0]['Trend breakdown']}")

# Result: Complete picture with both narrative (RSS) and numbers (CSV)
```

---

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
| **Countries** | **125** | ~50 | All |
| **US States** | **51** | ❌ None | Some |
| **Categories** | **20** | Limited | All |
| **Configurations** | **188,000+** | ~1,000 | Many |
| **Real-time Monitoring** | ✅ Every ~1 min | ❌ | ❌ |
| **Maintained** | ✅ Yes | ❌ No | ✅ Yes |

---

## 🌍 Supported Options

### Countries (125 total)
US, CA, UK, AU, IN, JP, DE, FR, BR, MX, ES, IT, RU, KR, and 111+ more

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

### v0.2.0 (Current)
- ✅ "Trending now" data downloads (RSS feed + CSV export)
- ✅ 188,000+ configuration options
- ✅ 125 countries + 51 US states
- ✅ 4 output formats (CSV, JSON, Parquet, DataFrame)
- ✅ Full type hints
- ✅ Active trends filtering

### v0.3.0 (Coming Soon)
- [ ] CLI tool (`trendspyg download --geo US-CA`)
- [ ] Real-time monitoring mode
- [ ] Batch downloads
- [ ] Enhanced error handling
- [ ] Caching layer

### v0.4.0 (Future)
- [ ] Async support
- [ ] Data visualization helpers
- [ ] Historical data archiving
- [ ] Advanced filtering options

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
