"""pytrends-compatible exceptions, mirroring ``pytrends.exceptions``.

Code that catches ``ResponseError`` or ``TooManyRequestsError`` keeps working
after its imports switch from ``pytrends`` to ``trendspyg.compat``. Both are
also trendspyg exceptions: ``TooManyRequestsError`` is a
:class:`~trendspyg.RateLimitError`, and both are
:class:`~trendspyg.TrendspygException`, so either family of ``except`` clauses
catches them.
"""

from typing import Any, Optional

from ..exceptions import RateLimitError, TrendspygException

__all__ = ["ResponseError", "TooManyRequestsError", "CompatWarning"]


class ResponseError(TrendspygException):
    """Google did not return usable data (pytrends' name for this error).

    ``response`` is always ``None`` here: trendspyg reads Google's data through
    a real browser session, so there is no single HTTP response to attach.
    """

    def __init__(self, message: str, response: Optional[Any] = None) -> None:
        super().__init__(message)
        self.response = response


class TooManyRequestsError(ResponseError, RateLimitError):
    """Google is rate-limiting this machine (pytrends' HTTP 429 error).

    Also a :class:`~trendspyg.RateLimitError`. For keyword analysis, stop for
    tens of minutes at least; retrying in a loop extends the block.
    """


class CompatWarning(UserWarning):
    """A pytrends feature that this compatibility layer can only partly serve."""
