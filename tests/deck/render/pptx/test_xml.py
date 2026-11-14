"""Tes scan XML, penghapusan timing/transition, dan hash paket."""

import zipfile
from pathlib import Path

import pytest
from lxml import etree
from pptx import Presentation
from pptx.oxml.ns import qn

from autooffice.deck.render.pptx.shapes import PptxRenderError
from autooffice.deck.render.pptx.xml import (
    assert_no_forbidden_nodes,
    content_hash,
    forbidden_node_paths,
    remove_animation_nodes,
    validate_package,
)


def test_remove_animation_nodes_strips_injected_nodes() -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    etree.SubElement(slide._element, qn("p:timing"))
    etree.SubElement(slide._element, qn("p:transition"))

    removed = remove_animation_nodes(presentation)

    assert removed == ("slide1:timing", "slide1:transition")
    assert slide._element.find(qn("p:timing")) is None
    assert slide._element.find(qn("p:transition")) is None


def test_remove_animation_nodes_is_noop_for_clean_slide() -> None:
    presentation = Presentation()
    presentation.slides.add_slide(presentation.slide_layouts[6])

    assert remove_animation_nodes(presentation) == ()


def test_forbidden_node_scan_detects_injected_timing(minimal_case, theme, tmp_path: Path) -> None:
    artifact = _render_minimal(minimal_case, theme)
    corrupted = tmp_path / "with-timing.pptx"
    with (
        zipfile.ZipFile(artifact.artifact_path) as source,
        zipfile.ZipFile(corrupted, "w") as target,
    ):
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "ppt/slides/slide1.xml":
                data = data.replace(b"</p:sld>", b"<p:timing/></p:sld>")
            target.writestr(info, data)

    assert forbidden_node_paths(corrupted) == ("ppt/slides/slide1.xml:p:timing",)
    with pytest.raises(PptxRenderError, match="animasi/transisi"):
        assert_no_forbidden_nodes(corrupted)


def test_validate_package_and_hash_are_deterministic(minimal_case, theme) -> None:
    first = _render_minimal(minimal_case, theme)
    second = _render_minimal(minimal_case, theme)

    validate_package(first.artifact_path)
    assert content_hash(first.artifact_path) == first.content_hash
    assert content_hash(second.artifact_path) == second.content_hash


def test_validate_package_rejects_missing_required_part(tmp_path: Path) -> None:
    path = tmp_path / "broken.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")

    with pytest.raises(PptxRenderError, match="part wajib"):
        validate_package(path)


def _render_minimal(case, theme):
    from autooffice.deck.render.pptx import PptxRenderer
    from autooffice.deck.render.protocol import OutputTarget, RenderRequest

    return PptxRenderer().render(
        RenderRequest(
            deck=case.deck,
            layout=case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=case.workspace,
        )
    )
