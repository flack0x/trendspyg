#!/usr/bin/env python3
"""Export a reproducible RSS dataset and compare it with your previous observation.

Install: pip install trendspyg[analysis]
Run: python examples/data_analysis.py --geo US --output-dir trends_analysis
Run again later to accumulate history. No historical data is backfilled.
"""

import argparse
import json
import sys
from pathlib import Path

from trendspyg import diff_trends, download_google_trends_rss, read_archive


def main(geo="US", output_dir="trends_analysis"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        import pandas as pd
    except ImportError:
        print("Install with: pip install trendspyg[analysis]")
        return

    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    db = str(folder / "history.sqlite3")
    env = download_google_trends_rss(
        geo=geo, normalize=True, cache="disk", archive=True, db_path=db
    )
    rows = [
        {
            "fetched_at": env["fetched_at"],
            "geo": env["geo"],
            "source": env["source"],
            "keyword": trend["keyword"],
            "feed_position": trend["rank"],
            "volume_min": trend["volume_min"],
            "volume_text": trend["volume_text"],
            "published_at": trend["started_at"],
            "article_count": len(trend["news"]),
        }
        for trend in env["trends"]
    ]
    columns = [
        "fetched_at",
        "geo",
        "source",
        "keyword",
        "feed_position",
        "volume_min",
        "volume_text",
        "published_at",
        "article_count",
    ]
    frame = pd.DataFrame(rows, columns=columns).sort_values("volume_min", ascending=False)
    frame.to_csv(folder / "trends.csv", index=False, encoding="utf-8")
    (folder / "snapshot.json").write_text(
        json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    history = read_archive(geo=env["geo"], source="rss", limit=2, db_path=db)
    changes = diff_trends(history[1]["trends"], history[0]["trends"]) if len(history) >= 2 else []
    (folder / "changes.json").write_text(
        json.dumps(changes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Observed {len(frame)} topics in {env['geo']} at {env['fetched_at']}.")
    print(frame[["keyword", "volume_min", "article_count"]].head(10).to_string(index=False))
    print("volume_min is a lower bound; feed coverage is limited and varies by region.")
    if len(history) < 2:
        print("First observation: no earlier snapshot yet. Run again after the 5-minute cache TTL.")
    else:
        print(
            f"Comparing {history[1]['fetched_at']} to {history[0]['fetched_at']}: "
            f"{len(changes)} changes."
        )
        print("A dropped topic left the feed; this does not establish that interest ended.")
    print(f"Saved trends.csv, snapshot.json, changes.json and history.sqlite3 in {folder}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geo", default="US")
    parser.add_argument("--output-dir", default="trends_analysis")
    args = parser.parse_args()
    main(args.geo, args.output_dir)
