#!/usr/bin/env python3
"""
Normalized Output Example (v0.5.0+)

Demonstrates `normalize=True` - one unified, JSON-native schema that is
identical for the RSS and CSV paths. Ideal for AI agents, pipelines, and
anywhere you want a predictable, JSON-safe shape instead of two different ones.
"""

import json

from trendspyg import download_google_trends_rss


def main():
    print("Fetching normalized trends for US...\n")

    # normalize=True returns a NormalizedEnvelope instead of a raw trend list.
    env = download_google_trends_rss(geo='US', normalize=True)

    # The envelope carries provenance alongside the data.
    print(f"schema_version : {env['schema_version']}")
    print(f"source         : {env['source']}")
    print(f"geo            : {env['geo']}")
    print(f"fetched_at     : {env['fetched_at']}")
    print(f"count          : {env['count']}\n")

    # Every trend has the same fixed, JSON-safe shape - on both paths.
    for trend in env['trends'][:5]:
        print(f"#{trend['rank']:>2}  {trend['keyword']}")
        print(f"     volume : {trend['volume_text']}  (volume_min={trend['volume_min']})")
        print(f"     active : {trend['is_active']}  started_at={trend['started_at']}")
        if trend['news']:
            print(f"     news   : {trend['news'][0]['headline']}")
        print()

    # The whole envelope is JSON-serializable as-is - no datetime objects, no NaN.
    print("First trend as JSON (always serializable):")
    print(json.dumps(env['trends'][0], indent=2)[:400] + " ...")

    # The same `normalize=True` works everywhere:
    #   download_google_trends_csv(geo='US', normalize=True)        -> envelope
    #   download_google_trends_rss_batch(['US', 'GB'], normalize=True)  -> {geo: envelope}
    # On the CLI:
    #   trendspyg rss --geo US --normalize


if __name__ == '__main__':
    main()
