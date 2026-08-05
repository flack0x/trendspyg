"""Archive trends while fetching, then query the history (new in 1.3.0).

Google's trending feed is ephemeral — once it updates, "what was trending last
Tuesday" is gone, and no API sells it. Opt in to archiving and every fetch
records a snapshot to one local SQLite file; over time you own a dataset that
cannot be bought.

Run:  python examples/archive_history.py
"""

from trendspyg import (
    download_google_trends_rss,
    get_archive_stats,
    get_keyword_history,
    read_archive,
)

# --- 1. Record a snapshot while fetching (opt-in, one kwarg) ---------------
# Schedule this (cron / Task Scheduler / `trendspyg rss --archive` in a loop)
# and the archive grows on its own.
trends = download_google_trends_rss(geo="US", archive=True)
print(f"Fetched {len(trends)} trends (snapshot archived)")

# A disk-backed cache persists across processes too — repeated CLI runs or MCP
# server restarts within the TTL skip the network entirely:
download_google_trends_rss(geo="US", cache="disk")

# --- 2. What WAS trending? -------------------------------------------------
snapshots = read_archive(geo="US", limit=5)  # newest first
for env in snapshots:
    keywords = ", ".join(t["keyword"] for t in env["trends"][:5])
    print(f"{env['fetched_at']}  ({env['source']}, {env['count']} trends)  {keywords}")

# --- 3. When did a keyword first trend, and how did it move? ---------------
first_keyword = trends[0]["trend"]
history = get_keyword_history(first_keyword)  # oldest first
if history:
    first = history[0]
    print(f"'{first_keyword}' first archived {first['fetched_at']} at rank {first['rank']}")

# --- 4. Housekeeping -------------------------------------------------------
stats = get_archive_stats()
print(
    f"Archive: {stats['snapshot_count']} snapshots, "
    f"{stats['db_size_bytes'] / 1024:.0f} KB at {stats['db_path']}"
)
# Reclaim space explicitly when you want it back:
#   from trendspyg import prune_archive
#   prune_archive("2026-01-01")
