"""pytrends-compatible front door: existing pytrends code runs on trendspyg.

Replace ``pytrends`` with ``trendspyg.compat`` in the imports::

    from pytrends.request import TrendReq          # before
    from trendspyg.compat.request import TrendReq  # after

    from pytrends.exceptions import TooManyRequestsError          # before
    from trendspyg.compat.exceptions import TooManyRequestsError  # after

``from trendspyg.compat import TrendReq`` works too. Requires pandas
(``pip install trendspyg[analysis]``), as pytrends did. Not imported by
``import trendspyg``; it loads only when used.
"""

from .exceptions import CompatWarning, ResponseError, TooManyRequestsError
from .request import TrendReq

__all__ = ["TrendReq", "ResponseError", "TooManyRequestsError", "CompatWarning"]
