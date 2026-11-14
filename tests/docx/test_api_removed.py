"""Tes kontrak penghapusan API mati dan alias stage."""

from dataclasses import fields

from lxml import etree

from autooffice.docx import pipeline, terms
from autooffice.docx.adeu import paragraph_ids
from autooffice.docx.markdown import blocks
from autooffice.docx.package import bookmarks, layout, sections, tables, xml
from autooffice.docx.stages import (
    blank_lines,
    captions,
    code,
    equations,
    numbering,
    style_reference,
    validate,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def test_layout_dead_api_is_removed() -> None:
    for name in ("read_document", "write_document", "is_deleted"):
        assert not hasattr(layout, name)
    for name in ("paragraphs", "skipped_style", "skipped_field"):
        assert not hasattr(layout.LayoutReport, name)


def test_duplicate_paragraph_is_removed_from_other_modules() -> None:
    for name in ("document_body", "heading_level", "paragraph_style_id", "paragraph_text"):
        assert not hasattr(layout, name)
    assert not hasattr(layout, "content_width")
    for name in (
        "field_name",
        "has_exempt_field",
        "has_field",
        "is_field_run",
        "iter_field_instructions",
        "iter_field_markers",
        "iter_field_runs",
    ):
        assert not hasattr(layout, name), f"layout masih mengekspor {name}"
    for name in ("paragraph_style_id", "paragraph_heading_level"):
        assert not hasattr(bookmarks, name)
    assert not hasattr(sections, "heading_level")
    assert not hasattr(tables, "document_body")
    assert not hasattr(terms, "paragraph_style_id")
    assert not hasattr(xml, "paragraph_text")


def test_terms_dead_api_is_removed() -> None:
    for name in ("term_count", "review_count"):
        assert not hasattr(terms.TermsReport, name)
    for name in ("failures", "direct_formatting"):
        assert not hasattr(terms.TermsVerifyReport, name)
    for name in ("apply_to_docx", "verify_docx", "check_markdown"):
        assert not hasattr(terms, name)


def test_markdown_and_adeu_stage_aliases_are_removed() -> None:
    removed = {
        equations: (
            "FormatEquationsReport",
            "number_equations",
            "EquationStage",
            "_run_number_text",
            "_content_width",
            "_display_equation",
            "_paragraph_text",
        ),
        blank_lines: (
            "blank_lines",
            "BlankLineStage",
            "_classify",
            "_make_empty_paragraph",
        ),
        style_reference: (
            "resolve_style_specs",
            "generate_reference_docx",
            "build_reference",
        ),
        code: ("format_code",),
        captions: ("CaptionStage", "format_figures"),
        numbering: ("normalize_numbering",),
        validate: ("check_captions", "validate_captions"),
        blocks: ("plain_inline",),
        paragraph_ids: ("ParagraphIdError",),
    }
    for module, names in removed.items():
        for name in names:
            assert not hasattr(module, name), f"{module.__name__} masih punya {name}"


def test_stage_spec_without_owner() -> None:
    assert "owner" not in {field.name for field in fields(pipeline.StageSpec)}


def test_docx_package_level_page_and_run_helpers_behave() -> None:
    from autooffice.docx.package import (
        PAGE_SIZES,
        PageError,
        ParagraphError,
        append_text_run,
        body_children,
        build_run,
        chapter_number,
        clone_run,
        content_width,
        copy_rpr,
        format_roman,
        heading_level,
        int_attribute,
        make_run,
        page_size,
        paragraph_style_id,
        paragraph_text,
        qn,
        remove_direct_children,
        roman_to_int,
        strip_bold_from_rpr,
        to_roman,
    )

    assert PAGE_SIZES["A4"] == (11906, 16838)
    assert page_size("Letter", "landscape") == (15840, 12240)
    assert PageError.default_code == "PAGE"
    assert ParagraphError.default_code == "PARAGRAPH"
    assert roman_to_int("XIV") == 14
    assert to_roman(14) == "XIV"
    assert chapter_number("BAB IV") == 4
    assert format_roman(4) == "IV"

    body = etree.fromstring(
        f'<w:body xmlns:w="{W_NS}">'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:left="1440" w:right="1440" w:gutter="720"/>'
        "</w:sectPr></w:body>"
    )
    assert content_width(body) == 8306
    assert [child.tag for child in body_children(body)] == [qn("w:sectPr")]

    paragraph = etree.fromstring(
        f'<w:p xmlns:w="{W_NS}"><w:pPr><w:pStyle w:val="Heading1"/></w:pPr></w:p>'
    )
    make_run(paragraph, text="BAB I")
    assert heading_level(paragraph) == 1
    assert paragraph_style_id(paragraph) == "Heading1"
    assert paragraph_text(paragraph) == "BAB I"

    append_text_run(paragraph, "A\tB")
    assert paragraph_text(paragraph) == "BAB IA\tB"

    built = build_run(text="Awal")
    cloned = clone_run(built)
    assert cloned is not built
    assert cloned[0] is not built[0]
    assert "".join(node.text or "" for node in cloned.iter(qn("w:t"))) == "Awal"

    rpr = etree.fromstring(f'<w:rPr xmlns:w="{W_NS}"><w:b/><w:i/></w:rPr>')
    copied = copy_rpr(rpr)
    assert copied is not rpr
    assert copied.find(qn("w:i")) is not None
    assert strip_bold_from_rpr(copied) == 1
    assert copied.find(qn("w:b")) is None
    assert rpr.find(qn("w:b")) is not None

    ppr = etree.fromstring(
        f'<w:pPr xmlns:w="{W_NS}"><w:keepNext/><w:keepNext/><w:spacing/></w:pPr>'
    )
    assert remove_direct_children(ppr, qn("w:keepNext")) == 2
    assert ppr.find(qn("w:spacing")) is not None

    size = etree.fromstring(f'<w:sz xmlns:w="{W_NS}" w:val="24"/>')
    assert int_attribute(size, qn("w:val")) == 24
    assert int_attribute(size, qn("w:missing")) is None


def test_docx_package_level_field_and_heading_helpers_behave() -> None:
    from autooffice.docx.package import (
        FieldMarkerKind,
        FieldPosition,
        Heading,
        HeadingError,
        HeadingReport,
        NumberingSpec,
        field_marker_kind,
        field_text_ranges,
        heading_bookmark_name,
        heading_text,
        insert_field,
        is_unnumbered,
        qn,
    )

    assert FieldMarkerKind.BEGIN.value == "begin"
    marker = etree.fromstring(f'<w:fldChar xmlns:w="{W_NS}" w:fldCharType="begin"/>')
    assert field_marker_kind(marker) is FieldMarkerKind.BEGIN

    paragraph = etree.fromstring(
        f'<w:p xmlns:w="{W_NS}">'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>3</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        "</w:p>"
    )
    assert field_text_ranges(paragraph) == ((0, 1),)

    inserted = insert_field(
        ["PAGE"],
        FieldPosition(paragraph=paragraph, before=paragraph[0]),
        "7",
    )
    assert inserted.begin.getparent() is paragraph
    assert inserted.end.getparent() is paragraph
    assert field_marker_kind(inserted.begin.find(qn("w:fldChar"))) is FieldMarkerKind.BEGIN

    heading_paragraph = etree.fromstring(
        f'<w:p xmlns:w="{W_NS}">'
        '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        "<w:r><w:t>1. PENDAHULUAN</w:t></w:r>"
        "</w:p>"
    )
    assert heading_text(heading_paragraph) == "1. PENDAHULUAN"
    assert heading_text(heading_paragraph, include_number=False) == "PENDAHULUAN"

    heading = Heading(
        level=1,
        paragraph=heading_paragraph,
        text="1. PENDAHULUAN",
        number="1.",
        unnumbered=False,
    )
    assert heading_bookmark_name(heading) == "_Toc1"
    report = HeadingReport(
        changed=False,
        numbered=1,
        unnumbered=0,
        skipped_without_chapter=0,
        headings=(heading,),
    )
    assert report.headings == (heading,)
    assert NumberingSpec(body="BAB_ROMAN") == NumberingSpec(
        body="BAB_ROMAN", sub_dot=True, subsub_dot=True
    )
    assert HeadingError.default_code == "HEADING"

    unnumbered_paragraph = etree.fromstring(
        f'<w:p xmlns:w="{W_NS}">'
        '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        "<w:r><w:t>KATA PENGANTAR</w:t></w:r>"
        "</w:p>"
    )
    assert is_unnumbered(unnumbered_paragraph) is True
    assert is_unnumbered(heading_paragraph) is False
