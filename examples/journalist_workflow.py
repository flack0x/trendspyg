#!/usr/bin/env python3
"""
Journalist Workflow Example

Real-world example showing how a journalist might use trendspyg
to quickly validate breaking news trends with credible sources.
"""

from datetime import datetime

from trendspyg import download_google_trends_rss


def main():
    print("=" * 70)
    print("JOURNALIST WORKFLOW: Trend Validation with Sources")
    print("=" * 70)
    print()

    # Get current trending topics
    print("Fetching latest trending topics...")
    trends = download_google_trends_rss("US")

    print(f"Found {len(trends)} trending topics at {datetime.now().strftime('%H:%M:%S')}")
    print()

    # Analyze top 3 trends for story potential
    for i, trend in enumerate(trends[:3], 1):
        print("=" * 70)
        print(f"TREND #{i}: {trend['trend'].upper()}")
        print("=" * 70)

        # Traffic analysis
        print(f"\nTraffic Level: {trend['traffic']}")
        if "+" in trend["traffic"]:
            volume = int(trend["traffic"].replace("+", "").replace(",", ""))
            if volume >= 500:
                print("📈 HIGH TRAFFIC - Breaking news potential")
            elif volume >= 200:
                print("📊 MODERATE TRAFFIC - Developing story")
            else:
                print("📉 LOW TRAFFIC - Niche interest")

        # Publication timing
        pub_time = trend["published"]
        print(f"First appeared: {pub_time}")

        # News sources (verify credibility)
        print("\n📰 News Coverage:")
        if trend.get("news_articles"):
            sources = set()
            for j, article in enumerate(trend["news_articles"][:5], 1):
                source = article["source"]
                sources.add(source)
                print(f"\n  {j}. {article['headline']}")
                print(f"     Source: {source}")
                print(f"     URL: {article['url']}")

            # Credibility check
            credible_sources = {"CNN", "BBC", "Reuters", "AP", "NPR", "Bloomberg"}
            verified = sources & credible_sources
            if verified:
                print(f"\n✅ VERIFIED: {len(verified)} credible source(s) - {', '.join(verified)}")
            else:
                print("\n⚠️ UNVERIFIED: No major news outlets yet - verify before publishing")

        # Visual content available
        if trend.get("image", {}).get("url"):
            print("\n📸 Image Available:")
            print(f"   URL: {trend['image']['url']}")
            print(f"   Source: {trend['image']['source']}")
            print("   (Check usage rights before publishing)")

        # Story angle suggestion
        print("\n💡 Story Angle:")
        if trend.get("news_articles") and len(trend["news_articles"]) > 0:
            headlines = [a["headline"] for a in trend["news_articles"][:3]]
            if any("breaking" in h.lower() for h in headlines):
                print("   BREAKING NEWS - Develop quickly, verify sources")
            elif any("update" in h.lower() for h in headlines):
                print("   DEVELOPING STORY - Monitor for updates")
            else:
                print("   FEATURE STORY - Deeper analysis opportunity")

        print()

    print("=" * 70)
    print("WORKFLOW COMPLETE")
    print("=" * 70)
    print("\n⏱️ Total time: <1 second")
    print("💰 Cost: $0 (vs $15-50 for commercial news APIs)")
    print("✅ Ready to write or monitor for updates")


if __name__ == "__main__":
    main()
