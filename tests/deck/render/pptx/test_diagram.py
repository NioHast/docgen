"""Tes integrasi block diagram Mermaid sebagai picture native PPTX."""

import base64
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from autooffice.deck.layout.spec import LayoutPlan, PlacedBlock, SlideLayout
from autooffice.deck.media.mermaid import MMDC_ENV_VAR
from autooffice.deck.model.deck_ir import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyKind,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.coverage import CoverageError
from autooffice.deck.render.pptx.shapes import PptxRenderError
from autooffice.deck.render.protocol import OutputTarget, RenderRequest, RenderResult

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

FAKE_MMDC = """\
import base64
import json
import os
import pathlib
import sys

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

arguments = sys.argv[1:]
log = os.environ.get("FAKE_MMDC_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(arguments) + "\\n")

if arguments == ["--version"]:
    print("12.2.0")
    raise SystemExit(0)


def option(flag):
    try:
        return arguments[arguments.index(flag) + 1]
    except (ValueError, IndexError):
        return None


source = option("-i")
target = option("-o")
if source is None or target is None:
    print("fake mmdc: butuh -i dan -o", file=sys.stderr)
    raise SystemExit(2)
pathlib.Path(source).read_text(encoding="utf-8")
output = pathlib.Path(target)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(PNG)
"""


def _fake_mmdc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log = tmp_path / "mmdc-log.jsonl"
    monkeypatch.setenv("FAKE_MMDC_LOG", str(log))
    script = tmp_path / "fake_mmdc.py"
    script.write_text(FAKE_MMDC, encoding="utf-8", newline="\n")
    monkeypatch.setenv(MMDC_ENV_VAR, str(script))
    return log


def _binding(
    key: str,
    *,
    block_id: str,
    leaf: str,
    kind: KeyKind = "text",
) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id="s01",
        block_id=block_id,
        leaf=leaf,
        kind=kind,
        sync=True,
        yaml_path=("slides", 0, "blocks", 0, leaf),
        value="nilai",
        plain_text="nilai",
    )


def _diagram_case(
    *,
    alt: str = "Diagram alur build",
    caption: str = "Alur build",
    source: str = "diagrams/flow.mmd",
    with_caption_key: bool = True,
) -> tuple[DeckIR, LayoutPlan]:
    fields: dict[str, object] = {
        "source": source,
        "alt": alt,
    }
    if caption:
        fields["caption"] = caption
    block = BlockIR("process", "diagram", None, None, fields)
    bindings: list[KeyBinding] = []
    if caption and with_caption_key:
        bindings.append(
            _binding(
                "s01.process.caption",
                block_id="process",
                leaf="caption",
                kind="media_text",
            )
        )
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Diagram Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "diagram", 0, (block,), None, None),),
        keys=KeyManifest(tuple(bindings)),
    )
    layout = LayoutPlan(
        (
            SlideLayout(
                "s01",
                (PlacedBlock("process", 914400, 609600, 8000000, 4000000),),
                (),
            ),
        )
    )
    return deck, layout


def _render(
    deck: DeckIR,
    layout: LayoutPlan,
    workspace: Path,
    theme,
) -> RenderResult:
    return PptxRenderer().render(
        RenderRequest(
            deck=deck,
            layout=layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=workspace,
        )
    )


def _write_diagram(workspace: Path) -> Path:
    source = workspace / "diagrams" / "flow.mmd"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    return source


def test_diagram_block_inserts_picture_caption_and_coverage(
    workspace: Path,
    theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_mmdc(tmp_path, monkeypatch)
    _write_diagram(workspace)
    deck, layout = _diagram_case()

    result = _render(deck, layout, workspace, theme)
    presentation = Presentation(str(result.artifact_path))
    shapes = {shape.name: shape for shape in presentation.slides[0].shapes}

    picture = shapes["autooffice:diagram:s01.process"]
    assert picture.shape_type == MSO_SHAPE_TYPE.PICTURE
    node = picture._element.find(".//" + qn("p:cNvPr"))
    assert node is not None
    assert node.get("title") == "s01.process"
    assert node.get("descr") == "Diagram alur build"
    caption = shapes["autooffice:key:s01.process.caption"]
    assert caption.text_frame.text == "Alur build"
    assert result.coverage.ok is True
    assert result.coverage.missing_alt == ()
    assert len(list((workspace / "cache" / "mermaid").glob("*.png"))) >= 1
    assert (workspace / "cache" / "mermaid" / "s01.process.png").is_file()


def test_diagram_without_caption_has_only_picture(
    workspace: Path,
    theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_mmdc(tmp_path, monkeypatch)
    _write_diagram(workspace)
    deck, layout = _diagram_case(caption="")

    result = _render(deck, layout, workspace, theme)
    presentation = Presentation(str(result.artifact_path))
    shapes = list(presentation.slides[0].shapes)

    assert len(shapes) == 1
    assert shapes[0].name == "autooffice:diagram:s01.process"
    assert shapes[0].shape_type == MSO_SHAPE_TYPE.PICTURE
    assert result.coverage.ok is True


def test_diagram_missing_mmdc_fails_without_pptx_fallback(
    workspace: Path,
    theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MMDC_ENV_VAR, str(tmp_path / "tidak-ada-mmdc.exe"))
    _write_diagram(workspace)
    deck, layout = _diagram_case()

    with pytest.raises(PptxRenderError, match="npm install -g @mermaid-js/mermaid-cli"):
        _render(deck, layout, workspace, theme)

    assert not (workspace / "diagram-deck.pptx").exists()
    assert list(workspace.glob("*.pptx")) == []
    assert list((workspace / "cache" / "mermaid").glob("*.png")) == []


def test_diagram_missing_alt_fails_coverage(
    workspace: Path,
    theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_mmdc(tmp_path, monkeypatch)
    _write_diagram(workspace)
    deck, layout = _diagram_case(alt="")

    with pytest.raises(CoverageError) as error:
        _render(deck, layout, workspace, theme)

    assert error.value.report.missing_alt == ("s01.process",)
    assert not (workspace / "diagram-deck.pptx").exists()


def test_diagram_missing_caption_key_fails_coverage(
    workspace: Path,
    theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_mmdc(tmp_path, monkeypatch)
    _write_diagram(workspace)
    deck, layout = _diagram_case(with_caption_key=False)

    with pytest.raises(CoverageError) as error:
        _render(deck, layout, workspace, theme)

    assert error.value.report.unkeyed_visible == ("s01.process.caption",)
    assert not (workspace / "diagram-deck.pptx").exists()


def test_diagram_source_traversal_fails_before_render(
    workspace: Path,
    theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_mmdc(tmp_path, monkeypatch)
    deck, layout = _diagram_case(source="../flow.mmd")

    with pytest.raises(PptxRenderError, match="\\.\\."):
        _render(deck, layout, workspace, theme)

    assert not (workspace / "diagram-deck.pptx").exists()


def test_minimal_deck_does_not_need_mmdc(
    minimal_case,
    theme,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MMDC_ENV_VAR, str(tmp_path / "tidak-ada-mmdc.exe"))

    result = PptxRenderer().render(
        RenderRequest(
            deck=minimal_case.deck,
            layout=minimal_case.layout,
            theme=theme,
            target=OutputTarget.PPTX,
            workspace=minimal_case.workspace,
        )
    )

    assert result.artifact_path.is_file()
    assert result.coverage.ok is True
