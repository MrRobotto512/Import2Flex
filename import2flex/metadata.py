"""Optional TMDb lookup to get the canonical movie title and year."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

TMDB_SEARCH = "https://api.themoviedb.org/3/search/movie"
TMDB_MOVIE = "https://api.themoviedb.org/3/movie"

# How many search results get their running time checked against the disc.
CANDIDATES = 5


@dataclass
class Match:
    title: str
    year: str
    runtime: int = 0      # minutes, 0 when TMDb doesn't say
    doubt: str = ""       # why this match shouldn't be trusted, "" when it's fine


def _get(url: str, params: dict, api_key: str, timeout: float) -> dict:
    """GET a TMDb URL with a v3 API key or a v4 "API Read Access Token"."""
    params = dict(params)
    headers = {"Accept": "application/json"}
    if len(api_key) > 40:  # v4 bearer token
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fits(disc_minutes: int, movie_minutes: int) -> bool:
    """Is the disc's main title as long as the movie? (6 minutes or 6 % apart
    at most: credits, studio logos and PAL's 4 % speed-up.)"""
    if disc_minutes <= 0 or movie_minutes <= 0:
        return False
    return abs(disc_minutes - movie_minutes) <= max(6, movie_minutes * 0.06)


def pick(results: list[dict], query: str, disc_minutes: int,
         runtime_of: Callable[[dict], int]) -> Match | None:
    """Choose among TMDb's search ``results`` for a disc whose main title
    runs ``disc_minutes`` (0 = unknown).

    A disc label is often one clipped word (``FOREST`` on a Forrest Gump
    disc), and TMDb's first hit for it is then another movie altogether (The
    Forest). The running time tells them apart: the first of the top hits
    that is as long as the disc wins; when none is and the first hit is way
    off, it is returned with ``doubt`` set so the user gets asked.
    """
    if not results:
        return None

    def match(r: dict, runtime: int = 0) -> Match:
        return Match(r.get("title") or r.get("original_title") or query,
                     (r.get("release_date") or "")[:4], runtime)

    first = results[0]
    if disc_minutes <= 0:
        return match(first)
    first_runtime = 0
    for i, r in enumerate(results[:CANDIDATES]):
        runtime = runtime_of(r)
        if i == 0:
            first_runtime = runtime
        if fits(disc_minutes, runtime):
            return match(r, runtime)
    m = match(first, first_runtime)
    if first_runtime and abs(disc_minutes - first_runtime) > first_runtime * 0.15:
        m.doubt = (f"the disc runs {disc_minutes} min, but {m.title}"
                   f"{f' ({m.year})' if m.year else ''} runs {first_runtime} min")
    return m


def lookup_movie(query: str, api_key: str, disc_minutes: int = 0,
                 timeout: float = 10) -> Match | None:
    """Return the best TMDb match for ``query``, or ``None``.

    ``disc_minutes`` is the length of the disc's main title; see ``pick``.
    """
    if not api_key or not query:
        return None
    try:
        data = _get(TMDB_SEARCH, {"query": query, "include_adult": "false"}, api_key, timeout)
    except Exception as exc:  # network errors should never stop a rip
        log.warning("TMDb lookup failed for %r: %s", query, exc)
        return None

    def runtime_of(result: dict) -> int:
        try:
            return int(_get(f"{TMDB_MOVIE}/{result['id']}", {}, api_key, timeout).get("runtime") or 0)
        except Exception as exc:
            log.warning("TMDb: no running time for %r: %s", result.get("title"), exc)
            return 0

    found = pick(data.get("results") or [], query, disc_minutes, runtime_of)
    if not found:
        log.info("TMDb: no match for %r", query)
        return None
    log.info("TMDb: %r -> %s (%s)%s", query, found.title, found.year or "?",
             f"; unsure: {found.doubt}" if found.doubt else "")
    return found
