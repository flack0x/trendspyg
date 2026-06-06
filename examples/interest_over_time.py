#!/usr/bin/env python3
"""
Interest Over Time / Explore Example (v0.6.0+)

Demonstrates the Explore path — keyword analysis over time, the data the
archived pytrends was most used for. This drives a real (headless) Chrome
browser and is rate-limit sensitive (~10-90s per call, may retry). Use it for
analysis, not high-frequency polling — use the RSS path for fast real-time checks.

Requires Chrome (same as the CSV path).
"""

import json

from trendspyg import (
    download_google_trends_interest_over_time,
    download_google_trends_explore,
)
from trendspyg.exceptions import RateLimitError


def main():
    keyword = "bitcoin"

    print(f"Interest over time for '{keyword}' (US, past 12 months)...\n")
    try:
        series = download_google_trends_interest_over_time(
            keyword, geo="US", timeframe="today 12-m"
        )
    except RateLimitError as exc:
        # Google throttles the Explore endpoints — back off and try again later.
        print(f"Rate-limited by Google: {exc}")
        return

    print(f"Got {len(series)} points. Most recent 5:")
    for point in series[-5:]:
        flag = "  (partial)" if point["is_partial"] else ""
        print(f"  {point['date'][:10]}  value={point['value']:>3}{flag}")

    peak = max(series, key=lambda p: p["value"])
    print(f"\nPeak interest: {peak['value']} on {peak['date'][:10]}\n")

    # The full Explore picture in a single browser load.
    print(f"Full Explore envelope for '{keyword}'...\n")
    env = download_google_trends_explore(keyword, geo="US")

    print(f"schema_version : {env['schema_version']}")
    print(f"timeframe      : {env['timeframe']}")
    print(f"count          : {env['count']} interest-over-time points")

    rising = env["related_queries"]["rising"][:3]
    if rising:
        print("\nRising related queries:")
        for q in rising:
            print(f"  {q['query']}  ({q['formatted_value']})")

    regions = env["interest_by_region"][:3]
    if regions:
        print("\nTop regions:")
        for r in regions:
            print(f"  {r['geo_name']} ({r['geo_code']}): {r['value']}")

    # The whole envelope is JSON-serializable as-is — no datetime objects, no NaN.
    print("\nEnvelope is JSON-safe:", bool(json.dumps(env)))

    # On the CLI:
    #   trendspyg explore --keyword bitcoin
    #   trendspyg explore -k bitcoin --full --quiet | jq .


if __name__ == "__main__":
    main()
