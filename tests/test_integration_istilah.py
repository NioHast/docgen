"""Tes integrasi modul istilah dengan Pandoc dan laporan penuh."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn

from istilah import ISTILAH_ASING, main

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MD = ROOT / "writing" / "istilah-uji.md"
GLOSSARY = ROOT / "writing" / "istilah.tsv"
REFERENCE_DOCX = ROOT / "reference.docx"
REPORT = ROOT / "Laporan.docx"

W_RPR = qn("w:rPr")
W_RSTYLE = qn("w:rStyle")
W_VAL = qn("w:val")


def paragraph_style_spans(paragraph, style_id: str) -> list[str]:
    """Gabungkan run berurutan yang memakai character style tertentu."""

    spans: list[str] = []
    current: list[str] = []
    for run in paragraph.runs:
        rpr = run._r.find(W_RPR)
        run_style = None
        if rpr is not None:
            rstyle = rpr.find(W_RSTYLE)
            if rstyle is not None:
                run_style = rstyle.get(W_VAL)
        if run_style == style_id:
            current.append(run.text)
        elif current:
            spans.append("".join(current))
            current = []
    if current:
        spans.append("".join(current))
    return spans


def all_style_spans(path: Path, style_id: str) -> list[str]:
    doc = Document(path)
    spans: list[str] = []
    for paragraph in doc.paragraphs:
        spans.extend(paragraph_style_spans(paragraph, style_id))
    return spans


def xml_text(path: Path) -> str:
    """Semua teks XML Word, termasuk header/footer, untuk cek penanda tersisa."""

    chunks: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                chunks.append(archive.read(name).decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def test_pandoc_apply_verify_and_marker_conversion(tmp_path: Path) -> None:
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        pytest.skip("pandoc tidak tersedia")

    docx = tmp_path / "istilah-uji.docx"
    subprocess.run(
        [
            pandoc,
            str(SOURCE_MD),
            f"--reference-doc={REFERENCE_DOCX}",
            "-o",
            str(docx),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert docx.is_file(), "pandoc tidak menghasilkan DOCX"

    review_file = tmp_path / "review" / "istilah-baru.txt"
    assert (
        main(
            [
                "apply",
                str(docx),
                "--glossary",
                str(GLOSSARY),
                "--review-file",
                str(review_file),
            ]
        )
        == 0
    )

    assert main(["verify", str(docx), "--glossary", str(GLOSSARY)]) == 0

    spans = all_style_spans(docx, ISTILAH_ASING)
    assert "training data" in spans
    assert not any("data pelatihan" in span for span in spans)

    remaining = xml_text(docx)
    assert "{{?" not in remaining
    assert "?}}" not in remaining

    # Penanda baru harus menjadi teks review, bukan hilang atau tersisa.
    review = review_file.read_text(encoding="utf-8")
    assert "prompt engineering" in review
    assert "nama istilah" in review


def test_laporan_penuh_lolos_verify() -> None:
    if not REPORT.is_file():
        pytest.skip("Laporan.docx belum dibangun; jalankan bash build-docx.sh")
    assert main(["verify", str(REPORT), "--glossary", str(GLOSSARY)]) == 0
