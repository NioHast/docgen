"""Golden invariant DOCX hasil build ``examples/thesis-single``.

Fixture ``tests/fixtures/golden/laporan-baseline.docx`` dibangun dari
``examples/thesis-single`` pada commit ``4a5b777`` memakai Microsoft Word di
Windows. Metadata pribadi di ``docProps/core.xml`` sudah dibersihkan. Tes ini
membekukan invariant struktur output baseline, bukan mem-build ulang dokumen.

Jalankan:
    python -m pytest tests/integration/test_golden_docx.py -v
"""

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from docgen.docx.xml import sha256_c14n

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "golden" / "laporan-baseline.docx"
BASELINE_JSON = ROOT / "tests" / "fixtures" / "golden" / "baseline-4a5b777.json"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
NS = {"w": W_NS, "r": REL_NS}

W_VAL = f"{{{W_NS}}}val"
W_TYPE = f"{{{W_NS}}}type"
W_STYLE_ID = f"{{{W_NS}}}styleId"
W_LEADER = f"{{{W_NS}}}leader"
W_INSTR = f"{{{W_NS}}}instr"
W_FLD_CHAR_TYPE = f"{{{W_NS}}}fldCharType"
APP_PAGES = f"{{{APP_NS}}}Pages"

TOC_FIELD_RE = re.compile(r"^\s*TOC\b")
CAPTION_RE = re.compile(r"^(Tabel|Gambar)\s+\d+\.\d+\b")
PAGE_RESULT_RE = re.compile(r"^\d+$")
CAPTION_STYLES = {"TableCaption", "ImageCaption"}

EXPECTED_TABLES = [
    "Tabel 2.1 Pemetaan lapisan pipeline docgen",
    "Tabel 4.1 Aspek yang diverifikasi pada contoh tesis",
]
EXPECTED_FIGURES = [
    "Gambar 3.1 Alur validasi dan build dokumen",
    "Gambar 4.1 Arsitektur pipeline docgen dari Markdown hingga DOCX",
]

EXPECTED_TOC_ENTRIES = {
    "BAB I PENDAHULUAN": ("1", True),
    "2.1.": ("3", False),
}
EXPECTED_TOC_FIELDS = 3
EXPECTED_TOC_GALLERIES = 3
EXPECTED_CODE_TABLES = 1


def _read_parts() -> dict[str, bytes]:
    assert FIXTURE.is_file(), f"fixture golden tidak ada: {FIXTURE}"
    with zipfile.ZipFile(FIXTURE) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _document_root(parts: dict[str, bytes]) -> etree._Element:
    return etree.fromstring(parts["word/document.xml"])


def _styles_root(parts: dict[str, bytes]) -> etree._Element:
    return etree.fromstring(parts["word/styles.xml"])


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _toc_field_count(root: etree._Element) -> int:
    """Hitung field TOC, baik field kompleks maupun ``w:fldSimple``."""

    count = 0
    for instruction in root.xpath("//w:instrText", namespaces=NS):
        if instruction.text and TOC_FIELD_RE.match(instruction.text):
            count += 1
    for field in root.xpath("//w:fldSimple", namespaces=NS):
        instruction = field.get(W_INSTR)
        if instruction and TOC_FIELD_RE.match(instruction):
            count += 1
    return count


def _toc_instructions(root: etree._Element) -> list[str]:
    instructions = [
        _normalized(instruction.text or "")
        for instruction in root.xpath("//w:instrText", namespaces=NS)
        if instruction.text and TOC_FIELD_RE.match(instruction.text)
    ]
    instructions.extend(
        _normalized(field.get(W_INSTR) or "")
        for field in root.xpath("//w:fldSimple", namespaces=NS)
        if field.get(W_INSTR) and TOC_FIELD_RE.match(field.get(W_INSTR) or "")
    )
    return instructions


def _toc_galleries(root: etree._Element) -> list[etree._Element]:
    return [
        gallery
        for gallery in root.xpath("//w:sdt/w:sdtPr/w:docPartObj/w:docPartGallery", namespaces=NS)
        if gallery.get(W_VAL) == "Table of Contents"
    ]


def _captions(root: etree._Element) -> dict[str, list[str]]:
    captions: dict[str, list[str]] = {"Tabel": [], "Gambar": []}
    for paragraph in root.xpath("//w:p", namespaces=NS):
        styles = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
        if not styles or styles[0] not in CAPTION_STYLES:
            continue
        text = _normalized(_paragraph_text(paragraph))
        if CAPTION_RE.match(text):
            captions[text.split()[0]].append(text)
    return captions


def _is_code_table(table: etree._Element) -> bool:
    styles = {
        style.get(W_VAL) for style in table.xpath(".//w:pStyle", namespaces=NS) if style.get(W_VAL)
    }
    return bool(styles) and styles <= {"SourceCode"}


def _effective_border(table: etree._Element, cell: etree._Element, side: str) -> str | None:
    """Ambil border efektif dari tabel atau sel untuk satu sisi."""

    cell_border = cell.find(f"./w:tcPr/w:tcBorders/w:{side}", namespaces=NS)
    if cell_border is not None:
        return cell_border.get(W_VAL)
    table_border = table.find(f"./w:tblPr/w:tblBorders/w:{side}", namespaces=NS)
    if table_border is not None:
        return table_border.get(W_VAL)
    return None


def _field_result_values(paragraph: etree._Element) -> list[str]:
    """Ambil nilai hasil field (teks setelah ``separate`` sampai ``end``)."""

    values: list[str] = []
    current: list[str] | None = None
    for element in paragraph.iter():
        if element.tag == f"{{{W_NS}}}fldChar":
            kind = element.get(W_FLD_CHAR_TYPE)
            if kind == "separate":
                current = []
            elif kind == "end" and current is not None:
                values.append("".join(current))
                current = None
        elif element.tag == f"{{{W_NS}}}t" and current is not None:
            current.append(element.text or "")
    return values


def _toc_entry(root: etree._Element, prefix: str) -> etree._Element:
    matches = []
    for paragraph in root.xpath("//w:p", namespaces=NS):
        style = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
        if not style or style[0] not in {"TOC1", "TOC2", "TOC3"}:
            continue
        if _paragraph_text(paragraph).startswith(prefix):
            matches.append(paragraph)
    assert len(matches) == 1, f"entri TOC {prefix} ditemukan {len(matches)} kali"
    return matches[0]


def _style_has_dot_leader(parts: dict[str, bytes], style_id: str) -> bool:
    styles = _styles_root(parts).xpath(f'//w:style[@w:styleId="{style_id}"]', namespaces=NS)
    assert len(styles) == 1, f"style {style_id} tidak ada"
    return any(tab.get(W_LEADER) == "dot" for tab in styles[0].xpath(".//w:tab", namespaces=NS))


def _app_page_count(parts: dict[str, bytes]) -> int:
    root = etree.fromstring(parts["docProps/app.xml"])
    pages = root.find(APP_PAGES)
    assert pages is not None and pages.text is not None
    return int(pages.text)


def test_toc_field_count_and_instructions() -> None:
    root = _document_root(_read_parts())
    assert _toc_field_count(root) == EXPECTED_TOC_FIELDS

    instructions = _toc_instructions(root)
    main = [value for value in instructions if value.startswith("TOC \\o")]
    table_captions = [value for value in instructions if 'TOC \\c "Tabel"' in value]
    figure_captions = [value for value in instructions if 'TOC \\c "Gambar"' in value]
    assert len(main) == 1
    assert len(table_captions) == 1
    assert len(figure_captions) == 1


def test_toc_gallery_sdt_count() -> None:
    root = _document_root(_read_parts())
    galleries = _toc_galleries(root)
    assert len(galleries) == EXPECTED_TOC_GALLERIES
    assert all(gallery.get(W_VAL) == "Table of Contents" for gallery in galleries)


def test_captions_match_baseline() -> None:
    captions = _captions(_document_root(_read_parts()))
    assert captions["Tabel"] == EXPECTED_TABLES
    assert captions["Gambar"] == EXPECTED_FIGURES


def test_fixture_fingerprint_matches_baseline_record() -> None:
    baseline = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    assert baseline["source"] == "examples/thesis-single/document.md"
    assert baseline["docx"]["path"] == (FIXTURE.relative_to(ROOT).as_posix())
    assert baseline["docx"]["size_bytes"] == FIXTURE.stat().st_size
    assert baseline["docx"]["sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

    parts = _read_parts()
    assert baseline["docx"]["document_xml_sha256_c14n"] == sha256_c14n(parts["word/document.xml"])
    assert baseline["docx"]["page_count"] == _app_page_count(parts)


def test_code_tables_are_1x1_with_full_borders() -> None:
    root = _document_root(_read_parts())
    code_tables = [table for table in root.xpath("//w:tbl", namespaces=NS) if _is_code_table(table)]
    assert len(code_tables) == EXPECTED_CODE_TABLES

    for table in code_tables:
        rows = table.xpath("./w:tr", namespaces=NS)
        assert len(rows) == 1, "tabel kode harus 1 baris"
        cells = rows[0].xpath("./w:tc", namespaces=NS)
        assert len(cells) == 1, "tabel kode harus 1 kolom"
        for side in ("top", "left", "bottom", "right"):
            border = _effective_border(table, cells[0], side)
            assert border not in (None, "nil", "none"), f"border {side} tabel kode hilang"


@pytest.mark.parametrize(
    ("prefix", "page", "dot_leader"),
    [(prefix, page, dot_leader) for prefix, (page, dot_leader) in EXPECTED_TOC_ENTRIES.items()],
)
def test_key_toc_entries_have_dot_leader_and_page_number(
    prefix: str, page: str, dot_leader: bool
) -> None:
    parts = _read_parts()
    entry = _toc_entry(_document_root(parts), prefix)
    style_id = entry.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)[0]

    dot_tabs = [
        tab
        for tab in entry.xpath("./w:pPr/w:tabs/w:tab", namespaces=NS)
        if tab.get(W_LEADER) == "dot"
    ]
    if dot_leader:
        assert dot_tabs or _style_has_dot_leader(parts, style_id), (
            f"entri TOC {prefix} tidak punya tab leader titik"
        )
        if dot_tabs:
            assert any(tab.get(W_VAL) == "right" for tab in dot_tabs)
    else:
        assert not dot_tabs, f"entri TOC {prefix} tidak diharapkan punya dot leader"
        assert not _style_has_dot_leader(parts, style_id), (
            f"style {style_id} tidak diharapkan punya dot leader"
        )
    assert entry.xpath(".//w:r/w:tab", namespaces=NS), (
        f"entri TOC {prefix} tidak memakai tab di dalam run"
    )

    instructions = entry.xpath(".//w:instrText/text()", namespaces=NS)
    assert any("PAGEREF" in instruction for instruction in instructions), (
        f"entri TOC {prefix} tidak memakai field PAGEREF"
    )

    results = _field_result_values(entry)
    assert len(results) == 1, f"entri TOC {prefix} punya {len(results)} hasil field"
    assert PAGE_RESULT_RE.match(results[0]), (
        f"hasil PAGEREF entri TOC {prefix} bukan nomor halaman: {results[0]!r}"
    )
    assert results[0] == page, f"halaman TOC {prefix} berubah: {results[0]} != {page}"


def test_toc_styles_exist() -> None:
    styles = {
        style.get(W_STYLE_ID): style
        for style in _styles_root(_read_parts()).xpath("//w:style", namespaces=NS)
    }
    for style_id in ("TOC1", "TOC2", "TOC3"):
        assert style_id in styles, f"style {style_id} tidak ada"
        assert styles[style_id].get(W_TYPE) == "paragraph"

    toc1 = styles["TOC1"]
    assert any(tab.get(W_LEADER) == "dot" for tab in toc1.xpath(".//w:tab", namespaces=NS)), (
        "style TOC1 tidak punya tab leader titik"
    )


def test_no_unresolved_placeholders() -> None:
    parts = _read_parts()
    for name, data in parts.items():
        if not name.endswith((".xml", ".rels")):
            continue
        text = data.decode("utf-8", errors="replace")
        assert "{{" not in text, f"placeholder '{{{{' ditemukan di {name}"
        assert "}}" not in text, f"placeholder '}}}}' ditemukan di {name}"
