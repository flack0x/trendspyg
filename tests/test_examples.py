"""Run the advertised workflows with real parsing and archives, offline."""

import io
import json
import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trendspyg import clear_rss_cache

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
XML = """<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
<item><title>قهوة</title><ht:approx_traffic>2K+</ht:approx_traffic>
<ht:news_item><ht:news_item_title>Café opens</ht:news_item_title>
<ht:news_item_url>https://example.test/story</ht:news_item_url>
<ht:news_item_source>The Guardian</ht:news_item_source></ht:news_item></item>
</channel></rss>""".encode(
    "utf-8"
)


def test_journalist_brief_handles_unicode_volume_and_sources(tmp_path):
    clear_rss_cache()
    main = runpy.run_path(str(EXAMPLES / "journalist_workflow.py"))["main"]
    # Reproduce Windows redirected stdout under a legacy code page.
    output = io.BytesIO()
    stream = io.TextIOWrapper(output, encoding="cp1252")
    with patch("sys.stdout", stream):
        with patch("trendspyg.rss_downloader.requests.get", return_value=MagicMock(content=XML)):
            main(output_dir=str(tmp_path))
    stream.flush()
    assert "قهوة" in output.getvalue().decode("utf-8")
    report = (tmp_path / "brief.md").read_text(encoding="utf-8")
    assert "2,000" in report
    assert "The Guardian" in report and "https://example.test/story" in report
    assert "VERIFIED" not in report
    assert "not independent verification" in report
    assert json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8"))["count"] == 1
    clear_rss_cache()


def test_analysis_creates_dataset_and_real_second_observation_diff(tmp_path, capsys):
    import pandas as pd

    main = runpy.run_path(str(EXAMPLES / "data_analysis.py"))["main"]
    with patch("trendspyg.rss_downloader.requests.get", return_value=MagicMock(content=XML)):
        main(output_dir=str(tmp_path))
    assert "First observation" in capsys.readouterr().out
    first = json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8"))
    # Expire only the disk cache; preserve the recorded observation.
    import sqlite3

    with sqlite3.connect(tmp_path / "history.sqlite3") as conn:
        conn.execute("UPDATE cache SET stored_at=0")
    with patch(
        "trendspyg.rss_downloader.requests.get",
        return_value=MagicMock(content=XML.replace(b"2K+", b"5M+")),
    ):
        main(output_dir=str(tmp_path))
    rows = pd.read_csv(tmp_path / "trends.csv")
    assert rows.loc[0, "volume_min"] == 5_000_000
    assert rows.loc[0, "geo"] == "US" and rows.loc[0, "source"] == "rss"
    changes = json.loads((tmp_path / "changes.json").read_text(encoding="utf-8"))
    assert changes[0]["event"] == "volume_up"
    assert changes[0]["prev_volume_min"] == 2000
    second = json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8"))
    assert first["fetched_at"] != second["fetched_at"]


def test_keyword_study_excludes_partial_period_from_statistics_and_chart(tmp_path):
    pytest.importorskip("matplotlib")
    env = {
        "keyword": "coffee",
        "geo": "US",
        "timeframe": "today 12-m",
        "gprop": "",
        "fetched_at": "2026-09-01T00:00:00+00:00",
        "is_empty": False,
        "related_queries": {"top": [{"query": "coffee table"}], "rising": []},
        "interest_over_time": [
            {"date": f"2026-08-{i:02d}T00:00:00+00:00", "value": value, "is_partial": i == 9}
            for i, value in enumerate([20, 20, 20, 20, 40, 40, 40, 40, 100], 1)
        ],
    }
    with patch("trendspyg.download_google_trends_explore", return_value=env) as fetch:
        main = runpy.run_path(str(EXAMPLES / "keyword_study.py"))["main"]
        main(output_dir=str(tmp_path))
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["recent_four_mean"] == 40
    assert summary["preceding_four_mean"] == 20
    assert summary["excluded_partial_periods"] == 1
    assert (tmp_path / "interest.png").stat().st_size > 1000
    assert fetch.call_count == 1
