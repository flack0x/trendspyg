"""
Tests for RSS downloader with mocked network calls
"""
import pytest
from unittest.mock import patch, MagicMock
from trendspyg.rss_downloader import (
    download_google_trends_rss,
    _parse_rss_xml,
    _format_output,
    _validate_geo_rss,
    _make_cache_key,
    _handle_http_error,
)
from trendspyg.exceptions import InvalidParameterError, DownloadError, RateLimitError
from trendspyg import clear_rss_cache


# Sample RSS XML for testing
SAMPLE_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
  <channel>
    <title>Trending Now - US</title>
    <item>
      <title>bitcoin</title>
      <ht:approx_traffic>500K+</ht:approx_traffic>
      <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
      <ht:picture>https://example.com/image.jpg</ht:picture>
      <ht:picture_source>Reuters</ht:picture_source>
      <ht:news_item>
        <ht:news_item_title>Bitcoin surges past $50K</ht:news_item_title>
        <ht:news_item_url>https://example.com/article</ht:news_item_url>
        <ht:news_item_source>CNN</ht:news_item_source>
        <ht:news_item_picture>https://example.com/article-img.jpg</ht:news_item_picture>
      </ht:news_item>
      <ht:news_item>
        <ht:news_item_title>Crypto markets rally</ht:news_item_title>
        <ht:news_item_url>https://example.com/article2</ht:news_item_url>
        <ht:news_item_source>BBC</ht:news_item_source>
      </ht:news_item>
    </item>
    <item>
      <title>ethereum</title>
      <ht:approx_traffic>100K+</ht:approx_traffic>
      <pubDate>Mon, 01 Jan 2024 11:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""


class TestParseRssXml:
    """Test XML parsing function"""

    def test_parse_invalid_xml_raises_error(self):
        """Test invalid XML raises DownloadError"""
        invalid_xml = b"<not valid xml"

        with pytest.raises(DownloadError) as exc_info:
            _parse_rss_xml(
                invalid_xml,
                geo='US',
                include_images=False,
                include_articles=False,
                max_articles_per_trend=0
            )

        assert 'Failed to parse RSS XML' in str(exc_info.value)

    def test_parse_malformed_date(self):
        """Test parsing handles malformed dates gracefully"""
        xml_with_bad_date = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
          <channel>
            <item>
              <title>test</title>
              <ht:approx_traffic>100+</ht:approx_traffic>
              <pubDate>Invalid Date Format</pubDate>
            </item>
          </channel>
        </rss>
        """

        trends = _parse_rss_xml(
            xml_with_bad_date,
            geo='US',
            include_images=False,
            include_articles=False,
            max_articles_per_trend=0
        )

        assert len(trends) == 1
        # Should fallback to string
        assert trends[0]['published'] == 'Invalid Date Format'

    def test_parse_basic(self):
        """Test basic XML parsing"""
        trends = _parse_rss_xml(
            SAMPLE_RSS_XML,
            geo='US',
            include_images=True,
            include_articles=True,
            max_articles_per_trend=5
        )

        assert len(trends) == 2
        assert trends[0]['trend'] == 'bitcoin'
        assert trends[0]['traffic'] == '500K+'
        assert trends[1]['trend'] == 'ethereum'

    def test_parse_with_images(self):
        """Test parsing includes images"""
        trends = _parse_rss_xml(
            SAMPLE_RSS_XML,
            geo='US',
            include_images=True,
            include_articles=False,
            max_articles_per_trend=0
        )

        assert 'image' in trends[0]
        assert trends[0]['image']['url'] == 'https://example.com/image.jpg'
        assert trends[0]['image']['source'] == 'Reuters'

    def test_parse_without_images(self):
        """Test parsing excludes images when disabled"""
        trends = _parse_rss_xml(
            SAMPLE_RSS_XML,
            geo='US',
            include_images=False,
            include_articles=False,
            max_articles_per_trend=0
        )

        assert 'image' not in trends[0]

    def test_parse_with_articles(self):
        """Test parsing includes articles"""
        trends = _parse_rss_xml(
            SAMPLE_RSS_XML,
            geo='US',
            include_images=False,
            include_articles=True,
            max_articles_per_trend=5
        )

        assert 'news_articles' in trends[0]
        assert len(trends[0]['news_articles']) == 2
        assert trends[0]['news_articles'][0]['headline'] == 'Bitcoin surges past $50K'
        assert trends[0]['news_articles'][0]['source'] == 'CNN'

    def test_parse_max_articles_limit(self):
        """Test max articles limit"""
        trends = _parse_rss_xml(
            SAMPLE_RSS_XML,
            geo='US',
            include_images=False,
            include_articles=True,
            max_articles_per_trend=1
        )

        assert len(trends[0]['news_articles']) == 1

    def test_parse_zero_articles(self):
        """Test zero articles limit"""
        trends = _parse_rss_xml(
            SAMPLE_RSS_XML,
            geo='US',
            include_images=False,
            include_articles=True,
            max_articles_per_trend=0
        )

        assert len(trends[0]['news_articles']) == 0

    def test_parse_includes_explore_link(self):
        """Test parsing includes explore link"""
        trends = _parse_rss_xml(
            SAMPLE_RSS_XML,
            geo='US',
            include_images=False,
            include_articles=False,
            max_articles_per_trend=0
        )

        assert 'explore_link' in trends[0]
        assert 'trends.google.com' in trends[0]['explore_link']


class TestFormatOutput:
    """Test output formatting function"""

    def test_format_dict(self):
        """Test dict format returns list"""
        trends = [{'trend': 'test', 'traffic': '100+'}]
        result = _format_output(trends, 'dict', False, False)

        assert result is trends

    def test_format_csv_empty_trends(self):
        """Test CSV format with empty trends returns empty string"""
        trends = []
        result = _format_output(trends, 'csv', False, False)

        assert result == ""

    def test_format_json(self):
        """Test JSON format returns string"""
        trends = [{'trend': 'test', 'traffic': '100+'}]
        result = _format_output(trends, 'json', False, False)

        assert isinstance(result, str)
        assert '"trend": "test"' in result

    def test_format_csv(self):
        """Test CSV format returns string"""
        trends = [
            {'trend': 'test', 'traffic': '100+', 'published': '2024-01-01', 'explore_link': 'http://example.com'}
        ]
        result = _format_output(trends, 'csv', False, False)

        assert isinstance(result, str)
        assert 'trend,traffic' in result
        assert 'test,100+' in result

    def test_format_invalid(self):
        """Test invalid format raises error"""
        trends = [{'trend': 'test'}]

        with pytest.raises(InvalidParameterError):
            _format_output(trends, 'invalid', False, False)


class TestValidateGeo:
    """Test geo validation"""

    def test_valid_country(self):
        """Test valid country codes"""
        assert _validate_geo_rss('US') == 'US'
        assert _validate_geo_rss('GB') == 'GB'
        assert _validate_geo_rss('CA') == 'CA'

    def test_valid_us_state(self):
        """Test valid US state codes"""
        assert _validate_geo_rss('US-CA') == 'US-CA'
        assert _validate_geo_rss('US-NY') == 'US-NY'

    def test_lowercase_converted(self):
        """Test lowercase is converted to uppercase"""
        assert _validate_geo_rss('us') == 'US'
        assert _validate_geo_rss('us-ca') == 'US-CA'

    def test_invalid_geo(self):
        """Test invalid geo raises error"""
        with pytest.raises(InvalidParameterError) as exc_info:
            _validate_geo_rss('INVALID')

        assert 'Invalid geo code' in str(exc_info.value)

    def test_invalid_geo_suggests_similar(self):
        """Test invalid geo suggests similar codes"""
        with pytest.raises(InvalidParameterError) as exc_info:
            _validate_geo_rss('USA')

        assert 'Did you mean' in str(exc_info.value)


class TestMakeCacheKey:
    """Test cache key generation"""

    def test_cache_key_format(self):
        """Test cache key format"""
        key = _make_cache_key('US', True, True, 5)
        assert key == 'US:True:True:5'

    def test_cache_key_different_params(self):
        """Test different params create different keys"""
        key1 = _make_cache_key('US', True, True, 5)
        key2 = _make_cache_key('GB', True, True, 5)
        key3 = _make_cache_key('US', False, True, 5)

        assert key1 != key2
        assert key1 != key3


class TestHandleHttpError:
    """Test HTTP error handling"""

    def test_429_raises_rate_limit(self):
        """Test 429 raises RateLimitError"""
        with pytest.raises(RateLimitError):
            _handle_http_error(429, 'US', 'http://example.com')

    def test_403_raises_rate_limit(self):
        """Test 403 raises RateLimitError"""
        with pytest.raises(RateLimitError):
            _handle_http_error(403, 'US', 'http://example.com')

    def test_404_raises_download_error(self):
        """Test 404 raises DownloadError"""
        with pytest.raises(DownloadError) as exc_info:
            _handle_http_error(404, 'XX', 'http://example.com')

        assert '404' in str(exc_info.value)

    def test_500_raises_download_error(self):
        """Test 500 raises DownloadError"""
        with pytest.raises(DownloadError) as exc_info:
            _handle_http_error(500, 'US', 'http://example.com')

        assert '500' in str(exc_info.value)

    def test_other_error_raises_download_error(self):
        """Test other errors raise DownloadError"""
        with pytest.raises(DownloadError):
            _handle_http_error(418, 'US', 'http://example.com')


class TestDownloadWithMock:
    """Test download function with mocked network"""

    def setup_method(self):
        """Clear cache before each test"""
        clear_rss_cache()

    @patch('trendspyg.rss_downloader.requests.get')
    def test_download_success(self, mock_get):
        """Test successful download"""
        mock_response = MagicMock()
        mock_response.content = SAMPLE_RSS_XML
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        trends = download_google_trends_rss(geo='US', cache=False)

        assert len(trends) == 2
        assert trends[0]['trend'] == 'bitcoin'
        mock_get.assert_called_once()

    @patch('trendspyg.rss_downloader.requests.get')
    def test_download_uses_cache(self, mock_get):
        """Test that cache is used on second call"""
        mock_response = MagicMock()
        mock_response.content = SAMPLE_RSS_XML
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # First call
        download_google_trends_rss(geo='US', cache=True)
        # Second call should use cache
        download_google_trends_rss(geo='US', cache=True)

        # Should only call network once
        assert mock_get.call_count == 1

    @patch('trendspyg.rss_downloader.requests.get')
    def test_download_bypass_cache(self, mock_get):
        """Test that cache=False bypasses cache"""
        mock_response = MagicMock()
        mock_response.content = SAMPLE_RSS_XML
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Both calls with cache=False
        download_google_trends_rss(geo='US', cache=False)
        download_google_trends_rss(geo='US', cache=False)

        # Should call network twice
        assert mock_get.call_count == 2

    @patch('trendspyg.rss_downloader.requests.get')
    def test_download_connection_error(self, mock_get):
        """Test connection error handling"""
        import requests
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        with pytest.raises(DownloadError) as exc_info:
            download_google_trends_rss(geo='US', cache=False)

        assert 'Connection failed' in str(exc_info.value)

    @patch('trendspyg.rss_downloader.requests.get')
    def test_download_timeout(self, mock_get):
        """Test timeout error handling"""
        import requests
        mock_get.side_effect = requests.Timeout("Request timed out")

        with pytest.raises(DownloadError) as exc_info:
            download_google_trends_rss(geo='US', cache=False)

        assert 'timed out' in str(exc_info.value)

    @patch('trendspyg.rss_downloader.requests.get')
    def test_download_http_error(self, mock_get):
        """Test HTTP error handling"""
        import requests
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.side_effect = requests.HTTPError(response=mock_response)

        with pytest.raises(RateLimitError):
            download_google_trends_rss(geo='US', cache=False)

    @patch('trendspyg.rss_downloader.requests.get')
    def test_download_different_output_formats(self, mock_get):
        """Test different output formats"""
        mock_response = MagicMock()
        mock_response.content = SAMPLE_RSS_XML
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Dict
        result = download_google_trends_rss(geo='US', output_format='dict', cache=False)
        assert isinstance(result, list)

        # JSON
        result = download_google_trends_rss(geo='US', output_format='json', cache=False)
        assert isinstance(result, str)
        assert result.startswith('[')

        # CSV
        result = download_google_trends_rss(geo='US', output_format='csv', cache=False)
        assert isinstance(result, str)
        assert 'trend,traffic' in result
