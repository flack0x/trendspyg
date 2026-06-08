"""Custom exceptions for trendspyg."""


class TrendspygException(Exception):
    """Base exception for all trendspyg errors."""

    pass


class DownloadError(TrendspygException):
    """Raised when download fails.

    Common causes:
    - Network connectivity issues
    - Download timeout
    - File save permission errors
    """

    pass


class RateLimitError(TrendspygException):
    """Raised when rate limit is exceeded.

    Google Trends may temporarily block requests if too many are made.
    Wait a few minutes before trying again.
    """

    pass


class InvalidParameterError(TrendspygException):
    """Raised when invalid parameters are provided.

    Check that:
    - geo is a valid country code (e.g., 'US', 'CA', 'UK')
    - hours is one of: 4, 24, 48, 168
    - category is valid (e.g., 'all', 'sports', 'technology')
    """

    pass


class BrowserError(TrendspygException):
    """Raised when browser automation fails.

    Common causes:
    - Chrome browser not installed
    - ChromeDriver version mismatch
    - Page load timeout
    - UI element not found (Google may have changed their interface)

    Solutions:
    - Ensure Chrome browser is installed
    - Update trendspyg: pip install --upgrade trendspyg
    - Check GitHub issues for known UI changes
    """

    pass


class ParseError(TrendspygException):
    """Raised when parsing CSV/RSS data fails.

    The downloaded file may be corrupted or in unexpected format.
    """

    pass
