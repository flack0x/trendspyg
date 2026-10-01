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
  `download_google_trends_explore`, `download_google_trends_comparison` (1.1.0)
- **Monitoring:** `watch_google_trends_rss`, `diff_trends`, `filter_changes`, `post_webhook`
- **Topic lookup (1.8.0):** `get_keyword_suggestions`, returning
  `list[KeywordSuggestion]` with required string fields `mid`, `title`, `type`.
- **Cache control:** `clear_rss_cache`, `get_rss_cache_stats`, `set_rss_cache_ttl`,
  `clear_explore_cookies` (1.6.0) — plus the opt-in `cookies="disk"` parameter on
  the three Explore functions (1.6.0)
- **Archive (1.3.0):** `read_archive`, `get_keyword_history`, `get_archive_stats`,
  `prune_archive` — plus the opt-in `archive=` / `cache="disk"` / `db_path=`
  parameters on the RSS and CSV download functions. Since 1.4.0 the three
  Explore functions carry the same opt-in parameters (plus `cache_ttl=`),
  Explore snapshots use `source` `"explore"` / `"explore_comparison"`, and
  `read_archive` / `get_keyword_history` accept a sequence of sources.
- **Exceptions:** `TrendspygException`, `DownloadError`, `RateLimitError`,
  `InvalidParameterError`, `BrowserError`, `ParseError`, `ArchiveError` (1.3.0) —
  importable from the package root and from `trendspyg.exceptions`. Every
  trendspyg error subclasses `TrendspygException`; the exception *type* raised
  for a given failure class is part of the contract (the message text is not).
- **Schema constants:** `SCHEMA_VERSION`, `EXPLORE_SCHEMA_VERSION`,
  `MONITOR_SCHEMA_VERSION`, `COMPARISON_SCHEMA_VERSION` (1.1.0)
- **Typed shapes:** `Trend`, `NewsArticle`, `TrendImage`, `TrendEnvelope`,
  `NormalizedTrend`, `NormalizedEnvelope`, `InterestPoint`, `RelatedQuery`,
  `RegionInterest`, `ExploreEnvelope`, `ComparisonPoint`,
  `ComparisonRegionInterest`, `ComparisonEnvelope` (1.1.0), `TrendChange`,
  `KeywordHistoryPoint` (1.3.0)
- `__version__`

Covered per name: the signature (parameter names, their defaults' *behavior*,
accepted values) and the documented return shape. Keyword arguments stay valid;
new parameters are only added with defaults that preserve existing behavior.

This surface is pinned by a test (`tests/test_public_api.py`) — CI fails if it
drifts.

1.7.0 additions preserve defaults: keyword-only `envelope=False` on sync/async
single-region RSS functions; keyword-only `cache=True` on both RSS batch functions;
`include_context=False` on the watcher; `watch --archive/--db/--context`; and
`archive=False` on the four MCP Trending Now fetch tools. No root exports changed.
`envelope=True` returns the raw `TrendEnvelope` dict, ignoring `output_format`;
`normalize=True` takes precedence. Cache hits preserve original observation times.

### 2. Data schemas

The four envelope/event schemas are versioned independently by their constants:

| Schema | Constant | Produced by |
|---|---|---|
| `NormalizedEnvelope` / `NormalizedTrend` | `SCHEMA_VERSION` | `normalize=True` on RSS/CSV paths |
| `ExploreEnvelope` | `EXPLORE_SCHEMA_VERSION` | the Explore path |
| `TrendChange` | `MONITOR_SCHEMA_VERSION` | monitoring / `trendspyg watch` |
| `ComparisonEnvelope` / `ComparisonPoint` / `ComparisonRegionInterest` | `COMPARISON_SCHEMA_VERSION` | multi-keyword comparison (1.1.0) |

Removing or renaming a field, or changing a field's type/meaning, is breaking
(major release + schema-constant bump). *Adding* a field is a minor release and
bumps the schema constant's minor component. Consumers should tolerate unknown
extra fields. (Applied in 1.5.0: `ExploreEnvelope` and `ComparisonEnvelope`
gained a `gprop` field — both constants moved 1.0 → 1.1. Applied again in
1.6.0: `ExploreEnvelope` gained `is_empty` — `EXPLORE_SCHEMA_VERSION` 1.1 → 1.2.)

1.7.0 schema additions: normalized schema **1.1** always includes `request`
(CSV request filters, `{}` for RSS); monitor schema **1.1** allows optional `geo`
and `observed_at` fields when the watcher uses `include_context=True`. The pure
diff and default watcher still return the six original fields. Historical
envelopes retain their original schema and remain readable. RSS cache keys are
versioned to keep timestamped payloads separate from older installations sharing
the database; this needs no table migration.

The local archive's on-disk table layout is versioned by `db_schema_version`
(stored inside the DB file). A layout change ships with automatic tolerance or
a clear `ArchiveError` telling the user to upgrade — silent misreads never. The
archived envelope payloads themselves follow the schemas above verbatim.

### 3. The CLI

Command names (`rss`, `csv`, `explore`, `watch`, `list`, `info`,
`history` (1.3.0), `suggest` (1.8.0)), their flags, and the pipe contract: **data goes to stdout,
banners/progress/errors go to stderr**; `watch` streams one NDJSON object per
line, `history` prints JSON. Removing a command or flag, or moving data off
stdout, is breaking. New commands/flags are minor.

### 4. The MCP server

The entry point (`trendspyg-mcp`), the nine tool names, and their parameters:
`get_trending_now`, `compare_trending`, `get_trend_changes`,
`list_supported_options`, `get_interest_over_time`,
`compare_interest_over_time` (1.1.0), `get_trending_full`,
`get_trending_history` (1.3.0), `suggest_keywords` (1.8.0). Tool result payloads follow the data schemas
above (`get_trending_history` returns a documented compact form).

1.8.0 is additive: the original 47 exports and all existing parameters/defaults
remain available; two root exports bring the total to 49. Lookup is separate
from Explore, and no text keyword is automatically interpreted as a topic.
No existing data-schema version changes in 1.8.0.

### 4b. The pytrends compatibility layer (1.9.0)

`trendspyg.compat`: the names `TrendReq`, `ResponseError`,
`TooManyRequestsError`, `CompatWarning`, the module paths
`trendspyg.compat.request` and `trendspyg.compat.exceptions`, `TrendReq`'s
public method names and argument names/defaults (pinned by
`tests/test_compat.py`), and the documented return shapes. Its contract is
pytrends 4.9.2's documented behavior with the differences listed in
`docs/MIGRATING_FROM_PYTRENDS.md`; serving more of pytrends' behavior (for
example `resolution="CITY"`) is a minor change. 1.9.0 is additive: the root
API stays at 49 names and no data-schema version changes.

1.9.0 also adds `engine` (last parameter, default `"browser"`) to the three
Explore download functions. `"browser"` keeps the previous behavior; `"auto"`
and `"http"` return the same shapes. Changing the default engine of an
existing function would change its documented behavior, so it is reserved for
a decision recorded in the changelog with evidence, not made silently.
`trendspyg.compat` is new, so its `engine` default is `"auto"` from the start.

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
