"""Tes cabang edge gambar: path, crop, dimensi, caption, dan WebP rusak."""

from pathlib import Path

import pytest
from _edge_helpers import new_slide

from autooffice.deck.model.deck_ir import BlockIR
from autooffice.deck.render.pptx import image as image_module
from autooffice.deck.render.pptx.image import (
    _media_boxes,
    _picture_source,
    contain_geometry,
    cover_crop,
    image_size,
    render_image_block,
    resolve_asset_path,
)
from autooffice.deck.render.pptx.shapes import Box, PptxRenderError


def test_resolve_asset_path_rejects_empty_path(workspace: Path) -> None:
    with pytest.raises(PptxRenderError, match="tidak boleh kosong"):
        resolve_asset_path(workspace, "")


def test_resolve_asset_path_rejects_backslash(workspace: Path) -> None:
    with pytest.raises(PptxRenderError, match="memakai '/'"):
        resolve_asset_path(workspace, "assets\\hero.png")


@pytest.mark.parametrize("relative_path", ["/etc/hero.png", "https://example.com/hero.png"])
def test_resolve_asset_path_rejects_absolute_and_scheme(
    workspace: Path,
    relative_path: str,
) -> None:
    with pytest.raises(PptxRenderError, match="harus relatif"):
        resolve_asset_path(workspace, relative_path)


def test_resolve_asset_path_rejects_unknown_suffix(workspace: Path) -> None:
    with pytest.raises(PptxRenderError, match="berekstensi png, jpg, jpeg, atau webp"):
        resolve_asset_path(workspace, "assets/hero.gif")


def test_resolve_asset_path_rejects_resolved_escape(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (workspace / "assets").mkdir(parents=True, exist_ok=True)
    outside = workspace.parent / "outside.png"
    original_resolve = Path.resolve

    def fake_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "hero.png":
            return outside
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)

    with pytest.raises(PptxRenderError, match="keluar dari workspace"):
        resolve_asset_path(workspace, "assets/hero.png")


@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
def test_resolve_asset_path_wraps_resolve_error(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[OSError | RuntimeError],
) -> None:
    assets = workspace / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "hero.png").write_bytes(b"png")
    original_resolve = Path.resolve

    def fake_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "hero.png":
            raise error_type("symlink loop")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)

    with pytest.raises(
        PptxRenderError,
        match=r"assets/hero\.png.*tidak dapat di-resolve",
    ) as exc_info:
        resolve_asset_path(workspace, "assets/hero.png")

    assert isinstance(exc_info.value.__cause__, error_type)


@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
def test_render_image_block_wraps_resolve_error_with_context(
    workspace: Path,
    theme,
    hero_image: str,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[OSError | RuntimeError],
) -> None:
    original_resolve = Path.resolve

    def fake_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "hero.png":
            raise error_type("path terlalu panjang")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    block = BlockIR("image1", "image", None, None, {"path": hero_image, "alt": "Alt"})

    with pytest.raises(
        PptxRenderError,
        match=r"Slide 's01', block 'image1'.*assets/hero\.png",
    ):
        render_image_block(
            new_slide(),
            block,
            Box(left=0, top=0, width=1_000_000, height=1_000_000),
            theme,
            slide_id="s01",
            workspace=workspace,
        )


@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
def test_image_size_wraps_open_error_with_context(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[OSError | RuntimeError],
) -> None:
    path = workspace / "assets" / "hero.png"

    def fake_open(_: object) -> object:
        raise error_type("tidak dapat dibuka")

    monkeypatch.setattr(image_module.PILImage, "open", fake_open)

    with pytest.raises(
        PptxRenderError,
        match=r"Slide 's01', block 'image1'.*hero\.png.*tidak dapat dibuka",
    ):
        image_size(path, slide_id="s01", block_id="image1")


def test_resolve_asset_path_wraps_symlink_loop(workspace: Path) -> None:
    assets = workspace / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    link = assets / "loop.png"
    try:
        link.symlink_to(link)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Platform tidak mendukung symlink: {error}")
    try:
        with pytest.raises(PptxRenderError, match=r"assets/loop\.png"):
            resolve_asset_path(workspace, "assets/loop.png")
    finally:
        link.unlink(missing_ok=True)


def test_image_size_wraps_unreadable_image(workspace: Path) -> None:
    path = workspace / "rusak.png"
    path.write_bytes(b"bukan gambar")

    with pytest.raises(PptxRenderError, match="tidak dapat dibaca"):
        image_size(path)


def test_image_size_rejects_zero_dimensions(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ZeroImage:
        size = (0, 5)

        def __enter__(self) -> ZeroImage:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    monkeypatch.setattr(image_module.PILImage, "open", lambda path: ZeroImage())

    with pytest.raises(PptxRenderError, match="dimensi tidak valid"):
        image_size(workspace / "nol.png")


def test_cover_crop_rejects_zero_dimensions() -> None:
    with pytest.raises(PptxRenderError, match="harus positif"):
        cover_crop(0, 10, 10, 10)


def test_cover_crop_returns_zero_for_matching_ratio() -> None:
    assert cover_crop(400, 200, 100, 50) == (0.0, 0.0, 0.0, 0.0)


def test_contain_geometry_rejects_zero_image_dimensions() -> None:
    box = Box(left=0, top=0, width=100, height=100)

    with pytest.raises(PptxRenderError, match="Dimensi gambar harus positif"):
        contain_geometry(0, 10, box)


def test_render_image_block_rejects_unknown_fit(workspace: Path, theme, hero_image: str) -> None:
    block = BlockIR(
        "image1",
        "image",
        None,
        None,
        {"path": hero_image, "fit": "fill", "alt": "Alt"},
    )

    with pytest.raises(PptxRenderError, match="fit tidak dikenal"):
        render_image_block(
            new_slide(),
            block,
            Box(left=0, top=0, width=1_000_000, height=1_000_000),
            theme,
            slide_id="s01",
            workspace=workspace,
        )


def test_media_boxes_rejects_caption_without_media_room(theme) -> None:
    box = Box(left=0, top=0, width=1_000_000, height=1000)

    with pytest.raises(PptxRenderError, match="tidak menyisakan ruang media"):
        _media_boxes(box, "Caption yang panjang sekali", theme)


def test_picture_source_wraps_broken_webp(workspace: Path) -> None:
    path = workspace / "rusak.webp"
    path.write_bytes(b"bukan webp")

    with pytest.raises(PptxRenderError, match="WebP tidak dapat dikonversi"):
        _picture_source(path)
