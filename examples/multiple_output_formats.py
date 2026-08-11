#!/usr/bin/env python3
"""
Multiple Output Formats Example

Demonstrates how to get trend data in different formats
(dict, JSON, CSV, DataFrame) based on your needs.
"""

import json

from trendspyg import download_google_trends_rss


def main():
    print("=" * 60)
    print("EXAMPLE 1: Dictionary Format (default)")
    print("=" * 60)

    # Default format - list of dictionaries
    trends_dict = download_google_trends_rss("US", output_format="dict")
    print(f"Type: {type(trends_dict)}")
    print(f"First trend: {trends_dict[0]['trend']}")
    print(f"Keys: {list(trends_dict[0].keys())}\n")

    print("=" * 60)
    print("EXAMPLE 2: JSON Format")
    print("=" * 60)

    # JSON string - good for APIs and file storage
    trends_json = download_google_trends_rss("US", output_format="json")
    print(f"Type: {type(trends_json)}")
    print(f"First 200 chars: {trends_json[:200]}...")

    # Can parse back to dict
    parsed = json.loads(trends_json)
    print(f"Parsed back to list of {len(parsed)} items\n")

    print("=" * 60)
    print("EXAMPLE 3: CSV Format")
    print("=" * 60)

    # CSV string - good for spreadsheets
    trends_csv = download_google_trends_rss("US", output_format="csv")
    print(f"Type: {type(trends_csv)}")
    lines = trends_csv.strip().split("\n")
    print(f"Lines: {len(lines)}")
    print("Header:", lines[0])
    print("First row:", lines[1][:100], "...\n")

    print("=" * 60)
    print("EXAMPLE 4: DataFrame Format")
    print("=" * 60)

    # pandas DataFrame - best for data analysis
    try:
        import pandas as pd  # noqa: F401  (probe: the dataframe format needs pandas)

        trends_df = download_google_trends_rss("US", output_format="dataframe")
        print(f"Type: {type(trends_df)}")
        print(f"Shape: {trends_df.shape}")
        print("\nColumns:", trends_df.columns.tolist())
        print("\nFirst 3 rows:")
        print(trends_df[["trend", "traffic", "article_count"]].head(3))
    except ImportError:
        print("pandas not installed - skipping DataFrame example")
        print("Install with: pip install trendspyg[analysis]")


if __name__ == "__main__":
    main()
