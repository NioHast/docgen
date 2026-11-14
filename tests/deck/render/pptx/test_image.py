"""Tes crop native, contain, WebP, dan alt text gambar."""

from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from autooffice.deck.layout.spec import LayoutPlan, PlacedBlock, SlideLayout
from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyManifest, SlideIR
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.image import (
    contain_geometry,
    cover_crop,
    image_size,
    resolve_asset_path,
)
from autooffice.deck.render.pptx.shapes import Box, PptxRenderError
from autooffice.deck.render.protocol import OutputTarget, RenderRequest


def test_cover_crop_uses_native_proportional_crop() -> None:
    left, top, right, bottom = cover_crop(400, 200, 100, 100)

    assert left == pytest.approx(0.25)
    assert right == pytest.approx(0.25)
    assert top == 0.0
    assert bottom == 0.0


def test_cover_crop_vertical_for_tall_box() -> None:
    left, top, right, bottom = cover_crop(200, 400, 100, 100)

    assert left == 0.0
    assert right == 0.0
    assert top == pytest.approx(0.25)
    assert bottom == pytest.approx(0.25)


def test_contain_geometry_preserves_aspect_ratio_and_centers() -> None:
    box = Box(left=10, top=20, width=400, height=400)

    left, top, width, height = contain_geometry(200, 100, box)

    assert width == 400
    assert height == 200
    assert left == 10
    assert top == 120


def test_resolve_asset_path_rejects_traversal(workspace: Path) -> None:
    with pytest.raises(PptxRenderError, match="keluar dari workspace"):
        resolve_asset_path(workspace, "../secret.png")


def test_resolve_asset_path_rejects_missing_file(workspace: Path) -> None:
    with pytest.raises(PptxRenderError, match="tidak ditemukan"):
        resolve_asset_path(workspace, "assets/missing.png")


def test_webp_is_normalized_and_alt_text_is_written(workspace: Path, theme) -> None:
    assets = workspace / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (300, 150), (90, 30, 60)).save(assets / "hero.webp")
    block = BlockIR(
        "image1",
        "image",
        None,
        None,
        {
            "path": "assets/hero.webp",
            "alt": "Diagram alur build",
            "fit": "contain",
        },
    )
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "WebP Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "content", 0, (block,), None, None),),
        keys=KeyManifest(()),
    )
    layout = LayoutPlan(
        (
            SlideLayout(
                "s01",
                (PlacedBlock("image1", 914400, 609600, 5000000, 2000000),),
                (),
            ),
        )
    )
    result = PptxRenderer().render(
        RenderRequest(
            deck=deck,
            layout=layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=workspace,
        )
    )
    presentation = Presentation(str(result.artifact_path))
    picture = next(
        shape
        for shape in presentation.slides[0].shapes
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE
    )
    node = picture._element.find(".//" + qn("p:cNvPr"))

    assert result.coverage.ok is True
    assert node is not None
    assert node.get("descr") == "Diagram alur build"
    assert picture.crop_left == 0.0
    assert picture.crop_top == 0.0


def test_image_size_reads_bounded_dimensions(workspace: Path) -> None:
    assets = workspace / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    path = assets / "sized.png"
    Image.new("RGB", (64, 32), (1, 2, 3)).save(path)

    assert image_size(path) == (64, 32)
