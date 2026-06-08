"""Normalization layer — one agent-friendly schema for both download paths.

The RSS and CSV paths return very different raw shapes:

* RSS  — lowercase keys, ``traffic`` as text, ``published`` as a ``datetime``.
* CSV  — Google's human CSV headers (``'Search volume'``), stringly-typed
  numbers (``'5M+'``), a localized ``Started`` timestamp, and a comma-joined
  ``Trend breakdown`` string.

When a caller passes ``normalize=True`` the raw output is run through here and
returned as a single :class:`~trendspyg.types.NormalizedEnvelope` whose fields
are identical across both paths and JSON-safe throughout (no ``datetime``
objects, no ``NaN``, lists are real lists).

This module is **opt-in and additive** — it never changes the default output.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .utils import _parse_traffic_to_min

#: Bumped when the normalized schema changes shape, so agents can detect drift.
SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _clean_str(value: Any) -> Optional[str]:
    """Return a stripped non-empty string, or ``None`` for empty/NaN/non-str input."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _to_iso(value: Any) -> Optional[str]:
    """Convert a ``datetime`` or ISO-ish string to an ISO 8601 string, else ``None``."""
    if isinstance(value, datetime):
        return value.isoformat()
    text = _clean_str(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        # Not ISO — hand it back unchanged rather than dropping data.
        return text


# Google's CSV timestamps look like: "May 21, 2026 at 5:50:00 PM UTC+3"
# (the space before AM/PM is often a U+202F narrow no-break space).
_CSV_DATE_RE = re.compile(r"^(?P<body>.+?)\s+UTC(?P<off>[+-]\d{1,2}(?::?\d{2})?)?$")


def _parse_csv_datetime(value: Any) -> Optional[str]:
    """Parse Google's localized CSV timestamp into an ISO 8601 string.

    Returns ``None`` for empty / NaN / unparseable input rather than raising,
    so a single odd row never breaks a whole normalization pass.
    """
    if not isinstance(value, str):
        return None
    # Collapse every kind of unicode whitespace (incl. U+202F) to plain spaces.
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return None
    match = _CSV_DATE_RE.match(text)
    if not match:
        return None
    try:
        parsed = datetime.strptime(match.group("body"), "%b %d, %Y at %I:%M:%S %p")
    except ValueError:
        return None
    offset = match.group("off")
    if offset:
        sign = -1 if offset[0] == "-" else 1
        digits = offset.lstrip("+-")
        if ":" in digits:
            hours, minutes = digits.split(":")
        elif len(digits) > 2:
            hours, minutes = digits[:-2], digits[-2:]
        else:
            hours, minutes = digits, "0"
        tzinfo = timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))
    else:
        tzinfo = timezone.utc
    return parsed.replace(tzinfo=tzinfo).isoformat()


def _build_envelope(source: str, geo: str, trends: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wrap a list of normalized trends in the standard envelope."""
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "geo": geo,
        "fetched_at": _now_iso(),
        "count": len(trends),
        "trends": trends,
    }


def _normalized_trend(
    *,
    keyword: str,
    rank: int,
    volume_text: str,
    volume_min: int,
    started_at: Optional[str],
    ended_at: Optional[str],
    related_queries: List[str],
    news: List[Dict[str, Any]],
    image: Optional[Dict[str, Any]],
    explore_url: str,
) -> Dict[str, Any]:
    """Assemble one normalized trend dict — every field always present."""
    return {
        "keyword": keyword,
        "rank": rank,
        "volume_text": volume_text,
        "volume_min": volume_min,
        "started_at": started_at,
        "ended_at": ended_at,
        "is_active": ended_at is None,
        "related_queries": related_queries,
        "news": news,
        "image": image,
        "explore_url": explore_url,
    }


def normalize_rss(trends: List[Dict[str, Any]], geo: str) -> Dict[str, Any]:
    """Convert raw RSS trend dicts into a :class:`NormalizedEnvelope`.

    Args:
        trends: The list returned by ``download_google_trends_rss`` (dict format).
        geo: The region code the data was fetched for.
    """
    normalized: List[Dict[str, Any]] = []
    for rank, trend in enumerate(trends, start=1):
        raw_image = trend.get("image")
        image: Optional[Dict[str, Any]] = None
        if isinstance(raw_image, dict) and raw_image.get("url"):
            image = {
                "url": raw_image.get("url", ""),
                "source": raw_image.get("source", ""),
            }

        news: List[Dict[str, Any]] = []
        for article in trend.get("news_articles", []) or []:
            news.append(
                {
                    "headline": article.get("headline", ""),
                    "url": article.get("url", ""),
                    "source": article.get("source", ""),
                    "image": _clean_str(article.get("image")),
                }
            )

        normalized.append(
            _normalized_trend(
                keyword=trend.get("trend", "") or "",
                rank=rank,
                volume_text=trend.get("traffic", "") or "",
                volume_min=int(trend.get("traffic_min", 0) or 0),
                started_at=_to_iso(trend.get("published")),
                ended_at=None,  # RSS only ever reports currently-trending topics
                related_queries=[],  # RSS has no related-query breakdown
                news=news,
                image=image,
                explore_url=trend.get("explore_link", "") or "",
            )
        )
    return _build_envelope("rss", geo, normalized)


def normalize_csv(rows: List[Dict[str, Any]], geo: str) -> Dict[str, Any]:
    """Convert raw CSV row dicts into a :class:`NormalizedEnvelope`.

    Args:
        rows: The list returned by ``download_google_trends_csv`` (dict format).
        geo: The region code the data was fetched for.
    """
    normalized: List[Dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        volume_text = _clean_str(row.get("Search volume")) or ""
        breakdown = _clean_str(row.get("Trend breakdown")) or ""
        related_queries = [q.strip() for q in breakdown.split(",") if q.strip()]

        normalized.append(
            _normalized_trend(
                keyword=_clean_str(row.get("Trends")) or "",
                rank=rank,
                volume_text=volume_text,
                volume_min=_parse_traffic_to_min(volume_text),
                started_at=_parse_csv_datetime(row.get("Started")),
                ended_at=_parse_csv_datetime(row.get("Ended")),
                related_queries=related_queries,
                news=[],  # CSV has no news articles
                image=None,  # CSV has no images
                explore_url=_clean_str(row.get("Explore link")) or "",
            )
        )
    return _build_envelope("csv", geo, normalized)
