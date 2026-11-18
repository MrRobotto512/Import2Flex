"""Ask Plex Media Server to rescan after a new movie arrives."""
from __future__ import annotations

import logging
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)


def refresh_library(base_url: str, token: str, section_id: str = "") -> bool:
    if not token:
        return False
    section = section_id.strip() or "all"
    url = (f"{base_url.rstrip('/')}/library/sections/{urllib.parse.quote(section)}/refresh"
           f"?X-Plex-Token={urllib.parse.quote(token)}")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            ok = 200 <= resp.status < 300
    except Exception as exc:
        log.warning("Plex refresh failed: %s", exc)
        return False
    if ok:
        log.info("Asked Plex to rescan library section %s", section)
    return ok
