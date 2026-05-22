# AGENTS.md

Reference for coding agents (Claude Code, Codex, Gemini CLI, Cursor, etc.) working with the `trendspyg` library. Human-written; agent-readable. Keep it short — link out for depth.

---

## What this library does

`trendspyg` is a Python library + CLI for **real-time Google Trends "Trending Now" data**. It is the maintained replacement for the archived `pytrends`. Two paths:

- **RSS path** (`download_google_trends_rss`) — fast (~0.2s), ~5–25 trends per region, includes news articles and images, no browser required. **Use this by default.**
- **CSV path** (`download_google_trends_csv`) — comprehensive (~10s), 480+ trends, supports time/category filtering, **requires Chrome + Selenium**. Use only when you need the extra volume or filtering.

Scope: current trends only. Historical/Explore data was removed in 0.2.0 on purpose — do not reintroduce it.

## Install

```bash
pip install trendspyg[all]      # everything
pip install trendspyg           # core (RSS path + CSV path, no CLI/async/DataFrame)
pip install trendspyg[cli]      # CLI only
pip install trendspyg[async]    # async RSS
pip install trendspyg[analysis] # DataFrame/JSON/Parquet output
```

## Minimal recipes

### Get unified, normalized data — recommended for agents

Pass `normalize=True` to either download path. You get one JSON-native schema
(a `NormalizedEnvelope`) that is **identical for the RSS and CSV paths** — learn
it once, and every field is always present and JSON-safe.

```python
from trendspyg import download_google_trends_rss

env = download_google_trends_rss(geo="US", normalize=True)
# env: {"schema_version", "source", "geo", "fetched_at", "count", "trends": [...]}
for t in env["trends"]:
    print(t["rank"], t["keyword"], t["volume_min"])   # volume_min is a real int
```

Same call shape for the CSV path: `download_google_trends_csv(geo="US", normalize=True)`.
CLI: `trendspyg rss --geo US --normalize` prints the envelope as pipe-clean JSON.

### Fetch trends for one region

```python
from trendspyg import download_google_trends_rss
trends = download_google_trends_rss(geo="US")
# trends: list[Trend]  (see type below)
```

### Fetch many regions in parallel

```python
import asyncio
from trendspyg import download_google_trends_rss_batch_async

results = asyncio.run(
    download_google_trends_rss_batch_async(["US", "GB", "DE", "JP"], max_concurrent=5)
)
# results: dict[str, list[Trend]]  (geo -> trends)
```

### Sort by volume

```python
trends = download_google_trends_rss(geo="US")
top = sorted(trends, key=lambda t: t["traffic_min"], reverse=True)[:5]
```

### Pipe-safe JSON from the CLI

```bash
trendspyg rss --geo US --output json --quiet | jq '.[0].trend'
trendspyg rss --geo US --output json --quiet --envelope | jq '.fetched_at, .count'
```

## Return shapes (import from `trendspyg`)

```python
from trendspyg import Trend, NewsArticle, TrendImage, TrendEnvelope
```

- `Trend` — keys: `trend: str`, `traffic: str` (e.g. `"50,000+"`), `traffic_min: int` (parsed, always present, `0` if unparseable), `published: datetime | str`, `explore_link: str`, optional `image: TrendImage`, optional `news_articles: list[NewsArticle]`.
- `NewsArticle` — `headline: str`, `url: str`, `source: str`, `image: str`.
- `TrendImage` — `url: str`, `source: str`.
- `TrendEnvelope` — `{fetched_at: str, geo: str, count: int, trends: list[Trend]}`. Only produced when passing `--envelope` to the CLI.

The `Trend` / `NewsArticle` / `TrendImage` TypedDicts are `total=False` — `image` and `news_articles` keys are present only when the corresponding include flags are true (default: true).

### Normalized shape (`normalize=True`)

```python
from trendspyg import NormalizedEnvelope, NormalizedTrend
```

- `NormalizedEnvelope` — `{schema_version: str, source: "rss"|"csv", geo: str, fetched_at: str, count: int, trends: list[NormalizedTrend]}`.
- `NormalizedTrend` — **every field is always present and JSON-safe**:
  `keyword: str`, `rank: int`, `volume_text: str`, `volume_min: int`,
  `started_at: str|None` (ISO 8601), `ended_at: str|None`, `is_active: bool`,
  `related_queries: list[str]`, `news: list[NewsArticle]`, `image: TrendImage|None`,
  `explore_url: str`. Fields a path cannot provide are `None`/`[]` — never missing.

## Exceptions

Catch `trendspyg.exceptions.TrendspygException` to handle any library error. Specifically:

- `RateLimitError` — HTTP 429/403 from Google. Back off and retry.
- `InvalidParameterError` — bad `geo`, `hours`, or `category`. Suggests valid values in the message.
- `DownloadError` — network / parse failure. Retry.
- `BrowserError` — CSV path only; Chrome/Selenium failed.
- `ParseError` — malformed response.

## Things to know (read before coding)

**For agents: pass `normalize=True`.** You get one stable, JSON-native schema across
both paths (see the first recipe). The notes below describe the raw, non-normalized output.

1. **Always prefer the RSS path.** CSV requires Chrome, takes ~10s, and is more fragile.
2. **The library caches RSS results for 5 minutes.** Pass `cache=False` to bypass. Use `clear_rss_cache()`, `get_rss_cache_stats()`, `set_rss_cache_ttl(seconds)` to control it.
3. **Rate limits are real.** When batching 50+ regions, set `max_concurrent<=5` and optionally `delay` between calls.
4. **`traffic_min` is new in 0.4.3.** Use it for sorting/filtering. Don't re-parse `traffic` by hand.
5. **Don't set `--envelope` unless you need it** — it changes the output shape.
6. **CSV sort param only affects the UI, not the export order.** Don't rely on it.

## Where things live

```
trendspyg/
├── __init__.py          — public exports
├── rss_downloader.py    — RSS path (sync + async + batch)
├── downloader.py        — CSV path (Selenium)
├── cli.py               — click-based CLI
├── types.py             — TypedDicts (Trend, NewsArticle, ...)
├── config.py            — COUNTRIES (125), US_STATES (51), CATEGORIES (20), TIME_PERIODS
├── utils.py             — TTLCache + helpers
├── exceptions.py        — TrendspygException + subclasses
└── version.py           — single source of truth for __version__
```

## If you're generating code

- Import from the top-level package (`from trendspyg import download_google_trends_rss`), not from submodules.
- Use the TypedDicts for annotations — don't redefine the dict shape.
- For batch fetches, default to the async batch function.
- Respect cache by default; only pass `cache=False` when you know you need fresh data.
- `geo` codes: uppercase ISO 3166 for countries (`"US"`, `"GB"`) or `"US-XX"` for US states (`"US-CA"`).

---

Full docs: `README.md`, `docs/API.md`, `CLI.md`, `CHANGELOG.md`, `examples/`.
