"""Regressions for the unbounded browser/transport failures seen by a consumer."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import TimeoutException
from urllib3.exceptions import ReadTimeoutError

from trendspyg import BrowserError, RateLimitError
from trendspyg.explore import _engine as engine


def transport_error():
    return ReadTimeoutError(None, "/session", "stalled driver")


def test_driver_configures_eager_and_finite_timeouts():
    with patch.object(engine.webdriver, "Chrome") as chrome:
        driver = engine._build_driver(True)
    assert chrome.call_args.kwargs["options"].page_load_strategy == "eager"
    driver.set_page_load_timeout.assert_called_once_with(20)
    driver.set_script_timeout.assert_called_once_with(10)
    assert driver.command_executor._client_config.timeout == 25


def test_legacy_selenium_timeout_is_per_connection():
    first = SimpleNamespace(command_executor=SimpleNamespace())
    second = SimpleNamespace(command_executor=SimpleNamespace(_timeout=99))
    engine._command_timeout(first, 4)
    assert first.command_executor._timeout == 4
    assert second.command_executor._timeout == 99


def test_page_timeout_still_allows_inspecting_rendered_data():
    driver = MagicMock()
    driver.get.side_effect = TimeoutException("resource still loading")
    engine._warm_up(driver)
    driver.set_page_load_timeout.assert_called_once_with(20)


@pytest.mark.parametrize("operation", ["navigate", "replay"])
def test_expired_budget_prevents_new_requests(operation):
    driver = MagicMock()
    with patch.object(engine.time, "monotonic", return_value=100):
        with pytest.raises(BrowserError, match="budget exhausted"):
            if operation == "navigate":
                engine._navigate(driver, "https://example.test", deadline=99)
            else:
                engine._replay_widget(driver, "https://example.test", deadline=99)
    driver.get.assert_not_called()
    driver.execute_async_script.assert_not_called()


@pytest.mark.parametrize("status", [403, 429])
def test_widget_http_throttle_stops_without_retry(status):
    driver = MagicMock()
    driver.execute_async_script.return_value = f"HTTP:{status}"
    with pytest.raises(RateLimitError):
        engine._replay_widget(driver, "https://example.test")
    assert driver.execute_async_script.call_count == 1


def test_stalled_widget_script_can_recover():
    driver = MagicMock()
    driver.execute_async_script.side_effect = [TimeoutException(), '{"default": {}}']
    with patch.object(engine.time, "sleep"):
        assert engine._replay_widget(driver, "https://example.test") == {"default": {}}


@pytest.mark.parametrize("comparison", [False, True])
def test_transport_failure_is_public_error_even_when_quit_fails(comparison):
    driver = MagicMock()
    driver.get.side_effect = transport_error()
    driver.quit.side_effect = transport_error()
    with patch.object(engine, "_build_driver", return_value=driver):
        with pytest.warns(RuntimeWarning, match="cleanup"):
            with pytest.raises(BrowserError, match="ReadTimeoutError") as caught:
                if comparison:
                    engine._fetch_comparison(["coffee", "tea"], "US", "today 12-m", 0, True, False)
                else:
                    engine._fetch_explore("coffee", "US", "today 12-m", 0, True, False, False)
    assert isinstance(caught.value.__cause__, ReadTimeoutError)
    driver.quit.assert_called_once()
    assert driver.command_executor._client_config.timeout == 5


def test_startup_transport_error_is_public_error():
    with patch.object(engine.webdriver, "Chrome", side_effect=transport_error()):
        with pytest.raises(BrowserError, match="Failed to start Chrome"):
            engine._build_driver(True)


def test_timeout_configuration_failure_closes_driver():
    driver = MagicMock()
    driver.set_page_load_timeout.side_effect = transport_error()
    with patch.object(engine.webdriver, "Chrome", return_value=driver):
        with pytest.raises(BrowserError, match="configure Chrome"):
            engine._build_driver(True)
    driver.quit.assert_called_once()
