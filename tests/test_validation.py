"""
Tests for validation and config functions
"""

import pytest

from trendspyg.config import CATEGORIES, COUNTRIES, TIME_PERIODS, US_STATES
from trendspyg.exceptions import InvalidParameterError


class TestConfigData:
    """Test that config data is properly structured"""

    def test_countries_exist(self):
        """Test that COUNTRIES dictionary is populated"""
        assert len(COUNTRIES) > 0
        assert "US" in COUNTRIES
        assert "GB" in COUNTRIES

    def test_us_states_exist(self):
        """Test that US_STATES dictionary is populated"""
        assert len(US_STATES) > 0
        assert "US-CA" in US_STATES
        assert "US-NY" in US_STATES

    def test_categories_exist(self):
        """Test that CATEGORIES dictionary is populated"""
        assert len(CATEGORIES) > 0
        assert "all" in CATEGORIES
        assert "sports" in CATEGORIES

    def test_time_periods_exist(self):
        """Test that TIME_PERIODS dictionary is populated"""
        assert len(TIME_PERIODS) > 0
        assert 4 in TIME_PERIODS
        assert 24 in TIME_PERIODS


class TestExceptions:
    """Test custom exception classes"""

    def test_invalid_parameter_error(self):
        """Test InvalidParameterError can be raised"""
        with pytest.raises(InvalidParameterError):
            raise InvalidParameterError("Test error")

    def test_invalid_parameter_error_message(self):
        """Test InvalidParameterError preserves message"""
        error_msg = "Custom error message"
        try:
            raise InvalidParameterError(error_msg)
        except InvalidParameterError as e:
            assert str(e) == error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
