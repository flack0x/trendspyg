"""A failed active-only filter must not be presented as a filtered dataset."""

from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import NoSuchElementException

from trendspyg import BrowserError, download_google_trends_csv
from trendspyg.downloader import _verify_active_only


def element():
    result = MagicMock()
    result.is_displayed.return_value = True
    result.is_enabled.return_value = True
    return result


@pytest.mark.parametrize("already_active", [False, True])
def test_filter_is_enabled_without_turning_an_existing_selection_off(already_active):
    driver = MagicMock()
    toggle = element()
    toggle.get_attribute.return_value = "true" if already_active else "false"
    driver.find_element.side_effect = lambda _by, selector: (
        toggle if "role='switch'" in selector else element()
    )

    def click(_script, element):
        assert element is toggle
        toggle.get_attribute.return_value = "true"

    driver.execute_script.side_effect = click
    _verify_active_only(driver, 0)
    assert driver.execute_script.call_count == (0 if already_active else 1)
    assert toggle.get_attribute("aria-checked") == "true"


@pytest.mark.parametrize("missing", [False, True])
def test_missing_or_ignored_filter_stops_before_export(tmp_path, missing):
    driver = MagicMock()
    export = element()
    status = element()
    toggle = element()
    toggle.get_attribute.return_value = "false"

    def find(_by, selector):
        if "Export" in selector:
            return export
        if missing:
            raise NoSuchElementException("status selector disappeared")
        return toggle if "role='switch'" in selector else status

    driver.find_element.side_effect = find
    with patch("trendspyg.downloader.webdriver.Chrome", return_value=driver):
        with pytest.raises(BrowserError, match="refusing to export unfiltered"):
            download_google_trends_csv(
                active_only=True, timeout=0, max_retries=1, download_dir=str(tmp_path)
            )
    export.click.assert_not_called()
    driver.quit.assert_called_once()
