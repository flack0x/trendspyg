# trendspyg

**Google Trends data in Python** — real-time trending topics *and* keyword
analysis over time. A modern, actively maintained alternative to the archived
`pytrends`.

```bash
pip install trendspyg            # core (RSS path)
pip install trendspyg[all]       # + CLI, async, pandas/parquet
pip install trendspyg[mcp]       # + MCP server for Claude & AI agents
```

## Three data paths

| Path | Answers | Speed | Chrome? |
|---|---|---|---|
| **RSS** | what's trending right now (10–20 trends + news/images) | sub-second\* | No |
| **CSV** | what's trending right now (480+ trends, time/category filters) | ~10s | Yes |
| **Explore** | how interest in a keyword moves — over time, by region, related queries, 2–5-keyword comparison, web/YouTube/News/Images/Shopping | ~10–40s (cached repeats instant) | Yes |

\* Network-dominated; honest measured numbers per path live in
[benchmarks](https://github.com/flack0x/trendspyg/tree/main/benchmarks).

## Sixty seconds of everything

```python
from trendspyg import (
    download_google_trends_rss,
    download_google_trends_interest_over_time,
    download_google_trends_comparison,
    get_keyword_history,
)

# What's trending in the US right now?
trends = download_google_trends_rss(geo="US", normalize=True)

# How has interest in "bitcoin" moved this year? (cache: repeats skip the browser)
series = download_google_trends_interest_over_time("bitcoin", cache="disk")

# bitcoin vs ethereum on ONE shared 0-100 scale (the pytrends kw_list use case)
env = download_google_trends_comparison(["bitcoin", "ethereum"])

# YouTube search interest instead of web (new in 1.5.0)
yt = download_google_trends_interest_over_time("bitcoin", gprop="youtube")

# Archive fetches locally, then ask "when did X first trend?"
download_google_trends_rss(geo="US", archive=True)
get_keyword_history("bitcoin")
```

Or from the terminal:

```bash
trendspyg rss --geo US
trendspyg explore -k bitcoin --cache disk --archive
trendspyg watch --geo US --events new,volume_up
trendspyg history -k bitcoin --timeline
```

## Where to go next

- **[API Reference](API.md)** — every function, parameter and returned shape.
- **[CLI](CLI.md)** — all commands and flags.
- **[Agents & MCP](AGENTS.md)** — the MCP server (8 tools for Claude and any
  MCP client) and agent-ready schemas.
- **[Stability Contract](STABILITY.md)** — what semver covers, in writing.
- **[Changelog](CHANGELOG.md)** · **[Roadmap](ROADMAP.md)**
- [GitHub](https://github.com/flack0x/trendspyg) ·
  [PyPI](https://pypi.org/project/trendspyg/)
