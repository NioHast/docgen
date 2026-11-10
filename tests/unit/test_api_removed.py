"""Tes kontrak penghapusan API mati dan alias stage."""

from dataclasses import fields

from docgen import pipeline
from docgen.docx import layout, terms
from docgen.features.adeu import paragraph_ids
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
