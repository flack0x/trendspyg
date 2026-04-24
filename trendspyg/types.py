"""Typed return shapes for trendspyg public data.

These are static-analysis hints only — runtime values are plain dicts. Exporting
them means IDEs and coding agents (Claude Code, Codex, Gemini CLI, etc.) get
autocomplete and type-checking without needing to scan the parser to learn the
dict shape.

Import from the package root:

    from trendspyg import Trend, NewsArticle, TrendImage, TrendEnvelope

All TypedDicts use ``total=False`` — optional fields (``image``, ``news_articles``)
are genuinely optional depending on the ``include_images`` / ``include_articles``
flags passed to the downloader.
"""

from __future__ import annotations

from typing import List, TypedDict


class TrendImage(TypedDict, total=False):
    """Image associated with a trend, from a news source."""

    url: str
    source: str


class NewsArticle(TypedDict, total=False):
    """A single news article attached to a trend."""

    headline: str
    url: str
    source: str
    image: str


class Trend(TypedDict, total=False):
    """A trending search term with metadata.

    Keys:
        trend: The search term (e.g. ``"Nia Long"``).
        traffic: Human-readable traffic band (e.g. ``"50,000+"``).
        traffic_min: Parsed lower bound of ``traffic`` as an int (new in 0.4.3).
                     Use this for sorting/filtering; always present, 0 if unparseable.
        published: ISO 8601 timestamp string, or a ``datetime`` before JSON serialization.
        explore_link: URL to the Google Trends Explore page for this term.
        image: Optional. Only present when ``include_images=True``.
        news_articles: Optional. Only present when ``include_articles=True``.
    """

    trend: str
    traffic: str
    traffic_min: int
    published: str
    explore_link: str
    image: TrendImage
    news_articles: List[NewsArticle]


class TrendEnvelope(TypedDict):
    """Envelope wrapper returned by ``--envelope`` CLI flag (new in 0.4.3).

    Useful for pipelines and archives where you need to know *when* and *where*
    the snapshot was taken alongside the data itself.
    """

    fetched_at: str
    geo: str
    count: int
    trends: List[Trend]


__all__ = ["TrendImage", "NewsArticle", "Trend", "TrendEnvelope"]
