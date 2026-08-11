#!/usr/bin/env python3
"""
Data Analysis Example

Shows how to use trendspyg with pandas for data analysis.
Demonstrates filtering, aggregation, and visualization potential.
"""

from trendspyg import download_google_trends_rss


def main():
    try:
        import pandas as pd
    except ImportError:
        print("This example requires pandas.")
        print("Install with: pip install trendspyg[analysis]")
        return

    print("Fetching trends data for analysis...\n")

    # Get trends as DataFrame
    df = download_google_trends_rss("US", output_format="dataframe")

    print("=" * 70)
    print("DATASET OVERVIEW")
    print("=" * 70)
    print(f"\nRows: {len(df)}")
    print(f"Columns: {len(df.columns)}")
    print("\nColumn names:")
    for col in df.columns:
        print(f"  - {col}")

    print("\n" + "=" * 70)
    print("DATA EXPLORATION")
    print("=" * 70)

    # Traffic analysis
    print("\nTraffic Distribution:")
    print(df["traffic"].value_counts())

    # Article coverage analysis
    if "article_count" in df.columns:
        print("\nNews Coverage Analysis:")
        print(f"  Average articles per trend: {df['article_count'].mean():.1f}")
        print(f"  Max articles for a trend: {df['article_count'].max()}")
        print(f"  Trends with 3+ articles: {(df['article_count'] >= 3).sum()}")

    print("\n" + "=" * 70)
    print("HIGH TRAFFIC TRENDS")
    print("=" * 70)

    # Filter high traffic trends
    # Extract numeric traffic (remove '+' and convert)
    df["traffic_numeric"] = df["traffic"].str.replace("+", "").str.replace(",", "").astype(float)
    high_traffic = df[df["traffic_numeric"] >= 200].sort_values("traffic_numeric", ascending=False)

    print(f"\nFound {len(high_traffic)} trends with 200+ searches:\n")
    if len(high_traffic) > 0:
        for idx, row in high_traffic.head(5).iterrows():
            print(f"{row['trend']:30} {row['traffic']:>10} searches")
            if pd.notna(row.get("top_article_headline")):
                print(f"  → {row['top_article_headline'][:60]}...")

    print("\n" + "=" * 70)
    print("EXPORT OPTIONS")
    print("=" * 70)

    # Export examples
    print("\nSave to CSV:")
    csv_path = "us_trends.csv"
    df.to_csv(csv_path, index=False)
    print(f"  ✓ Saved to {csv_path}")

    print("\nSave to JSON:")
    json_path = "us_trends.json"
    df.to_json(json_path, orient="records", indent=2)
    print(f"  ✓ Saved to {json_path}")

    print("\nSave to Excel (if openpyxl installed):")
    try:
        excel_path = "us_trends.xlsx"
        df.to_excel(excel_path, index=False)
        print(f"  ✓ Saved to {excel_path}")
    except ImportError:
        print("  ! Install openpyxl for Excel export: pip install openpyxl")

    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    print("\n💡 Next steps:")
    print("  - Combine with historical data for time-series analysis")
    print("  - Compare trends across different regions")
    print("  - Build dashboards with visualization libraries")
    print("  - Set up automated monitoring and alerts")


if __name__ == "__main__":
    main()
