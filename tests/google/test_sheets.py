"""Test workbook, tab per chart, layout data, dan chart object Sheets."""

from collections.abc import Mapping

from autooffice.deck.charts import ChartSpec
from autooffice.deck.model import ChartSeries, DeckIR
from autooffice.design.theme import Theme
from autooffice.google.charts import (
    build_chart_specs,
    ensure_sheet_chart,
    ensure_workbook,
    sheet_values,
    tab_name_for,
)
from autooffice.google.fake import FakeGoogleServices, FakeSheets
from autooffice.google.sheets import SheetsApi


def test_workbook_is_reused_for_the_same_state() -> None:
    sheets = FakeSheets()

    first, created = ensure_workbook(sheets, title="F2 Google")
    second, reused = ensure_workbook(
        sheets,
        title="F2 Google",
        existing_id=first.spreadsheet_id,
    )

    assert created is True
    assert reused is False
    assert second.spreadsheet_id == first.spreadsheet_id
    assert [operation for operation, _ in sheets.operations].count("create_spreadsheet") == 1


def test_workbook_is_recreated_when_existing_spreadsheet_is_absent() -> None:
    sheets = FakeSheets()

    first, _ = ensure_workbook(sheets, title="F2 Google")
    second, created = ensure_workbook(
        sheets,
        title="F2 Google",
        existing_id="spreadsheet-missing",
    )

    assert created is True
    assert second.spreadsheet_id != first.spreadsheet_id
    assert [operation for operation, _ in sheets.operations].count("create_spreadsheet") == 2


def test_one_tab_per_chart_with_header_and_data_rows(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
) -> None:
    workbook, _ = ensure_workbook(fake_google.sheets, title="F2 Google")
    spec = build_chart_specs(google_deck)[0]

    link = ensure_sheet_chart(
        fake_google.sheets,
        spreadsheet_id=workbook.spreadsheet_id,
        spec=spec,
        theme=google_theme,
    )

    assert link.chart_id == "s02.chart1"
    assert link.tab_name == "s02.chart1"
    assert link.sheet_id > 0
    assert link.embedded_chart_id > 0
    values = fake_google.sheets.sheet_values(workbook.spreadsheet_id, link.tab_name)
    assert values == [
        ["Category", "2025", "2026"],
        ["Q1", 12, 20],
        ["Q2", 18, 29],
        ["Q3", 27, 41],
        ["Q4", 35, 52],
    ]
    chart = fake_google.sheets.get_chart(workbook.spreadsheet_id, link.sheet_id)
    assert chart is not None
    assert chart.chart_id == link.embedded_chart_id
    spec_payload = chart.spec["basicChart"]
    assert isinstance(spec_payload, Mapping)
    assert spec_payload["chartType"] == "LINE"


def test_existing_chart_is_updated_without_new_chart_id(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
) -> None:
    workbook, _ = ensure_workbook(fake_google.sheets, title="F2 Google")
    spec = build_chart_specs(google_deck)[0]

    first = ensure_sheet_chart(
        fake_google.sheets,
        spreadsheet_id=workbook.spreadsheet_id,
        spec=spec,
        theme=google_theme,
    )
    second = ensure_sheet_chart(
        fake_google.sheets,
        spreadsheet_id=workbook.spreadsheet_id,
        spec=spec,
        theme=google_theme,
    )

    assert second.embedded_chart_id == first.embedded_chart_id
    operations = [operation for operation, _ in fake_google.sheets.operations]
    assert operations.count("create_chart") == 1
    assert operations.count("update_chart") == 1


def test_renamed_tab_keeps_chart_identity(
    fake_google: FakeGoogleServices,
    google_deck: DeckIR,
    google_theme: Theme,
) -> None:
    workbook, _ = ensure_workbook(fake_google.sheets, title="F2 Google")
    spec = build_chart_specs(google_deck)[0]
    first = ensure_sheet_chart(
        fake_google.sheets,
        spreadsheet_id=workbook.spreadsheet_id,
        spec=spec,
        theme=google_theme,
    )
    fake_google.sheets.rename_sheet(workbook.spreadsheet_id, first.sheet_id, "Tab diubah")

    second = ensure_sheet_chart(
        fake_google.sheets,
        spreadsheet_id=workbook.spreadsheet_id,
        spec=spec,
        theme=google_theme,
        existing_sheet_id=first.sheet_id,
    )

    assert second.sheet_id == first.sheet_id
    assert second.embedded_chart_id == first.embedded_chart_id
    assert second.tab_name == "Tab diubah"
    operations = [operation for operation, _ in fake_google.sheets.operations]
    assert operations.count("add_sheet") == 1


def test_donut_layout_uses_label_and_value_header() -> None:
    spec = ChartSpec(
        chart_id="s03.chart1",
        kind="donut",
        categories=("Langsung", "Referral"),
        series=(ChartSeries(name="Pengguna", values=(42, 28)),),
        orientation=None,
        title="Sumber akuisisi",
        alt="Diagram donat sumber akuisisi",
    )

    assert sheet_values(spec) == (
        ("Label", "Nilai"),
        ("Langsung", 42),
        ("Referral", 28),
    )


def test_long_tab_name_is_truncated_with_hash() -> None:
    chart_id = "s01." + "a" * 120

    name = tab_name_for(chart_id)

    assert len(name) == 100
    assert name.startswith("s01.aaaa")
    assert name[-9] == "-"


def test_fake_sheets_satisfies_protocol(fake_google: FakeGoogleServices) -> None:
    assert isinstance(fake_google.sheets, SheetsApi)


def test_chart_specs_are_deterministic(google_deck: DeckIR) -> None:
    first = build_chart_specs(google_deck)
    second = build_chart_specs(google_deck)

    assert [spec.chart_id for spec in first] == ["s02.chart1"]
    assert first == second
