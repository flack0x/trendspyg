"""
Tests for CLI functionality
"""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from click.testing import CliRunner


# Check if click is available
try:
    from trendspyg.cli import cli
    CLICK_AVAILABLE = True
except ImportError:
    CLICK_AVAILABLE = False


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIRSS:
    """Test RSS CLI command"""

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_basic(self, mock_download):
        """Test basic RSS command"""
        mock_download.return_value = [
            {'trend': 'test', 'traffic': '100+', 'published': '2024-01-01', 'explore_link': 'http://example.com'}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US'])

        assert result.exit_code == 0
        mock_download.assert_called_once()

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_with_geo(self, mock_download):
        """Test RSS with geo parameter"""
        mock_download.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'GB'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['geo'] == 'GB'

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_json_output(self, mock_download):
        """Test RSS with JSON output"""
        mock_download.return_value = '[{"trend": "test"}]'

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US', '--output', 'json'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['output_format'] == 'json'

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_csv_output(self, mock_download):
        """Test RSS with CSV output"""
        mock_download.return_value = 'trend,traffic\ntest,100+'

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US', '--output', 'csv'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['output_format'] == 'csv'
        assert 'trend,traffic' in result.output

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_dataframe_output(self, mock_download):
        """Test RSS with dataframe output"""
        mock_df = pd.DataFrame([{'trend': 'test', 'traffic': '100+'}])
        mock_download.return_value = mock_df

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US', '--output', 'dataframe'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['output_format'] == 'dataframe'
        assert 'DataFrame' in result.output or 'test' in result.output

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_no_images(self, mock_download):
        """Test RSS without images"""
        mock_download.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US', '--no-images'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['include_images'] == False

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_no_articles(self, mock_download):
        """Test RSS without articles"""
        mock_download.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US', '--no-articles'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['include_articles'] == False

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_max_articles(self, mock_download):
        """Test RSS with max-articles parameter"""
        mock_download.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US', '--max-articles', '3'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['max_articles_per_trend'] == 3

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_dict_output_with_images(self, mock_download):
        """Test RSS dict output displays image info"""
        mock_download.return_value = [
            {
                'trend': 'bitcoin',
                'traffic': '500K+',
                'published': '2024-01-01',
                'explore_link': 'http://example.com',
                'image': {'url': 'http://img.com/test.jpg', 'source': 'Reuters'}
            }
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US'])

        assert result.exit_code == 0
        assert 'BITCOIN' in result.output
        assert 'Reuters' in result.output

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_dict_output_with_articles(self, mock_download):
        """Test RSS dict output displays article info"""
        mock_download.return_value = [
            {
                'trend': 'bitcoin',
                'traffic': '500K+',
                'published': '2024-01-01',
                'explore_link': 'http://example.com',
                'news_articles': [
                    {'headline': 'Bitcoin surges', 'source': 'CNN', 'url': 'http://cnn.com'},
                    {'headline': 'Crypto rally', 'source': 'BBC', 'url': 'http://bbc.com'},
                    {'headline': 'Markets up', 'source': 'Fox', 'url': 'http://fox.com'},
                    {'headline': 'Extra article', 'source': 'NBC', 'url': 'http://nbc.com'}
                ]
            }
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US'])

        assert result.exit_code == 0
        assert 'Bitcoin surges' in result.output
        assert 'CNN' in result.output
        assert 'and 1 more articles' in result.output

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_dict_output_multiple_trends(self, mock_download):
        """Test RSS dict output with multiple trends shows separators"""
        mock_download.return_value = [
            {'trend': 'bitcoin', 'traffic': '500K+', 'published': '2024-01-01', 'explore_link': 'http://example.com'},
            {'trend': 'ethereum', 'traffic': '100K+', 'published': '2024-01-01', 'explore_link': 'http://example.com'}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'US'])

        assert result.exit_code == 0
        assert 'BITCOIN' in result.output
        assert 'ETHEREUM' in result.output
        assert '---' in result.output  # Separator


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLICSV:
    """Test CSV CLI command"""

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_basic(self, mock_download):
        """Test basic CSV command"""
        mock_download.return_value = '/path/to/file.csv'

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US'])

        assert result.exit_code == 0
        mock_download.assert_called_once()

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_with_hours(self, mock_download):
        """Test CSV with hours parameter"""
        mock_download.return_value = '/path/to/file.csv'

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US', '--hours', '48'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['hours'] == 48

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_with_category(self, mock_download):
        """Test CSV with category parameter"""
        mock_download.return_value = '/path/to/file.csv'

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US', '--category', 'sports'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['category'] == 'sports'

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_active_only(self, mock_download):
        """Test CSV with active-only flag"""
        mock_download.return_value = '/path/to/file.csv'

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US', '--active-only'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['active_only'] == True

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_with_sort(self, mock_download):
        """Test CSV with sort parameter"""
        mock_download.return_value = '/path/to/file.csv'

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US', '--sort', 'volume'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['sort_by'] == 'volume'

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_json_output(self, mock_download):
        """Test CSV with JSON output"""
        mock_download.return_value = '/path/to/file.json'

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US', '--output', 'json'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['output_format'] == 'json'
        assert 'Downloaded' in result.output

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_parquet_output(self, mock_download):
        """Test CSV with parquet output"""
        mock_download.return_value = '/path/to/file.parquet'

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US', '--output', 'parquet'])

        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['output_format'] == 'parquet'
        assert 'Downloaded' in result.output

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_dataframe_output(self, mock_download):
        """Test CSV with dataframe output"""
        mock_df = pd.DataFrame([
            {'Trends': 'bitcoin', 'Search volume': '500K+', 'Started': '2024-01-01',
             'Trend breakdown': 'crypto, blockchain', 'Explore link': 'http://example.com'},
            {'Trends': 'ethereum', 'Search volume': '100K+', 'Started': '2024-01-01',
             'Trend breakdown': 'crypto', 'Explore link': 'http://example.com'}
        ])
        mock_download.return_value = mock_df

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US', '--output', 'dataframe'])

        assert result.exit_code == 0
        assert 'BITCOIN' in result.output
        assert 'Search Volume' in result.output

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_dataframe_output_many_trends(self, mock_download):
        """Test CSV dataframe output with more than 10 trends"""
        mock_df = pd.DataFrame([
            {'Trends': f'trend{i}', 'Search volume': '100+', 'Started': '2024-01-01',
             'Trend breakdown': '', 'Explore link': 'http://example.com'}
            for i in range(15)
        ])
        mock_download.return_value = mock_df

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US', '--output', 'dataframe'])

        assert result.exit_code == 0
        assert '... and 5 more trends' in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIList:
    """Test list CLI command"""

    def test_list_countries(self):
        """Test list countries command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['list', '--type', 'countries'])

        assert result.exit_code == 0
        assert 'US' in result.output
        assert 'Countries' in result.output

    def test_list_states(self):
        """Test list states command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['list', '--type', 'states'])

        assert result.exit_code == 0
        assert 'US-CA' in result.output or 'California' in result.output

    def test_list_categories(self):
        """Test list categories command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['list', '--type', 'categories'])

        assert result.exit_code == 0
        assert 'Categories' in result.output

    def test_list_hours(self):
        """Test list hours command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['list', '--type', 'hours'])

        assert result.exit_code == 0
        assert 'Time Periods' in result.output
        assert '24' in result.output or 'hours' in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIInfo:
    """Test info CLI command"""

    def test_info_shows_version(self):
        """Test info command shows version"""
        runner = CliRunner()
        result = runner.invoke(cli, ['info'])

        assert result.exit_code == 0
        assert 'Version' in result.output

    def test_info_shows_features(self):
        """Test info command shows features"""
        runner = CliRunner()
        result = runner.invoke(cli, ['info'])

        assert result.exit_code == 0
        assert 'Countries' in result.output
        assert 'Categories' in result.output

    def test_info_shows_data_sources(self):
        """Test info command shows data sources"""
        runner = CliRunner()
        result = runner.invoke(cli, ['info'])

        assert result.exit_code == 0
        assert 'RSS' in result.output
        assert 'CSV' in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIErrorHandling:
    """Test CLI error handling"""

    @patch('trendspyg.cli.download_google_trends_rss')
    def test_rss_error_handling(self, mock_download):
        """Test RSS error handling"""
        from trendspyg.exceptions import InvalidParameterError
        mock_download.side_effect = InvalidParameterError("Invalid geo code")

        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--geo', 'INVALID'])

        assert result.exit_code != 0 or 'ERROR' in result.output or 'Invalid' in result.output

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_error_handling(self, mock_download):
        """Test CSV error handling"""
        from trendspyg.exceptions import BrowserError
        mock_download.side_effect = BrowserError("Chrome not found")

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US'])

        assert result.exit_code != 0 or 'ERROR' in result.output


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIHelp:
    """Test CLI help commands"""

    def test_main_help(self):
        """Test main help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])

        assert result.exit_code == 0
        assert 'trendspyg' in result.output.lower()

    def test_rss_help(self):
        """Test RSS help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['rss', '--help'])

        assert result.exit_code == 0
        assert '--geo' in result.output

    def test_csv_help(self):
        """Test CSV help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--help'])

        assert result.exit_code == 0
        assert '--geo' in result.output
        assert '--hours' in result.output

    def test_version(self):
        """Test version option"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--version'])

        assert result.exit_code == 0
        assert 'trendspyg' in result.output.lower()


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLIMain:
    """Test CLI main entry point"""

    def test_main_function_exists(self):
        """Test main function can be called"""
        from trendspyg.cli import main
        assert callable(main)

    @patch('trendspyg.cli.cli')
    def test_main_calls_cli(self, mock_cli):
        """Test main function calls cli"""
        from trendspyg.cli import main
        main()
        mock_cli.assert_called_once()


@pytest.mark.skipif(not CLICK_AVAILABLE, reason="click not installed")
class TestCLICSVDataframeEdgeCases:
    """Test CSV dataframe output edge cases"""

    @patch('trendspyg.cli.download_google_trends_csv')
    def test_csv_dataframe_with_long_breakdown(self, mock_download):
        """Test CSV dataframe with very long trend breakdown text"""
        mock_df = pd.DataFrame([
            {
                'Trends': 'bitcoin',
                'Search volume': '500K+',
                'Started': '2024-01-01',
                'Trend breakdown': 'a' * 150,  # Very long breakdown
                'Explore link': 'http://example.com'
            }
        ])
        mock_download.return_value = mock_df

        runner = CliRunner()
        result = runner.invoke(cli, ['csv', '--geo', 'US', '--output', 'dataframe'])

        assert result.exit_code == 0
        # Long breakdown should be truncated
        assert '...' in result.output
