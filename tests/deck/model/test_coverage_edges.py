"""Test edge case coverage plan: field opsional, series non-ChartSeries, dan deck kosong."""

from autooffice.deck.model import (
    BlockIR,
    ChartSeries,
    DeckIR,
    KeyManifest,
    SlideIR,
    build_coverage_plan,
    check_coverage,
    compile_deck,
    load_deck,
)


def _deck(
    blocks: tuple[BlockIR, ...],
    *,
    meta: dict[str, str] | None = None,
    source: dict[str, str] | None = None,
) -> DeckIR:
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Edge Deck"} if meta is None else meta,
        theme_name="indigo",
        slides=(
            SlideIR(
                slide_id="s01",
                layout="content",
                order=0,
                blocks=blocks,
                notes=None,
                source=source,
            ),
        ),
        keys=KeyManifest(bindings=()),
    )


def _block(block_id: str, block_type: str, fields: dict[str, object]) -> BlockIR:
    return BlockIR(
        block_id=block_id,
        block_type=block_type,
        span=None,
        role=None,
        fields=fields,
    )


def test_coverage_plan_flags_visible_blocks_without_manifest_bindings() -> None:
    blocks = (
        _block("text1", "text", {"text": "Teks"}),
        _block("bullets1", "bullets", {"items": ("Satu",), "ordered": False}),
        _block(
            "table1",
            "table",
            {"columns": ("Kolom A", "Kolom B"), "rows": (("1", "2"),)},
        ),
        _block(
            "chart1",
            "chart",
            {
                "title": "Judul",
                "alt": "Alt chart",
                "categories": ("Q1", "Q2"),
                "series": (ChartSeries("Satu", (1, 2)),),
            },
        ),
        _block(
            "chart2",
            "chart",
            {
                "title": "Judul tanpa kategori",
                "alt": "Alt chart",
                "categories": (),
                "series": (),
            },
        ),
        _block("code1", "code", {"code": "print(1)", "language": "python", "line_numbers": True}),
        _block("quote1", "quote", {"text": "Kutipan"}),
        _block("image1", "image", {"path": "assets/a.png", "alt": "Alt gambar", "fit": "contain"}),
        _block("diagram1", "diagram", {"source": "diagrams/a.mmd", "alt": "Alt diagram"}),
        _block("metric1", "metric", {"label": "Label", "value": "1", "status": "neutral"}),
        _block("line1", "divider", {}),
        _block("gap1", "spacer", {"size": "md"}),
    )

    plan = build_coverage_plan(_deck(blocks))

    assert set(plan.unkeyed_visible) == {
        "s01.text1",
        "s01.bullets1",
        "s01.table1",
        "s01.chart1",
        "s01.chart2",
        "s01.code1",
        "s01.quote1",
        "s01.metric1",
    }
    assert plan.missing_alt == ()
    assert plan.declared_keys == ()
    assert plan.ok is False
    assert tuple(chart.chart_id for chart in plan.charts) == ("s01.chart1", "s01.chart2")


def test_defensive_coverage_plan_tolerates_non_public_ir_shapes() -> None:
    """Plan coverage adalah proyeksi defensif atas IR, bukan validator authoring.

    Compiler publik selalu menghasilkan tuple dan ``ChartSeries``. Bentuk list,
    mapping series, dan string series di bawah ini mensimulasikan IR lama atau
    pemanggil internal, dan plan tetap harus membacanya tanpa crash.
    """
    blocks = (
        _block("table1", "table", {"columns": ["A"], "rows": [["1"]]}),
        _block(
            "chart1",
            "chart",
            {
                "title": "Judul",
                "alt": "Alt chart",
                "categories": ["Q1"],
                "series": [{"values": [3, 4]}, "bukan-series"],
            },
        ),
    )

    plan = build_coverage_plan(_deck(blocks))

    assert set(plan.unkeyed_visible) == {"s01.table1", "s01.chart1"}
    assert tuple(chart.chart_id for chart in plan.charts) == ("s01.chart1",)


def test_deck_id_falls_back_to_deck_without_title() -> None:
    plan = build_coverage_plan(_deck((), meta={}))

    assert plan.deck_id == "deck"
    assert plan.ok is True


def test_empty_deck_plan_has_no_findings() -> None:
    deck = DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Kosong"},
        theme_name="indigo",
        slides=(),
        keys=KeyManifest(bindings=()),
    )

    plan = build_coverage_plan(deck)

    assert plan.findings(()).ok is True
    assert plan.to_report(())["declared"] == 0


def test_report_lists_missing_alt() -> None:
    plan = build_coverage_plan(
        _deck((_block("image1", "image", {"path": "assets/a.png", "alt": "  ", "fit": "contain"}),))
    )
    report = plan.to_report(())

    assert report["deck_id"] == "edge-deck"
    assert report["missing_alt"] == ["s01.image1"]
    assert report["unkeyed_visible"] == []
    assert report["charts"] == []


def test_defensive_check_coverage_reports_duplicate_manifest_keys(fixture_dir) -> None:
    """Manifest duplikat tidak mungkin keluar dari compiler publik.

    Coverage tetap wajib melaporkannya bila IR dibangun ulang oleh pemanggil
    internal.
    """
    deck = compile_deck(load_deck(fixture_dir / "minimal.yaml"))
    first = deck.keys.bindings[0]
    duplicate_deck = DeckIR(
        schema=deck.schema,
        meta=deck.meta,
        theme_name=deck.theme_name,
        slides=deck.slides,
        keys=KeyManifest(bindings=(first, first)),
    )

    findings = check_coverage(duplicate_deck, deck.keys.keys())

    assert findings.duplicate == (first.key,)
    assert findings.ok is False
