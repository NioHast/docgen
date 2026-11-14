"""Tes integrasi chart native dan placeholder pada renderer PPTX."""

import io
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from lxml import etree
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame

from autooffice.deck.layout.measure import measure_text
from autooffice.deck.model.deck_ir import KeyManifest
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx import chart as chart_renderer
from autooffice.deck.render.pptx.coverage import CoverageError
from autooffice.deck.render.pptx.shapes import CHART_MARKER, key_from_shape
from autooffice.deck.render.pptx.xml import (
    content_hash,
    forbidden_node_paths,
    normalize_embedded_workbooks,
)
from autooffice.deck.render.protocol import OutputTarget, RenderRequest

KEY_EXTENSION = "{urn:autooffice:key}key"
CHART_NAME = "autooffice:chart:s01.chart1"
CAPTION_NAME = "autooffice:key:s01.chart1.caption"
FIXED_CORE_TIMESTAMP = "2000-01-01T00:00:00Z"
FIXED_ZIP_TIMESTAMP = (2000, 1, 1, 0, 0, 0)
DCTERMS_NS = "http://purl.org/dc/terms/"


def _render(case, theme, *, target: OutputTarget):
    return PptxRenderer().render(
        RenderRequest(
            deck=case.deck,
            layout=case.layout,
            theme=theme,
            target=target,
            workspace=case.workspace,
        )
    )


def _chart_shape(result) -> BaseShape:
    presentation = Presentation(str(result.artifact_path))
    return next(shape for shape in presentation.slides[0].shapes if shape.name == CHART_NAME)


def _shape_named(result, name: str) -> BaseShape:
    presentation = Presentation(str(result.artifact_path))
    return next(shape for shape in presentation.slides[0].shapes if shape.name == name)


def _keys(shape: BaseShape) -> tuple[str, ...]:
    return tuple(element.text for element in shape._element.iter(KEY_EXTENSION) if element.text)


def _embedded_workbook(path: Path) -> bytes:
    with zipfile.ZipFile(path) as package:
        name = next(
            entry
            for entry in package.namelist()
            if entry.startswith("ppt/embeddings/") and entry.lower().endswith(".xlsx")
        )
        return package.read(name)


def _core_timestamp(core: etree._Element, local_name: str) -> str | None:
    element = core.find(f"{{{DCTERMS_NS}}}{local_name}")
    return None if element is None else element.text


def _patch_workbook_clock(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    """Paksa XlsxWriter memakai waktu tetap agar dua render punya timestamp berbeda."""

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return moment

    monkeypatch.setattr("xlsxwriter.core.datetime", FixedDatetime)


@pytest.mark.parametrize("target", [OutputTarget.PPTX, OutputTarget.PDF])
def test_pptx_and_pdf_targets_render_native_chart_part(chart_case, theme, target) -> None:
    result = _render(chart_case, theme, target=target)
    presentation = Presentation(str(result.artifact_path))
    shape = _chart_shape(result)

    assert shape.has_chart is True
    assert shape.shape_type == MSO_SHAPE_TYPE.CHART
    assert not any(
        candidate.shape_type == MSO_SHAPE_TYPE.PICTURE
        for slide in presentation.slides
        for candidate in slide.shapes
    )
    part_names = {str(part.partname) for part in presentation.part.package.iter_parts()}
    assert any(name.startswith("/ppt/charts/chart") for name in part_names)
    assert any(name.startswith("/ppt/embeddings/") for name in part_names)
    assert not any(name.startswith("/ppt/media/") for name in part_names)
    assert result.target_metadata["chart_rendering"] == "native"
    assert not any("placeholder" in warning for warning in result.warnings)


def test_native_chart_data_categories_and_series_match_block(chart_case, theme) -> None:
    result = _render(chart_case, theme, target=OutputTarget.PPTX)
    shape = _chart_shape(result)
    chart = cast(GraphicFrame, shape).chart

    assert shape.name.startswith(CHART_MARKER)
    assert tuple(str(category) for category in chart.plots[0].categories) == ("Q1", "Q2")
    assert tuple(str(series.name) for series in chart.series) == ("2025", "2026")
    assert tuple(tuple(float(value) for value in series.values) for series in chart.series) == (
        (1.0, 2.0),
        (3.0, 4.0),
    )
    assert chart.chart_title.text_frame.text == "Adopsi per kuartal"
    node = shape._element.find(".//" + qn("p:cNvPr"))
    assert node is not None
    assert node.get("title") == "s01.chart1"
    assert node.get("descr") == "Grafik garis adopsi naik setiap kuartal"


@pytest.mark.parametrize("target", [OutputTarget.PPTX, OutputTarget.SLIDES])
def test_chart_caption_is_keyed_box_below_reduced_chart(chart_case, theme, target) -> None:
    result = _render(chart_case, theme, target=target)
    chart_shape = _chart_shape(result)
    caption_shape = _shape_named(result, CAPTION_NAME)
    placed = chart_case.layout.slides[0].boxes[0]
    caption_height = measure_text(
        "Target internal",
        available_width_emu=placed.width_emu,
        theme=theme,
        font_size_pt=theme.typography.body_pt,
        weight=400,
    ).height_emu

    assert caption_shape.name == CAPTION_NAME
    assert caption_shape.text_frame.text == "Target internal"
    assert caption_shape.top == chart_shape.top + chart_shape.height + theme.spacing.sm_emu
    assert caption_shape.height == caption_height
    assert chart_shape.height == placed.height_emu - caption_height - theme.spacing.sm_emu
    assert chart_shape.height < placed.height_emu
    assert result.coverage.ok is True


def test_slides_target_renders_placeholder_without_chart_part(chart_case, theme) -> None:
    result = _render(chart_case, theme, target=OutputTarget.SLIDES)
    presentation = Presentation(str(result.artifact_path))
    shape = _chart_shape(result)
    node = shape._element.find(".//" + qn("p:cNvPr"))

    assert shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
    assert shape.has_chart is False
    assert shape.name == CHART_NAME
    assert node is not None
    assert node.get("title") == CHART_NAME
    assert node.get("descr") == "Grafik garis adopsi naik setiap kuartal"
    part_names = {str(part.partname) for part in presentation.part.package.iter_parts()}
    assert not any(name.startswith("/ppt/charts/") for name in part_names)
    assert not any(name.startswith("/ppt/embeddings/") for name in part_names)
    assert result.target_metadata["chart_rendering"] == "placeholder"
    assert any("placeholder" in warning for warning in result.warnings)


@pytest.mark.parametrize("target", [OutputTarget.PPTX, OutputTarget.SLIDES])
def test_chart_coverage_includes_caption_and_data_keys(chart_case, theme, target) -> None:
    result = _render(chart_case, theme, target=target)
    chart_keys = set(_keys(_chart_shape(result)))
    expected = {
        "s01.chart1.title",
        "s01.chart1.cat1",
        "s01.chart1.cat2",
        "s01.chart1.series1.name",
        "s01.chart1.series1.value1",
        "s01.chart1.series1.value2",
        "s01.chart1.series2.name",
        "s01.chart1.series2.value1",
        "s01.chart1.series2.value2",
    }

    assert chart_keys == expected
    assert key_from_shape(_shape_named(result, CAPTION_NAME)) == "s01.chart1.caption"
    assert result.coverage.ok is True


@pytest.mark.parametrize("target", [OutputTarget.PPTX, OutputTarget.SLIDES])
def test_chart_coverage_fails_when_caption_shape_is_missing(
    chart_case,
    theme,
    monkeypatch: pytest.MonkeyPatch,
    target,
) -> None:
    monkeypatch.setattr(chart_renderer, "add_caption", lambda *args, **kwargs: None)

    with pytest.raises(CoverageError) as error:
        _render(chart_case, theme, target=target)

    assert error.value.report.missing_keys == ("s01.chart1.caption",)


def test_chart_coverage_fails_when_caption_and_data_bindings_are_missing(
    chart_case,
    theme,
) -> None:
    dropped = {"caption", "series1.value1"}
    bindings = tuple(
        binding for binding in chart_case.deck.keys.bindings if binding.leaf not in dropped
    )
    deck = replace(chart_case.deck, keys=KeyManifest(bindings))
    case = replace(chart_case, deck=deck)

    with pytest.raises(CoverageError) as error:
        _render(case, theme, target=OutputTarget.PPTX)

    assert "s01.chart1.caption" in error.value.report.unkeyed_visible
    assert "s01.chart1.series1.value1" in error.value.report.unkeyed_visible


def test_chart_coverage_fails_when_block_caption_is_missing(chart_case, theme) -> None:
    slide = chart_case.deck.slides[0]
    block = slide.blocks[0]
    fields = dict(block.fields)
    del fields["caption"]
    deck = replace(
        chart_case.deck,
        slides=(replace(slide, blocks=(replace(block, fields=fields),)),),
    )
    case = replace(chart_case, deck=deck)

    with pytest.raises(CoverageError) as error:
        _render(case, theme, target=OutputTarget.PPTX)

    assert error.value.report.missing_keys == ("s01.chart1.caption",)


@pytest.mark.parametrize(
    "target",
    [OutputTarget.PPTX, OutputTarget.PDF, OutputTarget.SLIDES],
)
def test_chart_render_has_no_timing_or_transition(chart_case, theme, target) -> None:
    result = _render(chart_case, theme, target=target)

    assert forbidden_node_paths(result.artifact_path) == ()


def test_native_chart_render_is_deterministic_and_normalizes_workbook(
    chart_case,
    theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_workbook_clock(monkeypatch, datetime(2020, 1, 1, tzinfo=UTC))
    first = _render(chart_case, theme, target=OutputTarget.PPTX)
    _patch_workbook_clock(monkeypatch, datetime(2021, 2, 3, tzinfo=UTC))
    second = _render(chart_case, theme, target=OutputTarget.PPTX)

    assert first.content_hash == second.content_hash

    presentation = Presentation(str(second.artifact_path))
    shape = _chart_shape(second)
    chart = cast(GraphicFrame, shape).chart
    assert tuple(str(category) for category in chart.plots[0].categories) == ("Q1", "Q2")
    assert tuple(tuple(float(value) for value in series.values) for series in chart.series) == (
        (1.0, 2.0),
        (3.0, 4.0),
    )
    assert len(presentation.slides) == 1

    with zipfile.ZipFile(io.BytesIO(_embedded_workbook(second.artifact_path))) as workbook:
        core = etree.fromstring(workbook.read("docProps/core.xml"))
        assert _core_timestamp(core, "created") == FIXED_CORE_TIMESTAMP
        assert _core_timestamp(core, "modified") == FIXED_CORE_TIMESTAMP
        assert {info.date_time for info in workbook.infolist()} == {FIXED_ZIP_TIMESTAMP}


def test_normalize_embedded_workbooks_is_idempotent(chart_case, theme) -> None:
    result = _render(chart_case, theme, target=OutputTarget.PPTX)
    workbook_name = "ppt/embeddings/Microsoft_Excel_Sheet1.xlsx"

    assert normalize_embedded_workbooks(result.artifact_path) == (workbook_name,)
    digest = content_hash(result.artifact_path)
    workbook = _embedded_workbook(result.artifact_path)

    assert normalize_embedded_workbooks(result.artifact_path) == (workbook_name,)
    assert content_hash(result.artifact_path) == digest
    assert _embedded_workbook(result.artifact_path) == workbook
