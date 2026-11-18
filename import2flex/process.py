"""Run a console tool without a console window, streaming its output."""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from typing import Callable, Iterable

log = logging.getLogger(__name__)


class Cancelled(Exception):
    """Raised when the user cancels the running job."""


def _creation_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    return 0


def run_streaming(args: Iterable[str], on_line: Callable[[str], None],
                  cancel: threading.Event | None = None) -> int:
    """Run ``args`` and call ``on_line`` for each output line.

    Lines are split on both ``\\n`` and ``\\r`` because HandBrake reports
    progress with carriage returns.
    """
    args = [str(a) for a in args]
    log.debug("Running: %s", subprocess.list2cmdline(args))
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=_creation_flags(),
        bufsize=0,
    )

    def watchdog() -> None:
        if cancel is None:
            return
        while proc.poll() is None:
            if cancel.wait(0.5):
                log.info("Cancelling %s", args[0])
                proc.kill()
                return

    threading.Thread(target=watchdog, daemon=True).start()

    buf = b""
    assert proc.stdout is not None
    while True:
        chunk = proc.stdout.read(4096)
        if not chunk:
            break
        buf += chunk
        while True:
            idx = min((i for i in (buf.find(b"\n"), buf.find(b"\r")) if i >= 0), default=-1)
            if idx < 0:
                break
            line, buf = buf[:idx], buf[idx + 1:]
            if line.strip():
                on_line(line.decode("utf-8", errors="replace").strip())
    if buf.strip():
        on_line(buf.decode("utf-8", errors="replace").strip())
    code = proc.wait()
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    return code
