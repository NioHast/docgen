"""Tes API ``build_docx`` dan golden part DOCX untuk fixture minimal.

Fixture dibangun dengan :func:`autooffice.docx.command.build_docx`, lalu
seluruh part dibandingkan dengan baseline JSON ternormalisasi di
``tests/fixtures/golden/docx/minimal/baseline.json``. Normalisasi menutup
timestamp, Id relationship, path data paket, dan part biner.

Word dinonaktifkan pada test golden agar output deterministik dan tidak
bergantung pada versi Word. Perilaku Word nyata tidak menjadi bagian baseline
ini; stage office diuji terpisah dengan fake Word.
"""

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from autooffice.docx.command import build_docx
from autooffice.docx.package import DocumentPackage
from autooffice.docx.stages import office
from tests._helpers.pandoc import pandoc_available

pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="Pandoc diperlukan untuk membangun fixture DOCX",
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "docx" / "minimal"
GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "docx" / "minimal"
BASELINE = GOLDEN_DIR / "baseline.json"
NORMALIZER = GOLDEN_DIR / "normalize.py"
EXPECTED_TEXT = "Teks dengan sitasi"
EXPECTED_WARNINGS = (
    "stage 'terms' dinonaktifkan oleh opsi build.",
    "stage 'toc' dinonaktifkan oleh opsi build.",
    "stage 'lists' dinonaktifkan oleh opsi build.",
    "Microsoft Word tidak tersedia; field DOCX tidak diperbarui dan TOC memakai "
    "cache terakhir. DOCX tetap dihasilkan.",
    "stage 'pdf' dinonaktifkan oleh opsi build.",
)


def _load_normalizer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("docx_golden_normalizer", NORMALIZER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"normalizer tidak dapat dimuat: {NORMALIZER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NORMALIZE = _load_normalizer()


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(FIXTURE, project)
    return project / "document.md"


def _disable_word(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(office, "word_available", lambda: False)


def _parts(package: DocumentPackage) -> dict[str, bytes]:
    return {name: package.part(name) for name in package.part_names()}


def _assert_parts_match(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    assert list(actual) == list(expected), "daftar part ternormalisasi berbeda"
    for name in expected:
        assert actual[name] == expected[name], f"part berbeda: {name}"


def test_build_docx_matches_golden_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_word(monkeypatch)
    document = _copy_project(tmp_path)
    out_dir = tmp_path / "out"

    result = build_docx(
        document,
        out=out_dir,
        terms=False,
        keep_intermediate=False,
    )

    # report_name menjadi nama berkas output.
    assert result.docx == out_dir / "Paritas.docx"
    assert result.docx.name == "Paritas.docx"
    assert result.docx.is_file()
    assert result.docx.stat().st_size > 0
    assert result.terms is None
    assert result.warnings == EXPECTED_WARNINGS
    assert result.workspace is None

    assert result.manifest is not None
    assert result.manifest == document.parent / ".laporan" / "manifest.json"
    assert result.manifest.is_file()
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["version"] == 1
    assert manifest["docx"] == "Paritas.docx"
    assert manifest["paragraphs"][0]["id"] == "p0001"

    package = DocumentPackage.load(result.docx)
    document_text = package.part("word/document.xml").decode("utf-8")
    assert EXPECTED_TEXT in document_text

    golden = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert golden["schema_version"] == 1
    assert golden["fixture"] == "tests/fixtures/docx/minimal/document.md"
    actual_parts = NORMALIZE.normalize_parts(_parts(package))
    _assert_parts_match(actual_parts, golden["parts"])


def test_build_docx_terms_and_workspace_opt_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_word(monkeypatch)
    document = _copy_project(tmp_path)
    out_dir = tmp_path / "out"

    result = build_docx(
        document,
        out=out_dir,
        terms=True,
        keep_intermediate=True,
    )

    assert result.docx == out_dir / "Paritas.docx"
    assert result.docx.is_file()
    assert result.terms is not None
    assert result.terms == document.parent / ".laporan" / "istilah-baru.txt"
    assert result.terms.is_file()
    assert result.workspace is not None
    assert result.workspace == (document.parent / ".laporan-build").resolve()
    assert result.workspace.is_dir()
    assert (result.workspace / "reference.docx").is_file()
    assert (result.workspace / "Paritas.docx").is_file()
    assert all("stage 'terms' dinonaktifkan" not in warning for warning in result.warnings)
