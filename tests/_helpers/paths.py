"""Helper path yang tidak bergantung pada current working directory."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Kembalikan root repo berdasarkan lokasi file ini, bukan cwd."""
    return Path(__file__).resolve().parents[2]
