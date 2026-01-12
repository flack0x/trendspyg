"""
Tests for async RSS functions - validation and error handling
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from trendspyg.exceptions import InvalidParameterError, DownloadError, RateLimitError


class TestAsyncImportError:
    """Test async import error handling"""

    def test_async_function_exists(self):
        """Test async function can be imported"""
        from trendspyg import download_google_trends_rss_async
        assert callable(download_google_trends_rss_async)

    def test_batch_async_function_exists(self):
        """Test batch async function can be imported"""
        from trendspyg import download_google_trends_rss_batch_async
        assert callable(download_google_trends_rss_batch_async)


@pytest.mark.asyncio
class TestAsyncValidation:
    """Test async parameter validation"""

    async def test_async_invalid_geo_raises_error(self):
        """Test async with invalid geo raises error"""
        from trendspyg import download_google_trends_rss_async

        with pytest.raises(InvalidParameterError) as exc_info:
            await download_google_trends_rss_async(geo='INVALID')

        assert 'Invalid geo code' in str(exc_info.value)

    async def test_async_invalid_output_format_raises_error(self):
        """Test async with invalid output format raises error"""
        from trendspyg import download_google_trends_rss_async

        with pytest.raises(InvalidParameterError) as exc_info:
            await download_google_trends_rss_async(geo='US', output_format='invalid')

        assert 'Invalid output_format' in str(exc_info.value)

    async def test_async_geo_case_insensitive(self):
        """Test async geo is case insensitive (validation passes)"""
        from trendspyg.rss_downloader import _validate_geo_rss

        # Just test validation, not full download
        assert _validate_geo_rss('us') == 'US'
        assert _validate_geo_rss('Gb') == 'GB'


class TestBatchValidation:
    """Test batch function validation"""

    def test_batch_function_signature(self):
        """Test batch function has correct signature"""
        from trendspyg import download_google_trends_rss_batch
        import inspect

        sig = inspect.signature(download_google_trends_rss_batch)
        params = list(sig.parameters.keys())

        assert 'geos' in params
        assert 'show_progress' in params

    def test_batch_async_function_signature(self):
        """Test batch async function has correct signature"""
        from trendspyg import download_google_trends_rss_batch_async
        import inspect

        sig = inspect.signature(download_google_trends_rss_batch_async)
        params = list(sig.parameters.keys())

        assert 'geos' in params
        assert 'max_concurrent' in params


class TestHandleHttpError:
    """Test HTTP error handling function"""

    def test_handle_429_raises_rate_limit(self):
        """Test 429 raises RateLimitError"""
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(RateLimitError):
            _handle_http_error(429, 'US', 'http://example.com')

    def test_handle_403_raises_rate_limit(self):
        """Test 403 raises RateLimitError"""
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(RateLimitError):
            _handle_http_error(403, 'US', 'http://example.com')

    def test_handle_404_raises_download_error(self):
        """Test 404 raises DownloadError"""
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(DownloadError) as exc_info:
            _handle_http_error(404, 'XX', 'http://example.com')

        assert '404' in str(exc_info.value)

    def test_handle_500_raises_download_error(self):
        """Test 500 raises DownloadError"""
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(DownloadError) as exc_info:
            _handle_http_error(500, 'US', 'http://example.com')

        assert '500' in str(exc_info.value)
        assert 'server error' in str(exc_info.value).lower()


@pytest.mark.asyncio
class TestAsyncBatchFunction:
    """Test async batch function"""

    async def test_batch_async_with_mock(self):
        """Test batch async with mocked single download"""
        from trendspyg.rss_downloader import download_google_trends_rss_batch_async

        async def mock_single_download(**kwargs):
            geo = kwargs.get('geo', 'US')
            return [{'trend': f'trend_{geo}', 'traffic': '100+'}]

        with patch('trendspyg.rss_downloader.download_google_trends_rss_async', side_effect=mock_single_download):
            results = await download_google_trends_rss_batch_async(
                geos=['US', 'GB'],
                show_progress=False
            )

        assert 'US' in results
        assert 'GB' in results
        assert results['US'][0]['trend'] == 'trend_US'
        assert results['GB'][0]['trend'] == 'trend_GB'

    async def test_batch_async_with_progress(self):
        """Test batch async with progress bar enabled"""
        from trendspyg.rss_downloader import download_google_trends_rss_batch_async

        async def mock_single_download(**kwargs):
            geo = kwargs.get('geo', 'US')
            return [{'trend': f'trend_{geo}', 'traffic': '100+'}]

        with patch('trendspyg.rss_downloader.download_google_trends_rss_async', side_effect=mock_single_download):
            # Try with progress - may or may not have tqdm
            results = await download_google_trends_rss_batch_async(
                geos=['US', 'GB'],
                show_progress=True  # Test progress path
            )

        assert 'US' in results
        assert 'GB' in results
