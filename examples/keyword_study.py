#!/usr/bin/env python3
"""One keyword study with query context, complete periods, an archive and a chart.

Install: pip install trendspyg[analysis] matplotlib
Run: python examples/keyword_study.py --keyword coffee --output-dir coffee_study
Requires Chrome. One fresh Explore call; repeats use disk cache and a saved cookie jar.
"""

import argparse
import json
import sys
from pathlib import Path

from trendspyg import download_google_trends_explore


def main(keyword="coffee", geo="US", output_dir="keyword_study"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    env = download_google_trends_explore(
        keyword,
        geo=geo,
        timeframe="today 12-m",
        cache="disk",
        cookies="disk",
        archive=True,
        db_path=str(folder / "history.sqlite3"),
    )
    (folder / "snapshot.json").write_text(
        json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    frame = pd.DataFrame(env["interest_over_time"], columns=["date", "value", "is_partial"])
    complete = frame.loc[frame["is_partial"] == False].copy()  # noqa: E712
    complete.to_csv(folder / "complete_periods.csv", index=False)
    summary = {
        "keyword": env["keyword"],
        "geo": env["geo"],
        "timeframe": env["timeframe"],
        "gprop": env["gprop"],
        "fetched_at": env["fetched_at"],
        "complete_periods": len(complete),
        "excluded_partial_periods": len(frame) - len(complete),
        "is_empty": env["is_empty"],
        "recent_four_mean": None,
        "preceding_four_mean": None,
        "interpretation": (
            "One sampled relative-interest series; not search counts, sales or a forecast."
        ),
    }
    if not env["is_empty"] and len(complete) >= 8:
        summary["recent_four_mean"] = float(complete["value"].iloc[-4:].mean())
        summary["preceding_four_mean"] = float(complete["value"].iloc[-8:-4].mean())
    (folder / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(pd.to_datetime(complete["date"], utc=True), complete["value"])
    ax.set(
        title=f"{keyword} | {geo} | complete periods",
        ylabel="Relative interest (0-100)",
        ylim=(0, 100),
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(folder / "interest.png", dpi=160)
    plt.close(fig)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(
        "Inspect related queries before interpreting the series: "
        "an ambiguous term mixes intentions."
    )
    print("Top related queries:", ", ".join(q["query"] for q in env["related_queries"]["top"][:10]))
    if env["is_empty"]:
        print("Google returned no non-zero points; do not interpret this as proof of no searches.")
    print(
        "Compare terms with download_google_trends_comparison; "
        "separate studies have separate scales."
    )
    print(f"Saved snapshot, summary, complete-period CSV, chart and local archive in {folder}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyword", default="coffee")
    parser.add_argument("--geo", default="US")
    parser.add_argument("--output-dir", default="keyword_study")
    args = parser.parse_args()
    main(args.keyword, args.geo, args.output_dir)
