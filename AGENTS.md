# AGENTS.md

Reference for coding agents (Claude Code, Codex, Gemini CLI, Cursor, etc.) working with the `trendspyg` library. Human-written; agent-readable. Keep it short — link out for depth.

---

## What this library does

`trendspyg` is a Python library + CLI for Google Trends data. It is the maintained replacement for the archived `pytrends`. Three paths:

- **RSS path** (`download_google_trends_rss`) — fast (typically 0.2–2s, network-dependent), ~10–20 current trends per region, includes news articles and images, no browser required. **Use this by default for "what's trending now?"**
- **CSV path** (`download_google_trends_csv`) — comprehensive (~10s), 480+ current trends, supports time/category filtering, **requires Chrome + Selenium**. Use when you need the extra volume or filtering.
- **Explore path** (`download_google_trends_interest_over_time`, `download_google_trends_explore`, `download_google_trends_comparison`) — **keyword analysis over time** (interest over time, related queries, interest by region, multi-keyword comparison on one shared scale) — the data `pytrends` was most used for. Requires Chrome; **rate-limit sensitive (~10–90s, may retry)**. Use for "how is interest in keyword *X* moving / where does it peak / which of these terms wins?", **not** for high-frequency polling.

## Install

```bash
pip install trendspyg[all]      # everything
pip install trendspyg           # core (RSS path + CSV path, no CLI/async/DataFrame)
pip install trendspyg[cli]      # CLI only
pip install trendspyg[async]    # async RSS
pip install trendspyg[analysis] # DataFrame/JSON/Parquet output
pip install trendspyg[mcp]      # MCP server (Python 3.10+)
```

## MCP server — the zero-code path

If your host supports MCP, you don't need to write Python at all: register the
`trendspyg-mcp` command (stdio) and call the tools directly.

```bash
pip install trendspyg[mcp]
claude mcp add trendspyg -- trendspyg-mcp   # Claude Code; other clients: command = "trendspyg-mcp"
```

Tools: `get_trending_now(geo)`, `compare_trending(geos)` (≤20),
`get_trend_changes(geo)` (diff since last call), `list_supported_options()` —
all <1s, no browser — plus `get_interest_over_time(keyword, geo, timeframe)`,
`compare_interest_over_time(keywords, geo, timeframe)` (2–5 terms, one shared
scale; ~10–40s, fail-fast retry profile) and `get_trending_full(geo, hours,
category)` (~10–15s). The browser tools drive Chrome and are rate-limited:
call once, never loop.

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

### Interest over time for a keyword (the pytrends use case)

```python
from trendspyg import download_google_trends_interest_over_time
series = download_google_trends_interest_over_time("bitcoin", geo="US", timeframe="today 12-m")
# series: list[InterestPoint] -> [{"date": ISO8601, "value": int 0-100, "is_partial": bool}, ...]
```

Full Explore picture in one browser load:

```python
from trendspyg import download_google_trends_explore
env = download_google_trends_explore("bitcoin", geo="US")
# env: ExploreEnvelope -> interest_over_time + related_queries{top,rising} + interest_by_region
```

CLI: `trendspyg explore --keyword bitcoin --full --quiet | jq .`
This path drives Chrome and is rate-limit sensitive — catch `RateLimitError` and back off; do not poll it frequently.

### Compare 2-5 keywords on ONE shared scale (new in 1.1.0)

**Use this to compare terms — never compare separate single-keyword calls.** Google
scales each single-keyword series independently (its own max = 100), so only a
comparison call returns directly comparable numbers. One browser load, not N.

```python
from trendspyg import download_google_trends_comparison
env = download_google_trends_comparison(["bitcoin", "ethereum"], geo="US")
# env: ComparisonEnvelope ->
#   averages: {"bitcoin": 39, "ethereum": 7}                       # keyed by keyword
#   interest_over_time: [{"date", "values": {kw: int}, "is_partial"}, ...]
#   interest_by_region: [{"geo_code", "geo_name", "values": {kw: int}, "top_keyword"}, ...]
```

Limits: 2-5 distinct terms, no commas in a term (URL separator). Same Chrome +
rate-limit profile as the other Explore calls. CLI: repeat `-k` —
`trendspyg explore -k bitcoin -k ethereum --quiet | jq .averages`

### Fetch many regions in parallel

```python
import asyncio
from trendspyg import download_google_trends_rss_batch_async

results = asyncio.run(
    download_google_trends_rss_batch_async(
        ["US", "GB", "DE", "JP"], max_concurrent=5, normalize=True
    )
)
# results: dict[str, NormalizedEnvelope]  (geo -> envelope)
# drop normalize=True to get dict[str, list[Trend]] instead
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

### Monitor for changes (new in 0.7.0)

```python
from trendspyg import watch_google_trends_rss, diff_trends

# Stream changes between RSS snapshots — RSS-only, safe for continuous polling.
for change in watch_google_trends_rss(geo="US", interval=60, events=["new", "volume_up"]):
    print(change["event"], change["keyword"], change["volume_min"])

# Or diff two snapshots yourself (pure, JSON-safe, no network):
#   diff_trends(old_list, new_list) -> list[TrendChange]
```

`TrendChange` = `{event, keyword, rank, prev_rank, volume_min, prev_volume_min}` where
`event ∈ {new, dropped, volume_up, volume_down, rank_change}`. The CLI equivalent
`trendspyg watch` streams one NDJSON change per line. The constants `SCHEMA_VERSION`,
`EXPLORE_SCHEMA_VERSION`, and `MONITOR_SCHEMA_VERSION` are importable from `trendspyg`
for drift detection.

## Return shapes (import from `trendspyg`)

```python
from trendspyg import Trend, NewsArticle, TrendImage, TrendEnvelope
from trendspyg import InterestPoint, RelatedQuery, RegionInterest, ExploreEnvelope
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

### Explore shapes (new in 0.6.0 — JSON-safe by construction, no `normalize` needed)

- `InterestPoint` — `{date: str (ISO 8601), value: int (0-100), is_partial: bool}`.
- `RelatedQuery` — `{query: str, value: int, formatted_value: str (e.g. "+3,650%", "Breakout"), link: str}`.
- `RegionInterest` — `{geo_code: str, geo_name: str, value: int (0-100)}`.
- `ExploreEnvelope` — `{schema_version, source: "explore", keyword, geo, timeframe, fetched_at, count, interest_over_time: list[InterestPoint], related_queries: {"top": [...], "rising": [...]}, interest_by_region: list[RegionInterest]}`.
  `related_queries`/`interest_by_region` are empty lists when not requested or not returned by Google (the time series is guaranteed).
- `ComparisonEnvelope` (new in 1.1.0) — `{schema_version, source: "explore_comparison", keywords: list[str], geo, timeframe, fetched_at, count, averages: {kw: int}, interest_over_time: list[ComparisonPoint], interest_by_region: list[ComparisonRegionInterest]}`.
  `ComparisonPoint` = `{date, values: {kw: int 0-100}, is_partial}`; `ComparisonRegionInterest` = `{geo_code, geo_name, values: {kw: int}, top_keyword}`. All values share ONE 0-100 scale across the compared keywords.

## Exceptions

Catch `TrendspygException` to handle any library error. Since 1.0.0 all exception
classes are importable from the package root (`from trendspyg import RateLimitError`);
`trendspyg.exceptions` also works. Specifically:

- `RateLimitError` — HTTP 429/403 from Google. Back off and retry.
- `InvalidParameterError` — bad `geo`, `hours`, or `category`. Suggests valid values in the message.
- `DownloadError` — network / parse failure. Retry.
- `BrowserError` — CSV and Explore paths; Chrome/Selenium failed.
- `RateLimitError` — also raised by the Explore path when Google persistently throttles (the "try again in a bit" state). Back off and retry; do not poll frequently.
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
├── explore.py           — Explore path (interest over time, related, geo)
├── normalize.py         — normalize=True engine (RSS/CSV unified schema)
├── cli.py               — click-based CLI
├── types.py             — TypedDicts (Trend, ExploreEnvelope, ...)
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
