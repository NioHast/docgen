"""Kontrak murni payload ChartSpec Google Sheets: bentuk dan enum valid."""

from collections.abc import Mapping

import pytest

from autooffice.deck.charts import ChartSpec
from autooffice.deck.model import ChartSeries
from autooffice.design.theme import Theme
from autooffice.google import SheetsError
from autooffice.google.charts import sheets_chart_spec
from autooffice.google.fake import FakeSheets
from autooffice.google.sheets import validate_chart_spec

_LEGEND_POSITIONS = {
    "LEGEND_POSITION_UNSPECIFIED",
    "BOTTOM_LEGEND",
    "RIGHT_LEGEND",
    "LEFT_LEGEND",
    "TOP_LEGEND",
    "NO_LEGEND",
}
_PIE_LEGEND_POSITIONS = _LEGEND_POSITIONS | {"PIE_CHART_LEGEND_POSITION_UNSPECIFIED"}
_TARGET_AXES = {"LEFT_AXIS", "RIGHT_AXIS"}


def _line() -> ChartSpec:
    return ChartSpec(
        chart_id="s02.chart1",
        kind="line",
        categories=("Q1", "Q2"),
        series=(
            ChartSeries(name="2025", values=(12, 18)),
            ChartSeries(name="2026", values=(20, 29)),
        ),
        orientation=None,
        title="Pengguna aktif",
        alt="Grafik garis pengguna aktif",
        unit="persen",
    )


def _bar(
    *,
    orientation: str = "vertical",
    series_count: int = 2,
    unit: str | None = None,
) -> ChartSpec:
    series = tuple(
        ChartSeries(name=f"Seri {index}", values=(10 + index, 20 + index))
        for index in range(series_count)
    )
    return ChartSpec(
        chart_id="s03.chart1",
        kind="bar",
        categories=("A", "B"),
        series=series,
        orientation=orientation,  # type: ignore[arg-type]
        title="Batang",
        alt="Diagram batang",
        unit=unit,
    )


def _donut() -> ChartSpec:
    return ChartSpec(
        chart_id="s04.chart1",
        kind="donut",
        categories=("Langsung", "Referral"),
        series=(ChartSeries(name="Pengguna", values=(42, 28)),),
        orientation=None,
        title="Sumber akuisisi",
        alt="Diagram donat sumber akuisisi",
    )


def _assert_chart_data(raw: object, *, sheet_id: int) -> None:
    assert isinstance(raw, Mapping)
    source_range = raw["sourceRange"]
    assert isinstance(source_range, Mapping)
    sources = source_range["sources"]
    assert isinstance(sources, list)
    assert sources
    assert sources[0]["sheetId"] == sheet_id


def test_line_chart_payload_uses_valid_axes_and_legend(google_theme: Theme) -> None:
    payload = sheets_chart_spec(
        _line(),
        google_theme,
        sheet_id=7,
        rows=3,
        columns=3,
    )

    basic = payload["basicChart"]
    assert isinstance(basic, Mapping)
    assert basic["chartType"] == "LINE"
    assert basic["legendPosition"] == "BOTTOM_LEGEND"
    assert basic["legendPosition"] in _LEGEND_POSITIONS
    assert "valueAxis" not in basic
    assert basic["axis"] == [{"position": "LEFT_AXIS", "title": "persen"}]
    series = basic["series"]
    assert isinstance(series, list)
    assert len(series) == 2
    for item in series:
        assert isinstance(item, Mapping)
        assert item["targetAxis"] in _TARGET_AXES
        _assert_chart_data(item["series"], sheet_id=7)
    assert len(basic["domains"]) == 1
    _assert_chart_data(basic["domains"][0]["domain"], sheet_id=7)
    assert "backgroundColorStyle" in payload


@pytest.mark.parametrize(
    ("orientation", "chart_type"),
    [("vertical", "COLUMN"), ("horizontal", "BAR")],
)
def test_bar_chart_payload_uses_valid_axis_and_legend(
    google_theme: Theme,
    orientation: str,
    chart_type: str,
) -> None:
    payload = sheets_chart_spec(
        _bar(orientation=orientation),
        google_theme,
        sheet_id=7,
        rows=3,
        columns=3,
    )

    basic = payload["basicChart"]
    assert isinstance(basic, Mapping)
    assert basic["chartType"] == chart_type
    assert basic["legendPosition"] == "BOTTOM_LEGEND"
    assert {item["targetAxis"] for item in basic["series"]} == {"LEFT_AXIS"}


def test_horizontal_bar_unit_uses_bottom_value_axis(google_theme: Theme) -> None:
    payload = sheets_chart_spec(
        _bar(orientation="horizontal", unit="orang"),
        google_theme,
        sheet_id=7,
        rows=3,
        columns=3,
    )

    basic = payload["basicChart"]
    assert isinstance(basic, Mapping)
    assert basic["chartType"] == "BAR"
    assert basic["axis"] == [{"position": "BOTTOM_AXIS", "title": "orang"}]


def test_vertical_bar_unit_uses_left_value_axis(google_theme: Theme) -> None:
    payload = sheets_chart_spec(
        _bar(orientation="vertical", unit="orang"),
        google_theme,
        sheet_id=7,
        rows=3,
        columns=3,
    )

    basic = payload["basicChart"]
    assert isinstance(basic, Mapping)
    assert basic["axis"] == [{"position": "LEFT_AXIS", "title": "orang"}]


def test_fake_accepts_documented_basic_chart_enum_values(google_theme: Theme) -> None:
    payload = sheets_chart_spec(
        _bar(unit="orang"),
        google_theme,
        sheet_id=7,
        rows=3,
        columns=3,
    )
    basic = payload["basicChart"]
    assert isinstance(basic, dict)
    basic["chartType"] = "STEPPED_AREA"
    basic["legendPosition"] = "BASIC_CHART_LEGEND_POSITION_UNSPECIFIED"
    basic["axis"] = [{"position": "BASIC_CHART_AXIS_POSITION_UNSPECIFIED", "title": "orang"}]

    validate_chart_spec(payload)


def test_single_series_bar_uses_no_legend(google_theme: Theme) -> None:
    payload = sheets_chart_spec(
        _bar(series_count=1),
        google_theme,
        sheet_id=7,
        rows=3,
        columns=2,
    )

    basic = payload["basicChart"]
    assert isinstance(basic, Mapping)
    assert basic["legendPosition"] == "NO_LEGEND"


def test_donut_payload_uses_chart_data_series_without_slice_info(google_theme: Theme) -> None:
    payload = sheets_chart_spec(
        _donut(),
        google_theme,
        sheet_id=7,
        rows=3,
        columns=2,
    )

    pie = payload["pieChart"]
    assert isinstance(pie, Mapping)
    assert pie["legendPosition"] == "RIGHT_LEGEND"
    assert pie["legendPosition"] in _PIE_LEGEND_POSITIONS
    assert isinstance(pie["series"], Mapping)
    assert not isinstance(pie["series"], list)
    assert "sliceInfo" not in pie
    _assert_chart_data(pie["domain"], sheet_id=7)
    _assert_chart_data(pie["series"], sheet_id=7)


def test_fake_rejects_invalid_series_target_axis(google_theme: Theme) -> None:
    payload = sheets_chart_spec(
        _line(),
        google_theme,
        sheet_id=7,
        rows=3,
        columns=3,
    )
    basic = payload["basicChart"]
    assert isinstance(basic, dict)
    series = basic["series"]
    assert isinstance(series, list)
    series[0]["targetAxis"] = "LEFT"
    sheets = FakeSheets()
    spreadsheet = sheets.create_spreadsheet("Deck")
    sheet = sheets.find_sheet(spreadsheet.spreadsheet_id, "Sheet1")
    assert sheet is not None

    with pytest.raises(SheetsError, match="targetAxis"):
        sheets.create_chart(spreadsheet.spreadsheet_id, sheet.sheet_id, payload)


def test_fake_rejects_pie_series_list(google_theme: Theme) -> None:
    payload = sheets_chart_spec(
        _donut(),
        google_theme,
        sheet_id=7,
        rows=3,
        columns=2,
    )
    pie = payload["pieChart"]
    assert isinstance(pie, dict)
    pie["series"] = [{"data": {"sourceRange": {}}, "sliceInfo": []}]
    sheets = FakeSheets()
    spreadsheet = sheets.create_spreadsheet("Deck")
    sheet = sheets.find_sheet(spreadsheet.spreadsheet_id, "Sheet1")
    assert sheet is not None

    with pytest.raises(SheetsError, match="ChartData"):
        sheets.create_chart(spreadsheet.spreadsheet_id, sheet.sheet_id, payload)
