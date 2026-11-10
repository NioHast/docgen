"""Tes unit stage ``numbering``: format dipertahankan, indent/tab, bold."""

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from docgen.docx import DOCUMENT_PART, DocumentPackage
from docgen.pipeline import BuildOptions, StageName
from docgen.stages import numbering

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_R = qn("w:r")
W_RPR = qn("w:rPr")
W_B = qn("w:b")
W_BCS = qn("w:bCs")
W_VAL = qn("w:val")
W_TABS = qn("w:tabs")
W_TAB = qn("w:tab")
W_POS = qn("w:pos")
W_IND = qn("w:ind")
W_LEFT = qn("w:left")
W_RIGHT = qn("w:right")
W_HANGING = qn("w:hanging")
W_NUMPR = qn("w:numPr")
W_NUMID = qn("w:numId")
W_ILVL = qn("w:ilvl")

NUMBERING_PART = "word/numbering.xml"

TEXTS = {
    "decimal": "Langkah satu",
    "lower_dot": "Enumerasi satu",
    "lower_paren": "Sub-poin satu",
    "bullet": "Butir bullet",
    "disabled": "Bukan list",
    "plain": "Paragraf non-list",
    "nested": "Langkah bersarang",
}


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def _set_numbering(paragraph, num_id: int, ilvl: int = 0) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    numpr = OxmlElement("w:numPr")
    level = OxmlElement("w:ilvl")
    level.set(W_VAL, str(ilvl))
    number = OxmlElement("w:numId")
    number.set(W_VAL, str(num_id))
    numpr.append(level)
    numpr.append(number)
    ppr.append(numpr)


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
        bold = "<w:rPr><w:b/><w:bCs/></w:rPr>" if level_bold and ilvl == 0 else ""
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
        '<w:multiLevelType w:val="hybridMultilevel"/>' + "".join(levels) + "</w:abstractNum>"
    )


def _numbering_xml() -> bytes:
    body = (
        _abstract_num(10, "decimal", ".")
        + _abstract_num(11, "lowerLetter", ".")
        + _abstract_num(12, "lowerLetter", ")", level_bold=True)
        + _abstract_num(13, "bullet", " ")
        + '<w:num w:numId="1"><w:abstractNumId w:val="10"/></w:num>'
        + '<w:num w:numId="2"><w:abstractNumId w:val="11"/></w:num>'
        + '<w:num w:numId="3"><w:abstractNumId w:val="12"/></w:num>'
        + '<w:num w:numId="4"><w:abstractNumId w:val="13"/></w:num>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:numbering xmlns:w="{W_NS}">{body}</w:numbering>'
    ).encode()


def _replace_part(path: Path, part: str, data: bytes) -> None:
    with zipfile.ZipFile(path, "r") as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    with zipfile.ZipFile(path, "w") as target:
        for info, payload in entries:
            target.writestr(info, data if info.filename == part else payload)


def build_numbering_fixture(path: Path) -> Path:
    document = Document()

    def add(text: str, num_id: int, ilvl: int = 0, *, bold: bool = False):
        paragraph = document.add_paragraph()
        run = paragraph.add_run(text)
        if bold:
            run.bold = True
        _set_numbering(paragraph, num_id, ilvl)
        return paragraph

    add(TEXTS["decimal"], 1)
    add(TEXTS["decimal"] + " dua", 1)
    add(TEXTS["lower_dot"], 2)
    add(TEXTS["lower_paren"], 3)
    add(TEXTS["bullet"], 4, bold=True)
    add(TEXTS["nested"], 1, 1)
    add(TEXTS["decimal"] + " tebal", 1, bold=True)

    disabled = document.add_paragraph(TEXTS["disabled"])
    disabled.runs[0].bold = True
    _set_numbering(disabled, 0)

    plain = document.add_paragraph(TEXTS["plain"])
    plain.runs[0].bold = True

    document.save(path)
    _replace_part(path, NUMBERING_PART, _numbering_xml())
    return path


@pytest.fixture()
def numbering_docx(tmp_path: Path) -> Path:
    return build_numbering_fixture(tmp_path / "numbering.docx")


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------


def _paragraph_by_text(package: DocumentPackage, marker: str):
    body = package.xml(DOCUMENT_PART).find(qn("w:body"))
    assert body is not None
    matches = [paragraph for paragraph in body.iter(W_P) if "".join(paragraph.itertext()) == marker]
    assert len(matches) == 1, f"paragraf {marker!r} tidak tunggal"
    return matches[0]


def _numbering_root(package: DocumentPackage):
    return package.xml(NUMBERING_PART)


def _level_for(package: DocumentPackage, num_id: str, ilvl: str = "0"):
    root = _numbering_root(package)
    abstract_ids = root.xpath(
        f'//w:num[@w:numId="{num_id}"]/w:abstractNumId/@w:val',
        namespaces=NS,
    )
    assert abstract_ids, f"numId {num_id} tidak ditemukan"
    levels = root.xpath(
        f'//w:abstractNum[@w:abstractNumId="{abstract_ids[0]}"]/w:lvl[@w:ilvl="{ilvl}"]',
        namespaces=NS,
    )
    assert levels
    return levels[0]


def _indentation(element) -> dict[str, str]:
    nodes = element.xpath("./w:pPr/w:ind", namespaces=NS)
    if not nodes:
        return {}
    return {key.split("}")[-1]: value for key, value in nodes[0].attrib.items()}


def _tabs(element) -> list[dict[str, str]]:
    return [
        {key.split("}")[-1]: value for key, value in tab.attrib.items()}
        for tab in element.xpath("./w:pPr/w:tabs/w:tab", namespaces=NS)
    ]


def _has_bold(element) -> bool:
    return bool(element.xpath(".//w:rPr/w:b | .//w:rPr/w:bCs", namespaces=NS))


def _save(package: DocumentPackage, path: Path) -> Path:
    package.save(path)
    return path


# ---------------------------------------------------------------------------
# Tes
# ---------------------------------------------------------------------------


def test_format_numbering_dipertahankan(numbering_docx: Path, tmp_path: Path) -> None:
    package = DocumentPackage.load(numbering_docx)
    before_formats = {}
    for num_id in ("1", "2", "3"):
        level = _level_for(package, num_id)
        before_formats[num_id] = (
            level.find(qn("w:numFmt")).get(W_VAL),
            level.find(qn("w:lvlText")).get(W_VAL),
        )

    report = numbering.format_numbering(package)
    assert report.list_paragraphs >= 6
    assert report.numbering_levels >= 1
    result = DocumentPackage.load(_save(package, tmp_path / "out.docx"))

    for num_id, expected in before_formats.items():
        level = _level_for(result, num_id)
        assert (
            level.find(qn("w:numFmt")).get(W_VAL),
            level.find(qn("w:lvlText")).get(W_VAL),
        ) == expected

    assert _indentation(_paragraph_by_text(result, TEXTS["decimal"])) == {
        "left": "720",
        "hanging": "720",
    }
    assert _tabs(_paragraph_by_text(result, TEXTS["decimal"])) == [{"val": "left", "pos": "720"}]
    assert _indentation(_paragraph_by_text(result, TEXTS["decimal"] + " dua")) == {
        "left": "720",
        "hanging": "720",
    }

    level = _level_for(result, "1")
    assert _indentation(level) == {"left": "720", "hanging": "720"}
    assert _tabs(level) == [{"val": "left", "pos": "720"}]
    assert level.xpath("./w:suff/@w:val", namespaces=NS) == ["tab"]


def test_level_dua_dan_bold(numbering_docx: Path, tmp_path: Path) -> None:
    package = DocumentPackage.load(numbering_docx)
    numbering.format_numbering(package)
    result = DocumentPackage.load(_save(package, tmp_path / "out.docx"))

    # Periksa langsung semua paragraf dengan numPr ilvl=1.
    body = result.xml(DOCUMENT_PART).find(qn("w:body"))
    nested_paragraphs = [
        paragraph
        for paragraph in body.iter(W_P)
        if paragraph.xpath("./w:pPr/w:numPr/w:ilvl/@w:val", namespaces=NS) == ["1"]
    ]
    assert nested_paragraphs
    assert _indentation(nested_paragraphs[0]) == {"left": "1440", "hanging": "720"}
    assert _tabs(nested_paragraphs[0]) == [{"val": "left", "pos": "1440"}]

    bold = _paragraph_by_text(result, TEXTS["decimal"] + " tebal")
    assert not _has_bold(bold)
    assert _has_bold(_paragraph_by_text(result, TEXTS["bullet"]))
    assert _has_bold(_paragraph_by_text(result, TEXTS["plain"]))
    assert _has_bold(_paragraph_by_text(result, TEXTS["disabled"]))

    # Level yang dipakai kehilangan bold; level bullet tidak disentuh.
    assert not _has_bold(_level_for(result, "3"))
    assert _level_for(result, "4").xpath("./w:suff", namespaces=NS) == []


def test_idempoten_part_identik_dan_stage(numbering_docx: Path, tmp_path: Path) -> None:
    before = {}
    with zipfile.ZipFile(numbering_docx) as archive:
        before = {name: archive.read(name) for name in archive.namelist()}

    package = DocumentPackage.load(numbering_docx)
    numbering.format_numbering(package)
    first = _save(package, tmp_path / "first.docx")
    with zipfile.ZipFile(first) as archive:
        after = {name: archive.read(name) for name in archive.namelist()}
    assert before.keys() == after.keys()
    for name in before:
        if name not in {DOCUMENT_PART, NUMBERING_PART}:
            assert before[name] == after[name], name

    second_package = DocumentPackage.load(first)
    report = numbering.format_numbering(second_package)
    assert report.paragraphs_changed == 0
    assert report.numbering_levels_changed == 0
    assert report.bold_removed == 0
    second = _save(second_package, tmp_path / "second.docx")
    assert DocumentPackage.load(first).part(DOCUMENT_PART) == DocumentPackage.load(second).part(
        DOCUMENT_PART
    )
    assert DocumentPackage.load(first).part(NUMBERING_PART) == DocumentPackage.load(second).part(
        NUMBERING_PART
    )

    assert numbering.NumberingStage.order == 100
    assert numbering.NumberingStage.name is StageName.NUMBERING
    ctx = SimpleNamespace(package=DocumentPackage.load(second), options=BuildOptions(), format=None)
    assert numbering.NumberingStage().run(ctx).changed is False
