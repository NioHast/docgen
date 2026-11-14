"""Tes integrasi renderer PPTX: slide, shape key, table, image, notes, XML."""

import pytest
from _edge_helpers import has_percentage_line_spacing, line_spacing_points
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE

from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.xml import forbidden_node_paths
from autooffice.deck.render.protocol import OutputTarget, RenderRequest


def _render(case, theme, *, target: OutputTarget = OutputTarget.PPTX):
    request = RenderRequest(
        deck=case.deck,
        layout=case.layout,
        theme=theme,
        target=target,
        workspace=case.workspace,
    )
    return PptxRenderer().render(request)


def test_minimal_deck_writes_artifact_and_metadata(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)

    assert result.artifact_path.exists()
    assert result.artifact_path.suffix == ".pptx"
    assert result.coverage.ok is True
    assert result.coverage.missing_keys == ()
    assert result.coverage.unkeyed_visible == ()
    assert result.coverage.missing_alt == ()
    assert len(result.content_hash) == 64
    assert int(result.content_hash, 16) >= 0
    assert any("font-embedding" in warning for warning in result.warnings)
    assert result.target_metadata["renderer"] == "pptx"
    assert result.target_metadata["target"] == "pptx"
    assert result.target_metadata["slides"] == "2"
    assert result.target_metadata["font_embedding"] == "deferred"


def test_minimal_deck_has_native_text_table_image_and_notes(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    presentation = Presentation(str(result.artifact_path))

    assert len(presentation.slides) == 2
    first = presentation.slides[0]
    shapes = {shape.name: shape for shape in first.shapes}

    title = shapes["autooffice:key:s01.title.text"]
    title_node = title._element.find(
        ".//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr"
    )
    assert title_node is not None
    assert title_node.get("title") == "s01.title.text"
    assert title_node.get("descr") == "Judul deck"
    assert title.text_frame.word_wrap is True
    assert title.text_frame.auto_size == MSO_AUTO_SIZE.NONE
    assert all(
        run.font.size is not None and run.font.size.pt >= theme.typography.minimum_pt
        for paragraph in title.text_frame.paragraphs
        for run in paragraph.runs
    )

    table_shape = shapes["autooffice:table:s01.table1"]
    assert table_shape.shape_type == MSO_SHAPE_TYPE.TABLE
    assert table_shape.has_table is True
    table = table_shape.table
    assert len(table.rows) == 3
    assert len(table.columns) == 3
    assert table.cell(0, 0).text == "Lane"
    assert table.cell(2, 2).text == "42"
    assert table.cell(0, 0).fill.fore_color.rgb == _rgb(theme.colors.accent)

    picture = shapes["autooffice:image:s01.image1"]
    assert picture.shape_type == MSO_SHAPE_TYPE.PICTURE
    picture_node = picture._element.find(
        ".//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr"
    )
    assert picture_node is not None
    assert picture_node.get("descr") == "Tim meninjau arsitektur"
    assert picture_node.get("title") == "s01.image1"
    assert picture.crop_top > 0
    assert picture.crop_bottom > 0

    assert first.has_notes_slide is True
    assert first.notes_slide.notes_text_frame is not None
    assert "Catatan pembicara untuk slide satu." in first.notes_slide.notes_text_frame.text
    assert presentation.slides[1].has_notes_slide is False


def test_all_text_uses_word_wrap_no_shrink_and_minimum_size(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    presentation = Presentation(str(result.artifact_path))

    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                text_frame = shape.text_frame
                assert text_frame.word_wrap is True
                assert text_frame.auto_size == MSO_AUTO_SIZE.NONE
                for paragraph in text_frame.paragraphs:
                    assert has_percentage_line_spacing(paragraph) is False
                    for run in paragraph.runs:
                        assert run.font.name is not None
                        assert run.font.size is not None
                        assert run.font.size.pt >= theme.typography.minimum_pt
                        assert line_spacing_points(paragraph) == round(
                            run.font.size.pt * theme.typography.line_height * 100
                        )
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        assert cell.text_frame.auto_size == MSO_AUTO_SIZE.NONE
                        for paragraph in cell.text_frame.paragraphs:
                            assert has_percentage_line_spacing(paragraph) is False
                            for run in paragraph.runs:
                                assert run.font.size is not None
                                assert run.font.size.pt >= theme.typography.minimum_pt
                                assert line_spacing_points(paragraph) == round(
                                    run.font.size.pt * theme.typography.line_height * 100
                                )
        if slide.has_notes_slide:
            notes_frame = slide.notes_slide.notes_text_frame
            assert notes_frame is not None
            for paragraph in notes_frame.paragraphs:
                assert has_percentage_line_spacing(paragraph) is False
                for run in paragraph.runs:
                    assert run.font.size is not None
                    assert line_spacing_points(paragraph) == round(
                        run.font.size.pt * theme.typography.line_height * 100
                    )


def test_table_cells_and_source_have_key_metadata(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)
    presentation = Presentation(str(result.artifact_path))
    table_shape = next(
        shape
        for shape in presentation.slides[0].shapes
        if shape.name == "autooffice:table:s01.table1"
    )
    table = table_shape.table

    assert _cell_key(table.cell(0, 0)) == "s01.table1.h1"
    assert _cell_key(table.cell(1, 2)) == "s01.table1.r1.c3"
    assert _cell_key(table.cell(2, 3 - 1)) == "s01.table1.r2.c3"
    source = next(
        shape
        for shape in presentation.slides[0].shapes
        if shape.name == "autooffice:key:s01.source.text"
    )
    source_node = source._element.find(
        ".//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr"
    )
    assert source_node is not None
    assert source_node.get("title") == "s01.source.text"


def test_renderer_never_writes_timing_or_transition(minimal_case, theme) -> None:
    result = _render(minimal_case, theme)

    assert forbidden_node_paths(result.artifact_path) == ()


def test_render_is_deterministic_for_same_input(minimal_case, theme) -> None:
    first = _render(minimal_case, theme)
    second = _render(minimal_case, theme)

    assert first.content_hash == second.content_hash
    assert first.artifact_path == second.artifact_path
    assert first.coverage == second.coverage


def test_pdf_target_returns_warning_but_pptx_artifact(minimal_case, theme) -> None:
    result = _render(minimal_case, theme, target=OutputTarget.PDF)

    assert result.artifact_path.suffix == ".pptx"
    assert result.target_metadata["target"] == "pdf"
    assert any("konversi PDF" in warning for warning in result.warnings)


def test_slides_target_uses_google_fonts_without_ppt_embedding_warning(minimal_case, theme) -> None:
    result = _render(minimal_case, theme, target=OutputTarget.SLIDES)

    assert not any("font-embedding" in warning for warning in result.warnings)
    assert result.target_metadata["font_embedding"] == "google"


@pytest.mark.parametrize("target", [OutputTarget.PPTX, OutputTarget.PDF])
def test_chart_block_renders_native_chart_part(chart_case, theme, target) -> None:
    result = _render(chart_case, theme, target=target)
    presentation = Presentation(str(result.artifact_path))
    charts = [shape for shape in presentation.slides[0].shapes if shape.has_chart]

    assert len(charts) == 1
    assert charts[0].shape_type == MSO_SHAPE_TYPE.CHART
    assert not any(
        shape.shape_type == MSO_SHAPE_TYPE.PICTURE for shape in presentation.slides[0].shapes
    )
    assert result.coverage.ok is True
    assert result.target_metadata["chart_rendering"] == "native"
    assert forbidden_node_paths(result.artifact_path) == ()


def _cell_key(cell: object) -> str | None:
    keys = [
        element.text
        for element in cell._tc.iter("{urn:autooffice:key}key")  # type: ignore[attr-defined]
        if element.text
    ]
    return keys[0] if keys else None


def _rgb(color: str) -> object:
    from pptx.dml.color import RGBColor

    return RGBColor.from_string(color[1:])
