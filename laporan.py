"""Shim agar ``python -m laporan`` berjalan dari akar repositori.

Implementasi sebenarnya berada di ``src/laporan``. Berkas ini hanya
menambahkan ``src/`` ke ``sys.path`` lalu meneruskan ke CLI. Instalasi
editable (``pip install -e .``) tidak diperlukan untuk quickstart.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from laporan.cli import main  # noqa: E402  (path harus disiapkan lebih dulu)

if __name__ == "__main__":
    raise SystemExit(main())
