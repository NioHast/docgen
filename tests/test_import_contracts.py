"""Tes kontrak import antar modul ``docgen``.

Kontrak didefinisikan di ``[tool.importlinter]`` pada ``pyproject.toml`` dan
diperiksa lewat entry point ``lint-imports`` dari dependency dev.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_import_contracts_respected() -> None:
    """Seluruh kontrak import di pyproject.toml harus KEPT."""
    executable = shutil.which("lint-imports")
    assert executable is not None, (
        "Entry point 'lint-imports' tidak ditemukan. Jalankan `uv sync --extra dev` lebih dulu."
    )

    result = subprocess.run(
        [executable, "--config", "pyproject.toml", "--no-cache"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, (
        f"lint-imports gagal dengan exit code {result.returncode}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
