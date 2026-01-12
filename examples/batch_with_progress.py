#!/usr/bin/env python3
"""
Batch Fetching with Progress Bar Example

This example demonstrates how to fetch trends from multiple countries
with a progress bar showing real-time progress.

Requires: pip install trendspyg[async]  (for async batch)
"""

import asyncio
from trendspyg import (
    download_google_trends_rss_batch,
    download_google_trends_rss_batch_async,
)


def sync_batch_example():
    """Synchronous batch fetching with progress bar."""
    countries = ['US', 'GB', 'CA', 'AU', 'DE', 'FR', 'JP', 'BR']

    print("Sync batch fetching (with progress bar):")
    print("-" * 40)

    # Fetch all countries with progress bar
    results = download_google_trends_rss_batch(
        countries,
        show_progress=True,  # Shows: Fetching trends: 100%|██████████| 8/8
        delay=0.1  # Small delay between requests to be nice to Google
    )

    print(f"\nFetched {len(results)} countries:")
    for country, trends in results.items():
        print(f"  {country}: {len(trends)} trends")


async def async_batch_example():
    """Asynchronous batch fetching - fastest option."""
    countries = ['US', 'GB', 'CA', 'AU', 'DE', 'FR', 'JP', 'BR', 'IN', 'MX']

    print("\nAsync batch fetching (fastest, with progress bar):")
    print("-" * 40)

    # Fetch all countries in parallel with progress bar
    results = await download_google_trends_rss_batch_async(
        countries,
        show_progress=True,
        max_concurrent=5  # Limit concurrent requests to avoid rate limits
    )

    print(f"\nFetched {len(results)} countries:")
    for country, trends in results.items():
        print(f"  {country}: {len(trends)} trends")


def main():
    print("=" * 50)
    print("Batch Fetching Examples")
    print("=" * 50)

    # Sync example
    sync_batch_example()

    # Async example
    print("\n")
    asyncio.run(async_batch_example())

    print("\nDone!")


if __name__ == '__main__':
    main()
