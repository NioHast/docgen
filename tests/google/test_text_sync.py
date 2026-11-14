"""Test push/pull/diff/apply teks untuk shape, tabel, notes, dan source."""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import autooffice.google.sync as sync_module
from autooffice.deck.model import compile_deck_file
from autooffice.google import GoogleSyncError
from autooffice.google.extract import PulledText, TextEntry, extract_text
from autooffice.google.fake import FakeGoogleServices
from autooffice.google.slides import PresentationSnapshot
from autooffice.google.state import GoogleState, load_state, save_state
from autooffice.google.sync import (
    _compiled_title,
    apply_diff,
    diff_text,
    pull_text,
    push_text,
    sync_deck,
)


def _with_text(
    presentation: PresentationSnapshot,
    key: str,
    text: str,
) -> PresentationSnapshot:
    slides = []
    found = False
    for slide in presentation.slides:
        page_elements = []
        for element in slide.page_elements:
            updated_element, matched = _with_element_text(element, key, text)
            page_elements.append(updated_element)
            found = found or matched
        notes_elements = []
        for element in slide.notes_page_elements:
            updated_element, matched = _with_element_text(element, key, text)
            notes_elements.append(updated_element)
            found = found or matched
        slides.append(
            replace(
                slide,
                page_elements=tuple(page_elements),
                notes_page_elements=tuple(notes_elements),
            )
        )
    assert found, key
    return replace(presentation, slides=tuple(slides))


def _with_element_text(
    element: object,
    key: str,
    text: str,
) -> tuple[object, bool]:
    from autooffice.google.slides import PageElement

    assert isinstance(element, PageElement)
    if element.marker == key and element.kind == "shape":
        return replace(element, text=text), True
    if element.kind != "table" or element.marker is None:
        return element, False
    prefix = f"{element.marker}."
    if not key.startswith(prefix):
        return element, False
    leaf = key[len(prefix) :]
    if leaf.startswith("h") and leaf[1:].isdigit():
        row, column = 0, int(leaf[1:]) - 1
    elif leaf.startswith("r") and ".c" in leaf:
        row_part, column_part = leaf[1:].split(".c", 1)
        if not row_part.isdigit() or not column_part.isdigit():
            return element, False
        row, column = int(row_part), int(column_part) - 1
    else:
        return element, False
    cells = [list(cell_row) for cell_row in element.cells]
    if row >= len(cells) or column >= len(cells[row]):
        return element, False
    cells[row][column] = text
    return replace(element, cells=tuple(tuple(cell_row) for cell_row in cells)), True


def _remote_snapshot(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> PresentationSnapshot:
    snapshot = make_snapshot(presentation_id="presentation-1")
    snapshot = _with_text(snapshot, "s01.title.text", "Judul remote")
    snapshot = _with_text(snapshot, "s01.body.text", "Isi remote")
    snapshot = _with_text(snapshot, "s01.notes", "Catatan remote\nBaris kedua")
    snapshot = _with_text(snapshot, "s01.table1.h1", "Metrik remote")
    snapshot = _with_text(snapshot, "s01.table1.r1.c1", "Peserta remote")
    snapshot = _with_text(snapshot, "s01.source.text", "Sumber remote")
    return snapshot


def _binding_text(deck_path: Path, key: str) -> str:
    deck = compile_deck_file(deck_path)
    for binding in deck.keys.bindings:
        if binding.key == key:
            return binding.plain_text
    raise AssertionError(f"key tidak ditemukan: {key}")


def test_extract_text_reads_shape_table_notes_and_source(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    pulled = extract_text(make_snapshot())

    entries = pulled.by_key()
    assert entries["s01.title.text"].text == "Judul awal"
    assert entries["s01.table1.h1"].text == "Metrik"
    assert entries["s01.table1.r1.c1"].text == "Peserta"
    assert entries["s01.notes"].text == (
        "Catatan awal untuk slide pertama.\nBaris kedua tetap dipertahankan."
    )
    assert entries["s01.source.text"].text == "Sumber: data internal, 2026"


def test_extract_rejects_shape_marker_moved_to_another_slide(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    first, second = snapshot.slides[0], snapshot.slides[1]
    shape = next(element for element in first.page_elements if element.marker == "s01.title.text")
    snapshot = replace(
        snapshot,
        slides=(
            replace(
                first,
                page_elements=tuple(
                    element
                    for element in first.page_elements
                    if element.object_id != shape.object_id
                ),
            ),
            replace(second, page_elements=(*second.page_elements, shape)),
        ),
    )

    with pytest.raises(GoogleSyncError, match=r"slide index 2.*s01"):
        extract_text(snapshot)


def test_extract_accepts_autooffice_table_marker_prefix(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    slide = snapshot.slides[0]
    table = next(element for element in slide.page_elements if element.kind == "table")
    marked = replace(table, title="autooffice:table:s01.table1")
    snapshot = replace(
        snapshot,
        slides=(
            replace(
                slide,
                page_elements=tuple(
                    marked if element.object_id == table.object_id else element
                    for element in slide.page_elements
                ),
            ),
            *snapshot.slides[1:],
        ),
    )

    entries = extract_text(snapshot).by_key()

    assert entries["s01.table1.h1"].text == "Metrik"
    assert entries["s01.table1.r1.c1"].text == "Peserta"
    assert entries["s01.table1.h1"].slide_index == 0


def test_extract_notes_falls_back_to_slide_order_without_marker(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    slide = snapshot.slides[0]
    notes = slide.notes_page_elements[0]
    unmarked = replace(notes, title=None, description=None)
    snapshot = replace(
        snapshot,
        slides=(
            replace(slide, notes_page_elements=(unmarked,)),
            *snapshot.slides[1:],
        ),
    )

    entries = extract_text(snapshot).by_key()

    assert entries["s01.notes"].text.startswith("Catatan awal")
    assert entries["s01.notes"].slide_index == 0


def test_extract_notes_uses_description_when_title_is_missing(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    slide = snapshot.slides[0]
    notes = slide.notes_page_elements[0]
    description_only = replace(notes, title=None, description="s01.notes")
    snapshot = replace(
        snapshot,
        slides=(
            replace(slide, notes_page_elements=(description_only,)),
            *snapshot.slides[1:],
        ),
    )

    entries = extract_text(snapshot).by_key()

    assert entries["s01.notes"].text.startswith("Catatan awal")


def test_diff_detects_all_synced_text_classes(
    deck_copy: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    pulled = extract_text(_remote_snapshot(make_snapshot))

    diff = diff_text(deck_copy, pulled)

    changes = {change.key: change for change in diff.changes}
    assert changes["s01.title.text"].to_value == "Judul remote"
    assert changes["s01.body.text"].to_value == "Isi remote"
    assert changes["s01.notes"].to_value == "Catatan remote\nBaris kedua"
    assert changes["s01.table1.h1"].to_value == "Metrik remote"
    assert changes["s01.table1.r1.c1"].to_value == "Peserta remote"
    assert changes["s01.source.text"].to_value == "Sumber remote"
    assert diff.missing == ()


def test_apply_writes_new_yaml_without_touching_source(
    deck_copy: Path,
    tmp_path: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    source_before = deck_copy.read_bytes()
    pulled = extract_text(_remote_snapshot(make_snapshot))
    diff = diff_text(deck_copy, pulled)
    output = tmp_path / "review" / "deck.applied.yaml"

    result = apply_diff(deck_copy, diff, output)

    assert result == output
    assert deck_copy.read_bytes() == source_before
    assert _binding_text(output, "s01.title.text") == "Judul remote"
    assert _binding_text(output, "s01.notes") == "Catatan remote\nBaris kedua"
    assert _binding_text(output, "s01.table1.h1") == "Metrik remote"


def test_apply_rejects_diff_with_unknown_keys(
    deck_copy: Path,
    tmp_path: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    pulled = extract_text(_remote_snapshot(make_snapshot))
    diff = diff_text(deck_copy, pulled)
    unknown = TextEntry(
        key="s09.extra.text",
        slide_id="s09",
        text="teks asing",
        kind="text",
        slide_index=8,
    )
    diff = replace(diff, unknown=(unknown,))
    output = tmp_path / "review" / "deck.applied.yaml"

    with pytest.raises(GoogleSyncError, match=r"key asing.*s09\.extra\.text"):
        apply_diff(deck_copy, diff, output)

    assert not output.exists()


def test_apply_refuses_to_overwrite_source(
    deck_copy: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    pulled = extract_text(_remote_snapshot(make_snapshot))
    diff = diff_text(deck_copy, pulled)

    with pytest.raises(GoogleSyncError, match="menimpa YAML sumber"):
        apply_diff(deck_copy, diff, deck_copy)


def test_push_text_updates_all_remote_text_classes(
    deck_copy: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(_remote_snapshot(make_snapshot))

    updated_count = push_text(fake.slides, "presentation-1", deck_copy)

    entries = extract_text(fake.slides.get_presentation("presentation-1")).by_key()
    assert updated_count > 0
    assert entries["s01.title.text"].text == "Judul awal"
    assert entries["s01.notes"].text.startswith("Catatan awal")
    assert entries["s01.table1.h1"].text == "Metrik"
    assert entries["s01.table1.r1.c1"].text == "Peserta"
    assert entries["s01.source.text"].text == "Sumber: data internal, 2026"


def test_push_text_accepts_autooffice_table_marker_prefix(
    deck_copy: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    snapshot = make_snapshot(presentation_id="presentation-1")
    slide = snapshot.slides[0]
    table = next(element for element in slide.page_elements if element.kind == "table")
    marked = replace(table, title="autooffice:table:s01.table1")
    snapshot = replace(
        snapshot,
        slides=(
            replace(
                slide,
                page_elements=tuple(
                    marked if element.object_id == table.object_id else element
                    for element in slide.page_elements
                ),
            ),
            *snapshot.slides[1:],
        ),
    )
    fake.slides.add_presentation(snapshot)

    push_text(fake.slides, "presentation-1", deck_copy)

    entries = extract_text(fake.slides.get_presentation("presentation-1")).by_key()
    assert entries["s01.table1.h1"].text == "Metrik"
    assert entries["s01.table1.r1.c1"].text == "Peserta"


def test_push_text_preflight_prevents_partial_mutation(
    deck_copy: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    snapshot = make_snapshot(presentation_id="presentation-1")
    snapshot = replace(
        snapshot,
        slides=tuple(
            replace(
                slide,
                page_elements=tuple(
                    element for element in slide.page_elements if element.marker != "s01.title.text"
                ),
            )
            for slide in snapshot.slides
        ),
    )
    fake.slides.add_presentation(snapshot)

    with pytest.raises(GoogleSyncError, match=r"s01\.title\.text"):
        push_text(fake.slides, "presentation-1", deck_copy)

    assert fake.slides.requests_log == []


def test_pull_and_diff_write_review_files_without_touching_source(
    deck_copy: Path,
    tmp_path: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(_remote_snapshot(make_snapshot))
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    state = GoogleState(
        deck_path=deck_copy.name,
        deck_sha256="a" * 64,
        presentation_id="presentation-1",
        spreadsheet_id="spreadsheet-1",
    )
    save_state(state, state_file)
    source_before = deck_copy.read_bytes()

    diff_path = sync_deck(
        deck=deck_copy,
        state=state_file,
        mode="diff",
        review_dir=tmp_path / "review",
        services=fake,
    )[0]
    pulled_path = sync_deck(
        deck=deck_copy,
        state=state_file,
        mode="pull",
        review_dir=tmp_path / "review",
        services=fake,
    )[0]

    report = json.loads(diff_path.read_text(encoding="utf-8"))
    assert report["stats"]["changed"] > 0
    assert any(change["key"] == "s01.title.text" for change in report["changes"])
    assert _binding_text(pulled_path, "s01.title.text") == "Judul remote"
    assert deck_copy.read_bytes() == source_before
    saved = load_state(state_file)
    assert saved.presentation_id == "presentation-1"
    assert saved.deck_sha256 == "a" * 64


def test_apply_mode_writes_applied_yaml(
    deck_copy: Path,
    tmp_path: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(_remote_snapshot(make_snapshot))
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256="a" * 64,
            presentation_id="presentation-1",
        ),
        state_file,
    )

    output = sync_deck(
        deck=deck_copy,
        state=state_file,
        mode="apply",
        review_dir=tmp_path / "review",
        services=fake,
    )[0]

    assert output.name == "deck.applied.yaml"
    assert _binding_text(output, "s01.body.text") == "Isi remote"
    assert deck_copy.read_bytes() != output.read_bytes()


def test_diff_marks_unknown_and_rejected_keys(
    deck_copy: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    pulled = extract_text(make_snapshot())
    extra = TextEntry(
        key="s09.extra.text",
        slide_id="s09",
        text="teks asing",
        kind="text",
    )
    structural = TextEntry(
        key="meta.title",
        slide_id="meta",
        text="judul",
        kind="text",
    )
    with_unknown = replace(
        pulled,
        entries=(*pulled.entries, extra, structural),
    )

    diff = diff_text(deck_copy, with_unknown)

    assert [entry.key for entry in diff.unknown] == ["s09.extra.text"]
    assert [entry.key for entry in diff.rejected] == ["meta.title"]


def test_pull_text_uses_fake_only(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))

    pulled = pull_text(fake.slides, "presentation-1")

    assert isinstance(pulled, PulledText)
    assert pulled.presentation_id == "presentation-1"


def test_sync_deck_reports_review_directory_file(
    deck_copy: Path,
    tmp_path: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(_remote_snapshot(make_snapshot))
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256="a" * 64,
            presentation_id="presentation-1",
        ),
        state_file,
    )
    review = tmp_path / "review"
    review.write_text("bukan direktori", encoding="utf-8")

    with pytest.raises(GoogleSyncError, match="Direktori review"):
        sync_deck(
            deck=deck_copy,
            state=state_file,
            mode="diff",
            review_dir=review,
            services=fake,
        )


def test_sync_deck_rejects_save_state_without_written_file(
    deck_copy: Path,
    tmp_path: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(_remote_snapshot(make_snapshot))
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256="a" * 64,
            presentation_id="presentation-1",
        ),
        state_file,
    )
    missing = tmp_path / "missing-state.json"
    monkeypatch.setattr(sync_module, "save_state", lambda *_args, **_kwargs: missing)

    with pytest.raises(GoogleSyncError, match="State Google tidak tertulis setelah sync"):
        sync_deck(
            deck=deck_copy,
            state=state_file,
            mode="diff",
            review_dir=tmp_path / "review",
            services=fake,
        )

    assert not missing.exists()


def test_sync_deck_rejects_apply_diff_without_written_file(
    deck_copy: Path,
    tmp_path: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(_remote_snapshot(make_snapshot))
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256="a" * 64,
            presentation_id="presentation-1",
        ),
        state_file,
    )
    missing = tmp_path / "missing-applied.yaml"
    monkeypatch.setattr(sync_module, "apply_diff", lambda *_args, **_kwargs: missing)

    with pytest.raises(GoogleSyncError, match="tidak menghasilkan berkas review"):
        sync_deck(
            deck=deck_copy,
            state=state_file,
            mode="apply",
            review_dir=tmp_path / "review",
            services=fake,
        )


def test_apply_diff_reports_destination_directory_error(
    deck_copy: Path,
    tmp_path: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    pulled = extract_text(_remote_snapshot(make_snapshot))
    diff = diff_text(deck_copy, pulled)
    blocked = tmp_path / "blocked"
    blocked.write_text("bukan direktori", encoding="utf-8")

    with pytest.raises(GoogleSyncError, match="YAML hasil sync tidak dapat ditulis"):
        apply_diff(deck_copy, diff, blocked / "deck.applied.yaml")


def test_compiled_title_requires_non_empty_meta_title() -> None:
    with pytest.raises(GoogleSyncError, match=r"meta\.title"):
        _compiled_title(SimpleNamespace(meta={}), Path("deck.yaml"))

    with pytest.raises(GoogleSyncError, match=r"meta\.title"):
        _compiled_title(SimpleNamespace(meta={"title": "  "}), Path("deck.yaml"))


def test_sync_deck_returns_review_and_state_paths(
    deck_copy: Path,
    tmp_path: Path,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake = FakeGoogleServices.create()
    fake.slides.add_presentation(_remote_snapshot(make_snapshot))
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256="a" * 64,
            presentation_id="presentation-1",
        ),
        state_file,
    )

    review_path, returned_state = sync_deck(
        deck=deck_copy,
        state=state_file,
        mode="diff",
        review_dir=tmp_path / "review",
        services=fake,
    )

    assert review_path == tmp_path / "review" / "deck.diff.json"
    assert review_path.is_file()
    assert returned_state == state_file
    assert returned_state.is_file()
    assert load_state(state_file).last_pulled_revision_id == "revision-1"
