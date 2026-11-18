"""Thin wrapper around ``makemkvcon`` in robot (``-r``) mode.

Robot-mode output reference: https://www.makemkv.com/developers/usage.txt
"""
from __future__ import annotations

import csv
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .process import run_streaming

log = logging.getLogger(__name__)

# TINFO / CINFO attribute ids (apdefs.h)
AP_NAME = 2
AP_CHAPTER_COUNT = 8
AP_DURATION = 9
AP_DISK_SIZE_BYTES = 11
AP_OUTPUT_FILENAME = 27


class MakeMKVError(RuntimeError):
    pass


@dataclass
class Title:
    index: int
    name: str = ""
    duration: int = 0          # seconds
    size_bytes: int = 0
    chapters: int = 0
    output_file: str = ""


@dataclass
class DiscInfo:
    name: str = ""
    titles: list[Title] = field(default_factory=list)

    def main_title(self) -> Title | None:
        if not self.titles:
            return None
        return max(self.titles, key=lambda t: (t.duration, t.size_bytes))


@dataclass
class DriveEntry:
    index: int
    has_disc: bool
    drive_name: str
    disc_name: str
    device: str


def parse_fields(payload: str) -> list[str]:
    """Split a robot-mode payload (CSV with quoted strings)."""
    return next(csv.reader([payload], skipinitialspace=False), [])


def parse_duration(text: str) -> int:
    parts = [int(p) for p in text.split(":") if p.isdigit()]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs


def parse_progress(line: str) -> float | None:
    """``PRGV:current,total,max`` -> fraction 0..1 of the whole job."""
    if not line.startswith("PRGV:"):
        return None
    try:
        _cur, total, maximum = (int(x) for x in line[5:].split(","))
    except ValueError:
        return None
    return total / maximum if maximum else None


def parse_message(line: str) -> str | None:
    """``MSG:code,flags,count,"text",...`` -> text."""
    if not line.startswith("MSG:"):
        return None
    f = parse_fields(line[4:])
    return f[3] if len(f) > 3 else None


def parse_info(lines: list[str]) -> DiscInfo:
    info = DiscInfo()
    titles: dict[int, Title] = {}
    for line in lines:
        key, _, payload = line.partition(":")
        if key == "CINFO":
            f = parse_fields(payload)
            if len(f) >= 3 and f[0] == str(AP_NAME):
                info.name = f[2]
        elif key == "TINFO":
            f = parse_fields(payload)
            if len(f) < 4:
                continue
            try:
                tid, attr = int(f[0]), int(f[1])
            except ValueError:
                continue
            t = titles.setdefault(tid, Title(index=tid))
            value = f[3]
            if attr == AP_NAME:
                t.name = value
            elif attr == AP_DURATION:
                t.duration = parse_duration(value)
            elif attr == AP_DISK_SIZE_BYTES and value.isdigit():
                t.size_bytes = int(value)
            elif attr == AP_CHAPTER_COUNT and value.isdigit():
                t.chapters = int(value)
            elif attr == AP_OUTPUT_FILENAME:
                t.output_file = value
    info.titles = [titles[k] for k in sorted(titles)]
    return info


def parse_drives(lines: list[str]) -> list[DriveEntry]:
    drives = []
    for line in lines:
        if not line.startswith("DRV:"):
            continue
        f = parse_fields(line[4:])
        if len(f) < 7 or not f[4]:
            continue  # unused drive slot
        drives.append(DriveEntry(
            index=int(f[0]), has_disc=f[1] == "2", drive_name=f[4],
            disc_name=f[5], device=f[6],
        ))
    return drives


class MakeMKV:
    def __init__(self, exe: str, min_seconds: int = 1200):
        self.exe = exe
        self.min_seconds = max(0, int(min_seconds))

    def _base(self) -> list[str]:
        return [self.exe, "-r", "--cache=16", f"--minlength={self.min_seconds}"]

    def _collect(self, args: list[str], cancel: threading.Event | None,
                 on_line: Callable[[str], None] | None = None) -> tuple[int, list[str]]:
        lines: list[str] = []

        def handle(line: str) -> None:
            lines.append(line)
            msg = parse_message(line)
            if msg:
                log.debug("makemkv: %s", msg)
            if on_line:
                on_line(line)

        try:
            code = run_streaming(args, handle, cancel)
        except FileNotFoundError as exc:
            raise MakeMKVError(
                f"MakeMKV not found at '{self.exe}'. Install MakeMKV or fix the path in Settings."
            ) from exc
        return code, lines

    def source_for_drive(self, drive_letter: str,
                         cancel: threading.Event | None = None) -> str:
        """Map ``D:`` to MakeMKV's ``disc:N`` index (falls back to ``dev:D:``)."""
        letter = drive_letter.rstrip("\\/").upper()
        _code, lines = self._collect([self.exe, "-r", "--cache=1", "info", "disc:9999"], cancel)
        for d in parse_drives(lines):
            if d.device.rstrip("\\/").upper() == letter:
                return f"disc:{d.index}"
        return f"dev:{letter}"

    def info(self, source: str, cancel: threading.Event | None = None) -> DiscInfo:
        code, lines = self._collect([*self._base(), "info", source], cancel)
        info = parse_info(lines)
        if not info.titles:
            errors = [m for m in (parse_message(l) for l in lines) if m]
            detail = errors[-1] if errors else f"exit code {code}"
            raise MakeMKVError(f"MakeMKV found no titles longer than "
                               f"{self.min_seconds // 60} min ({detail})")
        return info

    def rip(self, source: str, title: int | str, out_dir: Path,
            on_progress: Callable[[float], None],
            on_status: Callable[[str], None],
            cancel: threading.Event | None = None) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        before = set(out_dir.glob("*.mkv"))
        messages: list[str] = []

        def handle(line: str) -> None:
            frac = parse_progress(line)
            if frac is not None:
                on_progress(frac)
                return
            if line.startswith("PRGC:") or line.startswith("PRGT:"):
                f = parse_fields(line[5:])
                if len(f) >= 3:
                    on_status(f[2])
            msg = parse_message(line)
            if msg:
                messages.append(msg)

        args = [*self._base(), "--progress=-same", "mkv", source, str(title), str(out_dir)]
        code, _ = self._collect(args, cancel, handle)
        produced = sorted(set(out_dir.glob("*.mkv")) - before)
        if code != 0 or not produced:
            detail = messages[-1] if messages else f"exit code {code}"
            raise MakeMKVError(f"Rip failed: {detail}")
        return produced
