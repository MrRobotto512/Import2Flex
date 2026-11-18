"""'Start with Windows' via the per-user Run registry key."""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from . import APP_NAME

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    """Command line that starts this app minimized to the tray."""
    if getattr(sys, "frozen", False):  # PyInstaller build
        args = [sys.executable, "--minimized"]
    else:
        exe = Path(sys.executable)
        pythonw = exe.with_name("pythonw.exe")
        launcher = Path(__file__).resolve().parent.parent / "Import2Flex.pyw"
        args = [str(pythonw if pythonw.exists() else exe), str(launcher), "--minimized"]
    return subprocess.list2cmdline(args)


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
            log.info("Enabled start with Windows")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
                log.info("Disabled start with Windows")
            except FileNotFoundError:
                pass

