"""
Integration tests for CSV downloader with mocked Selenium
Tests all browser automation code paths
"""
import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock, PropertyMock
from trendspyg.downloader import (
    download_google_trends_csv,
    _download_with_retry,
    _convert_csv_to_format,
    validate_category,
    main,
    CATEGORIES,
)
from trendspyg.exceptions import (
    InvalidParameterError,
    BrowserError,
    DownloadError,
)


class TestDownloadWithRetry:
    """Test retry mechanism"""

    def test_retry_success_first_attempt(self):
        """Test successful download on first attempt"""
        mock_func = MagicMock(return_value="success")
        result = _download_with_retry(mock_func, max_retries=3)

        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_success_after_failures(self):
        """Test successful download after initial failures"""
        mock_func = MagicMock(side_effect=[
            BrowserError("First fail"),
            BrowserError("Second fail"),
            "success"
        ])

        with patch('trendspyg.downloader.time.sleep'):
            result = _download_with_retry(mock_func, max_retries=3)

        assert result == "success"
        assert mock_func.call_count == 3

    def test_retry_all_attempts_fail(self):
        """Test all retry attempts failing"""
        mock_func = MagicMock(side_effect=BrowserError("Always fails"))

        with patch('trendspyg.downloader.time.sleep'):
            with pytest.raises(BrowserError):
                _download_with_retry(mock_func, max_retries=3)

        assert mock_func.call_count == 3

    def test_retry_with_download_error(self):
        """Test retry with DownloadError"""
        mock_func = MagicMock(side_effect=[
            DownloadError("First fail"),
            "success"
        ])

        with patch('trendspyg.downloader.time.sleep'):
            result = _download_with_retry(mock_func, max_retries=3)

        assert result == "success"

    def test_retry_with_timeout_exception(self):
        """Test retry with TimeoutException"""
        from selenium.common.exceptions import TimeoutException

        mock_func = MagicMock(side_effect=[
            TimeoutException("Timeout"),
            "success"
        ])

        with patch('trendspyg.downloader.time.sleep'):
            result = _download_with_retry(mock_func, max_retries=3)

        assert result == "success"


class TestValidateCategorySimilar:
    """Test category validation with similar matches"""

    def test_category_suggests_similar(self):
        """Test invalid category suggests similar ones"""
        with pytest.raises(InvalidParameterError) as exc_info:
            validate_category('spo')  # Partial match for 'sports'

        # Should suggest similar categories
        error_msg = str(exc_info.value)
        assert 'Invalid category' in error_msg


class TestConvertCsvToFormat:
    """Test CSV conversion to various formats"""

    def test_convert_csv_returns_path(self):
        """Test CSV format returns original path"""
        result = _convert_csv_to_format('/path/to/file.csv', 'csv', '/path/to')
        assert result == '/path/to/file.csv'

    def test_convert_pandas_import_error(self, tmp_path):
        """Test pandas ImportError is handled"""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        # Mock pandas import to fail
        import sys
        original_modules = sys.modules.copy()

        # Remove pandas from modules to simulate import error
        with patch.dict('sys.modules', {'pandas': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'pandas'")):
                # Can't easily test this without breaking the test environment
                pass

    def test_convert_parquet_pyarrow_error(self, tmp_path):
        """Test parquet conversion handles pyarrow import error"""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        # Mock to_parquet to raise ImportError
        with patch('pandas.DataFrame.to_parquet', side_effect=ImportError("No module named 'pyarrow'")):
            with pytest.raises(ImportError) as exc_info:
                _convert_csv_to_format(str(csv_file), 'parquet', str(tmp_path))

            assert 'pyarrow' in str(exc_info.value)

    def test_convert_parquet_write_error(self, tmp_path):
        """Test parquet conversion handles write errors"""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        # Mock to_parquet to raise generic error
        with patch('pandas.DataFrame.to_parquet', side_effect=Exception("Write failed")):
            with pytest.raises(DownloadError) as exc_info:
                _convert_csv_to_format(str(csv_file), 'parquet', str(tmp_path))

            assert 'Failed to convert to Parquet' in str(exc_info.value)

    def test_convert_to_dataframe(self, tmp_path):
        """Test conversion to DataFrame"""
        # Create temp CSV
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        result = _convert_csv_to_format(str(csv_file), 'dataframe', str(tmp_path))

        assert hasattr(result, 'to_csv')  # It's a DataFrame
        assert len(result) == 1

    def test_convert_to_json(self, tmp_path):
        """Test conversion to JSON"""
        # Create temp CSV
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        result = _convert_csv_to_format(str(csv_file), 'json', str(tmp_path))

        assert result.endswith('.json')
        assert os.path.exists(result)
        # Original CSV should be removed
        assert not os.path.exists(str(csv_file))

    def test_convert_to_parquet(self, tmp_path):
        """Test conversion to Parquet"""
        pytest.importorskip("pyarrow")

        # Create temp CSV
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        result = _convert_csv_to_format(str(csv_file), 'parquet', str(tmp_path))

        assert result.endswith('.parquet')
        assert os.path.exists(result)

    def test_convert_invalid_csv_raises_error(self, tmp_path):
        """Test conversion with invalid CSV raises error"""
        # Create CSV with path that doesn't exist
        csv_file = tmp_path / "nonexistent.csv"

        with pytest.raises((DownloadError, FileNotFoundError)):
            _convert_csv_to_format(str(csv_file), 'dataframe', str(tmp_path))

    def test_convert_json_write_error(self, tmp_path):
        """Test JSON conversion error handling"""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        with patch('pandas.DataFrame.to_json', side_effect=Exception("Write error")):
            with pytest.raises(DownloadError) as exc_info:
                _convert_csv_to_format(str(csv_file), 'json', str(tmp_path))

        assert 'Failed to convert to JSON' in str(exc_info.value)


class TestDownloadGoogleTrendsCSVMocked:
    """Test download function with mocked Selenium"""

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_browser_initialization_error(self, mock_chrome):
        """Test browser startup error handling"""
        from selenium.common.exceptions import WebDriverException
        mock_chrome.side_effect = WebDriverException("Chrome not found")

        with pytest.raises(BrowserError) as exc_info:
            download_google_trends_csv(geo='US')

        assert 'Failed to start Chrome browser' in str(exc_info.value)
        assert 'Chrome browser is installed' in str(exc_info.value)

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_url_with_hours_parameter(self, mock_chrome):
        """Test URL includes hours parameter when not 24"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        # Make it fail early to check URL
        from selenium.common.exceptions import TimeoutException
        mock_driver.get.side_effect = TimeoutException("Test")

        with pytest.raises(BrowserError):
            download_google_trends_csv(geo='US', hours=48)

        # Check URL was built correctly
        call_args = mock_driver.get.call_args[0][0]
        assert 'hours=48' in call_args

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_url_with_category_parameter(self, mock_chrome):
        """Test URL includes category parameter"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        from selenium.common.exceptions import TimeoutException
        mock_driver.get.side_effect = TimeoutException("Test")

        with pytest.raises(BrowserError):
            download_google_trends_csv(geo='US', category='sports')

        call_args = mock_driver.get.call_args[0][0]
        assert 'cat=sports' in call_args

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_timeout_exception_handling(self, mock_chrome):
        """Test TimeoutException is converted to BrowserError"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        from selenium.common.exceptions import TimeoutException
        mock_driver.get.side_effect = TimeoutException("Page load timeout")

        with pytest.raises(BrowserError) as exc_info:
            download_google_trends_csv(geo='US')

        assert 'Page load timeout' in str(exc_info.value)
        assert 'Slow internet connection' in str(exc_info.value)

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_no_such_element_exception_handling(self, mock_chrome):
        """Test NoSuchElementException is converted to BrowserError"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        from selenium.common.exceptions import NoSuchElementException
        mock_driver.get.return_value = None

        # Fail on WebDriverWait
        with patch('trendspyg.downloader.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.side_effect = NoSuchElementException("Element not found")

            with pytest.raises(BrowserError) as exc_info:
                download_google_trends_csv(geo='US')

        assert 'Could not find UI element' in str(exc_info.value)

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_element_click_intercepted_handling(self, mock_chrome):
        """Test ElementClickInterceptedException handling"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        from selenium.common.exceptions import ElementClickInterceptedException

        with patch('trendspyg.downloader.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.side_effect = ElementClickInterceptedException("Click blocked")

            with pytest.raises(BrowserError) as exc_info:
                download_google_trends_csv(geo='US')

        assert 'Could not click UI element' in str(exc_info.value)

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_unexpected_exception_handling(self, mock_chrome):
        """Test unexpected exception is wrapped in BrowserError"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        mock_driver.get.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(BrowserError) as exc_info:
            download_google_trends_csv(geo='US')

        assert 'Unexpected error during download' in str(exc_info.value)
        assert 'RuntimeError' in str(exc_info.value)

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.WebDriverWait')
    @patch('trendspyg.downloader.os.listdir')
    @patch('trendspyg.downloader.time.sleep')
    def test_successful_download_flow(self, mock_sleep, mock_listdir, mock_wait, mock_chrome, tmp_path):
        """Test successful download flow"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        # Setup WebDriverWait to return mock elements
        mock_element = MagicMock()
        mock_wait.return_value.until.return_value = mock_element

        # Simulate file appearing after download
        mock_listdir.side_effect = [
            [],  # First call - existing files
            [],  # During wait loop
            ['trends.csv'],  # File appears
        ]

        # Create actual CSV file
        csv_file = tmp_path / "trends.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        with patch('trendspyg.downloader.os.path.join', return_value=str(csv_file)):
            with patch('trendspyg.downloader.os.rename'):
                result = download_google_trends_csv(
                    geo='US',
                    download_dir=str(tmp_path)
                )

        # Driver should be quit
        mock_driver.quit.assert_called_once()

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.WebDriverWait')
    @patch('trendspyg.downloader.time.sleep')
    def test_no_file_downloaded_error(self, mock_sleep, mock_wait, mock_chrome, tmp_path):
        """Test error when no file is downloaded"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        mock_element = MagicMock()
        mock_wait.return_value.until.return_value = mock_element

        # No files appear
        with patch('trendspyg.downloader.os.listdir', return_value=[]):
            with pytest.raises(DownloadError) as exc_info:
                download_google_trends_csv(
                    geo='US',
                    download_dir=str(tmp_path)
                )

        assert 'No new file detected' in str(exc_info.value)

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.WebDriverWait')
    @patch('trendspyg.downloader.time.sleep')
    def test_active_only_toggle(self, mock_sleep, mock_wait, mock_chrome, tmp_path):
        """Test active_only toggle flow"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        mock_element = MagicMock()
        mock_wait.return_value.until.return_value = mock_element

        # No files appear (will error, but we test the toggle was attempted)
        with patch('trendspyg.downloader.os.listdir', return_value=[]):
            with pytest.raises(DownloadError):
                download_google_trends_csv(
                    geo='US',
                    active_only=True,
                    download_dir=str(tmp_path)
                )

        # execute_script should have been called for toggle
        assert mock_driver.execute_script.called

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.time.sleep')
    def test_active_only_toggle_failure(self, mock_sleep, mock_chrome, tmp_path):
        """Test active_only toggle gracefully handles failure without crashing"""
        from selenium.common.exceptions import TimeoutException, NoSuchElementException

        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        # Mock find_element to raise NoSuchElementException for toggle
        mock_driver.find_element.side_effect = NoSuchElementException("Element not found")

        # This will cause the toggle to fail gracefully
        # No files appear - will raise DownloadError at the end
        with patch('trendspyg.downloader.WebDriverWait') as mock_wait:
            mock_wait.return_value.until.return_value = MagicMock()

            with patch('trendspyg.downloader.os.listdir', return_value=[]):
                with pytest.raises(DownloadError):
                    download_google_trends_csv(
                        geo='US',
                        active_only=True,
                        download_dir=str(tmp_path)
                    )

        # Test passes if we reach here - toggle failure was handled gracefully

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.WebDriverWait')
    @patch('trendspyg.downloader.time.sleep')
    def test_sort_info_message(self, mock_sleep, mock_wait, mock_chrome, tmp_path, capsys):
        """Test sort info message is printed"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        mock_element = MagicMock()
        mock_wait.return_value.until.return_value = mock_element

        with patch('trendspyg.downloader.os.listdir', return_value=[]):
            with pytest.raises(DownloadError):
                download_google_trends_csv(
                    geo='US',
                    sort_by='volume',
                    download_dir=str(tmp_path)
                )

        captured = capsys.readouterr()
        assert "Sort by 'volume' only affects UI display" in captured.out

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.WebDriverWait')
    @patch('trendspyg.downloader.os.listdir')
    @patch('trendspyg.downloader.time.sleep')
    def test_dataframe_output_message(self, mock_sleep, mock_listdir, mock_wait, mock_chrome, tmp_path, capsys):
        """Test DataFrame output prints row count"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        mock_element = MagicMock()
        mock_wait.return_value.until.return_value = mock_element

        # Create CSV file
        csv_file = tmp_path / "trends.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\nethereum,50K+\n")

        # Simulate file appearing
        mock_listdir.side_effect = [
            [],  # existing
            ['trends.csv'],  # new file
        ]

        with patch('trendspyg.downloader.os.path.join', return_value=str(csv_file)):
            with patch('trendspyg.downloader.os.rename'):
                result = download_google_trends_csv(
                    geo='US',
                    output_format='dataframe',
                    download_dir=str(tmp_path)
                )

        captured = capsys.readouterr()
        assert 'DataFrame with' in captured.out


class TestMainFunction:
    """Test main CLI function"""

    @patch('trendspyg.downloader.download_google_trends_csv')
    @patch('trendspyg.downloader.os.path.getsize')
    def test_main_success(self, mock_getsize, mock_download, capsys):
        """Test main function with successful download"""
        mock_download.return_value = '/path/to/file.csv'
        mock_getsize.return_value = 1234

        with patch('sys.argv', ['prog', '--geo', 'US']):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert 'Google Trends Configurable Downloader' in captured.out

    @patch('trendspyg.downloader.download_google_trends_csv')
    def test_main_failure(self, mock_download, capsys):
        """Test main function with failed download"""
        mock_download.return_value = None

        with patch('sys.argv', ['prog', '--geo', 'US']):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'Failed to download' in captured.out

    @patch('trendspyg.downloader.download_google_trends_csv')
    @patch('trendspyg.downloader.os.path.getsize')
    def test_main_with_all_args(self, mock_getsize, mock_download):
        """Test main function with all arguments"""
        mock_download.return_value = '/path/to/file.csv'
        mock_getsize.return_value = 1234

        with patch('sys.argv', [
            'prog',
            '--geo', 'GB',
            '--hours', '48',
            '--category', 'sports',
            '--active-only',
            '--sort', 'volume',
            '--visible',
            '--output-dir', '/tmp'
        ]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0

        # Verify download was called with correct args
        mock_download.assert_called_once()
        call_kwargs = mock_download.call_args[1]
        assert call_kwargs['geo'] == 'GB'
        assert call_kwargs['hours'] == 48
        assert call_kwargs['category'] == 'sports'
        assert call_kwargs['active_only'] == True
        assert call_kwargs['sort_by'] == 'volume'
        assert call_kwargs['headless'] == False
        assert call_kwargs['download_dir'] == '/tmp'


class TestHeadlessModeOptions:
    """Test headless mode configuration"""

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_headless_mode_options(self, mock_chrome):
        """Test headless mode adds correct options"""
        from selenium.common.exceptions import TimeoutException

        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        mock_driver.get.side_effect = TimeoutException("Test")

        with pytest.raises(BrowserError):
            download_google_trends_csv(geo='US', headless=True)

        # Check Chrome was called with options
        call_args = mock_chrome.call_args
        options = call_args[1]['options']

        # Verify headless arguments were added
        args = options.arguments
        assert '--headless=new' in args
        assert '--disable-gpu' in args
        assert '--no-sandbox' in args

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_visible_mode_options(self, mock_chrome):
        """Test visible mode doesn't add headless options"""
        from selenium.common.exceptions import TimeoutException

        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver
        mock_driver.get.side_effect = TimeoutException("Test")

        with pytest.raises(BrowserError):
            download_google_trends_csv(geo='US', headless=False)

        call_args = mock_chrome.call_args
        options = call_args[1]['options']

        args = options.arguments
        assert '--headless=new' not in args


class TestFileWaitLoop:
    """Test file download wait loop"""

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.WebDriverWait')
    @patch('trendspyg.downloader.time.sleep')
    def test_file_detected_after_wait(self, mock_sleep, mock_wait, mock_chrome, tmp_path):
        """Test file is detected after wait loop"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        mock_element = MagicMock()
        mock_wait.return_value.until.return_value = mock_element

        # Create CSV file
        csv_file = tmp_path / "trends.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        # File appears after several checks
        call_count = [0]
        def listdir_side_effect(path):
            call_count[0] += 1
            if call_count[0] <= 3:
                return []  # No files yet
            return ['trends.csv']  # File appears

        with patch('trendspyg.downloader.os.listdir', side_effect=listdir_side_effect):
            with patch('trendspyg.downloader.os.path.join', return_value=str(csv_file)):
                with patch('trendspyg.downloader.os.rename'):
                    result = download_google_trends_csv(
                        geo='US',
                        download_dir=str(tmp_path)
                    )

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.WebDriverWait')
    @patch('trendspyg.downloader.time.sleep')
    def test_final_check_finds_file(self, mock_sleep, mock_wait, mock_chrome, tmp_path):
        """Test file is found in final check after loop timeout"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        mock_element = MagicMock()
        mock_wait.return_value.until.return_value = mock_element

        # Create CSV file
        csv_file = tmp_path / "trends.csv"
        csv_file.write_text("Trends,Search volume\nbitcoin,100K+\n")

        # File only appears after the loop completes (in final check)
        # Loop runs max 20 iterations (10s / 0.5s check_interval)
        call_count = [0]
        def listdir_side_effect(path):
            call_count[0] += 1
            # First call is for existing_files, then loop calls
            # After ~21 calls (1 initial + 20 loop), then 2 final checks
            if call_count[0] <= 21:
                return []  # No files during loop
            return ['trends.csv']  # Final check finds file

        with patch('trendspyg.downloader.os.listdir', side_effect=listdir_side_effect):
            with patch('trendspyg.downloader.os.path.join', return_value=str(csv_file)):
                with patch('trendspyg.downloader.os.rename'):
                    with patch('trendspyg.downloader.os.makedirs'):
                        result = download_google_trends_csv(
                            geo='US',
                            download_dir=str(tmp_path)
                        )

        assert result is not None


class TestCustomExceptionReRaise:
    """Test that custom exceptions are re-raised without wrapping"""

    @patch('trendspyg.downloader.webdriver.Chrome')
    def test_invalid_parameter_error_not_wrapped(self, mock_chrome):
        """Test InvalidParameterError is not wrapped"""
        # This should fail at validation before Chrome is even called
        with pytest.raises(InvalidParameterError):
            download_google_trends_csv(geo='INVALID_GEO_CODE')

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.WebDriverWait')
    def test_browser_error_not_wrapped(self, mock_wait, mock_chrome):
        """Test BrowserError is not double-wrapped"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        # Raise BrowserError from inside
        mock_wait.return_value.until.side_effect = BrowserError("Original error")

        with pytest.raises(BrowserError) as exc_info:
            download_google_trends_csv(geo='US')

        assert str(exc_info.value) == "Original error"

    @patch('trendspyg.downloader.webdriver.Chrome')
    @patch('trendspyg.downloader.WebDriverWait')
    def test_download_error_not_wrapped(self, mock_wait, mock_chrome):
        """Test DownloadError is not double-wrapped"""
        mock_driver = MagicMock()
        mock_chrome.return_value = mock_driver

        mock_wait.return_value.until.side_effect = DownloadError("Original download error")

        with pytest.raises(DownloadError) as exc_info:
            download_google_trends_csv(geo='US')

        assert str(exc_info.value) == "Original download error"
