"""
Tests for async RSS functions - validation and error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trendspyg.exceptions import DownloadError, InvalidParameterError, RateLimitError


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
            await download_google_trends_rss_async(geo="INVALID")

        assert "Invalid geo code" in str(exc_info.value)

    async def test_async_invalid_output_format_raises_error(self):
        """Test async with invalid output format raises error"""
        from trendspyg import download_google_trends_rss_async

        with pytest.raises(InvalidParameterError) as exc_info:
            await download_google_trends_rss_async(geo="US", output_format="invalid")

        assert "Invalid output_format" in str(exc_info.value)

    async def test_async_geo_case_insensitive(self):
        """Test async geo is case insensitive (validation passes)"""
        from trendspyg.rss_downloader import _validate_geo_rss

        # Just test validation, not full download
        assert _validate_geo_rss("us") == "US"
        assert _validate_geo_rss("Gb") == "GB"


class TestBatchValidation:
    """Test batch function validation"""

    def test_batch_function_signature(self):
        """Test batch function has correct signature"""
        import inspect

        from trendspyg import download_google_trends_rss_batch

        sig = inspect.signature(download_google_trends_rss_batch)
        params = list(sig.parameters.keys())

        assert "geos" in params
        assert "show_progress" in params

    def test_batch_async_function_signature(self):
        """Test batch async function has correct signature"""
        import inspect

        from trendspyg import download_google_trends_rss_batch_async

        sig = inspect.signature(download_google_trends_rss_batch_async)
        params = list(sig.parameters.keys())

        assert "geos" in params
        assert "max_concurrent" in params


class TestHandleHttpError:
    """Test HTTP error handling function"""

    def test_handle_429_raises_rate_limit(self):
        """Test 429 raises RateLimitError"""
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(RateLimitError):
            _handle_http_error(429, "US", "http://example.com")

    def test_handle_403_raises_rate_limit(self):
        """Test 403 raises RateLimitError"""
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(RateLimitError):
            _handle_http_error(403, "US", "http://example.com")

    def test_handle_404_raises_download_error(self):
        """Test 404 raises DownloadError"""
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(DownloadError) as exc_info:
            _handle_http_error(404, "XX", "http://example.com")

        assert "404" in str(exc_info.value)

    def test_handle_500_raises_download_error(self):
        """Test 500 raises DownloadError"""
        from trendspyg.rss_downloader import _handle_http_error

        with pytest.raises(DownloadError) as exc_info:
            _handle_http_error(500, "US", "http://example.com")

        assert "500" in str(exc_info.value)
        assert "server error" in str(exc_info.value).lower()


@pytest.mark.asyncio
class TestAsyncBatchFunction:
    """Test async batch function"""

    async def test_batch_async_with_mock(self):
        """Test batch async with mocked single download"""
        from trendspyg.rss_downloader import download_google_trends_rss_batch_async

        async def mock_single_download(**kwargs):
            geo = kwargs.get("geo", "US")
            return [{"trend": f"trend_{geo}", "traffic": "100+"}]

        with patch(
            "trendspyg.rss_downloader.download_google_trends_rss_async",
            side_effect=mock_single_download,
        ):
            results = await download_google_trends_rss_batch_async(
                geos=["US", "GB"], show_progress=False
            )

        assert "US" in results
        assert "GB" in results
        assert results["US"][0]["trend"] == "trend_US"
        assert results["GB"][0]["trend"] == "trend_GB"

    async def test_batch_async_with_progress(self):
        """Test batch async with progress bar enabled"""
        from trendspyg.rss_downloader import download_google_trends_rss_batch_async

        async def mock_single_download(**kwargs):
            geo = kwargs.get("geo", "US")
            return [{"trend": f"trend_{geo}", "traffic": "100+"}]

        with patch(
            "trendspyg.rss_downloader.download_google_trends_rss_async",
            side_effect=mock_single_download,
        ):
            # Try with progress - may or may not have tqdm
            results = await download_google_trends_rss_batch_async(
                geos=["US", "GB"], show_progress=True  # Test progress path
            )

        assert "US" in results
        assert "GB" in results


class TestBatchNormalize:
    """normalize=True threads through both batch functions -> {geo: NormalizedEnvelope}."""

    def test_batch_sync_normalize(self):
        """Sync batch with normalize=True returns a NormalizedEnvelope per geo."""
        from trendspyg.rss_downloader import download_google_trends_rss_batch

        def mock_single(**kwargs):
            geo = kwargs.get("geo", "US")
            if kwargs.get("normalize"):
                return {
                    "schema_version": "1.0",
                    "source": "rss",
                    "geo": geo,
                    "fetched_at": "2026-05-22T00:00:00+00:00",
                    "count": 1,
                    "trends": [{"keyword": f"k_{geo}", "rank": 1}],
                }
            return [{"trend": f"trend_{geo}", "traffic": "100+"}]

        with patch("trendspyg.rss_downloader.download_google_trends_rss", side_effect=mock_single):
            results = download_google_trends_rss_batch(
                geos=["US", "GB"], show_progress=False, normalize=True
            )

        assert set(results) == {"US", "GB"}
        assert results["US"]["source"] == "rss"
        assert results["US"]["geo"] == "US"
        assert results["GB"]["trends"][0]["keyword"] == "k_GB"

    @pytest.mark.asyncio
    async def test_batch_async_normalize(self):
        """Async batch with normalize=True returns a NormalizedEnvelope per geo."""
        from trendspyg.rss_downloader import download_google_trends_rss_batch_async

        async def mock_single(**kwargs):
            geo = kwargs.get("geo", "US")
            if kwargs.get("normalize"):
                return {
                    "schema_version": "1.0",
                    "source": "rss",
                    "geo": geo,
                    "fetched_at": "2026-05-22T00:00:00+00:00",
                    "count": 1,
                    "trends": [{"keyword": f"k_{geo}", "rank": 1}],
                }
            return [{"trend": f"trend_{geo}", "traffic": "100+"}]

        with patch(
            "trendspyg.rss_downloader.download_google_trends_rss_async", side_effect=mock_single
        ):
            results = await download_google_trends_rss_batch_async(
                geos=["US", "GB"], show_progress=False, normalize=True
            )

        assert set(results) == {"US", "GB"}
        assert results["US"]["source"] == "rss"
        assert results["GB"]["geo"] == "GB"
        assert results["GB"]["trends"][0]["keyword"] == "k_GB"

    def test_batch_sync_default_unchanged(self):
        """normalize defaults to False -> batch still returns raw trend lists."""
        from trendspyg.rss_downloader import download_google_trends_rss_batch

        def mock_single(**kwargs):
            geo = kwargs.get("geo", "US")
            assert kwargs.get("normalize") is False
            return [{"trend": f"trend_{geo}", "traffic": "100+"}]

        with patch("trendspyg.rss_downloader.download_google_trends_rss", side_effect=mock_single):
            results = download_google_trends_rss_batch(geos=["US"], show_progress=False)

        assert isinstance(results["US"], list)
        assert results["US"][0]["trend"] == "trend_US"


# --- Offline fakes for the real async fetch engine -------------------------

SAMPLE_ASYNC_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
  <channel>
    <item>
      <title>bitcoin</title>
      <ht:approx_traffic>500K+</ht:approx_traffic>
      <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""


class _FakeResponse:
    """Async context manager standing in for an aiohttp response."""

    def __init__(self, status=200, body=SAMPLE_ASYNC_XML):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def read(self):
        return self._body


class _FakeSession:
    """Stands in for aiohttp.ClientSession; get() returns a response or raises."""

    def __init__(self, response=None, get_error=None):
        self.closed = False
        self._response = response if response is not None else _FakeResponse()
        self._get_error = get_error

    def get(self, url, **kwargs):
        if self._get_error is not None:
            raise self._get_error
        return self._response

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
class TestAsyncEngine:
    """Drive the real async fetch engine offline via a fake aiohttp session"""

    def setup_method(self):
        from trendspyg import clear_rss_cache

        clear_rss_cache()

    async def test_creates_and_closes_own_session(self, monkeypatch):
        """session=None -> engine creates its own session and closes it"""
        import aiohttp

        from trendspyg.rss_downloader import download_google_trends_rss_async

        fake = _FakeSession()
        monkeypatch.setattr(aiohttp, "ClientSession", lambda: fake)

        trends = await download_google_trends_rss_async(geo="US", cache=False)

        assert trends[0]["trend"] == "bitcoin"
        assert fake.closed is True

    async def test_injected_session_is_not_closed(self):
        """A caller-provided session must survive the call (connection pooling)"""
        from trendspyg.rss_downloader import download_google_trends_rss_async

        fake = _FakeSession()

        trends = await download_google_trends_rss_async(geo="US", cache=False, session=fake)

        assert trends[0]["trend"] == "bitcoin"
        assert fake.closed is False

    async def test_normalize_fresh_fetch_returns_envelope(self):
        """normalize=True on a fresh async fetch returns a NormalizedEnvelope"""
        from trendspyg.rss_downloader import download_google_trends_rss_async

        envelope = await download_google_trends_rss_async(
            geo="US", cache=False, normalize=True, session=_FakeSession()
        )

        assert envelope["source"] == "rss"
        assert envelope["geo"] == "US"
        assert envelope["count"] == 1
        assert envelope["trends"][0]["keyword"] == "bitcoin"

    async def test_cache_hit_skips_network(self):
        """Second call is served from cache — raw and normalized alike"""
        from trendspyg.rss_downloader import download_google_trends_rss_async

        first = await download_google_trends_rss_async(geo="US", session=_FakeSession())

        # A session that explodes on use proves the cache path never fetches.
        poison = _FakeSession(get_error=AssertionError("network was hit"))
        raw = await download_google_trends_rss_async(geo="US", session=poison)
        envelope = await download_google_trends_rss_async(geo="US", normalize=True, session=poison)

        assert raw == first
        assert envelope["count"] == 1
        assert envelope["trends"][0]["keyword"] == "bitcoin"

    async def test_non_200_status_maps_to_download_error(self):
        """HTTP 500 from the feed -> DownloadError via _handle_http_error"""
        from trendspyg.rss_downloader import download_google_trends_rss_async

        fake = _FakeSession(response=_FakeResponse(status=500))

        with pytest.raises(DownloadError):
            await download_google_trends_rss_async(geo="US", cache=False, session=fake)

    async def test_status_429_raises_rate_limit_error(self):
        """HTTP 429 from the feed -> RateLimitError"""
        from trendspyg.rss_downloader import download_google_trends_rss_async

        fake = _FakeSession(response=_FakeResponse(status=429))

        with pytest.raises(RateLimitError):
            await download_google_trends_rss_async(geo="US", cache=False, session=fake)

    async def test_client_response_error_maps_via_status(self):
        """aiohttp.ClientResponseError carries its status into the error mapping"""
        import aiohttp

        from trendspyg.rss_downloader import download_google_trends_rss_async

        error = aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=429)
        fake = _FakeSession(get_error=error)

        with pytest.raises(RateLimitError):
            await download_google_trends_rss_async(geo="US", cache=False, session=fake)

    async def test_connector_error_maps_to_download_error(self):
        """aiohttp.ClientConnectorError -> DownloadError with connection guidance"""
        import aiohttp

        from trendspyg.rss_downloader import download_google_trends_rss_async

        error = aiohttp.ClientConnectorError(MagicMock(), OSError("unreachable"))
        fake = _FakeSession(get_error=error)

        with pytest.raises(DownloadError) as exc_info:
            await download_google_trends_rss_async(geo="US", cache=False, session=fake)

        assert "Connection failed" in str(exc_info.value)

    async def test_timeout_maps_to_download_error(self):
        """asyncio.TimeoutError -> DownloadError with timeout guidance"""
        from trendspyg.rss_downloader import download_google_trends_rss_async

        fake = _FakeSession(get_error=asyncio.TimeoutError())

        with pytest.raises(DownloadError) as exc_info:
            await download_google_trends_rss_async(geo="US", cache=False, session=fake)

        assert "timed out" in str(exc_info.value)

    async def test_generic_client_error_maps_to_download_error(self):
        """Any other aiohttp.ClientError -> DownloadError with context"""
        import aiohttp

        from trendspyg.rss_downloader import download_google_trends_rss_async

        fake = _FakeSession(get_error=aiohttp.ClientError("proxy mangled the stream"))

        with pytest.raises(DownloadError) as exc_info:
            await download_google_trends_rss_async(geo="US", cache=False, session=fake)

        assert "Network error" in str(exc_info.value)


class TestAsyncImportGuards:
    """Missing optional deps -> actionable ImportError, not a stack trace"""

    @pytest.mark.asyncio
    async def test_async_requires_aiohttp(self, monkeypatch):
        import sys

        from trendspyg.rss_downloader import download_google_trends_rss_async

        monkeypatch.setitem(sys.modules, "aiohttp", None)

        with pytest.raises(ImportError) as exc_info:
            await download_google_trends_rss_async(geo="US")

        assert "aiohttp is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_batch_async_requires_aiohttp(self, monkeypatch):
        import sys

        from trendspyg.rss_downloader import download_google_trends_rss_batch_async

        monkeypatch.setitem(sys.modules, "aiohttp", None)

        with pytest.raises(ImportError) as exc_info:
            await download_google_trends_rss_batch_async(["US"])

        assert "async batch" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_batch_async_without_tqdm_prints_note(self, monkeypatch, capsys):
        import sys

        from trendspyg.rss_downloader import download_google_trends_rss_batch_async

        monkeypatch.setitem(sys.modules, "tqdm.asyncio", None)

        async def mock_single(**kwargs):
            return [{"trend": "t", "traffic": "1+"}]

        with patch(
            "trendspyg.rss_downloader.download_google_trends_rss_async",
            side_effect=mock_single,
        ):
            results = await download_google_trends_rss_batch_async(["US"], show_progress=True)

        assert set(results) == {"US"}
        assert "Install tqdm" in capsys.readouterr().err
