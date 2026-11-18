"""Write build/icon.ico for the PyInstaller .exe (uses the same drawing as the tray icon)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from import2flex.gui.icons import _disc  # noqa: E402

app = QGuiApplication([])
out = Path(__file__).resolve().parent.parent / "build" / "icon.ico"
out.parent.mkdir(exist_ok=True)
if not _disc(256).save(str(out), "ICO"):
    raise SystemExit("could not write icon")
print(f"wrote {out}")
