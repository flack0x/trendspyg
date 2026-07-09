"""Public-API lock: the v1.0.0 stability contract, pinned as a test.

STABILITY.md declares everything in ``trendspyg.__all__`` covered by semantic
versioning. This test pins that surface exactly:

- Removing or renaming a name from EXPECTED_PUBLIC_API is a BREAKING change and
  belongs in a major release.
- Adding a name is a minor release — add it here deliberately, in the same PR.

If this test fails, the public surface drifted. Fix the surface or update the
contract consciously; never silence the test.
"""

import trendspyg
from trendspyg import exceptions as exceptions_module

EXPECTED_PUBLIC_API = {
    "__version__",
    # Core downloaders
    "download_google_trends_csv",
    "download_google_trends_rss",
    "download_google_trends_rss_async",
    "download_google_trends_rss_batch",
    "download_google_trends_rss_batch_async",
    # Explore path
    "download_google_trends_interest_over_time",
    "download_google_trends_explore",
    # Monitoring
    "watch_google_trends_rss",
    "diff_trends",
    "filter_changes",
    "post_webhook",
    # Cache control
    "clear_rss_cache",
    "get_rss_cache_stats",
    "set_rss_cache_ttl",
    # Exceptions
    "TrendspygException",
    "DownloadError",
    "RateLimitError",
    "InvalidParameterError",
    "BrowserError",
    "ParseError",
    # Schema-version constants
    "SCHEMA_VERSION",
    "EXPLORE_SCHEMA_VERSION",
    "MONITOR_SCHEMA_VERSION",
    # Typed return shapes
    "Trend",
    "NewsArticle",
    "TrendImage",
    "TrendEnvelope",
    "NormalizedTrend",
    "NormalizedEnvelope",
    "InterestPoint",
    "RelatedQuery",
    "RegionInterest",
    "ExploreEnvelope",
    "TrendChange",
}

EXCEPTION_NAMES = [
    "TrendspygException",
    "DownloadError",
    "RateLimitError",
    "InvalidParameterError",
    "BrowserError",
    "ParseError",
]


class TestPublicApiLock:
    """The __all__ surface is the contract — it may only change deliberately."""

    def test_all_matches_contract_exactly(self):
        assert set(trendspyg.__all__) == EXPECTED_PUBLIC_API, (
            "trendspyg.__all__ no longer matches the pinned public API. "
            "Removals/renames are breaking (major release); additions are minor. "
            "Update EXPECTED_PUBLIC_API and STABILITY.md together, deliberately."
        )

    def test_all_has_no_duplicates(self):
        assert len(trendspyg.__all__) == len(set(trendspyg.__all__))

    def test_every_public_name_is_importable(self):
        for name in trendspyg.__all__:
            assert hasattr(trendspyg, name), f"'{name}' is in __all__ but not importable"


class TestExceptionsAtRoot:
    """Root re-exports must be the same objects as trendspyg.exceptions (new in 1.0.0)."""

    def test_root_exceptions_are_the_canonical_classes(self):
        for name in EXCEPTION_NAMES:
            root_cls = getattr(trendspyg, name)
            canonical_cls = getattr(exceptions_module, name)
            assert root_cls is canonical_cls, (
                f"trendspyg.{name} is not the same object as trendspyg.exceptions.{name} — "
                "except-clauses would silently stop matching"
            )

    def test_exception_hierarchy(self):
        assert issubclass(trendspyg.TrendspygException, Exception)
        for name in EXCEPTION_NAMES:
            if name == "TrendspygException":
                continue
            assert issubclass(
                getattr(trendspyg, name), trendspyg.TrendspygException
            ), f"{name} must subclass TrendspygException so users can catch the base class"
