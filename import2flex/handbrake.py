"""Optional re-encode with HandBrakeCLI to shrink the raw MakeMKV output."""
from __future__ import annotations

import re
import shlex
import threading
from pathlib import Path
from typing import Callable

from .process import run_streaming

_PROGRESS = re.compile(r"Encoding: task (\d+) of (\d+), ([\d.]+) %")


class HandBrakeError(RuntimeError):
    pass


def parse_progress(line: str) -> float | None:
    m = _PROGRESS.search(line)
    if not m:
        return None
    task, tasks, pct = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return ((task - 1) + pct / 100.0) / max(tasks, 1)


def transcode(exe: str, src: Path, dst: Path, preset: str, extra_args: str,
              on_progress: Callable[[float], None],
              cancel: threading.Event | None = None) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    args = [exe, "-i", str(src), "-o", str(dst), "--format", "av_mkv"]
    if preset.strip():
        args += ["--preset", preset.strip()]
    args += shlex.split(extra_args or "", posix=True)
    tail: list[str] = []

    def handle(line: str) -> None:
        frac = parse_progress(line)
        if frac is not None:
            on_progress(frac)
        else:
            tail.append(line)
            del tail[:-20]

    try:
        code = run_streaming(args, handle, cancel)
    except FileNotFoundError as exc:
        raise HandBrakeError(f"HandBrakeCLI not found at '{exe}'. Fix the path in Settings "
                             f"or turn off re-encoding.") from exc
    if code != 0 or not dst.exists() or dst.stat().st_size == 0:
        detail = tail[-1] if tail else f"exit code {code}"
        raise HandBrakeError(f"HandBrake failed: {detail}")
    return dst
