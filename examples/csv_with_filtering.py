#!/usr/bin/env python3
"""
CSV Download with Filtering Example

This example shows how to download comprehensive trend data
with time period and category filtering.

Note: Requires Chrome browser installed.
"""

from trendspyg import download_google_trends_csv


def main():
    print("Downloading California sports trends from past 7 days...\n")

    # Download sports trends from California, past week
    df = download_google_trends_csv(
        geo="US-CA",  # California
        hours=168,  # 7 days (24 * 7)
        category="sports",  # Sports category only
        active_only=True,  # Only rising trends
        output_format="dataframe",
    )

    print(f"Downloaded {len(df)} sports trends\n")

    # Show top 10 by search volume
    print("Top 10 California sports trends:")
    print(df[["Trends", "Search volume"]].head(10).to_string(index=False))

    print("\n" + "=" * 50)
    print("Breakdown by sport:")

    # Analyze trend breakdown
    for idx, row in df.head(5).iterrows():
        print(f"\n{row['Trends']} ({row['Search volume']}):")
        if row["Trend breakdown"]:
            breakdown = row["Trend breakdown"].split(",")[:3]
            for term in breakdown:
                print(f"  - {term.strip()}")


if __name__ == "__main__":
    main()
