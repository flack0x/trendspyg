"""
Pytest configuration and fixtures
"""

import pytest
import requests


@pytest.fixture(autouse=True)
def _direct_engine_offline(request, monkeypatch):
    """No test reaches Google through the direct Explore engine; its pause starts clear.

    Tests of the direct engine install their own fake session. Live tests
    (marked ``network``) keep the real one.
    """
    if request.node.get_closest_marker("network"):
        return
    from trendspyg.explore import _http

    class _Offline:
        def request(self, *args, **kwargs):
            raise requests.ConnectionError("tests do not reach Google")

        get = request

    monkeypatch.setattr(_http, "_session", _Offline())
    monkeypatch.setattr(_http, "_paused_until", 0.0)


@pytest.fixture
def sample_rss_trends():
    """Sample RSS trend data for testing"""
    return [
        {
            "trend": "test trend",
            "traffic": "200+",
            "published": "2025-11-04T10:00:00+00:00",
            "image": {"url": "https://example.com/image.jpg", "source": "Test Source"},
            "news_articles": [
                {
                    "headline": "Test headline",
                    "url": "https://example.com/article",
                    "source": "Test News",
                    "image": "https://example.com/news-image.jpg",
                }
            ],
            "explore_link": "https://trends.google.com/trends/explore?q=test",
        }
    ]


@pytest.fixture
def valid_geo_codes():
    """List of valid geo codes for testing"""
    return ["US", "GB", "CA", "AU", "DE", "FR", "JP", "US-CA", "US-NY"]


@pytest.fixture
def invalid_geo_codes():
    """List of invalid geo codes for testing"""
    return ["INVALID", "XX", "123", ""]
