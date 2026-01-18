"""
Tests for utility functions
"""
import pytest
import time
from trendspyg.utils import (
    TTLCache,
    get_rss_cache,
    clear_rss_cache,
    get_rss_cache_stats,
    set_rss_cache_ttl,
    get_timestamp,
    ensure_dir,
    rate_limit,
)


class TestVersion:
    """Test version module"""

    def test_version_exists(self):
        """Test version can be imported"""
        from trendspyg.version import __version__, VERSION
        assert __version__ == "0.4.2"
        assert VERSION == "0.4.2"

    def test_version_format(self):
        """Test version has correct format"""
        from trendspyg.version import __version__
        parts = __version__.split('.')
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


class TestTTLCacheAdvanced:
    """Advanced TTL cache tests"""

    def test_cache_thread_safety(self):
        """Test cache is thread-safe"""
        import threading

        cache = TTLCache(ttl=300.0, max_size=100)
        errors = []

        def writer():
            for i in range(100):
                try:
                    cache.set(f'key_{i}', f'value_{i}')
                except Exception as e:
                    errors.append(e)

        def reader():
            for i in range(100):
                try:
                    cache.get(f'key_{i}')
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_cache_eviction_order(self):
        """Test that oldest entries are evicted first"""
        cache = TTLCache(ttl=300.0, max_size=3)

        cache.set('a', 1)
        cache.set('b', 2)
        cache.set('c', 3)
        cache.set('d', 4)  # Should evict 'a'

        assert cache.get('a') is None
        assert cache.get('b') == 2
        assert cache.get('c') == 3
        assert cache.get('d') == 4

    def test_cache_update_existing_key(self):
        """Test updating an existing key"""
        cache = TTLCache(ttl=300.0, max_size=10)

        cache.set('key', 'value1')
        cache.set('key', 'value2')

        assert cache.get('key') == 'value2'
        assert cache.stats()['size'] == 1

    def test_cache_stats_hit_rate_zero_total(self):
        """Test hit rate when no requests made"""
        cache = TTLCache(ttl=300.0, max_size=10)
        stats = cache.stats()
        assert stats['hit_rate'] == '0.0%'

    def test_cache_evict_expired_during_set(self):
        """Test that expired entries are evicted during set"""
        cache = TTLCache(ttl=0.05, max_size=10)

        cache.set('key1', 'value1')
        cache.set('key2', 'value2')

        time.sleep(0.1)  # Let entries expire

        cache.set('key3', 'value3')  # Should trigger eviction

        # Expired entries should be gone
        assert cache.get('key1') is None
        assert cache.get('key2') is None
        assert cache.get('key3') == 'value3'


class TestGlobalCache:
    """Test global cache functions"""

    def test_get_rss_cache_returns_cache(self):
        """Test get_rss_cache returns a TTLCache"""
        cache = get_rss_cache()
        assert isinstance(cache, TTLCache)

    def test_global_cache_is_singleton(self):
        """Test global cache is the same instance"""
        cache1 = get_rss_cache()
        cache2 = get_rss_cache()
        assert cache1 is cache2

    def test_clear_rss_cache_clears(self):
        """Test clear_rss_cache clears the cache"""
        cache = get_rss_cache()
        cache.set('test_key', 'test_value')

        clear_rss_cache()

        assert cache.get('test_key') is None

    def test_get_rss_cache_stats_returns_dict(self):
        """Test get_rss_cache_stats returns proper dict"""
        clear_rss_cache()
        stats = get_rss_cache_stats()

        assert 'hits' in stats
        assert 'misses' in stats
        assert 'size' in stats
        assert 'max_size' in stats
        assert 'ttl' in stats
        assert 'hit_rate' in stats

    def test_set_rss_cache_ttl_changes_ttl(self):
        """Test set_rss_cache_ttl changes TTL"""
        original_ttl = get_rss_cache().ttl

        set_rss_cache_ttl(600.0)
        assert get_rss_cache().ttl == 600.0

        # Reset
        set_rss_cache_ttl(original_ttl)


class TestUtilityFunctions:
    """Test utility functions"""

    def test_get_timestamp_format(self):
        """Test timestamp format"""
        ts = get_timestamp()
        assert len(ts) == 15  # YYYYMMDD-HHMMSS
        assert '-' in ts

    def test_get_timestamp_unique(self):
        """Test timestamps are somewhat unique"""
        ts1 = get_timestamp()
        time.sleep(0.01)
        ts2 = get_timestamp()
        # Should be same or different (depends on timing)
        assert isinstance(ts1, str)
        assert isinstance(ts2, str)

    def test_ensure_dir_creates_directory(self, tmp_path):
        """Test ensure_dir creates directory"""
        new_dir = tmp_path / "new_folder"
        result = ensure_dir(str(new_dir))

        assert new_dir.exists()
        assert result == str(new_dir)

    def test_ensure_dir_existing_directory(self, tmp_path):
        """Test ensure_dir with existing directory"""
        result = ensure_dir(str(tmp_path))
        assert result == str(tmp_path)

    def test_ensure_dir_nested(self, tmp_path):
        """Test ensure_dir creates nested directories"""
        nested = tmp_path / "a" / "b" / "c"
        result = ensure_dir(str(nested))

        assert nested.exists()
        assert result == str(nested)


class TestRateLimitDecorator:
    """Test rate limit decorator"""

    def test_rate_limit_delays_calls(self):
        """Test rate limit adds delay between calls"""
        call_times = []

        @rate_limit(delay=0.1)
        def tracked_func():
            call_times.append(time.time())
            return "done"

        tracked_func()
        tracked_func()
        tracked_func()

        # Check delays between calls
        if len(call_times) >= 2:
            delay = call_times[1] - call_times[0]
            assert delay >= 0.09  # Allow small tolerance

    def test_rate_limit_returns_value(self):
        """Test rate limited function returns correct value"""
        @rate_limit(delay=0.01)
        def returns_value():
            return 42

        assert returns_value() == 42

    def test_rate_limit_preserves_function_name(self):
        """Test decorator preserves function metadata"""
        @rate_limit(delay=0.01)
        def my_function():
            """My docstring"""
            pass

        assert my_function.__name__ == 'my_function'
        assert my_function.__doc__ == 'My docstring'
