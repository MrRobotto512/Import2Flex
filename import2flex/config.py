"""User settings, stored as JSON in %APPDATA%\\Import2Flex\\config.json."""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import APP_NAME

log = logging.getLogger(__name__)


def app_data_dir() -> Path:
    """Folder for settings and logs."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_work_dir() -> str:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path.home() / ".cache"
    return str(base / APP_NAME / "work")


def default_makemkv_path() -> str:
    if sys.platform == "win32":
        for candidate in (
            r"C:\Program Files (x86)\MakeMKV\makemkvcon64.exe",
            r"C:\Program Files\MakeMKV\makemkvcon64.exe",
            r"C:\Program Files (x86)\MakeMKV\makemkvcon.exe",
        ):
            if Path(candidate).exists():
                return candidate
        return r"C:\Program Files (x86)\MakeMKV\makemkvcon64.exe"
    return "makemkvcon"


def default_handbrake_path() -> str:
    if sys.platform == "win32":
        for candidate in (
            r"C:\Program Files\HandBrake\HandBrakeCLI.exe",
            r"C:\Program Files\HandBrakeCLI\HandBrakeCLI.exe",
        ):
            if Path(candidate).exists():
                return candidate
        return r"C:\Program Files\HandBrake\HandBrakeCLI.exe"
    return "HandBrakeCLI"


def default_movies_dir() -> str:
    return str(Path.home() / "Videos" / "Movies")


@dataclass
class Config:
    # Where finished movies go (your Plex "Movies" library folder).
    movies_dir: str = field(default_factory=default_movies_dir)
    # Scratch space for the raw rip. Needs ~10 GB per DVD, ~50 GB per Blu-ray.
    work_dir: str = field(default_factory=default_work_dir)

    # Automation
    auto_rip: bool = True                 # start as soon as a video disc is inserted
    eject_when_done: bool = True          # eject after the rip finishes
    confirm_name: bool = False            # pop up a box to confirm/edit the movie name
    confirm_timeout_sec: int = 120        # ...then continue with the guessed name
    start_with_windows: bool = False
    start_minimized: bool = True
    notifications: bool = True

    # MakeMKV
    makemkv_path: str = field(default_factory=default_makemkv_path)
    min_title_seconds: int = 1200         # ignore titles shorter than 20 min (menus, trailers)
    rip_mode: str = "main"                # "main" = longest title only, "all" = every title

    # HandBrake (optional re-encode to shrink files)
    transcode: bool = False
    handbrake_path: str = field(default_factory=default_handbrake_path)
    handbrake_preset: str = "H.265 MKV 480p30"
    handbrake_extra_args: str = "--all-audio --all-subtitles"

    # ISO watch folder: any .iso dropped here is converted then deleted.
    iso_watch_enabled: bool = False
    iso_watch_dir: str = ""
    delete_iso_after: bool = True

    # Metadata / Plex
    tmdb_api_key: str = ""                # optional - gives proper title + year
    plex_url: str = "http://127.0.0.1:32400"
    plex_token: str = ""                  # optional - triggers a library scan
    plex_section_id: str = ""             # blank = refresh all libraries

    @classmethod
    def path(cls) -> Path:
        return app_data_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cfg
        except (OSError, ValueError) as exc:
            log.warning("Could not read settings (%s); using defaults", exc)
            return cfg
        known = {f.name: f for f in fields(cls)}
        for key, value in data.items():
            if key in known:
                default = getattr(cfg, key)
                if isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, int):
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        continue
                setattr(cfg, key, value)
        return cfg

    def save(self) -> None:
        tmp = self.path().with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(tmp, self.path())
