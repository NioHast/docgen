"""Konfigurasi pytest: buat modul di tools/dev/ dapat diimpor."""

from __future__ import annotations

import sys
from pathlib import Path

DEV_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools" / "dev"
if str(DEV_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(DEV_TOOLS_DIR))
