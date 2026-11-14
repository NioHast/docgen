"""State Google atomik tanpa token OAuth.

State hanya mencatat objek remote milik satu deck. Ia bukan sumber kebenaran
konten, tidak boleh menyimpan token, dan berada di ``.autooffice/state`` di
samping YAML. Semua penulisan memakai file sementara di direktori tujuan lalu
``os.replace`` agar state lama tidak pernah setengah tertulis.
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import cast

from . import GoogleStateError

STATE_SCHEMA = "autooffice.state/v1"
STATE_DIRECTORY = Path(".autooffice") / "state"
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "deck_path",
        "deck_sha256",
        "presentation_id",
        "presentation_url",
        "spreadsheet_id",
        "spreadsheet_url",
        "last_pulled_revision_id",
        "last_pushed_at",
        "charts",
    }
)
_CHART_FIELDS = frozenset({"tab_name", "sheet_id", "embedded_chart_id", "last_data_sha256"})
_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "token",
        "tokens",
        "secret",
        "client_secret",
        "credential",
        "credentials",
        "refresh",
        "refresh_token",
        "access_token",
        "client_id",
    }
)


def _require_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoogleStateError(f"State field '{field_name}' wajib berupa teks non-kosong.")
    return value


def _optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name=field_name)


def _require_positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GoogleStateError(f"State field '{field_name}' wajib berupa integer positif.")
    return value


def _require_non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GoogleStateError(f"State field '{field_name}' wajib berupa integer non-negatif.")
    return value


def _require_sha256(value: object, *, field_name: str) -> str:
    text = _require_text(value, field_name=field_name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise GoogleStateError(f"State field '{field_name}' wajib berupa SHA-256 heksadesimal.")
    return text


@dataclass(frozen=True, slots=True)
class ChartState:
    """Status remote satu chart: tab, sheet, chart object, dan hash data."""

    tab_name: str
    sheet_id: int
    embedded_chart_id: int
    last_data_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tab_name", _require_text(self.tab_name, field_name="tab_name"))
        object.__setattr__(
            self, "sheet_id", _require_non_negative_int(self.sheet_id, field_name="sheet_id")
        )
        object.__setattr__(
            self,
            "embedded_chart_id",
            _require_positive_int(self.embedded_chart_id, field_name="embedded_chart_id"),
        )
        object.__setattr__(
            self,
            "last_data_sha256",
            _require_sha256(self.last_data_sha256, field_name="last_data_sha256"),
        )

    def to_dict(self) -> dict[str, object]:
        """Bentuk JSON deterministik untuk satu chart."""
        return {
            "tab_name": self.tab_name,
            "sheet_id": self.sheet_id,
            "embedded_chart_id": self.embedded_chart_id,
            "last_data_sha256": self.last_data_sha256,
        }

    @classmethod
    def from_dict(cls, data: object, *, chart_id: str) -> ChartState:
        """Baca satu chart dari JSON dengan field strict."""
        if not isinstance(data, Mapping):
            raise GoogleStateError(f"State chart '{chart_id}' harus berupa objek JSON.")
        mapping = cast("Mapping[str, object]", data)
        _reject_secret_fields(
            cast("Mapping[object, object]", mapping),
            context=f"state chart '{chart_id}'",
        )
        unknown = sorted(set(mapping) - _CHART_FIELDS)
        if unknown:
            raise GoogleStateError(
                f"State chart '{chart_id}' memuat field tidak dikenal: {', '.join(unknown)}."
            )
        missing = sorted(_CHART_FIELDS - set(mapping))
        if missing:
            raise GoogleStateError(
                f"State chart '{chart_id}' kehilangan field: {', '.join(missing)}."
            )
        return cls(
            tab_name=_require_text(mapping["tab_name"], field_name="tab_name"),
            sheet_id=_require_non_negative_int(mapping["sheet_id"], field_name="sheet_id"),
            embedded_chart_id=_require_positive_int(
                mapping["embedded_chart_id"], field_name="embedded_chart_id"
            ),
            last_data_sha256=_require_sha256(
                mapping["last_data_sha256"], field_name="last_data_sha256"
            ),
        )


@dataclass(frozen=True, slots=True)
class GoogleState:
    """State remote satu deck tanpa token atau rahasia OAuth."""

    deck_path: str
    deck_sha256: str
    schema: str = STATE_SCHEMA
    presentation_id: str | None = None
    presentation_url: str | None = None
    spreadsheet_id: str | None = None
    spreadsheet_url: str | None = None
    last_pulled_revision_id: str | None = None
    last_pushed_at: str | None = None
    charts: Mapping[str, ChartState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema != STATE_SCHEMA:
            raise GoogleStateError(
                f"State schema '{self.schema}' tidak dikenal; harus {STATE_SCHEMA}."
            )
        object.__setattr__(self, "deck_path", _require_text(self.deck_path, field_name="deck_path"))
        object.__setattr__(
            self, "deck_sha256", _require_sha256(self.deck_sha256, field_name="deck_sha256")
        )
        for name in (
            "presentation_id",
            "presentation_url",
            "spreadsheet_id",
            "spreadsheet_url",
            "last_pulled_revision_id",
            "last_pushed_at",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name), field_name=name))
        charts: dict[str, ChartState] = {}
        for chart_id, chart in self.charts.items():
            if not isinstance(chart_id, str) or not chart_id.strip():
                raise GoogleStateError("State chart harus memiliki chart_id non-kosong.")
            if not isinstance(chart, ChartState):
                raise GoogleStateError(f"State chart '{chart_id}' bukan ChartState.")
            charts[chart_id] = chart
        object.__setattr__(self, "charts", MappingProxyType(charts))

    def to_dict(self) -> dict[str, object]:
        """Bentuk dict JSON sesuai urutan kontrak."""
        return {
            "schema": self.schema,
            "deck_path": self.deck_path,
            "deck_sha256": self.deck_sha256,
            "presentation_id": self.presentation_id,
            "presentation_url": self.presentation_url,
            "spreadsheet_id": self.spreadsheet_id,
            "spreadsheet_url": self.spreadsheet_url,
            "last_pulled_revision_id": self.last_pulled_revision_id,
            "last_pushed_at": self.last_pushed_at,
            "charts": {
                chart_id: self.charts[chart_id].to_dict() for chart_id in sorted(self.charts)
            },
        }

    @classmethod
    def from_dict(cls, data: object) -> GoogleState:
        """Baca state JSON dengan field strict dan tolak token/rahasia."""
        if not isinstance(data, Mapping):
            raise GoogleStateError("State Google harus berupa objek JSON.")
        mapping = cast("Mapping[str, object]", data)
        _reject_secret_fields(
            cast("Mapping[object, object]", mapping),
            context="state",
        )
        unknown = sorted(set(mapping) - _TOP_LEVEL_FIELDS)
        if unknown:
            raise GoogleStateError(
                f"State Google memuat field tidak dikenal: {', '.join(unknown)}."
            )
        if "schema" not in mapping:
            raise GoogleStateError("State Google kehilangan field 'schema'.")
        if "deck_path" not in mapping:
            raise GoogleStateError("State Google kehilangan field 'deck_path'.")
        if "deck_sha256" not in mapping:
            raise GoogleStateError("State Google kehilangan field 'deck_sha256'.")
        raw_charts = mapping.get("charts", {})
        if not isinstance(raw_charts, Mapping):
            raise GoogleStateError("State field 'charts' harus berupa objek JSON.")
        charts: dict[str, ChartState] = {}
        for chart_id, raw_chart in cast("Mapping[object, object]", raw_charts).items():
            if not isinstance(chart_id, str) or not chart_id.strip():
                raise GoogleStateError("State chart harus memiliki chart_id non-kosong.")
            charts[chart_id] = ChartState.from_dict(raw_chart, chart_id=chart_id)
        return cls(
            schema=_require_text(mapping["schema"], field_name="schema"),
            deck_path=_require_text(mapping["deck_path"], field_name="deck_path"),
            deck_sha256=_require_sha256(mapping["deck_sha256"], field_name="deck_sha256"),
            presentation_id=_optional_text(
                mapping.get("presentation_id"), field_name="presentation_id"
            ),
            presentation_url=_optional_text(
                mapping.get("presentation_url"), field_name="presentation_url"
            ),
            spreadsheet_id=_optional_text(
                mapping.get("spreadsheet_id"), field_name="spreadsheet_id"
            ),
            spreadsheet_url=_optional_text(
                mapping.get("spreadsheet_url"), field_name="spreadsheet_url"
            ),
            last_pulled_revision_id=_optional_text(
                mapping.get("last_pulled_revision_id"),
                field_name="last_pulled_revision_id",
            ),
            last_pushed_at=_optional_text(
                mapping.get("last_pushed_at"), field_name="last_pushed_at"
            ),
            charts=charts,
        )


def _reject_secret_fields(data: Mapping[object, object], *, context: str) -> None:
    """Tolak nama field skema rahasia; jangan menilai chart ID sebagai field.

    ``charts`` adalah map ``chart_id -> ChartState``. Chart ID seperti
    ``s02.token_usage`` adalah data pengguna yang sah, bukan nama field OAuth.
    """
    for raw_key in data:
        key = str(raw_key).lower()
        if key in _FORBIDDEN_FIELD_NAMES:
            raise GoogleStateError(
                f"{context} tidak boleh menyimpan field rahasia/OAuth '{raw_key}'."
            )


def state_path(deck_path: str | Path) -> Path:
    """Path state kanonik di samping YAML: ``.autooffice/state/<stem>.json``."""
    deck = Path(deck_path)
    if not deck.stem:
        raise GoogleStateError(f"Path deck tidak memiliki stem: {deck}.")
    return deck.parent / STATE_DIRECTORY / f"{deck.stem}.json"


def deck_sha256(deck_path: str | Path) -> str:
    """SHA-256 isi YAML sumber; perbedaan bukan error, hanya memicu sync."""
    path = Path(deck_path)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise GoogleStateError(f"Deck tidak dapat dibaca untuk hash: {path}: {error}") from error
    return hashlib.sha256(data).hexdigest()


def new_state(deck_path: str | Path) -> GoogleState:
    """State kosong untuk deck yang belum pernah di-push."""
    path = Path(deck_path)
    return GoogleState(
        deck_path=path.name,
        deck_sha256=deck_sha256(path),
    )


def now_iso(now: datetime | None = None) -> str:
    """Timestamp UTC detik tanpa mikrodetik, misalnya ``2026-11-14T00:00:00Z``."""
    value = datetime.now(UTC) if now is None else now.astimezone(UTC)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_state(path: str | Path) -> GoogleState:
    """Baca state JSON; error menyebut path dan tidak pernah menelan JSON rusak."""
    state_file = Path(path)
    try:
        text = state_file.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise GoogleStateError(
            f"State Google belum ada di {state_file}; jalankan push lebih dulu."
        ) from error
    except OSError as error:
        raise GoogleStateError(f"State Google tidak dapat dibaca: {state_file}: {error}") from error
    try:
        raw: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise GoogleStateError(f"State Google bukan JSON valid: {state_file}: {error}") from error
    return GoogleState.from_dict(raw)


def save_state(state: GoogleState, path: str | Path) -> Path:
    """Tulis state secara atomik dan kembalikan path final."""
    state_file = Path(path)
    atomic_write_json(state_file, state.to_dict())
    return state_file


def atomic_write_json(path: str | Path, payload: Mapping[str, object]) -> Path:
    """Tulis JSON UTF-8 secara atomik di direktori tujuan."""
    destination = Path(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise GoogleStateError(
            f"Direktori state tidak dapat dibuat: {destination.parent}: {error}"
        ) from error

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
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except OSError as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise GoogleStateError(
            f"State Google tidak dapat ditulis: {destination}: {error}"
        ) from error
    return destination


__all__ = [
    "STATE_SCHEMA",
    "ChartState",
    "GoogleState",
    "atomic_write_json",
    "deck_sha256",
    "load_state",
    "new_state",
    "now_iso",
    "save_state",
    "state_path",
]
