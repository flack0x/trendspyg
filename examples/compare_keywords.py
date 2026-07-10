#!/usr/bin/env python3
"""
Multi-Keyword Comparison Example (v1.1.0+)

Compare 2-5 keywords on ONE shared 0-100 scale — the pytrends `kw_list` use
case. Google scales single-keyword series independently (each keyword's own
peak = 100), so fetching terms one at a time does NOT produce comparable
numbers. A comparison call loads Google's own comparison view: one browser
load, directly comparable values.

Requires Chrome; rate-limit sensitive (~10-90s per call, may retry).
"""

import json

from trendspyg import download_google_trends_comparison
from trendspyg.exceptions import RateLimitError


def main():
    keywords = ["bitcoin", "ethereum", "solana"]

    print(f"Comparing {', '.join(keywords)} (US, past 12 months)...\n")
    try:
        env = download_google_trends_comparison(keywords, geo="US")
    except RateLimitError as exc:
        # Google throttles the Explore endpoints — back off and try again later.
        print(f"Rate-limited by Google: {exc}")
        return

    # Google's per-keyword averages, all on the same relative scale.
    print("Average interest (shared 0-100 scale):")
    for kw, avg in sorted(env["averages"].items(), key=lambda kv: -kv[1]):
        print(f"  {kw:<10} {avg:>3}  {'#' * avg}")

    winner = max(env["averages"], key=env["averages"].get)
    print(f"\n'{winner}' dominates US search interest among the compared terms.")

    print(f"\nMost recent {min(3, env['count'])} points:")
    for point in env["interest_over_time"][-3:]:
        flag = "  (partial)" if point["is_partial"] else ""
        values = "  ".join(f"{kw}={v}" for kw, v in point["values"].items())
        print(f"  {point['date'][:10]}  {values}{flag}")

    regions = env["interest_by_region"][:5]
    if regions:
        print("\nWho wins where (top regions):")
        for r in regions:
            print(f"  {r['geo_name']:<15} top: {r['top_keyword']}  {r['values']}")

    # The whole envelope is JSON-serializable as-is.
    print("\nEnvelope is JSON-safe:", bool(json.dumps(env)))

    # pytrends-style table instead (one column per keyword):
    #   df = download_google_trends_comparison(keywords, output_format="dataframe")
    # On the CLI:
    #   trendspyg explore -k bitcoin -k ethereum --quiet | jq .averages


if __name__ == "__main__":
    main()
