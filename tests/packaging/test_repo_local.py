"""Tes packaging repo-local untuk entry point ``docgen``.

Tes ini tidak mem-build DOCX/PDF. Fokusnya: perintah ``docgen`` tersedia
lewat ``uv run --project <repo>`` dari luar repo, ``check`` menerima dokumen
minimal, dan kedua perintah tidak mengubah ``git status`` repo.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests._helpers.paths import repo_root

pytestmark = pytest.mark.packaging

REPO = repo_root()

_MINIMAL_DOCUMENT = """---
title: "Tes Packaging"
author: "Nama Mahasiswa"
nim: "30000000000000"
structure: assignment
format: undip-msi
bibliography: references.bib
---

# Pendahuluan

Teks.

# Pembahasan

Teks.

# Penutup

Teks.
"""

_BIBLIOGRAPHY = """@book{contoh2026,
  title = {Contoh},
}
"""


def _uv() -> str:
    executable = shutil.which("uv")
    if executable is None:
        pytest.fail(
            "uv tidak ditemukan di PATH; tes packaging repo-local membutuhkan uv"
        )
    return executable


def _run_docgen(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Jalankan ``docgen`` lewat project uv dari ``cwd`` di luar repo."""

    return subprocess.run(
        [_uv(), "run", "--project", str(REPO), "docgen", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=180,
    )


def _write_minimal_document(root: Path) -> Path:
    (root / "references.bib").write_text(
        _BIBLIOGRAPHY,
        encoding="utf-8",
        newline="\n",
    )
    document = root / "document.md"
    document.write_text(
        _MINIMAL_DOCUMENT,
        encoding="utf-8",
        newline="\n",
    )
    return document


def _git_status() -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.splitlines()


def _assert_outside_repo(cwd: Path) -> None:
    assert not cwd.resolve().is_relative_to(REPO), (
        f"cwd tes harus di luar repo, tetapi berada di {cwd}"
    )


@contextmanager
def _git_status_unchanged() -> Iterator[None]:
    """Pastikan working tree repo tidak berubah selama blok berjalan.

    Status awal memuat artefak untracked yang sudah ada; perbandingan seluruh
    baris otomatis mengabaikannya selama tidak ada baris baru atau hilang.
    """

    before = _git_status()
    yield
    after = _git_status()
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    assert after == before, (
        "git status repo berubah\n"
        f"baris baru: {added}\n"
        f"baris hilang: {removed}"
    )


def test_version_dari_luar_repo(tmp_path: Path) -> None:
    _assert_outside_repo(tmp_path)

    with _git_status_unchanged():
        result = _run_docgen("--version", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "docgen 0.1.0"


def test_check_dokumen_minimal_dari_luar_repo(tmp_path: Path) -> None:
    _assert_outside_repo(tmp_path)
    document = _write_minimal_document(tmp_path)

    with _git_status_unchanged():
        result = _run_docgen("check", document.name, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "[OK] Tes Packaging" in result.stdout


def test_version_dan_check_tidak_mengubah_git_status(tmp_path: Path) -> None:
    _assert_outside_repo(tmp_path)
    _write_minimal_document(tmp_path)

    with _git_status_unchanged():
        version = _run_docgen("--version", cwd=tmp_path)
        check = _run_docgen("check", "document.md", cwd=tmp_path)

    assert version.returncode == 0, version.stderr
    assert check.returncode == 0, check.stderr
