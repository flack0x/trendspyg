"""
Pytest configuration and fixtures
"""

import pytest


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
