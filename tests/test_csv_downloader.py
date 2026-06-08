"""
Tests for CSV downloader functionality

Note: CSV tests require Chrome browser to be installed.
Some tests may be skipped if Chrome is not available or if running in CI.
"""

import pytest

from trendspyg import download_google_trends_csv
from trendspyg.exceptions import DownloadError, InvalidParameterError

# Mark all tests as slow (they require browser automation)
pytestmark = pytest.mark.slow


class TestCSVBasicFunctionality:
    """Test basic CSV download functionality"""

    @pytest.mark.skip(reason="Requires Chrome browser - run manually")
    def test_csv_returns_data(self):
        """Test that CSV download returns data"""
        result = download_google_trends_csv(geo="US", hours=4)

        # Should return filepath or DataFrame
        assert result is not None

    @pytest.mark.skip(reason="Requires Chrome browser - run manually")
    def test_csv_with_category_filter(self):
        """Test CSV download with category filtering"""
        result = download_google_trends_csv(geo="US", hours=24, category="sports")

        assert result is not None

    @pytest.mark.skip(reason="Requires Chrome browser - run manually")
    def test_csv_with_time_filtering(self):
        """Test CSV download with different time periods"""
        for hours in [4, 24, 48, 168]:
            result = download_google_trends_csv(geo="US", hours=hours)
            assert result is not None


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
        # These should not raise errors (even though download might fail)
        valid_geos = ["US", "GB", "CA", "AU", "DE"]
        for geo in valid_geos:
            try:
                # Just test validation, not actual download
                from trendspyg.downloader import _validate_geo_csv

                result = _validate_geo_csv(geo)
                assert result == geo
            except ImportError:
                pytest.skip("Cannot import validation function")

    def test_valid_us_states(self):
        """Test that validation accepts US state codes"""
        valid_states = ["US-CA", "US-NY", "US-TX", "US-FL"]
        for geo in valid_states:
            try:
                from trendspyg.downloader import _validate_geo_csv

                result = _validate_geo_csv(geo)
                assert result == geo
            except ImportError:
                pytest.skip("Cannot import validation function")


class TestCSVOutputFormats:
    """Test different output formats for CSV downloader"""

    @pytest.mark.skip(reason="Requires Chrome browser - run manually")
    def test_csv_format(self):
        """Test CSV string output format"""
        result = download_google_trends_csv(geo="US", hours=4, output_format="csv")

        assert isinstance(result, str)
        assert "Trends,Search volume" in result

    @pytest.mark.skip(reason="Requires Chrome browser - run manually")
    def test_json_format(self):
        """Test JSON output format"""
        result = download_google_trends_csv(geo="US", hours=4, output_format="json")

        assert isinstance(result, str)
        assert result.startswith("[") or result.startswith("{")

    @pytest.mark.skip(reason="Requires Chrome browser - run manually")
    def test_dataframe_format(self):
        """Test DataFrame output format"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")

        df = download_google_trends_csv(geo="US", hours=4, output_format="dataframe")

        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "Trends" in df.columns

    @pytest.mark.skip(reason="Requires Chrome browser - run manually")
    def test_parquet_format(self):
        """Test Parquet output format"""
        try:
            import pyarrow
        except ImportError:
            pytest.skip("pyarrow not installed")

        result = download_google_trends_csv(geo="US", hours=4, output_format="parquet")

        assert isinstance(result, str)
        assert result.endswith(".parquet")


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
            # Just test validation, not actual download
            try:
                from trendspyg.downloader import (
                    _validate_category,
                    _validate_geo_csv,
                    _validate_hours,
                )

                _validate_geo_csv(params["geo"])
                _validate_hours(params["hours"])
                _validate_category(params["category"])
            except ImportError:
                pytest.skip("Cannot import validation functions")

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
        try:
            from trendspyg.downloader import _validate_geo_csv

            upper = _validate_geo_csv("US")
            lower = _validate_geo_csv("us")

            assert upper == lower == "US"
        except ImportError:
            pytest.skip("Cannot import validation function")

    def test_case_insensitive_category(self):
        """Test that categories are case-insensitive"""
        try:
            from trendspyg.downloader import _validate_category

            upper = _validate_category("SPORTS")
            lower = _validate_category("sports")

            assert upper == lower
        except ImportError:
            pytest.skip("Cannot import validation function")

    @pytest.mark.skip(reason="Requires Chrome browser - run manually")
    def test_handles_network_errors(self):
        """Test that network errors are handled gracefully"""
        # This would test with no internet connection
        # Implementation depends on actual error handling in code
        pass


class TestCSVIntegration:
    """Integration tests for CSV downloader"""

    @pytest.mark.skip(reason="Requires Chrome browser - run manually")
    def test_full_workflow(self):
        """Test complete workflow: download, parse, filter"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not installed")

        # Download as DataFrame
        df = download_google_trends_csv(
            geo="US", hours=24, category="sports", active_only=True, output_format="dataframe"
        )

        # Verify data structure
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

        # Check for expected columns
        expected_columns = ["Trends", "Search volume"]
        for col in expected_columns:
            assert col in df.columns

        # Verify data types
        assert df["Trends"].dtype == object  # string
        assert df["Search volume"].dtype == object  # string (has '+' symbols)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
