"""Shim agar ``python -m laporan`` berjalan dari akar repositori.

Implementasi sebenarnya berada di ``src/laporan``. Berkas ini hanya
menambahkan ``src/`` ke ``sys.path`` lalu meneruskan ke CLI. Instalasi
editable (``pip install -e .``) tidak diperlukan untuk quickstart.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
_SRC_TEXT = str(_SRC)
# Instalasi editable menambahkan src/ ke akhir sys.path. Pindahkan ke depan
# agar shim ini tidak menimpa paket ``laporan`` dengan berkas laporan.py.
if _SRC_TEXT in sys.path:
    sys.path.remove(_SRC_TEXT)
sys.path.insert(0, _SRC_TEXT)

from laporan.cli import main  # noqa: E402  (path harus disiapkan lebih dulu)

if __name__ == "__main__":
    raise SystemExit(main())
