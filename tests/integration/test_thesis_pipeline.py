"""Integrasi pipeline thesis: ``docgen build --target both``.

Tes ini memakai contoh nyata ``examples/thesis-single`` yang disalin ke
direktori sementara. Stage nyata (Mermaid, Pandoc, Word bila tersedia)
dijalankan, lalu invariant DOCX/PDF kontrak WS15 diperiksa.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from docgen.docx.package import DocumentPackage
from docgen.features.adeu.manifest import load_manifest
from docgen.pipeline import (
    CANONICAL_ORDER,
    BuildOptions,
    Pipeline,
    StageName,
)
from docgen.stages.mermaid import find_mmdc
from docgen.stages.office import word_available
from docgen.stages.pandoc import find_pandoc

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "thesis-single"
PANDOC = find_pandoc()
MMDC = find_mmdc()
WORD = word_available()
SKIP_REASON = "Pandoc dan mmdc diperlukan untuk membangun contoh thesis"
TARGET = "both" if WORD else "docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W_VAL = f"{{{W_NS}}}val"
W_START = f"{{{W_NS}}}start"
W_FMT = f"{{{W_NS}}}fmt"
TOC_MAIN_RE = re.compile(r"^\s*TOC\s+\\o\b")
TOC_CAPTION_RE = re.compile(r'^\s*TOC\s+\\c\s+"(?P<label>[^"]+)"')
CAPTION_RE = re.compile(r"^(Tabel|Gambar)\s+\d+\.\d+\b")


def _copy_example(destination: Path) -> Path:
    project = destination / "proyek"
    shutil.copytree(EXAMPLE, project, ignore=shutil.ignore_patterns("out", ".laporan*"))
    return project / "document.md"


def _record_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    commands: list[list[str]] = []
    original = subprocess.run

    def run(command, *args, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(command, (list, tuple)):
            commands.append([str(part) for part in command])
        else:
            commands.append([str(command)])
        return original(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    return commands


def _record_package_io(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Path], list[Path]]:
    loads: list[Path] = []
    saves: list[Path] = []
    real_load = DocumentPackage.load
    real_save = DocumentPackage.save

    def load(cls, path, **kwargs):  # type: ignore[no-untyped-def]
        loads.append(Path(path))
        return real_load(path, **kwargs)

    def save(self, path, **kwargs):  # type: ignore[no-untyped-def]
        saves.append(Path(path))
        return real_save(self, path, **kwargs)

    monkeypatch.setattr(DocumentPackage, "load", classmethod(load))
    monkeypatch.setattr(DocumentPackage, "save", save)
    return loads, saves


def _document_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _instructions(root: etree._Element) -> list[str]:
    return [
        node.text or ""
        for node in root.xpath("//w:instrText", namespaces=NS)
        if (node.text or "").strip()
    ]


def _sdt_instruction(sdt: etree._Element) -> str:
    return "".join(
        node.text or ""
        for node in sdt.iter(f"{{{W_NS}}}instrText")
    )


def _sdt_text(sdt: etree._Element) -> str:
    return _normalized(
        " ".join(node.text or "" for node in sdt.iter(f"{{{W_NS}}}t"))
    )


def _caption_texts(root: etree._Element) -> list[str]:
    captions: list[str] = []
    for paragraph in root.xpath("//w:p", namespaces=NS):
        text = _normalized(_paragraph_text(paragraph))
        if CAPTION_RE.match(text):
            captions.append(text)
    return captions


def _headings(root: etree._Element, level: int = 1) -> list[str]:
    values: list[str] = []
    for paragraph in root.xpath("//w:p", namespaces=NS):
        styles = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
        if styles and styles[0] == f"Heading{level}":
            values.append(_normalized(_paragraph_text(paragraph)))
    return values


def _section_page_number_formats(root: etree._Element) -> list[tuple[str | None, str | None]]:
    return [
        (element.get(W_FMT), element.get(W_START))
        for element in root.xpath("//w:sectPr/w:pgNumType", namespaces=NS)
    ]


def _pdf_texts(path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return [(page.extract_text() or "").strip() for page in reader.pages]


@pytest.mark.skipif(
    PANDOC is None or MMDC is None,
    reason=SKIP_REASON,
)
def test_build_thesis_example_lewat_pipeline_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _copy_example(tmp_path)
    commands = _record_subprocess(monkeypatch)
    loads, saves = _record_package_io(monkeypatch)

    result = Pipeline().run(document, BuildOptions(target=TARGET))  # type: ignore[arg-type]

    assert result.docx is not None and result.docx.is_file()
    assert zipfile.is_zipfile(result.docx)
    output = result.docx
    assert output == document.parent / "Tugas.docx"
    if TARGET == "both":
        assert result.pdf is not None and result.pdf.is_file()
        assert result.pdf.read_bytes().startswith(b"%PDF-")
    else:
        assert result.pdf is None

    # Satu load/save package target. Verifikasi bookmark membaca ZIP mentah.
    assert len([path for path in saves if path.name == "Tugas.docx"]) == 1
    assert not any(path.name == "Tugas.docx" for path in loads)

    # Trust boundary: tidak ada docx.lua/shell lama yang dieksekusi.
    for command in commands:
        executable = Path(command[0]).name.lower()
        assert executable not in {"build-docx.sh", "build.sh", "docx.lua"}
        lowered = [part.lower() for part in command]
        assert not any("docx.lua" in part for part in lowered)
        assert not any(part.startswith("--lua-filter") for part in lowered)

    stages = [stage.stage for stage in result.stages]
    assert stages == [name.value for name in CANONICAL_ORDER]
    assert StageName.FRONT_MATTER.value in stages

    root = _document_root(output)
    instructions = _instructions(root)

    # Tepat satu field TOC utama, dan tepat satu sdt utama.
    main_toc = [value for value in instructions if TOC_MAIN_RE.match(value)]
    assert len(main_toc) == 1
    main_sdts = [
        sdt
        for sdt in root.xpath("//w:sdt", namespaces=NS)
        if TOC_MAIN_RE.match(_sdt_instruction(sdt))
    ]
    assert len(main_sdts) == 1
    galleries = root.xpath(
        "//w:sdt/w:sdtPr/w:docPartObj/w:docPartGallery[@w:val='Table of Contents']",
        namespaces=NS,
    )
    assert len(galleries) == 3  # TOC + daftar tabel + daftar gambar

    # Daftar tabel/gambar memakai TOC \c dan cache Word sudah terisi.
    caption_fields = {
        match.group("label"): value
        for value in instructions
        if (match := TOC_CAPTION_RE.match(value))
    }
    assert set(caption_fields) == {"Tabel", "Gambar"}
    list_texts: dict[str, str] = {}
    for sdt in root.xpath("//w:sdt", namespaces=NS):
        instruction = _sdt_instruction(sdt)
        match = TOC_CAPTION_RE.match(instruction)
        if match is not None:
            list_texts[match.group("label")] = _sdt_text(sdt)
    assert "Tabel 2.1" in list_texts["Tabel"]
    assert "Gambar 4.1" in list_texts["Gambar"]

    # Caption per bab sesuai isi contoh.
    captions = _caption_texts(root)
    assert any(text.startswith("Tabel 2.1 ") for text in captions)
    assert any(text.startswith("Gambar 4.1 ") for text in captions)

    # Lampiran tidak boleh menjadi bab bernomor (BAB VI).
    headings = _headings(root)
    assert any(text.casefold() == "lampiran" for text in headings)
    assert not any(text.upper().startswith("BAB VI") for text in headings)

    # Front matter Romawi, body mulai Arab 1. Word boleh menghapus fmt
    # decimal karena itu default, tetapi start=1 dan tidak ada lowerRoman.
    page_formats = _section_page_number_formats(root)
    assert page_formats
    roman_index = next(
        index for index, (fmt, _) in enumerate(page_formats) if fmt == "lowerRoman"
    )
    assert any(
        start == "1" and fmt != "lowerRoman"
        for fmt, start in page_formats[roman_index + 1 :]
    )

    # Manifest dan source scan tidak kosong.
    assert result.manifest is not None
    manifest = load_manifest(result.manifest)
    assert len(manifest) > 0
    assert any(paragraph.source_file for paragraph in manifest)
    assert manifest.docx == "Tugas.docx"

    # Bookmark pNNNN dipertahankan Word dan sama dengan manifest.
    with zipfile.ZipFile(output) as archive:
        final_root = etree.fromstring(archive.read("word/document.xml"))
    bookmarks = [
        element.get(f"{{{W_NS}}}name") or ""
        for element in final_root.xpath("//w:bookmarkStart", namespaces=NS)
        if re.fullmatch(r"p\d{4,}", element.get(f"{{{W_NS}}}name") or "")
    ]
    assert tuple(bookmarks) == tuple(paragraph.id for paragraph in manifest)

    if TARGET == "both":
        assert result.pdf is not None
        pdf_pages = _pdf_texts(result.pdf)
        assert len(pdf_pages) >= 2
        assert any("DAFTAR ISI" in page for page in pdf_pages)
        toc_index = next(index for index, page in enumerate(pdf_pages) if "DAFTAR ISI" in page)
        bab_index = next(
            index
            for index, page in enumerate(pdf_pages)
            if index > toc_index and "BAB I" in page
        )
        # Tidak ada halaman kosong di antara daftar isi dan BAB I.
        for page in pdf_pages[toc_index + 1 : bab_index]:
            assert len(_normalized(page)) > 8
        assert "BAB I" in pdf_pages[bab_index]
        assert "DAFTAR TABEL" in pdf_pages[toc_index]
        assert "DAFTAR GAMBAR" in pdf_pages[toc_index]
