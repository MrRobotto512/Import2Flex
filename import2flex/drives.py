"""Optical drive detection and eject (Windows), with harmless stubs elsewhere."""
from __future__ import annotations

import logging
import os
import string
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
DRIVE_CDROM = 5


@dataclass(frozen=True)
class Disc:
    drive: str        # "D:"
    label: str        # volume label, e.g. "THE_MATRIX"
    serial: int       # volume serial - identifies this particular disc
    kind: str         # "dvd", "bluray" or "other"

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.drive, self.label, self.serial)

    @property
    def is_video(self) -> bool:
        return self.kind in ("dvd", "bluray")


if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.GetLogicalDrives.restype = wintypes.DWORD
    _k32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    _k32.GetDriveTypeW.restype = wintypes.UINT
    _k32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR, wintypes.DWORD,
    ]
    _k32.GetVolumeInformationW.restype = wintypes.BOOL
    _k32.SetErrorMode.argtypes = [wintypes.UINT]
    _k32.SetErrorMode.restype = wintypes.UINT
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                     wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                     wintypes.LPVOID]
    _k32.DeviceIoControl.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]

    # Don't show "There is no disk in the drive" dialogs while probing.
    SEM_FAILCRITICALERRORS = 0x0001
    SEM_NOOPENFILEERRORBOX = 0x8000
    _k32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOOPENFILEERRORBOX)


def optical_drives() -> list[str]:
    """Return drive letters of all optical drives, e.g. ``["D:", "E:"]``."""
    if not IS_WINDOWS:
        return []
    mask = _k32.GetLogicalDrives()
    found = []
    for i, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << i) and _k32.GetDriveTypeW(f"{letter}:\\") == DRIVE_CDROM:
            found.append(f"{letter}:")
    return found


def disc_in(drive: str) -> Disc | None:
    """Return info about the disc in ``drive`` or ``None`` if empty/not ready."""
    if not IS_WINDOWS:
        return None
    root = f"{drive}\\"
    label = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(261)
    serial = wintypes.DWORD()
    max_len = wintypes.DWORD()
    flags = wintypes.DWORD()
    ok = _k32.GetVolumeInformationW(root, label, 261, ctypes.byref(serial),
                                    ctypes.byref(max_len), ctypes.byref(flags), fs, 261)
    if not ok:
        return None
    if os.path.isdir(os.path.join(root, "BDMV")):
        kind = "bluray"
    elif os.path.isdir(os.path.join(root, "VIDEO_TS")):
        kind = "dvd"
    else:
        kind = "other"
    return Disc(drive=drive, label=label.value, serial=serial.value, kind=kind)


def eject(drive: str) -> bool:
    """Open the tray of ``drive``. Returns True on success."""
    if not IS_WINDOWS:
        return False
    GENERIC_READ = 0x80000000
    FILE_SHARE_READ_WRITE = 0x3
    OPEN_EXISTING = 3
    IOCTL_STORAGE_EJECT_MEDIA = 0x2D4808
    INVALID = wintypes.HANDLE(-1).value
    handle = _k32.CreateFileW(f"\\\\.\\{drive}", GENERIC_READ, FILE_SHARE_READ_WRITE,
                              None, OPEN_EXISTING, 0, None)
    if handle and handle != INVALID:
        try:
            returned = wintypes.DWORD()
            if _k32.DeviceIoControl(handle, IOCTL_STORAGE_EJECT_MEDIA, None, 0, None, 0,
                                    ctypes.byref(returned), None):
                return True
        finally:
            _k32.CloseHandle(handle)
    # Fallback: the multimedia API.
    try:
        winmm = ctypes.WinDLL("winmm")
        alias = "i2f_drive"
        winmm.mciSendStringW(f"open {drive} type cdaudio alias {alias}", None, 0, None)
        rc = winmm.mciSendStringW(f"set {alias} door open", None, 0, None)
        winmm.mciSendStringW(f"close {alias}", None, 0, None)
        return rc == 0
    except OSError as exc:
        log.warning("Eject %s failed: %s", drive, exc)
        return False
