"""Custom exceptions for trendspy."""


class TrendspyException(Exception):
    """Base exception for all trendspy errors."""
    pass


class DownloadError(TrendspyException):
    """Raised when download fails."""
    pass


class RateLimitError(TrendspyException):
    """Raised when rate limit is exceeded."""
    pass


class InvalidParameterError(TrendspyException):
    """Raised when invalid parameters are provided."""
    pass


class BrowserError(TrendspyException):
    """Raised when browser automation fails."""
    pass


class ParseError(TrendspyException):
    """Raised when parsing CSV/RSS data fails."""
    pass
