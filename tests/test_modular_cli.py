"""Tes fondasi modular CLI tanpa menjalankan build penuh."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laporan import manifest as manifest_mod  # noqa: E402


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Jalankan ``python -m laporan`` dari akar repo lewat shim ``laporan.py``."""

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env.pop("LAPORAN_ROOT", None)
    return subprocess.run(
        [sys.executable, "-m", "laporan", *args],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def create_assignment(tmp_path: Path) -> Path:
    out = tmp_path / "tugas"
    completed = run_cli("new", "assignment", "--format", "undip-msi", "--out", str(out))
    assert completed.returncode == 0, completed.stderr
    return out


def test_list_menampilkan_tiga_struktur() -> None:
    completed = run_cli("list")

    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    assert "Struktur (3)" in output
    for name in ("thesis", "proposal", "assignment"):
        assert name in output
    assert "undip-msi" in output
    assert "BAB_ROMAN" not in output  # list hanya menampilkan ringkasan


def test_new_assignment_menghasilkan_berkas_lengkap(tmp_path: Path) -> None:
    out = create_assignment(tmp_path)

    required = [
        "manifest.yml",
        "metadata.yml",
        "cover.md",
        "references.bib",
        "chapters/01-pendahuluan.md",
        "chapters/02-pembahasan.md",
        "chapters/03-penutup.md",
    ]
    for relative in required:
        assert (out / relative).is_file(), relative
    assert (out / "gambar").is_dir()

    manifest = manifest_mod.load_yaml(out / "manifest.yml")
    assert manifest["manifest"] == 1
    assert manifest["structure"] == "assignment"
    assert manifest["format"] == "undip-msi"
    assert manifest["metadata"] == "metadata.yml"

    metadata = manifest_mod.load_yaml(out / "metadata.yml")
    assert metadata["preset"] == "undip-msi-proposal"
    assert metadata["lang"] == "id-ID"
    assert metadata["toc"] is False

    cover = (out / "cover.md").read_text(encoding="utf-8")
    assert "DAFTAR ISI" not in cover
    assert "outline(" not in cover

    project = manifest_mod.load_project(out)
    assert project.structure.name == "assignment"
    assert project.format.name == "undip-msi"
    assert len(project.chapter_paths) == 3
    assert all(path.is_file() for path in project.chapter_paths)


def test_new_thesis_menghasilkan_toc_true(tmp_path: Path) -> None:
    out = tmp_path / "tesis"
    completed = run_cli("new", "thesis", "--format", "undip-msi", "--out", str(out))
    assert completed.returncode == 0, completed.stderr

    metadata = manifest_mod.load_yaml(out / "metadata.yml")
    assert metadata["toc"] is True

    cover = (out / "cover.md").read_text(encoding="utf-8")
    assert "daftar-isi()" in cover


def test_check_gagal_jika_bab_hilang(tmp_path: Path) -> None:
    out = create_assignment(tmp_path)
    (out / "chapters" / "02-pembahasan.md").unlink()

    completed = run_cli("check", str(out))

    assert completed.returncode != 0
    combined = completed.stdout + completed.stderr
    assert "Bab tidak ditemukan" in combined
    assert "02-pembahasan.md" in combined


def test_check_gagal_jika_format_tidak_ada(tmp_path: Path) -> None:
    out = create_assignment(tmp_path)
    manifest_path = out / "manifest.yml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            "format: undip-msi", "format: format-tidak-ada"
        ),
        encoding="utf-8",
    )

    completed = run_cli("check", str(out))

    assert completed.returncode != 0
    assert "Format 'format-tidak-ada' tidak ditemukan" in completed.stderr


def test_manifest_parsing_valid() -> None:
    project = manifest_mod.load_project(ROOT / "content" / "examples" / "assignment")

    assert project.structure.name == "assignment"
    assert project.structure.body_numbering == "ARABIC_DOTTED"
    assert project.structure.toc is False
    assert project.structure.blank_line == "before_heading_only"
    assert project.structure.front_matter == ("cover",)
    assert project.structure.back_matter == ("bibliography",)
    assert project.structure.chapters == (
        "chapters/01-pendahuluan.md",
        "chapters/02-pembahasan.md",
        "chapters/03-penutup.md",
    )
    assert project.format.name == "undip-msi"
    assert project.format.preset_for("assignment") == "undip-msi-proposal"
    assert project.report_name == "Tugas"
    assert manifest_mod.load_yaml(project.metadata_path)["toc"] is False


def test_check_contoh_assignment_lulus() -> None:
    completed = run_cli("check", str(ROOT / "content" / "examples" / "assignment"))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "3 bab siap" in completed.stdout


def test_build_dry_run_memakai_env_pipeline_lama(tmp_path: Path) -> None:
    out = create_assignment(tmp_path)

    completed = run_cli("build", str(out), "--dry-run")

    assert completed.returncode == 0, completed.stderr
    assert "build-docx.sh" in completed.stdout
    assert "LAPORAN_METADATA=" in completed.stdout
    assert "LAPORAN_CHAPTERS=" in completed.stdout
    assert "LAPORAN_REPORT_NAME=Tugas" in completed.stdout
    assert "LAPORAN_TOC=false" in completed.stdout
    assert "metadata.yml" in completed.stdout
    assert "chapters" in completed.stdout


def test_build_dry_run_thesis_meneruskan_toc_true(tmp_path: Path) -> None:
    out = tmp_path / "tesis"
    completed = run_cli("new", "thesis", "--format", "undip-msi", "--out", str(out))
    assert completed.returncode == 0, completed.stderr

    completed = run_cli("build", str(out), "--dry-run")

    assert completed.returncode == 0, completed.stderr
    assert "LAPORAN_TOC=true" in completed.stdout


def test_build_dry_run_metadata_toc_menimpa_struktur(tmp_path: Path) -> None:
    out = create_assignment(tmp_path)
    metadata_path = out / "metadata.yml"
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace("toc: false", "toc: true"),
        encoding="utf-8",
    )

    completed = run_cli("build", str(out), "--dry-run")

    assert completed.returncode == 0, completed.stderr
    assert "LAPORAN_TOC=true" in completed.stdout


@pytest.mark.parametrize("structure", ["thesis", "proposal"])
def test_semua_struktur_dapat_dimuat(structure: str) -> None:
    loaded = manifest_mod.load_structure(structure)

    assert loaded.name == structure
    assert loaded.chapters
    assert loaded.format == "undip-msi"
