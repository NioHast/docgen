"""Pemetaan chart AutoOffice ke spreadsheet, tab, data, dan chart object."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from autooffice.deck.charts import ChartSpec, build_chart_spec
from autooffice.deck.model import DeckIR
from autooffice.design.theme import Theme

from . import SheetsError
from .sheets import CellValue, SheetRef, SheetsApi, SpreadsheetRef

MAX_TAB_LENGTH = 100


@dataclass(frozen=True, slots=True)
class ChartLink:
    """Hubungan satu chart logis ke tab, sheet, dan chart object Sheets."""

    spreadsheet_id: str
    chart_id: str
    tab_name: str
    sheet_id: int
    embedded_chart_id: int
    data_sha256: str

    def __post_init__(self) -> None:
        for name in ("spreadsheet_id", "chart_id", "tab_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SheetsError(f"ChartLink field '{name}' wajib teks non-kosong.")
        if self.sheet_id < 0 or self.embedded_chart_id <= 0:
            raise SheetsError("ChartLink sheet ID wajib non-negatif dan chart ID wajib positif.")
        if len(self.data_sha256) != 64:
            raise SheetsError("ChartLink data_sha256 wajib SHA-256.")


def build_chart_specs(deck: DeckIR) -> tuple[ChartSpec, ...]:
    """Kumpulkan seluruh chart spec deck dalam urutan slide dan block."""
    specs: list[ChartSpec] = []
    seen: set[str] = set()
    for slide in deck.slides:
        for block in slide.blocks:
            if block.block_type != "chart":
                continue
            spec = build_chart_spec(block, slide_id=slide.slide_id)
            if spec.chart_id in seen:
                raise SheetsError(f"chart_id '{spec.chart_id}' duplikat pada deck.")
            seen.add(spec.chart_id)
            specs.append(spec)
    return tuple(specs)


def spreadsheet_title(deck_title: str) -> str:
    """Nama spreadsheet sesuai kontrak ``AutoOffice Charts - <meta.title>``."""
    title = deck_title.strip()
    if not title:
        raise SheetsError("Judul deck kosong; nama spreadsheet tidak dapat dibentuk.")
    return f"AutoOffice Charts - {title}"


def tab_name_for(chart_id: str) -> str:
    """Nama tab stabil; potong dan tambah hash 8 karakter bila terlalu panjang."""
    value = chart_id.strip()
    if not value:
        raise SheetsError("chart_id tidak boleh kosong untuk nama tab.")
    if any(character in value for character in ("'", "[", "]", ":", "*", "?", "/", "\\")):
        raise SheetsError(f"chart_id '{chart_id}' memuat karakter terlarang untuk nama tab.")
    if len(value) <= MAX_TAB_LENGTH:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{value[: MAX_TAB_LENGTH - 9]}-{digest}"


def sheet_values(spec: ChartSpec) -> tuple[tuple[CellValue, ...], ...]:
    """Header baris 1 dan data baris berikutnya tanpa formula."""
    if spec.kind == "donut":
        series = spec.series[0]
        rows: list[tuple[CellValue, ...]] = [("Label", "Nilai")]
        rows.extend(
            (category, series.values[index]) for index, category in enumerate(spec.categories)
        )
        return tuple(rows)
    header: list[CellValue] = ["Category", *(series.name for series in spec.series)]
    rows = [tuple(header)]
    for index, category in enumerate(spec.categories):
        rows.append(tuple([category, *(series.values[index] for series in spec.series)]))
    return tuple(rows)


def data_sha256(values: Sequence[Sequence[CellValue]]) -> str:
    """Hash deterministik data tab untuk state ``last_data_sha256``."""
    canonical = json.dumps(
        [list(row) for row in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def a1_range(tab_name: str, rows: int, columns: int) -> str:
    """Range A1 dengan nama tab di-escape untuk apostrof."""
    if rows <= 0 or columns <= 0:
        raise SheetsError("Range A1 memerlukan baris dan kolom positif.")
    escaped = tab_name.replace("'", "''")
    last_column = _column_letter(columns)
    return f"'{escaped}'!A1:{last_column}{rows}"


def ensure_workbook(
    sheets: SheetsApi,
    *,
    title: str,
    existing_id: str | None = None,
) -> tuple[SpreadsheetRef, bool]:
    """Reuse spreadsheet state yang valid atau buat satu spreadsheet baru.

    Return ``(ref, created)``. Spreadsheet kedua tidak dibuat bila state masih
    bisa diakses.
    """
    if existing_id:
        current = sheets.get_spreadsheet(existing_id)
        if current is not None:
            return current, False
    return sheets.create_spreadsheet(spreadsheet_title(title)), True


def ensure_sheet_chart(
    sheets: SheetsApi,
    *,
    spreadsheet_id: str,
    spec: ChartSpec,
    theme: Theme,
    existing_sheet_id: int | None = None,
) -> ChartLink:
    """Pastikan tab, data, dan chart object ada; pertahankan chart ID saat update."""
    tab_name = tab_name_for(spec.chart_id)
    sheet: SheetRef | None = None
    if existing_sheet_id is not None:
        sheet = sheets.get_sheet(spreadsheet_id, existing_sheet_id)
    if sheet is None:
        sheet = sheets.find_sheet(spreadsheet_id, tab_name)
    if sheet is None:
        sheet = _add_sheet(sheets, spreadsheet_id, tab_name)
    values = sheet_values(spec)
    _write_values(sheets, spreadsheet_id, sheet.title, values)
    chart_spec = sheets_chart_spec(
        spec,
        theme,
        sheet_id=sheet.sheet_id,
        rows=len(values),
        columns=len(values[0]),
    )
    existing = sheets.get_chart(spreadsheet_id, sheet.sheet_id)
    if existing is None:
        chart = sheets.create_chart(spreadsheet_id, sheet.sheet_id, chart_spec)
    else:
        chart = sheets.update_chart(spreadsheet_id, existing.chart_id, chart_spec)
    return ChartLink(
        spreadsheet_id=spreadsheet_id,
        chart_id=spec.chart_id,
        tab_name=sheet.title,
        sheet_id=sheet.sheet_id,
        embedded_chart_id=chart.chart_id,
        data_sha256=data_sha256(values),
    )


def sheets_chart_spec(
    spec: ChartSpec,
    theme: Theme,
    *,
    sheet_id: int,
    rows: int,
    columns: int,
) -> dict[str, object]:
    """Bentuk ``ChartSpec`` Google Sheets dari ``ChartSpec`` AutoOffice."""
    if rows <= 1 or columns <= 0:
        raise SheetsError("Chart Sheets memerlukan minimal satu data row dan satu kolom.")
    palette = theme.chart.series
    domain_range = {
        "sourceRange": {
            "sources": [
                {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": rows,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                }
            ]
        }
    }
    base: dict[str, object] = {
        "title": spec.title,
        "fontName": theme.typography.family,
        "backgroundColor": _rgb(theme.colors.surface),
        "backgroundColorStyle": {"rgbColor": _rgb(theme.colors.surface)},
        "titleTextFormat": {
            "fontFamily": theme.typography.family,
            "foregroundColor": _rgb(theme.chart.title),
        },
    }
    if spec.kind == "donut":
        value_range = {
            "sourceRange": {
                "sources": [
                    {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": rows,
                        "startColumnIndex": 1,
                        "endColumnIndex": 2,
                    }
                ]
            }
        }
        base["pieChart"] = {
            "legendPosition": "RIGHT_LEGEND",
            "domain": domain_range,
            "series": value_range,
            "pieHole": 0.5,
        }
        return base
    chart_type = {
        ("bar", "vertical"): "COLUMN",
        ("bar", "horizontal"): "BAR",
        ("line", "vertical"): "LINE",
        ("line", "horizontal"): "LINE",
    }[(spec.kind, spec.orientation or "vertical")]
    series: list[dict[str, object]] = []
    for index in range(len(spec.series)):
        series_payload: dict[str, object] = {
            "series": {
                "sourceRange": {
                    "sources": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": rows,
                            "startColumnIndex": index + 1,
                            "endColumnIndex": index + 2,
                        }
                    ]
                }
            },
            "targetAxis": "LEFT_AXIS",
            "color": _rgb(palette[index % len(palette)]),
        }
        if spec.kind == "line":
            series_payload["pointStyle"] = {"size": 4, "shape": "CIRCLE"}
        series.append(series_payload)
    basic_chart: dict[str, object] = {
        "chartType": chart_type,
        "legendPosition": "BOTTOM_LEGEND" if len(spec.series) > 1 else "NO_LEGEND",
        "headerCount": 1,
        "domains": [{"domain": domain_range}],
        "series": series,
    }
    if spec.unit:
        value_axis = "BOTTOM_AXIS" if chart_type == "BAR" else "LEFT_AXIS"
        basic_chart["axis"] = [{"position": value_axis, "title": spec.unit}]
    base["basicChart"] = basic_chart
    return base


def _add_sheet(sheets: SheetsApi, spreadsheet_id: str, tab_name: str) -> SheetRef:
    try:
        return sheets.add_sheet(spreadsheet_id, tab_name)
    except SheetsError:
        raise
    except Exception as error:
        raise SheetsError(
            f"Pembuatan tab '{tab_name}' pada spreadsheet '{spreadsheet_id}' gagal: {error}"
        ) from error


def _write_values(
    sheets: SheetsApi,
    spreadsheet_id: str,
    tab_name: str,
    values: Sequence[Sequence[CellValue]],
) -> None:
    try:
        sheets.write_values(
            spreadsheet_id,
            a1_range(tab_name, rows=len(values), columns=len(values[0])),
            values,
        )
    except SheetsError:
        raise
    except Exception as error:
        raise SheetsError(
            f"Penulisan data tab '{tab_name}' pada spreadsheet '{spreadsheet_id}' gagal: {error}"
        ) from error


def _rgb(hex_color: str) -> dict[str, float]:
    value = hex_color.strip()
    if len(value) != 7 or not value.startswith("#"):
        raise SheetsError(f"Warna chart harus heksadesimal enam digit, bukan {hex_color!r}.")
    try:
        red = int(value[1:3], 16) / 255
        green = int(value[3:5], 16) / 255
        blue = int(value[5:7], 16) / 255
    except ValueError as error:
        raise SheetsError(f"Warna chart tidak valid: {hex_color!r}.") from error
    return {"red": red, "green": green, "blue": blue}


def _column_letter(index: int) -> str:
    if index <= 0:
        raise SheetsError("Indeks kolom harus positif.")
    letters = ""
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


__all__ = [
    "MAX_TAB_LENGTH",
    "ChartLink",
    "a1_range",
    "build_chart_specs",
    "data_sha256",
    "ensure_sheet_chart",
    "ensure_workbook",
    "sheet_values",
    "sheets_chart_spec",
    "spreadsheet_title",
    "tab_name_for",
]
