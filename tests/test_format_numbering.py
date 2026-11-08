"""Tes post-process numbering daftar DOCX (``tools/format_numbering.py``)."""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from lxml import etree

import format_numbering as api

DOCUMENT_PART = "word/document.xml"
NUMBERING_PART = "word/numbering.xml"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


# ---------------------------------------------------------------------------
# Pembuat fixture


def _set_numbering(paragraph, num_id: int, ilvl: int = 0) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    numpr = OxmlElement("w:numPr")
    level = OxmlElement("w:ilvl")
    level.set(qn("w:val"), str(ilvl))
    number = OxmlElement("w:numId")
    number.set(qn("w:val"), str(num_id))
    numpr.append(level)
    numpr.append(number)
    ppr.append(numpr)


def _set_correct_indent(paragraph) -> None:
    """Buat indent 720/720 + tab 720 yang sudah sesuai target."""

    ppr = paragraph._p.get_or_add_pPr()

    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "left")
    tab.set(qn("w:pos"), "720")
    tabs.append(tab)
    ppr.append(tabs)

    ind = OxmlElement("w:ind")
    ind.set(qn("w:left"), "720")
    ind.set(qn("w:hanging"), "720")
    ppr.append(ind)


def _abstract_num(
    abstract_id: int,
    fmt: str,
    suffix: str,
    *,
    level_bold: bool = False,
) -> str:
    levels: list[str] = []
    for ilvl in range(9):
        text = " " if fmt == "bullet" else f"%{ilvl + 1}{suffix}"
        bold = ""
        if level_bold and ilvl == 0:
            bold = "<w:rPr><w:b/><w:bCs/></w:rPr>"
        levels.append(
            f'<w:lvl w:ilvl="{ilvl}">'
            '<w:start w:val="1"/>'
            f'<w:numFmt w:val="{fmt}"/>'
            f'<w:lvlText w:val="{text}"/>'
            '<w:lvlJc w:val="left"/>'
            f'<w:pPr><w:ind w:left="{720 * (ilvl + 1)}" w:hanging="360"/></w:pPr>'
            f"{bold}"
            "</w:lvl>"
        )
    return (
        f'<w:abstractNum w:abstractNumId="{abstract_id}">'
        '<w:multiLevelType w:val="hybridMultilevel"/>'
        + "".join(levels)
        + "</w:abstractNum>"
    )


def _numbering_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:numbering xmlns:w="{W_NS}">'
        + _abstract_num(10, "decimal", ".")
        + _abstract_num(11, "lowerLetter", ".")
        + _abstract_num(12, "lowerLetter", ")", level_bold=True)
        + _abstract_num(13, "bullet", " ")
        + '<w:num w:numId="101"><w:abstractNumId w:val="10"/></w:num>'
        + '<w:num w:numId="102"><w:abstractNumId w:val="11"/></w:num>'
        + '<w:num w:numId="103"><w:abstractNumId w:val="12"/></w:num>'
        + '<w:num w:numId="104"><w:abstractNumId w:val="13"/></w:num>'
        + "</w:numbering>"
    )


def _replace_part(path: Path, part: str, data: bytes) -> None:
    with zipfile.ZipFile(path, "r") as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]

    with zipfile.ZipFile(path, "w") as target:
        for info, payload in entries:
            target.writestr(info, data if info.filename == part else payload)


def build_fixture(path: Path) -> Path:
    document = Document()
    document.add_heading("Probe Numbering", level=1)
    document.add_paragraph("Paragraf pengantar.")

    def add(text: str, num_id: int, ilvl: int = 0, *, bold: bool = False):
        paragraph = document.add_paragraph()
        run = paragraph.add_run(text)
        if bold:
            run.bold = True
        _set_numbering(paragraph, num_id, ilvl)
        return paragraph

    add("Langkah satu", 101)
    add("Langkah dua", 101)
    add("Enumerasi satu", 102)
    add("Enumerasi dua", 102)
    add("Sub-poin satu", 103)
    add("Sub-poin dua", 103)
    add("Langkah utama", 101)
    add("Enumerasi anak", 102, 1)
    add("Sub-poin anak", 103, 1)
    add("Langkah tebal", 101, bold=True)

    add("Butir bullet tebal", 104, bold=True)

    disabled = document.add_paragraph()
    disabled.add_run("Bukan list (numId 0)").bold = True
    _set_numbering(disabled, 0)

    normal = document.add_paragraph()
    normal.add_run("Paragraf non-list tebal").bold = True
    normal.paragraph_format.left_indent = Pt(36)
    normal.paragraph_format.first_line_indent = Pt(18)

    correct = document.add_paragraph()
    correct.add_run("List sudah benar")
    _set_numbering(correct, 101)
    _set_correct_indent(correct)

    legacy = document.add_paragraph()
    legacy.add_run("Langkah indent lama")
    _set_numbering(legacy, 101)
    legacy_ppr = legacy._p.get_or_add_pPr()
    legacy_tabs = OxmlElement("w:tabs")
    legacy_tab = OxmlElement("w:tab")
    legacy_tab.set(qn("w:val"), "left")
    legacy_tab.set(qn("w:pos"), "360")
    legacy_tabs.append(legacy_tab)
    legacy_ppr.append(legacy_tabs)
    legacy_ind = OxmlElement("w:ind")
    legacy_ind.set(qn("w:left"), "360")
    legacy_ind.set(qn("w:firstLine"), "360")
    legacy_ind.set(qn("w:start"), "360")
    legacy_ppr.append(legacy_ind)

    document.save(path)
    _replace_part(path, NUMBERING_PART, _numbering_xml().encode("utf-8"))
    return path


def run_tool(source: Path, output: Path) -> api.NumberingReport:
    return api.format_numbering(source, output)


def document_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read(DOCUMENT_PART))


def numbering_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read(NUMBERING_PART))


def part_bytes(path: Path, part: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(part)


def paragraph_by_text(root: etree._Element, text: str) -> etree._Element:
    for paragraph in root.xpath("//w:body/w:p", namespaces=NS):
        current = "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))
        if current == text:
            return paragraph
    raise AssertionError(f"Paragraf {text!r} tidak ditemukan")


def numbering_reference(paragraph: etree._Element) -> tuple[str, str] | None:
    num_ids = paragraph.xpath(
        "./w:pPr/w:numPr/w:numId/@w:val", namespaces=NS
    )
    if not num_ids:
        return None
    levels = paragraph.xpath("./w:pPr/w:numPr/w:ilvl/@w:val", namespaces=NS)
    return num_ids[0], levels[0] if levels else "0"


def level_for(numbering: etree._Element, num_id: str, ilvl: str = "0"):
    abstract_id = numbering.xpath(
        f'//w:num[@w:numId="{num_id}"]/w:abstractNumId/@w:val', namespaces=NS
    )
    assert abstract_id, f"numId {num_id} tidak ditemukan"
    levels = numbering.xpath(
        f'//w:abstractNum[@w:abstractNumId="{abstract_id[0]}"]'
        f'/w:lvl[@w:ilvl="{ilvl}"]',
        namespaces=NS,
    )
    assert levels, f"level {ilvl} untuk numId {num_id} tidak ditemukan"
    return levels[0]


def indentation(element: etree._Element) -> dict[str, str]:
    nodes = element.xpath("./w:pPr/w:ind", namespaces=NS)
    if not nodes:
        return {}
    return {key.split("}")[-1]: value for key, value in nodes[0].attrib.items()}


def tabs(element: etree._Element) -> list[dict[str, str]]:
    return [
        {key.split("}")[-1]: value for key, value in tab.attrib.items()}
        for tab in element.xpath("./w:pPr/w:tabs/w:tab", namespaces=NS)
    ]


# ---------------------------------------------------------------------------
# 1. Tiga format numbering


@pytest.mark.parametrize(
    ("text", "num_id", "expected_format", "expected_text"),
    [
        ("Langkah satu", "101", "decimal", "%1."),
        ("Enumerasi satu", "102", "lowerLetter", "%1."),
        ("Sub-poin satu", "103", "lowerLetter", "%1)"),
    ],
)
def test_tiga_format_dipertahankan(
    tmp_path: Path,
    text: str,
    num_id: str,
    expected_format: str,
    expected_text: str,
) -> None:
    source = build_fixture(tmp_path / "source.docx")
    output = tmp_path / "out.docx"

    run_tool(source, output)

    level = level_for(numbering_root(output), num_id)
    assert level.xpath("./w:numFmt/@w:val", namespaces=NS) == [expected_format]
    assert level.xpath("./w:lvlText/@w:val", namespaces=NS) == [expected_text]

    document = document_root(output)
    assert numbering_reference(paragraph_by_text(document, text)) == (num_id, "0")


# ---------------------------------------------------------------------------
# 2. Indent, hanging, tab stop


@pytest.mark.parametrize(
    ("text", "left"),
    [
        ("Langkah satu", "720"),
        ("Enumerasi satu", "720"),
        ("Sub-poin satu", "720"),
        ("Enumerasi anak", "1440"),
        ("Sub-poin anak", "1440"),
    ],
)
def test_indent_dan_tab_stop_paragraf(
    tmp_path: Path, text: str, left: str
) -> None:
    source = build_fixture(tmp_path / "source.docx")
    output = tmp_path / "out.docx"

    run_tool(source, output)

    paragraph = paragraph_by_text(document_root(output), text)
    assert indentation(paragraph) == {"left": left, "hanging": "720"}
    assert tabs(paragraph) == [{"val": "left", "pos": left}]


@pytest.mark.parametrize(
    ("num_id", "ilvl", "left"),
    [
        ("101", "0", "720"),
        ("102", "0", "720"),
        ("103", "0", "720"),
        ("102", "1", "1440"),
        ("103", "1", "1440"),
    ],
)
def test_indent_dan_tab_stop_level_numbering(
    tmp_path: Path, num_id: str, ilvl: str, left: str
) -> None:
    source = build_fixture(tmp_path / "source.docx")
    output = tmp_path / "out.docx"

    run_tool(source, output)

    level = level_for(numbering_root(output), num_id, ilvl)
    assert indentation(level) == {"left": left, "hanging": "720"}
    assert tabs(level) == [{"val": "left", "pos": left}]
    assert level.xpath("./w:suff/@w:val", namespaces=NS) == ["tab"]


# ---------------------------------------------------------------------------
# 3. Idempoten


def test_idempoten(tmp_path: Path) -> None:
    source = build_fixture(tmp_path / "source.docx")
    first = tmp_path / "first.docx"
    second = tmp_path / "second.docx"

    run_tool(source, first)
    report = run_tool(first, second)

    assert report.paragraphs_changed == 0
    assert report.numbering_levels_changed == 0
    assert report.bold_removed == 0
    assert part_bytes(first, DOCUMENT_PART) == part_bytes(second, DOCUMENT_PART)
    assert part_bytes(first, NUMBERING_PART) == part_bytes(second, NUMBERING_PART)


# ---------------------------------------------------------------------------
# 4. Paragraf non-list tidak berubah


def test_paragraf_non_list_tidak_berubah(tmp_path: Path) -> None:
    source = build_fixture(tmp_path / "source.docx")
    output = tmp_path / "out.docx"

    before = document_root(source)
    run_tool(source, output)
    after = document_root(output)

    def plain_paragraphs(root: etree._Element) -> list[bytes]:
        result = []
        for paragraph in root.xpath("//w:body/w:p", namespaces=NS):
            if paragraph.xpath("./w:pPr/w:numPr", namespaces=NS):
                continue
            result.append(etree.tostring(paragraph))
        return result

    assert plain_paragraphs(before) == plain_paragraphs(after)


# ---------------------------------------------------------------------------
# 5. Bold


def test_bold_list_dihapus_bold_non_list_dipertahankan(tmp_path: Path) -> None:
    source = build_fixture(tmp_path / "source.docx")
    output = tmp_path / "out.docx"

    run_tool(source, output)

    document = document_root(output)
    list_paragraph = paragraph_by_text(document, "Langkah tebal")
    normal_paragraph = paragraph_by_text(document, "Paragraf non-list tebal")

    assert not list_paragraph.xpath(".//w:rPr/w:b | .//w:rPr/w:bCs", namespaces=NS)
    assert normal_paragraph.xpath(".//w:rPr/w:b", namespaces=NS)

    level = level_for(numbering_root(output), "103")
    assert not level.xpath("./w:rPr/w:b | ./w:rPr/w:bCs", namespaces=NS)


def test_bullet_dan_numid_nol_tidak_disentuh(tmp_path: Path) -> None:
    source = build_fixture(tmp_path / "source.docx")
    output = tmp_path / "out.docx"

    run_tool(source, output)

    document = document_root(output)
    bullet = paragraph_by_text(document, "Butir bullet tebal")
    disabled = paragraph_by_text(document, "Bukan list (numId 0)")

    assert indentation(bullet) == {}
    assert tabs(bullet) == []
    assert bullet.xpath(".//w:rPr/w:b", namespaces=NS)
    assert indentation(disabled) == {}
    assert disabled.xpath(".//w:rPr/w:b", namespaces=NS)

    bullet_level = level_for(numbering_root(output), "104")
    assert indentation(bullet_level) == {"left": "720", "hanging": "360"}
    assert tabs(bullet_level) == []
    assert bullet_level.xpath("./w:suff", namespaces=NS) == []


def test_list_yang_sudah_benar_tidak_diubah(tmp_path: Path) -> None:
    source = build_fixture(tmp_path / "source.docx")
    output = tmp_path / "out.docx"

    before = etree.tostring(paragraph_by_text(document_root(source), "List sudah benar"))
    run_tool(source, output)
    after = etree.tostring(paragraph_by_text(document_root(output), "List sudah benar"))

    assert before == after


def test_indent_lama_ditimpa_tanpa_atribut_konflik(tmp_path: Path) -> None:
    source = build_fixture(tmp_path / "source.docx")
    output = tmp_path / "out.docx"

    run_tool(source, output)

    paragraph = paragraph_by_text(document_root(output), "Langkah indent lama")
    assert indentation(paragraph) == {"left": "720", "hanging": "720"}
    assert tabs(paragraph) == [{"val": "left", "pos": "720"}]


# ---------------------------------------------------------------------------
# 6. Integrasi Pandoc: pemetaan tiga sintaks Markdown


def _pandoc() -> str:
    candidates = [os.environ.get("PANDOC"), shutil.which("pandoc")]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(str(Path(local_appdata) / "Pandoc" / "pandoc.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    pytest.skip("pandoc tidak tersedia")


@pytest.mark.integration
def test_pandoc_memetakan_tiga_format_markdown(tmp_path: Path) -> None:
    source = tmp_path / "probe.md"
    source.write_text(
        "# Probe\n\n"
        "1. Langkah satu\n"
        "2. Langkah dua\n\n"
        "a. Enumerasi satu\n"
        "b. Enumerasi dua\n\n"
        "a) Sub-poin satu\n"
        "b) Sub-poin dua\n",
        encoding="utf-8",
    )
    docx = tmp_path / "probe.docx"
    output = tmp_path / "probe-fixed.docx"

    subprocess.run(
        [_pandoc(), str(source), "-o", str(docx)],
        check=True,
        cwd=tmp_path,
    )
    run_tool(docx, output)

    document = document_root(output)
    numbering = numbering_root(output)
    expectations = {
        "Langkah satu": ("decimal", "%1."),
        "Enumerasi satu": ("lowerLetter", "%1."),
        "Sub-poin satu": ("lowerLetter", "%1)"),
    }
    for text, (fmt, lvl_text) in expectations.items():
        reference = numbering_reference(paragraph_by_text(document, text))
        assert reference is not None
        num_id, ilvl = reference
        level = level_for(numbering, num_id, ilvl)
        assert level.xpath("./w:numFmt/@w:val", namespaces=NS) == [fmt]
        assert level.xpath("./w:lvlText/@w:val", namespaces=NS) == [lvl_text]

        paragraph = paragraph_by_text(document, text)
        assert indentation(paragraph) == {"left": "720", "hanging": "720"}
        assert tabs(paragraph) == [{"val": "left", "pos": "720"}]
