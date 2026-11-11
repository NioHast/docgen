"""Tes kontrak penghapusan API mati dan alias stage."""

from dataclasses import fields

from docgen import pipeline
from docgen.adeu import paragraph_ids
from docgen.docx import bookmarks, layout, sections, tables, terms, xml
from docgen.markdown import blocks
from docgen.stages import (
    blank_lines,
    captions,
    code,
    equations,
    numbering,
    style_reference,
    validate,
)


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


def test_docx_package_level_new_helpers_are_available() -> None:
    from docgen.docx import (
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
        document_body,
        format_roman,
        heading_level,
        int_attribute,
        make_run,
        page_size,
        paragraph_style_id,
        paragraph_text,
        remove_direct_children,
        roman_to_int,
        strip_bold_from_rpr,
        to_roman,
    )

    assert PAGE_SIZES["A4"] == (11906, 16838)
    assert page_size("Letter", "landscape") == (15840, 12240)
    assert PageError.default_code == "PAGE"
    assert callable(content_width)
    assert roman_to_int("XIV") == 14
    assert to_roman(14) == "XIV"
    assert chapter_number("BAB IV") == 4
    assert format_roman(4) == "IV"
    for helper in (
        ParagraphError,
        append_text_run,
        body_children,
        build_run,
        clone_run,
        copy_rpr,
        document_body,
        heading_level,
        int_attribute,
        make_run,
        paragraph_style_id,
        paragraph_text,
        remove_direct_children,
        strip_bold_from_rpr,
    ):
        assert helper is not None


def test_docx_package_level_field_and_heading_are_available() -> None:
    from docgen.docx import (
        FieldMarkerKind,
        FieldPosition,
        Heading,
        HeadingError,
        HeadingReport,
        NumberingSpec,
        apply_heading_numbering,
        field_marker_kind,
        field_text_ranges,
        heading_bookmark_name,
        heading_text,
        insert_field,
        is_unnumbered,
        iter_headings,
    )

    assert FieldMarkerKind.BEGIN.value == "begin"
    assert FieldPosition is not None
    for helper in (
        Heading,
        HeadingError,
        HeadingReport,
        NumberingSpec,
        apply_heading_numbering,
        field_marker_kind,
        field_text_ranges,
        heading_bookmark_name,
        heading_text,
        insert_field,
        is_unnumbered,
        iter_headings,
    ):
        assert helper is not None
