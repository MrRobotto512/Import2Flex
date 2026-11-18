"""Optional TMDb lookup to get the canonical movie title and year."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

TMDB_SEARCH = "https://api.themoviedb.org/3/search/movie"


def lookup_movie(query: str, api_key: str, timeout: float = 10) -> tuple[str, str] | None:
    """Return ``(title, year)`` for the best TMDb match, or ``None``.

    Accepts either a v3 API key or a v4 "API Read Access Token".
    """
    if not api_key or not query:
        return None
    params = {"query": query, "include_adult": "false"}
    headers = {"Accept": "application/json"}
    if len(api_key) > 40:  # v4 bearer token
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key
    url = f"{TMDB_SEARCH}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception as exc:  # network errors should never stop a rip
        log.warning("TMDb lookup failed for %r: %s", query, exc)
        return None
    results = data.get("results") or []
    if not results:
        log.info("TMDb: no match for %r", query)
        return None
    best = results[0]
    title = best.get("title") or best.get("original_title") or query
    year = (best.get("release_date") or "")[:4]
    log.info("TMDb: %r -> %s (%s)", query, title, year or "?")
    return title, year
