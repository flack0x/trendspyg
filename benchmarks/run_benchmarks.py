#!/usr/bin/env python
"""trendspyg performance benchmarks.

Offline microbenchmarks run by default (no network, no browser) and measure the
library's own overhead: RSS parsing, normalization, and snapshot diffing.
Live benchmarks are opt-in flags that hit Google for end-to-end timings.

Usage:
    python benchmarks/run_benchmarks.py                 # offline only, safe anywhere
    python benchmarks/run_benchmarks.py --live          # + live RSS (fresh + cache hit)
    python benchmarks/run_benchmarks.py --live-csv      # + live CSV export (Chrome, ~10-15s/run)
    python benchmarks/run_benchmarks.py --live-explore  # + live Explore (Chrome, 10-90s)

Results are recorded per release in benchmarks/README.md.

NOTE: the offline benchmarks intentionally call two *internal* helpers
(``rss_downloader._parse_rss_xml``, ``normalize.normalize_rss``) to isolate
parsing from network time. Internals are NOT covered by the stability contract
(see STABILITY.md); this script lives in the repo and moves with them.
"""

import argparse
import platform
import shutil
import statistics
import sys
import tempfile
import time
import timeit
from typing import Any, Callable, Dict, List, NamedTuple, Tuple

import trendspyg
from trendspyg import (
    clear_rss_cache,
    diff_trends,
    download_google_trends_csv,
    download_google_trends_interest_over_time,
    download_google_trends_rss,
    filter_changes,
)
from trendspyg.normalize import normalize_rss  # internal: parse-only timing
from trendspyg.rss_downloader import _parse_rss_xml  # internal: parse-only timing

FEED_ITEMS = 20  # matches a real Trending Now RSS feed (~10-20 items)


class Result(NamedTuple):
    label: str
    runs: int
    median: float
    best: float
    worst: float


# ---------------------------------------------------------------------------
# Synthetic inputs (offline)
# ---------------------------------------------------------------------------


def synthetic_feed(n_items: int = FEED_ITEMS) -> bytes:
    """A realistic Trending Now RSS feed: n items, image + 2 news articles each."""
    items = []
    for i in range(n_items):
        items.append(
            """    <item>
      <title>topic {i}</title>
      <ht:approx_traffic>{traffic}00K+</ht:approx_traffic>
      <pubDate>Mon, 01 Jan 2024 {hour:02d}:00:00 +0000</pubDate>
      <ht:picture>https://example.com/img{i}.jpg</ht:picture>
      <ht:picture_source>Source {i}</ht:picture_source>
      <ht:news_item>
        <ht:news_item_title>Headline A about topic {i}</ht:news_item_title>
        <ht:news_item_url>https://example.com/a{i}</ht:news_item_url>
        <ht:news_item_source>Outlet A</ht:news_item_source>
        <ht:news_item_picture>https://example.com/na{i}.jpg</ht:news_item_picture>
      </ht:news_item>
      <ht:news_item>
        <ht:news_item_title>Headline B about topic {i}</ht:news_item_title>
        <ht:news_item_url>https://example.com/b{i}</ht:news_item_url>
        <ht:news_item_source>Outlet B</ht:news_item_source>
      </ht:news_item>
    </item>""".format(
                i=i, traffic=i % 9 + 1, hour=i % 24
            )
        )
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">\n'
        "  <channel>\n"
        "    <title>Trending Now - US</title>\n" + "\n".join(items) + "\n  </channel>\n</rss>"
    )
    return feed.encode("utf-8")


def synthetic_snapshots(n: int = FEED_ITEMS) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Two RSS-shaped snapshots with drops, additions, rank shifts and volume bumps."""
    old = [{"trend": "topic {}".format(i), "traffic_min": (i % 9 + 1) * 100_000} for i in range(n)]
    kept = [dict(t) for t in old[:-3]]
    kept = kept[5:] + kept[:5]  # rank shifts
    for j, t in enumerate(kept):
        if j % 4 == 0:
            t["traffic_min"] = int(t["traffic_min"]) * 2  # volume_up events
    new = kept + [{"trend": "topic {}".format(i), "traffic_min": 200_000} for i in range(n, n + 3)]
    return old, new


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def bench_micro(label: str, func: Callable[[], Any], number: int, repeats: int = 5) -> Result:
    """Time ``func`` with timeit: ``repeats`` batches of ``number`` calls each."""
    raw = timeit.Timer(func).repeat(repeat=repeats, number=number)
    per_call = sorted(t / number for t in raw)
    return Result(label, number * repeats, statistics.median(per_call), per_call[0], per_call[-1])


def bench_live(label: str, func: Callable[[], Any], repeats: int, pause: float = 1.0) -> Result:
    """Time ``func`` end-to-end ``repeats`` times with a polite pause between runs."""
    times = []
    for i in range(repeats):
        start = time.perf_counter()
        func()
        times.append(time.perf_counter() - start)
        if pause and i < repeats - 1:
            time.sleep(pause)
    times.sort()
    return Result(label, repeats, statistics.median(times), times[0], times[-1])


def fmt_seconds(seconds: float) -> str:
    if seconds < 1e-3:
        return "{:.1f} us".format(seconds * 1e6)
    if seconds < 1.0:
        return "{:.2f} ms".format(seconds * 1e3)
    return "{:.2f} s".format(seconds)


def print_table(results: List[Result]) -> None:
    header = ("Benchmark", "Runs", "Median", "Best", "Worst")
    rows = [
        (r.label, str(r.runs), fmt_seconds(r.median), fmt_seconds(r.best), fmt_seconds(r.worst))
        for r in results
    ]
    widths = [max(len(row[c]) for row in [header] + rows) for c in range(len(header))]
    line = "  ".join("-" * w for w in widths)
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)))
    print(line)
    for row in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(row, widths)))


# ---------------------------------------------------------------------------
# Benchmark suites
# ---------------------------------------------------------------------------


def run_offline() -> List[Result]:
    feed = synthetic_feed()
    parsed = _parse_rss_xml(
        feed, geo="US", include_images=True, include_articles=True, max_articles_per_trend=5
    )
    old, new = synthetic_snapshots()
    changes = diff_trends(old, new)

    return [
        bench_micro(
            "parse RSS XML ({} trends)".format(FEED_ITEMS),
            lambda: _parse_rss_xml(
                feed,
                geo="US",
                include_images=True,
                include_articles=True,
                max_articles_per_trend=5,
            ),
            number=200,
        ),
        bench_micro(
            "normalize_rss ({} trends)".format(FEED_ITEMS),
            lambda: normalize_rss(parsed, "US"),
            number=200,
        ),
        bench_micro(
            "diff_trends ({} vs {} trends)".format(FEED_ITEMS, FEED_ITEMS),
            lambda: diff_trends(old, new),
            number=2000,
        ),
        bench_micro(
            "filter_changes ({} changes)".format(len(changes)),
            lambda: filter_changes(
                changes, min_volume=150_000, events=("new", "volume_up"), keywords=["topic"]
            ),
            number=2000,
        ),
    ]


def run_live_rss(repeats: int) -> List[Result]:
    results = []

    def fresh() -> None:
        download_google_trends_rss("US", cache=False)

    results.append(bench_live("RSS end-to-end, fresh (US)", fresh, repeats=repeats))

    clear_rss_cache()
    download_google_trends_rss("US", cache=True)  # warm the cache once
    results.append(
        bench_micro(
            "RSS cache hit (US)",
            lambda: download_google_trends_rss("US", cache=True),
            number=1000,
        )
    )
    return results


def run_live_csv() -> List[Result]:
    def once() -> None:
        download_dir = tempfile.mkdtemp(prefix="trendspyg_bench_")
        try:
            download_google_trends_csv(geo="US", output_format="csv", download_dir=download_dir)
        finally:
            shutil.rmtree(download_dir, ignore_errors=True)

    return [bench_live("CSV export end-to-end (US, Chrome)", once, repeats=2, pause=2.0)]


def run_live_explore() -> List[Result]:
    def once() -> None:
        download_google_trends_interest_over_time("bitcoin", output_format="dict")

    return [bench_live("Explore interest over time (Chrome)", once, repeats=1, pause=0.0)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="run live RSS benchmarks (network)")
    parser.add_argument(
        "--live-csv", action="store_true", help="run the live CSV benchmark (Chrome, ~10-15s/run)"
    )
    parser.add_argument(
        "--live-explore",
        action="store_true",
        help="run the live Explore benchmark (Chrome, 10-90s)",
    )
    parser.add_argument(
        "--repeats", type=int, default=5, help="repeats for live RSS runs (default 5)"
    )
    args = parser.parse_args()

    print(
        "trendspyg {} | Python {} | {}".format(
            trendspyg.__version__, platform.python_version(), platform.platform()
        )
    )
    print()

    results = run_offline()
    if args.live:
        results.extend(run_live_rss(args.repeats))
    if args.live_csv:
        results.extend(run_live_csv())
    if args.live_explore:
        results.extend(run_live_explore())

    print_table(results)
    if not (args.live or args.live_csv or args.live_explore):
        print()
        print("Offline suite only. Add --live / --live-csv / --live-explore for end-to-end runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
