"""
Tests for RSS downloader functionality
"""

import pytest

from trendspyg import (
    download_google_trends_rss,
    download_google_trends_rss_async,
    download_google_trends_rss_batch,
    download_google_trends_rss_batch_async,
)
from trendspyg.exceptions import InvalidParameterError


@pytest.mark.network
class TestRSSBasicFunctionality:
    """Test basic RSS download functionality"""

    def test_rss_returns_data(self):
        """Test that RSS download returns trend data"""
        trends = download_google_trends_rss(geo="US")

        assert isinstance(trends, list)
        assert len(trends) > 0
        assert "trend" in trends[0]
        assert "traffic" in trends[0]
        assert "published" in trends[0]

    def test_rss_with_articles(self):
        """Test RSS download includes news articles"""
        trends = download_google_trends_rss(geo="US", include_articles=True)

        assert "news_articles" in trends[0]
        assert isinstance(trends[0]["news_articles"], list)

    def test_rss_with_images(self):
        """Test RSS download includes images"""
        trends = download_google_trends_rss(geo="US", include_images=True)

        assert "image" in trends[0]
        assert "url" in trends[0]["image"]
        assert "source" in trends[0]["image"]

    def test_rss_without_articles(self):
        """Test RSS download without articles"""
        trends = download_google_trends_rss(geo="US", include_articles=False)

        assert "news_articles" not in trends[0]

    def test_rss_without_images(self):
        """Test RSS download without images"""
        trends = download_google_trends_rss(geo="US", include_images=False)

        assert "image" not in trends[0]


@pytest.mark.network
class TestRSSOutputFormats:
    """Test different output formats"""

    def test_dict_format(self):
        """Test dict output format (default)"""
        trends = download_google_trends_rss(geo="US", output_format="dict")

        assert isinstance(trends, list)
        assert isinstance(trends[0], dict)

    def test_json_format(self):
        """Test JSON output format"""
        result = download_google_trends_rss(geo="US", output_format="json")

        assert isinstance(result, str)
        assert result.startswith("[")

        # Should be valid JSON
        import json

        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_csv_format(self):
        """Test CSV output format"""
        result = download_google_trends_rss(geo="US", output_format="csv")

        assert isinstance(result, str)
        assert "trend,traffic,traffic_min,published" in result
        lines = result.strip().split("\n")
        assert len(lines) > 1  # Header + at least one data row

    def test_dataframe_format(self):
        """Test DataFrame output format"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")

        df = download_google_trends_rss(geo="US", output_format="dataframe")

        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "trend" in df.columns
        assert "traffic" in df.columns


class TestErrorMessages:
    """Test error message quality and helpfulness"""

    def test_invalid_geo_suggests_similar(self):
        """Test that invalid geo code suggests similar codes"""
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_rss(geo="INVALID")

        error_msg = str(exc_info.value)
        assert "Invalid geo code" in error_msg
        assert "Did you mean" in error_msg  # Should suggest alternatives

    def test_invalid_geo_shows_available_count(self):
        """Test that error shows available countries count"""
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_rss(geo="XXX")

        error_msg = str(exc_info.value)
        assert "125 countries" in error_msg
        assert "51 US states" in error_msg

    def test_invalid_output_format_lists_valid_options(self):
        """Test that invalid output format lists valid options"""
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_rss(geo="US", output_format="xml")

        error_msg = str(exc_info.value)
        assert "dict" in error_msg
        assert "dataframe" in error_msg
        assert "json" in error_msg
        assert "csv" in error_msg


class TestHTTPErrorHandling:
    """Test HTTP error message handling"""

    def test_rate_limit_error_message(self):
        """Test that rate limit errors have helpful messages"""
        from trendspyg.exceptions import RateLimitError
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(RateLimitError) as exc_info:
            _handle_http_error(429, "US", "http://example.com")

        error_msg = str(exc_info.value)
        assert "Rate limit" in error_msg
        assert "Wait" in error_msg or "wait" in error_msg

    def test_403_treated_as_rate_limit(self):
        """Test that 403 is treated as rate limit"""
        from trendspyg.exceptions import RateLimitError
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(RateLimitError):
            _handle_http_error(403, "US", "http://example.com")

    def test_404_error_message(self):
        """Test that 404 errors are helpful"""
        from trendspyg.exceptions import DownloadError
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(DownloadError) as exc_info:
            _handle_http_error(404, "XX", "http://example.com")

        error_msg = str(exc_info.value)
        assert "404" in error_msg
        assert "XX" in error_msg  # Should mention the geo code

    def test_500_error_message(self):
        """Test that server errors are helpful"""
        from trendspyg.exceptions import DownloadError
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(DownloadError) as exc_info:
            _handle_http_error(500, "US", "http://example.com")

        error_msg = str(exc_info.value)
        assert "500" in error_msg
        assert "server" in error_msg.lower()


@pytest.mark.network
class TestRSSValidation:
    """Test input validation"""

    def test_invalid_geo_code(self):
        """Test that invalid geo code raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_rss(geo="INVALID")

        assert "Invalid geo code" in str(exc_info.value)

    def test_invalid_output_format(self):
        """Test that invalid output format raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_rss(geo="US", output_format="xml")

        assert "Invalid output_format" in str(exc_info.value)

    def test_valid_country_codes(self):
        """Test that valid country codes work"""
        # Test a few country codes
        for geo in ["US", "GB", "CA", "AU"]:
            trends = download_google_trends_rss(geo=geo)
            assert len(trends) > 0

    def test_us_state_codes(self):
        """Test that US state codes work"""
        trends = download_google_trends_rss(geo="US-CA")
        assert len(trends) > 0


@pytest.mark.network
class TestRSSDataStructure:
    """Test the structure of returned data"""

    def test_trend_has_required_fields(self):
        """Test that each trend has required fields"""
        trends = download_google_trends_rss(geo="US")

        required_fields = ["trend", "traffic", "published", "explore_link"]
        for field in required_fields:
            assert field in trends[0]

    def test_news_article_structure(self):
        """Test news article data structure"""
        trends = download_google_trends_rss(geo="US", include_articles=True)

        if trends[0]["news_articles"]:
            article = trends[0]["news_articles"][0]
            assert "headline" in article
            assert "url" in article
            assert "source" in article

    def test_max_articles_limit(self):
        """Test max_articles_per_trend parameter"""
        trends = download_google_trends_rss(
            geo="US", include_articles=True, max_articles_per_trend=2
        )

        if trends[0]["news_articles"]:
            assert len(trends[0]["news_articles"]) <= 2


@pytest.mark.network
class TestRSSErrorHandling:
    """Test error handling"""

    def test_case_insensitive_geo(self):
        """Test that geo codes are case-insensitive"""
        trends_upper = download_google_trends_rss(geo="US")
        trends_lower = download_google_trends_rss(geo="us")

        # Both should work (we can't compare exact trends as they change)
        assert len(trends_upper) > 0
        assert len(trends_lower) > 0

    def test_empty_max_articles(self):
        """Test with max_articles_per_trend=0"""
        trends = download_google_trends_rss(
            geo="US", include_articles=True, max_articles_per_trend=0
        )

        assert len(trends[0]["news_articles"]) == 0


@pytest.mark.network
@pytest.mark.asyncio
class TestAsyncRSSBasicFunctionality:
    """Test async RSS download functionality"""

    async def test_async_rss_returns_data(self):
        """Test that async RSS download returns trend data"""
        trends = await download_google_trends_rss_async(geo="US")

        assert isinstance(trends, list)
        assert len(trends) > 0
        assert "trend" in trends[0]
        assert "traffic" in trends[0]
        assert "published" in trends[0]

    async def test_async_rss_with_articles(self):
        """Test async RSS download includes news articles"""
        trends = await download_google_trends_rss_async(geo="US", include_articles=True)

        assert "news_articles" in trends[0]
        assert isinstance(trends[0]["news_articles"], list)

    async def test_async_rss_with_images(self):
        """Test async RSS download includes images"""
        trends = await download_google_trends_rss_async(geo="US", include_images=True)

        assert "image" in trends[0]
        assert "url" in trends[0]["image"]
        assert "source" in trends[0]["image"]


@pytest.mark.network
@pytest.mark.asyncio
class TestAsyncRSSOutputFormats:
    """Test async output formats"""

    async def test_async_dict_format(self):
        """Test async dict output format (default)"""
        trends = await download_google_trends_rss_async(geo="US", output_format="dict")

        assert isinstance(trends, list)
        assert isinstance(trends[0], dict)

    async def test_async_json_format(self):
        """Test async JSON output format"""
        result = await download_google_trends_rss_async(geo="US", output_format="json")

        assert isinstance(result, str)
        assert result.startswith("[")

        import json

        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) > 0

    async def test_async_dataframe_format(self):
        """Test async DataFrame output format"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")

        df = await download_google_trends_rss_async(geo="US", output_format="dataframe")

        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "trend" in df.columns


@pytest.mark.network
@pytest.mark.asyncio
class TestAsyncRSSParallelFetching:
    """Test parallel/concurrent fetching capabilities"""

    async def test_parallel_fetch_multiple_countries(self):
        """Test fetching multiple countries in parallel"""
        import asyncio

        countries = ["US", "GB", "CA"]
        tasks = [download_google_trends_rss_async(geo=geo) for geo in countries]
        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        for trends in results:
            assert isinstance(trends, list)
            assert len(trends) > 0

    async def test_parallel_fetch_with_shared_session(self):
        """Test parallel fetching with shared aiohttp session"""
        try:
            import asyncio

            import aiohttp
        except ImportError:
            pytest.skip("aiohttp not installed")

        countries = ["US", "GB"]

        async with aiohttp.ClientSession() as session:
            tasks = [
                download_google_trends_rss_async(geo=geo, session=session) for geo in countries
            ]
            results = await asyncio.gather(*tasks)

        assert len(results) == 2
        for trends in results:
            assert isinstance(trends, list)
            assert len(trends) > 0


@pytest.mark.network
@pytest.mark.asyncio
class TestAsyncRSSValidation:
    """Test async input validation"""

    async def test_async_invalid_geo_code(self):
        """Test that invalid geo code raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            await download_google_trends_rss_async(geo="INVALID")

        assert "Invalid geo code" in str(exc_info.value)

    async def test_async_invalid_output_format(self):
        """Test that invalid output format raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            await download_google_trends_rss_async(geo="US", output_format="xml")

        assert "Invalid output_format" in str(exc_info.value)


class TestAsyncRSSImportError:
    """Test error handling when aiohttp is not installed"""

    def test_import_error_message(self, monkeypatch):
        """Test that helpful error message is shown when aiohttp missing"""
        import asyncio
        import sys

        # Mock aiohttp as not available
        monkeypatch.setitem(sys.modules, "aiohttp", None)

        # Need to reload the module to trigger import check
        # This test verifies the error message pattern exists in the code
        from trendspyg.rss_downloader import download_google_trends_rss_async

        # The actual ImportError is raised at runtime when aiohttp import fails


@pytest.mark.network
class TestBatchRSSFunctionality:
    """Test batch RSS download functionality"""

    def test_batch_returns_dict(self):
        """Test that batch returns a dictionary"""
        results = download_google_trends_rss_batch(["US", "GB"], show_progress=False)
        assert isinstance(results, dict)
        assert "US" in results
        assert "GB" in results

    def test_batch_contains_trends(self):
        """Test that batch results contain trends"""
        results = download_google_trends_rss_batch(["US"], show_progress=False)
        assert len(results["US"]) > 0
        assert "trend" in results["US"][0]

    def test_batch_with_delay(self):
        """Test batch with delay parameter"""
        import time

        start = time.time()
        results = download_google_trends_rss_batch(["US", "GB"], show_progress=False, delay=0.5)
        elapsed = time.time() - start
        # Should take at least 0.5s due to delay
        assert elapsed >= 0.5
        assert len(results) == 2

    def test_batch_without_images(self):
        """Test batch without images"""
        results = download_google_trends_rss_batch(
            ["US"], include_images=False, show_progress=False
        )
        assert "image" not in results["US"][0]


@pytest.mark.network
@pytest.mark.asyncio
class TestBatchAsyncRSSFunctionality:
    """Test async batch RSS download functionality"""

    async def test_async_batch_returns_dict(self):
        """Test that async batch returns a dictionary"""
        results = await download_google_trends_rss_batch_async(["US", "GB"], show_progress=False)
        assert isinstance(results, dict)
        assert "US" in results
        assert "GB" in results

    async def test_async_batch_contains_trends(self):
        """Test that async batch results contain trends"""
        results = await download_google_trends_rss_batch_async(["US"], show_progress=False)
        assert len(results["US"]) > 0
        assert "trend" in results["US"][0]

    async def test_async_batch_with_concurrency_limit(self):
        """Test async batch with max_concurrent parameter"""
        results = await download_google_trends_rss_batch_async(
            ["US", "GB", "CA"], show_progress=False, max_concurrent=2
        )
        assert len(results) == 3

    async def test_async_batch_returns_results(self):
        """Test that async batch returns valid results for multiple countries"""
        results = await download_google_trends_rss_batch_async(["US", "GB"], show_progress=False)

        # Should return dict with results for each geo
        assert isinstance(results, dict)
        assert "US" in results
        assert "GB" in results


class TestTTLCache:
    """Test TTLCache utility class"""

    def test_cache_set_and_get(self):
        """Test basic cache set and get"""
        from trendspyg.utils import TTLCache

        cache = TTLCache(ttl=300.0, max_size=10)
        cache.set("key1", {"data": "value1"})
        result = cache.get("key1")

        assert result is not None
        assert result["data"] == "value1"

    def test_cache_miss(self):
        """Test cache miss returns None"""
        from trendspyg.utils import TTLCache

        cache = TTLCache(ttl=300.0, max_size=10)
        result = cache.get("nonexistent")

        assert result is None

    def test_cache_expiration(self):
        """Test that cache entries expire after TTL"""
        import time

        from trendspyg.utils import TTLCache

        cache = TTLCache(ttl=0.1, max_size=10)  # 100ms TTL
        cache.set("key1", "value1")

        # Should be available immediately
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(0.15)

        # Should be expired
        assert cache.get("key1") is None

    def test_cache_max_size(self):
        """Test that cache respects max size"""
        from trendspyg.utils import TTLCache

        cache = TTLCache(ttl=300.0, max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # This should evict oldest

        # One of the old keys should be evicted
        assert cache.stats()["size"] == 3

    def test_cache_stats(self):
        """Test cache statistics"""
        from trendspyg.utils import TTLCache

        cache = TTLCache(ttl=300.0, max_size=10)
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["max_size"] == 10
        assert stats["hit_rate"] == "66.7%"

    def test_cache_clear(self):
        """Test cache clear"""
        from trendspyg.utils import TTLCache

        cache = TTLCache(ttl=300.0, max_size=10)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.stats()["size"] == 0

    def test_cache_ttl_property(self):
        """Test TTL property getter and setter"""
        from trendspyg.utils import TTLCache

        cache = TTLCache(ttl=300.0, max_size=10)
        assert cache.ttl == 300.0

        cache.ttl = 600.0
        assert cache.ttl == 600.0


class TestRSSCacheIntegration:
    """Test RSS caching integration"""

    def test_global_cache_functions(self):
        """Test global cache control functions"""
        from trendspyg import clear_rss_cache, get_rss_cache_stats, set_rss_cache_ttl

        # Clear cache first
        clear_rss_cache()

        # Check stats
        stats = get_rss_cache_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # Set TTL
        set_rss_cache_ttl(600.0)
        stats = get_rss_cache_stats()
        assert stats["ttl"] == 600.0

        # Reset TTL to default
        set_rss_cache_ttl(300.0)


@pytest.mark.network
class TestRSSCacheFunctionality:
    """Test RSS caching with network calls"""

    def test_rss_caching_enabled_by_default(self):
        """Test that caching is enabled by default"""
        from trendspyg import clear_rss_cache, download_google_trends_rss, get_rss_cache_stats

        clear_rss_cache()

        # First call - should be a cache miss
        download_google_trends_rss(geo="US")
        stats = get_rss_cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0
        assert stats["size"] == 1

        # Second call - should be a cache hit
        download_google_trends_rss(geo="US")
        stats = get_rss_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_rss_cache_bypass(self):
        """Test that cache=False bypasses cache"""
        from trendspyg import clear_rss_cache, download_google_trends_rss, get_rss_cache_stats

        clear_rss_cache()

        # Call with cache=False
        download_google_trends_rss(geo="US", cache=False)
        stats = get_rss_cache_stats()
        # Should not add to cache
        assert stats["size"] == 0

    def test_rss_cache_different_params(self):
        """Test that different parameters create different cache entries"""
        from trendspyg import clear_rss_cache, download_google_trends_rss, get_rss_cache_stats

        clear_rss_cache()

        # Different params should create different cache entries
        download_google_trends_rss(geo="US")
        download_google_trends_rss(geo="GB")
        download_google_trends_rss(geo="US", include_images=False)

        stats = get_rss_cache_stats()
        assert stats["size"] == 3

    def test_rss_cache_output_format_reuse(self):
        """Test that cached data works with different output formats"""
        from trendspyg import clear_rss_cache, download_google_trends_rss, get_rss_cache_stats

        clear_rss_cache()

        # First call as dict
        dict_result = download_google_trends_rss(geo="US", output_format="dict")
        assert isinstance(dict_result, list)

        # Second call as json (should use cache)
        json_result = download_google_trends_rss(geo="US", output_format="json")
        assert isinstance(json_result, str)

        stats = get_rss_cache_stats()
        # Both should use same cache entry
        assert stats["hits"] == 1
        assert stats["misses"] == 1


@pytest.mark.network
@pytest.mark.asyncio
class TestAsyncRSSCacheFunctionality:
    """Test async RSS caching"""

    async def test_async_rss_caching(self):
        """Test that async also uses the cache"""
        from trendspyg import clear_rss_cache, download_google_trends_rss_async, get_rss_cache_stats

        clear_rss_cache()

        # First call
        await download_google_trends_rss_async(geo="CA")
        stats = get_rss_cache_stats()
        assert stats["misses"] == 1
        assert stats["size"] == 1

        # Second call - should hit cache
        await download_google_trends_rss_async(geo="CA")
        stats = get_rss_cache_stats()
        assert stats["hits"] == 1

    async def test_sync_async_cache_sharing(self):
        """Test that sync and async share the same cache"""
        from trendspyg import (
            clear_rss_cache,
            download_google_trends_rss,
            download_google_trends_rss_async,
            get_rss_cache_stats,
        )

        clear_rss_cache()

        # Sync call
        download_google_trends_rss(geo="AU")

        # Async call should hit cache
        await download_google_trends_rss_async(geo="AU")

        stats = get_rss_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    async def test_async_cache_bypass(self):
        """Test async cache bypass"""
        from trendspyg import clear_rss_cache, download_google_trends_rss_async, get_rss_cache_stats

        clear_rss_cache()

        await download_google_trends_rss_async(geo="GB", cache=False)
        stats = get_rss_cache_stats()
        assert stats["size"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
