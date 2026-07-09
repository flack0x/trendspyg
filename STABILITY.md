# API Stability Policy

As of **v1.0.0**, trendspyg follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
with the concrete rules below. This document defines exactly what "the public API"
means for this project — the semver promise is only as good as that definition.

## What is covered

The following surfaces are stable. Removing or renaming anything here, changing
its documented behavior, or narrowing what it accepts is a **breaking change**
and only happens in a major release.

### 1. The Python API

Every name in `trendspyg.__all__` — the full list:

- **Downloaders:** `download_google_trends_rss`, `download_google_trends_rss_async`,
  `download_google_trends_rss_batch`, `download_google_trends_rss_batch_async`,
  `download_google_trends_csv`, `download_google_trends_interest_over_time`,
  `download_google_trends_explore`
- **Monitoring:** `watch_google_trends_rss`, `diff_trends`, `filter_changes`, `post_webhook`
- **Cache control:** `clear_rss_cache`, `get_rss_cache_stats`, `set_rss_cache_ttl`
- **Exceptions:** `TrendspygException`, `DownloadError`, `RateLimitError`,
  `InvalidParameterError`, `BrowserError`, `ParseError` — importable from the
  package root and from `trendspyg.exceptions`. Every trendspyg error subclasses
  `TrendspygException`; the exception *type* raised for a given failure class is
  part of the contract (the message text is not).
- **Schema constants:** `SCHEMA_VERSION`, `EXPLORE_SCHEMA_VERSION`, `MONITOR_SCHEMA_VERSION`
- **Typed shapes:** `Trend`, `NewsArticle`, `TrendImage`, `TrendEnvelope`,
  `NormalizedTrend`, `NormalizedEnvelope`, `InterestPoint`, `RelatedQuery`,
  `RegionInterest`, `ExploreEnvelope`, `TrendChange`
- `__version__`

Covered per name: the signature (parameter names, their defaults' *behavior*,
accepted values) and the documented return shape. Keyword arguments stay valid;
new parameters are only added with defaults that preserve existing behavior.

This surface is pinned by a test (`tests/test_public_api.py`) — CI fails if it
drifts.

### 2. Data schemas

The three envelope/event schemas are versioned independently by their constants:

| Schema | Constant | Produced by |
|---|---|---|
| `NormalizedEnvelope` / `NormalizedTrend` | `SCHEMA_VERSION` | `normalize=True` on RSS/CSV paths |
| `ExploreEnvelope` | `EXPLORE_SCHEMA_VERSION` | the Explore path |
| `TrendChange` | `MONITOR_SCHEMA_VERSION` | monitoring / `trendspyg watch` |

Removing or renaming a field, or changing a field's type/meaning, is breaking
(major release + schema-constant bump). *Adding* a field is a minor release and
bumps the schema constant's minor component. Consumers should tolerate unknown
extra fields.

### 3. The CLI

Command names (`rss`, `csv`, `explore`, `watch`, `list`, `info`), their flags,
and the pipe contract: **data goes to stdout, banners/progress/errors go to
stderr**; `watch` streams one NDJSON object per line. Removing a command or
flag, or moving data off stdout, is breaking. New commands/flags are minor.

### 4. The MCP server

The entry point (`trendspyg-mcp`), the six tool names, and their parameters:
`get_trending_now`, `compare_trending`, `get_trend_changes`,
`list_supported_options`, `get_interest_over_time`, `get_trending_full`.
Tool result payloads follow the data schemas above.

### 5. Python version support

The 1.x line supports **Python 3.8+** (the MCP extra requires 3.10+, as its SDK
does). Dropping a Python version is a breaking change reserved for a major
release.

## What is NOT covered

Honesty about the boundary matters as much as the promise:

- **Google's side of the wire.** trendspyg reads Google Trends by RSS feed and
  browser automation. Google can change data contents, availability, throttling
  behavior, or page structure at any time — that can break a data path in *any*
  release of this library, and fixes ship as patches. The contract covers what
  the library accepts and returns **when Google serves data**, not Google.
- **Private names.** Anything prefixed with `_`, and any module content not
  exported in `__all__` (e.g. the internals of `trendspyg.mcp_server`,
  `trendspyg.normalize`, `trendspyg.utils`). Import at your own risk.
- **Exception message text.** Catch types, don't parse messages.
- **Performance.** Timings are network-dominated; see `benchmarks/` for honest
  measured numbers, not guarantees.
- **Dependency pins.** Floors may rise in minor releases (e.g. for security);
  we don't promise compatibility with any specific selenium/requests version.
- **Runtime types of TypedDicts.** The typed shapes are static hints; at
  runtime the library returns plain dicts.

## Deprecation policy

When something covered must go:

1. It keeps working, emits a `DeprecationWarning`, and is flagged in the
   CHANGELOG for **at least one minor release**.
2. It is removed only in the next **major** release.
3. The CHANGELOG entry names the replacement.

## Release discipline

- **Patch (1.0.x):** bug fixes, doc changes, internal refactors, Google-breakage
  repairs. No API change.
- **Minor (1.x.0):** new functions, parameters (defaulted), schema fields,
  CLI flags, MCP tools. Deprecation announcements.
- **Major (x.0.0):** anything that removes, renames, or changes documented
  behavior of a covered surface; Python-version drops.

Only the latest release receives fixes (see [SECURITY.md](SECURITY.md)).
