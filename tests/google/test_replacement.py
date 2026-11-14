"""Test createSheetsChart linked, preflight sebelum mutasi, dan rerun idempoten."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from autooffice.deck.model import DeckIR
from autooffice.design.theme import Theme
from autooffice.google import (
    ChartPlaceholderError,
    GoogleSyncError,
    SheetsError,
    SlidesError,
    TablePreflightError,
)
from autooffice.google.charts import (
    ChartLink,
    build_chart_specs,
    ensure_sheet_chart,
    ensure_workbook,
)
from autooffice.google.fake import FakeGoogleServices
from autooffice.google.slides import (
    CHART_MARKER_PREFIX,
    PageElement,
    PresentationSnapshot,
    preflight_chart_replacements,
    replace_chart_placeholders,
)
from autooffice.google.state import (
    GoogleState,
    deck_sha256,
    load_state,
    save_state,
)


def _options(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "include_chart_placeholders": True,
        "include_tables": True,
        "table_kind": "table",
        "table_rows": None,
        "table_columns": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _links(
    fake: FakeGoogleServices,
    deck: DeckIR,
    theme: Theme,
) -> tuple[dict[str, ChartLink], str]:
    workbook, _ = ensure_workbook(fake.sheets, title=str(deck.meta["title"]))
    links = {
        spec.chart_id: ensure_sheet_chart(
            fake.sheets,
            spreadsheet_id=workbook.spreadsheet_id,
            spec=spec,
            theme=theme,
        )
        for spec in build_chart_specs(deck)
    }
    return links, workbook.spreadsheet_id


def _create_requests(fake: FakeGoogleServices) -> list[Mapping[str, object]]:
    return [
        request["createSheetsChart"]
        for request in fake.slides.requests_log
        if "createSheetsChart" in request
    ]


class _UnappliedBatchSlides:
    """Adapter Slides yang mengaku sukses tetapi tidak menerapkan batch."""

    def __init__(self, snapshot: PresentationSnapshot) -> None:
        self._snapshot = snapshot
        self.requests: list[tuple[Mapping[str, object], ...]] = []
        self.get_calls = 0

    def get_presentation(self, presentation_id: str) -> PresentationSnapshot:
        assert presentation_id == self._snapshot.presentation_id
        self.get_calls += 1
        return self._snapshot

    def batch_update(
        self,
        presentation_id: str,
        requests: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        assert presentation_id == self._snapshot.presentation_id
        self.requests.append(tuple(requests))
        return {"replies": [{} for _ in requests]}


def test_create_sheets_chart_uses_linked_mode(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot(presentation_id="presentation-1")
    fake_google.slides.add_presentation(snapshot)
    links, spreadsheet_id = _links(fake_google, google_deck, google_theme)

    replace_chart_placeholders(
        fake_google.slides,
        "presentation-1",
        deck=google_deck,
        links=links,
    )

    requests = _create_requests(fake_google)
    assert len(requests) == 1
    payload = requests[0]
    assert payload["linkingMode"] == "LINKED"
    assert payload["spreadsheetId"] == spreadsheet_id
    assert payload["chartId"] == links["s02.chart1"].embedded_chart_id
    assert "elementProperties" in payload
    assert fake_google.slides.create_table_requests == []


def test_replacement_verifies_counts_and_removes_placeholder(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake_google.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))
    links, _ = _links(fake_google, google_deck, google_theme)

    updated = replace_chart_placeholders(
        fake_google.slides,
        "presentation-1",
        deck=google_deck,
        links=links,
    )

    assert not any(
        element.marker == "autooffice:chart:s02.chart1"
        for element in updated.elements_including_notes()
    )
    linked = [
        element for element in updated.elements_including_notes() if element.kind == "sheets_chart"
    ]
    assert len(linked) == 1
    assert linked[0].spreadsheet_id == links["s02.chart1"].spreadsheet_id
    assert linked[0].chart_id == links["s02.chart1"].embedded_chart_id


def test_replacement_rejects_batch_success_without_applying_chart(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    links, _ = _links(fake_google, google_deck, google_theme)
    slides = _UnappliedBatchSlides(make_snapshot(presentation_id="presentation-1"))

    with pytest.raises(ChartPlaceholderError, match="setelah replacement"):
        replace_chart_placeholders(
            slides,
            "presentation-1",
            deck=google_deck,
            links=links,
        )

    assert slides.get_calls == 2
    assert [tuple(request) for batch in slides.requests for request in batch] == [
        ("deleteObject",),
        ("createSheetsChart",),
    ]


def test_rerun_does_not_create_duplicate_linked_chart(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake_google.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))
    links, _ = _links(fake_google, google_deck, google_theme)
    replace_chart_placeholders(
        fake_google.slides,
        "presentation-1",
        deck=google_deck,
        links=links,
    )
    first_create_count = len(_create_requests(fake_google))

    snapshot = fake_google.slides.get_presentation("presentation-1")
    plan = preflight_chart_replacements(google_deck, snapshot, links)
    updated = replace_chart_placeholders(
        fake_google.slides,
        "presentation-1",
        deck=google_deck,
        links=links,
        presentation=snapshot,
    )

    assert [action.action for action in plan.actions] == ["keep"]
    assert len(_create_requests(fake_google)) == first_create_count == 1
    linked = [
        element for element in updated.elements_including_notes() if element.kind == "sheets_chart"
    ]
    assert len(linked) == 1


def test_table_preflight_failure_happens_before_any_deletion(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake_google.slides.add_presentation(
        make_snapshot(
            presentation_id="presentation-1",
            options=_options(table_kind="image"),
        )
    )
    links, _ = _links(fake_google, google_deck, google_theme)

    with pytest.raises(TablePreflightError, match=r"slide 's01' block 'table1'"):
        replace_chart_placeholders(
            fake_google.slides,
            "presentation-1",
            deck=google_deck,
            links=links,
        )

    assert fake_google.slides.requests_log == []
    assert fake_google.slides.create_table_requests == []
    snapshot = fake_google.slides.get_presentation("presentation-1")
    assert any(
        element.marker == "autooffice:chart:s02.chart1"
        for element in snapshot.elements_including_notes()
    )


def test_missing_placeholder_fails_before_mutation(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    fake_google.slides.add_presentation(
        make_snapshot(
            presentation_id="presentation-1",
            options=_options(include_chart_placeholders=False),
        )
    )
    links, _ = _links(fake_google, google_deck, google_theme)

    with pytest.raises(ChartPlaceholderError, match=r"s02\.chart1"):
        replace_chart_placeholders(
            fake_google.slides,
            "presentation-1",
            deck=google_deck,
            links=links,
        )

    assert fake_google.slides.requests_log == []


def test_push_deck_table_preflight_failure_persists_workbook_and_presentation(
    make_snapshot: Callable[..., PresentationSnapshot],
    deck_copy: Path,
    tmp_path: Path,
) -> None:
    from autooffice.google.sync import push_deck

    def converter(_path: Path, _name: str, presentation_id: str) -> PresentationSnapshot:
        return make_snapshot(
            presentation_id=presentation_id,
            options=_options(table_kind="image"),
        )

    fake = FakeGoogleServices.create(converter=converter)
    staging = tmp_path / "deck.slides-upload.pptx"
    staging.write_bytes(b"PK\x03\x04fake")
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"

    with pytest.raises(TablePreflightError, match=r"slide 's01' block 'table1'"):
        push_deck(
            deck=deck_copy,
            staging=staging,
            state=state_file,
            services=fake,
        )

    state = load_state(state_file)
    assert state.spreadsheet_id is not None
    assert state.presentation_id is not None
    assert state.last_pushed_at is None
    assert fake.slides.requests_log == []


def test_push_deck_creates_one_workbook_and_links_charts(
    fake_google: FakeGoogleServices,
    deck_copy: Path,
    tmp_path: Path,
) -> None:
    from autooffice.google.sync import push_deck

    staging = tmp_path / "deck.slides-upload.pptx"
    staging.write_bytes(b"PK\x03\x04fake")
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"

    first = push_deck(
        deck=deck_copy,
        staging=staging,
        state=state_file,
        services=fake_google,
    )
    second = push_deck(
        deck=deck_copy,
        staging=staging,
        state=state_file,
        services=fake_google,
    )

    assert first == (state_file,)
    assert second == (state_file,)
    operations = [operation for operation, _ in fake_google.sheets.operations]
    assert operations.count("create_spreadsheet") == 1
    state_text = state_file.read_text(encoding="utf-8")
    state = load_state(state_file)
    chart = state.charts["s02.chart1"]
    assert "presentation_id" in state_text
    assert "token" not in state_text
    assert state.spreadsheet_id is not None
    assert chart.sheet_id > 0
    assert chart.embedded_chart_id > 0
    assert chart.last_data_sha256
    assert len(_create_requests(fake_google)) == 2


def _two_chart_deck(google_deck: DeckIR) -> DeckIR:
    slide = google_deck.slides[1]
    chart = next(block for block in slide.blocks if block.block_type == "chart")
    second = replace(chart, block_id="chart2")
    return replace(
        google_deck,
        slides=(
            google_deck.slides[0],
            replace(slide, blocks=(*slide.blocks, second)),
        ),
    )


def test_chart_preflight_validates_all_geometry_before_first_batch(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    deck = _two_chart_deck(google_deck)
    links, _ = _links(fake_google, deck, google_theme)
    snapshot = make_snapshot(presentation_id="presentation-1")
    missing_geometry = PageElement(
        object_id="chart-s02-chart2",
        page_object_id="slide-s02",
        kind="shape",
        title=f"{CHART_MARKER_PREFIX}s02.chart2",
    )
    slide = snapshot.slides[1]
    snapshot = replace(
        snapshot,
        slides=(
            *snapshot.slides[:1],
            replace(slide, page_elements=(*slide.page_elements, missing_geometry)),
        ),
    )
    fake_google.slides.add_presentation(snapshot)

    with pytest.raises(ChartPlaceholderError, match="size/transform"):
        replace_chart_placeholders(
            fake_google.slides,
            "presentation-1",
            deck=deck,
            links=links,
        )

    assert fake_google.slides.requests_log == []


def test_push_deck_reuses_pending_presentation_only_for_same_deck(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
    make_snapshot: Callable[..., PresentationSnapshot],
    deck_copy: Path,
    tmp_path: Path,
) -> None:
    from autooffice.google.sync import push_deck

    workbook, _ = ensure_workbook(fake_google.sheets, title=str(google_deck.meta["title"]))
    staging = tmp_path / "deck.slides-upload.pptx"
    staging.write_bytes(b"PK\x03\x04fake")
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    fake_google.slides.add_presentation(make_snapshot(presentation_id="presentation-99"))
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256="b" * 64,
            presentation_id="presentation-99",
            presentation_url="https://docs.google.com/presentation/d/presentation-99/edit",
            spreadsheet_id=workbook.spreadsheet_id,
            spreadsheet_url=workbook.url,
        ),
        state_file,
    )

    push_deck(
        deck=deck_copy,
        staging=staging,
        state=state_file,
        services=fake_google,
    )

    assert len(fake_google.drive.uploads) == 1
    assert load_state(state_file).presentation_id != "presentation-99"


def test_push_deck_completes_pending_placeholders_for_unchanged_deck(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
    deck_copy: Path,
    tmp_path: Path,
) -> None:
    from autooffice.google.sync import push_deck

    workbook, _ = ensure_workbook(fake_google.sheets, title=str(google_deck.meta["title"]))
    staging = tmp_path / "deck.slides-upload.pptx"
    staging.write_bytes(b"PK\x03\x04fake")
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    fake_google.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256=deck_sha256(deck_copy),
            presentation_id="presentation-1",
            presentation_url="https://docs.google.com/presentation/d/presentation-1/edit",
            spreadsheet_id=workbook.spreadsheet_id,
            spreadsheet_url=workbook.url,
        ),
        state_file,
    )

    push_deck(
        deck=deck_copy,
        staging=staging,
        state=state_file,
        services=fake_google,
    )

    assert fake_google.drive.uploads == []
    state = load_state(state_file)
    assert state.presentation_id == "presentation-1"
    snapshot = fake_google.slides.get_presentation("presentation-1")
    assert not any(
        element.marker == f"{CHART_MARKER_PREFIX}s02.chart1"
        for element in snapshot.elements_including_notes()
    )


def test_push_deck_keeps_old_last_pushed_at_until_replacement_succeeds(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
    deck_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autooffice.google import sync as sync_module

    workbook, _ = ensure_workbook(fake_google.sheets, title=str(google_deck.meta["title"]))
    fake_google.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))
    staging = tmp_path / "deck.slides-upload.pptx"
    staging.write_bytes(b"PK\x03\x04fake")
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    old_pushed_at = "2026-11-13T08:00:00Z"
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256=deck_sha256(deck_copy),
            presentation_id="presentation-1",
            presentation_url="https://docs.google.com/presentation/d/presentation-1/edit",
            spreadsheet_id=workbook.spreadsheet_id,
            spreadsheet_url=workbook.url,
            last_pushed_at=old_pushed_at,
        ),
        state_file,
    )

    def fail_replacement(*args: object, **kwargs: object) -> PresentationSnapshot:
        raise ChartPlaceholderError("replacement gagal")

    with monkeypatch.context() as patch:
        patch.setattr(sync_module, "replace_chart_placeholders", fail_replacement)
        with pytest.raises(ChartPlaceholderError, match="replacement gagal"):
            sync_module.push_deck(
                deck=deck_copy,
                staging=staging,
                state=state_file,
                services=fake_google,
                now=datetime(2026, 11, 14, 0, 0, tzinfo=UTC),
            )

    after_failure = load_state(state_file)
    assert after_failure.last_pushed_at == old_pushed_at
    assert after_failure.presentation_id is not None
    assert after_failure.spreadsheet_id == workbook.spreadsheet_id

    sync_module.push_deck(
        deck=deck_copy,
        staging=staging,
        state=state_file,
        services=fake_google,
        now=datetime(2026, 11, 14, 1, 0, tzinfo=UTC),
    )

    assert load_state(state_file).last_pushed_at == "2026-11-14T01:00:00Z"


def test_push_deck_slides_403_does_not_upload_replacement(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
    deck_copy: Path,
    tmp_path: Path,
) -> None:
    from autooffice.google.sync import push_deck

    workbook, _ = ensure_workbook(fake_google.sheets, title=str(google_deck.meta["title"]))
    staging = tmp_path / "deck.slides-upload.pptx"
    staging.write_bytes(b"PK\x03\x04fake")
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    fake_google.slides.add_presentation(make_snapshot(presentation_id="presentation-1"))
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256=deck_sha256(deck_copy),
            presentation_id="presentation-1",
            presentation_url="https://docs.google.com/presentation/d/presentation-1/edit",
            spreadsheet_id=workbook.spreadsheet_id,
            spreadsheet_url=workbook.url,
        ),
        state_file,
    )
    original = fake_google.slides.get_presentation

    def forbidden(presentation_id: str) -> PresentationSnapshot:
        if presentation_id == "presentation-1":
            raise SlidesError("HTTP 403", code=403)
        return original(presentation_id)

    fake_google.slides.get_presentation = forbidden  # type: ignore[method-assign]

    with pytest.raises(GoogleSyncError, match="tidak dapat diakses"):
        push_deck(
            deck=deck_copy,
            staging=staging,
            state=state_file,
            services=fake_google,
        )

    assert fake_google.drive.uploads == []


def test_changed_deck_failure_keeps_old_digest_and_retry_uploads_fresh(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
    deck_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autooffice.google import sync as sync_module

    workbook, _ = ensure_workbook(fake_google.sheets, title=str(google_deck.meta["title"]))
    staging = tmp_path / "deck.slides-upload.pptx"
    staging.write_bytes(b"PK\x03\x04fake")
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    fake_google.slides.add_presentation(make_snapshot(presentation_id="presentation-99"))
    save_state(
        GoogleState(
            deck_path=deck_copy.name,
            deck_sha256="b" * 64,
            presentation_id="presentation-99",
            presentation_url="https://docs.google.com/presentation/d/presentation-99/edit",
            spreadsheet_id=workbook.spreadsheet_id,
            spreadsheet_url=workbook.url,
        ),
        state_file,
    )

    def fail_chart(*args: object, **kwargs: object) -> ChartLink:
        raise SheetsError("chart gagal")

    with monkeypatch.context() as patch:
        patch.setattr(sync_module, "ensure_sheet_chart", fail_chart)
        with pytest.raises(SheetsError, match="chart gagal"):
            sync_module.push_deck(
                deck=deck_copy,
                staging=staging,
                state=state_file,
                services=fake_google,
            )

    after_failure = load_state(state_file)
    assert after_failure.deck_sha256 == "b" * 64
    assert after_failure.presentation_id == "presentation-99"

    sync_module.push_deck(
        deck=deck_copy,
        staging=staging,
        state=state_file,
        services=fake_google,
    )

    assert len(fake_google.drive.uploads) == 1
    assert load_state(state_file).presentation_id != "presentation-99"


def test_push_deck_persists_workbook_before_second_chart_failure(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    deck_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autooffice.google import sync as sync_module

    staging = tmp_path / "deck.slides-upload.pptx"
    staging.write_bytes(b"PK\x03\x04fake")
    state_file = tmp_path / ".autooffice" / "state" / "deck.json"
    first_spec = build_chart_specs(google_deck)[0]
    second_spec = replace(first_spec, chart_id="s02.chart2")
    real_create = sync_module.ensure_sheet_chart
    calls = 0

    def fail_second_chart(*args: object, **kwargs: object) -> ChartLink:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SheetsError("chart kedua gagal")
        return real_create(*args, **kwargs)  # type: ignore[arg-type]

    with monkeypatch.context() as patch:
        patch.setattr(sync_module, "build_chart_specs", lambda _deck: (first_spec, second_spec))
        patch.setattr(sync_module, "ensure_sheet_chart", fail_second_chart)
        with pytest.raises(SheetsError, match="chart kedua"):
            sync_module.push_deck(
                deck=deck_copy,
                staging=staging,
                state=state_file,
                services=fake_google,
            )

    after_failure = load_state(state_file)
    assert after_failure.spreadsheet_id is not None
    assert after_failure.presentation_id is None

    sync_module.push_deck(
        deck=deck_copy,
        staging=staging,
        state=state_file,
        services=fake_google,
    )

    operations = [operation for operation, _ in fake_google.sheets.operations]
    assert operations.count("create_spreadsheet") == 1
    assert load_state(state_file).spreadsheet_id == after_failure.spreadsheet_id
