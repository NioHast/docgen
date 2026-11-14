"""Tes unit helper kanonis paragraf DOCX."""

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from autooffice.docx.package import (
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    PACKAGE_RELS_PART,
    REL_TYPE_OFFICE_DOCUMENT,
    DocumentPackage,
    parse_xml,
    qn,
)
from autooffice.docx.package.paragraphs import (
    ParagraphError,
    body_children,
    document_body,
    heading_level,
    int_attribute,
    paragraph_style_id,
    paragraph_text,
    remove_direct_children,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
RELS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"


# ---------------------------------------------------------------------------
# Fixture XML dan package minimal
# ---------------------------------------------------------------------------


def _document(body: str) -> etree._Element:
    data = f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'.encode()
    return parse_xml(data)


def _paragraph(inner: str = "", *, style: str | None = None) -> etree._Element:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style is not None else ""
    root = _document(f"<w:p>{ppr}{inner}</w:p>")
    paragraph = root.find(f".//{qn('w:p')}")
    assert paragraph is not None
    return paragraph


def _content_types() -> bytes:
    return (
        f'<Types xmlns="{CT_NS}">'
        f'<Default Extension="rels" ContentType="{RELS_CONTENT_TYPE}"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{DOCUMENT_PART}" ContentType="{DOCUMENT_CONTENT_TYPE}"/>'
        "</Types>"
    ).encode()


def _package_rels() -> bytes:
    return (
        f'<Relationships xmlns="{PR_NS}">'
        f'<Relationship Id="rId1" Type="{REL_TYPE_OFFICE_DOCUMENT}" Target="{DOCUMENT_PART}"/>'
        "</Relationships>"
    ).encode()


def _write_parts(
    tmp_path: Path,
    *,
    document: bytes | None,
    filename: str = "paragraphs.docx",
) -> Path:
    path = tmp_path / filename
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(CONTENT_TYPES_PART, _content_types())
        archive.writestr(PACKAGE_RELS_PART, _package_rels())
        if document is not None:
            archive.writestr(DOCUMENT_PART, document)
    return path


def _write_package(tmp_path: Path, body: str) -> Path:
    document = (f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>').encode()
    return _write_parts(tmp_path, document=document)


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------


def test_document_body_from_minimal_package(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        "<w:p><w:r><w:t>Halo</w:t></w:r></w:p><w:sectPr/>",
    )
    package = DocumentPackage.load(path)

    body = document_body(package)
    assert body.tag == qn("w:body")
    assert paragraph_text(body.find(qn("w:p"))) == "Halo"

    with pytest.raises(ParagraphError):
        document_body(etree.Element(qn("w:document")))  # type: ignore[arg-type]


def test_document_body_requires_document_part(tmp_path: Path) -> None:
    package = DocumentPackage.load(
        _write_parts(tmp_path, document=None, filename="tanpa-document.docx"),
        validate=False,
    )

    with pytest.raises(ParagraphError) as caught:
        document_body(package)

    assert caught.value.code == "PARAGRAPH"


def test_document_body_requires_body_element(tmp_path: Path) -> None:
    document = f'<w:document xmlns:w="{W_NS}"/>'.encode()
    package = DocumentPackage.load(
        _write_parts(tmp_path, document=document, filename="tanpa-body.docx")
    )

    with pytest.raises(ParagraphError) as caught:
        document_body(package)

    assert caught.value.code == "PARAGRAPH"


def test_body_children_skips_comments_and_processing_instructions() -> None:
    body = etree.Element(qn("w:body"))
    paragraph = etree.SubElement(body, qn("w:p"))
    table = etree.SubElement(body, qn("w:tbl"))
    body.append(etree.Comment("komentar"))
    body.append(etree.ProcessingInstruction("target", "data"))
    section = etree.SubElement(body, qn("w:sectPr"))

    assert body_children(body) == [paragraph, table, section]


# ---------------------------------------------------------------------------
# Style dan level
# ---------------------------------------------------------------------------


def test_paragraph_style_id() -> None:
    assert paragraph_style_id(_paragraph("<w:r><w:t>x</w:t></w:r>")) is None

    without_style = _document("<w:p><w:pPr><w:keepNext/></w:pPr></w:p>")
    assert paragraph_style_id(without_style.find(f".//{qn('w:p')}")) is None

    assert paragraph_style_id(_paragraph(style="Heading1")) == "Heading1"

    without_value = parse_xml(
        f'<w:document xmlns:w="{W_NS}"><w:body><w:p>'
        "<w:pPr><w:pStyle/></w:pPr></w:p></w:body></w:document>".encode()
    )
    assert paragraph_style_id(without_value.find(f".//{qn('w:p')}")) is None


def test_heading_level() -> None:
    assert heading_level(_paragraph(style="Heading1")) == 1
    assert heading_level(_paragraph(style="Heading2")) == 2
    assert heading_level(_paragraph(style="heading 3")) == 3
    assert heading_level(_paragraph(style="BodyText")) is None
    assert heading_level(_paragraph(style="NonHeading")) is None
    assert heading_level(_paragraph()) is None
    assert heading_level(_paragraph(style="ChapterTitle")) is None


# ---------------------------------------------------------------------------
# Teks
# ---------------------------------------------------------------------------


def test_paragraph_text_includes_hyperlink_nested_run_and_tab() -> None:
    paragraph = _paragraph(
        "<w:r><w:t>A</w:t><w:tab/><w:br/><w:t>B</w:t></w:r>"
        "<w:hyperlink><w:r><w:t>link</w:t></w:r></w:hyperlink>"
        "<w:sdt><w:sdtContent><w:r><w:t>nested</w:t></w:r></w:sdtContent></w:sdt>"
        "<w:r><w:instrText> PAGE </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>7</w:t></w:r>"
        "<w:del><w:r><w:delText>deleted</w:delText></w:r></w:del>"
        "<w:r><w:drawing><w:txbxContent>"
        "<w:p><w:r><w:t>box</w:t></w:r></w:p>"
        "</w:txbxContent></w:drawing></w:r>"
    )

    assert paragraph_text(paragraph) == "A\t\nBlinknested7"


def test_paragraph_text_includes_ptab_and_no_break_hyphen() -> None:
    paragraph = _paragraph(
        "<w:r><w:t>A</w:t><w:ptab/><w:t>B</w:t><w:noBreakHyphen/><w:t>C</w:t></w:r>"
    )

    assert paragraph_text(paragraph) == "A\tB\u2011C"


def test_paragraph_text_always_ignores_instr_text() -> None:
    paragraph = _paragraph(
        "<w:r><w:t>Nilai: </w:t><w:instrText> PAGE </w:instrText></w:r><w:r><w:t>7</w:t></w:r>"
    )

    assert paragraph_text(paragraph) == "Nilai: 7"
    assert "PAGE" not in paragraph_text(paragraph)


def test_paragraph_text_skips_nested_paragraph() -> None:
    paragraph = _paragraph("<w:r><w:t>luar</w:t></w:r><w:p><w:r><w:t>dalam</w:t></w:r></w:p>")

    assert paragraph_text(paragraph) == "luar"


# ---------------------------------------------------------------------------
# Mutasi dan atribut
# ---------------------------------------------------------------------------


def test_remove_direct_children_only_removes_direct_children() -> None:
    parent = etree.Element(qn("w:pPr"))
    etree.SubElement(parent, qn("w:b"))
    etree.SubElement(parent, qn("w:b"))
    run = etree.SubElement(parent, qn("w:r"))
    nested = etree.SubElement(run, qn("w:b"))

    assert remove_direct_children(parent, qn("w:b")) == 2
    assert parent.findall(qn("w:b")) == []
    assert run.find(qn("w:b")) is nested


def test_int_attribute() -> None:
    element = etree.Element(qn("w:pgSz"))
    element.set(qn("w:w"), "11906")

    assert int_attribute(element, qn("w:w")) == 11906
    assert int_attribute(element, qn("w:h")) is None

    element.set(qn("w:h"), "bukan-angka")
    assert int_attribute(element, qn("w:h")) is None
