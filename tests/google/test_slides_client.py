"""Test adapter Slides, parser payload, preflight, dan request builder."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from types import SimpleNamespace

import pytest

from autooffice.deck.model import DeckIR
from autooffice.google import ChartPlaceholderError, SlidesError, TablePreflightError
from autooffice.google.charts import ChartLink
from autooffice.google.fake import FakeSlides
from autooffice.google.slides import (
    CHART_MARKER_PREFIX,
    ChartReplacementAction,
    ElementSize,
    ElementTransform,
    GoogleSlidesApi,
    PageElement,
    PresentationSnapshot,
    SlidesApi,
    SlideSnapshot,
    _require_placeholder,
    chart_ids,
    create_sheets_chart_request,
    delete_object_request,
    delete_text_request,
    find_chart_placeholders,
    insert_text_request,
    preflight_chart_replacements,
    preflight_native_tables,
    presentation_from_api,
    replace_chart_placeholders,
    table_requirements,
    verify_linked_charts,
)


class FakeRequest:
    """Request Slides palsu yang mengembalikan payload atau error."""

    def __init__(self, result: object) -> None:
        self.result = result

    def execute(self) -> object:
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakeSlidesService:
    """Service Slides minimal: ``presentations().get/batchUpdate().execute()``."""

    def __init__(
        self,
        *,
        get_result: object = None,
        batch_update_result: object = None,
    ) -> None:
        self.get_result = {} if get_result is None else get_result
        self.batch_update_result = {} if batch_update_result is None else batch_update_result
        self.calls: list[tuple[str, dict[str, object]]] = []

    def presentations(self) -> FakeSlidesService:
        return self

    def get(self, **kwargs: object) -> FakeRequest:
        self.calls.append(("get", kwargs))
        return FakeRequest(self.get_result)

    def batchUpdate(self, **kwargs: object) -> FakeRequest:
        self.calls.append(("batchUpdate", kwargs))
        return FakeRequest(self.batch_update_result)


class ServiceError(Exception):
    """Error HTTP gaya googleapiclient dengan status pada ``resp``."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.resp = SimpleNamespace(status=status)


def _shape_text(*contents: str) -> dict[str, object]:
    return {"textElements": [{"textRun": {"content": content}} for content in contents]}


def _full_payload() -> dict[str, object]:
    return {
        "presentationId": "presentation-1",
        "title": "Deck",
        "revisionId": "revision-1",
        "slides": [
            {
                "objectId": "slide-1",
                "pageElements": [
                    {
                        "objectId": "shape-1",
                        "title": "s01.title.text",
                        "description": "Judul",
                        "shape": {"text": _shape_text("Halo ", "dunia")},
                        "size": {
                            "width": {"magnitude": 100.4, "unit": ""},
                            "height": {"magnitude": 50, "unit": "PT"},
                        },
                        "transform": {
                            "scaleX": 2,
                            "scaleY": 3,
                            "translateX": 4,
                            "translateY": 5,
                            "unit": "PT",
                        },
                    },
                    {
                        "objectId": "shape-plain",
                        "shape": {"text": {"text": "Plain"}},
                    },
                    {
                        "objectId": "shape-empty",
                        "title": 42,
                        "description": 43,
                        "shape": {"text": {}},
                    },
                    {
                        "objectId": "shape-nonstring",
                        "shape": {
                            "text": {
                                "textElements": [{"textRun": {"content": 42}}],
                                "text": "fallback",
                            }
                        },
                    },
                    {
                        "objectId": "table-1",
                        "title": "s01.table1",
                        "table": {
                            "rows": 2,
                            "columns": 2,
                            "tableRows": [
                                {
                                    "tableCells": [
                                        {"text": {"textElements": [{"textRun": {"content": "A"}}]}},
                                        {"text": {"text": "B"}},
                                    ]
                                },
                                {"tableCells": [{"text": {"text": "C"}}, {}]},
                            ],
                            "tableColumns": [{}, {}],
                        },
                    },
                    {
                        "objectId": "table-derived",
                        "table": {
                            "tableRows": [
                                {
                                    "tableCells": [
                                        {"text": {"textElements": [{"textRun": {"content": "D"}}]}}
                                    ]
                                }
                            ],
                            "tableColumns": [{}],
                        },
                    },
                    {
                        "objectId": "chart-1",
                        "sheetsChart": {
                            "spreadsheetId": "spreadsheet-1",
                            "chartId": 42,
                        },
                    },
                    {
                        "objectId": "chart-invalid",
                        "sheetsChart": {"spreadsheetId": 42, "chartId": "x"},
                    },
                    {"objectId": "image-1", "image": {"contentUrl": "https://example.com/x.png"}},
                    {"objectId": "group-1", "elementGroup": {"children": []}},
                    {"objectId": "other-1"},
                    {"title": "tanpa-object-id"},
                ],
                "slideProperties": {
                    "notesPage": {
                        "objectId": "notes-1",
                        "pageElements": [
                            {
                                "objectId": "notes-shape",
                                "shape": {"text": {"text": "Catatan"}},
                            }
                        ],
                    }
                },
            }
        ],
    }


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


def _link(
    chart_id: str = "s02.chart1",
    *,
    spreadsheet_id: str = "spreadsheet-1",
    embedded_chart_id: int = 42,
) -> ChartLink:
    return ChartLink(
        spreadsheet_id=spreadsheet_id,
        chart_id=chart_id,
        tab_name=chart_id,
        sheet_id=1,
        embedded_chart_id=embedded_chart_id,
        data_sha256="a" * 64,
    )


def _replace_element(
    snapshot: PresentationSnapshot,
    object_id: str,
    replacement: PageElement,
) -> PresentationSnapshot:
    slides = []
    for slide in snapshot.slides:
        slides.append(
            replace(
                slide,
                page_elements=tuple(
                    replacement if element.object_id == object_id else element
                    for element in slide.page_elements
                ),
                notes_page_elements=tuple(
                    replacement if element.object_id == object_id else element
                    for element in slide.notes_page_elements
                ),
            )
        )
    return replace(snapshot, slides=tuple(slides))


def _append_element(
    snapshot: PresentationSnapshot,
    element: PageElement,
    *,
    slide_index: int = 1,
) -> PresentationSnapshot:
    slides = list(snapshot.slides)
    slide = slides[slide_index]
    slides[slide_index] = replace(
        slide,
        page_elements=(*slide.page_elements, element),
    )
    return replace(snapshot, slides=tuple(slides))


def _chart_placeholder(
    snapshot: PresentationSnapshot,
    chart_id: str = "s02.chart1",
) -> PageElement:
    marker = f"{CHART_MARKER_PREFIX}{chart_id}"
    return next(element for element in snapshot.elements() if element.marker == marker)


def _chart_snapshot(
    make_snapshot: Callable[..., PresentationSnapshot],
    *,
    options: SimpleNamespace | None = None,
) -> PresentationSnapshot:
    return make_snapshot(presentation_id="presentation-1", options=options)


def test_get_presentation_maps_payload_to_typed_snapshot() -> None:
    service = FakeSlidesService(get_result=_full_payload())

    snapshot = GoogleSlidesApi(service).get_presentation("presentation-1")

    assert snapshot.presentation_id == "presentation-1"
    assert snapshot.title == "Deck"
    assert snapshot.revision_id == "revision-1"
    assert len(snapshot.slides) == 1
    slide = snapshot.slides[0]
    assert slide.object_id == "slide-1"
    assert slide.index == 0
    elements = {element.object_id: element for element in snapshot.elements()}
    assert set(elements) == {
        "shape-1",
        "shape-plain",
        "shape-empty",
        "shape-nonstring",
        "table-1",
        "table-derived",
        "chart-1",
        "chart-invalid",
        "image-1",
        "group-1",
        "other-1",
    }
    shape = elements["shape-1"]
    assert shape.kind == "shape"
    assert shape.text == "Halo dunia"
    assert shape.size == ElementSize(width=100, height=50, unit="PT")
    assert shape.transform == ElementTransform(
        scale_x=2.0,
        scale_y=3.0,
        translate_x=4.0,
        translate_y=5.0,
        unit="PT",
    )
    assert elements["shape-plain"].text == "Plain"
    assert elements["shape-empty"].text == ""
    assert elements["shape-empty"].title is None
    assert elements["shape-empty"].description is None
    assert elements["shape-nonstring"].text == "fallback"
    table = elements["table-1"]
    assert table.is_table
    assert (table.row_count, table.column_count) == (2, 2)
    assert table.cells == (("A", "B"), ("C", ""))
    derived = elements["table-derived"]
    assert (derived.row_count, derived.column_count) == (1, 1)
    chart = elements["chart-1"]
    assert chart.kind == "sheets_chart"
    assert chart.spreadsheet_id == "spreadsheet-1"
    assert chart.chart_id == 42
    invalid = elements["chart-invalid"]
    assert invalid.spreadsheet_id is None
    assert invalid.chart_id is None
    assert elements["image-1"].kind == "image"
    assert elements["group-1"].kind == "group"
    assert elements["other-1"].kind == "other"
    assert len(snapshot.elements_including_notes()) == len(elements) + 1
    notes = slide.notes_page_elements[0]
    assert notes.object_id == "notes-shape"
    assert notes.page_object_id == "notes-1"
    assert notes.text == "Catatan"
    assert service.calls == [("get", {"presentationId": "presentation-1"})]


def test_get_presentation_uses_slide_id_for_notes_without_page_id() -> None:
    payload = {
        "presentationId": "presentation-1",
        "slides": [
            {
                "objectId": "slide-1",
                "slideProperties": {
                    "notesPage": {
                        "pageElements": [
                            {
                                "objectId": "notes-shape",
                                "shape": {"text": {"text": "Catatan"}},
                            }
                        ]
                    }
                },
            }
        ],
    }

    snapshot = presentation_from_api(payload)

    assert snapshot.slides[0].notes_page_elements[0].page_object_id == "slide-1"


def test_presentation_from_api_accepts_minimal_payload() -> None:
    snapshot = presentation_from_api({"presentationId": "presentation-1"})

    assert snapshot.title == ""
    assert snapshot.revision_id is None
    assert snapshot.slides == ()


@pytest.mark.parametrize(
    "payload",
    [{}, {"presentationId": " "}],
    ids=["missing", "blank"],
)
def test_presentation_from_api_requires_presentation_id(payload: dict[str, object]) -> None:
    with pytest.raises(SlidesError, match="presentationId"):
        presentation_from_api(payload)


def test_presentation_from_api_requires_slide_object_id() -> None:
    with pytest.raises(SlidesError, match="Slide index 0"):
        presentation_from_api({"presentationId": "presentation-1", "slides": [{}]})


def test_presentation_from_api_ignores_non_sequence_slides() -> None:
    snapshot = presentation_from_api({"presentationId": "presentation-1", "slides": "invalid"})

    assert snapshot.slides == ()


def test_presentation_from_api_tolerates_malformed_table_rows() -> None:
    payload = {
        "presentationId": "presentation-1",
        "slides": [
            {
                "objectId": "slide-1",
                "pageElements": [
                    {
                        "objectId": "table-1",
                        "table": {"rows": 1, "columns": 1, "tableRows": "invalid"},
                    }
                ],
            }
        ],
    }

    snapshot = presentation_from_api(payload)

    table = snapshot.elements()[0]
    assert table.cells == ()


def test_element_size_parses_and_rejects_invalid_dimensions() -> None:
    assert ElementSize.from_api(None) is None
    assert ElementSize.from_api({"width": {}, "height": {}}) is None
    assert ElementSize.from_api({"width": {"magnitude": True}, "height": {"magnitude": 20}}) is None
    assert ElementSize.from_api(
        {"width": {"magnitude": 10, "unit": ""}, "height": {"magnitude": 20, "unit": ""}}
    ) == ElementSize(width=10, height=20, unit="EMU")


def test_element_transform_parses_defaults_and_valid_values() -> None:
    assert ElementTransform.from_api(None) is None
    assert ElementTransform.from_api({}) is None
    assert ElementTransform.from_api(
        {
            "scaleX": "invalid",
            "scaleY": True,
            "translateX": None,
            "translateY": 1.5,
            "unit": "PT",
        }
    ) == ElementTransform(
        scale_x=1.0,
        scale_y=1.0,
        translate_x=0.0,
        translate_y=1.5,
        unit="PT",
    )


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (lambda: ElementSize(width=0, height=10), "positif"),
        (lambda: ElementSize(width=10, height=10, unit=" "), "Unit"),
        (
            lambda: PageElement(object_id=" ", page_object_id="slide", kind="shape"),
            "objectId",
        ),
        (
            lambda: PageElement(object_id="shape", page_object_id=" ", kind="shape"),
            "pageObjectId",
        ),
        (
            lambda: PageElement(
                object_id="shape",
                page_object_id="slide",
                kind="shape",
                row_count=-1,
            ),
            "negatif",
        ),
        (
            lambda: PageElement(
                object_id="table",
                page_object_id="slide",
                kind="table",
                row_count=0,
                column_count=1,
            ),
            "baris",
        ),
        (
            lambda: PageElement(
                object_id="table",
                page_object_id="slide",
                kind="table",
                row_count=1,
                column_count=0,
            ),
            "kolom",
        ),
        (lambda: SlideSnapshot(object_id=" ", index=0), "Slide"),
        (
            lambda: PresentationSnapshot(
                presentation_id=" ",
                title="Deck",
                revision_id=None,
                slides=(),
            ),
            "presentationId",
        ),
    ],
    ids=[
        "size-zero",
        "size-unit",
        "shape-object",
        "shape-page",
        "shape-negative",
        "table-rows",
        "table-columns",
        "slide-object",
        "presentation-object",
    ],
)
def test_slides_value_objects_reject_invalid_fields(
    factory: Callable[[], object],
    match: str,
) -> None:
    with pytest.raises(SlidesError, match=match):
        factory()


def test_page_element_marker_prefers_title_and_exposes_table_flag() -> None:
    titled = PageElement(
        object_id="shape",
        page_object_id="slide",
        kind="shape",
        title="autooffice:chart:s01.chart1",
        description="description",
    )
    untitled = replace(titled, title=None)

    assert titled.marker == "autooffice:chart:s01.chart1"
    assert untitled.marker == "description"
    assert titled.is_table is False


def test_slides_api_rejects_blank_presentation_id() -> None:
    service = FakeSlidesService()

    with pytest.raises(SlidesError, match="presentationId"):
        GoogleSlidesApi(service).get_presentation(" ")

    assert service.calls == []


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_get_presentation_wraps_http_errors_without_retry(status: int) -> None:
    service = FakeSlidesService(get_result=ServiceError(status))

    with pytest.raises(SlidesError, match=f"HTTP {status}"):
        GoogleSlidesApi(service).get_presentation("presentation-1")

    assert len(service.calls) == 1


def test_get_presentation_wraps_generic_service_error() -> None:
    service = FakeSlidesService(get_result=RuntimeError("presentation hilang"))

    with pytest.raises(SlidesError, match="tidak dapat dibaca: presentation hilang"):
        GoogleSlidesApi(service).get_presentation("presentation-1")


def test_batch_update_short_circuits_empty_requests() -> None:
    service = FakeSlidesService()

    result = GoogleSlidesApi(service).batch_update("presentation-1", [])

    assert result == {"replies": []}
    assert service.calls == []


def test_batch_update_sends_requests_and_returns_payload() -> None:
    payload = {"replies": [{"deleteObject": {}}], "revisionId": "revision-2"}
    service = FakeSlidesService(batch_update_result=payload)

    result = GoogleSlidesApi(service).batch_update(
        "presentation-1",
        [{"deleteObject": {"objectId": "shape-1"}}],
    )

    assert result == payload
    assert service.calls == [
        (
            "batchUpdate",
            {
                "presentationId": "presentation-1",
                "body": {"requests": [{"deleteObject": {"objectId": "shape-1"}}]},
            },
        )
    ]


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_batch_update_wraps_http_errors_without_retry(status: int) -> None:
    service = FakeSlidesService(batch_update_result=ServiceError(status))

    with pytest.raises(SlidesError, match=f"HTTP {status}"):
        GoogleSlidesApi(service).batch_update(
            "presentation-1",
            [{"deleteObject": {"objectId": "x"}}],
        )

    assert len(service.calls) == 1


def test_batch_update_rejects_non_object_payload() -> None:
    service = FakeSlidesService(batch_update_result=[])

    with pytest.raises(SlidesError, match="bukan objek JSON"):
        GoogleSlidesApi(service).batch_update("presentation-1", [{"deleteObject": {}}])


def test_google_slides_adapter_satisfies_protocol() -> None:
    assert isinstance(GoogleSlidesApi(FakeSlidesService()), SlidesApi)


def test_table_requirements_reject_table_without_columns(google_deck: DeckIR) -> None:
    deck = _deck_with_table_fields(google_deck, {"rows": (("data",),)})

    with pytest.raises(TablePreflightError, match="tidak memiliki kolom"):
        table_requirements(deck)


def test_table_requirements_reject_table_without_rows(google_deck: DeckIR) -> None:
    deck = _deck_with_table_fields(google_deck, {"columns": ("A",)})

    with pytest.raises(TablePreflightError, match="tidak memiliki baris"):
        table_requirements(deck)


def _deck_with_table_fields(deck: DeckIR, fields: Mapping[str, object]) -> DeckIR:
    source = deck.slides[0]
    table = next(block for block in source.blocks if block.block_type == "table")
    slide = replace(source, blocks=(replace(table, fields=fields),))
    return replace(deck, slides=(slide,))


def test_chart_ids_lists_chart_blocks_in_order(google_deck: DeckIR) -> None:
    assert chart_ids(google_deck) == ("s02.chart1",)


def test_find_chart_placeholders_rejects_duplicate_expected_ids(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    with pytest.raises(ChartPlaceholderError, match="duplikat"):
        find_chart_placeholders(make_snapshot(), ("s02.chart1", "s02.chart1"))


def test_find_chart_placeholders_rejects_unknown_marker(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = _append_element(
        make_snapshot(),
        PageElement(
            object_id="unknown-chart",
            page_object_id="slide-s02",
            kind="shape",
            title="autooffice:chart:s99.chart9",
        ),
    )

    with pytest.raises(ChartPlaceholderError, match="tidak dikenal"):
        find_chart_placeholders(snapshot, ("s02.chart1",))


def test_find_chart_placeholders_rejects_non_shape_element(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    placeholder = _chart_placeholder(snapshot)
    image = replace(placeholder, kind="image")

    with pytest.raises(ChartPlaceholderError, match="bukan shape"):
        find_chart_placeholders(
            _replace_element(snapshot, placeholder.object_id, image),
            ("s02.chart1",),
        )


def test_find_chart_placeholders_ignores_malformed_marker_variants(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    for index, marker in enumerate(
        ["autooffice:chart:", "autooffice:chart:a:b", "autooffice:chart:a b"]
    ):
        snapshot = _append_element(
            snapshot,
            PageElement(
                object_id=f"malformed-{index}",
                page_object_id="slide-s02",
                kind="shape",
                title=marker,
            ),
        )

    placeholders = find_chart_placeholders(snapshot, ("s02.chart1",))

    assert set(placeholders) == {"s02.chart1"}


def test_preflight_native_tables_rejects_duplicate_table(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    table = next(element for element in snapshot.elements() if element.kind == "table")
    duplicated = _append_element(
        snapshot,
        replace(table, object_id="table-duplicate"),
        slide_index=0,
    )

    with pytest.raises(TablePreflightError, match="ditemukan 2 kali"):
        preflight_native_tables(google_deck, duplicated)


def test_preflight_chart_replacements_rejects_missing_links(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    with pytest.raises(SlidesError, match=r"link hilang: s02\.chart1"):
        preflight_chart_replacements(google_deck, make_snapshot(), {})


def test_preflight_chart_replacements_rejects_extra_links(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    links = {"s02.chart1": _link(), "s99.chart9": _link("s99.chart9")}

    with pytest.raises(SlidesError, match=r"link asing: s99\.chart9"):
        preflight_chart_replacements(google_deck, make_snapshot(), links)


def test_preflight_chart_replacements_rejects_unknown_placeholder(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = _append_element(
        make_snapshot(),
        PageElement(
            object_id="unknown-chart",
            page_object_id="slide-s02",
            kind="shape",
            title="autooffice:chart:s99.chart9",
        ),
    )

    with pytest.raises(ChartPlaceholderError, match="tidak dikenal"):
        preflight_chart_replacements(google_deck, snapshot, {"s02.chart1": _link()})


def test_preflight_chart_replacements_rejects_placeholder_moved_to_another_slide(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    placeholder = _chart_placeholder(snapshot)
    first, second = snapshot.slides[0], snapshot.slides[1]
    snapshot = replace(
        snapshot,
        slides=(
            replace(first, page_elements=(*first.page_elements, placeholder)),
            replace(
                second,
                page_elements=tuple(
                    element
                    for element in second.page_elements
                    if element.object_id != placeholder.object_id
                ),
            ),
        ),
    )

    with pytest.raises(ChartPlaceholderError, match=r"slide index 1.*slide index 2"):
        preflight_chart_replacements(google_deck, snapshot, {"s02.chart1": _link()})


def test_preflight_chart_replacements_rejects_one_on_slide_and_one_off_slide_placeholder(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    placeholder = _chart_placeholder(snapshot)
    duplicate = replace(placeholder, object_id="chart-offslide")
    snapshot = _append_element(snapshot, duplicate, slide_index=0)
    slides = FakeSlides()
    slides.add_presentation(snapshot)

    with pytest.raises(ChartPlaceholderError, match="ditemukan 2 kali"):
        replace_chart_placeholders(
            slides,
            "presentation-1",
            deck=google_deck,
            links={"s02.chart1": _link()},
        )

    assert slides.requests_log == []


def test_preflight_chart_replacements_rejects_linked_chart_moved_to_another_slide(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    moved = PageElement(
        object_id="linked-chart-moved",
        page_object_id="slide-s01",
        kind="sheets_chart",
        spreadsheet_id="spreadsheet-1",
        chart_id=42,
    )
    snapshot = _append_element(snapshot, moved, slide_index=0)

    with pytest.raises(
        ChartPlaceholderError,
        match=r"Linked chart untuk 's02\.chart1' berada di slide index 1.*slide index 2",
    ):
        preflight_chart_replacements(google_deck, snapshot, {"s02.chart1": _link()})


def test_preflight_chart_replacements_rejects_duplicate_linked_chart(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    linked = PageElement(
        object_id="linked-chart",
        page_object_id="slide-s02",
        kind="sheets_chart",
        spreadsheet_id="spreadsheet-1",
        chart_id=42,
    )
    snapshot = _append_element(
        _append_element(make_snapshot(), linked),
        replace(linked, object_id="linked-2"),
    )

    with pytest.raises(ChartPlaceholderError, match="ditemukan 2 kali"):
        preflight_chart_replacements(google_deck, snapshot, {"s02.chart1": _link()})


def test_preflight_chart_replacements_rejects_duplicate_placeholder(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    placeholder = _chart_placeholder(snapshot)
    duplicated = _append_element(
        snapshot,
        replace(placeholder, object_id="chart-duplicate"),
    )

    with pytest.raises(ChartPlaceholderError, match="ditemukan 2 kali"):
        preflight_chart_replacements(google_deck, duplicated, {"s02.chart1": _link()})


def test_preflight_chart_replacements_rejects_non_shape_placeholder(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    placeholder = _chart_placeholder(snapshot)
    image = replace(placeholder, kind="image")

    with pytest.raises(ChartPlaceholderError, match="bukan shape"):
        preflight_chart_replacements(
            google_deck,
            _replace_element(snapshot, placeholder.object_id, image),
            {"s02.chart1": _link()},
        )


def test_preflight_chart_replacements_rejects_missing_placeholder_and_link(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = _chart_snapshot(
        make_snapshot,
        options=_options(include_chart_placeholders=False),
    )

    with pytest.raises(ChartPlaceholderError, match="linked chart yang cocok juga tidak ada"):
        preflight_chart_replacements(google_deck, snapshot, {"s02.chart1": _link()})


def test_preflight_chart_replacements_rejects_geometry_conflict(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    placeholder = _chart_placeholder(snapshot)
    conflict = PageElement(
        object_id="foreign-linked-chart",
        page_object_id="slide-s02",
        kind="sheets_chart",
        spreadsheet_id="other-spreadsheet",
        chart_id=99,
        size=placeholder.size,
        transform=placeholder.transform,
    )

    with pytest.raises(ChartPlaceholderError, match="sudah ditempati"):
        preflight_chart_replacements(
            google_deck,
            _append_element(snapshot, conflict),
            {"s02.chart1": _link()},
        )


def test_preflight_chart_replacements_deletes_placeholder_when_link_exists(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    placeholder = _chart_placeholder(snapshot)
    linked = PageElement(
        object_id="linked-chart",
        page_object_id="slide-s02",
        kind="sheets_chart",
        spreadsheet_id="spreadsheet-1",
        chart_id=42,
        size=placeholder.size,
        transform=placeholder.transform,
    )

    plan = preflight_chart_replacements(
        google_deck,
        _append_element(snapshot, linked),
        {"s02.chart1": _link()},
    )

    assert [action.action for action in plan.actions] == ["delete_placeholder"]
    assert plan.actions[0].placeholder == placeholder
    assert plan.actions[0].existing == linked


def test_replace_chart_placeholders_only_deletes_stale_placeholder(
    google_deck: DeckIR,
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    snapshot = make_snapshot()
    placeholder = _chart_placeholder(snapshot)
    linked = PageElement(
        object_id="linked-chart",
        page_object_id="slide-s02",
        kind="sheets_chart",
        spreadsheet_id="spreadsheet-1",
        chart_id=42,
    )
    slides = FakeSlides()
    slides.add_presentation(_append_element(snapshot, linked))

    updated = replace_chart_placeholders(
        slides,
        "presentation-1",
        deck=google_deck,
        links={"s02.chart1": _link()},
    )

    assert slides.requests_log == [{"deleteObject": {"objectId": placeholder.object_id}}]
    assert not any(
        element.marker == f"{CHART_MARKER_PREFIX}s02.chart1"
        for element in updated.elements_including_notes()
    )
    assert len([element for element in updated.elements() if element.kind == "sheets_chart"]) == 1


def test_verify_linked_charts_rejects_duplicate_match(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    linked = PageElement(
        object_id="linked-chart",
        page_object_id="slide-s02",
        kind="sheets_chart",
        spreadsheet_id="spreadsheet-1",
        chart_id=42,
    )
    snapshot = _append_element(
        _append_element(make_snapshot(), linked),
        replace(linked, object_id="linked-2"),
    )

    with pytest.raises(ChartPlaceholderError, match="ditemukan 2 kali setelah replacement"):
        verify_linked_charts(snapshot, {"s02.chart1": _link()})


def test_verify_linked_charts_rejects_leftover_placeholder(
    make_snapshot: Callable[..., PresentationSnapshot],
) -> None:
    linked = PageElement(
        object_id="linked-chart",
        page_object_id="slide-s02",
        kind="sheets_chart",
        spreadsheet_id="spreadsheet-1",
        chart_id=42,
    )

    with pytest.raises(ChartPlaceholderError, match="tersisa setelah replacement"):
        verify_linked_charts(
            _append_element(make_snapshot(), linked),
            {"s02.chart1": _link()},
        )


def test_create_sheets_chart_request_uses_literal_element_properties() -> None:
    placeholder = PageElement(
        object_id="placeholder-chart",
        page_object_id="slide-s02",
        kind="shape",
        size=ElementSize(width=123, height=45, unit="PT"),
        transform=ElementTransform(
            scale_x=2.0,
            scale_y=3.0,
            translate_x=10.0,
            translate_y=20.0,
            unit="PT",
        ),
    )

    request = create_sheets_chart_request(_link(), placeholder)

    assert request == {
        "createSheetsChart": {
            "spreadsheetId": "spreadsheet-1",
            "chartId": 42,
            "linkingMode": "LINKED",
            "elementProperties": {
                "pageObjectId": "slide-s02",
                "size": {
                    "width": {"magnitude": 123, "unit": "PT"},
                    "height": {"magnitude": 45, "unit": "PT"},
                },
                "transform": {
                    "scaleX": 2.0,
                    "scaleY": 3.0,
                    "translateX": 10.0,
                    "translateY": 20.0,
                    "unit": "PT",
                },
            },
        }
    }


@pytest.mark.parametrize(
    "placeholder",
    [
        PageElement(object_id="shape", page_object_id="slide", kind="shape"),
        PageElement(
            object_id="shape",
            page_object_id="slide",
            kind="shape",
            size=ElementSize(width=10, height=10),
        ),
    ],
    ids=["without-size", "without-transform"],
)
def test_create_sheets_chart_request_requires_geometry(placeholder: PageElement) -> None:
    with pytest.raises(ChartPlaceholderError, match="tidak memiliki size/transform"):
        create_sheets_chart_request(_link(), placeholder)


def test_request_builders_reject_blank_ids() -> None:
    with pytest.raises(SlidesError, match="deleteObject"):
        delete_object_request(" ")
    with pytest.raises(SlidesError, match="deleteText"):
        delete_text_request(" ")
    with pytest.raises(SlidesError, match="insertText memerlukan objectId"):
        insert_text_request(" ", "text")
    with pytest.raises(SlidesError, match="insertText memerlukan teks"):
        insert_text_request("shape", " ")


def test_text_request_builders_include_cell_location() -> None:
    assert delete_text_request("table", cell_location=(1, 2)) == {
        "deleteText": {
            "objectId": "table",
            "textRange": {"type": "ALL"},
            "cellLocation": {"rowIndex": 1, "columnIndex": 2},
        }
    }
    assert insert_text_request("table", "value", cell_location=(1, 2)) == {
        "insertText": {
            "objectId": "table",
            "insertionIndex": 0,
            "text": "value",
            "cellLocation": {"rowIndex": 1, "columnIndex": 2},
        }
    }
    assert delete_text_request("shape") == {
        "deleteText": {"objectId": "shape", "textRange": {"type": "ALL"}}
    }
    assert insert_text_request("shape", "value") == {
        "insertText": {"objectId": "shape", "insertionIndex": 0, "text": "value"}
    }


@pytest.mark.parametrize("builder", [delete_text_request, insert_text_request])
def test_text_request_builders_reject_negative_cell(builder: Callable[..., object]) -> None:
    arguments: tuple[str, ...] = ("table", "text") if builder is insert_text_request else ("table",)

    with pytest.raises(SlidesError, match="tidak boleh negatif"):
        builder(*arguments, cell_location=(-1, 0))


def test_require_placeholder_rejects_action_without_placeholder() -> None:
    action = ChartReplacementAction(
        chart_id="s02.chart1",
        action="replace",
        placeholder=None,
        existing=None,
    )

    with pytest.raises(ChartPlaceholderError, match="tidak memiliki placeholder"):
        _require_placeholder(action)
