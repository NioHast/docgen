"""Model IR transkrip AutoOffice v1.

Transkrip adalah naskah pembicara, bukan teks slide dan bukan notes. Setiap
bagian terikat ke satu ``slide_id``. Urutan bagian dalam berkas bebas; mapping
selalu memakai ID, bukan posisi.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class TranscriptProse:
    """Satu blok prosa transkrip beserta nomor baris awalnya."""

    text: str
    line: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("TranscriptProse.text harus string tidak kosong.")
        if self.line < 0:
            raise ValueError("TranscriptProse.line tidak boleh negatif.")


@dataclass(frozen=True, slots=True)
class TranscriptSection:
    """Satu bagian transkrip untuk satu slide."""

    slide_id: str
    title: str
    indonesian: TranscriptProse
    english: TranscriptProse | None = None
    duration_seconds: int | None = None
    heading_line: int = 0

    def __post_init__(self) -> None:
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise ValueError("TranscriptSection.duration_seconds harus bilangan bulat positif.")

    @property
    def id_key(self) -> str:
        """Key diagnostic untuk bagian Indonesia."""
        return f"{self.slide_id}.transcript.id"

    @property
    def en_key(self) -> str:
        """Key diagnostic untuk bagian Inggris."""
        return f"{self.slide_id}.transcript.en"


@dataclass(frozen=True, slots=True)
class TranscriptIR:
    """Seluruh bagian transkrip yang sudah tervalidasi."""

    sections: tuple[TranscriptSection, ...] = ()
    source: str | None = None

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for section in self.sections:
            if section.slide_id in seen:
                raise ValueError(f"Slide ID '{section.slide_id}' duplikat pada transkrip.")
            seen.add(section.slide_id)
        object.__setattr__(self, "sections", tuple(self.sections))

    def __iter__(self) -> Iterator[TranscriptSection]:
        return iter(self.sections)

    def __len__(self) -> int:
        return len(self.sections)

    @property
    def by_slide_id(self) -> Mapping[str, TranscriptSection]:
        """Mapping slide ID ke bagian transkrip."""
        return MappingProxyType({section.slide_id: section for section in self.sections})

    def section(self, slide_id: str) -> TranscriptSection | None:
        """Kembalikan bagian untuk satu slide, atau None."""
        for section in self.sections:
            if section.slide_id == slide_id:
                return section
        return None

    def keys(self) -> tuple[str, ...]:
        """Key diagnostic transkrip dalam urutan bagian."""
        keys: list[str] = []
        for section in self.sections:
            keys.append(section.id_key)
            if section.english is not None:
                keys.append(section.en_key)
        return tuple(keys)
