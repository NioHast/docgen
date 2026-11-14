"""Test adapter GoogleSheetsApi dengan service palsu tanpa panggilan jaringan."""

from collections.abc import Callable, Mapping
from types import SimpleNamespace

import pytest

from autooffice.google import SheetsError
from autooffice.google.sheets import (
    ChartRecord,
    GoogleSheetsApi,
    SheetRef,
    SpreadsheetRef,
)


class FakeRequest:
    """Request Sheets palsu yang mengembalikan payload atau error."""

    def __init__(self, result: object) -> None:
        self.result = result

    def execute(self) -> object:
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakeSheetsService:
    """Service Sheets minimal untuk create, get, batchUpdate, dan values.update."""

    def __init__(
        self,
        *,
        create_result: object = None,
        get_result: object = None,
        batch_update_result: object = None,
        update_result: object = None,
    ) -> None:
        self.create_result = {} if create_result is None else create_result
        self.get_result = {} if get_result is None else get_result
        self.batch_update_result = {} if batch_update_result is None else batch_update_result
        self.update_result = {} if update_result is None else update_result
        self.calls: list[tuple[str, dict[str, object]]] = []

    def spreadsheets(self) -> FakeSheetsService:
        return self

    def values(self) -> FakeSheetsService:
        return self

    def create(self, **kwargs: object) -> FakeRequest:
        self.calls.append(("create", kwargs))
        return FakeRequest(self.create_result)

    def get(self, **kwargs: object) -> FakeRequest:
        self.calls.append(("get", kwargs))
        return FakeRequest(self.get_result)

    def batchUpdate(self, **kwargs: object) -> FakeRequest:
        self.calls.append(("batchUpdate", kwargs))
        return FakeRequest(self.batch_update_result)

    def update(self, **kwargs: object) -> FakeRequest:
        self.calls.append(("values.update", kwargs))
        return FakeRequest(self.update_result)


class ServiceError(Exception):
    """Error HTTP gaya googleapiclient dengan status pada ``resp`` atau ``code``."""

    def __init__(self, *, status: int | None = None, code: int | None = None) -> None:
        label = status if status is not None else code
        super().__init__(f"HTTP {label}")
        if status is not None:
            self.resp = SimpleNamespace(status=status)
        if code is not None:
            self.code = code


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: SpreadsheetRef(" ", "https://docs.google.com/spreadsheets/d/x/edit", "Deck"),
            "Spreadsheet ID",
        ),
        (
            lambda: SpreadsheetRef("x", "https://example.com/x", "Deck"),
            "URL spreadsheet",
        ),
        (lambda: SheetRef(True, "Tab"), "integer"),
        (lambda: SheetRef(-1, "Tab"), "negatif"),
        (lambda: SheetRef(1, " "), "Judul"),
        (lambda: ChartRecord(False, {}), "integer"),
        (lambda: ChartRecord(0, {}), "positif"),
    ],
    ids=[
        "spreadsheet-id",
        "spreadsheet-url",
        "sheet-bool",
        "sheet-negative",
        "sheet-title",
        "chart-bool",
        "chart-zero",
    ],
)
def test_sheets_value_objects_reject_invalid_fields(
    factory: Callable[[], object],
    match: str,
) -> None:
    with pytest.raises(SheetsError, match=match):
        factory()


def test_create_spreadsheet_builds_body_and_uses_local_title() -> None:
    service = FakeSheetsService(
        create_result={
            "spreadsheetId": "spreadsheet-1",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/spreadsheet-1/edit",
        }
    )

    reference = GoogleSheetsApi(service).create_spreadsheet("AutoOffice Charts - Deck")

    assert reference == SpreadsheetRef(
        spreadsheet_id="spreadsheet-1",
        url="https://docs.google.com/spreadsheets/d/spreadsheet-1/edit",
        title="AutoOffice Charts - Deck",
    )
    assert service.calls == [
        (
            "create",
            {
                "body": {"properties": {"title": "AutoOffice Charts - Deck"}},
                "fields": "spreadsheetId,spreadsheetUrl",
            },
        )
    ]


def test_create_spreadsheet_rejects_blank_title() -> None:
    service = FakeSheetsService()

    with pytest.raises(SheetsError, match="Judul spreadsheet"):
        GoogleSheetsApi(service).create_spreadsheet(" ")

    assert service.calls == []


def test_create_spreadsheet_rejects_missing_id() -> None:
    service = FakeSheetsService(create_result={"spreadsheetUrl": "https://example.com"})

    with pytest.raises(SheetsError, match="spreadsheetId"):
        GoogleSheetsApi(service).create_spreadsheet("Deck")


def test_create_spreadsheet_rejects_non_object_payload() -> None:
    service = FakeSheetsService(create_result=[])

    with pytest.raises(SheetsError, match="bukan objek JSON"):
        GoogleSheetsApi(service).create_spreadsheet("Deck")


def test_create_spreadsheet_wraps_service_error() -> None:
    service = FakeSheetsService(create_result=RuntimeError("quota"))

    with pytest.raises(SheetsError, match="Pembuatan spreadsheet gagal: quota"):
        GoogleSheetsApi(service).create_spreadsheet("Deck")


def test_get_spreadsheet_reads_title_from_properties() -> None:
    service = FakeSheetsService(
        get_result={
            "spreadsheetId": "spreadsheet-1",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/spreadsheet-1/edit",
            "properties": {"title": "Remote title"},
            "title": "Top-level must not win",
        }
    )

    reference = GoogleSheetsApi(service).get_spreadsheet("spreadsheet-1")

    assert reference == SpreadsheetRef(
        spreadsheet_id="spreadsheet-1",
        url="https://docs.google.com/spreadsheets/d/spreadsheet-1/edit",
        title="Remote title",
    )
    operation, kwargs = service.calls[0]
    assert operation == "get"
    assert kwargs["spreadsheetId"] == "spreadsheet-1"
    assert kwargs["includeGridData"] is False


def test_get_spreadsheet_derives_url_and_blank_title_from_short_payload() -> None:
    service = FakeSheetsService(get_result={"spreadsheetId": "spreadsheet-1"})

    reference = GoogleSheetsApi(service).get_spreadsheet("spreadsheet-1")

    assert reference is not None
    assert reference.url == "https://docs.google.com/spreadsheets/d/spreadsheet-1/edit"
    assert reference.title == ""


def test_get_spreadsheet_maps_http_404_response_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = GoogleSheetsApi(FakeSheetsService())

    def missing(_spreadsheet_id: str) -> Mapping[str, object]:
        raise ServiceError(status=404)

    monkeypatch.setattr(api, "_get_spreadsheet_payload", missing)

    assert api.get_spreadsheet("missing") is None


def test_get_spreadsheet_maps_http_404_code_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = GoogleSheetsApi(FakeSheetsService())

    def missing(_spreadsheet_id: str) -> Mapping[str, object]:
        raise ServiceError(code=404)

    monkeypatch.setattr(api, "_get_spreadsheet_payload", missing)

    assert api.get_spreadsheet("missing") is None


def test_get_spreadsheet_maps_service_404_to_none_without_retry() -> None:
    service = FakeSheetsService(get_result=ServiceError(status=404))

    assert GoogleSheetsApi(service).get_spreadsheet("spreadsheet-1") is None
    assert len(service.calls) == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_get_spreadsheet_wraps_non_404_http_errors_without_retry(status: int) -> None:
    service = FakeSheetsService(get_result=ServiceError(status=status))

    with pytest.raises(SheetsError, match=f"HTTP {status}") as caught:
        GoogleSheetsApi(service).get_spreadsheet("spreadsheet-1")

    assert caught.value.code == status
    assert len(service.calls) == 1


def test_get_spreadsheet_wraps_non_mapping_payload() -> None:
    service = FakeSheetsService(get_result=[])

    with pytest.raises(SheetsError, match="bukan objek JSON"):
        GoogleSheetsApi(service).get_spreadsheet("spreadsheet-1")


def test_find_sheet_matches_title_and_reads_sheet_id() -> None:
    service = FakeSheetsService(
        get_result={
            "spreadsheetId": "spreadsheet-1",
            "sheets": [
                {"properties": {"sheetId": 3, "title": "Sheet1"}},
                {"properties": {"sheetId": 7, "title": "chart-tab"}},
            ],
        }
    )

    result = GoogleSheetsApi(service).find_sheet("spreadsheet-1", "chart-tab")

    assert result == SheetRef(sheet_id=7, title="chart-tab")


def test_find_sheet_returns_none_for_unknown_or_malformed_tabs() -> None:
    service = FakeSheetsService(
        get_result={
            "sheets": [
                None,
                {"properties": "not-an-object"},
                {"properties": {"sheetId": 1, "title": "other"}},
            ]
        }
    )

    assert GoogleSheetsApi(service).find_sheet("spreadsheet-1", "missing") is None


def test_find_sheet_returns_none_for_non_sequence_sheets() -> None:
    service = FakeSheetsService(get_result={"sheets": "not-a-list"})

    assert GoogleSheetsApi(service).find_sheet("spreadsheet-1", "missing") is None


def test_find_sheet_rejects_invalid_sheet_id() -> None:
    service = FakeSheetsService(
        get_result={"sheets": [{"properties": {"sheetId": -1, "title": "tab"}}]}
    )

    with pytest.raises(SheetsError, match="sheetId"):
        GoogleSheetsApi(service).find_sheet("spreadsheet-1", "tab")


def test_find_sheet_accepts_default_sheet_id_zero() -> None:
    service = FakeSheetsService(
        get_result={"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}]}
    )

    assert GoogleSheetsApi(service).find_sheet("spreadsheet-1", "Sheet1") == SheetRef(
        sheet_id=0,
        title="Sheet1",
    )


@pytest.mark.parametrize("sheet_id", [True, -1, "1"], ids=["bool", "negative", "text"])
def test_get_sheet_rejects_invalid_sheet_id(sheet_id: object) -> None:
    api = GoogleSheetsApi(FakeSheetsService())

    with pytest.raises(SheetsError, match="sheet_id"):
        api.get_sheet("spreadsheet-1", sheet_id)  # type: ignore[arg-type]


def test_get_sheet_accepts_default_sheet_id_zero() -> None:
    service = FakeSheetsService(
        get_result={"sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}}]}
    )

    assert GoogleSheetsApi(service).get_sheet("spreadsheet-1", 0) == SheetRef(
        sheet_id=0,
        title="Sheet1",
    )


def test_get_sheet_matches_by_id_and_keeps_title() -> None:
    service = FakeSheetsService(
        get_result={"sheets": [{"properties": {"sheetId": 7, "title": "renamed"}}]}
    )

    result = GoogleSheetsApi(service).get_sheet("spreadsheet-1", 7)

    assert result == SheetRef(sheet_id=7, title="renamed")


def test_get_sheet_uses_fallback_title_when_properties_omit_it() -> None:
    service = FakeSheetsService(get_result={"sheets": [{"properties": {"sheetId": 7}}]})

    result = GoogleSheetsApi(service).get_sheet("spreadsheet-1", 7)

    assert result == SheetRef(sheet_id=7, title="sheet-7")


def test_get_sheet_returns_none_when_id_is_missing() -> None:
    service = FakeSheetsService(
        get_result={"sheets": [{"properties": {"sheetId": 7, "title": "other"}}]}
    )

    assert GoogleSheetsApi(service).get_sheet("spreadsheet-1", 8) is None


def test_add_sheet_returns_reply_id_and_sends_add_sheet_request() -> None:
    service = FakeSheetsService(
        batch_update_result={
            "replies": [{"addSheet": {"properties": {"sheetId": 5, "title": "tab-new"}}}]
        }
    )

    result = GoogleSheetsApi(service).add_sheet("spreadsheet-1", "tab-new")

    assert result == SheetRef(sheet_id=5, title="tab-new")
    operation, kwargs = service.calls[0]
    assert operation == "batchUpdate"
    assert kwargs["spreadsheetId"] == "spreadsheet-1"
    assert kwargs["body"] == {"requests": [{"addSheet": {"properties": {"title": "tab-new"}}}]}


def test_add_sheet_falls_back_to_requested_title() -> None:
    service = FakeSheetsService(
        batch_update_result={"replies": [{"addSheet": {"properties": {"sheetId": 5}}}]}
    )

    result = GoogleSheetsApi(service).add_sheet("spreadsheet-1", "tab-new")

    assert result == SheetRef(sheet_id=5, title="tab-new")


def test_add_sheet_rejects_blank_title() -> None:
    service = FakeSheetsService()

    with pytest.raises(SheetsError, match="Judul tab baru"):
        GoogleSheetsApi(service).add_sheet("spreadsheet-1", " ")

    assert service.calls == []


@pytest.mark.parametrize(
    "payload",
    [{}, {"replies": []}, {"replies": [{"addSheet": {"properties": {}}}]}],
    ids=["missing-replies", "empty-replies", "empty-properties"],
)
def test_add_sheet_requires_sheet_id_reply(payload: dict[str, object]) -> None:
    service = FakeSheetsService(batch_update_result=payload)

    with pytest.raises(SheetsError, match="tidak mengembalikan sheetId"):
        GoogleSheetsApi(service).add_sheet("spreadsheet-1", "tab-new")


def test_add_sheet_wraps_batch_update_failure() -> None:
    service = FakeSheetsService(batch_update_result=RuntimeError("batch gagal"))

    with pytest.raises(SheetsError, match="Batch update spreadsheet"):
        GoogleSheetsApi(service).add_sheet("spreadsheet-1", "tab-new")


def test_batch_update_rejects_non_object_payload() -> None:
    service = FakeSheetsService(batch_update_result="not-an-object")

    with pytest.raises(SheetsError, match="bukan objek JSON"):
        GoogleSheetsApi(service).add_sheet("spreadsheet-1", "tab-new")


def test_write_values_sends_raw_matrix() -> None:
    service = FakeSheetsService()

    GoogleSheetsApi(service).write_values(
        "spreadsheet-1",
        "'chart-tab'!A1:B2",
        [("Category", "Value"), ("Q1", 12)],
    )

    assert service.calls == [
        (
            "values.update",
            {
                "spreadsheetId": "spreadsheet-1",
                "range": "'chart-tab'!A1:B2",
                "valueInputOption": "RAW",
                "body": {"values": [["Category", "Value"], ["Q1", 12]]},
            },
        )
    ]


def test_write_values_rejects_blank_range() -> None:
    service = FakeSheetsService()

    with pytest.raises(SheetsError, match="Range penulisan"):
        GoogleSheetsApi(service).write_values("spreadsheet-1", " ", [])

    assert service.calls == []


def test_write_values_rejects_empty_matrix() -> None:
    service = FakeSheetsService()

    with pytest.raises(SheetsError, match="tidak boleh kosong"):
        GoogleSheetsApi(service).write_values("spreadsheet-1", "'tab'!A1", [])

    assert service.calls == []


def test_write_values_wraps_service_error() -> None:
    service = FakeSheetsService(update_result=RuntimeError("range invalid"))

    with pytest.raises(SheetsError, match=r"Penulisan nilai ke .* gagal"):
        GoogleSheetsApi(service).write_values("spreadsheet-1", "'tab'!A1", [["value"]])


def test_get_chart_returns_first_chart_on_matching_sheet() -> None:
    service = FakeSheetsService(
        get_result={
            "sheets": [
                {"properties": {"sheetId": 3}, "charts": []},
                {
                    "properties": {"sheetId": 7},
                    "charts": [{"chartId": 11, "spec": {"basicChart": {"chartType": "LINE"}}}],
                },
            ]
        }
    )

    record = GoogleSheetsApi(service).get_chart("spreadsheet-1", 7)

    assert record == ChartRecord(
        chart_id=11,
        spec={"basicChart": {"chartType": "LINE"}},
    )


def test_get_chart_rejects_multiple_chart_objects_on_one_tab() -> None:
    service = FakeSheetsService(
        get_result={
            "sheets": [
                {
                    "properties": {"sheetId": 7},
                    "charts": [{"chartId": 11, "spec": {}}, {"chartId": 12, "spec": {}}],
                }
            ]
        }
    )

    with pytest.raises(SheetsError, match="2 chart object"):
        GoogleSheetsApi(service).get_chart("spreadsheet-1", 7)


def test_get_chart_returns_none_when_matching_sheet_has_no_chart() -> None:
    service = FakeSheetsService(
        get_result={"sheets": [{"properties": {"sheetId": 7}, "charts": []}]}
    )

    assert GoogleSheetsApi(service).get_chart("spreadsheet-1", 7) is None


def test_get_chart_returns_none_when_sheet_is_missing() -> None:
    service = FakeSheetsService(get_result={"sheets": [{"properties": {"sheetId": 3}}]})

    assert GoogleSheetsApi(service).get_chart("spreadsheet-1", 7) is None


def test_get_chart_rejects_invalid_chart_id() -> None:
    service = FakeSheetsService(
        get_result={
            "sheets": [
                {"properties": {"sheetId": 7}, "charts": [{"chartId": 0, "spec": {}}]},
            ]
        }
    )

    with pytest.raises(SheetsError, match="chartId"):
        GoogleSheetsApi(service).get_chart("spreadsheet-1", 7)


def test_create_chart_sends_anchored_add_chart_request() -> None:
    spec = {"basicChart": {"chartType": "COLUMN"}}
    service = FakeSheetsService(
        batch_update_result={"replies": [{"addChart": {"chart": {"chartId": 11, "spec": spec}}}]}
    )

    record = GoogleSheetsApi(service).create_chart("spreadsheet-1", 7, spec)

    assert record == ChartRecord(chart_id=11, spec=spec)
    operation, kwargs = service.calls[0]
    assert operation == "batchUpdate"
    body = kwargs["body"]
    assert isinstance(body, Mapping)
    requests = body["requests"]
    assert isinstance(requests, list)
    chart = requests[0]["addChart"]["chart"]
    assert chart["spec"] == spec
    assert chart["position"] == {
        "overlayPosition": {
            "anchorCell": {"sheetId": 7, "rowIndex": 7, "columnIndex": 0},
            "widthPixels": 640,
            "heightPixels": 360,
        }
    }


@pytest.mark.parametrize(
    "payload",
    [{}, {"replies": []}, {"replies": [{"addChart": {"chart": {}}}]}],
    ids=["missing-replies", "empty-replies", "empty-chart"],
)
def test_create_chart_requires_chart_id_reply(payload: dict[str, object]) -> None:
    service = FakeSheetsService(batch_update_result=payload)

    with pytest.raises(SheetsError, match="tidak mengembalikan chartId"):
        GoogleSheetsApi(service).create_chart("spreadsheet-1", 7, {"basicChart": {}})


def test_create_chart_rejects_invalid_chart_id() -> None:
    service = FakeSheetsService(
        batch_update_result={"replies": [{"addChart": {"chart": {"chartId": 0, "spec": {}}}}]}
    )

    with pytest.raises(SheetsError, match="chartId"):
        GoogleSheetsApi(service).create_chart("spreadsheet-1", 7, {"basicChart": {}})


def test_update_chart_keeps_chart_id_and_sends_update_spec() -> None:
    spec = {"basicChart": {"chartType": "LINE"}}
    service = FakeSheetsService()

    record = GoogleSheetsApi(service).update_chart("spreadsheet-1", 11, spec)

    assert record == ChartRecord(chart_id=11, spec=spec)
    assert service.calls == [
        (
            "batchUpdate",
            {
                "spreadsheetId": "spreadsheet-1",
                "body": {
                    "requests": [{"updateChartSpec": {"chartId": 11, "spec": spec}}],
                },
            },
        )
    ]
