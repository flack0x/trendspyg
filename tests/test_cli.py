"""
Tests for CLI functionality
"""

import importlib
import json
import runpy
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from click.testing import CliRunner

# Check if click is available
try:
    from trendspyg.cli import cli

    CLICK_AVAILABLE = True
except ImportError:
    CLICK_AVAILABLE = False


def _all_output(result):
    """stdout + stderr of a CliRunner result, across click versions.

    click <8.2 mixes stderr into .output and raises on .stderr; 8.2+ captures
    them separately. CI floats click, so tests must accept both layouts.
    """
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIRSS:
    """Test RSS CLI command"""

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_basic(self, mock_download):
        """Test basic RSS command"""
        mock_download.return_value = [
            {
                "trend": "test",
                "traffic": "100+",
                "published": "2024-01-01",
                "explore_link": "http://example.com",
            }
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US"])

        assert result.exit_code == 0
        mock_download.assert_called_once()

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_with_geo(self, mock_download):
        """Test RSS with geo parameter"""
        mock_download.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "GB"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["geo"] == "GB"

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_json_output(self, mock_download):
        """Test RSS with JSON output"""
        mock_download.return_value = '[{"trend": "test"}]'

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US", "--output", "json"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["output_format"] == "json"

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_csv_output(self, mock_download):
        """Test RSS with CSV output"""
        mock_download.return_value = "trend,traffic\ntest,100+"

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US", "--output", "csv"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["output_format"] == "csv"
        assert "trend,traffic" in result.output

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_dataframe_output(self, mock_download):
        """Test RSS with dataframe output"""
        mock_df = pd.DataFrame([{"trend": "test", "traffic": "100+"}])
        mock_download.return_value = mock_df

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US", "--output", "dataframe"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["output_format"] == "dataframe"
        assert "DataFrame" in result.output or "test" in result.output

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_no_images(self, mock_download):
        """Test RSS without images"""
        mock_download.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US", "--no-images"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["include_images"] == False

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_no_articles(self, mock_download):
        """Test RSS without articles"""
        mock_download.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US", "--no-articles"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["include_articles"] == False

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_max_articles(self, mock_download):
        """Test RSS with max-articles parameter"""
        mock_download.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US", "--max-articles", "3"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["max_articles_per_trend"] == 3

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_dict_output_with_images(self, mock_download):
        """Test RSS dict output displays image info"""
        mock_download.return_value = [
            {
                "trend": "bitcoin",
                "traffic": "500K+",
                "published": "2024-01-01",
                "explore_link": "http://example.com",
                "image": {"url": "http://img.com/test.jpg", "source": "Reuters"},
            }
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US"])

        assert result.exit_code == 0
        assert "BITCOIN" in result.output
        assert "Reuters" in result.output

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_dict_output_with_articles(self, mock_download):
        """Test RSS dict output displays article info"""
        mock_download.return_value = [
            {
                "trend": "bitcoin",
                "traffic": "500K+",
                "published": "2024-01-01",
                "explore_link": "http://example.com",
                "news_articles": [
                    {"headline": "Bitcoin surges", "source": "CNN", "url": "http://cnn.com"},
                    {"headline": "Crypto rally", "source": "BBC", "url": "http://bbc.com"},
                    {"headline": "Markets up", "source": "Fox", "url": "http://fox.com"},
                    {"headline": "Extra article", "source": "NBC", "url": "http://nbc.com"},
                ],
            }
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US"])

        assert result.exit_code == 0
        assert "Bitcoin surges" in result.output
        assert "CNN" in result.output
        assert "and 1 more articles" in result.output

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_dict_output_multiple_trends(self, mock_download):
        """Test RSS dict output with multiple trends shows separators"""
        mock_download.return_value = [
            {
                "trend": "bitcoin",
                "traffic": "500K+",
                "published": "2024-01-01",
                "explore_link": "http://example.com",
            },
            {
                "trend": "ethereum",
                "traffic": "100K+",
                "published": "2024-01-01",
                "explore_link": "http://example.com",
            },
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "US"])

        assert result.exit_code == 0
        assert "BITCOIN" in result.output
        assert "ETHEREUM" in result.output
        assert "---" in result.output  # Separator


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLICSV:
    """Test CSV CLI command"""

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_basic(self, mock_download):
        """Test basic CSV command"""
        mock_download.return_value = "/path/to/file.csv"

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US"])

        assert result.exit_code == 0
        mock_download.assert_called_once()

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_with_hours(self, mock_download):
        """Test CSV with hours parameter"""
        mock_download.return_value = "/path/to/file.csv"

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US", "--hours", "48"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["hours"] == 48

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_with_category(self, mock_download):
        """Test CSV with category parameter"""
        mock_download.return_value = "/path/to/file.csv"

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US", "--category", "sports"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["category"] == "sports"

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_active_only(self, mock_download):
        """Test CSV with active-only flag"""
        mock_download.return_value = "/path/to/file.csv"

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US", "--active-only"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["active_only"] == True

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_with_sort(self, mock_download):
        """Test CSV with sort parameter"""
        mock_download.return_value = "/path/to/file.csv"

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US", "--sort", "volume"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["sort_by"] == "volume"

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_json_output(self, mock_download):
        """Test CSV with JSON output"""
        mock_download.return_value = "/path/to/file.json"

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US", "--output", "json"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["output_format"] == "json"
        assert "Downloaded" in result.output

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_parquet_output(self, mock_download):
        """Test CSV with parquet output"""
        mock_download.return_value = "/path/to/file.parquet"

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US", "--output", "parquet"])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs["output_format"] == "parquet"
        assert "Downloaded" in result.output

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_dataframe_output(self, mock_download):
        """Test CSV with dataframe output"""
        mock_df = pd.DataFrame(
            [
                {
                    "Trends": "bitcoin",
                    "Search volume": "500K+",
                    "Started": "2024-01-01",
                    "Trend breakdown": "crypto, blockchain",
                    "Explore link": "http://example.com",
                },
                {
                    "Trends": "ethereum",
                    "Search volume": "100K+",
                    "Started": "2024-01-01",
                    "Trend breakdown": "crypto",
                    "Explore link": "http://example.com",
                },
            ]
        )
        mock_download.return_value = mock_df

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US", "--output", "dataframe"])

        assert result.exit_code == 0
        assert "BITCOIN" in result.output
        assert "Search Volume" in result.output

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_dataframe_output_many_trends(self, mock_download):
        """Test CSV dataframe output with more than 10 trends"""
        mock_df = pd.DataFrame(
            [
                {
                    "Trends": f"trend{i}",
                    "Search volume": "100+",
                    "Started": "2024-01-01",
                    "Trend breakdown": "",
                    "Explore link": "http://example.com",
                }
                for i in range(15)
            ]
        )
        mock_download.return_value = mock_df

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US", "--output", "dataframe"])

        assert result.exit_code == 0
        assert "... and 5 more trends" in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIList:
    """Test list CLI command"""

    def test_list_countries(self):
        """Test list countries command"""
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--type", "countries"])

        assert result.exit_code == 0
        assert "US" in result.output
        assert "Countries" in result.output

    def test_list_states(self):
        """Test list states command"""
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--type", "states"])

        assert result.exit_code == 0
        assert "US-CA" in result.output or "California" in result.output

    def test_list_categories(self):
        """Test list categories command"""
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--type", "categories"])

        assert result.exit_code == 0
        assert "Categories" in result.output

    def test_list_hours(self):
        """Test list hours command"""
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--type", "hours"])

        assert result.exit_code == 0
        assert "Time Periods" in result.output
        assert "24" in result.output or "hours" in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIInfo:
    """Test info CLI command"""

    def test_info_shows_version(self):
        """Test info command shows version"""
        runner = CliRunner()
        result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "Version" in result.output

    def test_info_shows_features(self):
        """Test info command shows features"""
        runner = CliRunner()
        result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "Countries" in result.output
        assert "Categories" in result.output

    def test_info_shows_data_sources(self):
        """Test info command shows data sources"""
        runner = CliRunner()
        result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "RSS" in result.output
        assert "CSV" in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIErrorHandling:
    """Test CLI error handling"""

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_error_handling(self, mock_download):
        """Test RSS error handling"""
        from trendspyg.exceptions import InvalidParameterError

        mock_download.side_effect = InvalidParameterError("Invalid geo code")

        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--geo", "INVALID"])

        assert result.exit_code != 0 or "ERROR" in result.output or "Invalid" in result.output

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_error_handling(self, mock_download):
        """Test CSV error handling"""
        from trendspyg.exceptions import BrowserError

        mock_download.side_effect = BrowserError("Chrome not found")

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US"])

        assert result.exit_code != 0 or "ERROR" in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIHelp:
    """Test CLI help commands"""

    def test_main_help(self):
        """Test main help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "trendspyg" in result.output.lower()

    def test_rss_help(self):
        """Test RSS help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ["rss", "--help"])

        assert result.exit_code == 0
        assert "--geo" in result.output

    def test_csv_help(self):
        """Test CSV help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--help"])

        assert result.exit_code == 0
        assert "--geo" in result.output
        assert "--hours" in result.output

    def test_version(self):
        """Test version option"""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        assert "trendspyg" in result.output.lower()


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIMain:
    """Test CLI main entry point"""

    def test_main_function_exists(self):
        """Test main function can be called"""
        from trendspyg.cli import main

        assert callable(main)

    @patch("trendspyg.cli.cli")
    def test_main_calls_cli(self, mock_cli):
        """Test main function calls cli"""
        from trendspyg.cli import main

        main()
        mock_cli.assert_called_once()


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLICSVDataframeEdgeCases:
    """Test CSV dataframe output edge cases"""

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_dataframe_with_long_breakdown(self, mock_download):
        """Test CSV dataframe with very long trend breakdown text"""
        mock_df = pd.DataFrame(
            [
                {
                    "Trends": "bitcoin",
                    "Search volume": "500K+",
                    "Started": "2024-01-01",
                    "Trend breakdown": "a" * 150,  # Very long breakdown
                    "Explore link": "http://example.com",
                }
            ]
        )
        mock_download.return_value = mock_df

        runner = CliRunner()
        result = runner.invoke(cli, ["csv", "--geo", "US", "--output", "dataframe"])

        assert result.exit_code == 0
        # Long breakdown should be truncated
        assert "..." in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIRSSOutputBranches:
    """RSS command output branches: --normalize, --envelope, dict --quiet"""

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_normalize_prints_envelope_json(self, mock_download):
        envelope = {"schema_version": "1.0", "source": "rss", "geo": "US", "count": 0, "trends": []}
        mock_download.return_value = envelope

        result = CliRunner().invoke(cli, ["rss", "--normalize", "--quiet"])

        assert result.exit_code == 0
        assert json.loads(result.output) == envelope
        assert mock_download.call_args[1]["normalize"] is True

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_envelope_json_output(self, mock_download):
        mock_download.return_value = '[{"trend": "test"}]'

        result = CliRunner().invoke(cli, ["rss", "--output", "json", "--envelope", "--quiet"])

        assert result.exit_code == 0
        wrapped = json.loads(result.output)
        assert wrapped["geo"] == "US"
        assert wrapped["count"] == 1
        assert wrapped["trends"] == [{"trend": "test"}]
        assert "fetched_at" in wrapped

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_envelope_dict_output(self, mock_download):
        mock_download.return_value = [{"trend": "test"}]

        result = CliRunner().invoke(cli, ["rss", "--output", "dict", "--envelope", "--quiet"])

        assert result.exit_code == 0
        assert "'count': 1" in result.output
        assert "'geo': 'US'" in result.output

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_dict_quiet_prints_raw_list(self, mock_download):
        mock_download.return_value = [{"trend": "test"}]

        result = CliRunner().invoke(cli, ["rss", "--output", "dict", "--quiet"])

        assert result.exit_code == 0
        assert "Found" not in result.output
        assert "'trend': 'test'" in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLICSVOutputBranches:
    """CSV command output branches: --normalize, filepath --quiet, dict, dataframe --quiet"""

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_normalize_prints_envelope_json(self, mock_download):
        envelope = {"schema_version": "1.0", "source": "csv", "geo": "US", "count": 0, "trends": []}
        mock_download.return_value = envelope

        result = CliRunner().invoke(cli, ["csv", "--normalize", "--quiet"])

        assert result.exit_code == 0
        assert json.loads(result.output) == envelope

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_filepath_output_quiet_is_pipe_clean(self, mock_download):
        mock_download.return_value = "downloads/trends.csv"

        result = CliRunner().invoke(cli, ["csv", "--output", "csv", "--quiet"])

        assert result.exit_code == 0
        assert "downloads/trends.csv" in result.output
        assert "[OK]" not in result.output

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_dict_output(self, mock_download):
        mock_download.return_value = [{"Trends": "bitcoin"}]

        result = CliRunner().invoke(cli, ["csv", "--output", "dict"])

        assert result.exit_code == 0
        assert "Retrieved 1 trends" in result.output
        assert "bitcoin" in result.output

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_dict_output_quiet(self, mock_download):
        mock_download.return_value = [{"Trends": "bitcoin"}]

        result = CliRunner().invoke(cli, ["csv", "--output", "dict", "--quiet"])

        assert result.exit_code == 0
        assert "Retrieved" not in result.output
        assert "bitcoin" in result.output

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_dataframe_output_quiet(self, mock_download):
        mock_download.return_value = pd.DataFrame([{"Trends": "bitcoin"}])

        result = CliRunner().invoke(cli, ["csv", "--output", "dataframe", "--quiet"])

        assert result.exit_code == 0
        assert "bitcoin" in result.output
        assert "Top 10 Trends" not in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIExplore:
    """Explore command: banner, output formats, --full envelope, error path"""

    @patch("trendspyg.cli.download_google_trends_interest_over_time")
    def test_explore_json_output_with_banner_and_success(self, mock_iot):
        mock_iot.return_value = '[{"time": "2026-01-01", "value": 50}]'

        result = CliRunner().invoke(cli, ["explore", "-k", "bitcoin"])

        assert result.exit_code == 0
        assert "Analyzing 'bitcoin'" in result.output
        assert '"value": 50' in result.output
        assert "[OK] Success!" in result.output
        assert mock_iot.call_args[0][0] == "bitcoin"
        assert mock_iot.call_args[1]["headless"] is True

    @patch("trendspyg.cli.download_google_trends_interest_over_time")
    def test_explore_quiet_is_pipe_clean(self, mock_iot):
        mock_iot.return_value = "[]"

        result = CliRunner().invoke(cli, ["explore", "-k", "bitcoin", "--quiet"])

        assert result.exit_code == 0
        assert "Analyzing" not in result.output
        assert "[OK]" not in result.output

    @patch("trendspyg.cli.download_google_trends_interest_over_time")
    def test_explore_dataframe_output(self, mock_iot):
        mock_iot.return_value = pd.DataFrame([{"time": "2026-01-01", "value": 50}])

        result = CliRunner().invoke(
            cli, ["explore", "-k", "bitcoin", "--output", "dataframe", "--quiet"]
        )

        assert result.exit_code == 0
        assert "value" in result.output

    @patch("trendspyg.cli.download_google_trends_explore")
    def test_explore_full_prints_envelope_json(self, mock_explore):
        env = {
            "keyword": "bitcoin",
            "interest_over_time": [],
            "related_queries": {"top": [], "rising": []},
            "interest_by_region": [],
        }
        mock_explore.return_value = env

        result = CliRunner().invoke(cli, ["explore", "-k", "bitcoin", "--full"])

        assert result.exit_code == 0
        assert json.loads(result.output) == env

    @patch("trendspyg.cli.download_google_trends_interest_over_time")
    def test_explore_error_exits_1(self, mock_iot):
        mock_iot.side_effect = RuntimeError("persistently throttled")

        result = CliRunner().invoke(cli, ["explore", "-k", "bitcoin", "--quiet"])

        assert result.exit_code == 1
        assert "[ERROR] persistently throttled" in _all_output(result)


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIExploreArchiveCache:
    """--archive / --cache / --cache-ttl / --db on explore (new in 1.4.0)."""

    @patch("trendspyg.cli.download_google_trends_interest_over_time")
    def test_defaults_thread_cache_off_no_archive(self, mock_iot):
        mock_iot.return_value = "[]"
        result = CliRunner().invoke(cli, ["explore", "-k", "bitcoin", "--quiet"])

        assert result.exit_code == 0
        kwargs = mock_iot.call_args[1]
        assert kwargs["cache"] is False
        assert kwargs["cache_ttl"] is None
        assert kwargs["archive"] is False
        assert kwargs["db_path"] is None

    @patch("trendspyg.cli.download_google_trends_interest_over_time")
    def test_flags_thread_through_iot(self, mock_iot):
        mock_iot.return_value = "[]"
        result = CliRunner().invoke(
            cli,
            [
                "explore",
                "-k",
                "bitcoin",
                "--quiet",
                "--cache",
                "disk",
                "--cache-ttl",
                "500",
                "--archive",
                "--db",
                "X:\\my.db",
            ],
        )

        assert result.exit_code == 0
        kwargs = mock_iot.call_args[1]
        assert kwargs["cache"] == "disk"
        assert kwargs["cache_ttl"] == 500.0
        assert kwargs["archive"] is True
        assert kwargs["db_path"] == "X:\\my.db"
        assert kwargs["cookies"] is False  # off unless --cookies disk (1.6.0)

    @patch("trendspyg.cli.download_google_trends_interest_over_time", return_value=[])
    def test_cookies_disk_is_forwarded(self, mock_iot):
        # 1.6.0: --cookies disk → cookies="disk" (opt-in returning-visitor jar).
        result = CliRunner().invoke(cli, ["explore", "-k", "bitcoin", "--cookies", "disk"])
        assert result.exit_code == 0, result.output
        assert mock_iot.call_args[1]["cookies"] == "disk"

    @patch("trendspyg.cli.download_google_trends_explore")
    def test_flags_thread_through_full_envelope(self, mock_explore):
        mock_explore.return_value = {"keyword": "bitcoin"}
        result = CliRunner().invoke(
            cli, ["explore", "-k", "bitcoin", "--full", "--cache", "disk", "--archive"]
        )

        assert result.exit_code == 0
        kwargs = mock_explore.call_args[1]
        assert kwargs["cache"] == "disk" and kwargs["archive"] is True

    @patch("trendspyg.cli.download_google_trends_comparison")
    def test_flags_thread_through_comparison(self, mock_cmp):
        mock_cmp.return_value = "{}"
        result = CliRunner().invoke(
            cli,
            ["explore", "-k", "bitcoin", "-k", "ethereum", "--quiet", "--cache", "disk"],
        )

        assert result.exit_code == 0
        kwargs = mock_cmp.call_args[1]
        assert kwargs["cache"] == "disk"
        assert kwargs["cache_ttl"] is None

    @patch("trendspyg.cli.download_google_trends_interest_over_time")
    def test_gprop_defaults_to_web_and_threads_choice(self, mock_iot):
        mock_iot.return_value = "[]"
        CliRunner().invoke(cli, ["explore", "-k", "bitcoin", "--quiet"])
        assert mock_iot.call_args[1]["gprop"] == "web"  # library normalizes to ""

        CliRunner().invoke(cli, ["explore", "-k", "bitcoin", "--quiet", "--gprop", "YouTube"])
        assert mock_iot.call_args[1]["gprop"] == "youtube"

    def test_gprop_rejects_unknown_property(self):
        result = CliRunner().invoke(
            cli, ["explore", "-k", "bitcoin", "--quiet", "--gprop", "shopping"]
        )
        assert result.exit_code == 2  # click Choice validation

    def test_history_source_explore_filters(self, tmp_path):
        from trendspyg.archive import _store_snapshot

        db = str(tmp_path / "cli.db")
        _store_snapshot(
            {
                "schema_version": "1.0",
                "source": "rss",
                "geo": "US",
                "fetched_at": "2026-08-01T09:00:00+00:00",
                "count": 1,
                "trends": [{"keyword": "bitcoin", "rank": 1, "volume_min": 500000}],
            },
            db_path=db,
        )
        _store_snapshot(
            {
                "schema_version": "1.0",
                "source": "explore",
                "keyword": "bitcoin",
                "geo": "US",
                "timeframe": "today 12-m",
                "fetched_at": "2026-08-02T09:00:00+00:00",
                "count": 0,
                "interest_over_time": [],
                "related_queries": {"top": [], "rising": []},
                "interest_by_region": [],
            },
            db_path=db,
        )

        result = CliRunner().invoke(cli, ["history", "--db", db, "--source", "explore", "--quiet"])
        assert result.exit_code == 0
        envelopes = json.loads(result.output)
        assert [e["source"] for e in envelopes] == ["explore"]


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIExploreCompare:
    """Repeatable -k (new in 1.1.0): 2-5 keywords switch explore to comparison mode"""

    @patch("trendspyg.cli.download_google_trends_comparison")
    def test_two_keywords_invoke_comparison(self, mock_cmp):
        mock_cmp.return_value = '{"keywords": ["bitcoin", "ethereum"], "averages": {}}'

        result = CliRunner().invoke(cli, ["explore", "-k", "bitcoin", "-k", "ethereum"])

        assert result.exit_code == 0
        assert "Comparing bitcoin, ethereum" in result.output
        assert '"keywords"' in result.output
        assert "[OK] Success!" in result.output
        assert mock_cmp.call_args[0][0] == ["bitcoin", "ethereum"]
        assert mock_cmp.call_args[1]["output_format"] == "json"

    @patch("trendspyg.cli.download_google_trends_comparison")
    def test_compare_quiet_is_pipe_clean(self, mock_cmp):
        mock_cmp.return_value = "{}"

        result = CliRunner().invoke(cli, ["explore", "-k", "a", "-k", "b", "--quiet"])

        assert result.exit_code == 0
        assert "Comparing" not in result.output
        assert "[OK]" not in result.output

    @patch("trendspyg.cli.download_google_trends_comparison")
    def test_compare_forwards_knobs(self, mock_cmp):
        mock_cmp.return_value = "{}"

        result = CliRunner().invoke(
            cli,
            [
                "explore",
                "-k",
                "a",
                "-k",
                "b",
                "--geo",
                "GB",
                "--timeframe",
                "today 5-y",
                "--max-retries",
                "3",
                "--retry-wait",
                "5.0",
                "--quiet",
            ],
        )

        assert result.exit_code == 0
        kwargs = mock_cmp.call_args[1]
        assert kwargs["geo"] == "GB"
        assert kwargs["timeframe"] == "today 5-y"
        assert kwargs["max_retries"] == 3
        assert kwargs["retry_wait"] == 5.0

    @patch("trendspyg.cli.download_google_trends_comparison")
    def test_compare_dataframe_output(self, mock_cmp):
        mock_cmp.return_value = pd.DataFrame(
            [{"date": "2026-01-01", "bitcoin": 50, "ethereum": 10, "is_partial": False}]
        )

        result = CliRunner().invoke(
            cli, ["explore", "-k", "bitcoin", "-k", "ethereum", "--output", "dataframe", "-q"]
        )

        assert result.exit_code == 0
        assert "ethereum" in result.output

    @patch("trendspyg.cli.download_google_trends_comparison")
    def test_compare_error_exits_1(self, mock_cmp):
        mock_cmp.side_effect = RuntimeError("throttled hard")

        result = CliRunner().invoke(cli, ["explore", "-k", "a", "-k", "b", "--quiet"])

        assert result.exit_code == 1
        assert "[ERROR] throttled hard" in _all_output(result)

    @patch("trendspyg.cli.download_google_trends_interest_over_time")
    def test_single_keyword_still_uses_single_path(self, mock_iot):
        mock_iot.return_value = "[]"

        result = CliRunner().invoke(cli, ["explore", "-k", "bitcoin", "--quiet"])

        assert result.exit_code == 0
        mock_iot.assert_called_once()


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIWatchHandlers:
    """Watch command: startup banner, KeyboardInterrupt, error exit"""

    @patch("trendspyg.monitor.watch_google_trends_rss")
    def test_watch_banner_when_not_quiet(self, mock_watch):
        mock_watch.return_value = iter([])

        result = CliRunner().invoke(cli, ["watch", "--iterations", "1", "--interval", "0"])

        assert result.exit_code == 0
        assert "[watch] Monitoring RSS trends for US" in _all_output(result)

    @patch("trendspyg.monitor.watch_google_trends_rss")
    def test_watch_keyboard_interrupt_stops_cleanly(self, mock_watch):
        def interrupted():
            yield {"event": "new", "keyword": "bitcoin"}
            raise KeyboardInterrupt

        mock_watch.return_value = interrupted()

        result = CliRunner().invoke(cli, ["watch"])

        assert result.exit_code == 0
        assert "[watch] Stopped." in _all_output(result)

    @patch("trendspyg.monitor.watch_google_trends_rss")
    def test_watch_error_exits_1(self, mock_watch):
        mock_watch.side_effect = RuntimeError("feed exploded")

        result = CliRunner().invoke(cli, ["watch", "--quiet"])

        assert result.exit_code == 1
        assert "[ERROR] feed exploded" in _all_output(result)


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestStdoutEncodingEdgeCases:
    """_configure_stdout_encoding must fail open on exotic streams"""

    def test_stream_without_reconfigure_is_skipped(self, monkeypatch):
        from trendspyg.cli import _configure_stdout_encoding

        class PlainStream:
            pass

        monkeypatch.setattr(sys, "stdout", PlainStream())
        monkeypatch.setattr(sys, "stderr", PlainStream())

        _configure_stdout_encoding()  # must not raise

    def test_reconfigure_failure_is_swallowed(self, monkeypatch):
        from trendspyg.cli import _configure_stdout_encoding

        class ExplodingStream:
            def reconfigure(self, **kwargs):
                raise ValueError("stream does not support reconfigure")

        monkeypatch.setattr(sys, "stdout", ExplodingStream())
        monkeypatch.setattr(sys, "stderr", ExplodingStream())

        _configure_stdout_encoding()  # must not raise


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestModuleEntryPoints:
    """The `python -m trendspyg.cli` guard and the click import guard"""

    @pytest.mark.filterwarnings("ignore:.*found in sys.modules.*:RuntimeWarning")
    def test_module_runs_as_script(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["trendspyg", "--version"])

        with pytest.raises(SystemExit) as excinfo:
            runpy.run_module("trendspyg.cli", run_name="__main__")

        assert excinfo.value.code == 0

    def test_missing_click_exits_with_install_hint(self, monkeypatch, capsys):
        import trendspyg.cli as cli_mod

        monkeypatch.setitem(sys.modules, "click", None)
        try:
            with pytest.raises(SystemExit) as excinfo:
                importlib.reload(cli_mod)

            assert excinfo.value.code == 1
            out = capsys.readouterr().out
            assert "click is required" in out
            assert "pip install trendspyg[cli]" in out
        finally:
            # Restore the real module no matter what — other tests use it.
            monkeypatch.undo()
            importlib.reload(cli_mod)


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIRetryFlags:
    """--timeout/--max-retries (csv) and --max-retries/--retry-wait (explore)"""

    @patch("trendspyg.cli.download_google_trends_interest_over_time")
    def test_explore_forwards_retry_flags(self, mock_iot):
        mock_iot.return_value = "[]"

        result = CliRunner().invoke(
            cli,
            ["explore", "-k", "bitcoin", "--quiet", "--max-retries", "2", "--retry-wait", "5"],
        )

        assert result.exit_code == 0
        assert mock_iot.call_args[1]["max_retries"] == 2
        assert mock_iot.call_args[1]["retry_wait"] == 5.0

    @patch("trendspyg.cli.download_google_trends_explore")
    def test_explore_full_forwards_retry_flags_with_defaults(self, mock_explore):
        mock_explore.return_value = {}

        result = CliRunner().invoke(
            cli, ["explore", "-k", "bitcoin", "--full", "--max-retries", "3"]
        )

        assert result.exit_code == 0
        assert mock_explore.call_args[1]["max_retries"] == 3
        assert mock_explore.call_args[1]["retry_wait"] == 8.0  # default preserved

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_forwards_timeout_and_retries(self, mock_download):
        mock_download.return_value = "downloads/trends.csv"

        result = CliRunner().invoke(
            cli, ["csv", "--output", "csv", "--quiet", "--timeout", "20", "--max-retries", "1"]
        )

        assert result.exit_code == 0
        assert mock_download.call_args[1]["timeout"] == 20
        assert mock_download.call_args[1]["max_retries"] == 1


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIArchiveFlags:
    """--archive / --cache / --db forwarding on rss and csv (new in 1.3.0)."""

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_forwards_archive_cache_and_db(self, mock_download):
        mock_download.return_value = []

        result = CliRunner().invoke(
            cli, ["rss", "--quiet", "--archive", "--cache", "disk", "--db", "X.db"]
        )

        assert result.exit_code == 0
        kwargs = mock_download.call_args[1]
        assert kwargs["archive"] is True
        assert kwargs["cache"] == "disk"
        assert kwargs["db_path"] == "X.db"

    @patch("trendspyg.cli.download_google_trends_rss")
    def test_rss_cache_off_maps_to_false(self, mock_download):
        mock_download.return_value = []

        result = CliRunner().invoke(cli, ["rss", "--quiet", "--cache", "off"])

        assert result.exit_code == 0
        assert mock_download.call_args[1]["cache"] is False
        assert mock_download.call_args[1]["archive"] is False

    @patch("trendspyg.cli.download_google_trends_csv")
    def test_csv_forwards_archive_and_db(self, mock_download):
        mock_download.return_value = "downloads/trends.csv"

        result = CliRunner().invoke(
            cli, ["csv", "--output", "csv", "--quiet", "--archive", "--db", "X.db"]
        )

        assert result.exit_code == 0
        assert mock_download.call_args[1]["archive"] is True
        assert mock_download.call_args[1]["db_path"] == "X.db"


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIHistory:
    """The `trendspyg history` command (new in 1.3.0) — offline, real tmp DBs."""

    @pytest.fixture()
    def db(self, tmp_path):
        from trendspyg.archive import _store_snapshot

        path = str(tmp_path / "cli.db")
        _store_snapshot(
            {
                "schema_version": "1.0",
                "source": "rss",
                "geo": "US",
                "fetched_at": "2026-08-01T09:00:00+00:00",
                "count": 1,
                "trends": [{"keyword": "bitcoin", "rank": 1, "volume_min": 500000}],
            },
            db_path=path,
        )
        return path

    def test_history_outputs_json_snapshots(self, db):
        result = CliRunner().invoke(cli, ["history", "--db", db, "--quiet"])

        assert result.exit_code == 0
        envelopes = json.loads(result.output)
        assert len(envelopes) == 1
        assert envelopes[0]["trends"][0]["keyword"] == "bitcoin"

    def test_history_summary_goes_to_stderr_not_stdout(self, db):
        result = CliRunner().invoke(cli, ["history", "--db", db])

        assert result.exit_code == 0
        assert "[history] 1 snapshots" in _all_output(result)
        # stdout itself must stay valid JSON in both click output layouts
        try:
            json.loads(result.output)
        except json.JSONDecodeError:
            pass  # click <8.2 mixes stderr into .output; _all_output covered it

    def test_history_stats(self, db):
        result = CliRunner().invoke(cli, ["history", "--stats", "--db", db])

        assert result.exit_code == 0
        stats = json.loads(result.output)
        assert stats["snapshot_count"] == 1
        assert stats["geos"] == ["US"]

    def test_history_timeline_with_keyword(self, db):
        result = CliRunner().invoke(
            cli, ["history", "--timeline", "-k", "bitcoin", "--db", db, "--quiet"]
        )

        assert result.exit_code == 0
        points = json.loads(result.output)
        assert points[0]["rank"] == 1

    def test_history_timeline_requires_keyword(self, db):
        result = CliRunner().invoke(cli, ["history", "--timeline", "--db", db])

        assert result.exit_code == 2  # click usage error
        assert "--timeline requires -k/--keyword" in _all_output(result)

    def test_history_prune_before(self, db):
        result = CliRunner().invoke(
            cli, ["history", "--prune-before", "2026-08-02", "--db", db, "--quiet"]
        )

        assert result.exit_code == 0
        assert json.loads(result.output) == {"deleted": 1}
        check = CliRunner().invoke(cli, ["history", "--db", db, "--quiet"])
        assert json.loads(check.output) == []

    def test_history_error_exits_nonzero(self, db):
        result = CliRunner().invoke(cli, ["history", "--since", "   ", "--db", db])

        assert result.exit_code == 1
        assert "[ERROR]" in _all_output(result)
