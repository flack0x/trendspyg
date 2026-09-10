"""Topic lookup contracts: real response shape, errors, caching and CLI output."""

import json
from unittest.mock import Mock

import pytest
import requests
from click.testing import CliRunner

from trendspyg import (
    DownloadError,
    InvalidParameterError,
    ParseError,
    RateLimitError,
    get_keyword_suggestions,
)
from trendspyg import keywords as lookup
from trendspyg.cli import cli

TOPICS = [
    {"mid": "/m/014j1m", "title": "Apple", "type": "Fruit"},
    {"mid": "/m/0k8z", "title": "Apple", "type": "Technology company"},
]


@pytest.fixture(autouse=True)
def http(monkeypatch):
    lookup._cache.clear()
    response = Mock(status_code=200, text=")]}'\n" + json.dumps({"default": {"topics": TOPICS}}))
    get = Mock(return_value=response)
    monkeypatch.setattr(lookup.requests, "get", get)
    yield get
    lookup._cache.clear()


def test_preserves_distinct_meanings_and_encodes_query(http):
    assert get_keyword_suggestions(" café / C++ ", "fr", timeout=4) == TOPICS
    http.assert_called_once_with(
        "https://trends.google.com/trends/api/autocomplete/caf%C3%A9%20%2F%20C%2B%2B",
        params={"hl": "fr"},
        timeout=4,
    )


def test_cache_is_per_query_language_and_protected_from_caller_mutation(http):
    first = get_keyword_suggestions("apple")
    first[0]["title"] = "changed"
    second = get_keyword_suggestions(" apple ")
    assert second == TOPICS
    second.clear()
    assert get_keyword_suggestions("apple") == TOPICS
    assert http.call_count == 1
    get_keyword_suggestions("apple", "fr")
    get_keyword_suggestions("jaguar")
    assert http.call_count == 3


def test_cache_false_bypasses_both_reads_and_writes(http):
    assert get_keyword_suggestions("apple", cache=False) == TOPICS
    http.return_value.text = '{"default":{"topics":[]}}'
    assert get_keyword_suggestions("apple") == []
    http.return_value.text = json.dumps({"default": {"topics": TOPICS}})
    assert get_keyword_suggestions("apple", cache=False) == TOPICS
    assert get_keyword_suggestions("apple") == []
    assert http.call_count == 3


def test_cached_empty_result_expires_after_one_hour(http, monkeypatch):
    monkeypatch.setattr("trendspyg.utils.time.time", lambda: 100)
    http.return_value.text = '{"default":{"topics":[]}}'
    assert get_keyword_suggestions("missing") == []
    monkeypatch.setattr("trendspyg.utils.time.time", lambda: 3701)
    http.return_value.text = json.dumps({"default": {"topics": TOPICS}})
    assert get_keyword_suggestions("missing") == TOPICS
    assert http.call_count == 2


@pytest.mark.parametrize(
    "status,error",
    [(403, RateLimitError), (429, RateLimitError), (500, DownloadError), (404, DownloadError)],
)
def test_http_failure_is_not_retried_or_cached(http, status, error):
    http.return_value.status_code = status
    with pytest.raises(error):
        get_keyword_suggestions("apple")
    http.assert_called_once()
    http.return_value.status_code = 200
    assert get_keyword_suggestions("apple") == TOPICS
    assert http.call_count == 2


@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError])
def test_network_error_keeps_cause_and_is_not_retried(http, error):
    http.side_effect = error("failed")
    with pytest.raises(DownloadError) as caught:
        get_keyword_suggestions("apple")
    assert isinstance(caught.value.__cause__, error)
    http.assert_called_once()


@pytest.mark.parametrize(
    "text",
    [
        "<html>unavailable</html>",
        "null",
        "[]",
        "{}",
        '{"default":null}',
        '{"default":{"topics":null}}',
        '{"default":{"topics":{}}}',
        '{"default":{"topics":[null]}}',
        '{"default":{"topics":[{}]}}',
        '{"default":{"topics":[{"mid":3,"title":"Apple","type":"Fruit"}]}}',
        '{"default":{"topics":[{"mid":"/m/a","title":" ","type":"Fruit"}]}}',
    ],
)
def test_malformed_response_is_not_misreported_as_no_matches(http, text):
    http.return_value.text = text
    with pytest.raises(ParseError):
        get_keyword_suggestions("apple")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"keyword": ""},
        {"keyword": "  "},
        {"keyword": None},
        {"keyword": ["apple"]},
        {"language": ""},
        {"language": None},
        {"language": "en_US"},
        {"language": "en?x=1"},
        {"cache": "disk"},
        {"cache": 1},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": True},
        {"timeout": "10"},
        {"timeout": float("nan")},
        {"timeout": float("inf")},
    ],
)
def test_invalid_parameters_fail_before_network(http, kwargs):
    args = {"keyword": "apple", **kwargs}
    with pytest.raises(InvalidParameterError):
        get_keyword_suggestions(**args)
    http.assert_not_called()


@pytest.mark.parametrize("language", ["en-US", "fr", "es-419", "zh-Hant-TW"])
def test_language_tags_forwarded(http, language):
    get_keyword_suggestions("apple", language)
    assert http.call_args.kwargs["params"] == {"hl": language}


def test_cli_stdout_is_only_json_with_unicode(http):
    topics = [{"mid": "/m/test", "title": "Café", "type": "Boisson"}]
    http.return_value.text = json.dumps({"default": {"topics": topics}})
    result = CliRunner().invoke(
        cli, ["suggest", "-k", "café", "--language", "fr", "--no-cache", "--timeout", "4"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == topics
    assert http.call_args.kwargs["timeout"] == 4


def test_cli_empty_result_is_success(http):
    http.return_value.text = '{"default":{"topics":[]}}'
    result = CliRunner().invoke(cli, ["suggest", "-k", "missing"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


def test_cli_failure_has_nonzero_exit_and_no_fake_data(http):
    http.return_value.status_code = 429
    result = CliRunner().invoke(cli, ["suggest", "-k", "apple"])
    assert result.exit_code == 1
    assert "rate-limited" in result.output
    assert "[]" not in result.output
