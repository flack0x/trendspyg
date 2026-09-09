"""A cache hit must never pretend to be a newly observed snapshot."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from trendspyg import (
    InvalidParameterError,
    clear_rss_cache,
    download_google_trends_rss,
    download_google_trends_rss_async,
    read_archive,
)
from trendspyg.cli import cli
from trendspyg.downloader import validate_geo
from trendspyg.rss_downloader import _validate_geo_rss

XML = b"<rss><channel><item><title>coffee</title></item></channel></rss>"
STAMP = "2026-09-01T12:00:00+00:00"


@pytest.mark.parametrize("validate", [_validate_geo_rss, validate_geo])
def test_common_uk_mistake_suggests_gb(validate):
    with pytest.raises(InvalidParameterError, match="GB"):
        validate("UK")
    with pytest.raises(InvalidParameterError):
        validate("")


@pytest.fixture(autouse=True)
def clean_cache():
    clear_rss_cache()
    yield
    clear_rss_cache()


@pytest.mark.parametrize("cache", [True, "disk"])
@pytest.mark.parametrize("first_async", [False, True])
def test_cross_format_cross_sync_hits_keep_original_timestamp(tmp_path, cache, first_async):
    db = str(tmp_path / "history.sqlite3")
    response = MagicMock(content=XML)
    session = MagicMock()
    session.get.return_value.__aenter__.return_value = MagicMock(
        status=200, read=AsyncMock(return_value=XML)
    )
    with patch("trendspyg.rss_downloader._now_iso", return_value=STAMP):
        if first_async:
            asyncio.run(
                download_google_trends_rss_async(
                    session=session, cache=cache, archive=True, db_path=db
                )
            )
        else:
            with patch("trendspyg.rss_downloader.requests.get", return_value=response):
                download_google_trends_rss(cache=cache, archive=True, db_path=db)
    with patch(
        "trendspyg.rss_downloader.requests.get", side_effect=AssertionError("unexpected fetch")
    ):
        with patch(
            "trendspyg.rss_downloader._now_iso", side_effect=AssertionError("new timestamp")
        ):
            normalized = download_google_trends_rss(normalize=True, cache=cache, db_path=db)
            async_result = asyncio.run(
                download_google_trends_rss_async(normalize=True, cache=cache, db_path=db)
            )
            raw = download_google_trends_rss(envelope=True, cache=cache, db_path=db)
    assert normalized == async_result == read_archive(db_path=db)[0]
    assert normalized["fetched_at"] == raw["fetched_at"] == STAMP
    assert raw["trends"][0]["trend"] == "coffee"


def test_cli_disk_envelope_preserves_original_observation(tmp_path):
    db = str(tmp_path / "history.sqlite3")
    with patch("trendspyg.rss_downloader.requests.get", return_value=MagicMock(content=XML)):
        with patch("trendspyg.rss_downloader._now_iso", return_value=STAMP):
            download_google_trends_rss(cache="disk", db_path=db)
    clear_rss_cache()
    with patch(
        "trendspyg.rss_downloader.requests.get", side_effect=AssertionError("unexpected fetch")
    ):
        result = CliRunner().invoke(
            cli, ["rss", "--cache", "disk", "--db", db, "--envelope", "--output", "json", "--quiet"]
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["fetched_at"] == STAMP
