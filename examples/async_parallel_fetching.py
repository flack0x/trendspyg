#!/usr/bin/env python3
"""
Async Parallel Fetching Example

This example demonstrates how to use async functions to fetch
trends from multiple countries in parallel - 50-100x faster than sequential.

Requires: pip install trendspyg[async]
"""

import asyncio
from trendspyg import download_google_trends_rss_async


async def fetch_single_country():
    """Fetch trends for a single country asynchronously."""
    print("Fetching US trends...")
    trends = await download_google_trends_rss_async(geo='US')
    print(f"Got {len(trends)} trends from US")
    return trends


async def fetch_multiple_countries():
    """Fetch trends from multiple countries in parallel."""
    countries = ['US', 'GB', 'CA', 'AU', 'DE', 'FR', 'JP', 'BR', 'IN', 'MX']

    print(f"Fetching trends from {len(countries)} countries in parallel...")

    # Create tasks for all countries
    tasks = [
        download_google_trends_rss_async(geo=geo)
        for geo in countries
    ]

    # Execute all in parallel
    results = await asyncio.gather(*tasks)

    # Combine results
    all_trends = dict(zip(countries, results))

    print("\nResults:")
    for country, trends in all_trends.items():
        print(f"  {country}: {len(trends)} trends")

    return all_trends


async def fetch_with_shared_session():
    """Use a shared session for better connection pooling."""
    import aiohttp

    countries = ['US', 'GB', 'CA']

    print("Fetching with shared session (better performance)...")

    async with aiohttp.ClientSession() as session:
        tasks = [
            download_google_trends_rss_async(geo=geo, session=session)
            for geo in countries
        ]
        results = await asyncio.gather(*tasks)

    for country, trends in zip(countries, results):
        print(f"  {country}: {len(trends)} trends")


async def main():
    print("=" * 50)
    print("Async Parallel Fetching Examples")
    print("=" * 50)

    # Example 1: Single country
    print("\n1. Single Country Fetch:")
    await fetch_single_country()

    # Example 2: Multiple countries in parallel
    print("\n2. Multiple Countries (Parallel):")
    await fetch_multiple_countries()

    # Example 3: Shared session
    print("\n3. Shared Session:")
    await fetch_with_shared_session()

    print("\nDone!")


if __name__ == '__main__':
    asyncio.run(main())
