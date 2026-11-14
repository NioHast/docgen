"""Tes validasi aset font dan penanda embedding final oleh CLI."""

from dataclasses import replace
from pathlib import Path

import pytest
from pptx import Presentation

from autooffice.deck.render.pptx import PptxRenderer, fonts
from autooffice.deck.render.pptx.fonts import (
    DEFERRED,
    FONT_EMBEDDING_WARNING,
    embed_fonts,
    embedded_fonts,
    font_files_for_theme,
)
from autooffice.deck.render.pptx.shapes import PptxRenderError
from autooffice.deck.render.protocol import OutputTarget, RenderRequest
from autooffice.design.fonts import FONT_HASHES, sha256


def _render_minimal(case, theme):
    return PptxRenderer().render(
        RenderRequest(
            deck=case.deck,
            layout=case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=case.workspace,
        )
    )


def test_bundled_font_files_are_valid_truetype(theme) -> None:
    paths = font_files_for_theme(theme)

    assert tuple(path.name for path in paths) == (
        "PlusJakartaSans-Regular.ttf",
        "PlusJakartaSans-SemiBold.ttf",
        "PlusJakartaSans-Bold.ttf",
        "PlusJakartaSans-ExtraBold.ttf",
    )
    assert all(path.is_file() for path in paths)
    assert all(path.read_bytes()[:4] in {b"\x00\x01\x00\x00", b"OTTO"} for path in paths)
    assert {path.name: sha256(path) for path in paths} == dict(FONT_HASHES)


def test_font_files_accept_family_stack_with_plus_jakarta_primary(theme) -> None:
    stacked = replace(
        theme,
        typography=replace(
            theme.typography,
            family="'Plus Jakarta Sans', 'Helvetica Neue', sans-serif",
        ),
    )

    assert font_files_for_theme(stacked) == font_files_for_theme(theme)


def test_font_files_reject_corrupted_byte_after_header(
    theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = font_files_for_theme(theme)[0]
    corrupted = bytearray(source.read_bytes())
    corrupted[64] ^= 0xFF
    path = tmp_path / source.name
    path.write_bytes(corrupted)
    monkeypatch.setattr(fonts, "font_path", lambda name: path)

    with pytest.raises(PptxRenderError, match="hash SHA-256"):
        font_files_for_theme(theme)


def test_font_embedding_is_deferred_to_cli(minimal_case, theme) -> None:
    artifact = _render_minimal(minimal_case, theme).artifact_path

    result = embed_fonts(artifact, theme)

    assert result.status == DEFERRED
    assert result.blocker is None
    assert result.warnings == (FONT_EMBEDDING_WARNING,)
    assert "font-embedding" in result.warnings[0]
    assert "PowerPoint COM" in result.warnings[0]


def test_fresh_render_has_no_embedded_font_parts(minimal_case, theme) -> None:
    artifact = _render_minimal(minimal_case, theme).artifact_path

    assert embedded_fonts(artifact) == ()
    presentation = Presentation(str(artifact))
    assert "embeddedFontLst" not in presentation.part.blob.decode("utf-8")


def test_font_embedding_rejects_theme_without_bundled_assets(theme) -> None:
    wrong_theme = replace(
        theme,
        typography=replace(theme.typography, family="Font Tidak Dikenal"),
    )

    with pytest.raises(PptxRenderError, match="aset tertanam"):
        font_files_for_theme(wrong_theme)


def test_font_embedding_rejects_missing_artifact(theme, tmp_path: Path) -> None:
    with pytest.raises(PptxRenderError, match="tidak ditemukan"):
        embed_fonts(tmp_path / "missing.pptx", theme)
