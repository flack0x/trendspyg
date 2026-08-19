"""The Explore session cookie jar (``cookies="disk"``, new in 1.6.0).

Measured 2026-08-19: after a burst Google refuses *new* Explore visitors with
its hard 429 page while a session carrying an established cookie jar (chiefly
``NID``) is still served. These tests pin the jar's file handling, the engine
wiring (load → inject after warm-up → remember after the chart settles) and
the public ``cookies=`` argument. All offline.
"""

import json
import os
from unittest.mock import MagicMock, call, patch

import pytest
from selenium.common.exceptions import WebDriverException

import trendspyg
from trendspyg.exceptions import InvalidParameterError, RateLimitError
from trendspyg.explore import (
    _fetch_comparison,
    _fetch_explore,
    clear_explore_cookies,
    download_google_trends_comparison,
    download_google_trends_explore,
    download_google_trends_interest_over_time,
)
from trendspyg.explore._cookies import (
    _default_cookie_path,
    _forget_cookies,
    _inject_cookies,
    _load_cookies,
    _save_cookies,
)
from trendspyg.explore._engine import _remember_session

FAKE_FETCH = {
    "interest_over_time": [{"date": "2025-06-01T00:00:00+00:00", "value": 66, "is_partial": False}],
    "related_queries": {"top": [], "rising": []},
    "interest_by_region": [],
}
FAKE_COMPARISON = {
    "keywords": ["a", "b"],
    "interest_over_time": [
        {"date": "2025-06-01T00:00:00+00:00", "values": {"a": 1, "b": 2}, "is_partial": False}
    ],
    "averages": {"a": 1, "b": 2},
    "interest_by_region": [],
}
GOOGLE = [
    {
        "name": "NID",
        "value": "abc",
        "domain": ".google.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "expiry": 1800000000,
    },
    {"name": "_ga", "value": "GA1", "domain": ".trends.google.com", "path": "/"},
]
OTHER = [{"name": "foo", "value": "bar", "domain": ".example.com", "path": "/"}]


class TestDefaultPath:
    def test_env_var_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRENDSPYG_COOKIES", str(tmp_path / "jar.json"))
        assert _default_cookie_path() == str(tmp_path / "jar.json")

    def test_defaults_beside_the_archive_db(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TRENDSPYG_COOKIES", raising=False)
        monkeypatch.setenv("TRENDSPYG_DB", str(tmp_path / "data" / "trendspyg.db"))
        assert _default_cookie_path() == str(tmp_path / "data" / "explore_cookies.json")


class TestLoad:
    def test_missing_file_is_empty(self, tmp_path):
        assert _load_cookies(str(tmp_path / "nope.json")) == []

    def test_corrupt_file_is_empty(self, tmp_path):
        p = tmp_path / "jar.json"
        p.write_text("{not json", encoding="utf-8")
        assert _load_cookies(str(p)) == []

    def test_non_list_is_empty(self, tmp_path):
        p = tmp_path / "jar.json"
        p.write_text(json.dumps({"name": "NID", "value": "x"}), encoding="utf-8")
        assert _load_cookies(str(p)) == []

    def test_keeps_only_well_formed_entries(self, tmp_path):
        p = tmp_path / "jar.json"
        p.write_text(json.dumps([GOOGLE[0], "junk", {"value": "no name"}]), encoding="utf-8")
        assert _load_cookies(str(p)) == [GOOGLE[0]]


class TestSave:
    def test_writes_google_cookies_only_and_roundtrips(self, tmp_path):
        driver = MagicMock()
        driver.get_cookies.return_value = GOOGLE + OTHER
        path = str(tmp_path / "sub" / "jar.json")  # directory created on demand

        assert _save_cookies(driver, path) == 2

        assert _load_cookies(path) == GOOGLE
        assert not any(
            name.startswith(".explore_cookies-") for name in os.listdir(tmp_path / "sub")
        )

    def test_nothing_google_writes_nothing(self, tmp_path):
        driver = MagicMock()
        driver.get_cookies.return_value = OTHER
        path = str(tmp_path / "jar.json")
        assert _save_cookies(driver, path) == 0
        assert not os.path.exists(path)

    def test_driver_error_is_swallowed(self, tmp_path):
        driver = MagicMock()
        driver.get_cookies.side_effect = WebDriverException("gone")
        assert _save_cookies(driver, str(tmp_path / "jar.json")) == 0

    def test_replaces_atomically(self, tmp_path):
        path = str(tmp_path / "jar.json")
        d1 = MagicMock()
        d1.get_cookies.return_value = [GOOGLE[0]]
        d2 = MagicMock()
        d2.get_cookies.return_value = [GOOGLE[1]]
        _save_cookies(d1, path)
        _save_cookies(d2, path)
        assert _load_cookies(path) == [GOOGLE[1]]


class TestInjectAndForget:
    def test_adds_each_cookie(self):
        driver = MagicMock()
        assert _inject_cookies(driver, GOOGLE) == 2
        assert driver.add_cookie.call_args_list == [call(GOOGLE[0]), call(GOOGLE[1])]

    def test_rejected_cookie_is_skipped(self):
        driver = MagicMock()
        driver.add_cookie.side_effect = [WebDriverException("bad domain"), None]
        assert _inject_cookies(driver, GOOGLE) == 1

    def test_forget_reports_whether_a_file_existed(self, tmp_path):
        p = tmp_path / "jar.json"
        p.write_text("[]", encoding="utf-8")
        assert _forget_cookies(str(p)) is True
        assert _forget_cookies(str(p)) is False
        assert clear_explore_cookies(str(p)) is False


class TestRememberSession:
    def test_ready_saves(self, tmp_path):
        driver = MagicMock()
        driver.get_cookies.return_value = GOOGLE
        path = str(tmp_path / "jar.json")
        _remember_session(driver, path, "ready", had_jar=False)
        assert _load_cookies(path) == GOOGLE

    def test_blocked_with_a_jar_forgets_it(self, tmp_path):
        p = tmp_path / "jar.json"
        p.write_text(json.dumps(GOOGLE), encoding="utf-8")
        _remember_session(MagicMock(), str(p), "blocked", had_jar=True)
        assert not p.exists()

    @pytest.mark.parametrize(
        "status,had_jar", [("blocked", False), ("throttled", True), ("timeout", True)]
    )
    def test_other_outcomes_leave_the_jar_alone(self, tmp_path, status, had_jar):
        p = tmp_path / "jar.json"
        p.write_text(json.dumps(GOOGLE), encoding="utf-8")
        driver = MagicMock()
        _remember_session(driver, str(p), status, had_jar=had_jar)
        assert _load_cookies(str(p)) == GOOGLE
        driver.get_cookies.assert_not_called()


class TestEngineWiring:
    """load → warm-up → inject → Explore URL → chart → remember, in that order."""

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._remember_session")
    @patch("trendspyg.explore._engine._await_chart", return_value="blocked")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver")
    def test_fetch_explore_injects_saved_jar_after_warm_up(
        self, bd, _dc, _aw, remember, _sleep, tmp_path
    ):
        p = tmp_path / "jar.json"
        p.write_text(json.dumps(GOOGLE), encoding="utf-8")
        driver = bd.return_value
        events = []
        driver.get.side_effect = lambda url: events.append(("get", url))
        driver.add_cookie.side_effect = lambda c: events.append(("cookie", c["name"]))

        with pytest.raises(RateLimitError):
            _fetch_explore("bitcoin", "US", "today 12-m", 0, True, False, False, cookie_path=str(p))

        assert events[0] == ("get", "https://trends.google.com/")
        assert events[1:3] == [("cookie", "NID"), ("cookie", "_ga")]
        assert events[3][0] == "get" and "explore?" in events[3][1]
        remember.assert_called_once_with(driver, str(p), "blocked", True)

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._remember_session")
    @patch("trendspyg.explore._engine._await_chart", return_value="blocked")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver")
    def test_fetch_explore_without_a_jar_file_still_remembers(
        self, bd, _dc, _aw, remember, _sleep, tmp_path
    ):
        driver = bd.return_value
        with pytest.raises(RateLimitError):
            _fetch_explore(
                "bitcoin",
                "US",
                "today 12-m",
                0,
                True,
                False,
                False,
                cookie_path=str(tmp_path / "jar.json"),
            )
        driver.add_cookie.assert_not_called()
        remember.assert_called_once_with(driver, str(tmp_path / "jar.json"), "blocked", False)

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._remember_session")
    @patch("trendspyg.explore._engine._await_chart", return_value="blocked")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver")
    def test_default_is_no_jar_at_all(self, bd, _dc, _aw, remember, _sleep):
        driver = bd.return_value
        with pytest.raises(RateLimitError):
            _fetch_explore("bitcoin", "US", "today 12-m", 0, True, False, False)
        driver.add_cookie.assert_not_called()
        remember.assert_not_called()

    @patch("trendspyg.explore._engine.time.sleep")
    @patch("trendspyg.explore._engine._remember_session")
    @patch("trendspyg.explore._engine._await_chart", return_value="blocked")
    @patch("trendspyg.explore._engine._dismiss_cookie_banner")
    @patch("trendspyg.explore._engine._build_driver")
    def test_fetch_comparison_is_wired_the_same_way(self, bd, _dc, _aw, remember, _sleep, tmp_path):
        p = tmp_path / "jar.json"
        p.write_text(json.dumps(GOOGLE), encoding="utf-8")
        driver = bd.return_value
        events = []
        driver.get.side_effect = lambda url: events.append(("get", url))
        driver.add_cookie.side_effect = lambda c: events.append(("cookie", c["name"]))

        with pytest.raises(RateLimitError):
            _fetch_comparison(["a", "b"], "US", "today 12-m", 0, True, False, cookie_path=str(p))

        assert events[0] == ("get", "https://trends.google.com/")
        assert events[1:3] == [("cookie", "NID"), ("cookie", "_ga")]
        assert "explore?" in events[3][1]
        remember.assert_called_once_with(driver, str(p), "blocked", True)


class TestPublicArgument:
    @pytest.mark.parametrize("bad", [True, "yes", "DISK", 1])
    def test_invalid_values_fail_fast(self, bad):
        with pytest.raises(InvalidParameterError) as exc_info:
            download_google_trends_explore("bitcoin", cookies=bad)
        assert "cookies='disk'" in str(exc_info.value)

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_disk_threads_the_default_jar_path(self, mock_fetch, monkeypatch, tmp_path):
        monkeypatch.setenv("TRENDSPYG_COOKIES", str(tmp_path / "jar.json"))
        download_google_trends_explore("bitcoin", cookies="disk")
        assert mock_fetch.call_args.kwargs["cookie_path"] == str(tmp_path / "jar.json")

    @patch("trendspyg.explore._fetch_explore", return_value=FAKE_FETCH)
    def test_off_by_default(self, mock_fetch):
        download_google_trends_interest_over_time("bitcoin")
        assert mock_fetch.call_args.kwargs["cookie_path"] is None

    @patch("trendspyg.explore._fetch_comparison", return_value=FAKE_COMPARISON)
    def test_comparison_threads_it_too(self, mock_fetch, monkeypatch, tmp_path):
        monkeypatch.setenv("TRENDSPYG_COOKIES", str(tmp_path / "jar.json"))
        download_google_trends_comparison(["a", "b"], cookies="disk")
        assert mock_fetch.call_args.kwargs["cookie_path"] == str(tmp_path / "jar.json")

    def test_clear_is_public(self, monkeypatch, tmp_path):
        p = tmp_path / "jar.json"
        p.write_text("[]", encoding="utf-8")
        monkeypatch.setenv("TRENDSPYG_COOKIES", str(p))
        assert trendspyg.clear_explore_cookies() is True
        assert not p.exists()
        assert trendspyg.clear_explore_cookies() is False
