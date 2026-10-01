# From a Trends response to a defensible result

Choose the path by the question: RSS for current reporting leads and monitoring;
CSV for a larger Trending Now list with category/time filters; Explore for a
keyword study. The normalized RSS/CSV shape makes processing consistent, but
does not make their coverage or measurements interchangeable.

## Keep the observation and the question together

Save the full envelope before transforming it. `fetched_at` is the original
collection time; memory and disk cache hits preserve it. `started_at` on RSS
comes from the feed's publication timestamp. It is not proof of when an event
happened. A first archived appearance means "first observed here"; the archive
cannot recover periods when collection was off.

Normalized schema **1.1** adds `request`: CSV downloads record `hours`,
`category`, `active_only` and `sort_by`; RSS uses `{}` because its geography is
already in `geo` and it has no category/time filters. These are the requested
settings, not a claim that every upstream control was independently audited.
The downloader verifies category selection and, when requested, the active-only
switch before exporting; it raises `BrowserError` if a filter cannot be applied. `sort_by` does not control CSV
export order; sort the returned rows explicitly. Older archived schema-1.0
envelopes have no `request` field and remain readable.

`volume_min` / raw `traffic_min` is a bucket lower bound, with 0 also used for
unparseable input; keep the corresponding text field. `rank` is source row
position. A short RSS list is not an exhaustive popularity ranking. A dropped
item left that feed snapshot; it does not establish that interest ended.
Google explains Trending Now groupings, volume buckets and filters in its
[Trending Now guide](https://support.google.com/trends/answer/3076011?hl=en).

## Record now, ask about history later

```bash
trendspyg watch --geo US --interval 60 --archive --db trends.sqlite3 --context --quiet
trendspyg history --geo US --db trends.sqlite3 --quiet
```

The watcher archives every poll, even its initial baseline and polls with no
change events. `--context` adds `geo` and `observed_at` to NDJSON events.
In Python use `include_context=True` on `watch_google_trends_rss`.
Pure `diff_trends` stays clock-free and returns the six original fields.

MCP users can call `get_trending_now(geo="US", archive=true)` from the first
fetch, then `get_trending_history(geo="US")`. `compare_trending`,
`get_trend_changes` and `get_trending_full` also accept `archive=true`.
RSS cache hits do not add observations. If collection started with archiving
off, `get_trend_changes(geo="US", archive=true)` records a fresh baseline.
The database path can be set with `TRENDSPYG_DB` in the MCP host environment.

For recurring country jobs, pass `cache="disk", archive=True, normalize=True`
to `download_google_trends_rss_batch_async`, with `max_concurrent=3` or 5.
Repeated cached jobs retain their original observation times.

## Design a keyword study before interpreting its numbers

Google Trends uses sampled, normalized search interest. A 100 is a relative
peak, not 100 searches. Equal regional scores do not mean equal search counts.
Small samples can fluctuate, and zeros need care. See
[Google's data explanation](https://support.google.com/trends/answer/4365533?hl=en).

Inspect related queries for mixed intent: our coffee study included "coffee
table" near the top. A broad word can answer a different question from the one
you intended. Since 1.8.0, use `get_keyword_suggestions` to inspect topic
candidates before selecting one. A topic represents a concept across languages;
a search term matches the text you supply, as explained in
[Google's terms/topics guide](https://support.google.com/trends/answer/4359550?hl=en).
Record your term or selected topic ID and label, geo, timeframe, property and
fetch time. Avoid treating search interest as sales or market size.

```python
from trendspyg import get_keyword_suggestions, download_google_trends_comparison

for candidate in get_keyword_suggestions("apple"):
    print(candidate["mid"], candidate["title"], candidate["type"])

# After reviewing the candidates, choose these two meanings explicitly:
selected = {
    "/m/0k8z": "Apple — Technology company",
    "/m/014j1m": "Apple — Fruit",
}
env = download_google_trends_comparison(
    list(selected), geo="US", cache="disk", cookies="disk", archive=True
)
study = {"topics": selected, "comparison": env}  # save both labels and raw data
```

Lookup needs no Chrome; analyzing the selected IDs still uses Chrome. Lookup
results are matching candidates, not a popularity ranking or an exhaustive
catalog. `[]` means no candidates, not zero interest. The selected IDs remain
the keys in the comparison and archive, so keep their labels with your study.

Exclude `is_partial=True` points before comparing complete periods. Check
`is_empty` on a full Explore response; sparse isolated spikes also deserve
inspection. Use `download_google_trends_comparison` for 2–5 terms on one shared
scale. Separate single-keyword studies each have their own normalization.

Use `cache="disk"` for repeats and opt into `cookies="disk"` when keeping a
Google session cookie locally is appropriate. Explore has finite page-load,
transport and script timeouts, plus a 40–90s browser-work budget checked between
phases (44s with the MCP retry profile). This is not a whole-call deadline:
Chrome/driver discovery, first-time downloads and cleanup add time. A hard
`RateLimitError` means stop and allow a long cooldown, rather than loop.

## Related queries are leads, not facts

Rising related queries can include searches unrelated to your keyword. On
2026-10-02, Google's rising list for "coffee" in the US over the past 12
months began "sports scores today", "home workout routines", "pet care tips".
The same entries came back through trendspyg's headless session, a visible
browser with a long-established profile on the same machine, and pytrends'
direct requests, so they are the data Google served, not a parsing error. It is not yet established whether Google
serves such entries to everyone or only to machines it has flagged; its request
for that session carried `userType: USER_TYPE_SCRAPER`. Treat related queries,
especially "Breakout" entries, as leads: explore a surprising one directly
before reporting it.

## Run a finished workflow

From a repository checkout with the library installed:

```bash
pip install trendspyg[analysis]
python examples/journalist_workflow.py --geo US --output-dir reporting_brief
python examples/data_analysis.py --geo US --output-dir trends_analysis
```

The first saves a source-linked Markdown brief and original snapshot. Linked
articles are reporting leads, not automatic verification; investigate their
primary evidence and whether outlets repeat the same underlying source.

The second saves a CSV with provenance, the full JSON, a SQLite archive, and
changes from the previous observation. Run it later, after the cache expires,
to build a history. It clearly reports when there is only one observation.

```bash
pip install matplotlib
python examples/keyword_study.py --keyword coffee --geo US --output-dir coffee_study
```

The study performs one full Explore query and saves a chart, complete-period
CSV, descriptive summary, original response and archive. Identical repeats use
the disk cache. No result from these examples is a causal inference or forecast.

## Upgrading existing workflows

1.8.0 adds an optional lookup function, TypedDict, CLI command and MCP tool.
Existing functions, argument names/defaults, CLI commands/options and data
schemas stay unchanged. Topic IDs are selected explicitly; existing text
keywords are not converted to topics automatically. No new dependency is needed.

The 1.7.0 corrections can change what an existing workflow observes:

| Area | What to account for |
|---|---|
| CSV filters | Category and active-only selection is verified. A failed filter raises `BrowserError`; code that relied on an unfiltered fallback now gets an error. |
| Cached RSS | `fetched_at` retains the original observation time. Repeated cached reads are not fresh observations. |
| Normalized output | Schema 1.1 adds `request`; strict schema validators must allow the new field/version. Raw RSS output stays a list by default. |
| Monitoring | Schema constant is 1.1. Default events retain their six fields; `geo`/`observed_at` require the new context option. |
| Explore failures | Finite browser-work timeouts can end slow attempts earlier; failures use library exceptions. Large retry settings do not guarantee an equally large time budget. |
| Example scripts | Reporting and analysis examples now create reusable files and preserve provenance; scripts that consume their printed text or output filenames should review the revised examples. |

Existing archives remain readable, and storing history stays opt-in. Treat new
metadata and error handling as deliberate corrections; test any strict consumer
of exact JSON keys, schema versions or example output before upgrading it.
