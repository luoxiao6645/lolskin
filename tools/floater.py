"""模式一悬浮窗入口：python -m tools.floater"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysnskin_learn.ui.float_window import main

if __name__ == "__main__":
    raise SystemExit(main())
