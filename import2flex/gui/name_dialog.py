"""Small non-blocking popup to confirm/edit the movie name, with a countdown."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QLineEdit,
                               QVBoxLayout)


class NameDialog(QDialog):
    def __init__(self, source: str, guess: str, timeout: int,
                 on_done: Callable[[str | None], None], parent=None, doubt: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Import2Flex - Name this movie")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._on_done = on_done
        self._answered = False
        # timeout 0: no countdown, the guess is in doubt and needs an answer
        self._remaining = max(5, timeout) if timeout > 0 else 0

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Ripping <b>{source}</b>. What should it be called in Plex?"))
        if doubt:
            warn = QLabel(f"<b>Not sure this is the right movie:</b> {doubt}.")
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #c0392b")
            layout.addWidget(warn)
        hint = QLabel("Use the form <i>Movie Title (Year)</i> for best Plex matching.")
        hint.setStyleSheet("color: gray")
        layout.addWidget(hint)
        self.edit = QLineEdit(guess)
        self.edit.selectAll()
        layout.addWidget(self.edit)
        self.countdown = QLabel()
        layout.addWidget(self.countdown)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Cancel).setText("Use guess")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(460, self.sizeHint().height())

        self._timer = QTimer(self, interval=1000, timeout=self._tick)
        if self._remaining:
            self._timer.start()
            self.edit.textEdited.connect(self._stop_countdown)
            self._tick(first=True)
        else:
            self.countdown.setText("The rip goes on meanwhile; the movie is filed once you answer.")

    def _stop_countdown(self) -> None:
        self._timer.stop()
        self.countdown.setText("Countdown stopped - press OK when ready.")

    def _tick(self, first: bool = False) -> None:
        if not first:
            self._remaining -= 1
        if self._remaining <= 0:
            self.reject()
            return
        self.countdown.setText(f"Continuing with this name in {self._remaining}s…")

    def _finish(self, value: str | None) -> None:
        if not self._answered:
            self._answered = True
            self._timer.stop()
            self._on_done(value)

    def accept(self) -> None:
        self._finish(self.edit.text())
        super().accept()

    def reject(self) -> None:
        self._finish(None)
        super().reject()

    def closeEvent(self, event) -> None:
        self._finish(None)
        super().closeEvent(event)
