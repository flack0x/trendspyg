#!/usr/bin/env python3
"""
Basic RSS Usage Example

This example demonstrates the simplest way to get trending topics
from Google Trends using the RSS feed.
"""

from trendspyg import download_google_trends_rss


def main():
    print("Fetching trending topics from US...\n")

    # Get trending topics for United States
    trends = download_google_trends_rss(geo="US")

    print(f"Found {len(trends)} trending topics:\n")

    # Display first 5 trends
    for i, trend in enumerate(trends[:5], 1):
        print(f"{i}. {trend['trend']}")
        print(f"   Traffic: {trend['traffic']}")
        print(f"   Published: {trend['published']}")

        # Show first news article if available
        if trend.get("news_articles"):
            article = trend["news_articles"][0]
            print(f"   Top headline: {article['headline']}")
            print(f"   Source: {article['source']}")

        print()


if __name__ == "__main__":
    main()
