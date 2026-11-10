"""Golden invariant PDF (Windows/Word-only untuk build ulang).

``pdf-baseline.json`` mencatat invariant PDF yang dibangun dari
``examples/thesis-single``. PDF hasil build tidak di-commit karena ukurannya
besar; tes ini membangun ulang contoh ke direktori sementara lalu
membandingkannya dengan catatan baseline.

Jalankan di Windows:
    python -m pytest -m windows tests/integration/test_golden_pdf.py -v
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.windows,
    pytest.mark.word,
]

ROOT = Path(__file__).resolve().parents[2]
BASELINE_JSON = ROOT / "tests" / "fixtures" / "golden" / "pdf-baseline.json"
EXAMPLE = ROOT / "examples" / "thesis-single"

TOC_LINE_RE = re.compile(r"^(?P<label>.+?)\s*\.{3,}\s*(?P<page>[ivxlcdm]+|\d+)\s*$", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^(?:[ivxlcdm]+|\d+)$", re.IGNORECASE)


def _normalized(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def baseline() -> dict[str, object]:
    assert BASELINE_JSON.is_file(), f"baseline JSON tidak ada: {BASELINE_JSON}"
    return json.loads(BASELINE_JSON.read_text(encoding="utf-8"))


def _extract_toc(reader: object) -> list[dict[str, str]] | None:
    """Ambil entri TOC utama dari halaman yang memuat ``DAFTAR ISI``."""

    for page in reader.pages:  # type: ignore[attr-defined]
        text = page.extract_text() or ""
        if "DAFTAR ISI" not in _normalized(text):
            continue
        entries: list[dict[str, str]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if _normalized(stripped).startswith("DAFTAR TABEL"):
                break
            match = TOC_LINE_RE.match(stripped)
            if match:
                entries.append(
                    {
                        "label": match.group("label").strip(),
                        "page": match.group("page").strip(),
                    }
                )
        return entries
    return None


def _assert_pdf_matches_baseline(reader: object, baseline: dict[str, object]) -> None:
    expected_pages = baseline["page_count"]
    assert isinstance(expected_pages, int)
    assert len(reader.pages) == expected_pages  # type: ignore[attr-defined]

    expected_size = baseline["page_size_points"]
    assert isinstance(expected_size, list) and len(expected_size) == 2
    for page in reader.pages:  # type: ignore[attr-defined]
        actual_size = [float(page.mediabox.width), float(page.mediabox.height)]
        assert actual_size == pytest.approx(expected_size, abs=0.01)

    all_text = _normalized(
        " ".join((page.extract_text() or "") for page in reader.pages)  # type: ignore[attr-defined]
    )
    key_text = baseline["key_text"]
    assert isinstance(key_text, list)
    for key in key_text:
        assert key in all_text, f"teks kunci PDF hilang: {key}"

    actual_toc = _extract_toc(reader)
    assert actual_toc is not None, "halaman DAFTAR ISI tidak ditemukan di PDF"
    assert actual_toc == baseline["toc"]


def test_pdf_baseline_record_is_complete(baseline: dict[str, object]) -> None:
    """Validasi isi catatan baseline, bukan PDF hasil build."""

    assert baseline["schema_version"] == 1
    assert "fixture" not in baseline

    source = baseline["source"]
    assert isinstance(source, str) and "examples/thesis-single" in source

    page_count = baseline["page_count"]
    assert isinstance(page_count, int) and page_count > 0

    page_size = baseline["page_size_points"]
    assert isinstance(page_size, list) and len(page_size) == 2
    assert all(isinstance(value, (int, float)) and value > 0 for value in page_size)
    assert page_size[0] < page_size[1]

    key_text = baseline["key_text"]
    assert isinstance(key_text, list) and key_text
    assert all(isinstance(key, str) and key for key in key_text)
    assert len(set(key_text)) == len(key_text)

    toc = baseline["toc"]
    assert isinstance(toc, list) and toc
    labels: list[str] = []
    for entry in toc:
        assert isinstance(entry, dict)
        assert set(entry) == {"label", "page"}
        label = entry["label"]
        page = entry["page"]
        assert isinstance(label, str) and label
        assert isinstance(page, str) and PAGE_NUMBER_RE.match(page)
        labels.append(label)
    assert len(set(labels)) == len(labels)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="PDF build memerlukan Microsoft Word di Windows",
)
def test_pdf_build_matches_baseline(baseline: dict[str, object], tmp_path: Path) -> None:
    from pypdf import PdfReader

    project = tmp_path / "thesis-single"
    shutil.copytree(
        EXAMPLE,
        project,
        ignore=shutil.ignore_patterns("out", ".laporan*"),
    )

    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH")
    source = str(ROOT / "src")
    environment["PYTHONPATH"] = source if not existing else source + os.pathsep + existing
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "docgen",
            "build",
            str(project / "document.md"),
            "--target",
            "pdf",
        ],
        cwd=str(ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    pdf = project / "Tugas.pdf"
    assert pdf.is_file() and pdf.read_bytes().startswith(b"%PDF-")

    _assert_pdf_matches_baseline(PdfReader(str(pdf)), baseline)
