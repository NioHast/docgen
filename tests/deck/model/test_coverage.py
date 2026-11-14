"""Test coverage plan dan deteksi key/alt yang tidak lengkap."""

from pathlib import Path

from autooffice.deck.model import (
    BlockIR,
    DeckIR,
    KeyManifest,
    SlideIR,
    build_coverage_plan,
    check_coverage,
    compile_deck,
    load_deck,
)


def _deck(blocks: tuple[BlockIR, ...], *, source: dict[str, str] | None = None) -> DeckIR:
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Coverage Deck"},
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


def _text_block() -> BlockIR:
    return BlockIR(
        block_id="title",
        block_type="text",
        span=None,
        role="title",
        fields={"text": "Judul"},
    )


def _image_block(alt: str) -> BlockIR:
    return BlockIR(
        block_id="image1",
        block_type="image",
        span=None,
        role=None,
        fields={"path": "assets/a.png", "alt": alt, "fit": "contain"},
    )


def test_plan_from_all_blocks_is_complete(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)

    assert plan.ok is True
    assert len(plan.declared_keys) == 37
    assert plan.unkeyed_visible == ()
    assert plan.missing_alt == ()
    assert plan.charts[0].chart_id == "s01.chart1"


def test_plan_findings_are_ok_for_all_rendered_keys(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)
    findings = plan.findings(deck.keys.keys())

    assert findings.ok is True
    assert findings.missing == ()
    assert findings.extra == ()
    assert findings.duplicate == ()


def test_missing_extra_and_duplicate_rendered_keys_detected(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)
    rendered = list(deck.keys.keys())
    missing = rendered.pop(0)
    rendered.append("s01.unknown.text")
    rendered.append(rendered[0])
    findings = plan.findings(rendered)

    assert findings.missing == (missing,)
    assert findings.extra == ("s01.unknown.text",)
    assert findings.duplicate == (rendered[0],)
    assert findings.ok is False


def test_unkeyed_visible_block_detected() -> None:
    plan = build_coverage_plan(_deck((_text_block(),)))

    assert plan.unkeyed_visible == ("s01.title",)
    assert plan.ok is False


def test_defensive_missing_alt_detected() -> None:
    """Guard internal: schema menolak alt kosong sebelum IR sampai ke plan."""
    plan = build_coverage_plan(_deck((_image_block("   "),)))

    assert plan.missing_alt == ("s01.image1",)
    assert plan.ok is False


def test_unkeyed_slide_source_detected() -> None:
    plan = build_coverage_plan(_deck((), source={"text": "Sumber"}))

    assert plan.unkeyed_visible == ("s01.source",)


def test_defensive_duplicate_manifest_key_detected(fixture_dir: Path) -> None:
    """Guard internal: KeyRegistry menolak key duplikat sebelum IR terbentuk."""
    deck = compile_deck(load_deck(fixture_dir / "minimal.yaml"))
    first = deck.keys.bindings[0]
    duplicate_deck = DeckIR(
        schema=deck.schema,
        meta=deck.meta,
        theme_name=deck.theme_name,
        slides=deck.slides,
        keys=KeyManifest(bindings=(first, first)),
    )
    plan = build_coverage_plan(duplicate_deck)

    assert plan.duplicate_keys == (first.key,)
    assert plan.ok is False


def test_check_coverage_convenience(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "minimal.yaml"))

    assert check_coverage(deck, deck.keys.keys()).ok is True


def test_report_is_deterministic_and_has_schema(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)
    report = plan.to_report(deck.keys.keys())

    assert report["schema"] == "autooffice.coverage/v1"
    assert report["deck_id"] == "semua-block"
    assert report["declared"] == 37
    assert report["rendered"] == 37
    assert report["missing"] == []
    assert report["extra"] == []
    assert report["duplicate"] == []
    assert report["unkeyed_visible"] == []
    assert report["missing_alt"] == []
    assert report["charts"] == [{"chart_id": "s01.chart1", "native": True, "key": "s01.chart1"}]


def test_visible_and_sync_keys_are_separated(fixture_dir: Path) -> None:
    deck = compile_deck(load_deck(fixture_dir / "all-blocks.yaml"))
    plan = build_coverage_plan(deck)

    assert "s01.title.text" in plan.visible_keys
    assert "s01.notes" not in plan.visible_keys
    assert "s01.chart1.series1.value1" in plan.data_keys
    assert "s01.chart1.title" in plan.visible_keys
    assert "s01.chart1.title" not in plan.sync_keys
    assert "s01.notes" in plan.sync_keys
