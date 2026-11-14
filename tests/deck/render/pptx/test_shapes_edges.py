"""Tes cabang edge primitif shape, metadata key, dan validasi field."""

import logging
from types import SimpleNamespace

import pytest
from _edge_helpers import new_slide, shape_with_metadata
from lxml import etree
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu

from autooffice.deck.layout.spec import PlacedBlock
from autooffice.deck.render.pptx.shapes import (
    Box,
    PptxRenderError,
    add_extension_keys,
    apply_paragraph_style,
    apply_run_style,
    box_from_placed,
    collect_render_warnings,
    configure_text_frame,
    extension_keys,
    field_optional_text,
    field_rows,
    field_sequence,
    field_text,
    key_from_shape,
    primary_typeface,
    record_render_warning,
    rgb,
    sequence,
    set_chrome_shape,
    set_keyed_shape,
    set_namespace_marker,
    set_non_visual_properties,
    shape_extension_keys,
    validate_box_within_slide,
)


def _textbox():
    return new_slide().shapes.add_textbox(Emu(0), Emu(0), Emu(100000), Emu(100000))


@pytest.mark.parametrize(("width", "height"), [(0, 10), (10, 0), (-1, 10)])
def test_box_rejects_non_positive_dimensions(width: int, height: int) -> None:
    with pytest.raises(PptxRenderError, match="lebar dan tinggi positif"):
        Box(left=0, top=0, width=width, height=height)


def test_box_inset_rejects_negative_padding() -> None:
    with pytest.raises(PptxRenderError, match="Padding shape tidak boleh negatif"):
        Box(left=0, top=0, width=100, height=100).inset(-1)


def test_box_inset_rejects_padding_larger_than_box() -> None:
    with pytest.raises(PptxRenderError, match="terlalu besar untuk kotak"):
        Box(left=0, top=0, width=10, height=10).inset(5)


@pytest.mark.parametrize(
    "box",
    [
        Box(left=-1, top=0, width=10, height=10),
        Box(left=95, top=0, width=10, height=10),
        Box(left=0, top=95, width=10, height=10),
    ],
)
def test_validate_box_within_slide_rejects_negative_and_outside(box: Box) -> None:
    with pytest.raises(PptxRenderError):
        validate_box_within_slide(box, slide_width_emu=100, slide_height_emu=100)


def test_box_from_placed_copies_emu_coordinates() -> None:
    placed = PlacedBlock("b", 1, 2, 3, 4)

    box = box_from_placed(placed)

    assert (box.left, box.top, box.width, box.height) == (1, 2, 3, 4)
    assert box.right == 4
    assert box.bottom == 6


@pytest.mark.parametrize("color", ["1234567", "#12345", "#GGGGGG"])
def test_rgb_rejects_malformed_hex(color: str) -> None:
    with pytest.raises(PptxRenderError, match="Warna token"):
        rgb(color)


def test_primary_typeface_falls_back_to_generic_stack_head() -> None:
    assert primary_typeface("serif, monospace") == "serif"


@pytest.mark.parametrize(
    ("weight", "expected", "bold"),
    [
        (400, "Plus Jakarta Sans", False),
        (600, "Plus Jakarta Sans SemiBold", False),
        (700, "Plus Jakarta Sans", True),
        (800, "Plus Jakarta Sans ExtraBold", False),
    ],
)
def test_apply_run_style_selects_named_weight_typeface(
    weight: int,
    expected: str,
    bold: bool,
) -> None:
    run, warning = _styled_run("Plus Jakarta Sans, sans-serif", weight)

    assert warning is None
    assert run.font.name == expected
    assert run.font.bold is bold
    latin = run.font._element.find(qn("a:latin"))
    assert latin is not None
    assert latin.get("typeface") == expected


@pytest.mark.parametrize("weight", [600, 800])
def test_apply_run_style_falls_back_and_warns_for_unknown_weight_family(weight: int) -> None:
    run, warning = _styled_run("Inter", weight)

    assert run.font.name == "Inter"
    assert run.font.bold is True
    assert warning is not None
    assert "tidak tersedia" in warning
    assert "bold=True" in warning


def test_record_render_warning_logs_without_collector(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="autooffice.deck.render.pptx.shapes"):
        record_render_warning("font-weight: fallback")

    assert "font-weight: fallback" in caplog.text


def test_collect_render_warnings_deduplicates_messages() -> None:
    with collect_render_warnings() as warnings:
        record_render_warning("font-weight: fallback")
        record_render_warning("font-weight: fallback")

    assert warnings == ["font-weight: fallback"]


def _styled_run(family: str, weight: int):
    paragraph = _textbox().text_frame.paragraphs[0]
    paragraph.text = "Contoh"
    run = paragraph.runs[0]
    warning = apply_run_style(
        run,
        family=family,
        size_pt=12,
        weight=weight,
        color="#102030",
        tracking_em=0.0,
    )
    return run, warning


def test_set_non_visual_properties_requires_cnv_pr() -> None:
    fake = SimpleNamespace(_element=etree.Element(qn("p:sp")))

    with pytest.raises(PptxRenderError, match="tidak punya cNvPr"):
        set_non_visual_properties(fake, name="baru")


def test_set_non_visual_properties_removes_title_and_description() -> None:
    shape = _textbox()
    set_non_visual_properties(shape, name="nama", title="judul", description="deskripsi")

    set_non_visual_properties(shape, name="nama", title=None, description=None)

    node = shape._element.find(".//" + qn("p:cNvPr"))
    assert node is not None
    assert node.get("name") == "nama"
    assert node.get("title") is None
    assert node.get("descr") is None


def test_marker_setters_reject_empty_values() -> None:
    shape = _textbox()

    with pytest.raises(PptxRenderError, match="Key shape tidak boleh kosong"):
        set_keyed_shape(shape, "", description="")
    with pytest.raises(PptxRenderError, match="Namespace block tidak boleh kosong"):
        set_namespace_marker(shape, "autooffice:image:", "", description="")
    with pytest.raises(PptxRenderError, match="Nama chrome tidak boleh kosong"):
        set_chrome_shape(shape, "")


def test_key_from_shape_uses_plain_title_fallback() -> None:
    shape = shape_with_metadata("Shape Biasa", title="s01.title.text")

    assert key_from_shape(shape) == "s01.title.text"


def test_key_from_shape_ignores_autooffice_title_and_media_names() -> None:
    autooffice_title = shape_with_metadata("Shape Biasa", title="autooffice:key:x")
    media = shape_with_metadata("autooffice:image:s01.image1")

    assert key_from_shape(autooffice_title) is None
    assert key_from_shape(media) is None


def test_add_extension_keys_reuses_existing_extension_list_and_skips_duplicates() -> None:
    parent = etree.Element(qn("a:tcPr"))
    etree.SubElement(parent, qn("a:extLst"))

    add_extension_keys(parent, ("s01.a", "s01.b"))
    add_extension_keys(parent, ("s01.b", "s01.c"))

    assert extension_keys(parent) == ("s01.a", "s01.b", "s01.c")


def test_add_extension_keys_returns_early_for_empty_input() -> None:
    parent = etree.Element(qn("a:tcPr"))

    add_extension_keys(parent, ())

    assert parent.find(qn("a:extLst")) is None


def test_shape_extension_keys_returns_empty_without_cnv_pr() -> None:
    fake = SimpleNamespace(_element=etree.Element(qn("p:sp")))

    assert shape_extension_keys(fake) == ()


@pytest.mark.parametrize("value", [None, 3, ""])
def test_field_text_rejects_missing_or_non_string(value: object) -> None:
    fields = {} if value is None else {"text": value}

    with pytest.raises(PptxRenderError, match="tidak memiliki field teks"):
        field_text(fields, "text", block_id="b1")


def test_field_optional_text_returns_empty_for_non_string() -> None:
    assert field_optional_text({"caption": 3}, "caption") == ""
    assert field_optional_text({}, "caption") == ""
    assert field_optional_text({"caption": "isi"}, "caption") == "isi"


def test_field_sequence_rejects_non_sequence() -> None:
    with pytest.raises(PptxRenderError, match="tidak memiliki field daftar"):
        field_sequence({"items": "bukan list"}, "items", block_id="b1")


def test_field_sequence_rejects_non_string_item() -> None:
    with pytest.raises(PptxRenderError, match="harus string"):
        field_sequence({"items": ("ok", 2)}, "items", block_id="b1")


def test_field_rows_rejects_non_sequence() -> None:
    with pytest.raises(PptxRenderError, match="tidak memiliki field baris"):
        field_rows({"rows": "bukan list"}, "rows", block_id="b1")


def test_field_rows_rejects_non_row_value() -> None:
    with pytest.raises(PptxRenderError, match="harus baris string"):
        field_rows({"rows": ("bukan baris",)}, "rows", block_id="b1")


def test_field_rows_rejects_non_string_cell() -> None:
    with pytest.raises(PptxRenderError, match="harus string"):
        field_rows({"rows": (("ok", 2),)}, "rows", block_id="b1")


def test_sequence_normalizes_sequences_and_rejects_scalars() -> None:
    assert sequence([1, 2]) == (1, 2)
    assert sequence((1, 2)) == (1, 2)
    assert sequence("teks") == ()
    assert sequence(b"bytes") == ()
    assert sequence(3) == ()


def test_configure_text_frame_sets_wrap_size_anchor_and_margins() -> None:
    text_frame = _textbox().text_frame

    configure_text_frame(text_frame, vertical_anchor=MSO_ANCHOR.MIDDLE)

    assert text_frame.word_wrap is True
    assert text_frame.auto_size == MSO_AUTO_SIZE.NONE
    assert text_frame.vertical_anchor == MSO_ANCHOR.MIDDLE
    assert text_frame.margin_left == text_frame.margin_right == Emu(0)
    assert text_frame.margin_top == text_frame.margin_bottom == Emu(0)


@pytest.mark.parametrize(
    ("line_height", "font_size_pt"),
    [(0.0, 12.0), (1.2, 0.0)],
)
def test_apply_paragraph_style_rejects_non_positive_values(
    line_height: float,
    font_size_pt: float,
) -> None:
    paragraph = _textbox().text_frame.paragraphs[0]

    with pytest.raises(PptxRenderError, match="harus positif"):
        apply_paragraph_style(
            paragraph,
            line_height=line_height,
            font_size_pt=font_size_pt,
        )


def test_apply_paragraph_style_uses_exact_point_line_spacing() -> None:
    paragraph = _textbox().text_frame.paragraphs[0]

    apply_paragraph_style(
        paragraph,
        line_height=1.25,
        font_size_pt=16.0,
        alignment=PP_ALIGN.RIGHT,
    )

    p_pr = paragraph._p.find(qn("a:pPr"))
    assert p_pr is not None
    spacing = p_pr.find(f"{qn('a:lnSpc')}/{qn('a:spcPts')}")
    assert spacing is not None
    assert spacing.get("val") == "2000"
    assert p_pr.find(".//" + qn("a:spcPct")) is None
    assert paragraph.alignment == PP_ALIGN.RIGHT
