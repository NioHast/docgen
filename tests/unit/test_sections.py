"""Tes unit section DOCX dan stage ``sections``."""

import html
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from docgen.docx.fields import FieldKind, iter_fields
from docgen.docx.heading_numbering import (
    NumberingSpec,
    apply_heading_numbering,
    heading_bookmark_name,
    heading_text,
    is_unnumbered,
    iter_headings,
)
from docgen.docx.package import (
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    PACKAGE_RELS_PART,
    REL_TYPE_OFFICE_DOCUMENT,
    REL_TYPE_STYLES,
    DocumentPackage,
)
from docgen.docx.paragraphs import paragraph_text
from docgen.docx.sections import (
    FOOTER_CONTENT_TYPE,
    HEADER_CONTENT_TYPE,
    add_section_break,
    clear_header_footer_references,
    create_header_footer_part,
    iter_sections,
    remove_empty_sections,
    remove_unused_header_footer_parts,
    section_at,
    section_header_footer,
    set_header_footer_reference,
    set_margins,
    set_page_number_format,
    set_page_size,
    set_section_type,
    set_title_page,
)
from docgen.docx.xml import qn, sha256_c14n
from docgen.errors import StageError
from docgen.pipeline import StageName
from docgen.stages.sections import SectionsError, SectionsStage

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "fixtures" / "golden" / "laporan-baseline.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

RELS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"
DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
STYLES_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"

STYLES_XML = (
    f'<w:styles xmlns:w="{W_NS}">'
    '<w:style w:type="paragraph" w:styleId="Normal">'
    '<w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1">'
    '<w:name w:val="heading 1"/></w:style>'
    "</w:styles>"
).encode()


# ---------------------------------------------------------------------------
# Helper package minimal
# ---------------------------------------------------------------------------


def _content_types(extra: str = "") -> bytes:
    return (
        f'<Types xmlns="{CT_NS}">'
        f'<Default Extension="rels" ContentType="{RELS_CONTENT_TYPE}"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{DOCUMENT_PART}" '
        f'ContentType="{DOCUMENT_CONTENT_TYPE}"/>'
        '<Override PartName="/word/styles.xml" '
        f'ContentType="{STYLES_CONTENT_TYPE}"/>'
        f"{extra}</Types>"
    ).encode()


def _package_rels() -> bytes:
    return (
        f'<Relationships xmlns="{REL_NS}">'
        f'<Relationship Id="rId1" Type="{REL_TYPE_OFFICE_DOCUMENT}" '
        f'Target="{DOCUMENT_PART}"/>'
        "</Relationships>"
    ).encode()


def _document_rels() -> bytes:
    return (
        f'<Relationships xmlns="{REL_NS}">'
        f'<Relationship Id="rId2" Type="{REL_TYPE_STYLES}" '
        'Target="styles.xml"/>'
        "</Relationships>"
    ).encode()


def _paragraph(
    text: str = "",
    *,
    style: str | None = None,
    extra_ppr: str = "",
    extra_runs: str = "",
) -> str:
    ppr = ""
    if style or extra_ppr:
        ppr = "<w:pPr>"
        if style:
            ppr += f'<w:pStyle w:val="{html.escape(style)}"/>'
        ppr += extra_ppr + "</w:pPr>"
    runs = ""
    if text:
        runs += f"<w:r><w:t>{html.escape(text)}</w:t></w:r>"
    runs += extra_runs
    return f"<w:p>{ppr}{runs}</w:p>"


def _sect_pr(*inner: str) -> str:
    return "<w:sectPr>" + "".join(inner) + "</w:sectPr>"


def _break_paragraph(sect_pr: str) -> str:
    return f"<w:p><w:pPr>{sect_pr}</w:pPr></w:p>"


def _document(body: str, *, final_sect: str | None = None) -> bytes:
    sect = final_sect if final_sect is not None else _sect_pr()
    return (
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}"><w:body>{body}{sect}</w:body></w:document>'
    ).encode()


def _write_package(
    tmp_path: Path,
    document: bytes,
    *,
    extra_entries: dict[str, bytes] | None = None,
    content_type_extra: str = "",
    name: str = "test.docx",
) -> Path:
    path = tmp_path / name
    entries: dict[str, bytes] = {
        CONTENT_TYPES_PART: _content_types(content_type_extra),
        PACKAGE_RELS_PART: _package_rels(),
        DOCUMENT_PART: document,
        "word/_rels/document.xml.rels": _document_rels(),
        "word/styles.xml": STYLES_XML,
    }
    if extra_entries:
        entries.update(extra_entries)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry_name, data in entries.items():
            archive.writestr(entry_name, data)
    return path


def _fake_ctx(
    package: DocumentPackage,
    *,
    numbering: object | None = None,
) -> SimpleNamespace:
    structure = SimpleNamespace(numbering=numbering) if numbering is not None else SimpleNamespace()
    return SimpleNamespace(
        package=package,
        document=SimpleNamespace(),
        structure=structure,
        format=SimpleNamespace(
            page=SimpleNamespace(
                size="A4",
                orientation="portrait",
                margins=SimpleNamespace(
                    top=1440,
                    right=1440,
                    bottom=1440,
                    left=1440,
                ),
                header_distance=720,
                footer_distance=720,
                gutter=0,
            )
        ),
        options=SimpleNamespace(),
        dry_run=False,
    )


def _pg_num(section) -> tuple[str | None, str | None]:
    element = section.sect_pr.find(qn("w:pgNumType"))
    if element is None:
        return None, None
    return element.get(qn("w:fmt")), element.get(qn("w:start"))


def _sdt_gallery(root) -> list:
    return [
        node
        for node in root.iter(qn("w:sdt"))
        if (
            node.find(qn("w:sdtPr")) is not None
            and node.find(qn("w:sdtPr")).find(".//" + qn("w:docPartGallery")) is not None
            and node.find(qn("w:sdtPr")).find(".//" + qn("w:docPartGallery")).get(qn("w:val"))
            == "Table of Contents"
        )
    ]


def _has_page_break(paragraph) -> bool:
    for br in paragraph.iter(qn("w:br")):
        if (br.get(qn("w:type")) or "").casefold() == "page":
            return True
    ppr = paragraph.find(qn("w:pPr"))
    return ppr is not None and ppr.find(qn("w:pageBreakBefore")) is not None


# ---------------------------------------------------------------------------
# Golden baseline: section, Romawi/Arab, header/footer, blank page
# ---------------------------------------------------------------------------


def test_iter_sections_golden_baseline() -> None:
    package = DocumentPackage.load(GOLDEN)
    sections = iter_sections(package)
    assert len(sections) == 13
    assert [section.kind for section in sections] == [
        "cover",
        "front_matter",
        "front_matter",
        "front_matter",
        "front_matter",
        "front_matter",
        "body",
        "body",
        "body",
        "body",
        "body",
        "back_matter",
        "back_matter",
    ]
    assert [section.start for section in sections] == [
        0,
        13,
        20,
        27,
        32,
        38,
        50,
        67,
        81,
        104,
        125,
        133,
        141,
    ]


def test_iter_sections_first_section_without_paragraphs_is_cover(tmp_path: Path) -> None:
    document = _document("<w:tbl><w:tblPr/><w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl>")
    package = DocumentPackage.load(_write_package(tmp_path, document))

    sections = iter_sections(package)

    assert len(sections) == 1
    assert sections[0].kind == "cover"


def test_iter_sections_later_section_without_paragraphs_is_front_matter(
    tmp_path: Path,
) -> None:
    document = _document(
        _break_paragraph(_sect_pr()) + "<w:tbl><w:tblPr/><w:tr><w:tc><w:p/></w:tc></w:tr></w:tbl>"
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))

    sections = iter_sections(package)

    assert len(sections) == 2
    assert sections[0].kind == "front_matter"
    assert sections[1].kind == "front_matter"


def test_golden_page_numbers_lower_roman_then_decimal() -> None:
    package = DocumentPackage.load(GOLDEN)
    sections = iter_sections(package)
    assert _pg_num(sections[0]) == (None, None)

    front_matter = [section for section in sections if section.kind == "front_matter"]
    assert _pg_num(front_matter[0]) == ("lowerRoman", "1")
    for section in front_matter[1:]:
        assert _pg_num(section) == ("lowerRoman", None)

    body = [section for section in sections if section.kind == "body"]
    # Word menghapus fmt default; start=1 tetap menandai awal penomoran Arab.
    assert _pg_num(body[0]) == (None, "1")
    for section in body[1:]:
        assert _pg_num(section) == (None, None)


def test_golden_header_footer_per_section() -> None:
    package = DocumentPackage.load(GOLDEN)
    sections = iter_sections(package)
    cover_refs = section_header_footer(sections[0])
    assert cover_refs == section_header_footer(sections[0])
    assert cover_refs.header is None and cover_refs.footer is None
    front_refs = section_header_footer(sections[1])
    assert front_refs.header is None
    assert front_refs.footer is not None
    body_refs = section_header_footer(
        next(section for section in sections if section.kind == "body")
    )
    assert body_refs.header is not None
    assert body_refs.footer is not None
    assert body_refs.first_page_header is not None
    assert body_refs.first_page_footer is not None


def test_golden_no_blank_page_between_toc_and_bab_i() -> None:
    package = DocumentPackage.load(GOLDEN)
    root = package.xml(DOCUMENT_PART)
    body = root.find(qn("w:body"))
    children = [child for child in body if isinstance(child.tag, str)]
    sdts = _sdt_gallery(root)
    assert len(sdts) == 3
    toc_index = children.index(sdts[-1])

    bab_index = next(
        index
        for index, child in enumerate(children)
        if child.tag == qn("w:p")
        and paragraph_text(child).strip().startswith("BAB I")
        and child.find(qn("w:pPr")) is not None
        and child.find(qn("w:pPr")).find(qn("w:pStyle")) is not None
        and child.find(qn("w:pPr")).find(qn("w:pStyle")).get(qn("w:val")) == "Heading1"
    )
    assert bab_index > toc_index
    between = children[toc_index + 1 : bab_index]
    assert len(between) == 1
    carrier = between[0]
    assert carrier.find(qn("w:pPr")) is not None
    assert carrier.find(qn("w:pPr")).find(qn("w:sectPr")) is not None
    assert not _has_page_break(carrier)
    assert section_at(package, bab_index).start == bab_index
    assert section_at(package, bab_index).kind == "body"


# ---------------------------------------------------------------------------
# Mutator w:sectPr
# ---------------------------------------------------------------------------


def test_section_mutators_set_children_in_schema_order(tmp_path: Path) -> None:
    document = _document(_paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(_write_package(tmp_path, document))
    section = iter_sections(package)[0]

    set_margins(
        section,
        top=1440,
        right=1440,
        bottom=1440,
        left=1440,
        header=720,
        footer=720,
        gutter=0,
    )
    set_page_size(section, width=11906, height=16838, orientation="portrait")
    set_page_number_format(section, fmt="lowerRoman", start=1)
    set_title_page(section, True)
    set_section_type(section, "nextPage")

    tags = [child.tag.split("}")[-1] for child in section.sect_pr if isinstance(child.tag, str)]
    assert tags == [
        "type",
        "pgSz",
        "pgMar",
        "pgNumType",
        "titlePg",
    ]
    assert section.sect_pr.find(qn("w:pgSz")).get(qn("w:w")) == "11906"
    assert section.sect_pr.find(qn("w:pgMar")).get(qn("w:left")) == "1440"
    assert _pg_num(section) == ("lowerRoman", "1")
    assert section.sect_pr.find(qn("w:titlePg")) is not None
    assert section.sect_pr.find(qn("w:type")).get(qn("w:val")) == "nextPage"

    set_page_number_format(section, fmt="decimal")
    assert _pg_num(section) == ("decimal", None)


def test_add_section_break_idempotent(tmp_path: Path) -> None:
    document = _document(
        _paragraph("Sampul", style="CoverTitle") + _paragraph("BAB I", style="Heading1")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))
    root = package.xml(DOCUMENT_PART)
    body = root.find(qn("w:body"))
    heading = next(
        child
        for child in body
        if child.tag == qn("w:p") and paragraph_text(child).strip() == "BAB I"
    )

    first = add_section_break(package, before=heading, kind="nextPage")
    assert first.kind == "body"
    assert first.start == 2
    assert len(iter_sections(package)) == 2
    assert len(body.findall(".//" + qn("w:sectPr"))) == 2

    second = add_section_break(package, before=heading, kind="nextPage")
    assert second.start == first.start
    assert len(iter_sections(package)) == 2


def test_remove_empty_sections_removes_empty_break(tmp_path: Path) -> None:
    document = _document(
        _paragraph("Sampul", style="CoverTitle")
        + _break_paragraph(_sect_pr())
        + _break_paragraph(_sect_pr())
        + _paragraph("BAB I", style="Heading1")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))
    assert len(iter_sections(package)) == 3
    assert remove_empty_sections(package) == 1
    assert len(iter_sections(package)) == 2
    assert remove_empty_sections(package) == 0


def test_create_header_footer_part_sets_part_relationship_and_content_type(
    tmp_path: Path,
) -> None:
    document = _document(_paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(_write_package(tmp_path, document))
    section = iter_sections(package)[0]

    from lxml import etree

    header = etree.Element(qn("w:hdr"))
    etree.SubElement(header, qn("w:p"))
    rel_id = create_header_footer_part(package, kind="header", content=header)
    set_header_footer_reference(
        section,
        kind="header",
        reference_type="default",
        rel_id=rel_id,
    )

    assert package.has_part("word/header1.xml")
    assert package.part_info("word/header1.xml").content_type == HEADER_CONTENT_TYPE
    assert any(rel.rel_id == rel_id for rel in package.relationships(DOCUMENT_PART))
    assert section_header_footer(section).header == rel_id

    clear_header_footer_references(section)
    assert remove_unused_header_footer_parts(package) == 1
    assert not package.has_part("word/header1.xml")
    assert HEADER_CONTENT_TYPE
    assert FOOTER_CONTENT_TYPE


# ---------------------------------------------------------------------------
# Stage sections
# ---------------------------------------------------------------------------


def test_sections_stage_splits_cover_front_matter_and_chapters(
    tmp_path: Path,
) -> None:
    document = _document(
        _paragraph("Sampul", style="CoverTitle")
        + _paragraph("KATA PENGANTAR", style="Heading1")
        + _paragraph("")
        + _paragraph("BAB I", style="Heading1")
        + _paragraph("Isi")
        + _paragraph("BAB II", style="Heading1")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))
    ctx = _fake_ctx(package)

    result = SectionsStage().run(ctx)

    assert result.stage == StageName.SECTIONS.value
    assert result.status == "ok"
    assert result.changed is True
    sections = iter_sections(package)
    assert [section.kind for section in sections] == [
        "cover",
        "front_matter",
        "body",
        "body",
    ]
    for section in sections:
        assert section.sect_pr.find(qn("w:pgSz")).get(qn("w:w")) == "11906"
        assert section.sect_pr.find(qn("w:pgMar")).get(qn("w:top")) == "1440"
        assert section.sect_pr.find(qn("w:type")).get(qn("w:val")) == "nextPage"

    second = SectionsStage().run(ctx)
    assert second.changed is False
    assert len(iter_sections(package)) == len(sections)


def test_sections_stage_requires_package() -> None:
    ctx = _fake_ctx(None)  # type: ignore[arg-type]
    with pytest.raises(StageError):
        SectionsStage().run(ctx)


def test_sections_stage_landscape_menukar_dimensi(tmp_path: Path) -> None:
    document = _document(_paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(_write_package(tmp_path, document))
    ctx = _fake_ctx(package)
    ctx.format.page.orientation = "landscape"

    SectionsStage().run(ctx)

    pg_sz = iter_sections(package)[0].sect_pr.find(qn("w:pgSz"))
    assert pg_sz.get(qn("w:w")) == "16838"
    assert pg_sz.get(qn("w:h")) == "11906"
    assert pg_sz.get(qn("w:orient")) == "landscape"


def test_sections_stage_menolak_ukuran_tidak_dikenal(tmp_path: Path) -> None:
    document = _document(_paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(_write_package(tmp_path, document))
    ctx = _fake_ctx(package)
    ctx.format.page.size = "A5"

    with pytest.raises(StageError) as excinfo:
        SectionsStage().run(ctx)

    assert excinfo.value.code == "SECTION-STAGE"
    assert isinstance(excinfo.value.cause, SectionsError)
    assert "A5" in str(excinfo.value)


def test_sections_stage_numbers_plain_headings_before_splitting(
    tmp_path: Path,
) -> None:
    document = _document(
        _paragraph("Sampul", style="CoverTitle")
        + _paragraph("KATA PENGANTAR", style="Heading1")
        + _paragraph("Pendahuluan", style="Heading1")
        + _paragraph("Latar Belakang", style="Heading2")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))
    ctx = _fake_ctx(
        package,
        numbering=SimpleNamespace(body="BAB_ROMAN", sub_dot=True, subsub_dot=True),
    )

    result = SectionsStage().run(ctx)

    assert result.status == "ok"
    assert result.metrics["headings_numbered"] == 2
    headings = [heading for heading in iter_headings(package)]
    assert heading_text(headings[1].paragraph).startswith("BAB I")
    assert heading_text(headings[2].paragraph).startswith("1.1.")
    sections = iter_sections(package)
    assert [section.kind for section in sections] == [
        "cover",
        "front_matter",
        "body",
    ]


def test_sections_stage_arabic_dotted_body_starts_at_chapter(
    tmp_path: Path,
) -> None:
    document = _document(
        _paragraph("Sampul", style="CoverTitle")
        + _paragraph("KATA PENGANTAR", style="Heading1")
        + _paragraph("Pendahuluan", style="Heading1")
        + _paragraph("Latar Belakang", style="Heading2")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))
    ctx = _fake_ctx(
        package,
        numbering=SimpleNamespace(
            body="ARABIC_DOTTED",
            sub_dot=True,
            subsub_dot=True,
        ),
    )

    SectionsStage().run(ctx)

    sections = iter_sections(package)
    assert [section.kind for section in sections] == [
        "cover",
        "front_matter",
        "body",
    ]
    headings = [heading for heading in iter_headings(package)]
    assert heading_text(headings[1].paragraph) == "1. PENDAHULUAN"
    body_start = next(index for index, section in enumerate(sections) if section.kind == "body")
    assert sections[body_start].start == headings[1].paragraph.getparent().index(
        headings[1].paragraph
    )


def test_golden_toc_field_count_for_section_boundary() -> None:
    package = DocumentPackage.load(GOLDEN)
    toc_fields = [field for field in iter_fields(package) if field.kind is FieldKind.TOC]
    assert len(toc_fields) == 3
    # Section body pertama dimulai tepat di Heading1 BAB I.
    body_sections = [section for section in iter_sections(package) if section.kind == "body"]
    assert body_sections[0].start == 50


# ---------------------------------------------------------------------------
# Heading numbering
# ---------------------------------------------------------------------------


def _heading_runs(*runs: tuple[str, str]) -> str:
    """Runs berisi pasangan (format, teks), format ``b``/``i``/``plain``."""

    output = ""
    for fmt, text in runs:
        rpr = ""
        if fmt == "b":
            rpr = "<w:rPr><w:b/><w:bCs/></w:rPr>"
        elif fmt == "i":
            rpr = "<w:rPr><w:i/><w:iCs/></w:rPr>"
        output += f"<w:r>{rpr}<w:t>{html.escape(text)}</w:t></w:r>"
    return output


def test_apply_heading_numbering_bab_roman_and_inline_formatting(
    tmp_path: Path,
) -> None:
    document = _document(
        _paragraph(
            style="Heading1",
            extra_runs=_heading_runs(("b", "Pendahuluan"), ("i", " Lanjutan")),
        )
        + _paragraph("Latar Belakang", style="Heading2")
        + _paragraph("Ruang Lingkup", style="Heading3")
        + _paragraph("Tinjauan", style="Heading1")
        + _paragraph("Teori", style="Heading2")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))

    report = apply_heading_numbering(
        package,
        NumberingSpec(body="BAB_ROMAN", sub_dot=True, subsub_dot=True),
    )

    assert report.changed is True
    assert report.numbered == 5
    headings = iter_headings(package)
    assert heading_text(headings[0].paragraph).startswith("BAB I")
    assert "PENDAHULUAN LANJUTAN" in heading_text(headings[0].paragraph)
    assert heading_text(headings[1].paragraph).startswith("1.1.")
    assert heading_text(headings[2].paragraph).startswith("1.1.1.")
    assert heading_text(headings[3].paragraph).startswith("BAB II")
    assert heading_text(headings[4].paragraph).startswith("2.1.")

    first = headings[0].paragraph
    assert first.find(".//" + qn("w:b")) is not None
    assert first.find(".//" + qn("w:i")) is not None
    assert first.find(".//" + qn("w:br")) is not None

    before = sha256_c14n(package.xml(DOCUMENT_PART))
    second = apply_heading_numbering(
        package,
        NumberingSpec(body="BAB_ROMAN", sub_dot=True, subsub_dot=True),
    )
    assert second.changed is False
    assert sha256_c14n(package.xml(DOCUMENT_PART)) == before


def test_apply_heading_numbering_arabic_dotted(tmp_path: Path) -> None:
    document = _document(
        _paragraph("Pendahuluan", style="Heading1")
        + _paragraph("Latar Belakang", style="Heading2")
        + _paragraph("Ruang Lingkup", style="Heading3")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))

    apply_heading_numbering(
        package,
        NumberingSpec(body="ARABIC_DOTTED", sub_dot=False, subsub_dot=True),
    )

    headings = iter_headings(package)
    assert heading_text(headings[0].paragraph) == "1. PENDAHULUAN"
    assert heading_text(headings[0].paragraph, include_number=False) == "PENDAHULUAN"
    assert headings[0].number == "1."
    separators = [node for node in headings[0].paragraph.iter(qn("w:t")) if node.text == " "]
    assert len(separators) == 1
    assert separators[0].get(qn("xml:space")) == "preserve"
    assert heading_text(headings[1].paragraph).startswith("1.1\t")
    assert heading_text(headings[2].paragraph).startswith("1.1.1.")

    before = sha256_c14n(package.xml(DOCUMENT_PART))
    second = apply_heading_numbering(
        package,
        NumberingSpec(body="ARABIC_DOTTED", sub_dot=False, subsub_dot=True),
    )
    assert second.changed is False
    assert sha256_c14n(package.xml(DOCUMENT_PART)) == before


def test_apply_heading_numbering_h2_before_h1_is_not_zero(tmp_path: Path) -> None:
    document = _document(
        _paragraph("Awal", style="Heading2") + _paragraph("Pendahuluan", style="Heading1")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))

    report = apply_heading_numbering(
        package,
        NumberingSpec(body="BAB_ROMAN"),
    )

    headings = iter_headings(package)
    assert heading_text(headings[0].paragraph) == "Awal"
    assert heading_text(headings[1].paragraph).startswith("BAB I")
    assert report.skipped_without_chapter == 1


def test_apply_heading_numbering_skips_front_matter_and_explicit_marker(
    tmp_path: Path,
) -> None:
    document = _document(
        _paragraph("KATA PENGANTAR", style="Heading1")
        + _paragraph("{-}Judul Bebas", style="Heading1")
        + _paragraph("Pendahuluan", style="Heading1")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))

    assert is_unnumbered(iter_headings(package)[0].paragraph) is True
    assert is_unnumbered(iter_headings(package)[1].paragraph) is True

    report = apply_heading_numbering(
        package,
        NumberingSpec(body="BAB_ROMAN"),
    )

    headings = iter_headings(package)
    assert heading_text(headings[0].paragraph) == "KATA PENGANTAR"
    assert heading_text(headings[1].paragraph) == "{-}Judul Bebas"
    assert heading_text(headings[2].paragraph).startswith("BAB I")
    assert report.unnumbered == 2
    assert report.numbered == 1


def test_apply_heading_numbering_h2_under_unnumbered_h1(tmp_path: Path) -> None:
    document = _document(
        _paragraph("Pendahuluan", style="Heading1")
        + _paragraph("Latar Belakang", style="Heading2")
        + _paragraph("KATA PENGANTAR", style="Heading1")
        + _paragraph("Ucapan", style="Heading2")
        + _paragraph("DAFTAR PUSTAKA", style="Heading1")
        + _paragraph("Rujukan", style="Heading2")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))

    report = apply_heading_numbering(
        package,
        NumberingSpec(body="BAB_ROMAN"),
    )

    headings = iter_headings(package)
    assert heading_text(headings[1].paragraph).startswith("1.1.")
    assert heading_text(headings[3].paragraph) == "Ucapan"
    assert heading_text(headings[5].paragraph) == "Rujukan"
    assert report.numbered == 2
    assert report.unnumbered == 4


def test_heading_bookmark_name_is_stable(tmp_path: Path) -> None:
    document = _document(
        _paragraph("Pendahuluan", style="Heading1") + _paragraph("Latar Belakang", style="Heading2")
    )
    package = DocumentPackage.load(_write_package(tmp_path, document))
    apply_heading_numbering(package, NumberingSpec(body="BAB_ROMAN"))
    headings = iter_headings(package)
    assert heading_bookmark_name(headings[0]) == "_TocBAB_I"
    assert heading_bookmark_name(headings[1]) == "_Toc1_1"
