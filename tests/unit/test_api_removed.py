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


def test_layout_api_mati_hilang() -> None:
    for name in ("read_document", "write_document", "is_deleted"):
        assert not hasattr(layout, name)
    for name in ("paragraphs", "skipped_style", "skipped_field"):
        assert not hasattr(layout.LayoutReport, name)


def test_duplikat_paragraf_hilang_dari_modul_lain() -> None:
    for name in ("document_body", "heading_level", "paragraph_style_id", "paragraph_text"):
        assert not hasattr(layout, name)
    for name in ("paragraph_style_id", "paragraph_heading_level"):
        assert not hasattr(bookmarks, name)
    assert not hasattr(sections, "heading_level")
    assert not hasattr(tables, "document_body")
    assert not hasattr(terms, "paragraph_style_id")
    assert not hasattr(xml, "paragraph_text")


def test_terms_api_mati_hilang() -> None:
    for name in ("term_count", "review_count"):
        assert not hasattr(terms.TermsReport, name)
    for name in ("failures", "direct_formatting"):
        assert not hasattr(terms.TermsVerifyReport, name)
    for name in ("apply_to_docx", "verify_docx", "check_markdown"):
        assert not hasattr(terms, name)


def test_alias_stage_markdown_dan_adeu_hilang() -> None:
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


def test_stage_spec_tanpa_owner() -> None:
    assert "owner" not in {field.name for field in fields(pipeline.StageSpec)}


def test_docx_package_level_helper_baru_tersedia() -> None:
    from docgen.docx import (
        PAGE_SIZES,
        ParagraphError,
        append_text_run,
        body_children,
        build_run,
        chapter_number,
        clone_run,
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


def test_private_duplikat_docx_hilang() -> None:
    from docgen.docx import captions as docx_captions
    from docgen.docx import fields as docx_fields
    from docgen.docx import paragraphs, runs

    assert not hasattr(docx_captions, "_append_text")
    assert not hasattr(docx_fields, "_paragraph_style")
    assert hasattr(paragraphs, "document_body")
    assert hasattr(runs, "append_text_run")
    assert not hasattr(layout, "_toggle_is_on")
    assert not hasattr(layout, "strip_bold_from_rpr")
