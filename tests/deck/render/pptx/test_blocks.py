"""Tes block teks tambahan: heading, quote, metric, code, divider, spacer."""

from _edge_helpers import line_spacing_points
from pptx import Presentation
from pptx.oxml.ns import qn

from autooffice.deck.layout.spec import LayoutPlan, PlacedBlock, SlideLayout
from autooffice.deck.model.deck_ir import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.pptx.shapes import primary_typeface
from autooffice.deck.render.protocol import OutputTarget, RenderRequest
from autooffice.design.theme import resolve_theme


def _binding(key: str, block_id: str, leaf: str) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id="s01",
        block_id=block_id,
        leaf=leaf,
        kind="text",
        sync=True,
        yaml_path=("slides", 0, "blocks", 0, leaf),
        value="nilai",
        plain_text="nilai",
    )


def _case() -> tuple[DeckIR, LayoutPlan]:
    blocks = (
        BlockIR(
            "lead",
            "text",
            None,
            "body",
            {"heading": "Ringkasan", "text": "Isi paragraf."},
        ),
        BlockIR(
            "q1",
            "quote",
            None,
            None,
            {"text": "Kutipan", "attribution": "Tim AutoOffice"},
        ),
        BlockIR(
            "kpi1",
            "metric",
            None,
            None,
            {"label": "Coverage", "value": "100%", "caption": "Gate final"},
        ),
        BlockIR(
            "snippet",
            "code",
            None,
            None,
            {
                "code": "def key():\n    return 1",
                "language": "python",
                "line_numbers": True,
                "filename": "keys.py",
            },
        ),
        BlockIR("line1", "divider", None, None, {}),
        BlockIR("gap1", "spacer", None, None, {"size": "md"}),
    )
    bindings = (
        _binding("s01.lead.heading", "lead", "heading"),
        _binding("s01.lead.text", "lead", "text"),
        _binding("s01.q1.text", "q1", "text"),
        _binding("s01.q1.attribution", "q1", "attribution"),
        _binding("s01.kpi1.label", "kpi1", "label"),
        _binding("s01.kpi1.value", "kpi1", "value"),
        _binding("s01.kpi1.caption", "kpi1", "caption"),
        _binding("s01.snippet.filename", "snippet", "filename"),
        _binding("s01.snippet.code", "snippet", "code"),
    )
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Block Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(SlideIR("s01", "custom", 0, blocks, None, None),),
        keys=KeyManifest(bindings),
    )
    layout = LayoutPlan(
        (
            SlideLayout(
                "s01",
                (
                    PlacedBlock("lead", 914400, 609600, 5000000, 1200000),
                    PlacedBlock("q1", 7000000, 609600, 4000000, 1200000),
                    PlacedBlock("kpi1", 914400, 1900000, 3000000, 1400000),
                    PlacedBlock("snippet", 4000000, 1900000, 7000000, 1400000),
                    PlacedBlock("line1", 914400, 3500000, 10000000, 100000),
                    PlacedBlock("gap1", 914400, 3700000, 10000000, 100000),
                ),
                (),
            ),
        )
    )
    return deck, layout


def test_text_heading_quote_metric_and_code_shapes(workspace) -> None:
    deck, layout = _case()
    theme = resolve_theme("indigo")
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
    shapes = {shape.name: shape for shape in presentation.slides[0].shapes}

    assert result.coverage.ok is True
    assert shapes["autooffice:key:s01.lead.heading"].text_frame.text == "Ringkasan"
    assert shapes["autooffice:key:s01.lead.text"].text_frame.text == "Isi paragraf."
    assert shapes["autooffice:key:s01.q1.text"].text_frame.text == "Kutipan"
    assert shapes["autooffice:key:s01.q1.attribution"].text_frame.text == "Tim AutoOffice"
    assert shapes["autooffice:key:s01.kpi1.value"].text_frame.text == "100%"
    assert shapes["autooffice:key:s01.kpi1.label"].text_frame.text == "Coverage"
    assert shapes["autooffice:key:s01.kpi1.caption"].text_frame.text == "Gate final"
    assert shapes["autooffice:key:s01.snippet.filename"].text_frame.text == "keys.py"
    code_shape = shapes["autooffice:key:s01.snippet.code"]
    assert "def key():" in code_shape.text_frame.text
    assert len(code_shape.text_frame.paragraphs) == 2
    code_run = code_shape.text_frame.paragraphs[0].runs[0]
    assert code_run.font.name == primary_typeface(theme.code.family)
    display_run = shapes["autooffice:key:s01.kpi1.value"].text_frame.paragraphs[0].runs[0]
    body_run = shapes["autooffice:key:s01.lead.text"].text_frame.paragraphs[0].runs[0]
    assert display_run.font.name == "Plus Jakarta Sans ExtraBold"
    assert display_run.font.bold is False
    assert _latin_typeface(display_run) == "Plus Jakarta Sans ExtraBold"
    assert body_run.font.name == "Plus Jakarta Sans"
    assert body_run.font.bold is False
    assert _latin_typeface(body_run) == "Plus Jakarta Sans"


def test_code_uses_exact_point_line_spacing(workspace) -> None:
    deck, layout = _case()
    theme = resolve_theme("indigo")
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
    shapes = {shape.name: shape for shape in presentation.slides[0].shapes}
    code_shape = shapes["autooffice:key:s01.snippet.code"]

    for paragraph in code_shape.text_frame.paragraphs:
        run = paragraph.runs[0]
        assert run.font.size is not None
        assert line_spacing_points(paragraph) == round(
            run.font.size.pt * theme.code.line_height * 100
        )


def test_divider_is_chrome_and_spacer_has_no_shape(workspace) -> None:
    deck, layout = _case()
    theme = resolve_theme("indigo")
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
    names = [shape.name for shape in presentation.slides[0].shapes]

    assert "chrome:divider:line1" in names
    assert all("gap1" not in name for name in names)
    divider = next(
        shape for shape in presentation.slides[0].shapes if shape.name == "chrome:divider:line1"
    )
    node = divider._element.find(".//" + qn("p:cNvPr"))
    assert node is not None
    assert node.get("title") is None


def _latin_typeface(run) -> str:
    latin = run.font._element.find(qn("a:latin"))
    assert latin is not None
    return latin.get("typeface", "")
