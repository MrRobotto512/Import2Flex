"""Double-click launcher (runs without a console window on Windows)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import2flex.app import main  # noqa: E402

raise SystemExit(main())
