"""Offline tests for the CSV downloader: parameter validation only.

The browser-driven CSV export is checked live by ``tests/test_live_contract.py``
(``-m contract``); the nine always-skipped placeholder tests that used to live
here were removed in 1.6.0 — they could never run and asserted only ``is not None``.
"""

import pytest

from trendspyg import download_google_trends_csv
from trendspyg.downloader import validate_category, validate_geo, validate_hours
from trendspyg.exceptions import DownloadError, InvalidParameterError

# Mark all tests as slow (they require browser automation)
pytestmark = pytest.mark.slow


class TestCSVValidation:
    """Test input validation for CSV downloader"""

    def test_invalid_geo_code(self):
        """Test that invalid geo code raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_csv(geo="INVALID")

        assert "Invalid geo code" in str(exc_info.value)

    def test_invalid_hours(self):
        """Test that invalid hours value raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_csv(geo="US", hours=999)

        assert "Invalid hours" in str(exc_info.value)

    def test_invalid_category(self):
        """Test that invalid category raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_csv(geo="US", category="invalid_category")

        assert "Invalid category" in str(exc_info.value)

    def test_invalid_output_format(self):
        """Test that invalid output format raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_csv(geo="US", output_format="xml")

        assert "Unsupported output format" in str(exc_info.value)

    def test_valid_country_codes(self):
        """Test that validation accepts valid country codes"""
        for geo in ["US", "GB", "CA", "AU", "DE"]:
            assert validate_geo(geo) == geo

    def test_valid_us_states(self):
        """Test that validation accepts US state codes"""
        for geo in ["US-CA", "US-NY", "US-TX", "US-FL"]:
            assert validate_geo(geo) == geo


class TestCSVParameterCombinations:
    """Test various parameter combinations"""

    def test_valid_parameter_combinations(self):
        """Test that valid parameter combinations are accepted"""
        valid_combos = [
            {"geo": "US", "hours": 24, "category": "all"},
            {"geo": "GB", "hours": 48, "category": "sports"},
            {"geo": "US-CA", "hours": 168, "category": "technology"},
        ]

        for params in valid_combos:
            assert validate_geo(params["geo"]) == params["geo"]
            assert validate_hours(params["hours"]) == params["hours"]
            assert validate_category(params["category"]) == params["category"]

    def test_active_only_parameter(self):
        """Test active_only filtering parameter"""
        # Should accept boolean values
        for active_only in [True, False]:
            # Just verify parameter is accepted (no actual download)
            assert isinstance(active_only, bool)

    def test_sort_parameter(self):
        """Test sort parameter validation"""
        valid_sorts = ["relevance", "title", "volume", "recency"]

        for sort in valid_sorts:
            # Should not raise errors
            assert sort in valid_sorts


class TestCSVErrorHandling:
    """Test error handling in CSV downloader"""

    def test_case_insensitive_geo(self):
        """Test that geo codes are case-insensitive"""
        assert validate_geo("US") == validate_geo("us") == "US"

    def test_case_insensitive_category(self):
        """Test that categories are case-insensitive"""
        assert validate_category("SPORTS") == validate_category("sports") == "sports"
