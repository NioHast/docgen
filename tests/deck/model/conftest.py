"""Fixture bersama untuk test model deck."""

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "deck"


@pytest.fixture
def fixture_dir() -> Path:
    """Kembalikan direktori fixture YAML deck."""
    return FIXTURE_DIR
