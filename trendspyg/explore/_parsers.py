"""Pure parsers for Google's widgetdata JSON shapes (no browser, no network)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def _strip_xssi(text: str) -> str:
    """Drop Google's ``)]}',`` anti-JSON-hijack prefix, returning clean JSON."""
    brace = text.find("{")
    return text[brace:] if brace != -1 else text


def _epoch_to_iso(epoch: str) -> str:
    """Convert a Trends unix-seconds string to an ISO 8601 UTC string."""
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()


def _parse_multiline(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse ``widgetdata/multiline`` JSON into a list of interest points.

    Each point: ``{'date': ISO8601, 'value': int, 'is_partial': bool}``.
    ``value`` is Google's 0-100 relative interest index. The most recent point
    is usually flagged ``is_partial`` (the current period is still in progress).
    """
    points: List[Dict[str, Any]] = []
    for entry in data.get("default", {}).get("timelineData", []) or []:
        values = entry.get("value") or [0]
        try:
            value = int(values[0])
        except (TypeError, ValueError, IndexError):
            value = 0
        epoch = entry.get("time")
        try:
            date_iso = _epoch_to_iso(epoch) if epoch is not None else ""
        except (TypeError, ValueError):
            date_iso = ""
        points.append(
            {
                "date": date_iso,
                "value": value,
                "is_partial": bool(entry.get("isPartial", False)),
            }
        )
    return points


def _parse_relatedsearches(data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Parse ``widgetdata/relatedsearches`` into ``{'top': [...], 'rising': [...]}``.

    Google returns up to two ranked lists: index 0 is *top* (0-100 relative),
    index 1 is *rising* (growth — ``value`` is a percent, or a sentinel for
    "Breakout"). Each item: ``{'query', 'value', 'formatted_value', 'link'}``.
    """
    out: Dict[str, List[Dict[str, Any]]] = {"top": [], "rising": []}
    ranked_lists = data.get("default", {}).get("rankedList", []) or []
    for idx, bucket in enumerate(("top", "rising")):
        if idx >= len(ranked_lists):
            break
        for kw in ranked_lists[idx].get("rankedKeyword", []) or []:
            link = kw.get("link", "") or ""
            if link and link.startswith("/"):
                link = "https://trends.google.com" + link
            out[bucket].append(
                {
                    "query": kw.get("query", "") or "",
                    "value": int(kw.get("value", 0) or 0),
                    "formatted_value": kw.get("formattedValue", "") or "",
                    "link": link,
                }
            )
    return out


def _parse_comparedgeo(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse ``widgetdata/comparedgeo`` into a list of regional interest rows.

    Each row: ``{'geo_code', 'geo_name', 'value': int}`` (0-100 relative),
    already sorted by Google from strongest to weakest interest.
    """
    rows: List[Dict[str, Any]] = []
    for entry in data.get("default", {}).get("geoMapData", []) or []:
        values = entry.get("value") or [0]
        try:
            value = int(values[0])
        except (TypeError, ValueError, IndexError):
            value = 0
        # Skip regions Google reports with no data
        has_data = entry.get("hasData") or [False]
        if not has_data[0]:
            continue
        rows.append(
            {
                "geo_code": entry.get("geoCode", "") or "",
                "geo_name": entry.get("geoName", "") or "",
                "value": value,
            }
        )
    return rows


def _parse_multiline_comparison(
    data: Dict[str, Any], keywords: List[str]
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Parse a multi-keyword ``widgetdata/multiline`` payload.

    Google returns one ``value`` array per point, aligned to the comparison's
    keyword order (verified live 2026-07-10). Returns ``(points, averages)``:
    each point ``{'date': ISO8601, 'values': {keyword: int}, 'is_partial': bool}``,
    and ``averages`` as ``{keyword: int}`` from the payload's ``averages`` array.
    Missing/short arrays fill with 0 rather than raising — the shape stays fixed.
    """
    points: List[Dict[str, Any]] = []
    for entry in data.get("default", {}).get("timelineData", []) or []:
        raw_values = entry.get("value") or []
        values: Dict[str, int] = {}
        for i, kw in enumerate(keywords):
            try:
                values[kw] = int(raw_values[i])
            except (TypeError, ValueError, IndexError):
                values[kw] = 0
        epoch = entry.get("time")
        try:
            date_iso = _epoch_to_iso(epoch) if epoch is not None else ""
        except (TypeError, ValueError):
            date_iso = ""
        points.append(
            {
                "date": date_iso,
                "values": values,
                "is_partial": bool(entry.get("isPartial", False)),
            }
        )
    raw_averages = data.get("default", {}).get("averages") or []
    averages: Dict[str, int] = {}
    for i, kw in enumerate(keywords):
        try:
            averages[kw] = int(raw_averages[i])
        except (TypeError, ValueError, IndexError):
            averages[kw] = 0
    return points, averages


def _parse_comparedgeo_comparison(
    data: Dict[str, Any], keywords: List[str]
) -> List[Dict[str, Any]]:
    """Parse a *combined* multi-keyword ``widgetdata/comparedgeo`` payload.

    Each row: ``{'geo_code', 'geo_name', 'values': {keyword: int},
    'top_keyword': str}``. ``top_keyword`` comes from Google's
    ``maxValueIndex`` (falling back to our own argmax if absent). Regions
    where Google reports no data for any keyword are skipped.
    """
    rows: List[Dict[str, Any]] = []
    for entry in data.get("default", {}).get("geoMapData", []) or []:
        has_data = entry.get("hasData") or []
        if not any(has_data):
            continue
        raw_values = entry.get("value") or []
        values: Dict[str, int] = {}
        for i, kw in enumerate(keywords):
            try:
                values[kw] = int(raw_values[i])
            except (TypeError, ValueError, IndexError):
                values[kw] = 0
        max_idx = entry.get("maxValueIndex")
        if not isinstance(max_idx, int) or not 0 <= max_idx < len(keywords):
            max_idx = max(range(len(keywords)), key=lambda i: values[keywords[i]])
        rows.append(
            {
                "geo_code": entry.get("geoCode", "") or "",
                "geo_name": entry.get("geoName", "") or "",
                "values": values,
                "top_keyword": keywords[max_idx],
            }
        )
    return rows
