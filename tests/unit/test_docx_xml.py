"""Tes unit fondasi XML DOCX."""

import re

import pytest
from lxml import etree

from docgen.docx import (
    PPR_ORDER,
    RPR_ORDER,
    XmlError,
    canonicalize_xml,
    ensure_ppr,
    ensure_rpr,
    ensure_tblpr,
    ensure_tcpr,
    get_or_add,
    insert_ordered,
    is_on,
    iter_paragraphs,
    iter_runs,
    paragraph_text,
    parse_xml,
    qn,
    run_text,
    serialize_xml,
    sha256_c14n,
)
from docgen.docx.names import (
    is_caption_style,
    is_code_style,
    is_cover_style,
    is_heading_style,
    is_style,
    local_name,
    normalize_style_id,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _document(body: str) -> etree._Element:
    data = (
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}"><w:body>{body}</w:body></w:document>'
    ).encode()
    return parse_xml(data)


def _paragraph(body: str) -> etree._Element:
    root = _document(f"<w:p>{body}</w:p>")
    paragraph = root.find(f"{W}body/{W}p")
    assert paragraph is not None
    return paragraph


def test_qn_and_local_name() -> None:
    assert qn("w:p") == f"{W}p"
    assert qn("w:val") == f"{W}val"
    assert qn("r:id") == f"{{{R_NS}}}id"
    assert qn(f"{W}p") == f"{W}p"

    with pytest.raises(ValueError):
        qn("unknown:p")
    with pytest.raises(ValueError):
        qn("p")

    assert local_name(f"{W}p") == "p"
    assert local_name("w:p") == "p"
    assert local_name("p") == "p"
    assert local_name(None) == ""  # type: ignore[arg-type]


def test_style_name_helpers() -> None:
    assert normalize_style_id("Image Caption") == "imagecaption"
    assert normalize_style_id("image_caption") == "imagecaption"
    assert normalize_style_id("Image-Caption") == "imagecaption"

    assert is_style("Image Caption", "image_caption", "ImageCaption")
    assert is_style("ImageCaption", "Image Caption")
    assert not is_style(None, "ImageCaption")

    assert is_heading_style("Heading1")
    assert is_heading_style("heading 3")
    assert not is_heading_style("Heading10")
    assert not is_heading_style("TOCHeading")

    assert is_caption_style("ImageCaption")
    assert is_caption_style("table_caption")
    assert is_caption_style("Caption")
    assert not is_caption_style("FigureCaption")

    assert is_code_style("SourceCode")
    assert is_code_style("HTMLCode1")
    assert not is_code_style("BodyText")

    assert is_cover_style("CoverTitle")
    assert is_cover_style("cover_course")
    assert not is_cover_style("Title")


def test_parse_and_serialize_preserve_comments_pi_and_space() -> None:
    data = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:p xmlns:w="{W_NS}"><!-- komentar --><?pi data?>'
        '<w:r><w:t xml:space="preserve"> a </w:t></w:r></w:p>'
    ).encode()
    root = parse_xml(data)

    output = serialize_xml(root)
    assert output.startswith(b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n')
    assert b"<!-- komentar -->" in output
    assert b"<?pi data?>" in output
    assert b"> a </w:t>" in output
    assert b"\r" not in output

    assert not serialize_xml(root, xml_declaration=False).startswith(b"<?xml")

    reparsed = parse_xml(serialize_xml(root))
    assert canonicalize_xml(reparsed) == canonicalize_xml(root)


def test_parse_xml_rejects_malformed_and_entities() -> None:
    with pytest.raises(XmlError):
        parse_xml(b"<w:p>")

    entity_document = (f'<!DOCTYPE w:p [<!ENTITY e "x">]><w:p xmlns:w="{W_NS}">&e;</w:p>').encode()
    with pytest.raises(XmlError):
        parse_xml(entity_document)

    with pytest.raises(XmlError):
        parse_xml(b"")


def test_canonicalize_docx_profile_removes_word_noise() -> None:
    noisy = (
        f'<w:p xmlns:w="{W_NS}" w:rsidR="00AA" w:rsidRPr="00BB">'
        '<w:proofErr w:type="spellStart"/>'
        "<w:r><w:t>x</w:t></w:r>"
        "<w:lastRenderedPageBreak/>"
        "</w:p>"
    ).encode()
    clean = f'<w:p xmlns:w="{W_NS}"><w:r><w:t>x</w:t></w:r></w:p>'.encode()

    assert canonicalize_xml(noisy) == canonicalize_xml(clean)
    assert canonicalize_xml(noisy, profile="c14n") != canonicalize_xml(clean, profile="c14n")

    canonical = canonicalize_xml(noisy)
    assert b"proofErr" not in canonical
    assert b"lastRenderedPageBreak" not in canonical
    assert b"<!--" not in canonical
    assert canonical.startswith(b"<w:p ")

    root = parse_xml(noisy)
    canonicalize_xml(root)
    assert root.get(f"{W}rsidR") == "00AA"
    assert root.find(f"{W}proofErr") is not None

    with pytest.raises(ValueError):
        canonicalize_xml(noisy, profile="invalid")  # type: ignore[arg-type]


def test_canonicalize_is_deterministic_and_sha256_is_lowercase_hex() -> None:
    data = f'<w:p xmlns:w="{W_NS}"><w:r><w:t>x</w:t></w:r></w:p>'.encode()
    first = canonicalize_xml(data)
    second = canonicalize_xml(data)
    assert first == second

    digest = sha256_c14n(data)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)

    # Komentar tidak memengaruhi canonical C14N tanpa komentar.
    with_comment = (f'<w:p xmlns:w="{W_NS}"><!--x--><w:r><w:t>x</w:t></w:r></w:p>').encode()
    assert sha256_c14n(with_comment) == digest


def test_iter_paragraphs_order_tables_and_textbox() -> None:
    body = (
        "<w:p><w:r><w:t>one</w:t></w:r></w:p>"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>two</w:t></w:r></w:p>"
        "</w:tc></w:tr></w:tbl>"
        "<w:p><w:r><w:drawing><w:txbxContent>"
        "<w:p><w:r><w:t>box</w:t></w:r></w:p>"
        "</w:txbxContent></w:drawing></w:r></w:p>"
    )
    root = _document(body)
    body_element = root.find(f"{W}body")
    assert body_element is not None

    all_paragraphs = list(iter_paragraphs(body_element))
    assert [paragraph_text(p) for p in all_paragraphs] == ["one", "two", ""]

    without_tables = list(iter_paragraphs(body_element, include_tables=False))
    assert [paragraph_text(p) for p in without_tables] == ["one", ""]

    table = body_element.find(f"{W}tbl")
    assert table is not None
    assert list(iter_paragraphs(table, include_tables=False)) == []
    assert [paragraph_text(p) for p in iter_paragraphs(table)] == ["two"]


def test_paragraph_text_and_run_text() -> None:
    paragraph = _paragraph(
        "<w:r><w:t>A</w:t><w:tab/><w:br/><w:t>B</w:t></w:r>"
        "<w:hyperlink><w:r><w:t>link</w:t></w:r></w:hyperlink>"
        "<w:r><w:instrText> PAGE </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>7</w:t></w:r>"
        "<w:del><w:r><w:delText>deleted</w:delText></w:r></w:del>"
        "<w:r><w:drawing><w:txbxContent>"
        "<w:p><w:r><w:t>box</w:t></w:r></w:p>"
        "</w:txbxContent></w:drawing></w:r>"
    )

    assert paragraph_text(paragraph) == "A\t\nBlink7"
    assert "PAGE" not in paragraph_text(paragraph)

    runs = list(iter_runs(paragraph))
    assert run_text(runs[0]) == "A\t\nB"
    assert all("box" not in run_text(run) for run in runs)


def test_ensure_containers_and_order() -> None:
    paragraph = etree.Element(f"{W}p")
    run = etree.SubElement(paragraph, f"{W}r")

    ppr = ensure_ppr(paragraph)
    assert paragraph[0] is ppr
    assert ensure_ppr(paragraph) is ppr
    assert run.getparent() is paragraph

    run2 = etree.Element(f"{W}r")
    rpr = ensure_rpr(run2)
    assert rpr.tag == f"{W}rPr"
    assert ensure_rpr(run2) is rpr
    assert run2[0] is rpr

    existing = etree.Element(f"{W}p")
    existing.append(etree.Element(f"{W}r"))
    old_ppr = etree.SubElement(existing, f"{W}pPr")
    assert ensure_ppr(existing) is old_ppr
    assert existing[0] is old_ppr

    table = etree.Element(f"{W}tbl")
    assert ensure_tblpr(table).tag == f"{W}tblPr"
    assert table[0].tag == f"{W}tblPr"
    cell = etree.Element(f"{W}tc")
    assert ensure_tcpr(cell).tag == f"{W}tcPr"
    assert cell[0].tag == f"{W}tcPr"

    with pytest.raises(XmlError):
        ensure_ppr(etree.Element(f"{W}r"))


def test_get_or_add_and_insert_ordered() -> None:
    ppr = etree.Element(f"{W}pPr")
    pstyle = etree.SubElement(ppr, f"{W}pStyle")
    spacing = etree.SubElement(ppr, f"{W}spacing")
    rpr = etree.SubElement(ppr, f"{W}rPr")

    jc = get_or_add(ppr, "w:jc", PPR_ORDER)
    assert list(ppr) == [pstyle, spacing, jc, rpr]
    assert get_or_add(ppr, "w:jc", PPR_ORDER) is jc
    assert sum(child.tag == f"{W}jc" for child in ppr) == 1

    unknown = get_or_add(ppr, "w:foo", PPR_ORDER)
    assert ppr[-1] is unknown

    run = etree.Element(f"{W}r")
    rpr = ensure_rpr(run)
    color = etree.Element(f"{W}color")
    insert_ordered(rpr, color, RPR_ORDER)
    font = etree.Element(f"{W}rFonts")
    insert_ordered(rpr, font, RPR_ORDER)
    assert [child.tag for child in rpr] == [f"{W}rFonts", f"{W}color"]


def test_is_on() -> None:
    def toggle(value: str | None = None) -> etree._Element:
        element = etree.Element(f"{W}b")
        if value is not None:
            element.set(f"{W}val", value)
        return element

    assert is_on(None) is False
    assert is_on(toggle()) is True
    assert is_on(toggle("1")) is True
    assert is_on(toggle("true")) is True
    assert is_on(toggle("on")) is True
    assert is_on(toggle("0")) is False
    assert is_on(toggle("false")) is False
    assert is_on(toggle("OFF")) is False
