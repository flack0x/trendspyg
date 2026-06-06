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

from typing import Dict, List, Optional, TypedDict


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


class NormalizedTrend(TypedDict):
    """A single trend in the unified, agent-friendly schema (``normalize=True``).

    Unlike :class:`Trend`, every field here is **always present** and JSON-safe.
    Fields a given source cannot provide are filled with ``None`` / ``[]`` —
    never omitted — so an agent can rely on a fixed shape regardless of whether
    the data came from the RSS or the CSV path.

    Keys:
        keyword: The search term, verbatim from the source.
        rank: 1-based position in the source ordering.
        volume_text: Raw human-readable volume (e.g. ``"5M+"``); ``""`` if unknown.
        volume_min: Parsed lower bound of ``volume_text`` as an int; ``0`` if unparseable.
        started_at: ISO 8601 timestamp the trend started, or ``None``.
        ended_at: ISO 8601 timestamp the trend ended, or ``None`` if still active.
        is_active: ``True`` when ``ended_at`` is ``None``.
        related_queries: Related search terms (CSV breakdown); ``[]`` for RSS.
        news: News articles attached to the trend; ``[]`` for CSV.
        image: Trend image, or ``None``.
        explore_url: URL to the Google Trends Explore page for this term.
    """

    keyword: str
    rank: int
    volume_text: str
    volume_min: int
    started_at: Optional[str]
    ended_at: Optional[str]
    is_active: bool
    related_queries: List[str]
    news: List[NewsArticle]
    image: Optional[TrendImage]
    explore_url: str


class NormalizedEnvelope(TypedDict):
    """Envelope returned when ``normalize=True`` — unified across RSS and CSV.

    The shape is identical no matter which download path produced it, so a
    coding agent learns it once.
    """

    schema_version: str
    source: str
    geo: str
    fetched_at: str
    count: int
    trends: List[NormalizedTrend]


class InterestPoint(TypedDict):
    """One point in an interest-over-time series (Explore path, new in 0.6.0).

    Born JSON-safe — no ``normalize`` pass needed.

    Keys:
        date: ISO 8601 UTC timestamp of the period start.
        value: Google's 0-100 relative-interest index.
        is_partial: ``True`` for the final, still-in-progress period.
    """

    date: str
    value: int
    is_partial: bool


class RelatedQuery(TypedDict):
    """A related search query for an Explore keyword (new in 0.6.0).

    Keys:
        query: The related search term.
        value: For ``top`` queries, a 0-100 relative score; for ``rising``
            queries, the percent growth (e.g. ``3650``).
        formatted_value: Google's display string, e.g. ``"100"``, ``"+3,650%"``
            or ``"Breakout"``.
        link: Absolute Google Trends Explore URL for the related term.
    """

    query: str
    value: int
    formatted_value: str
    link: str


class RegionInterest(TypedDict):
    """Relative search interest for one region (Explore path, new in 0.6.0).

    Keys:
        geo_code: Region code (e.g. ``"US-CA"``).
        geo_name: Human-readable region name (e.g. ``"California"``).
        value: Google's 0-100 relative-interest index.
    """

    geo_code: str
    geo_name: str
    value: int


class ExploreEnvelope(TypedDict):
    """Full Explore result for a keyword (``download_google_trends_explore``).

    New in 0.6.0. Every field present and JSON-safe — an agent learns the shape
    once. ``related_queries`` / ``interest_by_region`` are empty lists when not
    requested or not returned by Google (the time series is the guaranteed part).
    """

    schema_version: str
    source: str
    keyword: str
    geo: str
    timeframe: str
    fetched_at: str
    count: int
    interest_over_time: List[InterestPoint]
    related_queries: Dict[str, List[RelatedQuery]]
    interest_by_region: List[RegionInterest]


__all__ = [
    "TrendImage",
    "NewsArticle",
    "Trend",
    "TrendEnvelope",
    "NormalizedTrend",
    "NormalizedEnvelope",
    "InterestPoint",
    "RelatedQuery",
    "RegionInterest",
    "ExploreEnvelope",
]
