#!/usr/bin/env python3
"""
Caching Example

This example demonstrates how to use the built-in caching system
to reduce API calls and improve performance for repeated requests.
"""

import time
from trendspyg import (
    download_google_trends_rss,
    clear_rss_cache,
    get_rss_cache_stats,
    set_rss_cache_ttl,
)


def demonstrate_caching():
    """Show how caching speeds up repeated requests."""
    print("Demonstrating cache performance:")
    print("-" * 40)

    # Clear cache to start fresh
    clear_rss_cache()
    print("Cache cleared\n")

    # First call - fetches from network
    print("First call (network)...")
    start = time.time()
    trends = download_google_trends_rss(geo='US')
    first_time = time.time() - start
    print(f"  Time: {first_time:.3f}s")
    print(f"  Got {len(trends)} trends\n")

    # Second call - uses cache (instant)
    print("Second call (cached)...")
    start = time.time()
    trends = download_google_trends_rss(geo='US')
    second_time = time.time() - start
    print(f"  Time: {second_time:.6f}s")
    print(f"  Got {len(trends)} trends\n")

    # Show speedup
    if second_time > 0:
        speedup = first_time / second_time
        print(f"Cache speedup: {speedup:.0f}x faster!")


def show_cache_stats():
    """Display cache statistics."""
    print("\nCache Statistics:")
    print("-" * 40)

    stats = get_rss_cache_stats()
    print(f"  Hits: {stats['hits']}")
    print(f"  Misses: {stats['misses']}")
    print(f"  Size: {stats['size']} / {stats['max_size']} entries")
    print(f"  Hit Rate: {stats['hit_rate']}")
    print(f"  TTL: {stats['ttl']} seconds")


def bypass_cache():
    """Show how to bypass cache for fresh data."""
    print("\nBypassing Cache:")
    print("-" * 40)

    # Force fresh data (bypass cache)
    print("Fetching fresh data (cache=False)...")
    trends = download_google_trends_rss(geo='US', cache=False)
    print(f"  Got {len(trends)} fresh trends")


def configure_cache():
    """Show how to configure cache TTL."""
    print("\nConfiguring Cache TTL:")
    print("-" * 40)

    # Increase TTL to 10 minutes
    set_rss_cache_ttl(600)
    print("  TTL set to 600 seconds (10 minutes)")

    # Disable caching
    set_rss_cache_ttl(0)
    print("  TTL set to 0 (caching disabled)")

    # Reset to default
    set_rss_cache_ttl(300)
    print("  TTL reset to 300 seconds (5 minutes)")


def main():
    print("=" * 50)
    print("Caching Examples")
    print("=" * 50)

    demonstrate_caching()
    show_cache_stats()
    bypass_cache()
    configure_cache()

    print("\nDone!")


if __name__ == '__main__':
    main()
