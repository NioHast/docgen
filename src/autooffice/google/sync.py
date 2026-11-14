"""Push, pull, diff, dan apply teks Google Slides.

Chart data tetap satu arah dari YAML ke Sheets. Modul ini hanya menyinkronkan
teks: isi shape, sel tabel native, notes, dan source. ``apply`` selalu menulis
berkas YAML baru dan tidak pernah mengubah sumber.
"""

import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from ruamel.yaml import YAML

from autooffice.deck.model import DeckIR, KeyBinding, compile_deck_file
from autooffice.design import resolve_theme
from autooffice.design.theme import Theme

from . import GoogleError, GoogleStateError, GoogleSyncError
from .auth import OAuthSettings, TokenStore, load_credentials
from .charts import ChartLink, build_chart_specs, ensure_sheet_chart, ensure_workbook
from .drive import DriveApi, GoogleDriveApi, upload_presentation
from .extract import PulledText, TextEntry, extract_text, normalize_preserve_newlines
from .sheets import GoogleSheetsApi, SheetsApi
from .slides import (
    CHART_MARKER_PREFIX,
    GoogleSlidesApi,
    PresentationSnapshot,
    SlidesApi,
    delete_text_request,
    insert_text_request,
    preflight_chart_replacements,
    replace_chart_placeholders,
    table_namespace,
)
from .state import (
    ChartState,
    atomic_write_json,
    deck_sha256,
    load_state,
    new_state,
    now_iso,
    save_state,
)

SyncMode = Literal["push", "pull", "diff", "apply"]
_TABLE_CELL_KEY = re.compile(
    r"^(?P<namespace>s[0-9]{2,}\.[a-z][a-z0-9_]*)"
    r"(?:\.h(?P<header>[1-9][0-9]*)|\.r(?P<row>[1-9][0-9]*)\.c(?P<column>[1-9][0-9]*))$"
)


@dataclass(frozen=True, slots=True)
class TextChange:
    """Satu perbedaan teks remote terhadap YAML."""

    key: str
    slide_id: str
    from_value: str
    to_value: str
    kind: str

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise GoogleSyncError("TextChange key tidak boleh kosong.")
        if not self.slide_id.strip():
            raise GoogleSyncError(f"TextChange '{self.key}' tidak memiliki slide_id.")


@dataclass(frozen=True, slots=True)
class RejectedChange:
    """Key remote yang tidak boleh masuk ke YAML."""

    key: str
    reason: str


@dataclass(frozen=True, slots=True)
class TextDiff:
    """Hasil diff teks, termasuk key asing dan key yang hilang."""

    presentation_id: str | None
    revision_id: str | None
    changes: tuple[TextChange, ...] = ()
    unknown: tuple[TextEntry, ...] = ()
    missing: tuple[str, ...] = ()
    rejected: tuple[RejectedChange, ...] = ()
    unchanged: int = 0
    generated_at: str | None = None

    @property
    def stats(self) -> Mapping[str, int]:
        """Ringkasan jumlah untuk report."""
        return MappingProxyType(
            {
                "changed": len(self.changes),
                "unchanged": self.unchanged,
                "unknown": len(self.unknown),
                "missing": len(self.missing),
                "rejected": len(self.rejected),
            }
        )

    def to_dict(self) -> dict[str, object]:
        """Bentuk JSON report yang stabil."""
        return {
            "presentation_id": self.presentation_id,
            "revision_id": self.revision_id,
            "generated_at": self.generated_at,
            "changes": [
                {
                    "key": change.key,
                    "slide_id": change.slide_id,
                    "from": change.from_value,
                    "to": change.to_value,
                    "kind": change.kind,
                }
                for change in self.changes
            ],
            "unknown": [{"key": entry.key, "text": entry.text} for entry in self.unknown],
            "missing": list(self.missing),
            "rejected": [
                {"key": rejected.key, "reason": rejected.reason} for rejected in self.rejected
            ],
            "stats": dict(self.stats),
        }


@dataclass(frozen=True, slots=True)
class GoogleServices:
    """Bundle adapter Google yang dipakai orchestrator."""

    drive: DriveApi
    sheets: SheetsApi
    slides: SlidesApi


def create_google_services(
    settings: OAuthSettings | None = None,
    token_store: TokenStore | None = None,
) -> GoogleServices:
    """Bangun services Google nyata dari token OAuth pengguna.

    Client id/secret hanya diperlukan untuk login interaktif. Token yang sudah
    tersimpan dapat dipakai tanpa environment client OAuth.
    """
    store = TokenStore.from_environment() if token_store is None else token_store
    credentials = load_credentials(settings, store)
    try:
        from googleapiclient.discovery import build
    except ImportError as error:  # pragma: no cover - extra google belum terpasang
        raise GoogleSyncError(
            "Extra 'google' belum terpasang; jalankan uv sync --extra google."
        ) from error
    try:
        drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
        sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        slides = build("slides", "v1", credentials=credentials, cache_discovery=False)
    except Exception as error:
        raise GoogleSyncError(f"Google API client tidak dapat dibuat: {error}") from error
    return GoogleServices(
        drive=GoogleDriveApi(drive),
        sheets=GoogleSheetsApi(sheets),
        slides=GoogleSlidesApi(slides),
    )


def pull_text(slides: SlidesApi, presentation_id: str) -> PulledText:
    """Baca seluruh teks berkey remote tanpa mutasi."""
    return extract_text(slides.get_presentation(presentation_id))


def diff_text(
    deck_path: str | Path,
    pulled: PulledText,
    *,
    generated_at: datetime | None = None,
) -> TextDiff:
    """Bandingkan binding teks YAML dengan pulled text remote."""
    deck = compile_deck_file(deck_path)
    return _diff_deck(deck, pulled, generated_at=generated_at)


def _diff_deck(
    deck: DeckIR,
    pulled: PulledText,
    *,
    generated_at: datetime | None,
) -> TextDiff:
    bindings = _all_bindings(deck)
    sync_bindings = {binding.key: binding for binding in bindings if binding.sync}
    all_keys = {binding.key for binding in bindings}
    slide_indices = {slide.slide_id: index for index, slide in enumerate(deck.slides)}
    pulled_entries = pulled.by_key()
    changes: list[TextChange] = []
    unknown: list[TextEntry] = []
    rejected: list[RejectedChange] = []
    unchanged = 0
    for key, entry in pulled_entries.items():
        binding = sync_bindings.get(key)
        if binding is None:
            if key in all_keys:
                rejected.append(
                    RejectedChange(
                        key=key,
                        reason="key bukan target sinkronisasi teks chart/data",
                    )
                )
            elif _looks_structural(key):
                rejected.append(
                    RejectedChange(key=key, reason="key struktural tidak boleh disinkronkan")
                )
            else:
                unknown.append(entry)
            continue
        if entry.slide_id != binding.slide_id:
            rejected.append(
                RejectedChange(
                    key=key,
                    reason=f"slide remote '{entry.slide_id}' bukan '{binding.slide_id}'",
                )
            )
            continue
        expected_index = slide_indices.get(binding.slide_id)
        if (
            entry.slide_index >= 0
            and expected_index is not None
            and entry.slide_index != expected_index
        ):
            rejected.append(
                RejectedChange(
                    key=key,
                    reason=(
                        f"slide index remote {entry.slide_index + 1} bukan "
                        f"{expected_index + 1} untuk '{binding.slide_id}'"
                    ),
                )
            )
            continue
        actual = normalize_text_value(key, entry.text)
        expected = _binding_text(binding)
        if actual == expected:
            unchanged += 1
            continue
        problem = _validate_value(actual, key=key)
        if problem is not None:
            rejected.append(RejectedChange(key=key, reason=problem))
            continue
        changes.append(
            TextChange(
                key=key,
                slide_id=binding.slide_id,
                from_value=expected,
                to_value=actual,
                kind=_change_kind(binding),
            )
        )
    missing = tuple(
        binding.key for binding in sync_bindings.values() if binding.key not in pulled_entries
    )
    return TextDiff(
        presentation_id=pulled.presentation_id,
        revision_id=pulled.revision_id,
        changes=tuple(changes),
        unknown=tuple(unknown),
        missing=missing,
        rejected=tuple(rejected),
        unchanged=unchanged,
        generated_at=now_iso(generated_at) if generated_at is not None else None,
    )


def write_diff_report(diff: TextDiff, path: str | Path) -> Path:
    """Tulis report diff JSON secara atomik."""
    destination = Path(path)
    atomic_write_json(destination, diff.to_dict())
    return destination


def apply_diff(
    deck_path: str | Path,
    diff: TextDiff,
    output_path: str | Path,
) -> Path:
    """Terapkan perubahan diff ke berkas YAML BARU, bukan sumber."""
    source = Path(deck_path)
    destination = Path(output_path).expanduser()
    if source.resolve() == destination.resolve():
        raise GoogleSyncError(
            f"apply tidak boleh menimpa YAML sumber: {destination}. Pilih path baru."
        )
    if diff.unknown:
        keys = ", ".join(entry.key for entry in diff.unknown)
        raise GoogleSyncError(
            f"Diff memuat key asing yang tidak boleh diterapkan: {keys}. "
            "Hapus key tersebut dari sumber remote atau perbaiki deck terlebih dahulu."
        )
    deck = compile_deck_file(source)
    bindings = {binding.key: binding for binding in _all_bindings(deck) if binding.sync}
    seen: set[str] = set()
    for change in diff.changes:
        if change.key in seen:
            raise GoogleSyncError(f"Diff memuat perubahan duplikat untuk key '{change.key}'.")
        seen.add(change.key)
        binding = bindings.get(change.key)
        if binding is None:
            raise GoogleSyncError(
                f"Key '{change.key}' bukan target sinkronisasi teks yang dikenal."
            )
        if change.slide_id != binding.slide_id:
            raise GoogleSyncError(
                f"Key '{change.key}' milik slide '{binding.slide_id}', bukan '{change.slide_id}'."
            )
        expected = _binding_text(binding)
        if normalize_text_value(change.key, change.from_value) != expected:
            raise GoogleSyncError(
                f"Perubahan '{change.key}' basi: from '{change.from_value}' "
                f"tetapi YAML berisi '{expected}'."
            )
        problem = _validate_value(change.to_value, key=change.key)
        if problem is not None:
            raise GoogleSyncError(f"Perubahan '{change.key}' tidak valid: {problem}")

    try:
        text = source.read_text(encoding="utf-8")
    except OSError as error:
        raise GoogleSyncError(f"YAML sumber tidak dapat dibaca: {source}: {error}") from error
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    data: object = yaml.load(text.removeprefix("\ufeff"))
    if not isinstance(data, Mapping):
        raise GoogleSyncError(f"YAML sumber bukan objek mapping: {source}.")
    for change in diff.changes:
        binding = bindings[change.key]
        _set_yaml_path(data, binding.yaml_path, change.to_value, key=change.key)
    _write_yaml_atomic(yaml, data, destination)
    return destination


def apply_pulled_text(
    deck_path: str | Path,
    pulled: PulledText,
    output_path: str | Path,
) -> Path:
    """Tulis YAML baru dengan seluruh nilai remote yang berubah."""
    diff = diff_text(deck_path, pulled)
    return apply_diff(deck_path, diff, output_path)


def push_text(
    slides: SlidesApi,
    presentation_id: str,
    deck_path: str | Path,
    *,
    presentation: PresentationSnapshot | None = None,
) -> int:
    """Tulis teks YAML ke remote setelah seluruh target lolos preflight."""
    deck = compile_deck_file(deck_path)
    snapshot = slides.get_presentation(presentation_id) if presentation is None else presentation
    bindings = tuple(binding for binding in _all_bindings(deck) if binding.sync)
    targets = _text_targets(snapshot)
    slide_indices = {slide.slide_id: index for index, slide in enumerate(deck.slides)}
    requests: list[Mapping[str, object]] = []
    for binding in bindings:
        expected_slide_index = slide_indices.get(binding.slide_id)
        resolved = _resolve_text_target(
            targets,
            binding,
            expected_slide_index=expected_slide_index,
        )
        if resolved is None:
            raise GoogleSyncError(
                f"Elemen teks untuk key '{binding.key}' tidak ditemukan di presentasi "
                f"'{presentation_id}'."
            )
        object_id, cell = resolved
        value = _binding_text(binding)
        requests.append(delete_text_request(object_id, cell_location=cell))
        requests.append(insert_text_request(object_id, value, cell_location=cell))
    if not requests:
        return 0
    slides.batch_update(presentation_id, requests)
    return len(bindings)


def push_deck(
    *,
    deck: str | Path,
    staging: str | Path,
    state: str | Path,
    mode: str = "push",
    review_dir: str | Path | None = None,
    services: GoogleServices | None = None,
    now: datetime | None = None,
    theme: Theme | str | None = None,
) -> tuple[Path, ...]:
    """Push satu deck: spreadsheet, chart linked, presentasi, dan teks."""
    if mode != "push":
        raise GoogleSyncError(f"push_deck hanya menerima mode push, bukan '{mode}'.")
    deck_path = Path(deck)
    staging_path = Path(staging)
    state_file = Path(state)
    compiled = compile_deck_file(deck_path)
    if isinstance(theme, Theme):
        resolved_theme = theme
    elif isinstance(theme, str):
        resolved_theme = resolve_theme(theme)
    else:
        resolved_theme = resolve_theme(compiled.theme_name)
    specs = build_chart_specs(compiled)
    resolved_services = create_google_services() if services is None else services
    current_state = load_state(state_file) if state_file.is_file() else new_state(deck_path)
    current_digest = deck_sha256(deck_path)
    # Digest tetap milik presentasi yang sudah di-upload. Jangan majukan di
    # sini: workbook/chart bisa gagal sebelum upload dan retry tidak boleh
    # menganggap presentasi lama cocok dengan deck baru.
    updated_state = replace(current_state, deck_path=deck_path.name)

    workbook, created = ensure_workbook(
        resolved_services.sheets,
        title=str(compiled.meta.get("title", "")),
        existing_id=updated_state.spreadsheet_id,
    )
    if created:
        updated_state = replace(
            updated_state,
            spreadsheet_id=workbook.spreadsheet_id,
            spreadsheet_url=workbook.url,
            presentation_id=None,
            presentation_url=None,
            charts={},
        )
    else:
        updated_state = replace(
            updated_state,
            spreadsheet_id=workbook.spreadsheet_id,
            spreadsheet_url=workbook.url,
        )
    # Persist workbook lebih dulu: kegagalan chart berikutnya tidak boleh
    # membuat workbook kedua pada rerun.
    save_state(updated_state, state_file)

    links: dict[str, ChartLink] = {}
    chart_states: dict[str, ChartState] = {}
    for spec in specs:
        previous_chart = updated_state.charts.get(spec.chart_id)
        link = ensure_sheet_chart(
            resolved_services.sheets,
            spreadsheet_id=workbook.spreadsheet_id,
            spec=spec,
            theme=resolved_theme,
            existing_sheet_id=(None if previous_chart is None else previous_chart.sheet_id),
        )
        links[spec.chart_id] = link
        chart_states[spec.chart_id] = ChartState(
            tab_name=link.tab_name,
            sheet_id=link.sheet_id,
            embedded_chart_id=link.embedded_chart_id,
            last_data_sha256=link.data_sha256,
        )
    updated_state = replace(updated_state, charts=chart_states)
    save_state(updated_state, state_file)

    snapshot: PresentationSnapshot | None = None
    if updated_state.presentation_id:
        try:
            candidate = resolved_services.slides.get_presentation(updated_state.presentation_id)
        except GoogleError as error:
            if error.code != 404:
                raise GoogleSyncError(
                    f"Presentasi '{updated_state.presentation_id}' tidak dapat diakses: {error}. "
                    "Periksa akun OAuth atau reset state."
                ) from error
            candidate = None
        if (
            candidate is not None
            and _has_pending_placeholders(candidate, links)
            and current_state.deck_sha256 == current_digest
        ):
            snapshot = candidate

    if snapshot is None:
        uploaded = upload_presentation(
            resolved_services.drive,
            staging_path,
            name=str(compiled.meta.get("title", staging_path.stem)),
        )
        updated_state = replace(
            updated_state,
            presentation_id=uploaded.presentation_id,
            presentation_url=uploaded.url,
            deck_sha256=current_digest,
        )
        # Simpan presentasi sebelum preflight; rerun dengan deck yang sama
        # dapat melanjutkan placeholder yang tertunda.
        save_state(updated_state, state_file)
        snapshot = resolved_services.slides.get_presentation(uploaded.presentation_id)

    # Preflight lengkap sebelum placeholder dihapus.
    preflight_chart_replacements(compiled, snapshot, links)

    presentation_id = updated_state.presentation_id
    if presentation_id is None:
        raise GoogleSyncError("State kehilangan presentation_id setelah upload.")
    replaced = replace_chart_placeholders(
        resolved_services.slides,
        presentation_id,
        deck=compiled,
        links=links,
        presentation=snapshot,
    )
    push_text(
        resolved_services.slides,
        presentation_id,
        deck_path,
        presentation=replaced,
    )
    # last_pushed_at baru menandai push selesai setelah replacement dan teks
    # sukses. Kegagalan sebelumnya mempertahankan nilai lama, sementara progress
    # workbook/presentasi/chart yang sudah tersimpan tetap dipakai rerun.
    updated_state = replace(updated_state, last_pushed_at=now_iso(now))
    save_state(updated_state, state_file)
    return (state_file,)


def sync_deck(
    *,
    deck: str | Path,
    staging: str | Path | None = None,
    state: str | Path,
    mode: str,
    review_dir: str | Path,
    services: GoogleServices | None = None,
    now: datetime | None = None,
) -> tuple[Path, ...]:
    """Mode ``pull``/``diff``/``apply``: baca remote, tulis review, tanpa source."""
    if mode not in {"pull", "diff", "apply"}:
        raise GoogleSyncError(f"sync_deck tidak menerima mode '{mode}'.")
    deck_path = Path(deck)
    state_file = Path(state)
    google_state = load_state(state_file)
    if google_state.presentation_id is None:
        raise GoogleStateError(
            f"State '{state_file}' tidak memiliki presentation_id; jalankan push lebih dulu."
        )
    resolved_services = create_google_services() if services is None else services
    compiled = compile_deck_file(deck_path)
    pulled = pull_text(resolved_services.slides, google_state.presentation_id)
    diff = _diff_deck(compiled, pulled, generated_at=now)

    review = Path(review_dir)
    review.mkdir(parents=True, exist_ok=True)
    stem = deck_path.stem
    if mode == "diff":
        output = write_diff_report(diff, review / f"{stem}.diff.json")
    elif mode == "pull":
        output = apply_pulled_text(deck_path, pulled, review / f"{stem}.pulled.yaml")
    else:
        output = apply_diff(deck_path, diff, review / f"{stem}.applied.yaml")

    # Review-only: jangan majukan deck_sha256. Digest hanya berubah saat
    # presentasi baru berhasil di-upload agar reuse staging tetap aman.
    updated_state = replace(
        google_state,
        deck_path=deck_path.name,
        last_pulled_revision_id=pulled.revision_id,
    )
    save_state(updated_state, state_file)
    return (output,)


def _has_pending_placeholders(
    presentation: PresentationSnapshot,
    links: Mapping[str, ChartLink],
) -> bool:
    expected = set(links)
    for element in presentation.elements_including_notes():
        marker = element.marker
        if marker is None or not marker.startswith(CHART_MARKER_PREFIX):
            continue
        chart_id = marker[len(CHART_MARKER_PREFIX) :]
        if chart_id in expected:
            return True
    return False


def _all_bindings(deck: object) -> tuple[KeyBinding, ...]:
    keys = getattr(deck, "keys", None)
    bindings = getattr(keys, "bindings", None)
    if not isinstance(bindings, tuple):
        raise GoogleSyncError("Deck IR tidak memiliki KeyManifest.bindings.")
    return bindings


def _binding_text(binding: KeyBinding) -> str:
    return normalize_text_value(binding.key, binding.plain_text)


def normalize_text_value(key: str, value: str) -> str:
    """Normalisasi pulled/source text sesuai kelas key."""
    if key.endswith(".notes") or key.endswith(".code"):
        return normalize_preserve_newlines(value)
    return " ".join(value.split())


def _change_kind(binding: KeyBinding) -> str:
    if _TABLE_CELL_KEY.fullmatch(binding.key):
        return "tableCell"
    if binding.kind == "notes":
        return "text"
    if binding.kind == "source":
        return "text"
    return "text"


def _validate_value(value: str, *, key: str) -> str | None:
    if not value.strip():
        return f"nilai kosong atau hanya spasi untuk '{key}'"
    if any(ord(character) < 32 and character not in "\n\t" for character in value):
        return "nilai memuat karakter kontrol"
    if "\u2013" in value or "\u2014" in value:
        return "nilai memakai en dash atau em dash"
    return None


def _looks_structural(key: str) -> bool:
    segments = {segment.lower() for segment in re.split(r"[.\-_/]", key) if segment}
    return bool(
        segments & {"meta", "theme", "schema", "token", "tokens", "style", "styles", "layout"}
    )


def _set_yaml_path(data: object, path: Sequence[str | int], value: str, *, key: str) -> None:
    if not path:
        raise GoogleSyncError(f"yaml_path untuk key '{key}' kosong.")
    current: Any = data
    try:
        for segment in path[:-1]:
            current = current[segment]
        current[path[-1]] = value
    except (KeyError, IndexError, TypeError) as error:
        raise GoogleSyncError(
            f"yaml_path untuk key '{key}' tidak cocok dengan YAML sumber: {error}"
        ) from error


def _write_yaml_atomic(yaml: YAML, data: object, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            yaml.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except OSError as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise GoogleSyncError(
            f"YAML hasil sync tidak dapat ditulis: {destination}: {error}"
        ) from error


def _text_targets(
    presentation: PresentationSnapshot,
) -> dict[str, list[tuple[int, str, tuple[int, int] | None]]]:
    targets: dict[str, list[tuple[int, str, tuple[int, int] | None]]] = {}
    for slide in presentation.slides:
        for element in (*slide.page_elements, *slide.notes_page_elements):
            marker = element.marker
            if marker is None:
                continue
            if element.kind == "table":
                namespace = table_namespace(marker)
                if namespace and not namespace.startswith(("autooffice:", "chrome:")):
                    targets.setdefault(namespace, []).append((slide.index, element.object_id, None))
                continue
            if marker.startswith(("autooffice:", "chrome:")):
                continue
            if element.kind == "shape":
                targets.setdefault(marker, []).append((slide.index, element.object_id, None))
    return targets


def _resolve_text_target(
    targets: Mapping[str, list[tuple[int, str, tuple[int, int] | None]]],
    binding: KeyBinding,
    *,
    expected_slide_index: int | None,
) -> tuple[str, tuple[int, int] | None] | None:
    match = _TABLE_CELL_KEY.match(binding.key)
    if match is not None:
        namespace = match.group("namespace")
        elements = _targets_on_slide(
            targets.get(namespace, []),
            expected_slide_index=expected_slide_index,
        )
        if len(elements) != 1:
            return None
        _, object_id, _ = elements[0]
        if match.group("header") is not None:
            return object_id, (0, int(match.group("header")) - 1)
        return object_id, (int(match.group("row")), int(match.group("column")) - 1)
    elements = _targets_on_slide(
        targets.get(binding.key, []),
        expected_slide_index=expected_slide_index,
    )
    if len(elements) != 1:
        return None
    _, object_id, cell = elements[0]
    return object_id, cell


def _targets_on_slide(
    elements: Sequence[tuple[int, str, tuple[int, int] | None]],
    *,
    expected_slide_index: int | None,
) -> Sequence[tuple[int, str, tuple[int, int] | None]]:
    if expected_slide_index is None:
        return elements
    return [element for element in elements if element[0] == expected_slide_index]


__all__ = [
    "GoogleServices",
    "RejectedChange",
    "SyncMode",
    "TextChange",
    "TextDiff",
    "apply_diff",
    "apply_pulled_text",
    "create_google_services",
    "diff_text",
    "normalize_text_value",
    "pull_text",
    "push_deck",
    "push_text",
    "sync_deck",
    "write_diff_report",
]
