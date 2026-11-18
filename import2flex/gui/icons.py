"""App/tray icons drawn in code (no image files to ship)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient


def _disc(size: int, busy: bool = False, paused: bool = False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    rect = QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92)
    grad = QRadialGradient(QPointF(s * 0.35, s * 0.35), s * 0.7)
    grad.setColorAt(0.0, QColor("#f2f6ff"))
    grad.setColorAt(0.45, QColor("#9fb6ff"))
    grad.setColorAt(0.75, QColor("#c49bff"))
    grad.setColorAt(1.0, QColor("#6b7bd6"))
    p.setPen(QPen(QColor("#2b2f45"), max(1.0, s / 32)))
    p.setBrush(grad)
    p.drawEllipse(rect)
    # hub + hole
    p.setBrush(QColor("#e8ebf5"))
    p.drawEllipse(QPointF(s / 2, s / 2), s * 0.17, s * 0.17)
    p.setBrush(QColor("#2b2f45"))
    p.drawEllipse(QPointF(s / 2, s / 2), s * 0.06, s * 0.06)
    # status badge
    if busy or paused:
        color = QColor("#e5a00d") if paused else QColor("#2fbf71")
        r = s * 0.2
        p.setPen(QPen(QColor("white"), max(1.0, s / 24)))
        p.setBrush(color)
        p.drawEllipse(QPointF(s - r - 1, s - r - 1), r, r)
    p.end()
    return pm


def app_icon(busy: bool = False, paused: bool = False) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_disc(size, busy, paused))
    return icon
