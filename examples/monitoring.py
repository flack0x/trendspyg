#!/usr/bin/env python3
"""Real-time monitoring example — stream Google Trends changes (new in 0.7.0).

Monitoring is built on the fast RSS path, so it is safe to poll continuously
(the CSV and Explore paths are not). Each poll is diffed against the previous
snapshot and every change is yielded as a ``TrendChange``.

Run:  python examples/monitoring.py
Stop: Ctrl-C
"""

from trendspyg import diff_trends, download_google_trends_rss, watch_google_trends_rss


def live_stream() -> None:
    """Print each change between consecutive RSS snapshots as it happens."""
    print("Watching US trends every 60s (Ctrl-C to stop)...\n")
    try:
        for change in watch_google_trends_rss(
            geo="US",
            interval=60,
            events=["new", "volume_up"],  # only brand-new or surging trends
            # min_volume=20000,                 # optional: require a volume floor
            # keywords=["bitcoin", "nvidia"],   # optional: a watchlist (substring match)
            # webhook="https://example.com/hook",  # optional: POST each change as JSON
        ):
            label = change["event"].upper()
            print(
                f"[{label:11}] {change['keyword']!r}  "
                f"rank={change['rank']}  volume_min={change['volume_min']}"
            )
    except KeyboardInterrupt:
        print("\nStopped.")


def diff_two_snapshots() -> None:
    """Manage snapshots yourself and diff them — pure, offline, no polling loop."""
    old = download_google_trends_rss(geo="US", cache=False)
    # ... some time later ...
    new = download_google_trends_rss(geo="US", cache=False)

    for change in diff_trends(old, new):
        # TrendChange: {event, keyword, rank, prev_rank, volume_min, prev_volume_min}
        print(change)


if __name__ == "__main__":
    live_stream()
