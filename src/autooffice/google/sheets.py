"""Adapter Google Sheets: spreadsheet, tab, nilai, dan chart object.

Modul ini hanya mengurus operasi Sheets level rendah. Pemetaan chart AutoOffice
ke tab dan chart spec ada di :mod:`autooffice.google.charts`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, cast, runtime_checkable

from . import SheetsError

_LEGEND_POSITIONS = frozenset(
    {
        "BASIC_CHART_LEGEND_POSITION_UNSPECIFIED",
        "BOTTOM_LEGEND",
        "RIGHT_LEGEND",
        "LEFT_LEGEND",
        "TOP_LEGEND",
        "NO_LEGEND",
    }
)
_PIE_LEGEND_POSITIONS = frozenset(
    {
        "PIE_CHART_LEGEND_POSITION_UNSPECIFIED",
        "BOTTOM_LEGEND",
        "RIGHT_LEGEND",
        "LEFT_LEGEND",
        "TOP_LEGEND",
        "NO_LEGEND",
    }
)
_AXIS_POSITIONS = frozenset(
    {
        "BASIC_CHART_AXIS_POSITION_UNSPECIFIED",
        "BOTTOM_AXIS",
        "LEFT_AXIS",
        "RIGHT_AXIS",
        "TOP_AXIS",
    }
)
_SERIES_TARGET_AXES = frozenset({"LEFT_AXIS", "RIGHT_AXIS"})
_BASIC_CHART_TYPES = frozenset(
    {
        "BASIC_CHART_TYPE_UNSPECIFIED",
        "BAR",
        "LINE",
        "AREA",
        "COLUMN",
        "SCATTER",
        "COMBO",
        "STEPPED_AREA",
    }
)


@dataclass(frozen=True, slots=True)
class SpreadsheetRef:
    """Identitas spreadsheet remote."""

    spreadsheet_id: str
    url: str
    title: str

    def __post_init__(self) -> None:
        if not self.spreadsheet_id.strip():
            raise SheetsError("Spreadsheet ID tidak boleh kosong.")
        if not self.url.startswith("https://docs.google.com/spreadsheets/d/"):
            raise SheetsError(f"URL spreadsheet tidak valid: {self.url!r}.")


@dataclass(frozen=True, slots=True)
class SheetRef:
    """Identitas satu tab spreadsheet."""

    sheet_id: int
    title: str

    def __post_init__(self) -> None:
        if isinstance(self.sheet_id, bool) or not isinstance(self.sheet_id, int):
            raise SheetsError("Sheet ID harus integer.")
        if self.sheet_id < 0:
            raise SheetsError("Sheet ID tidak boleh negatif.")
        if not self.title.strip():
            raise SheetsError("Judul tab tidak boleh kosong.")


@dataclass(frozen=True, slots=True)
class ChartRecord:
    """Chart object Sheets beserta spec-nya."""

    chart_id: int
    spec: Mapping[str, object]

    def __post_init__(self) -> None:
        if isinstance(self.chart_id, bool) or not isinstance(self.chart_id, int):
            raise SheetsError("Chart ID harus integer.")
        if self.chart_id <= 0:
            raise SheetsError("Chart ID harus positif.")
        object.__setattr__(self, "spec", MappingProxyType(dict(self.spec)))


CellValue = str | int | float


@runtime_checkable
class SheetsApi(Protocol):
    """Kontrak Sheets yang dipakai lane chart dan sync."""

    def create_spreadsheet(self, title: str) -> SpreadsheetRef:
        """Buat spreadsheet baru."""

    def get_spreadsheet(self, spreadsheet_id: str) -> SpreadsheetRef | None:
        """Ambil spreadsheet; ``None`` bila tidak ditemukan atau tidak bisa diakses."""

    def find_sheet(self, spreadsheet_id: str, title: str) -> SheetRef | None:
        """Cari tab berdasarkan judul stabil."""

    def get_sheet(self, spreadsheet_id: str, sheet_id: int) -> SheetRef | None:
        """Ambil tab berdasarkan ID stabil, tahan terhadap rename tab."""

    def add_sheet(self, spreadsheet_id: str, title: str) -> SheetRef:
        """Tambah satu tab baru."""

    def write_values(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: Sequence[Sequence[CellValue]],
    ) -> None:
        """Tulis matriks nilai mentah ke satu range A1."""

    def get_chart(self, spreadsheet_id: str, sheet_id: int) -> ChartRecord | None:
        """Ambil chart object pertama pada satu tab."""

    def create_chart(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        spec: Mapping[str, object],
    ) -> ChartRecord:
        """Buat chart object pada tab."""

    def update_chart(
        self,
        spreadsheet_id: str,
        chart_id: int,
        spec: Mapping[str, object],
    ) -> ChartRecord:
        """Perbarui spec chart tanpa mengganti chart ID."""


class GoogleSheetsApi:
    """Adapter tipis Google Sheets v4."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def create_spreadsheet(self, title: str) -> SpreadsheetRef:
        """Buat spreadsheet dengan nama ``AutoOffice Charts - <deck title>``."""
        if not title.strip():
            raise SheetsError("Judul spreadsheet tidak boleh kosong.")
        try:
            payload = (
                self._service.spreadsheets()
                .create(
                    body={"properties": {"title": title}}, fields="spreadsheetId,spreadsheetUrl"
                )
                .execute()
            )
        except Exception as error:
            raise SheetsError(f"Pembuatan spreadsheet gagal: {error}") from error
        return _spreadsheet_from_payload(payload, title=title)

    def get_spreadsheet(self, spreadsheet_id: str) -> SpreadsheetRef | None:
        """Ambil spreadsheet; hanya 404 dipetakan ke ``None`` sesuai kontrak state."""
        try:
            payload = self._get_spreadsheet_payload(spreadsheet_id)
        except Exception as error:
            status = _http_status(error)
            if status == 404:
                return None
            raise SheetsError(
                f"Spreadsheet '{spreadsheet_id}' tidak dapat dibaca: {error}",
                code=status,
            ) from error
        return _spreadsheet_from_payload(payload, title="")

    def find_sheet(self, spreadsheet_id: str, title: str) -> SheetRef | None:
        """Cari tab berdasarkan judul; tidak membuat tab duplikat."""
        payload = self._get_spreadsheet_payload(spreadsheet_id)
        for raw_sheet in _sequence(payload.get("sheets")):
            properties = _mapping(_mapping(raw_sheet).get("properties"))
            if properties.get("title") == title:
                return SheetRef(
                    sheet_id=_non_negative_int(properties.get("sheetId"), field_name="sheetId"),
                    title=title,
                )
        return None

    def get_sheet(self, spreadsheet_id: str, sheet_id: int) -> SheetRef | None:
        """Ambil tab berdasarkan sheetId, sehingga rename tab tidak memutus link."""
        if isinstance(sheet_id, bool) or not isinstance(sheet_id, int) or sheet_id < 0:
            raise SheetsError("sheet_id harus integer non-negatif.")
        payload = self._get_spreadsheet_payload(spreadsheet_id)
        for raw_sheet in _sequence(payload.get("sheets")):
            properties = _mapping(_mapping(raw_sheet).get("properties"))
            if properties.get("sheetId") == sheet_id:
                title = properties.get("title")
                return SheetRef(
                    sheet_id=sheet_id,
                    title=title if isinstance(title, str) and title else f"sheet-{sheet_id}",
                )
        return None

    def add_sheet(self, spreadsheet_id: str, title: str) -> SheetRef:
        """Tambah tab baru dan kembalikan ID-nya dari reply batchUpdate."""
        if not title.strip():
            raise SheetsError("Judul tab baru tidak boleh kosong.")
        payload = self._batch_update(
            spreadsheet_id,
            [{"addSheet": {"properties": {"title": title}}}],
        )
        for reply in _sequence(payload.get("replies")):
            properties = _mapping(_mapping(_mapping(reply).get("addSheet")).get("properties"))
            if properties:
                return SheetRef(
                    sheet_id=_non_negative_int(properties.get("sheetId"), field_name="sheetId"),
                    title=str(properties.get("title", title)),
                )
        raise SheetsError(
            f"Penambahan tab '{title}' pada spreadsheet '{spreadsheet_id}' "
            "tidak mengembalikan sheetId."
        )

    def write_values(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: Sequence[Sequence[CellValue]],
    ) -> None:
        """Tulis nilai mentah tanpa formula."""
        if not range_name.strip():
            raise SheetsError("Range penulisan nilai tidak boleh kosong.")
        matrix = [list(row) for row in values]
        if not matrix:
            raise SheetsError("Nilai spreadsheet tidak boleh kosong.")
        try:
            (
                self._service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption="RAW",
                    body={"values": matrix},
                )
                .execute()
            )
        except Exception as error:
            raise SheetsError(f"Penulisan nilai ke '{range_name}' gagal: {error}") from error

    def get_chart(self, spreadsheet_id: str, sheet_id: int) -> ChartRecord | None:
        """Ambil satu-satunya chart pada tab; lebih dari satu adalah error."""
        payload = self._get_spreadsheet_payload(spreadsheet_id)
        for raw_sheet in _sequence(payload.get("sheets")):
            sheet = _mapping(raw_sheet)
            properties = _mapping(sheet.get("properties"))
            if properties.get("sheetId") != sheet_id:
                continue
            charts = [_mapping(raw_chart) for raw_chart in _sequence(sheet.get("charts"))]
            if not charts:
                return None
            if len(charts) > 1:
                raise SheetsError(
                    f"Tab {sheet_id} memiliki {len(charts)} chart object; "
                    "satu tab hanya boleh memiliki satu chart."
                )
            chart = charts[0]
            chart_id = _positive_int(chart.get("chartId"), field_name="chartId")
            return ChartRecord(chart_id=chart_id, spec=_mapping(chart.get("spec")))
        return None

    def create_chart(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        spec: Mapping[str, object],
    ) -> ChartRecord:
        """Buat chart object pada tab mulai baris 8."""
        chart: dict[str, object] = {
            "spec": dict(spec),
            "position": {
                "overlayPosition": {
                    "anchorCell": {"sheetId": sheet_id, "rowIndex": 7, "columnIndex": 0},
                    "widthPixels": 640,
                    "heightPixels": 360,
                }
            },
        }
        payload = self._batch_update(
            spreadsheet_id,
            [{"addChart": {"chart": chart}}],
        )
        for reply in _sequence(payload.get("replies")):
            added = _mapping(_mapping(reply).get("addChart"))
            chart_payload = _mapping(added.get("chart"))
            if chart_payload:
                return ChartRecord(
                    chart_id=_positive_int(chart_payload.get("chartId"), field_name="chartId"),
                    spec=_mapping(chart_payload.get("spec")),
                )
        raise SheetsError(f"Pembuatan chart pada tab {sheet_id} tidak mengembalikan chartId.")

    def update_chart(
        self,
        spreadsheet_id: str,
        chart_id: int,
        spec: Mapping[str, object],
    ) -> ChartRecord:
        """Perbarui spec chart tanpa mengganti ID, sehingga link Slides tetap."""
        self._batch_update(
            spreadsheet_id,
            [{"updateChartSpec": {"chartId": chart_id, "spec": dict(spec)}}],
        )
        return ChartRecord(chart_id=chart_id, spec=spec)

    def _get_spreadsheet_payload(self, spreadsheet_id: str) -> Mapping[str, object]:
        try:
            payload = (
                self._service.spreadsheets()
                .get(
                    spreadsheetId=spreadsheet_id,
                    includeGridData=False,
                    fields=(
                        "spreadsheetId,spreadsheetUrl,properties.title,"
                        "sheets(properties(sheetId,title),charts(chartId,spec))"
                    ),
                )
                .execute()
            )
        except Exception as error:
            raise SheetsError(
                f"Spreadsheet '{spreadsheet_id}' tidak dapat dibaca: {error}",
                code=_http_status(error),
            ) from error
        if not isinstance(payload, Mapping):
            raise SheetsError("Sheets mengembalikan respons yang bukan objek JSON.")
        return cast("Mapping[str, object]", payload)

    def _batch_update(
        self,
        spreadsheet_id: str,
        requests: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        try:
            payload = (
                self._service.spreadsheets()
                .batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": list(requests)})
                .execute()
            )
        except Exception as error:
            raise SheetsError(
                f"Batch update spreadsheet '{spreadsheet_id}' gagal: {error}"
            ) from error
        if not isinstance(payload, Mapping):
            raise SheetsError("Sheets batchUpdate mengembalikan respons yang bukan objek JSON.")
        return cast("Mapping[str, object]", payload)


def _spreadsheet_from_payload(payload: object, *, title: str) -> SpreadsheetRef:
    if not isinstance(payload, Mapping):
        raise SheetsError("Sheets mengembalikan respons spreadsheet yang bukan objek JSON.")
    data = cast("Mapping[str, object]", payload)
    spreadsheet_id = data.get("spreadsheetId")
    if not isinstance(spreadsheet_id, str) or not spreadsheet_id.strip():
        raise SheetsError("Sheets tidak mengembalikan spreadsheetId.")
    url = data.get("spreadsheetUrl")
    if not isinstance(url, str) or not url:
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    properties = _mapping(data.get("properties"))
    remote_title = properties.get("title", data.get("title", title))
    return SpreadsheetRef(
        spreadsheet_id=spreadsheet_id,
        url=url,
        title=remote_title if isinstance(remote_title, str) else str(remote_title),
    )


def validate_chart_spec(spec: object) -> None:
    """Validasi bentuk ``ChartSpec`` Google Sheets sebelum dikirim ke API/fake.

    Google menolak enum chart yang salah, ``valueAxis``, dan ``sliceInfo``.
    Validator ini menjaga fake dan adapter nyata memakai kontrak yang sama.
    """
    if not isinstance(spec, Mapping):
        raise SheetsError("Chart spec Sheets harus berupa objek JSON.")
    payload = cast("Mapping[str, object]", spec)
    basic = payload.get("basicChart")
    pie = payload.get("pieChart")
    if basic is not None and pie is not None:
        raise SheetsError("Chart spec tidak boleh memuat basicChart dan pieChart sekaligus.")
    if basic is not None:
        _validate_basic_chart(basic)
        return
    if pie is not None:
        _validate_pie_chart(pie)
        return
    raise SheetsError("Chart spec harus memuat basicChart atau pieChart.")


def _validate_basic_chart(raw: object) -> None:
    chart = _mapping(raw)
    if not chart:
        raise SheetsError("basicChart harus berupa objek JSON.")
    chart_type = chart.get("chartType")
    if not isinstance(chart_type, str) or chart_type not in _BASIC_CHART_TYPES:
        raise SheetsError(f"basicChart.chartType tidak valid: {chart_type!r}.")
    legend = chart.get("legendPosition")
    if not isinstance(legend, str) or legend not in _LEGEND_POSITIONS:
        raise SheetsError(f"basicChart.legendPosition tidak valid: {legend!r}.")
    if "valueAxis" in chart:
        raise SheetsError("basicChart.valueAxis tidak dikenal; gunakan basicChart.axis.")
    series = chart.get("series")
    if not isinstance(series, list | tuple) or not series:
        raise SheetsError("basicChart.series wajib berupa daftar tidak kosong.")
    for index, raw_series in enumerate(series):
        item = _mapping(raw_series)
        target_axis = item.get("targetAxis")
        if not isinstance(target_axis, str) or target_axis not in _SERIES_TARGET_AXES:
            raise SheetsError(
                f"basicChart.series[{index}].targetAxis harus LEFT_AXIS atau RIGHT_AXIS, "
                f"bukan {target_axis!r}."
            )
        _validate_chart_data(item.get("series"), field=f"basicChart.series[{index}].series")
    domains = chart.get("domains")
    if not isinstance(domains, list | tuple) or not domains:
        raise SheetsError("basicChart.domains wajib berupa daftar tidak kosong.")
    for index, raw_domain in enumerate(domains):
        domain = _mapping(raw_domain)
        _validate_chart_data(domain.get("domain"), field=f"basicChart.domains[{index}].domain")
    axes = chart.get("axis", ())
    if not isinstance(axes, list | tuple):
        raise SheetsError("basicChart.axis harus berupa daftar.")
    for index, raw_axis in enumerate(axes):
        axis = _mapping(raw_axis)
        position = axis.get("position")
        if not isinstance(position, str) or position not in _AXIS_POSITIONS:
            raise SheetsError(f"basicChart.axis[{index}].position tidak valid: {position!r}.")
        title = axis.get("title")
        if title is not None and not isinstance(title, str):
            raise SheetsError(f"basicChart.axis[{index}].title harus teks.")


def _validate_pie_chart(raw: object) -> None:
    chart = _mapping(raw)
    if not chart:
        raise SheetsError("pieChart harus berupa objek JSON.")
    legend = chart.get("legendPosition")
    if not isinstance(legend, str) or legend not in _PIE_LEGEND_POSITIONS:
        raise SheetsError(f"pieChart.legendPosition tidak valid: {legend!r}.")
    if "sliceInfo" in chart:
        raise SheetsError("pieChart.sliceInfo tidak dikenal oleh Sheets API.")
    _validate_chart_data(chart.get("domain"), field="pieChart.domain")
    series = chart.get("series")
    if isinstance(series, list | tuple):
        raise SheetsError("pieChart.series harus ChartData, bukan daftar sliceInfo.")
    _validate_chart_data(series, field="pieChart.series")


def _validate_chart_data(raw: object, *, field: str) -> None:
    data = _mapping(raw)
    if not data:
        raise SheetsError(f"{field} wajib berupa ChartData dengan sourceRange.")
    source_range = _mapping(data.get("sourceRange"))
    sources = source_range.get("sources")
    if not isinstance(sources, list | tuple) or not sources:
        raise SheetsError(f"{field}.sourceRange.sources wajib berupa daftar tidak kosong.")
    for index, raw_source in enumerate(sources):
        source = _mapping(raw_source)
        for key in (
            "sheetId",
            "startRowIndex",
            "endRowIndex",
            "startColumnIndex",
            "endColumnIndex",
        ):
            value = source.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SheetsError(
                    f"{field}.sourceRange.sources[{index}].{key} wajib integer non-negatif."
                )


def _http_status(error: BaseException) -> int | None:
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status
    code = getattr(error, "code", None)
    return code if isinstance(code, int) else None


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)
    return {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, list | tuple):
        return tuple(value)
    return ()


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SheetsError(f"Sheets field '{field_name}' wajib integer positif.")
    return value


def _non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SheetsError(f"Sheets field '{field_name}' wajib integer non-negatif.")
    return value


__all__ = [
    "CellValue",
    "ChartRecord",
    "GoogleSheetsApi",
    "SheetRef",
    "SheetsApi",
    "SpreadsheetRef",
    "validate_chart_spec",
]
