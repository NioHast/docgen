"""Tes kontrak bentuk dataclass AutoOffice F0."""

from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Literal

import pytest

from autooffice.deck.blocks.registry import block_specs
from autooffice.deck.blocks.spec import BlockSpec
from autooffice.deck.layout.spec import (
    LayoutPlan,
    LayoutSpec,
    PlacedBlock,
    SlideLayout,
    SlotSpec,
)
from autooffice.deck.model.deck_ir import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyKind,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.render.protocol import (
    CoverageReport,
    OutputTarget,
    RenderRequest,
    RenderResult,
)
from autooffice.design.theme import (
    ChartPalette,
    CodeTokens,
    GridTokens,
    RadiusTokens,
    ShadowTokens,
    SpacingTokens,
    Theme,
    ThemeColors,
    Typography,
)

EXPECTED_BLOCK_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], bool]] = {
    "text": (("text",), ("heading", "role"), ("text", "heading"), True),
    "bullets": (("items",), ("ordered",), ("itemN.text",), True),
    "image": (("path", "alt"), ("caption", "fit"), ("caption",), True),
    "table": (
        ("columns", "rows"),
        ("caption", "emphasis_column"),
        ("caption", "hN", "rN.cM"),
        True,
    ),
    "chart": (
        ("kind", "title", "alt", "categories", "series"),
        ("orientation", "unit", "caption"),
        ("title", "catN", "seriesN.name", "seriesN.valueN", "caption"),
        True,
    ),
    "code": (("code",), ("language", "filename", "line_numbers"), ("code", "filename"), True),
    "quote": (("text",), ("attribution",), ("text", "attribution"), True),
    "diagram": (("source", "alt"), ("caption",), ("caption",), True),
    "divider": ((), (), (), False),
    "spacer": ((), ("size",), (), False),
    "metric": (
        ("label", "value"),
        ("caption", "status"),
        ("label", "value", "caption"),
        True,
    ),
}

EXACT_FIELDS: tuple[tuple[type, dict[str, object]], ...] = (
    (
        KeyBinding,
        {
            "key": str,
            "slide_id": str,
            "block_id": str | None,
            "leaf": str,
            "kind": KeyKind,
            "sync": bool,
            "yaml_path": tuple[str | int, ...],
            "value": str | int | float,
            "plain_text": str,
        },
    ),
    (KeyManifest, {"bindings": tuple[KeyBinding, ...]}),
    (
        BlockIR,
        {
            "block_id": str,
            "block_type": str,
            "span": int | None,
            "role": str | None,
            "fields": Mapping[str, object],
        },
    ),
    (
        SlideIR,
        {
            "slide_id": str,
            "layout": str,
            "order": int,
            "blocks": tuple[BlockIR, ...],
            "notes": str | None,
            "source": Mapping[str, str] | None,
        },
    ),
    (
        DeckIR,
        {
            "schema": str,
            "meta": Mapping[str, str],
            "theme_name": str,
            "slides": tuple[SlideIR, ...],
            "keys": KeyManifest,
        },
    ),
    (
        BlockSpec,
        {
            "block_type": str,
            "required": tuple[str, ...],
            "optional": tuple[str, ...],
            "key_leaves": tuple[str, ...],
            "allowed_in_preset": bool,
        },
    ),
    (
        SlotSpec,
        {
            "slot_id": str,
            "required": bool,
            "block_types": tuple[str, ...],
            "role": str | None,
        },
    ),
    (
        LayoutSpec,
        {
            "layout_id": str,
            "slots": tuple[SlotSpec, ...],
            "rows": tuple[tuple[str, ...], ...],
            "accepts_source": bool,
        },
    ),
    (
        PlacedBlock,
        {
            "block_id": str,
            "left_emu": int,
            "top_emu": int,
            "width_emu": int,
            "height_emu": int,
        },
    ),
    (
        SlideLayout,
        {
            "slide_id": str,
            "boxes": tuple[PlacedBlock, ...],
            "overflow_keys": tuple[str, ...],
        },
    ),
    (LayoutPlan, {"slides": tuple[SlideLayout, ...]}),
    (
        ThemeColors,
        {
            "background": str,
            "surface": str,
            "surface_alt": str,
            "ink": str,
            "ink_secondary": str,
            "muted": str,
            "border": str,
            "accent": str,
            "accent_deep": str,
            "accent_soft": str,
            "accent_line": str,
            "accent_ink": str,
            "status": Mapping[str, str],
        },
    ),
    (
        ChartPalette,
        {
            "series": tuple[str, str, str, str],
            "grid": str,
            "axis": str,
            "legend": str,
            "title": str,
        },
    ),
    (
        Typography,
        {
            "family": str,
            "weights": tuple[int, int, int, int],
            "title_pt": float,
            "body_pt": float,
            "minimum_pt": float,
            "line_height": float,
            "tracking_em": float,
        },
    ),
    (
        GridTokens,
        {
            "columns": int,
            "gutter_emu": int,
            "margin_left_emu": int,
            "margin_right_emu": int,
            "margin_top_emu": int,
            "margin_bottom_emu": int,
            "row_gap_emu": int,
            "slide_width_emu": int,
            "slide_height_emu": int,
        },
    ),
    (
        SpacingTokens,
        {
            "sm_emu": int,
            "md_emu": int,
            "lg_emu": int,
            "card_padding_emu": int,
            "divider_emu": int,
        },
    ),
    (
        RadiusTokens,
        {
            "sm_emu": int,
            "md_emu": int,
            "lg_emu": int,
        },
    ),
    (
        ShadowTokens,
        {
            "card": str,
            "overlay": str,
            "none": str,
        },
    ),
    (
        CodeTokens,
        {
            "family": str,
            "size_pt": float,
            "line_height": float,
        },
    ),
    (
        Theme,
        {
            "name": str,
            "mode": Literal["light"],
            "colors": ThemeColors,
            "chart": ChartPalette,
            "typography": Typography,
            "grid": GridTokens,
            "spacing": SpacingTokens,
            "radius": RadiusTokens,
            "shadow": ShadowTokens,
            "code": CodeTokens,
        },
    ),
    (
        CoverageReport,
        {
            "missing_keys": tuple[str, ...],
            "duplicate_keys": tuple[str, ...],
            "unkeyed_visible": tuple[str, ...],
            "missing_alt": tuple[str, ...],
        },
    ),
    (
        RenderRequest,
        {
            "deck": DeckIR,
            "layout": LayoutPlan,
            "theme": Theme,
            "target": OutputTarget,
            "workspace": Path,
        },
    ),
    (
        RenderResult,
        {
            "artifact_path": Path,
            "coverage": CoverageReport,
            "warnings": tuple[str, ...],
            "content_hash": str,
            "target_metadata": Mapping[str, str],
        },
    ),
)


def _binding() -> KeyBinding:
    return KeyBinding(
        key="s01.title.text",
        slide_id="s01",
        block_id="title",
        leaf="text",
        kind="text",
        sync=True,
        yaml_path=("slides", 0, "blocks", 0, "text"),
        value="Judul",
        plain_text="Judul",
    )


def _manifest() -> KeyManifest:
    return KeyManifest(bindings=(_binding(),))


def _block() -> BlockIR:
    return BlockIR(
        block_id="title",
        block_type="text",
        span=None,
        role="title",
        fields={"text": "Judul"},
    )


def _slide() -> SlideIR:
    return SlideIR(
        slide_id="s01",
        layout="cover",
        order=0,
        blocks=(_block(),),
        notes="Catatan pembicara.",
        source={"text": "Sumber internal", "url": "https://example.com/sumber"},
    )


def _deck() -> DeckIR:
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Demo", "author": "Tim AutoOffice"},
        theme_name="indigo",
        slides=(_slide(),),
        keys=_manifest(),
    )


def _block_spec() -> BlockSpec:
    return BlockSpec(
        block_type="divider",
        required=(),
        optional=(),
        key_leaves=(),
        allowed_in_preset=False,
    )


def _slot_spec() -> SlotSpec:
    return SlotSpec(
        slot_id="title",
        required=True,
        block_types=("text",),
        role="title",
    )


def _layout_spec() -> LayoutSpec:
    return LayoutSpec(
        layout_id="cover",
        slots=(_slot_spec(),),
        rows=(("title",),),
        accepts_source=True,
    )


def _placed_block() -> PlacedBlock:
    return PlacedBlock(
        block_id="title",
        left_emu=914400,
        top_emu=609600,
        width_emu=5486400,
        height_emu=1828800,
    )


def _slide_layout() -> SlideLayout:
    return SlideLayout(
        slide_id="s01",
        boxes=(_placed_block(),),
        overflow_keys=(),
    )


def _layout_plan() -> LayoutPlan:
    return LayoutPlan(slides=(_slide_layout(),))


def _theme_colors() -> ThemeColors:
    return ThemeColors(
        background="#FFFFFF",
        surface="#FFFFFF",
        surface_alt="#F9FAFB",
        ink="#111827",
        ink_secondary="#374151",
        muted="#6B7280",
        border="#E5E7EB",
        accent="#4F46E5",
        accent_deep="#4338CA",
        accent_soft="#EEF2FF",
        accent_line="#C7D2FE",
        accent_ink="#FFFFFF",
        status={
            "neutral": "#374151",
            "success": "#0F766E",
            "warning": "#B45309",
            "danger": "#BE123C",
        },
    )


def _chart_palette() -> ChartPalette:
    return ChartPalette(
        series=("#4F46E5", "#0F766E", "#B45309", "#BE123C"),
        grid="#E5E7EB",
        axis="#6B7280",
        legend="#374151",
        title="#111827",
    )


def _typography() -> Typography:
    return Typography(
        family="Plus Jakarta Sans",
        weights=(400, 600, 700, 800),
        title_pt=30.0,
        body_pt=16.5,
        minimum_pt=10.0,
        line_height=1.2,
        tracking_em=-0.01,
    )


def _grid_tokens() -> GridTokens:
    return GridTokens(
        columns=12,
        gutter_emu=228600,
        margin_left_emu=914400,
        margin_right_emu=914400,
        margin_top_emu=609600,
        margin_bottom_emu=609600,
        row_gap_emu=182880,
        slide_width_emu=12192000,
        slide_height_emu=6858000,
    )


def _spacing_tokens() -> SpacingTokens:
    return SpacingTokens(
        sm_emu=91440,
        md_emu=182880,
        lg_emu=274320,
        card_padding_emu=274320,
        divider_emu=12700,
    )


def _radius_tokens() -> RadiusTokens:
    return RadiusTokens(
        sm_emu=45720,
        md_emu=91440,
        lg_emu=182880,
    )


def _shadow_tokens() -> ShadowTokens:
    return ShadowTokens(
        card="0 1 2 0 rgba(17, 24, 39, 0.08)",
        overlay="0 8 24 0 rgba(17, 24, 39, 0.16)",
        none="none",
    )


def _code_tokens() -> CodeTokens:
    return CodeTokens(
        family="ui-monospace, 'Cascadia Mono', Consolas, monospace",
        size_pt=10.5,
        line_height=1.35,
    )


def _theme() -> Theme:
    return Theme(
        name="indigo",
        mode="light",
        colors=_theme_colors(),
        chart=_chart_palette(),
        typography=_typography(),
        grid=_grid_tokens(),
        spacing=_spacing_tokens(),
        radius=_radius_tokens(),
        shadow=_shadow_tokens(),
        code=_code_tokens(),
    )


def _coverage() -> CoverageReport:
    return CoverageReport(
        missing_keys=(),
        duplicate_keys=(),
        unkeyed_visible=(),
        missing_alt=(),
    )


def _request() -> RenderRequest:
    return RenderRequest(
        deck=_deck(),
        layout=_layout_plan(),
        theme=_theme(),
        target=OutputTarget.PPTX,
        workspace=Path("build"),
    )


def _result() -> RenderResult:
    return RenderResult(
        artifact_path=Path("build/deck.pptx"),
        coverage=_coverage(),
        warnings=(),
        content_hash="abc123",
        target_metadata={"slide_count": "1"},
    )


@pytest.mark.parametrize(
    ("dataclass_type", "expected"),
    EXACT_FIELDS,
    ids=[dataclass_type.__name__ for dataclass_type, _ in EXACT_FIELDS],
)
def test_dataclass_fields_match_contract(
    dataclass_type: type,
    expected: dict[str, object],
) -> None:
    actual = {field.name: field.type for field in fields(dataclass_type)}
    assert actual == expected


FROZEN_CASES: tuple[tuple[Callable[[], object], str], ...] = (
    (_binding, "key"),
    (_manifest, "bindings"),
    (_block, "block_id"),
    (_slide, "slide_id"),
    (_deck, "schema"),
    (_block_spec, "block_type"),
    (_slot_spec, "slot_id"),
    (_layout_spec, "layout_id"),
    (_placed_block, "block_id"),
    (_slide_layout, "slide_id"),
    (_layout_plan, "slides"),
    (_theme_colors, "accent"),
    (_chart_palette, "series"),
    (_typography, "family"),
    (_grid_tokens, "columns"),
    (_spacing_tokens, "sm_emu"),
    (_radius_tokens, "sm_emu"),
    (_shadow_tokens, "card"),
    (_code_tokens, "family"),
    (_theme, "name"),
    (_coverage, "missing_keys"),
    (_request, "target"),
    (_result, "content_hash"),
)


@pytest.mark.parametrize(
    ("factory", "field_name"),
    FROZEN_CASES,
    ids=[field_name for _, field_name in FROZEN_CASES],
)
def test_frozen_instance_rejects_assignment(
    factory: Callable[[], object],
    field_name: str,
) -> None:
    instance = factory()
    with pytest.raises(FrozenInstanceError):
        type(instance).__setattr__(instance, field_name, object())


def test_block_specs_match_plan() -> None:
    actual = {
        spec.block_type: (spec.required, spec.optional, spec.key_leaves, spec.allowed_in_preset)
        for spec in block_specs()
    }
    assert tuple(actual) == tuple(EXPECTED_BLOCK_SPECS)
    assert actual == EXPECTED_BLOCK_SPECS


def test_only_divider_and_spacer_are_disallowed_in_preset() -> None:
    flags = {spec.block_type: spec.allowed_in_preset for spec in block_specs()}
    assert flags["divider"] is False
    assert flags["spacer"] is False
    assert all(
        allowed for block_type, allowed in flags.items() if block_type not in {"divider", "spacer"}
    )


def test_deck_meta_is_read_only() -> None:
    deck = _deck()
    with pytest.raises(TypeError):
        deck.meta["title"] = "Berubah"


def test_block_fields_are_read_only() -> None:
    block = _block()
    with pytest.raises(TypeError):
        block.fields["text"] = "Berubah"


def test_slide_source_is_read_only() -> None:
    source = _slide().source
    assert source is not None
    with pytest.raises(TypeError):
        source["text"] = "Berubah"


def test_theme_status_is_read_only() -> None:
    colors = _theme_colors()
    with pytest.raises(TypeError):
        colors.status["success"] = "#000000"


def test_render_target_metadata_is_read_only() -> None:
    result = _result()
    with pytest.raises(TypeError):
        result.target_metadata["slide_count"] = "2"


def test_slide_source_requires_text() -> None:
    with pytest.raises(ValueError, match="text"):
        SlideIR(
            slide_id="s01",
            layout="cover",
            order=0,
            blocks=(),
            notes=None,
            source={"url": "https://example.com"},
        )


def test_slide_source_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="url"):
        SlideIR(
            slide_id="s01",
            layout="cover",
            order=0,
            blocks=(),
            notes=None,
            source={"text": "Sumber", "url": "https://example.com", "credit": "Tim"},
        )


def test_chart_palette_has_exactly_four_series_colors() -> None:
    palette = _chart_palette()
    assert len(palette.series) == 4
    assert all(isinstance(color, str) for color in palette.series)


def test_coverage_report_ok_when_no_findings() -> None:
    assert _coverage().ok is True


@pytest.mark.parametrize(
    "report",
    [
        CoverageReport(("s01.title.text",), (), (), ()),
        CoverageReport((), ("s01.title.text",), (), ()),
        CoverageReport((), (), ("s01.title.text",), ()),
        CoverageReport((), (), (), ("s01.image1",)),
    ],
    ids=["missing-keys", "duplicate-keys", "unkeyed-visible", "missing-alt"],
)
def test_coverage_report_not_ok_when_any_finding_exists(report: CoverageReport) -> None:
    assert report.ok is False


def test_output_target_members() -> None:
    assert tuple(OutputTarget) == (OutputTarget.PPTX, OutputTarget.PDF, OutputTarget.SLIDES)
    assert tuple(target.value for target in OutputTarget) == ("pptx", "pdf", "slides")


def test_deck_and_key_manifest_are_constructible() -> None:
    deck = _deck()
    assert deck.schema == "autooffice.deck/v1"
    assert deck.meta == {"title": "Demo", "author": "Tim AutoOffice"}
    assert deck.theme_name == "indigo"
    assert deck.slides[0].slide_id == "s01"
    assert deck.slides[0].order == 0
    assert deck.slides[0].blocks[0].fields == {"text": "Judul"}
    assert deck.keys.keys() == ("s01.title.text",)


def test_deck_slide_order_matches_index() -> None:
    second = SlideIR(
        slide_id="s02",
        layout="content",
        order=1,
        blocks=(),
        notes=None,
        source=None,
    )
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={},
        theme_name="indigo",
        slides=(_slide(), second),
        keys=KeyManifest(bindings=()),
    )

    assert tuple(slide.order for slide in deck.slides) == (0, 1)
    assert all(slide.order == index for index, slide in enumerate(deck.slides))


def test_deck_rejects_slide_order_not_matching_index() -> None:
    duplicate_order = SlideIR(
        slide_id="s02",
        layout="content",
        order=0,
        blocks=(),
        notes=None,
        source=None,
    )

    with pytest.raises(ValueError, match=r"s02.*order 0.*1"):
        DeckIR(
            schema="autooffice.deck/v1",
            meta={},
            theme_name="indigo",
            slides=(_slide(), duplicate_order),
            keys=KeyManifest(bindings=()),
        )


def test_theme_and_render_contracts_are_constructible() -> None:
    theme = _theme()
    request = _request()
    result = _result()

    assert theme.name == "indigo"
    assert theme.mode == "light"
    assert theme.chart.series == ("#4F46E5", "#0F766E", "#B45309", "#BE123C")
    assert request.target is OutputTarget.PPTX
    assert request.workspace == Path("build")
    assert result.coverage.ok is True
    assert result.target_metadata == {"slide_count": "1"}


def test_theme_exposes_extended_tokens() -> None:
    theme = _theme()

    assert theme.grid.slide_width_emu == 12192000
    assert theme.grid.slide_height_emu == 6858000
    assert theme.grid.row_gap_emu == 182880
    assert theme.typography.tracking_em == -0.01
    assert theme.spacing.divider_emu == 12700
    assert theme.radius == RadiusTokens(sm_emu=45720, md_emu=91440, lg_emu=182880)
    assert theme.shadow.card == "0 1 2 0 rgba(17, 24, 39, 0.08)"
    assert theme.shadow.overlay == "0 8 24 0 rgba(17, 24, 39, 0.16)"
    assert theme.shadow.none == "none"
    assert theme.code.family == "ui-monospace, 'Cascadia Mono', Consolas, monospace"
    assert theme.code.size_pt == 10.5
    assert theme.code.line_height == 1.35
