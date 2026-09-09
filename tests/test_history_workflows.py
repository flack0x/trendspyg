"""Consumer workflows must be able to create the history they later query."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from trendspyg import (
    clear_rss_cache,
    download_google_trends_rss_batch,
    download_google_trends_rss_batch_async,
    read_archive,
)
from trendspyg.cli import cli

XML = b"<rss><channel><item><title>coffee</title></item></channel></rss>"


@pytest.fixture(autouse=True)
def isolated_cache():
    clear_rss_cache()
    yield
    clear_rss_cache()


def test_cli_watch_records_baseline_even_when_no_events(tmp_path):
    db = str(tmp_path / "watch.sqlite3")
    with patch("trendspyg.rss_downloader.requests.get", return_value=MagicMock(content=XML)):
        result = CliRunner().invoke(
            cli, ["watch", "--geo", "GB", "--iterations", "1", "--archive", "--db", db, "--quiet"]
        )
    assert result.exit_code == 0, result.output
    assert result.output == ""
    history = CliRunner().invoke(cli, ["history", "--db", db, "--quiet"])
    assert history.exit_code == 0, history.output
    assert json.loads(history.output)[0]["trends"][0]["keyword"] == "coffee"


def test_cli_context_events_match_archived_observation(tmp_path):
    db = str(tmp_path / "watch.sqlite3")
    responses = [MagicMock(content=b"<rss><channel/></rss>"), MagicMock(content=XML)]
    with patch("trendspyg.rss_downloader.requests.get", side_effect=responses):
        result = CliRunner().invoke(
            cli,
            [
                "watch",
                "--geo",
                "gb",
                "--iterations",
                "2",
                "--interval",
                "0",
                "--archive",
                "--db",
                db,
                "--context",
                "--quiet",
            ],
        )
    assert result.exit_code == 0, result.output
    event = json.loads(result.output)
    assert event["keyword"] == "coffee" and event["geo"] == "GB"
    assert event["observed_at"] == read_archive(db_path=db)[0]["fetched_at"]


def test_sync_batch_disk_cache_reuses_observations(tmp_path):
    db = str(tmp_path / "batch.sqlite3")
    with patch("trendspyg.rss_downloader.requests.get", return_value=MagicMock(content=XML)) as get:
        first = download_google_trends_rss_batch(
            ["US", "GB"],
            normalize=True,
            archive=True,
            cache="disk",
            db_path=db,
            show_progress=False,
        )
        second = download_google_trends_rss_batch(
            ["US", "GB"],
            normalize=True,
            archive=True,
            cache="disk",
            db_path=db,
            show_progress=False,
        )
    assert get.call_count == 2
    assert first == second
    assert len(read_archive(db_path=db)) == 2


def test_async_batch_can_read_sync_disk_cache(tmp_path):
    db = str(tmp_path / "batch.sqlite3")
    with patch("trendspyg.rss_downloader.requests.get", return_value=MagicMock(content=XML)):
        first = download_google_trends_rss_batch(
            ["US", "GB"], normalize=True, cache="disk", db_path=db, show_progress=False
        )
    with patch("aiohttp.ClientSession.get", side_effect=AssertionError("unexpected network")):
        second = asyncio.run(
            download_google_trends_rss_batch_async(
                ["US", "GB"], normalize=True, cache="disk", db_path=db, show_progress=False
            )
        )
    assert first == second


@pytest.mark.parametrize("asynchronous", [False, True])
def test_batch_cache_false_reaches_each_fetch(asynchronous):
    if asynchronous:
        with patch(
            "trendspyg.rss_downloader.download_google_trends_rss_async", new_callable=AsyncMock
        ) as get:
            get.return_value = []
            asyncio.run(
                download_google_trends_rss_batch_async(["US"], cache=False, show_progress=False)
            )
    else:
        with patch("trendspyg.rss_downloader.download_google_trends_rss", return_value=[]) as get:
            download_google_trends_rss_batch(["US"], cache=False, show_progress=False)
    assert get.call_args.kwargs["cache"] is False
