#!/usr/bin/env python3
"""Create a source-linked reporting brief and keep its original RSS snapshot.

Run: python examples/journalist_workflow.py --geo US --output-dir reporting_brief
These are reporting leads; inclusion in the feed does not verify a claim.
"""

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

from trendspyg import download_google_trends_rss


def main(geo="US", output_dir="reporting_brief"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    started = perf_counter()
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    env = download_google_trends_rss(geo=geo, normalize=True)
    (folder / "snapshot.json").write_text(
        json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        f"# Reporting leads: {env['geo']}",
        f"\nObserved: {env['fetched_at']} (cached reads retain this time).",
        f"Feed coverage: {env['count']} topics; this is not all searches or all news.",
        "Volumes are lower bounds; feed position is not a popularity ranking.",
        "Linked coverage is context, not independent verification of a claim.",
    ]
    # Rank remains the original feed position; explicitly sort this brief by volume.
    leads = sorted(env["trends"], key=lambda trend: trend["volume_min"], reverse=True)[:5]
    for lead in leads:
        lines.extend(
            [
                f"\n## {lead['keyword']}",
                f"Volume lower bound: {lead['volume_min']:,}; feed position: {lead['rank']}.",
                f"Feed publication time: {lead['started_at']} (not the event's start time).",
            ]
        )
        for article in lead["news"]:
            lines.append(f"- [{article['headline']}]({article['url']}) — {article['source']}")
        if not lead["news"]:
            lines.append("No linked coverage in this snapshot; investigate separately.")
        lines.append(
            "\nReporting task: read the linked stories, trace their primary evidence, "
            "check whether they repeat the same source, and verify dates and claims."
        )
    brief = "\n".join(lines) + "\n"
    (folder / "brief.md").write_text(brief, encoding="utf-8")
    print(brief)
    print(f"Saved brief.md and snapshot.json in {folder}; elapsed {perf_counter() - started:.2f}s.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geo", default="US")
    parser.add_argument("--output-dir", default="reporting_brief")
    args = parser.parse_args()
    main(args.geo, args.output_dir)
