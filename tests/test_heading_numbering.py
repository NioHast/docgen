"""Regresi penomoran heading DOCX terhadap acuan/re/02-headings.yml.

H1 tetap literal ("BAB " + Romawi + line break + judul kapital).
H2/H3 memakai nomor literal dengan titik akhir dan TAB sebelum judul.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DOCX = ROOT / "reference.docx"
LUA_FILTER = ROOT / "docx.lua"

TEST_MD = """\
# KATA PENGANTAR {-}

Puji syukur.

# PENDAHULUAN

## Latar Belakang

Teks.

### Sub Pertama

Teks.

#### Detail Antara

Teks.

### Sub Kedua

Teks.

## Rumusan Masalah

Teks.

### Sub Ketiga

Teks.

### Sub Keempat

Teks.

# TINJAUAN PUSTAKA

## Landasan Teori

Teks.

### Sub Kelima

Teks.

## Penelitian Terdahulu

Teks.

### Sub Keenam

Teks.

# DAFTAR PUSTAKA {-}

Referensi.
"""


def _pandoc() -> str:
    """Cari pandoc di PATH, env PANDOC, atau instalasi Windows pengguna."""

    candidates = [os.environ.get("PANDOC"), shutil.which("pandoc")]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(str(Path(local_appdata) / "Pandoc" / "pandoc.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    pytest.skip("pandoc tidak tersedia")


def _headings(path: Path) -> list[tuple[str, str]]:
    doc = Document(path)
    result: list[tuple[str, str]] = []
    for paragraph in doc.paragraphs:
        style = paragraph.style.name if paragraph.style is not None else ""
        if style.startswith("Heading"):
            result.append((style, paragraph.text))
    return result


def test_nomor_heading_sesuai_acuan(tmp_path: Path) -> None:
    source = tmp_path / "test.md"
    source.write_text(TEST_MD, encoding="utf-8")
    output = tmp_path / "test.docx"

    subprocess.run(
        [
            _pandoc(),
            str(source),
            f"--reference-doc={REFERENCE_DOCX}",
            f"--lua-filter={LUA_FILTER}",
            "-o",
            str(output),
        ],
        check=True,
        cwd=ROOT,
    )

    headings = _headings(output)
    assert headings == [
        ("Heading 1", "KATA PENGANTAR"),
        ("Heading 1", "BAB I\nPENDAHULUAN"),
        ("Heading 2", "1.1.\tLatar Belakang"),
        ("Heading 3", "1.1.1.\tSub Pertama"),
        ("Heading 4", "Detail Antara"),
        ("Heading 3", "1.1.2.\tSub Kedua"),
        ("Heading 2", "1.2.\tRumusan Masalah"),
        ("Heading 3", "1.2.1.\tSub Ketiga"),
        ("Heading 3", "1.2.2.\tSub Keempat"),
        ("Heading 1", "BAB II\nTINJAUAN PUSTAKA"),
        ("Heading 2", "2.1.\tLandasan Teori"),
        ("Heading 3", "2.1.1.\tSub Kelima"),
        ("Heading 2", "2.2.\tPenelitian Terdahulu"),
        ("Heading 3", "2.2.1.\tSub Keenam"),
        ("Heading 1", "DAFTAR PUSTAKA"),
    ]


def test_tab_dan_indent_tidak_ditulis_manual(tmp_path: Path) -> None:
    source = tmp_path / "test.md"
    source.write_text(TEST_MD, encoding="utf-8")
    output = tmp_path / "test.docx"

    subprocess.run(
        [
            _pandoc(),
            str(source),
            f"--reference-doc={REFERENCE_DOCX}",
            f"--lua-filter={LUA_FILTER}",
            "-o",
            str(output),
        ],
        check=True,
        cwd=ROOT,
    )

    doc = Document(output)
    checked = 0
    for paragraph in doc.paragraphs:
        style = paragraph.style.name if paragraph.style is not None else ""
        if style not in ("Heading 2", "Heading 3"):
            continue
        checked += 1
        xml = paragraph._p.xml
        assert xml.count("<w:tab/>") == 1, paragraph.text
        assert re.search(r"<w:r>\s*<w:tab/>\s*</w:r>", xml), paragraph.text
        assert paragraph.paragraph_format.left_indent is None
        assert paragraph.paragraph_format.first_line_indent is None
    assert checked == 10

    # H1 memakai line break literal, bukan tab/spasi.
    bab = next(p for p in doc.paragraphs if p.text.startswith("BAB I\n"))
    assert "<w:br/>" in bab._p.xml
