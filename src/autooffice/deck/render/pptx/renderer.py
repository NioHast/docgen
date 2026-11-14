"""Renderer PPTX utama yang menggambar DeckIR dan LayoutPlan."""

import os
import re
import tempfile
from pathlib import Path

from pptx import Presentation as PresentationFactory
from pptx.enum.shapes import MSO_SHAPE
from pptx.slide import Slide
from pptx.util import Emu

from autooffice.deck.charts.spec import ChartSpec, build_chart_spec
from autooffice.deck.layout.spec import PlacedBlock
from autooffice.deck.model.deck_ir import BlockIR, SlideIR
from autooffice.deck.render.protocol import OutputTarget, RenderRequest, RenderResult
from autooffice.design.theme import Theme

from . import chart as chart_renderer
from . import diagram as diagram_renderer
from . import image as image_renderer
from . import table as table_renderer
from . import textbox as text_renderer
from .coverage import collect_coverage, raise_if_incomplete
from .fonts import FontEmbeddingResult, embed_fonts
from .notes import set_notes
from .shapes import (
    CHART_MARKER,
    Box,
    PptxRenderError,
    add_extension_keys,
    box_from_placed,
    c_nv_pr,
    field_optional_text,
    rgb,
    set_chrome_shape,
    validate_box_within_slide,
)
from .theme import apply_slide_background, blank_layout, new_presentation
from .xml import (
    assert_no_forbidden_nodes,
    content_hash,
    normalize_embedded_workbooks,
    remove_animation_nodes,
    validate_package,
)

_CHART_PLACEHOLDER_WARNING = (
    "chart: {count} chart memakai placeholder {marker}<chart_id> untuk target slides; "
    "placeholder diganti linked chart oleh lane Google."
)
_PDF_WARNING = (
    "target pdf: PptxRenderer hanya menghasilkan PPTX intermediate; konversi PDF "
    "ditangani lane PDF."
)


class PptxRenderer:
    """Implementasi ``DeckRenderer`` untuk artefak PPTX native."""

    def render(self, request: RenderRequest) -> RenderResult:
        """Render satu deck dan kembalikan artefak beserta coverage."""
        _validate_request(request)
        presentation = new_presentation(
            request.theme,
            deck_title=request.deck.meta.get("title", ""),
            author=request.deck.meta.get("author", ""),
        )
        chart_count = 0
        for slide_ir, slide_layout in zip(request.deck.slides, request.layout.slides, strict=True):
            slide = presentation.slides.add_slide(blank_layout(presentation))
            apply_slide_background(slide, request.theme)
            blocks = {block.block_id: block for block in slide_ir.blocks}
            for placed in slide_layout.boxes:
                block = blocks[placed.block_id]
                chart_count += _render_block(
                    slide,
                    slide_ir,
                    block,
                    placed,
                    request.theme,
                    target=request.target,
                    workspace=request.workspace,
                )
            if slide_ir.source is not None:
                text_renderer.render_source_text(
                    slide,
                    slide_ir.slide_id,
                    dict(slide_ir.source),
                    request.theme,
                )
            if slide_ir.notes:
                set_notes(
                    slide,
                    slide_ir.notes,
                    slide_id=slide_ir.slide_id,
                    theme=request.theme,
                )
        remove_animation_nodes(presentation)
        warnings: list[str] = []
        if request.target == OutputTarget.PDF:
            warnings.append(_PDF_WARNING)
        if chart_count and request.target == OutputTarget.SLIDES:
            warnings.append(
                _CHART_PLACEHOLDER_WARNING.format(count=chart_count, marker=CHART_MARKER)
            )

        artifact_path = _artifact_path(request)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = _temporary_path(artifact_path)
        try:
            presentation.save(str(temporary))
            coverage = collect_coverage(PresentationFactory(str(temporary)), request.deck)
            raise_if_incomplete(coverage)
            font_result = embed_fonts(temporary, request.theme)
            if request.target != OutputTarget.SLIDES:
                warnings.extend(font_result.warnings)
            normalize_embedded_workbooks(temporary)
            assert_no_forbidden_nodes(temporary)
            validate_package(temporary)
            digest = content_hash(temporary)
            os.replace(temporary, artifact_path)
        finally:
            temporary.unlink(missing_ok=True)
        return RenderResult(
            artifact_path=artifact_path,
            coverage=coverage,
            warnings=tuple(warnings),
            content_hash=digest,
            target_metadata=_target_metadata(
                request,
                chart_count=chart_count,
                font_result=font_result,
                slide_count=len(request.deck.slides),
            ),
        )


def _render_block(
    slide: Slide,
    slide_ir: SlideIR,
    block: BlockIR,
    placed: PlacedBlock,
    theme: Theme,
    *,
    target: OutputTarget,
    workspace: Path,
) -> int:
    box = box_from_placed(placed)
    validate_box_within_slide(
        box,
        slide_width_emu=theme.grid.slide_width_emu,
        slide_height_emu=theme.grid.slide_height_emu,
    )
    block_type = block.block_type
    if block_type == "text":
        text_renderer.render_text_block(slide, block, box, theme, slide_id=slide_ir.slide_id)
    elif block_type == "bullets":
        text_renderer.render_bullets_block(slide, block, box, theme, slide_id=slide_ir.slide_id)
    elif block_type == "quote":
        text_renderer.render_quote_block(slide, block, box, theme, slide_id=slide_ir.slide_id)
    elif block_type == "metric":
        text_renderer.render_metric_block(slide, block, box, theme, slide_id=slide_ir.slide_id)
    elif block_type == "code":
        text_renderer.render_code_block(slide, block, box, theme, slide_id=slide_ir.slide_id)
    elif block_type == "table":
        table_renderer.render_table_block(slide, block, box, theme, slide_id=slide_ir.slide_id)
    elif block_type == "image":
        image_renderer.render_image_block(
            slide,
            block,
            box,
            theme,
            slide_id=slide_ir.slide_id,
            workspace=workspace,
        )
    elif block_type == "chart":
        _render_chart(slide, slide_ir, block, box, theme, target=target)
        return 1
    elif block_type == "divider":
        _render_divider(slide, block, box, theme)
    elif block_type == "spacer":
        return 0
    elif block_type == "diagram":
        diagram_renderer.render_diagram_block(
            slide,
            block,
            box,
            theme,
            slide_id=slide_ir.slide_id,
            workspace=workspace,
        )
    else:
        raise PptxRenderError(
            f"Slide '{slide_ir.slide_id}', block '{block.block_id}': "
            f"block type '{block_type}' tidak didukung renderer PPTX."
        )
    return 0


def _render_chart(
    slide: Slide,
    slide_ir: SlideIR,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    target: OutputTarget,
) -> None:
    spec = build_chart_spec(block, slide_id=slide_ir.slide_id)
    shape = chart_renderer.render_chart(
        slide,
        spec,
        theme,
        left=box.left,
        top=box.top,
        width=box.width,
        height=box.height,
        placeholder=target == OutputTarget.SLIDES,
        caption=field_optional_text(block.fields, "caption"),
    )
    node = c_nv_pr(shape)
    if node is not None:
        add_extension_keys(node, _chart_keys(spec))


def _chart_keys(spec: ChartSpec) -> tuple[str, ...]:
    """Turunkan key metadata chart; caption dihitung dari shape nyata."""
    keys = [f"{spec.chart_id}.title"]
    keys.extend(f"{spec.chart_id}.cat{index}" for index in range(1, len(spec.categories) + 1))
    for series_index, series in enumerate(spec.series, start=1):
        keys.append(f"{spec.chart_id}.series{series_index}.name")
        keys.extend(
            f"{spec.chart_id}.series{series_index}.value{value_index}"
            for value_index in range(1, len(series.values) + 1)
        )
    return tuple(keys)


def _render_divider(slide: Slide, block: BlockIR, box: Box, theme: Theme) -> None:
    height = min(box.height, max(1, theme.spacing.divider_emu))
    top = box.top + (box.height - height) // 2
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Emu(box.left),
        Emu(top),
        Emu(box.width),
        Emu(height),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(theme.colors.accent_line)
    shape.line.fill.background()
    shape.shadow.inherit = False
    set_chrome_shape(shape, f"divider:{block.block_id}")


def _target_metadata(
    request: RenderRequest,
    *,
    chart_count: int,
    font_result: FontEmbeddingResult,
    slide_count: int,
) -> dict[str, str]:
    return {
        "renderer": "pptx",
        "target": request.target.value,
        "theme": request.theme.name,
        "slides": str(slide_count),
        "chart_rendering": (
            "none"
            if not chart_count
            else "placeholder"
            if request.target == OutputTarget.SLIDES
            else "native"
        ),
        "font_embedding": (
            "google" if request.target == OutputTarget.SLIDES else font_result.status
        ),
    }


def _artifact_path(request: RenderRequest) -> Path:
    title = request.deck.meta.get("title", "")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "deck"
    return request.workspace / f"{slug}.pptx"


def _temporary_path(artifact_path: Path) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix=".autooffice-",
        suffix=".pptx",
        dir=artifact_path.parent,
    )
    os.close(descriptor)
    return Path(name)


def _validate_request(request: RenderRequest) -> None:
    if not request.deck.slides:
        raise PptxRenderError(f"Deck untuk target '{request.target.value}' tidak memiliki slide.")
    if len(request.layout.slides) != len(request.deck.slides):
        raise PptxRenderError(
            f"LayoutPlan memiliki {len(request.layout.slides)} slide; DeckIR memiliki "
            f"{len(request.deck.slides)} slide."
        )
    for slide_ir, slide_layout in zip(request.deck.slides, request.layout.slides, strict=True):
        if slide_ir.slide_id != slide_layout.slide_id:
            raise PptxRenderError(
                f"Urutan slide tidak cocok: DeckIR '{slide_ir.slide_id}', "
                f"LayoutPlan '{slide_layout.slide_id}'."
            )
        if slide_layout.overflow_keys:
            raise PptxRenderError(
                f"Slide '{slide_ir.slide_id}' masih memiliki overflow: "
                f"{', '.join(slide_layout.overflow_keys)}."
            )
        block_ids = [block.block_id for block in slide_ir.blocks]
        placed_ids = [placed.block_id for placed in slide_layout.boxes]
        duplicates = sorted({block_id for block_id in placed_ids if placed_ids.count(block_id) > 1})
        if duplicates:
            raise PptxRenderError(
                f"Slide '{slide_ir.slide_id}' menempatkan block lebih dari sekali: "
                f"{', '.join(duplicates)}."
            )
        missing = sorted(set(block_ids) - set(placed_ids))
        unknown = sorted(set(placed_ids) - set(block_ids))
        if missing:
            raise PptxRenderError(
                f"Slide '{slide_ir.slide_id}' tidak memiliki kotak layout untuk block: "
                f"{', '.join(missing)}."
            )
        if unknown:
            raise PptxRenderError(
                f"Slide '{slide_ir.slide_id}' memiliki kotak layout untuk block asing: "
                f"{', '.join(unknown)}."
            )


__all__ = ["PptxRenderer"]
