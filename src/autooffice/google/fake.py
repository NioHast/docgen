"""Fake Google in-memory dengan kontrak metode yang sama.

Fake tidak menyentuh jaringan. Drive membuat snapshot presentasi melalui
``converter`` milik test atau presentasi kosong, Sheets menyimpan spreadsheet
dan chart, dan Slides mengeksekusi batchUpdate terhadap snapshot immutable.
"""

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from . import DriveError, FakeGoogleError, SheetsError
from .drive import PPTX_MIME_TYPE, SLIDES_MIME_TYPE, UploadedPresentation
from .sheets import CellValue, ChartRecord, SheetRef, SpreadsheetRef, validate_chart_spec
from .slides import (
    LINKED_MODE,
    ElementSize,
    ElementTransform,
    PageElement,
    PresentationSnapshot,
    SlideSnapshot,
)

PresentationConverter = Callable[[Path, str, str], PresentationSnapshot]


@dataclass(frozen=True, slots=True)
class UploadRequest:
    """Satu upload Drive yang tercatat di fake."""

    source_path: Path
    name: str
    media_mime_type: str
    target_mime_type: str
    size_bytes: int


@dataclass(slots=True)
class _FakeSheet:
    sheet_id: int
    title: str
    values: dict[str, list[list[CellValue]]]
    chart: ChartRecord | None = None


@dataclass(slots=True)
class _FakeSpreadsheet:
    spreadsheet_id: str
    title: str
    url: str
    sheets: dict[int, _FakeSheet]


class FakeSheets:
    """Sheets in-memory dengan ID deterministik dan trace operasi."""

    def __init__(self) -> None:
        self._spreadsheets: dict[str, _FakeSpreadsheet] = {}
        self._next_spreadsheet = 1
        self._next_sheet = 1
        self._next_chart = 1
        self.operations: list[tuple[str, Mapping[str, object]]] = []

    def create_spreadsheet(self, title: str) -> SpreadsheetRef:
        """Buat spreadsheet baru dan tab default ``Sheet1``."""
        if not title.strip():
            raise SheetsError("Judul spreadsheet fake tidak boleh kosong.")
        spreadsheet_id = f"spreadsheet-{self._next_spreadsheet}"
        self._next_spreadsheet += 1
        default_sheet = _FakeSheet(
            sheet_id=self._next_sheet,
            title="Sheet1",
            values={},
        )
        self._next_sheet += 1
        spreadsheet = _FakeSpreadsheet(
            spreadsheet_id=spreadsheet_id,
            title=title,
            url=f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
            sheets={default_sheet.sheet_id: default_sheet},
        )
        self._spreadsheets[spreadsheet_id] = spreadsheet
        self.operations.append(("create_spreadsheet", {"title": title}))
        return SpreadsheetRef(spreadsheet_id=spreadsheet_id, url=spreadsheet.url, title=title)

    def get_spreadsheet(self, spreadsheet_id: str) -> SpreadsheetRef | None:
        """Ambil spreadsheet atau ``None`` bila sudah dihapus."""
        spreadsheet = self._spreadsheets.get(spreadsheet_id)
        if spreadsheet is None:
            return None
        return SpreadsheetRef(
            spreadsheet_id=spreadsheet.spreadsheet_id,
            url=spreadsheet.url,
            title=spreadsheet.title,
        )

    def find_sheet(self, spreadsheet_id: str, title: str) -> SheetRef | None:
        """Cari tab berdasarkan judul."""
        spreadsheet = self._require_spreadsheet(spreadsheet_id)
        for sheet in spreadsheet.sheets.values():
            if sheet.title == title:
                return SheetRef(sheet_id=sheet.sheet_id, title=sheet.title)
        return None

    def get_sheet(self, spreadsheet_id: str, sheet_id: int) -> SheetRef | None:
        """Ambil tab berdasarkan sheetId, tahan terhadap rename tab."""
        spreadsheet = self._require_spreadsheet(spreadsheet_id)
        sheet = spreadsheet.sheets.get(sheet_id)
        if sheet is None:
            return None
        return SheetRef(sheet_id=sheet.sheet_id, title=sheet.title)

    def rename_sheet(self, spreadsheet_id: str, sheet_id: int, title: str) -> SheetRef:
        """Rename tab tanpa mengubah sheetId; dipakai test dan fake."""
        spreadsheet = self._require_spreadsheet(spreadsheet_id)
        sheet = spreadsheet.sheets.get(sheet_id)
        if sheet is None:
            raise FakeGoogleError(f"Sheet ID {sheet_id} tidak ditemukan.", code=404)
        if any(
            other.title == title and other.sheet_id != sheet_id
            for other in spreadsheet.sheets.values()
        ):
            raise FakeGoogleError(f"Tab '{title}' sudah ada pada spreadsheet '{spreadsheet_id}'.")
        sheet.title = title
        self.operations.append(("rename_sheet", {"sheetId": sheet_id, "title": title}))
        return SheetRef(sheet_id=sheet.sheet_id, title=sheet.title)

    def add_sheet(self, spreadsheet_id: str, title: str) -> SheetRef:
        """Tambah tab; judul duplikat ditolak seperti Sheets."""
        spreadsheet = self._require_spreadsheet(spreadsheet_id)
        if any(sheet.title == title for sheet in spreadsheet.sheets.values()):
            raise FakeGoogleError(f"Tab '{title}' sudah ada pada spreadsheet '{spreadsheet_id}'.")
        sheet = _FakeSheet(sheet_id=self._next_sheet, title=title, values={})
        self._next_sheet += 1
        spreadsheet.sheets[sheet.sheet_id] = sheet
        self.operations.append(("add_sheet", {"title": title, "sheetId": sheet.sheet_id}))
        return SheetRef(sheet_id=sheet.sheet_id, title=title)

    def write_values(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: Sequence[Sequence[CellValue]],
    ) -> None:
        """Simpan matriks nilai per range tanpa formula."""
        spreadsheet = self._require_spreadsheet(spreadsheet_id)
        title = _tab_from_range(range_name)
        sheet = self._require_sheet_title(spreadsheet, title)
        matrix = [list(row) for row in values]
        if not matrix or any(not row for row in matrix):
            raise SheetsError("Nilai fake tidak boleh kosong.")
        sheet.values[range_name] = matrix
        self.operations.append(("write_values", {"range": range_name, "rows": len(matrix)}))

    def get_chart(self, spreadsheet_id: str, sheet_id: int) -> ChartRecord | None:
        """Ambil chart pertama pada tab."""
        spreadsheet = self._require_spreadsheet(spreadsheet_id)
        sheet = spreadsheet.sheets.get(sheet_id)
        if sheet is None:
            return None
        return sheet.chart

    def create_chart(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        spec: Mapping[str, object],
    ) -> ChartRecord:
        """Buat satu chart object per tab."""
        validate_chart_spec(spec)
        spreadsheet = self._require_spreadsheet(spreadsheet_id)
        sheet = spreadsheet.sheets.get(sheet_id)
        if sheet is None:
            raise FakeGoogleError(f"Sheet ID {sheet_id} tidak ditemukan.")
        if sheet.chart is not None:
            raise FakeGoogleError(f"Tab '{sheet.title}' sudah memiliki chart object.")
        chart = ChartRecord(chart_id=self._next_chart, spec=copy.deepcopy(dict(spec)))
        self._next_chart += 1
        sheet.chart = chart
        self.operations.append(("create_chart", {"chartId": chart.chart_id, "sheetId": sheet_id}))
        return chart

    def update_chart(
        self,
        spreadsheet_id: str,
        chart_id: int,
        spec: Mapping[str, object],
    ) -> ChartRecord:
        """Perbarui spec chart dan pertahankan chart ID."""
        validate_chart_spec(spec)
        spreadsheet = self._require_spreadsheet(spreadsheet_id)
        for sheet in spreadsheet.sheets.values():
            if sheet.chart is not None and sheet.chart.chart_id == chart_id:
                sheet.chart = ChartRecord(chart_id=chart_id, spec=copy.deepcopy(dict(spec)))
                self.operations.append(("update_chart", {"chartId": chart_id}))
                return sheet.chart
        raise FakeGoogleError(f"Chart ID {chart_id} tidak ditemukan.")

    def has_chart(self, spreadsheet_id: str, chart_id: int) -> bool:
        """True bila chart object ada di spreadsheet, dipakai fake Slides."""
        spreadsheet = self._spreadsheets.get(spreadsheet_id)
        if spreadsheet is None:
            return False
        return any(
            sheet.chart is not None and sheet.chart.chart_id == chart_id
            for sheet in spreadsheet.sheets.values()
        )

    def sheet_values(self, spreadsheet_id: str, title: str) -> list[list[CellValue]] | None:
        """Nilai terakhir satu tab, untuk assertion test."""
        spreadsheet = self._spreadsheets.get(spreadsheet_id)
        if spreadsheet is None:
            return None
        for sheet in spreadsheet.sheets.values():
            if sheet.title == title:
                if not sheet.values:
                    return None
                return copy.deepcopy(next(iter(sheet.values.values())))
        return None

    def _require_spreadsheet(self, spreadsheet_id: str) -> _FakeSpreadsheet:
        spreadsheet = self._spreadsheets.get(spreadsheet_id)
        if spreadsheet is None:
            raise FakeGoogleError(f"Spreadsheet '{spreadsheet_id}' tidak ditemukan.", code=404)
        return spreadsheet

    def _require_sheet_title(self, spreadsheet: _FakeSpreadsheet, title: str) -> _FakeSheet:
        for sheet in spreadsheet.sheets.values():
            if sheet.title == title:
                return sheet
        raise FakeGoogleError(
            f"Tab '{title}' tidak ditemukan pada spreadsheet '{spreadsheet.spreadsheet_id}'.",
            code=404,
        )


class FakeSlides:
    """Slides in-memory yang mengeksekusi deleteObject/createSheetsChart/text."""

    def __init__(self, sheets: FakeSheets | None = None) -> None:
        self._presentations: dict[str, PresentationSnapshot] = {}
        self._sheets = sheets
        self._next_presentation = 1
        self._next_object = 1
        self._revision = 0
        self.requests_log: list[Mapping[str, object]] = []
        self.create_table_requests: list[Mapping[str, object]] = []

    def add_presentation(self, presentation: PresentationSnapshot) -> None:
        """Daftarkan snapshot presentasi yang sudah dibuat test."""
        if presentation.presentation_id in self._presentations:
            raise FakeGoogleError(f"Presentasi '{presentation.presentation_id}' sudah terdaftar.")
        self._presentations[presentation.presentation_id] = copy.deepcopy(presentation)

    def new_presentation_id(self) -> str:
        """ID presentasi deterministik berikutnya."""
        value = f"presentation-{self._next_presentation}"
        self._next_presentation += 1
        return value

    def get_presentation(self, presentation_id: str) -> PresentationSnapshot:
        """Ambil snapshot; revisi mengikuti jumlah batchUpdate."""
        presentation = self._presentations.get(presentation_id)
        if presentation is None:
            raise FakeGoogleError(f"Presentasi '{presentation_id}' tidak ditemukan.", code=404)
        return copy.deepcopy(presentation)

    def batch_update(
        self,
        presentation_id: str,
        requests: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        """Terapkan request secara berurutan dan kembalikan replies."""
        presentation = self.get_presentation(presentation_id)
        replies: list[Mapping[str, object]] = []
        mutable = _MutablePresentation.from_snapshot(presentation)
        for raw_request in requests:
            request = dict(raw_request)
            self.requests_log.append(copy.deepcopy(request))
            if "createTable" in request:
                self.create_table_requests.append(copy.deepcopy(request))
                raise FakeGoogleError("CreateTableRequest tidak dipakai v1.", code=400)
            if "deleteObject" in request:
                object_id = _object_id_from(request["deleteObject"])
                mutable.delete_object(object_id)
                replies.append({"deleteObject": {}})
                continue
            if "createSheetsChart" in request:
                reply = mutable.create_sheets_chart(request["createSheetsChart"], self._sheets)
                replies.append(reply)
                continue
            if "deleteText" in request:
                mutable.delete_text(request["deleteText"])
                replies.append({"deleteText": {}})
                continue
            if "insertText" in request:
                mutable.insert_text(request["insertText"])
                replies.append({"insertText": {}})
                continue
            raise FakeGoogleError(f"Request Slides fake tidak dikenal: {sorted(request)}.")
        self._revision += 1
        updated = mutable.to_snapshot(revision_id=f"revision-{self._revision}")
        self._presentations[presentation_id] = updated
        return {"replies": replies, "revisionId": updated.revision_id}

    def next_object_id(self, prefix: str = "object") -> str:
        """Object ID deterministik untuk fixture test."""
        value = f"{prefix}-{self._next_object}"
        self._next_object += 1
        return value


class FakeDrive:
    """Drive in-memory yang membuat presentasi melalui converter test."""

    def __init__(
        self,
        slides: FakeSlides,
        *,
        converter: PresentationConverter | None = None,
    ) -> None:
        self._slides = slides
        self._converter = converter
        self.uploads: list[UploadRequest] = []

    def upload_presentation(self, pptx: Path, *, name: str) -> UploadedPresentation:
        """Catat upload dan daftarkan snapshot presentasi baru."""
        source = Path(pptx)
        if not source.is_file():
            raise DriveError(f"File staging PPTX tidak ditemukan: {source}.")
        if source.suffix.lower() != ".pptx":
            raise DriveError(f"Upload fake memerlukan .pptx, bukan {source.name!r}.")
        if not name.strip():
            raise DriveError("Nama presentasi fake tidak boleh kosong.")
        presentation_id = self._slides.new_presentation_id()
        if self._converter is None:
            snapshot = PresentationSnapshot(
                presentation_id=presentation_id,
                title=name,
                revision_id=None,
                slides=(),
            )
        else:
            snapshot = self._converter(source, name, presentation_id)
            if snapshot.presentation_id != presentation_id:
                snapshot = replace(snapshot, presentation_id=presentation_id)
        self._slides.add_presentation(snapshot)
        self.uploads.append(
            UploadRequest(
                source_path=source,
                name=name,
                media_mime_type=PPTX_MIME_TYPE,
                target_mime_type=SLIDES_MIME_TYPE,
                size_bytes=source.stat().st_size,
            )
        )
        return UploadedPresentation(
            presentation_id=presentation_id,
            url=f"https://docs.google.com/presentation/d/{presentation_id}/edit",
            name=name,
        )


@dataclass(frozen=True, slots=True)
class FakeGoogleServices:
    """Bundle fake dengan kontrak yang sama seperti services nyata."""

    drive: FakeDrive
    sheets: FakeSheets
    slides: FakeSlides

    @classmethod
    def create(
        cls,
        *,
        converter: PresentationConverter | None = None,
    ) -> FakeGoogleServices:
        """Buat bundle fake yang saling terhubung untuk linked chart."""
        sheets = FakeSheets()
        slides = FakeSlides(sheets)
        return cls(drive=FakeDrive(slides, converter=converter), sheets=sheets, slides=slides)


@dataclass(slots=True)
class _MutableSlide:
    object_id: str
    index: int
    page_elements: list[PageElement]
    notes_page_elements: list[PageElement]

    @classmethod
    def from_snapshot(cls, slide: SlideSnapshot) -> _MutableSlide:
        return cls(
            object_id=slide.object_id,
            index=slide.index,
            page_elements=list(slide.page_elements),
            notes_page_elements=list(slide.notes_page_elements),
        )


@dataclass(slots=True)
class _MutablePresentation:
    presentation_id: str
    title: str
    slides: list[_MutableSlide]

    @classmethod
    def from_snapshot(cls, presentation: PresentationSnapshot) -> _MutablePresentation:
        return cls(
            presentation_id=presentation.presentation_id,
            title=presentation.title,
            slides=[_MutableSlide.from_snapshot(slide) for slide in presentation.slides],
        )

    def to_snapshot(self, *, revision_id: str) -> PresentationSnapshot:
        return PresentationSnapshot(
            presentation_id=self.presentation_id,
            title=self.title,
            revision_id=revision_id,
            slides=tuple(
                SlideSnapshot(
                    object_id=slide.object_id,
                    index=slide.index,
                    page_elements=tuple(slide.page_elements),
                    notes_page_elements=tuple(slide.notes_page_elements),
                )
                for slide in self.slides
            ),
        )

    def delete_object(self, object_id: str) -> None:
        for slide in self.slides:
            for collection in (slide.page_elements, slide.notes_page_elements):
                for index, element in enumerate(collection):
                    if element.object_id == object_id:
                        del collection[index]
                        return
        raise FakeGoogleError(f"Object '{object_id}' tidak ditemukan.", code=404)

    def create_sheets_chart(
        self,
        payload: object,
        sheets: FakeSheets | None,
    ) -> Mapping[str, object]:
        data = _mapping(payload)
        spreadsheet_id = data.get("spreadsheetId")
        chart_id = data.get("chartId")
        linking_mode = data.get("linkingMode")
        if linking_mode != LINKED_MODE:
            raise FakeGoogleError(
                f"createSheetsChart fake hanya menerima linkingMode {LINKED_MODE}.",
                code=400,
            )
        if not isinstance(spreadsheet_id, str) or not spreadsheet_id:
            raise FakeGoogleError("createSheetsChart memerlukan spreadsheetId.", code=400)
        if isinstance(chart_id, bool) or not isinstance(chart_id, int) or chart_id <= 0:
            raise FakeGoogleError("createSheetsChart memerlukan chartId positif.", code=400)
        if sheets is not None and not sheets.has_chart(spreadsheet_id, chart_id):
            raise FakeGoogleError(
                f"Chart '{chart_id}' tidak ada di spreadsheet '{spreadsheet_id}'.",
                code=404,
            )
        properties = _mapping(data.get("elementProperties"))
        page_object_id = properties.get("pageObjectId")
        if not isinstance(page_object_id, str) or not page_object_id:
            raise FakeGoogleError("createSheetsChart memerlukan pageObjectId.", code=400)
        slide = _find_slide(self.slides, page_object_id)
        size = ElementSize.from_api(properties.get("size"))
        transform = ElementTransform.from_api(properties.get("transform"))
        object_id = f"linked-chart-{page_object_id}-{chart_id}-{len(slide.page_elements)}"
        element = PageElement(
            object_id=object_id,
            page_object_id=page_object_id,
            kind="sheets_chart",
            spreadsheet_id=spreadsheet_id,
            chart_id=chart_id,
            size=size,
            transform=transform,
        )
        slide.page_elements.append(element)
        return {"createSheetsChart": {"objectId": object_id}}

    def delete_text(self, payload: object) -> None:
        _slide, collection, index, cell = _resolve_text_target(self.slides, payload)
        element = collection[index]
        if cell is None:
            collection[index] = replace(element, text="")
            return
        row, column = cell
        collection[index] = replace(
            element,
            cells=_replace_cell(element.cells, row, column, ""),
        )

    def insert_text(self, payload: object) -> None:
        data = _mapping(payload)
        text = data.get("text")
        if not isinstance(text, str) or not text:
            raise FakeGoogleError("insertText memerlukan teks non-kosong.", code=400)
        _slide, collection, index, cell = _resolve_text_target(self.slides, payload)
        element = collection[index]
        if cell is None:
            collection[index] = replace(element, text=text)
            return
        row, column = cell
        collection[index] = replace(
            element,
            cells=_replace_cell(element.cells, row, column, text),
        )


def _find_slide(slides: Sequence[_MutableSlide], page_object_id: str) -> _MutableSlide:
    for slide in slides:
        if slide.object_id == page_object_id:
            return slide
    raise FakeGoogleError(f"Slide '{page_object_id}' tidak ditemukan.", code=404)


def _find_element(
    slides: Sequence[_MutableSlide],
    object_id: str,
) -> tuple[_MutableSlide, list[PageElement], int]:
    for slide in slides:
        for collection in (slide.page_elements, slide.notes_page_elements):
            for index, element in enumerate(collection):
                if element.object_id == object_id:
                    return slide, collection, index
    raise FakeGoogleError(f"Object '{object_id}' tidak ditemukan.", code=404)


def _resolve_text_target(
    slides: Sequence[_MutableSlide],
    payload: object,
) -> tuple[_MutableSlide, list[PageElement], int, tuple[int, int] | None]:
    data = _mapping(payload)
    object_id = data.get("objectId")
    if not isinstance(object_id, str) or not object_id:
        raise FakeGoogleError("deleteText/insertText memerlukan objectId.", code=400)
    slide, collection, index = _find_element(slides, object_id)
    cell_data = data.get("cellLocation")
    if cell_data is None:
        return slide, collection, index, None
    cell = _mapping(cell_data)
    row = cell.get("rowIndex")
    column = cell.get("columnIndex")
    if (
        isinstance(row, bool)
        or not isinstance(row, int)
        or isinstance(column, bool)
        or not isinstance(column, int)
        or row < 0
        or column < 0
    ):
        raise FakeGoogleError("cellLocation fake tidak valid.", code=400)
    return slide, collection, index, (row, column)


def _replace_cell(
    cells: tuple[tuple[str, ...], ...],
    row: int,
    column: int,
    text: str,
) -> tuple[tuple[str, ...], ...]:
    if row >= len(cells) or column >= len(cells[row]):
        raise FakeGoogleError(f"Cell ({row}, {column}) tidak ditemukan.", code=404)
    mutable = [list(item) for item in cells]
    mutable[row][column] = text
    return tuple(tuple(item) for item in mutable)


def _object_id_from(payload: object) -> str:
    data = _mapping(payload)
    object_id = data.get("objectId")
    if not isinstance(object_id, str) or not object_id:
        raise FakeGoogleError("deleteObject memerlukan objectId.", code=400)
    return object_id


def _tab_from_range(range_name: str) -> str:
    if "!" not in range_name:
        raise FakeGoogleError(f"Range '{range_name}' tidak memuat nama tab.", code=400)
    prefix, _ = range_name.split("!", 1)
    value = prefix.strip()
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)
    return {}


__all__ = [
    "FakeDrive",
    "FakeGoogleServices",
    "FakeSheets",
    "FakeSlides",
    "PresentationConverter",
    "UploadRequest",
]
