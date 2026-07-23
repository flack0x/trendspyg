"""Real-time monitoring for trendspyg — built entirely on the RSS path.

New in 0.7.0. This is the ROADMAP's "monitoring & reliability" target, kept
deliberately narrow.

Why RSS-only:
    The RSS path (:func:`download_google_trends_rss`) is the one durable,
    browser-free primitive (typically 0.2-2s, network-dependent). The CSV and
    Explore paths drive Selenium and
    are explicitly *not* for high-frequency polling. Monitoring therefore polls
    the RSS feed and diffs consecutive snapshots.

Design:
    The diff core — :func:`diff_trends` and :func:`filter_changes` — is pure and
    JSON-safe: no network, no browser, no clock. It is fully unit-testable
    offline, so the monitoring feature lands under the coverage gate without a
    single Chrome or network test. :func:`watch_google_trends_rss` is the thin
    polling loop on top; its ``sleep`` and the underlying fetch are injectable so
    it, too, is testable without waiting or hitting the network.

Typical use::

    from trendspyg import watch_google_trends_rss

    for change in watch_google_trends_rss(geo="US", interval=60):
        print(change["event"], change["keyword"])
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, cast

from .rss_downloader import download_google_trends_rss
from .types import TrendChange

#: Bumped when the :class:`~trendspyg.types.TrendChange` shape changes, so agents
#: can detect drift the same way they can for the other envelopes.
MONITOR_SCHEMA_VERSION = "1.0"

#: The complete set of events :func:`diff_trends` can emit.
CHANGE_EVENTS = ("new", "dropped", "volume_up", "volume_down", "rank_change")


def _keyword(trend: Dict[str, Any]) -> str:
    """Read the search term from a trend dict.

    Accepts both the raw RSS shape (``trend``) and the normalized shape
    (``keyword``) so monitoring works on either.
    """
    return str(trend.get("trend") or trend.get("keyword") or "")


def _volume(trend: Dict[str, Any]) -> int:
    """Read the parsed lower-bound traffic (``traffic_min`` / ``volume_min``)."""
    value = trend.get("traffic_min", trend.get("volume_min", 0))
    return int(value) if isinstance(value, (int, float)) else 0


def diff_trends(old: Sequence[Dict[str, Any]], new: Sequence[Dict[str, Any]]) -> List[TrendChange]:
    """Diff two RSS snapshots and return the list of changes between them.

    Pure and deterministic — no network, no clock. Each trend's rank is its
    1-based position in the snapshot list (Google returns them in trend order).

    Args:
        old: The previous snapshot — a list of trend dicts (RSS ``dict`` output).
        new: The current snapshot, same shape.

    Returns:
        A list of :class:`~trendspyg.types.TrendChange`, ordered by the new
        snapshot's ranking with ``"dropped"`` events appended last. Unchanged
        trends produce no entry. A trend whose volume *and* rank both changed
        yields a single event (volume takes the label) — the rank fields still
        carry both values, so no information is lost.
    """
    old_map: Dict[str, Dict[str, int]] = {}
    for i, trend in enumerate(old, start=1):
        key = _keyword(trend)
        if key and key not in old_map:
            old_map[key] = {"rank": i, "volume_min": _volume(trend)}

    changes: List[TrendChange] = []
    seen_new: set = set()
    for i, trend in enumerate(new, start=1):
        key = _keyword(trend)
        if not key or key in seen_new:
            continue
        seen_new.add(key)
        cur_vol = _volume(trend)

        if key not in old_map:
            changes.append(
                TrendChange(
                    event="new",
                    keyword=key,
                    rank=i,
                    prev_rank=None,
                    volume_min=cur_vol,
                    prev_volume_min=None,
                )
            )
            continue

        prev = old_map[key]
        vol_changed = cur_vol != prev["volume_min"]
        rank_changed = i != prev["rank"]
        if vol_changed:
            event = "volume_up" if cur_vol > prev["volume_min"] else "volume_down"
        elif rank_changed:
            event = "rank_change"
        else:
            continue  # unchanged — emit nothing

        changes.append(
            TrendChange(
                event=event,
                keyword=key,
                rank=i,
                prev_rank=prev["rank"],
                volume_min=cur_vol,
                prev_volume_min=prev["volume_min"],
            )
        )

    for key, prev in old_map.items():
        if key not in seen_new:
            changes.append(
                TrendChange(
                    event="dropped",
                    keyword=key,
                    rank=None,
                    prev_rank=prev["rank"],
                    volume_min=None,
                    prev_volume_min=prev["volume_min"],
                )
            )

    return changes


def filter_changes(
    changes: Sequence[TrendChange],
    *,
    min_volume: Optional[int] = None,
    events: Optional[Sequence[str]] = None,
    keywords: Optional[Sequence[str]] = None,
) -> List[TrendChange]:
    """Filter a change list down to what a caller cares about.

    Args:
        changes: Output of :func:`diff_trends`.
        min_volume: Keep only changes whose current or previous ``volume_min`` is
            at least this. ``None`` disables the check.
        events: Keep only these event types (e.g. ``["new", "volume_up"]``).
            ``None`` keeps all.
        keywords: A watchlist — keep only changes whose keyword contains one of
            these terms (case-insensitive substring, so ``"bitcoin"`` matches
            ``"bitcoin price"``). ``None`` keeps all.

    Returns:
        A new filtered list (input is not mutated).
    """
    event_set = set(events) if events is not None else None
    watch_terms = [k.lower() for k in keywords] if keywords else None

    kept: List[TrendChange] = []
    for change in changes:
        if event_set is not None and change["event"] not in event_set:
            continue
        if min_volume is not None:
            volume = change["volume_min"]
            if volume is None:
                volume = change["prev_volume_min"] or 0
            if volume < min_volume:
                continue
        if watch_terms is not None:
            keyword = change["keyword"].lower()
            if not any(term in keyword for term in watch_terms):
                continue
        kept.append(change)
    return kept


def post_webhook(url: str, change: TrendChange, timeout: float = 10.0) -> bool:
    """Fire-and-forget POST of one change as JSON. Never raises.

    A deliberately dumb notifier: one HTTP POST, a timeout, no retries, no
    signing, no queue (those are v1 concerns — see ROADMAP). Returns ``True`` on
    a 2xx response and ``False`` on any non-2xx or transport error, so a caller
    can count failures without handling exceptions.
    """
    try:
        import requests

        response = requests.post(url, json=change, timeout=timeout)
        return 200 <= response.status_code < 300
    except Exception:
        return False


def watch_google_trends_rss(
    geo: str = "US",
    interval: float = 60.0,
    iterations: Optional[int] = None,
    *,
    on_change: Optional[Callable[[TrendChange], Any]] = None,
    min_volume: Optional[int] = None,
    events: Optional[Sequence[str]] = None,
    keywords: Optional[Sequence[str]] = None,
    webhook: Optional[str] = None,
    sleep: Callable[[float], Any] = time.sleep,
    **rss_kwargs: Any,
) -> Iterator[TrendChange]:
    """Poll the RSS feed and yield each change between consecutive snapshots.

    Safe for continuous polling (the RSS path is browser-free and typically
    0.2-2s depending on network). The
    first poll establishes a baseline and yields nothing; each later poll is
    diffed against the previous one.

    Args:
        geo: Country/region code to monitor.
        interval: Seconds to wait between polls.
        iterations: Number of polls before stopping. ``None`` (default) runs
            forever until the caller stops iterating (e.g. Ctrl-C).
        on_change: Optional callback invoked with each yielded change.
        min_volume: Passed to :func:`filter_changes`.
        events: Passed to :func:`filter_changes`.
        keywords: Watchlist passed to :func:`filter_changes`.
        webhook: If given, each change is POSTed there via :func:`post_webhook`.
        sleep: Sleep function (injectable for testing).
        **rss_kwargs: Extra keyword args forwarded to
            :func:`download_google_trends_rss` (e.g. ``include_images=False``).
            ``output_format``, ``normalize`` and ``cache`` are managed internally
            and ignored if passed.

    Yields:
        :class:`~trendspyg.types.TrendChange` objects, one at a time.
    """
    for reserved in ("output_format", "normalize", "cache"):
        rss_kwargs.pop(reserved, None)

    previous: Optional[List[Dict[str, Any]]] = None
    count = 0
    while iterations is None or count < iterations:
        snapshot = cast(
            List[Dict[str, Any]],
            download_google_trends_rss(geo=geo, cache=False, output_format="dict", **rss_kwargs),
        )
        count += 1

        if previous is not None:
            changes = filter_changes(
                diff_trends(previous, snapshot),
                min_volume=min_volume,
                events=events,
                keywords=keywords,
            )
            for change in changes:
                if on_change is not None:
                    on_change(change)
                if webhook is not None:
                    post_webhook(webhook, change)
                yield change

        previous = snapshot

        if iterations is not None and count >= iterations:
            break
        sleep(interval)
