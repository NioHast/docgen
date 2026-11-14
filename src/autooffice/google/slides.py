"""Snapshot Slides, preflight placeholder/table, dan replacement linked chart."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Protocol, cast, runtime_checkable

from autooffice.deck.model import DeckIR

from . import ChartPlaceholderError, SlidesError, TablePreflightError
from .charts import ChartLink

CHART_MARKER_PREFIX = "autooffice:chart:"
TABLE_MARKER_PREFIX = "autooffice:table:"
LINKED_MODE = "LINKED"

ElementKind = Literal["shape", "table", "image", "group", "sheets_chart", "other"]
ReplacementAction = Literal["replace", "delete_placeholder", "keep"]


def slide_id_for_index(index: int) -> str:
    """ID slide kanonik untuk posisi 0-based, misalnya index 1 -> ``s02``."""
    if index < 0:
        raise SlidesError("Index slide tidak boleh negatif.")
    return f"s{index + 1:02d}"


def table_namespace(marker: str) -> str:
    """Normalisasi marker tabel: buang prefix ``autooffice:table:`` bila ada."""
    value = marker.strip()
    if value.startswith(TABLE_MARKER_PREFIX):
        return value[len(TABLE_MARKER_PREFIX) :]
    return value


@dataclass(frozen=True, slots=True)
class ElementSize:
    """Ukuran page element dalam unit Slides (EMU untuk staging PPTX)."""

    width: int
    height: int
    unit: str = "EMU"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise SlidesError("Ukuran page element harus positif.")
        if not self.unit.strip():
            raise SlidesError("Unit ukuran page element tidak boleh kosong.")

    def to_api(self) -> dict[str, object]:
        """Bentuk ``Size`` Slides API."""
        return {
            "width": {"magnitude": self.width, "unit": self.unit},
            "height": {"magnitude": self.height, "unit": self.unit},
        }

    @classmethod
    def from_api(cls, raw: object) -> ElementSize | None:
        """Baca ``Size`` Slides API dengan aman."""
        data = _mapping(raw)
        width = _dimension(data.get("width"))
        height = _dimension(data.get("height"))
        if width is None or height is None:
            return None
        magnitude, unit = width
        height_magnitude, height_unit = height
        return cls(
            width=magnitude,
            height=height_magnitude,
            unit=unit or height_unit or "EMU",
        )


@dataclass(frozen=True, slots=True)
class ElementTransform:
    """Transform page element yang dipakai ulang oleh linked chart."""

    scale_x: float = 1.0
    scale_y: float = 1.0
    translate_x: float = 0.0
    translate_y: float = 0.0
    unit: str = "EMU"

    def to_api(self) -> dict[str, object]:
        """Bentuk ``AffineTransform`` Slides API."""
        return {
            "scaleX": self.scale_x,
            "scaleY": self.scale_y,
            "translateX": self.translate_x,
            "translateY": self.translate_y,
            "unit": self.unit,
        }

    @classmethod
    def from_api(cls, raw: object) -> ElementTransform | None:
        """Baca transform Slides API dengan default identitas."""
        data = _mapping(raw)
        if not data:
            return None
        return cls(
            scale_x=_float(data.get("scaleX"), default=1.0),
            scale_y=_float(data.get("scaleY"), default=1.0),
            translate_x=_float(data.get("translateX"), default=0.0),
            translate_y=_float(data.get("translateY"), default=0.0),
            unit=str(data.get("unit", "EMU")),
        )


@dataclass(frozen=True, slots=True)
class PageElement:
    """Satu page element Slides yang relevan untuk preflight dan sync."""

    object_id: str
    page_object_id: str
    kind: ElementKind
    title: str | None = None
    description: str | None = None
    text: str = ""
    row_count: int = 0
    column_count: int = 0
    cells: tuple[tuple[str, ...], ...] = ()
    spreadsheet_id: str | None = None
    chart_id: int | None = None
    size: ElementSize | None = None
    transform: ElementTransform | None = None

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise SlidesError("Page element wajib memiliki objectId.")
        if not self.page_object_id.strip():
            raise SlidesError("Page element wajib memiliki pageObjectId.")
        if self.row_count < 0 or self.column_count < 0:
            raise SlidesError("Jumlah baris/kolom page element tidak boleh negatif.")
        if self.kind == "table" and self.row_count == 0:
            raise SlidesError(f"Tabel '{self.object_id}' wajib memiliki minimal satu baris.")
        if self.kind == "table" and self.column_count == 0:
            raise SlidesError(f"Tabel '{self.object_id}' wajib memiliki minimal satu kolom.")

    @property
    def is_table(self) -> bool:
        """True hanya untuk page element ``table`` native."""
        return self.kind == "table"

    @property
    def marker(self) -> str | None:
        """Nilai title/description yang dipakai sebagai identitas AutoOffice."""
        if self.title:
            return self.title
        return self.description


@dataclass(frozen=True, slots=True)
class SlideSnapshot:
    """Satu slide dan page element-nya, termasuk notes page."""

    object_id: str
    index: int
    page_elements: tuple[PageElement, ...] = ()
    notes_page_elements: tuple[PageElement, ...] = ()

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise SlidesError("Slide wajib memiliki objectId.")


@dataclass(frozen=True, slots=True)
class PresentationSnapshot:
    """Snapshot read-only presentasi Google Slides."""

    presentation_id: str
    title: str
    revision_id: str | None
    slides: tuple[SlideSnapshot, ...]

    def __post_init__(self) -> None:
        if not self.presentation_id.strip():
            raise SlidesError("Presentasi wajib memiliki presentationId.")

    def elements(self) -> tuple[PageElement, ...]:
        """Seluruh page element semua slide, tanpa notes page."""
        return tuple(element for slide in self.slides for element in slide.page_elements)

    def elements_including_notes(self) -> tuple[PageElement, ...]:
        """Seluruh page element termasuk notes page."""
        return tuple(
            element
            for slide in self.slides
            for element in (*slide.page_elements, *slide.notes_page_elements)
        )


@dataclass(frozen=True, slots=True)
class TableRequirement:
    """Bentuk table native yang diharapkan dari satu block table."""

    slide_id: str
    block_id: str
    row_count: int
    column_count: int

    @property
    def namespace(self) -> str:
        """Namespace block yang muncul sebagai title tabel di Slides."""
        return f"{self.slide_id}.{self.block_id}"

    @property
    def marker(self) -> str:
        """Marker deterministik yang dipasang renderer PPTX."""
        return f"{TABLE_MARKER_PREFIX}{self.slide_id}.{self.block_id}"


@dataclass(frozen=True, slots=True)
class ChartReplacementAction:
    """Satu aksi replacement untuk satu chart logis.

    ``request`` sudah dibangun saat preflight untuk aksi ``replace`` sehingga
    placeholder tanpa geometry gagal sebelum batch update pertama.
    """

    chart_id: str
    action: ReplacementAction
    placeholder: PageElement | None
    existing: PageElement | None
    request: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.request is not None:
            object.__setattr__(self, "request", MappingProxyType(dict(self.request)))


@dataclass(frozen=True, slots=True)
class ChartReplacementPlan:
    """Rencana replacement yang sudah lolos seluruh preflight."""

    actions: tuple[ChartReplacementAction, ...]
    links: Mapping[str, ChartLink]

    def __post_init__(self) -> None:
        object.__setattr__(self, "links", MappingProxyType(dict(self.links)))


@runtime_checkable
class SlidesApi(Protocol):
    """Kontrak Slides yang dipakai replacement dan sync."""

    def get_presentation(self, presentation_id: str) -> PresentationSnapshot:
        """Ambil snapshot presentasi."""

    def batch_update(
        self,
        presentation_id: str,
        requests: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        """Kirim batchUpdate dan kembalikan respons mentah."""


class GoogleSlidesApi:
    """Adapter tipis Google Slides v1."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def get_presentation(self, presentation_id: str) -> PresentationSnapshot:
        """Ambil presentasi dan ubah menjadi snapshot bertipe."""
        if not presentation_id.strip():
            raise SlidesError("presentationId tidak boleh kosong.")
        try:
            payload = self._service.presentations().get(presentationId=presentation_id).execute()
        except Exception as error:
            raise SlidesError(
                f"Presentasi '{presentation_id}' tidak dapat dibaca: {error}",
                code=_http_status(error),
            ) from error
        return presentation_from_api(payload)

    def batch_update(
        self,
        presentation_id: str,
        requests: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        """Kirim batchUpdate tanpa fallback diam-diam."""
        if not requests:
            return {"replies": []}
        try:
            payload = (
                self._service.presentations()
                .batchUpdate(
                    presentationId=presentation_id,
                    body={"requests": [dict(request) for request in requests]},
                )
                .execute()
            )
        except Exception as error:
            raise SlidesError(
                f"Batch update presentasi '{presentation_id}' gagal: {error}"
            ) from error
        if not isinstance(payload, Mapping):
            raise SlidesError("Slides batchUpdate mengembalikan respons yang bukan objek JSON.")
        return cast("Mapping[str, object]", payload)


def table_requirements(deck: DeckIR) -> tuple[TableRequirement, ...]:
    """Turunkan row/column count native dari setiap block table."""
    requirements: list[TableRequirement] = []
    for slide in deck.slides:
        for block in slide.blocks:
            if block.block_type != "table":
                continue
            columns = block.fields.get("columns")
            rows = block.fields.get("rows")
            if not isinstance(columns, tuple) or not columns:
                raise TablePreflightError(
                    f"Block table '{block.block_id}' pada slide '{slide.slide_id}' "
                    "tidak memiliki kolom."
                )
            if not isinstance(rows, tuple) or not rows:
                raise TablePreflightError(
                    f"Block table '{block.block_id}' pada slide '{slide.slide_id}' "
                    "tidak memiliki baris."
                )
            width = len(columns)
            requirements.append(
                TableRequirement(
                    slide_id=slide.slide_id,
                    block_id=block.block_id,
                    row_count=len(rows) + 1,
                    column_count=width,
                )
            )
    return tuple(requirements)


def chart_ids(deck: DeckIR) -> tuple[str, ...]:
    """Seluruh chart_id logis deck dalam urutan slide dan block."""
    ids: list[str] = []
    for slide in deck.slides:
        for block in slide.blocks:
            if block.block_type == "chart":
                ids.append(f"{slide.slide_id}.{block.block_id}")
    return tuple(ids)


def find_chart_placeholders(
    presentation: PresentationSnapshot,
    expected_chart_ids: Sequence[str],
) -> Mapping[str, PageElement]:
    """Cari placeholder chart tepat satu per ``chart_id`` yang diharapkan."""
    expected = tuple(expected_chart_ids)
    if len(set(expected)) != len(expected):
        raise ChartPlaceholderError("Daftar chart_id yang diharapkan memuat duplikat.")
    placeholders = _collect_chart_placeholders(presentation)
    unexpected = sorted(set(placeholders) - set(expected))
    if unexpected:
        raise ChartPlaceholderError(
            "Placeholder chart tidak dikenal: " + ", ".join(unexpected) + "."
        )
    result: dict[str, PageElement] = {}
    for chart_id in expected:
        elements = placeholders.get(chart_id, ())
        if not elements:
            raise ChartPlaceholderError(
                f"Placeholder chart '{chart_id}' tidak ditemukan pada presentasi "
                f"'{presentation.presentation_id}'."
            )
        if len(elements) > 1:
            raise ChartPlaceholderError(
                f"Placeholder chart '{chart_id}' ditemukan {len(elements)} kali; wajib tepat satu."
            )
        element = elements[0]
        if element.kind != "shape":
            raise ChartPlaceholderError(
                f"Placeholder chart '{chart_id}' bertipe '{element.kind}', bukan shape placeholder."
            )
        result[chart_id] = element
    return MappingProxyType(result)


def preflight_native_tables(deck: DeckIR, presentation: PresentationSnapshot) -> None:
    """Pastikan setiap block table menjadi page element ``table`` native.

    Semua requirement diperiksa sebelum ada mutasi remote. Marker
    ``sNN.block`` dan ``autooffice:table:sNN.block`` diperlakukan sama.
    Elemen yang berpindah slide ditolak, bukan diterima sebagai milik key.
    """
    elements = _elements_with_slide_index(presentation)
    slide_indices = {slide.slide_id: index for index, slide in enumerate(deck.slides)}
    for requirement in table_requirements(deck):
        expected_index = slide_indices[requirement.slide_id]
        all_matches = [
            (slide_index, element)
            for slide_index, element in elements
            if element.marker is not None
            and table_namespace(element.marker) == requirement.namespace
        ]
        matches = [
            (slide_index, element)
            for slide_index, element in all_matches
            if slide_index == expected_index
        ]
        location = f"slide '{requirement.slide_id}' block '{requirement.block_id}'"
        off_slide = [
            (slide_index, element)
            for slide_index, element in all_matches
            if slide_index != expected_index
        ]
        if off_slide:
            actual = sorted({slide_index + 1 for slide_index, _ in all_matches})
            raise TablePreflightError(
                f"Table native untuk {location} ditemukan di slide index "
                f"{', '.join(str(index) for index in actual)}, "
                f"bukan hanya slide index {expected_index + 1}."
            )
        if not matches:
            raise TablePreflightError(
                f"Table native untuk {location} tidak ditemukan; "
                "Google Slides mengimpor table sebagai elemen yang hilang."
            )
        if len(matches) > 1:
            raise TablePreflightError(
                f"Table native untuk {location} ditemukan {len(matches)} kali; wajib tepat satu."
            )
        element = matches[0][1]
        if not element.is_table:
            raise TablePreflightError(
                f"Table untuk {location} bukan table native; ditemukan '{element.kind}'. "
                "Table tidak boleh menjadi image atau shape group."
            )
        if (
            element.row_count != requirement.row_count
            or element.column_count != requirement.column_count
        ):
            raise TablePreflightError(
                f"Table native untuk {location} memiliki "
                f"{element.row_count}x{element.column_count}; "
                f"diharapkan {requirement.row_count}x{requirement.column_count}."
            )


def preflight_chart_replacements(
    deck: DeckIR,
    presentation: PresentationSnapshot,
    links: Mapping[str, ChartLink],
) -> ChartReplacementPlan:
    """Validasi table, placeholder, dan linked chart sebelum mutasi apa pun."""
    expected_ids = chart_ids(deck)
    if set(links) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(links))
        extra = sorted(set(links) - set(expected_ids))
        detail = []
        if missing:
            detail.append("link hilang: " + ", ".join(missing))
        if extra:
            detail.append("link asing: " + ", ".join(extra))
        raise SlidesError("Link chart tidak sesuai deck: " + "; ".join(detail) + ".")

    preflight_native_tables(deck, presentation)
    placeholders = _collect_chart_placeholders_with_index(presentation)
    unexpected = sorted(set(placeholders) - set(expected_ids))
    if unexpected:
        raise ChartPlaceholderError(
            "Placeholder chart tidak dikenal: " + ", ".join(unexpected) + "."
        )
    slide_indices = {slide.slide_id: index for index, slide in enumerate(deck.slides)}

    linked_with_index = _collect_linked_charts_with_index(presentation)
    linked = tuple(element for _, element in linked_with_index)
    actions: list[ChartReplacementAction] = []
    for chart_id in expected_ids:
        link = links[chart_id]
        expected_index = slide_indices[chart_id.split(".", 1)[0]]
        identity_matches = [
            (slide_index, element)
            for slide_index, element in linked_with_index
            if element.spreadsheet_id == link.spreadsheet_id
            and element.chart_id == link.embedded_chart_id
        ]
        if len(identity_matches) > 1:
            raise ChartPlaceholderError(
                f"Linked chart untuk '{chart_id}' ditemukan {len(identity_matches)} kali; "
                "wajib tepat satu."
            )
        if identity_matches and identity_matches[0][0] != expected_index:
            actual_index = identity_matches[0][0]
            raise ChartPlaceholderError(
                f"Linked chart untuk '{chart_id}' berada di slide index "
                f"{actual_index + 1}, bukan slide index {expected_index + 1}."
            )
        existing = identity_matches[0][1] if identity_matches else None
        placeholder_elements = placeholders.get(chart_id, ())
        if len(placeholder_elements) > 1:
            actual = sorted({slide_index + 1 for slide_index, _ in placeholder_elements})
            raise ChartPlaceholderError(
                f"Placeholder chart '{chart_id}' ditemukan {len(placeholder_elements)} kali "
                f"di slide index {', '.join(str(index) for index in actual)}; wajib tepat satu."
            )
        on_expected_slide = [
            element
            for slide_index, element in placeholder_elements
            if slide_index == expected_index
        ]
        if not on_expected_slide and placeholder_elements:
            actual = sorted({slide_index + 1 for slide_index, _ in placeholder_elements})
            raise ChartPlaceholderError(
                f"Placeholder chart '{chart_id}' ditemukan di slide index "
                f"{', '.join(str(index) for index in actual)}, "
                f"bukan slide index {expected_index + 1}."
            )
        placeholder = on_expected_slide[0] if on_expected_slide else None
        if placeholder is not None and placeholder.kind != "shape":
            raise ChartPlaceholderError(
                f"Placeholder chart '{chart_id}' bertipe '{placeholder.kind}', "
                "bukan shape placeholder."
            )
        if existing is not None and placeholder is not None:
            actions.append(
                ChartReplacementAction(
                    chart_id=chart_id,
                    action="delete_placeholder",
                    placeholder=placeholder,
                    existing=existing,
                )
            )
        elif existing is not None:
            actions.append(
                ChartReplacementAction(
                    chart_id=chart_id,
                    action="keep",
                    placeholder=None,
                    existing=existing,
                )
            )
        elif placeholder is not None:
            # Bangun request sekarang agar geometry divalidasi sebelum batch pertama.
            actions.append(
                ChartReplacementAction(
                    chart_id=chart_id,
                    action="replace",
                    placeholder=placeholder,
                    existing=None,
                    request=create_sheets_chart_request(link, placeholder),
                )
            )
        else:
            raise ChartPlaceholderError(
                f"Placeholder chart '{chart_id}' tidak ditemukan dan linked chart "
                "yang cocok juga tidak ada."
            )

    _reject_geometry_conflicts(actions, linked, links)
    return ChartReplacementPlan(actions=tuple(actions), links=links)


def replace_chart_placeholders(
    slides: SlidesApi,
    presentation_id: str,
    *,
    deck: DeckIR,
    links: Mapping[str, ChartLink],
    presentation: PresentationSnapshot | None = None,
) -> PresentationSnapshot:
    """Hapus placeholder dan buat linked Sheets chart secara idempoten."""
    snapshot = slides.get_presentation(presentation_id) if presentation is None else presentation
    plan = preflight_chart_replacements(deck, snapshot, links)
    for action in plan.actions:
        requests: list[Mapping[str, object]] = []
        if action.action == "replace":
            placeholder = _require_placeholder(action)
            request = action.request
            if request is None:
                raise ChartPlaceholderError(
                    f"Aksi replacement '{action.chart_id}' belum memiliki request preflight."
                )
            requests.append(delete_object_request(placeholder.object_id))
            requests.append(request)
        elif action.action == "delete_placeholder":
            placeholder = _require_placeholder(action)
            requests.append(delete_object_request(placeholder.object_id))
        if requests:
            slides.batch_update(presentation_id, requests)
    updated = slides.get_presentation(presentation_id)
    verify_linked_charts(updated, plan.links, deck=deck)
    return updated


def verify_linked_charts(
    presentation: PresentationSnapshot,
    links: Mapping[str, ChartLink],
    *,
    deck: DeckIR | None = None,
) -> None:
    """Verifikasi setiap chart muncul tepat satu kali dan tanpa placeholder sisa."""
    linked = _collect_linked_charts_with_index(presentation)
    slide_indices = (
        {slide.slide_id: index for index, slide in enumerate(deck.slides)}
        if deck is not None
        else {}
    )
    for chart_id, link in links.items():
        matches = [
            (slide_index, element)
            for slide_index, element in linked
            if element.spreadsheet_id == link.spreadsheet_id
            and element.chart_id == link.embedded_chart_id
        ]
        expected_index = slide_indices.get(chart_id.split(".", 1)[0])
        if expected_index is not None and any(
            slide_index != expected_index for slide_index, _ in matches
        ):
            actual = sorted({slide_index + 1 for slide_index, _ in matches})
            raise ChartPlaceholderError(
                f"Linked chart '{chart_id}' berada di slide index "
                f"{', '.join(str(index) for index in actual)}, "
                f"bukan slide index {expected_index + 1}."
            )
        elements = [element for _, element in matches]
        if len(elements) != 1:
            raise ChartPlaceholderError(
                f"Linked chart '{chart_id}' ditemukan {len(elements)} kali setelah replacement; "
                "wajib tepat satu."
            )
    placeholders = _collect_chart_placeholders(presentation)
    leftovers = sorted(set(placeholders) & set(links))
    if leftovers:
        raise ChartPlaceholderError(
            "Placeholder chart tersisa setelah replacement: " + ", ".join(leftovers) + "."
        )


def create_sheets_chart_request(
    link: ChartLink,
    placeholder: PageElement,
) -> Mapping[str, object]:
    """Request ``createSheetsChart`` linked dengan posisi dari placeholder."""
    if placeholder.size is None or placeholder.transform is None:
        raise ChartPlaceholderError(
            f"Placeholder chart '{link.chart_id}' tidak memiliki size/transform."
        )
    element_properties: dict[str, object] = {
        "pageObjectId": placeholder.page_object_id,
        "size": placeholder.size.to_api(),
        "transform": placeholder.transform.to_api(),
    }
    return {
        "createSheetsChart": {
            "spreadsheetId": link.spreadsheet_id,
            "chartId": link.embedded_chart_id,
            "linkingMode": LINKED_MODE,
            "elementProperties": element_properties,
        }
    }


def delete_object_request(object_id: str) -> Mapping[str, object]:
    """Request ``deleteObject`` untuk satu page element."""
    if not object_id.strip():
        raise SlidesError("deleteObject memerlukan objectId non-kosong.")
    return {"deleteObject": {"objectId": object_id}}


def delete_text_request(
    object_id: str,
    *,
    cell_location: tuple[int, int] | None = None,
) -> Mapping[str, object]:
    """Request ``deleteText`` seluruh isi shape, tabel, atau notes."""
    if not object_id.strip():
        raise SlidesError("deleteText memerlukan objectId non-kosong.")
    payload: dict[str, object] = {
        "objectId": object_id,
        "textRange": {"type": "ALL"},
    }
    if cell_location is not None:
        payload["cellLocation"] = _cell_location(cell_location)
    return {"deleteText": payload}


def insert_text_request(
    object_id: str,
    text: str,
    *,
    cell_location: tuple[int, int] | None = None,
) -> Mapping[str, object]:
    """Request ``insertText`` pada index 0 untuk shape, tabel, atau notes."""
    if not object_id.strip():
        raise SlidesError("insertText memerlukan objectId non-kosong.")
    if not text.strip():
        raise SlidesError("insertText memerlukan teks non-kosong.")
    payload: dict[str, object] = {
        "objectId": object_id,
        "insertionIndex": 0,
        "text": text,
    }
    if cell_location is not None:
        payload["cellLocation"] = _cell_location(cell_location)
    return {"insertText": payload}


def presentation_from_api(raw: object) -> PresentationSnapshot:
    """Ubah respons ``presentations.get`` menjadi snapshot bertipe."""
    payload = _mapping(raw)
    presentation_id = payload.get("presentationId")
    if not isinstance(presentation_id, str) or not presentation_id.strip():
        raise SlidesError("Slides tidak mengembalikan presentationId.")
    slides: list[SlideSnapshot] = []
    for index, raw_slide in enumerate(_sequence(payload.get("slides"))):
        slide = _mapping(raw_slide)
        object_id = slide.get("objectId")
        if not isinstance(object_id, str) or not object_id.strip():
            raise SlidesError(f"Slide index {index} tidak memiliki objectId.")
        page_elements = tuple(
            element
            for raw_element in _sequence(slide.get("pageElements"))
            if (
                element := _page_element_from_api(
                    raw_element,
                    page_object_id=object_id,
                )
            )
            is not None
        )
        notes_page = _mapping(_mapping(slide.get("slideProperties")).get("notesPage"))
        notes_elements = tuple(
            element
            for raw_element in _sequence(notes_page.get("pageElements"))
            if (
                element := _page_element_from_api(
                    raw_element,
                    page_object_id=str(notes_page.get("objectId", object_id)),
                )
            )
            is not None
        )
        slides.append(
            SlideSnapshot(
                object_id=object_id,
                index=index,
                page_elements=page_elements,
                notes_page_elements=notes_elements,
            )
        )
    revision = payload.get("revisionId")
    return PresentationSnapshot(
        presentation_id=presentation_id,
        title=str(payload.get("title", "")),
        revision_id=revision if isinstance(revision, str) else None,
        slides=tuple(slides),
    )


def _page_element_from_api(raw: object, *, page_object_id: str) -> PageElement | None:
    data = _mapping(raw)
    object_id = data.get("objectId")
    if not isinstance(object_id, str) or not object_id.strip():
        return None
    title_value = data.get("title")
    title = title_value if isinstance(title_value, str) else None
    description_value = data.get("description")
    description = description_value if isinstance(description_value, str) else None
    size = ElementSize.from_api(data.get("size"))
    transform = ElementTransform.from_api(data.get("transform"))
    table = _mapping(data.get("table"))
    if table:
        rows = _sequence(table.get("tableRows"))
        columns = _sequence(table.get("tableColumns"))
        row_count = _positive_count(table.get("rows")) or len(rows)
        column_count = _positive_count(table.get("columns")) or len(columns)
        return PageElement(
            object_id=object_id,
            page_object_id=page_object_id,
            kind="table",
            title=title,
            description=description,
            row_count=row_count,
            column_count=column_count,
            cells=_table_cells(table),
            size=size,
            transform=transform,
        )
    sheets_chart = _mapping(data.get("sheetsChart"))
    if sheets_chart:
        spreadsheet_id = sheets_chart.get("spreadsheetId")
        chart_id = sheets_chart.get("chartId")
        return PageElement(
            object_id=object_id,
            page_object_id=page_object_id,
            kind="sheets_chart",
            title=title,
            description=description,
            spreadsheet_id=spreadsheet_id if isinstance(spreadsheet_id, str) else None,
            chart_id=chart_id
            if isinstance(chart_id, int) and not isinstance(chart_id, bool)
            else None,
            size=size,
            transform=transform,
        )
    if data.get("image"):
        kind: ElementKind = "image"
        text = ""
    elif data.get("elementGroup"):
        kind = "group"
        text = ""
    elif data.get("shape"):
        kind = "shape"
        text = _text_content(_mapping(_mapping(data.get("shape")).get("text")))
    else:
        kind = "other"
        text = ""
    return PageElement(
        object_id=object_id,
        page_object_id=page_object_id,
        kind=kind,
        title=title,
        description=description,
        text=text,
        size=size,
        transform=transform,
    )


def _collect_chart_placeholders(
    presentation: PresentationSnapshot,
) -> dict[str, tuple[PageElement, ...]]:
    return {
        chart_id: tuple(element for _, element in elements)
        for chart_id, elements in _collect_chart_placeholders_with_index(presentation).items()
    }


def _collect_chart_placeholders_with_index(
    presentation: PresentationSnapshot,
) -> dict[str, tuple[tuple[int, PageElement], ...]]:
    result: dict[str, list[tuple[int, PageElement]]] = {}
    for slide in presentation.slides:
        for element in (*slide.page_elements, *slide.notes_page_elements):
            marker = element.marker
            if marker is None or not marker.startswith(CHART_MARKER_PREFIX):
                continue
            chart_id = marker[len(CHART_MARKER_PREFIX) :]
            if (
                not chart_id
                or ":" in chart_id
                or any(character.isspace() for character in chart_id)
            ):
                continue
            result.setdefault(chart_id, []).append((slide.index, element))
    return {chart_id: tuple(elements) for chart_id, elements in result.items()}


def _elements_with_slide_index(
    presentation: PresentationSnapshot,
) -> tuple[tuple[int, PageElement], ...]:
    return tuple(
        (slide.index, element)
        for slide in presentation.slides
        for element in (*slide.page_elements, *slide.notes_page_elements)
    )


def _collect_linked_charts_with_index(
    presentation: PresentationSnapshot,
) -> tuple[tuple[int, PageElement], ...]:
    return tuple(
        (slide.index, element)
        for slide in presentation.slides
        for element in (*slide.page_elements, *slide.notes_page_elements)
        if element.kind == "sheets_chart"
        and element.spreadsheet_id is not None
        and element.chart_id is not None
    )


def _reject_geometry_conflicts(
    actions: Sequence[ChartReplacementAction],
    linked: Sequence[PageElement],
    links: Mapping[str, ChartLink],
) -> None:
    for action in actions:
        placeholder = action.placeholder
        if placeholder is None:
            continue
        link = links[action.chart_id]
        own_identity = (link.spreadsheet_id, link.embedded_chart_id)
        for element in linked:
            if element.size != placeholder.size or element.transform != placeholder.transform:
                continue
            identity = (element.spreadsheet_id, element.chart_id)
            if identity == own_identity:
                continue
            raise ChartPlaceholderError(
                f"Posisi placeholder chart '{action.chart_id}' sudah ditempati linked chart "
                f"dengan spreadsheet '{element.spreadsheet_id}' chart '{element.chart_id}'."
            )


def _require_placeholder(action: ChartReplacementAction) -> PageElement:
    if action.placeholder is None:
        raise ChartPlaceholderError(
            f"Aksi replacement '{action.chart_id}' tidak memiliki placeholder."
        )
    return action.placeholder


def _cell_location(cell: tuple[int, int]) -> dict[str, object]:
    row, column = cell
    if row < 0 or column < 0:
        raise SlidesError("Lokasi sel tabel tidak boleh negatif.")
    return {"rowIndex": row, "columnIndex": column}


def _table_cells(table: Mapping[str, object]) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for raw_row in _sequence(table.get("tableRows")):
        row = _mapping(raw_row)
        cells: list[str] = []
        for raw_cell in _sequence(row.get("tableCells")):
            text = _mapping(_mapping(raw_cell).get("text"))
            cells.append(_text_content(text))
        rows.append(tuple(cells))
    return tuple(rows)


def _text_content(raw: object) -> str:
    data = _mapping(raw)
    parts: list[str] = []
    for raw_element in _sequence(data.get("textElements")):
        element = _mapping(raw_element)
        run = _mapping(element.get("textRun"))
        content = run.get("content")
        if isinstance(content, str):
            parts.append(content)
    if parts:
        return "".join(parts)
    text = data.get("text")
    return text if isinstance(text, str) else ""


def _dimension(raw: object) -> tuple[int, str] | None:
    data = _mapping(raw)
    magnitude = data.get("magnitude")
    if isinstance(magnitude, bool) or not isinstance(magnitude, int | float):
        return None
    return round(magnitude), str(data.get("unit", "EMU"))


def _positive_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return 0
    return value


def _float(value: object, *, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return float(value)


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


__all__ = [
    "CHART_MARKER_PREFIX",
    "LINKED_MODE",
    "TABLE_MARKER_PREFIX",
    "ChartReplacementAction",
    "ChartReplacementPlan",
    "ElementSize",
    "ElementTransform",
    "GoogleSlidesApi",
    "PageElement",
    "PresentationSnapshot",
    "SlideSnapshot",
    "SlidesApi",
    "TableRequirement",
    "chart_ids",
    "create_sheets_chart_request",
    "delete_object_request",
    "delete_text_request",
    "find_chart_placeholders",
    "insert_text_request",
    "preflight_chart_replacements",
    "preflight_native_tables",
    "presentation_from_api",
    "replace_chart_placeholders",
    "slide_id_for_index",
    "table_namespace",
    "table_requirements",
    "verify_linked_charts",
]
