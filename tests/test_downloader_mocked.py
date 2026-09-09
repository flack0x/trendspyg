"""
Tests for CSV downloader validation and helpers
"""

import pytest

from trendspyg.downloader import (
    validate_category,
    validate_geo,
    validate_hours,
)
from trendspyg.exceptions import InvalidParameterError


class TestValidateGeo:
    """Test geo validation"""

    def test_valid_country_codes(self):
        """Test valid country codes"""
        assert validate_geo("US") == "US"
        assert validate_geo("GB") == "GB"
        assert validate_geo("DE") == "DE"

    def test_valid_us_states(self):
        """Test valid US state codes"""
        assert validate_geo("US-CA") == "US-CA"
        assert validate_geo("US-NY") == "US-NY"
        assert validate_geo("US-TX") == "US-TX"

    def test_lowercase_to_uppercase(self):
        """Test lowercase conversion"""
        assert validate_geo("us") == "US"
        assert validate_geo("gb") == "GB"
        assert validate_geo("us-ca") == "US-CA"

    def test_invalid_geo_raises_error(self):
        """Test invalid geo raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            validate_geo("INVALID")

        assert "Invalid geo code" in str(exc_info.value)

    def test_invalid_geo_suggests_alternatives(self):
        """Test invalid geo suggests alternatives"""
        with pytest.raises(InvalidParameterError) as exc_info:
            validate_geo("USA")

        error_msg = str(exc_info.value)
        assert "Did you mean" in error_msg


class TestValidateHours:
    """Test hours validation"""

    def test_valid_hours(self):
        """Test valid hour values"""
        assert validate_hours(4) == 4
        assert validate_hours(24) == 24
        assert validate_hours(48) == 48
        assert validate_hours(168) == 168

    def test_invalid_hours_raises_error(self):
        """Test invalid hours raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            validate_hours(12)

        assert "Invalid hours value" in str(exc_info.value)
        assert "4, 24, 48, 168" in str(exc_info.value)

    def test_invalid_hours_zero(self):
        """Test zero hours raises error"""
        with pytest.raises(InvalidParameterError):
            validate_hours(0)

    def test_invalid_hours_negative(self):
        """Test negative hours raises error"""
        with pytest.raises(InvalidParameterError):
            validate_hours(-24)


class TestValidateCategory:
    """Test category validation"""

    def test_valid_categories(self):
        """Test valid categories"""
        assert validate_category("all") == "all"
        assert validate_category("sports") == "sports"
        assert validate_category("technology") == "technology"
        assert validate_category("entertainment") == "entertainment"
        assert validate_category("business") == "business"

    def test_lowercase_category(self):
        """Test lowercase category"""
        assert validate_category("SPORTS") == "sports"
        assert validate_category("Technology") == "technology"
        assert validate_category("ENTERTAINMENT") == "entertainment"

    def test_invalid_category_raises_error(self):
        """Test invalid category raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            validate_category("invalid_category")

        assert "Invalid category" in str(exc_info.value)

    def test_all_valid_categories(self):
        """Test all valid categories work"""
        valid_categories = [
            "all",
            "sports",
            "entertainment",
            "business",
            "politics",
            "technology",
            "health",
            "science",
            "games",
            "shopping",
            "food",
            "travel",
            "beauty",
            "hobbies",
            "climate",
            "jobs",
            "law",
            "pets",
            "autos",
            "other",
        ]
        for cat in valid_categories:
            assert validate_category(cat) == cat


class TestValidationEdgeCases:
    """Test edge cases in validation"""

    def test_empty_geo_raises_error(self):
        """Test empty geo raises error"""
        with pytest.raises(InvalidParameterError):
            validate_geo("")

    def test_whitespace_geo_raises_error(self):
        """Test whitespace geo raises error"""
        with pytest.raises(InvalidParameterError):
            validate_geo("  ")

    def test_empty_category_raises_error(self):
        """Test empty category raises error"""
        with pytest.raises(InvalidParameterError):
            validate_category("")


class TestLogToStderr:
    """Progress output must go to stderr, never stdout (pipe-safety)."""

    def test_log_writes_to_stderr_only(self, capsys):
        """_log() output must land on stderr so stdout stays pipe-clean"""
        from trendspyg.downloader import _log

        _log("[INFO] progress message")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "[INFO] progress message" in captured.err


class TestConvertCsvToFormat:
    """Output-format conversion for the CSV path"""

    def test_csv_format_returns_path(self, tmp_path):
        """csv format returns the path unchanged, no pandas needed"""
        from trendspyg.downloader import _convert_csv_to_format

        csv_file = tmp_path / "trends.csv"
        csv_file.write_text("Trends,Search volume\nfoo,100+\n")
        result = _convert_csv_to_format(str(csv_file), "csv", str(tmp_path))
        assert result == str(csv_file)

    def test_dict_format_returns_list_of_dicts(self, tmp_path):
        """dict format returns a list of row dicts (regression: was unsupported)"""
        pytest.importorskip("pandas")
        from trendspyg.downloader import _convert_csv_to_format

        csv_file = tmp_path / "trends.csv"
        csv_file.write_text("Trends,Search volume\nfoo,100+\nbar,200+\n")
        result = _convert_csv_to_format(str(csv_file), "dict", str(tmp_path))
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["Trends"] == "foo"
        assert result[0]["Search volume"] == "100+"


class TestEffectiveCategory:
    def test_ignored_url_is_corrected_through_the_menu(self):
        from unittest.mock import MagicMock

        from trendspyg.downloader import _verify_category

        driver = MagicMock()
        button = MagicMock()
        item = MagicMock()
        button.get_attribute.return_value = "All categories, select category"
        driver.find_element.side_effect = lambda *args: (
            item if "menuitemradio" in args[1] else button
        )

        def click(_script, element):
            if element is item:
                button.get_attribute.return_value = "Sports, select category"

        driver.execute_script.side_effect = click
        _verify_category(driver, "sports", 0)
        assert driver.execute_script.call_count == 2

    def test_matching_selector_is_accepted(self):
        from unittest.mock import MagicMock

        from trendspyg.downloader import _verify_category

        driver = MagicMock()
        driver.find_element.return_value.get_attribute.return_value = "Sports, select category"
        _verify_category(driver, "sports", 0)

    def test_ignored_category_prevents_export(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from trendspyg import BrowserError, download_google_trends_csv

        driver = MagicMock()
        driver.find_element.return_value.get_attribute.return_value = (
            "All categories, select category"
        )
        with patch("trendspyg.downloader.webdriver.Chrome", return_value=driver):
            with pytest.raises(BrowserError, match="refusing to export unfiltered"):
                download_google_trends_csv(
                    category="sports", timeout=0, max_retries=1, download_dir=str(tmp_path)
                )
        driver.find_element.return_value.click.assert_not_called()
        driver.quit.assert_called_once()

    def test_every_category_has_a_verified_label(self):
        from trendspyg.config import CATEGORIES
        from trendspyg.downloader import _CATEGORY_LABELS

        assert set(_CATEGORY_LABELS) == set(CATEGORIES) - {"all"}
        assert CATEGORIES["sports"] == "17"
        assert CATEGORIES["climate"] == "20"
