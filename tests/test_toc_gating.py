"""Regresi pemisahan ``toc`` (Pandoc/PDF) dan ``docx_toc`` (DOCX).

``build-docx.sh`` selalu mematikan TOC writer Pandoc untuk DOCX agar tidak
menghasilkan daftar isi ganda. TOC kustom ``docx.lua`` dikendalikan metadata
``docx_toc``: ``true`` menghasilkan tepat satu DAFTAR ISI setelah sampul
(dibungkus ``w:sdt`` gallery "Table of Contents" berisi field TOC tanpa entri
manual), ``false`` menghasilkan nol daftar isi. PDF diekspor dari DOCX final,
jadi tidak ada jalur template terpisah.
"""

from __future__ import annotations

import os
import re
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
# PENDAHULUAN

## Latar Belakang

Teks.
"""

COVER_METADATA = (
    "--metadata=title=Judul Sampul",
    "--metadata=author=Nama Penulis",
    "--metadata=course=Mata Kuliah",
    "--metadata=institution=Universitas Uji",
    "--metadata=faculty=Fakultas Uji",
    "--metadata=year=2026",
)


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


def _build_docx(
    tmp_path: Path,
    *,
    docx_toc: bool | None = None,
    cover: bool = False,
) -> bytes:
    """Bangun DOCX dengan kontrak flag yang sama seperti ``build-docx.sh``.

    ``--metadata=toc=false`` selalu dikirim agar TOC writer Pandoc tidak
    menulis daftar isi. Nilai proyek ``toc`` diterjemahkan oleh build script
    menjadi ``docx_toc``; ``docx_toc=None`` menguji default ``docx.lua``.
    """

    source = tmp_path / "toc.md"
    source.write_text(MARKDOWN, encoding="utf-8")
    output = tmp_path / "toc.docx"
    pandoc, env = _pandoc()

    metadata = ["--metadata=toc=false"]
    if docx_toc is not None:
        metadata.append(f"--metadata=docx_toc={'true' if docx_toc else 'false'}")
    if cover:
        metadata.extend(COVER_METADATA)

    command = [
        pandoc,
        str(source),
        f"--reference-doc={REFERENCE_DOCX}",
        f"--lua-filter={LUA_FILTER}",
        *metadata,
        "-o",
        str(output),
    ]
    result = subprocess.run(
        command,
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
        return archive.read("word/document.xml")


def _style_id(paragraph: ElementTree.Element) -> str:
    ppr = paragraph.find(f"{W}pPr")
    if ppr is None:
        return ""
    style = ppr.find(f"{W}pStyle")
    return style.get(f"{W}val", "") if style is not None else ""


def _paragraphs(root: ElementTree.Element) -> list[ElementTree.Element]:
    return list(root.iter(f"{W}p"))


def _texts(paragraphs: list[ElementTree.Element]) -> list[str]:
    return [
        "".join(node.text or "" for node in paragraph.iter(f"{W}t"))
        for paragraph in paragraphs
    ]


def _toc_fields(root: ElementTree.Element) -> list[str]:
    instructions = [node.text or "" for node in root.iter(f"{W}instrText")]
    return [instruction for instruction in instructions if re.search(r"\bTOC\b", instruction)]


def _toc_content_controls(root: ElementTree.Element) -> list[ElementTree.Element]:
    """Kembalikan ``w:sdt`` dengan gallery content control TOC."""

    controls = []
    for sdt in root.iter(f"{W}sdt"):
        gallery = sdt.find(
            f"{W}sdtPr/{W}docPartObj/{W}docPartGallery"
        )
        if gallery is not None and gallery.get(f"{W}val") == "Table of Contents":
            controls.append(sdt)
    return controls


def _assert_no_toc(document: bytes) -> None:
    root = ElementTree.fromstring(document)
    paragraphs = _paragraphs(root)
    texts = _texts(paragraphs)

    assert "DAFTAR ISI" not in texts
    assert "Table of Contents" not in texts
    assert all(not _style_id(paragraph).startswith("TOC") for paragraph in paragraphs)
    assert _toc_fields(root) == []
    assert _toc_content_controls(root) == []


def _assert_exactly_one_toc(
    document: bytes, *, after_cover: bool = False
) -> None:
    root = ElementTree.fromstring(document)
    paragraphs = _paragraphs(root)
    texts = _texts(paragraphs)

    assert texts.count("DAFTAR ISI") == 1
    assert "Table of Contents" not in texts
    assert len(_toc_fields(root)) == 1

    controls = _toc_content_controls(root)
    assert len(controls) == 1, "TOC harus dibungkus satu w:sdt gallery TOC"
    content = controls[0].find(f"{W}sdtContent")
    assert content is not None, "w:sdt TOC tidak punya w:sdtContent"
    content_texts = _texts(_paragraphs(content))
    assert "DAFTAR ISI" in content_texts, "judul TOC harus berada di dalam w:sdtContent"
    assert len(_toc_fields(content)) == 1, "field TOC harus berada di dalam w:sdtContent"

    # docx.lua hanya menulis field; entri manual (TOC2/TOC3/PAGEREF) tidak
    # boleh ada. Word/LibreOffice yang mengisi hasil field.
    manual_entries = [
        paragraph
        for paragraph in paragraphs
        if _style_id(paragraph) in {"TOC2", "TOC3"}
    ]
    assert manual_entries == [], "docx.lua tidak boleh menulis entri TOC manual"
    assert "PAGEREF" not in document.decode("utf-8")

    toc_index = texts.index("DAFTAR ISI")
    assert _style_id(paragraphs[toc_index]) == "TOCHeading"

    if after_cover:
        cover_indices = [
            index
            for index, paragraph in enumerate(paragraphs)
            if _style_id(paragraph).startswith("Cover")
        ]
        assert cover_indices, "sampul tidak terbentuk dari metadata"
        assert toc_index > max(cover_indices), "DAFTAR ISI harus setelah sampul"


def test_toc_true_tepat_satu_daftar_isi_setelah_sampul(tmp_path: Path) -> None:
    document = _build_docx(tmp_path, docx_toc=True, cover=True)

    _assert_exactly_one_toc(document, after_cover=True)


def test_toc_false_tidak_menyisipkan_daftar_isi(tmp_path: Path) -> None:
    document = _build_docx(tmp_path, docx_toc=False, cover=True)

    _assert_no_toc(document)


def test_docx_tanpa_metadata_tetap_default_tesis(tmp_path: Path) -> None:
    # ``toc=false`` dari writer tidak boleh mematikan TOC kustom: default
    # ``docx_toc`` tetap true untuk proyek lama.
    document = _build_docx(tmp_path)

    _assert_exactly_one_toc(document)



