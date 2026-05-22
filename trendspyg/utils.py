"""Utility functions for trendspy."""

import os
import re
import time
import threading
from datetime import datetime
from typing import Callable, Any, TypeVar, cast, Dict, Optional, Tuple, Generic
from functools import wraps

# Type variable for generic function
F = TypeVar('F', bound=Callable[..., Any])
T = TypeVar('T')


# --- Traffic / volume parsing ------------------------------------------------
# Shared by the RSS path (traffic_min) and the normalization layer (CSV volume).

_TRAFFIC_PATTERN = re.compile(r"([\d,.]+)\s*([KMB]?)", re.IGNORECASE)
_TRAFFIC_SUFFIX = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def _parse_traffic_to_min(traffic: Optional[str]) -> int:
    """Parse a human-readable traffic/volume string into an int lower bound.

    Handles forms like '1000+', '50,000+', '2K+', '5M+', '1.5B+'. Returns the
    minimum bound; unparseable input returns 0 rather than raising so a
    malformed feed never breaks a caller sorting by volume.
    """
    if not traffic or traffic == "N/A":
        return 0
    match = _TRAFFIC_PATTERN.search(traffic)
    if not match:
        return 0
    number_part, suffix = match.group(1), match.group(2).upper()
    try:
        value = float(number_part.replace(",", ""))
    except ValueError:
        return 0
    return int(value * _TRAFFIC_SUFFIX.get(suffix, 1))


class TTLCache(Generic[T]):
    """
    Thread-safe TTL (Time-To-Live) cache for storing temporary data.

    Features:
    - Automatic expiration based on TTL
    - Thread-safe operations
    - Maximum size limit with LRU-style eviction
    - Cache statistics (hits, misses)

    Example:
        >>> cache = TTLCache(ttl=300, max_size=100)  # 5 min TTL, max 100 items
        >>> cache.set('US', trends_data)
        >>> data = cache.get('US')  # Returns data if not expired
        >>> cache.clear()  # Clear all cached data
    """

    def __init__(self, ttl: float = 300.0, max_size: int = 256):
        """
        Initialize TTL cache.

        Args:
            ttl: Time-to-live in seconds (default: 300 = 5 minutes)
            max_size: Maximum number of items to cache (default: 256)
        """
        self._cache: Dict[str, Tuple[T, float]] = {}  # key -> (value, expiry_time)
        self._ttl = ttl
        self._max_size = max_size
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[T]:
        """
        Get value from cache if exists and not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    self._hits += 1
                    return value
                else:
                    # Expired, remove it
                    del self._cache[key]
            self._misses += 1
            return None

    def set(self, key: str, value: T) -> None:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            # Evict oldest entries if at max size
            if len(self._cache) >= self._max_size and key not in self._cache:
                self._evict_expired()
                # If still at max, remove oldest entry
                if len(self._cache) >= self._max_size:
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]

            expiry = time.time() + self._ttl
            self._cache[key] = (value, expiry)

    def _evict_expired(self) -> int:
        """Remove all expired entries. Returns count of evicted items."""
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._cache.items() if now >= exp]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with hits, misses, size, hit_rate
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                'hits': self._hits,
                'misses': self._misses,
                'size': len(self._cache),
                'max_size': self._max_size,
                'ttl': self._ttl,
                'hit_rate': f"{hit_rate:.1f}%"
            }

    @property
    def ttl(self) -> float:
        """Get current TTL value."""
        return self._ttl

    @ttl.setter
    def ttl(self, value: float) -> None:
        """Set new TTL value (doesn't affect existing entries)."""
        self._ttl = value


# Global RSS cache instance (5 minute TTL, max 256 entries)
_rss_cache: TTLCache = TTLCache(ttl=300.0, max_size=256)


def get_rss_cache() -> TTLCache:
    """Get the global RSS cache instance."""
    return _rss_cache


def clear_rss_cache() -> None:
    """Clear the global RSS cache."""
    _rss_cache.clear()


def get_rss_cache_stats() -> Dict[str, Any]:
    """Get statistics for the global RSS cache."""
    return _rss_cache.stats()


def set_rss_cache_ttl(ttl: float) -> None:
    """
    Set the TTL for the global RSS cache.

    Args:
        ttl: New TTL in seconds (0 to disable caching)
    """
    _rss_cache.ttl = ttl


def get_timestamp() -> str:
    """Get current timestamp in YYYYMMDD-HHMMSS format."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_dir(directory: str) -> str:
    """Ensure directory exists, create if it doesn't."""
    os.makedirs(directory, exist_ok=True)
    return directory


def rate_limit(delay: float = 1.0) -> Callable[[F], F]:
    """Simple rate limiting decorator."""
    def decorator(func: F) -> F:
        last_called = [0.0]

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            elapsed = time.time() - last_called[0]
            if elapsed < delay:
                time.sleep(delay - elapsed)
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        return cast(F, wrapper)
    return decorator
