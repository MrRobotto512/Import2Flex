"""Main window: queue/status tab, settings tab, log tab."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..pipeline import Engine, Job, Status
from .icons import app_icon
from .settings_page import SettingsPage

COLS = ["#", "Source", "Movie", "Status", "Progress", "Details"]
STATUS_COLORS = {Status.DONE: "#2fbf71", Status.FAILED: "#e5484d", Status.CANCELLED: "#8b8d98"}


def open_path(path: str | Path) -> None:
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class MainWindow(QMainWindow):
    def __init__(self, engine: Engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.cfg = engine.cfg
        self._rows: dict[int, int] = {}
        self._jobs: dict[int, Job] = {}
        self.quitting = False
        self.on_hidden_first_time = None

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setWindowIcon(app_icon())
        self.resize(980, 600)

        tabs = QTabWidget()
        tabs.addTab(self._build_queue_tab(), "Imports")
        self.settings = SettingsPage(self.cfg)
        tabs.addTab(self.settings, "Settings")
        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setStyleSheet("font-family: Consolas, monospace;")
        tabs.addTab(self.log_view, "Log")
        self.setCentralWidget(tabs)
        self.tabs = tabs
        self.statusBar().showMessage("Insert a DVD or Blu-ray to start.")

    # ------------------------------------------------------------------ layout
    def _build_queue_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        top = QHBoxLayout()
        top.addWidget(QLabel("Drive:"))
        self.drive_combo = QComboBox(minimumWidth=260)
        top.addWidget(self.drive_combo)
        self.rip_btn = QPushButton("Import disc now")
        self.rip_btn.clicked.connect(self._rip_now)
        top.addWidget(self.rip_btn)
        eject_btn = QPushButton("Eject")
        eject_btn.clicked.connect(self._eject)
        top.addWidget(eject_btn)
        top.addStretch(1)
        iso_btn = QPushButton("Import ISO file…")
        iso_btn.clicked.connect(self._add_iso)
        top.addWidget(iso_btn)
        self.pause_btn = QPushButton("Pause auto-import", checkable=True)
        self.pause_btn.toggled.connect(self.set_paused)
        top.addWidget(self.pause_btn)
        v.addLayout(top)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(5, QHeaderView.Stretch)
        h.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 170)
        self.table.cellDoubleClicked.connect(self._open_row)
        v.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        cancel = QPushButton("Cancel selected")
        cancel.clicked.connect(self._cancel_selected)
        clear = QPushButton("Clear finished")
        clear.clicked.connect(self._clear_finished)
        movies = QPushButton("Open Movies folder")
        movies.clicked.connect(lambda: open_path(self.cfg.movies_dir))
        bottom.addWidget(cancel)
        bottom.addWidget(clear)
        bottom.addStretch(1)
        bottom.addWidget(movies)
        v.addLayout(bottom)
        return w

    # ------------------------------------------------------------------ engine events
    def update_job(self, job: Job) -> None:
        self._jobs[job.id] = job
        row = self._rows.get(job.id)
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._rows[job.id] = row
            for col in range(len(COLS)):
                if col != 4:
                    self.table.setItem(row, col, QTableWidgetItem())
            bar = QProgressBar(minimum=0, maximum=1000, textVisible=True)
            bar.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(row, 4, bar)
        self.table.item(row, 0).setText(str(job.id))
        self.table.item(row, 1).setText(job.source)
        self.table.item(row, 2).setText(job.name)
        status_item = self.table.item(row, 3)
        status_item.setText(job.status)
        color = STATUS_COLORS.get(job.status)
        status_item.setData(Qt.ForegroundRole, QColor(color) if color else None)
        self.table.item(row, 5).setText(job.error or job.detail)
        self.table.item(row, 5).setToolTip(job.error or job.detail)
        bar: QProgressBar = self.table.cellWidget(row, 4)
        bar.setValue(int(job.progress * 1000))
        bar.setFormat(f"{job.progress * 100:.1f}%" if not job.finished else job.status)
        self._update_status_bar()

    def update_drives(self, state: dict) -> None:
        current = self.drive_combo.currentData()
        self.drive_combo.clear()
        for drive, disc in sorted(state.items()):
            if disc is None:
                text = f"{drive}  (empty)"
            else:
                kind = {"dvd": "DVD", "bluray": "Blu-ray"}.get(disc.kind, "not a movie disc")
                text = f"{drive}  {disc.label or '(no label)'}  [{kind}]"
            self.drive_combo.addItem(text, drive)
        if not state:
            self.drive_combo.addItem("No optical drive found", None)
        idx = self.drive_combo.findData(current)
        if idx >= 0:
            self.drive_combo.setCurrentIndex(idx)

    def append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def _update_status_bar(self) -> None:
        active = [j for j in self._jobs.values() if not j.finished]
        if self.engine.paused:
            msg = "Auto-import paused."
        elif active:
            j = active[0]
            msg = f"{j.status}: {j.name or j.label} ({j.progress * 100:.0f}%)"
            if len(active) > 1:
                msg += f"  +{len(active) - 1} more"
        else:
            msg = "Idle - insert a DVD or Blu-ray to start."
        self.statusBar().showMessage(msg)

    # ------------------------------------------------------------------ actions
    def set_paused(self, paused: bool) -> None:
        self.engine.set_paused(paused)
        if self.pause_btn.isChecked() != paused:
            self.pause_btn.setChecked(paused)
        self.pause_btn.setText("Resume auto-import" if paused else "Pause auto-import")
        self._update_status_bar()

    def selected_drive(self) -> str | None:
        return self.drive_combo.currentData()

    def _rip_now(self) -> None:
        drive = self.selected_drive()
        if drive:
            self.engine.rip_drive_now(drive)

    def _eject(self) -> None:
        drive = self.selected_drive()
        if drive:
            self.engine.eject(drive)

    def _add_iso(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Choose ISO files", str(Path.home()),
                                                "Disc images (*.iso);;All files (*)")
        for f in files:
            self.engine.queue_iso(Path(f))

    def _selected_job(self) -> Job | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        job_id = int(self.table.item(rows[0].row(), 0).text())
        return self._jobs.get(job_id)

    def _cancel_selected(self) -> None:
        job = self._selected_job()
        if job:
            self.engine.cancel_job(job.id)

    def _clear_finished(self) -> None:
        self.engine.clear_finished()
        for job_id, job in list(self._jobs.items()):
            if job.finished:
                del self._jobs[job_id]
        self.table.setRowCount(0)
        self._rows.clear()
        for job in sorted(self._jobs.values(), key=lambda j: j.id):
            self.update_job(job)

    def _open_row(self, row: int, _col: int) -> None:
        job_id = int(self.table.item(row, 0).text())
        job = self._jobs.get(job_id)
        if job and job.dest and job.dest.exists():
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", str(job.dest)])
            else:
                open_path(job.dest.parent)

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        if self.quitting:
            event.accept()
            return
        # Closing the window just hides it - the app keeps running in the tray.
        event.ignore()
        self.hide()
        if self.on_hidden_first_time:
            self.on_hidden_first_time()
            self.on_hidden_first_time = None

