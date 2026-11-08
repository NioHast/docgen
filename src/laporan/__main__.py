"""Titik masuk ``python -m laporan`` saat ``src/`` ada di ``sys.path``."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
