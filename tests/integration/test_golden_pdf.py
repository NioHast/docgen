"""Golden invariant PDF (Windows/Word-only).

PDF baseline tidak di-commit karena ukurannya besar. ``pdf-baseline.json``
mencatat invariant yang harus dijaga. Jika ``laporan-baseline.pdf`` tidak ada,
perbandingan PDF di-skip secara eksplisit supaya tidak menjadi false-green.

Jalankan di Windows:
    python -m pytest -m windows tests/integration/test_golden_pdf.py -v
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.windows,
    pytest.mark.skipif(sys.platform != "win32", reason="Word-only"),
]

ROOT = Path(__file__).resolve().parents[2]
BASELINE_JSON = ROOT / "tests" / "fixtures" / "golden" / "pdf-baseline.json"
PDF_FIXTURE = ROOT / "tests" / "fixtures" / "golden" / "laporan-baseline.pdf"

TOC_LINE_RE = re.compile(
    r"^(?P<label>.+?)\s*\.{3,}\s*(?P<page>[ivxlcdm]+|\d+)\s*$", re.IGNORECASE
)

EXPECTED_PAGE_COUNT = 26
EXPECTED_TOC_COUNT = 44
EXPECTED_PAGES = {
    "2.6.1. Manajemen Dependensi dengan Python Virtual Environment": "9",
    "3.2.3. Algoritma Keseimbangan Judul Sampul": "13",
}
EXPECTED_KEY_TEXT = {
    "OTOMATISASI PEMBUATAN DOKUMEN LAPORAN",
    "MENGGUNAKAN PANDOC, TYPST, DAN MARKDOWN",
    "KATA PENGANTAR",
    "DAFTAR ISI",
    "BAB I",
    "PENDAHULUAN",
    "BAB V",
    "PENUTUP",
    "DAFTAR PUSTAKA",
}


def _normalized(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def baseline() -> dict[str, object]:
    assert BASELINE_JSON.is_file(), f"baseline JSON tidak ada: {BASELINE_JSON}"
    return json.loads(BASELINE_JSON.read_text(encoding="utf-8"))


def _toc_map(baseline: dict[str, object]) -> dict[str, str]:
    toc = baseline["toc"]
    assert isinstance(toc, list)
    return {entry["label"]: entry["page"] for entry in toc}


def _extract_toc(reader: object) -> list[dict[str, str]] | None:
    """Ambil entri TOC dari halaman yang memuat DAFTAR ISI."""

    for page in reader.pages:  # type: ignore[attr-defined]
        text = page.extract_text() or ""
        if "DAFTAR ISI" not in _normalized(text):
            continue
        entries: list[dict[str, str]] = []
        for line in text.splitlines():
            match = TOC_LINE_RE.match(line.strip())
            if match:
                entries.append(
                    {
                        "label": match.group("label").strip(),
                        "page": match.group("page").strip(),
                    }
                )
        return entries
    return None


def test_pdf_baseline_record_is_complete(baseline: dict[str, object]) -> None:
    """Validasi isi catatan baseline, bukan PDF hasil build."""

    assert baseline["schema_version"] == 1
    assert baseline["page_count"] == EXPECTED_PAGE_COUNT
    page_size = baseline["page_size_points"]
    assert isinstance(page_size, list) and len(page_size) == 2
    assert page_size == [595.5, 842.25]

    key_text = baseline["key_text"]
    assert isinstance(key_text, list)
    assert EXPECTED_KEY_TEXT <= set(key_text)

    toc = baseline["toc"]
    assert isinstance(toc, list)
    assert len(toc) == EXPECTED_TOC_COUNT
    toc_map = _toc_map(baseline)
    for label, page in EXPECTED_PAGES.items():
        assert toc_map.get(label) == page
    assert toc[0] == {"label": "KATA PENGANTAR", "page": "i"}
    assert toc[-1] == {"label": "DAFTAR PUSTAKA", "page": "22"}


def test_pdf_fixture_matches_baseline(baseline: dict[str, object]) -> None:
    if not PDF_FIXTURE.is_file():
        pytest.skip(
            f"fixture PDF tidak ada: {PDF_FIXTURE}; golden PDF tidak di-commit "
            "(manual/not gate)"
        )

    from pypdf import PdfReader

    reader = PdfReader(str(PDF_FIXTURE))
    assert len(reader.pages) == baseline["page_count"]

    expected_size = baseline["page_size_points"]
    assert isinstance(expected_size, list)
    for page in reader.pages:
        actual_size = [float(page.mediabox.width), float(page.mediabox.height)]
        assert actual_size == pytest.approx(expected_size, abs=0.01)

    all_text = _normalized(
        " ".join((page.extract_text() or "") for page in reader.pages)
    )
    key_text = baseline["key_text"]
    assert isinstance(key_text, list)
    for key in key_text:
        assert key in all_text, f"teks kunci PDF hilang: {key}"

    actual_toc = _extract_toc(reader)
    assert actual_toc is not None, "halaman DAFTAR ISI tidak ditemukan di PDF"
    assert actual_toc == baseline["toc"]
