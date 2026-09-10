"""Resolve ambiguous search text to Google Trends topic candidates."""

import json
import math
import re
from typing import List
from urllib.parse import quote

import requests

from .exceptions import DownloadError, InvalidParameterError, ParseError, RateLimitError
from .types import KeywordSuggestion
from .utils import TTLCache

_SUGGESTIONS_URL = "https://trends.google.com/trends/api/autocomplete/"
_LANGUAGE = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")
_cache: TTLCache[List[KeywordSuggestion]] = TTLCache(ttl=3600, max_size=128)


def _parse_suggestions(text: str) -> List[KeywordSuggestion]:
    text = text.lstrip()
    if text.startswith(")]}'"):
        text = text[4:].lstrip(",\r\n ")
    try:
        payload = json.loads(text)
        topics = payload["default"]["topics"]
        if not isinstance(topics, list):
            raise TypeError
        result: List[KeywordSuggestion] = []
        for topic in topics:
            if not isinstance(topic, dict) or any(
                not isinstance(topic.get(key), str) or not topic[key].strip()
                for key in ("mid", "title", "type")
            ):
                raise ValueError
            result.append({"mid": topic["mid"], "title": topic["title"], "type": topic["type"]})
        return result
    except (ValueError, TypeError, KeyError) as exc:
        raise ParseError("Google returned an unexpected topic-lookup response.") from exc


def get_keyword_suggestions(
    keyword: str,
    language: str = "en-US",
    *,
    cache: bool = True,
    timeout: float = 10.0,
) -> List[KeywordSuggestion]:
    """Find Google Trends topics matching text, without starting Chrome.

    Each candidate has ``mid`` (the topic ID), ``title`` and ``type``. Choose
    the intended meaning explicitly, then pass its ``mid`` as the keyword to
    an Explore function. For example, Apple the fruit and Apple the company
    have different IDs. Results are suggestions, not a popularity ranking or
    an exhaustive catalog; an empty list means Google offered no candidates.

    Args:
        keyword: Non-empty search text; leading/trailing whitespace is removed.
        language: Language tag for candidate labels, e.g. ``en-US``, ``fr`` or
            ``es-419``. Does not set the geography of a later Explore query.
        cache: Reuse identical keyword/language lookups for one hour in this
            process (up to 128 entries). False bypasses cache reads and writes.
            No cookies or files are stored; RSS cache controls are independent.
        timeout: Positive finite seconds for each connection/read wait.
            One lookup attempt, no retry loop. Not a whole-call deadline.

    Raises:
        InvalidParameterError: Invalid keyword, language, cache or timeout.
        RateLimitError: Google returned HTTP 403/429; stop and back off.
        DownloadError: Network failure or another unsuccessful HTTP status.
        ParseError: Google returned malformed or unexpected data.
    """
    if not isinstance(keyword, str) or not keyword.strip():
        raise InvalidParameterError("keyword must be a non-empty string.")
    if not isinstance(language, str) or not _LANGUAGE.fullmatch(language):
        raise InvalidParameterError("language must be a language tag such as 'en-US' or 'fr'.")
    if not isinstance(cache, bool):
        raise InvalidParameterError("cache must be True or False for keyword suggestions.")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise InvalidParameterError("timeout must be a positive finite number of seconds.")

    keyword = keyword.strip()
    key = json.dumps([keyword, language])
    cached = _cache.get(key) if cache else None
    if cached is not None:
        return [item.copy() for item in cached]
    try:
        response = requests.get(
            _SUGGESTIONS_URL + quote(keyword, safe=""),
            params={"hl": language},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise DownloadError("Could not retrieve Google Trends topic suggestions.") from exc
    if response.status_code in (403, 429):
        raise RateLimitError("Google rate-limited topic lookup; stop and back off.")
    if not 200 <= response.status_code < 300:
        raise DownloadError(f"Google topic lookup returned HTTP {response.status_code}.")
    result = _parse_suggestions(response.text)
    if cache:
        _cache.set(key, [item.copy() for item in result])
    return result
