"""Settings tab."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
                               QWidget)

from .. import startup
from ..config import Config

HANDBRAKE_PRESETS = [
    "H.265 MKV 480p30", "H.264 MKV 480p30", "H.265 MKV 576p25", "H.264 MKV 576p25",
    "H.265 MKV 720p30", "H.265 MKV 1080p30", "H.264 MKV 1080p30", "H.265 MKV 2160p60 4K",
]


class PathEdit(QWidget):
    def __init__(self, folder: bool, file_filter: str = "Programs (*.exe);;All files (*)"):
        super().__init__()
        self.folder = folder
        self.file_filter = file_filter
        self.edit = QLineEdit()
        btn = QPushButton("Browse…")
        btn.clicked.connect(self._browse)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.edit, 1)
        lay.addWidget(btn)

    def _browse(self) -> None:
        start = self.edit.text() or str(Path.home())
        if self.folder:
            path = QFileDialog.getExistingDirectory(self, "Choose folder", start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Choose program", start, self.file_filter)
        if path:
            self.edit.setText(str(Path(path)))

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str) -> None:
        self.edit.setText(value)


class SettingsPage(QWidget):
    saved = Signal()

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg

        # Library
        self.movies_dir = PathEdit(folder=True)
        self.work_dir = PathEdit(folder=True)
        g_lib = QGroupBox("Library")
        f = QFormLayout(g_lib)
        f.addRow("Plex Movies folder:", self.movies_dir)
        f.addRow("Temporary rip folder:", self.work_dir)

        # Automation
        self.auto_rip = QCheckBox("Start importing as soon as a movie disc is inserted")
        self.eject = QCheckBox("Eject the disc when ripping is finished")
        self.confirm = QCheckBox("Ask me to confirm the movie name (rip starts immediately)")
        self.confirm_timeout = QSpinBox(minimum=10, maximum=3600, suffix=" s")
        self.startup = QCheckBox("Start Import2Flex when I sign in to Windows")
        self.minimized = QCheckBox("Start minimized to the system tray")
        self.notify = QCheckBox("Show notifications")
        g_auto = QGroupBox("Automation")
        f = QFormLayout(g_auto)
        for w in (self.auto_rip, self.eject, self.confirm):
            f.addRow(w)
        f.addRow("Use guessed name after:", self.confirm_timeout)
        for w in (self.startup, self.minimized, self.notify):
            f.addRow(w)

        # MakeMKV
        self.makemkv = PathEdit(folder=False)
        self.min_len = QSpinBox(minimum=0, maximum=240, suffix=" min")
        self.rip_mode = QComboBox()
        self.rip_mode.addItem("Main movie only (longest title)", "main")
        self.rip_mode.addItem("All titles (extras go in an 'Other' folder)", "all")
        g_mkv = QGroupBox("MakeMKV (ripping)")
        f = QFormLayout(g_mkv)
        f.addRow("makemkvcon64.exe:", self.makemkv)
        f.addRow("Skip titles shorter than:", self.min_len)
        f.addRow("What to rip:", self.rip_mode)

        # HandBrake
        self.transcode = QCheckBox("Re-encode with HandBrake to make files smaller (slower)")
        self.handbrake = PathEdit(folder=False)
        self.preset = QComboBox(editable=True)
        self.preset.addItems(HANDBRAKE_PRESETS)
        self.hb_args = QLineEdit()
        g_hb = QGroupBox("HandBrake (optional)")
        f = QFormLayout(g_hb)
        f.addRow(self.transcode)
        f.addRow("HandBrakeCLI.exe:", self.handbrake)
        f.addRow("Preset:", self.preset)
        f.addRow("Extra arguments:", self.hb_args)
        self.transcode.toggled.connect(lambda on: [w.setEnabled(on) for w in
                                                   (self.handbrake, self.preset, self.hb_args)])

        # ISO folder
        self.iso_enabled = QCheckBox("Watch a folder for .iso files and import them")
        self.iso_dir = PathEdit(folder=True)
        self.iso_delete = QCheckBox("Delete the .iso after it has been imported successfully")
        g_iso = QGroupBox("ISO watch folder")
        f = QFormLayout(g_iso)
        f.addRow(self.iso_enabled)
        f.addRow("Folder:", self.iso_dir)
        f.addRow(self.iso_delete)

        # Metadata / Plex
        self.tmdb = QLineEdit(echoMode=QLineEdit.Password,
                              placeholderText="optional - gets the exact title and year")
        self.plex_url = QLineEdit()
        self.plex_token = QLineEdit(echoMode=QLineEdit.Password,
                                    placeholderText="optional - makes Plex scan right away")
        self.plex_section = QLineEdit(placeholderText="blank = all libraries")
        g_meta = QGroupBox("Movie names && Plex")
        f = QFormLayout(g_meta)
        f.addRow("TMDb API key:", self.tmdb)
        f.addRow("Plex server URL:", self.plex_url)
        f.addRow("Plex token:", self.plex_token)
        f.addRow("Plex library section ID:", self.plex_section)

        save = QPushButton("Save settings")
        save.setDefault(True)
        save.clicked.connect(self.save)
        check = QPushButton("Check setup")
        check.clicked.connect(self.check_setup)
        revert = QPushButton("Revert")
        revert.clicked.connect(self.load)
        buttons = QHBoxLayout()
        buttons.addWidget(check)
        buttons.addStretch(1)
        buttons.addWidget(revert)
        buttons.addWidget(save)

        inner = QWidget()
        v = QVBoxLayout(inner)
        for g in (g_lib, g_auto, g_mkv, g_hb, g_iso, g_meta):
            v.addWidget(g)
        v.addStretch(1)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.addWidget(scroll, 1)
        outer.addLayout(buttons)
        self.load()

    def load(self) -> None:
        c = self.cfg
        self.movies_dir.setText(c.movies_dir)
        self.work_dir.setText(c.work_dir)
        self.auto_rip.setChecked(c.auto_rip)
        self.eject.setChecked(c.eject_when_done)
        self.confirm.setChecked(c.confirm_name)
        self.confirm_timeout.setValue(c.confirm_timeout_sec)
        self.startup.setChecked(startup.is_enabled() or c.start_with_windows)
        self.minimized.setChecked(c.start_minimized)
        self.notify.setChecked(c.notifications)
        self.makemkv.setText(c.makemkv_path)
        self.min_len.setValue(c.min_title_seconds // 60)
        self.rip_mode.setCurrentIndex(max(0, self.rip_mode.findData(c.rip_mode)))
        self.transcode.setChecked(c.transcode)
        self.transcode.toggled.emit(c.transcode)
        self.handbrake.setText(c.handbrake_path)
        self.preset.setCurrentText(c.handbrake_preset)
        self.hb_args.setText(c.handbrake_extra_args)
        self.iso_enabled.setChecked(c.iso_watch_enabled)
        self.iso_dir.setText(c.iso_watch_dir)
        self.iso_delete.setChecked(c.delete_iso_after)
        self.tmdb.setText(c.tmdb_api_key)
        self.plex_url.setText(c.plex_url)
        self.plex_token.setText(c.plex_token)
        self.plex_section.setText(c.plex_section_id)

    def save(self) -> None:
        c = self.cfg
        if not self.movies_dir.text():
            QMessageBox.warning(self, "Import2Flex", "Please choose your Plex Movies folder.")
            return
        c.movies_dir = self.movies_dir.text()
        c.work_dir = self.work_dir.text() or c.work_dir
        c.auto_rip = self.auto_rip.isChecked()
        c.eject_when_done = self.eject.isChecked()
        c.confirm_name = self.confirm.isChecked()
        c.confirm_timeout_sec = self.confirm_timeout.value()
        c.start_with_windows = self.startup.isChecked()
        c.start_minimized = self.minimized.isChecked()
        c.notifications = self.notify.isChecked()
        c.makemkv_path = self.makemkv.text()
        c.min_title_seconds = self.min_len.value() * 60
        c.rip_mode = self.rip_mode.currentData()
        c.transcode = self.transcode.isChecked()
        c.handbrake_path = self.handbrake.text()
        c.handbrake_preset = self.preset.currentText().strip()
        c.handbrake_extra_args = self.hb_args.text().strip()
        c.iso_watch_enabled = self.iso_enabled.isChecked()
        c.iso_watch_dir = self.iso_dir.text()
        c.delete_iso_after = self.iso_delete.isChecked()
        c.tmdb_api_key = self.tmdb.text().strip()
        c.plex_url = self.plex_url.text().strip() or "http://127.0.0.1:32400"
        c.plex_token = self.plex_token.text().strip()
        c.plex_section_id = self.plex_section.text().strip()
        try:
            c.save()
            startup.set_enabled(c.start_with_windows)
        except OSError as exc:
            QMessageBox.critical(self, "Import2Flex", f"Could not save settings:\n{exc}")
            return
        self.saved.emit()

    def check_setup(self) -> None:
        problems, ok = [], []

        def exe_ok(path: str) -> bool:
            return bool(path) and (Path(path).is_file() or shutil.which(path) is not None)

        (ok if exe_ok(self.makemkv.text()) else problems).append("MakeMKV (makemkvcon64.exe)")
        if self.transcode.isChecked():
            (ok if exe_ok(self.handbrake.text()) else problems).append("HandBrakeCLI.exe")
        for label, path in (("Movies folder", self.movies_dir.text()),
                            ("Temporary folder", self.work_dir.text())):
            p = Path(path)
            try:
                p.mkdir(parents=True, exist_ok=True)
                free = shutil.disk_usage(p).free / 1e9
                ok.append(f"{label} ({free:.0f} GB free)")
                if label == "Temporary folder" and free < 15:
                    problems.append(f"{label} has under 15 GB free - a DVD rip needs ~8 GB")
            except OSError as exc:
                problems.append(f"{label}: {exc}")
        text = "".join(f"✔ {o}\n" for o in ok) + "".join(f"✘ {p}\n" for p in problems)
        if problems:
            text += "\nMakeMKV: https://www.makemkv.com/download/\nHandBrake CLI: https://handbrake.fr/downloads2.php"
        (QMessageBox.warning if problems else QMessageBox.information)(self, "Setup check", text)
