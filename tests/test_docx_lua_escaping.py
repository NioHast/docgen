"""Regresi escaping XML di docx.lua untuk judul heading di daftar isi.

Heading yang memuat ``&``, ``<``, atau ``>`` ditulis docx.lua ke XML mentah
untuk entri daftar isi. Tanpa escaping, ``word/document.xml`` menjadi tidak
valid. Tes ini memastikan dokumen tetap well-formed dan teks heading tidak
berubah.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DOCX = ROOT / "reference.docx"
LUA_FILTER = ROOT / "docx.lua"
PANDOC_DIR = Path(r"C:\Users\nioha\AppData\Local\Pandoc")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

MARKDOWN = """\
# BAB I

## R&D <Test> > 1

Teks.
"""


def _pandoc() -> tuple[str, dict[str, str]]:
    """Cari Pandoc dan siapkan PATH yang menyertakan instalasi Windows."""

    env = os.environ.copy()
    search_path = env.get("PATH", "")
    if PANDOC_DIR.is_dir():
        search_path = str(PANDOC_DIR) + os.pathsep + search_path
    env["PATH"] = search_path

    candidates = [
        env.get("PANDOC"),
        shutil.which("pandoc", path=search_path),
    ]
    local_appdata = env.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(str(Path(local_appdata) / "Pandoc" / "pandoc.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate, env
    pytest.skip("pandoc tidak tersedia")


def _style_id(paragraph: ElementTree.Element) -> str:
    ppr = paragraph.find(f"{W}pPr")
    if ppr is None:
        return ""
    style = ppr.find(f"{W}pStyle")
    return style.get(f"{W}val", "") if style is not None else ""


def _text(paragraph: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{W}t"))


def test_heading_dengan_karakter_xml_tetap_valid(tmp_path: Path) -> None:
    source = tmp_path / "escaping.md"
    source.write_text(MARKDOWN, encoding="utf-8")
    output = tmp_path / "escaping.docx"
    pandoc, env = _pandoc()

    result = subprocess.run(
        [
            pandoc,
            # raw_html dimatikan agar <Test> tetap teks literal, bukan tag HTML
            # yang dibuang saat menulis DOCX.
            "--from=markdown-raw_html",
            str(source),
            "--reference-doc=reference.docx",
            "--lua-filter=docx.lua",
            "-o",
            str(output),
        ],
        cwd=str(ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert output.is_file(), "pandoc tidak menghasilkan DOCX"

    with zipfile.ZipFile(output) as archive:
        document = archive.read("word/document.xml")

    # Gagal bila XML tidak well-formed (mis. & atau < mentah di entri TOC).
    root = ElementTree.fromstring(document)
    paragraphs = list(root.iter(f"{W}p"))

    heading_texts = [
        _text(paragraph)
        for paragraph in paragraphs
        if _style_id(paragraph) == "Heading2"
    ]
    assert len(heading_texts) == 1, heading_texts
    assert heading_texts[0].startswith("1.1.")
    assert heading_texts[0].endswith("R&D <Test> > 1")

    toc_texts = [
        _text(paragraph)
        for paragraph in paragraphs
        if _style_id(paragraph) == "TOC2"
    ]
    assert len(toc_texts) == 1, toc_texts
    assert toc_texts[0].startswith("1.1.")
    assert "R&D <Test> > 1" in toc_texts[0]

    raw = document.decode("utf-8")
    assert "R&amp;D &lt;Test&gt; &gt; 1" in raw
    assert "R&D" not in raw
    assert "<Test>" not in raw
