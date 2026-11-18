"""Application entry point: tray icon, main window, engine wiring."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
import threading

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME, __version__
from .config import Config, app_data_dir
from .drives import Disc
from .pipeline import Engine, Job
from .gui.icons import app_icon
from .gui.main_window import MainWindow, open_path
from .gui.name_dialog import NameDialog

log = logging.getLogger("import2flex")


class _NameRequest:
    def __init__(self, job: Job, guess: str, timeout: int):
        self.job, self.guess, self.timeout = job, guess, timeout
        self.done = threading.Event()
        self.answer: str | None = None


class Bridge(QObject):
    """Receives engine callbacks on worker threads and re-emits them on the GUI thread."""

    jobChanged = Signal(object)
    notified = Signal(str, str, bool)
    nameRequested = Signal(object)
    drivesChanged = Signal(object)
    logLine = Signal(str)

    # EngineEvents implementation (called from worker threads)
    def job_changed(self, job: Job) -> None:
        self.jobChanged.emit(job)

    def notify(self, title: str, message: str, error: bool = False) -> None:
        self.notified.emit(title, message, error)

    def ask_name(self, job: Job, guess: str, timeout: int) -> str | None:
        req = _NameRequest(job, guess, timeout)
        self.nameRequested.emit(req)
        req.done.wait()
        return req.answer

    def drives_changed(self, state: dict[str, Disc | None]) -> None:
        self.drivesChanged.emit(state)


class QtLogHandler(logging.Handler):
    def __init__(self, bridge: Bridge):
        super().__init__(logging.INFO)
        self.bridge = bridge
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.bridge.logLine.emit(self.format(record))
        except RuntimeError:
            pass  # GUI already gone


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fh = logging.handlers.RotatingFileHandler(app_data_dir() / "import2flex.log",
                                              maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(fh)
    if sys.stderr is not None:  # pythonw has no console
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        root.addHandler(sh)


class TrayApp(QObject):
    def __init__(self, app: QApplication, cfg: Config, minimized: bool):
        super().__init__()
        self.app = app
        self.cfg = cfg
        self.bridge = Bridge()
        self.engine = Engine(cfg, self.bridge)
        self.window = MainWindow(self.engine)
        self._busy_icon = self._paused_icon = False

        logging.getLogger().addHandler(QtLogHandler(self.bridge))
        self.bridge.logLine.connect(self.window.append_log)
        self.bridge.jobChanged.connect(self._on_job)
        self.bridge.notified.connect(self._on_notify)
        self.bridge.nameRequested.connect(self._on_name_request)
        self.bridge.drivesChanged.connect(self._on_drives)
        self.window.settings.saved.connect(self._on_settings_saved)
        self.window.pause_btn.toggled.connect(self._sync_pause)

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"{APP_NAME} - idle")
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self.window.show_and_raise)
        self.tray.setContextMenu(self._build_menu())
        self.tray.show()
        self.window.on_hidden_first_time = lambda: self._on_notify(
            APP_NAME, "Still running in the tray. Right-click the icon to quit.", False)

        self.engine.start()
        if not minimized:
            self.window.show()
        if not cfg.movies_dir or not Config.path().exists():
            # First run: point the user at Settings.
            self.window.show_and_raise()
            self.window.tabs.setCurrentWidget(self.window.settings)
            QTimer.singleShot(300, lambda: QMessageBox.information(
                self.window, f"Welcome to {APP_NAME}",
                "Choose your Plex Movies folder and check that MakeMKV is found, "
                "then click Save settings.\n\nAfter that, just insert a DVD."))

    # ------------------------------------------------------------------ tray
    def _build_menu(self) -> QMenu:
        menu = QMenu()
        open_act = QAction("Open Import2Flex", menu)
        open_act.triggered.connect(self.window.show_and_raise)
        menu.addAction(open_act)
        menu.setDefaultAction(open_act)
        menu.addSeparator()
        self.pause_act = QAction("Pause auto-import", menu, checkable=True)
        self.pause_act.toggled.connect(self.window.set_paused)
        menu.addAction(self.pause_act)
        self.rip_menu = menu.addMenu("Import disc now")
        self.eject_menu = menu.addMenu("Eject")
        menu.addAction("Open Movies folder", lambda: open_path(self.cfg.movies_dir))
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self._on_drives({})
        return menu

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.window.isVisible() and not self.window.isMinimized():
                self.window.hide()
            else:
                self.window.show_and_raise()

    def _refresh_icon(self) -> None:
        busy = self.engine.busy()
        paused = self.engine.paused
        if (busy, paused) != (self._busy_icon, self._paused_icon):
            self._busy_icon, self._paused_icon = busy, paused
            self.tray.setIcon(app_icon(busy=busy, paused=paused))

    # ------------------------------------------------------------------ slots
    @Slot(object)
    def _on_job(self, job: Job) -> None:
        self.window.update_job(job)
        self._refresh_icon()
        active = [j for j in list(self.engine.jobs) if not j.finished]
        if active:
            j = active[0]
            tip = f"{APP_NAME} - {j.status} {j.name or j.label} {j.progress * 100:.0f}%"
            if len(active) > 1:
                tip += f" (+{len(active) - 1} queued)"
        else:
            tip = f"{APP_NAME} - {'paused' if self.engine.paused else 'idle'}"
        self.tray.setToolTip(tip[:120])

    @Slot(str, str, bool)
    def _on_notify(self, title: str, message: str, error: bool) -> None:
        if error:
            log.error("%s: %s", title, message)
        if self.cfg.notifications or error:
            icon = QSystemTrayIcon.Critical if error else QSystemTrayIcon.Information
            self.tray.showMessage(title, message, icon, 8000)

    @Slot(object)
    def _on_name_request(self, req: _NameRequest) -> None:
        def done(answer: str | None) -> None:
            req.answer = answer
            req.done.set()

        dlg = NameDialog(req.job.source, req.guess, req.timeout, done)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    @Slot(object)
    def _on_drives(self, state: dict) -> None:
        self.window.update_drives(state)
        for menu, action in ((self.rip_menu, self.engine.rip_drive_now),
                             (self.eject_menu, self.engine.eject)):
            menu.clear()
            for drive, disc in sorted(state.items()):
                label = f"{drive} {disc.label}" if disc else f"{drive} (empty)"
                act = menu.addAction(label, lambda d=drive, a=action: a(d))
                if action is self.engine.rip_drive_now:
                    act.setEnabled(disc is not None)
            menu.setEnabled(bool(state))

    def _sync_pause(self, paused: bool) -> None:
        if self.pause_act.isChecked() != paused:
            self.pause_act.setChecked(paused)
        self._refresh_icon()

    def _on_settings_saved(self) -> None:
        log.info("Settings saved")
        self.window.statusBar().showMessage("Settings saved.", 4000)

    def quit(self) -> None:
        if self.engine.busy():
            answer = QMessageBox.question(
                self.window, APP_NAME,
                "An import is still running. Quit anyway? The current import will be cancelled.")
            if answer != QMessageBox.Yes:
                return
        self.engine.stop()
        self.tray.hide()
        self.window.quitting = True
        self.window.close()
        self.app.quit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME)
    parser.add_argument("--minimized", action="store_true", help="start hidden in the tray")
    args, _ = parser.parse_known_args(argv)

    if sys.platform == "win32":
        import ctypes
        # Give the app its own taskbar identity/icon instead of python.exe's.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.{__version__}")

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    lock = QLockFile(str(app_data_dir() / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME,
                                f"{APP_NAME} is already running - look for its icon in the system tray.")
        return 0

    setup_logging()
    log.info("%s %s starting", APP_NAME, __version__)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("No system tray available; the window will stay open")

    cfg = Config.load()
    minimized = (args.minimized or cfg.start_minimized) and Config.path().exists()
    tray_app = TrayApp(app, cfg, minimized)  # noqa: F841 - keep a reference
    code = app.exec()
    lock.unlock()
    return code
