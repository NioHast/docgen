"""Parser ``transcripts.md`` AutoOffice v1.

Parser memetakan bagian berdasarkan ``slide_id``, bukan posisi. Berkas harus
memuat tepat satu bagian untuk setiap slide saat berkas ada. Heading memakai
titik setelah ID, ``### Indonesia`` wajib, ``### English`` opsional, dan durasi
opsional berupa bilangan bulat positif.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from autooffice.errors import AutoOfficeError

from .model import TranscriptIR, TranscriptProse, TranscriptSection

_SECTION_HEADING = re.compile(r"^##\s+(?P<slide_id>s[0-9]{2,})\.\s+(?P<title>.+?)\s*$")
_DURATION_LINE = re.compile(r"^\s*\*\*Perkiraan durasi:\*\*\s*(?P<value>.*)$")
_DURATION_VALUE = re.compile(r"^(?P<number>[0-9]+)\s+detik$")


class TranscriptError(AutoOfficeError):
    """``transcripts.md`` tidak memenuhi kontrak transcript v1."""

    def __init__(
        self,
        message: str,
        *,
        source: str | None = "transcripts.md",
        line: int | None = None,
        slide_id: str | None = None,
    ) -> None:
        self.message = message
        self.source = source
        self.line = line
        self.slide_id = slide_id
        location = source or "<transcript>"
        if line is not None:
            location = f"{location}:{line}"
        suffix = f" (slide={slide_id})" if slide_id is not None else ""
        super().__init__(f"{location}: {message}{suffix}")


@dataclass
class _LanguageBuffer:
    """Baris prosa yang belum difinalisasi untuk satu bahasa."""

    lines: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class _SectionBuilder:
    """Bagian transkrip yang sedang dirakit."""

    slide_id: str
    title: str
    heading_line: int
    indonesian: _LanguageBuffer | None = None
    english: _LanguageBuffer | None = None
    duration_seconds: int | None = None


def parse_transcript(
    text: str,
    slide_ids: Sequence[str],
    *,
    source_name: str | None = "transcripts.md",
) -> TranscriptIR:
    """Parse teks transkrip dan validasi cakupan seluruh slide."""
    if not isinstance(text, str):
        raise TranscriptError("Input transkrip harus string.", source=source_name)
    expected = tuple(slide_ids)
    expected_set = set(expected)
    seen_sections: dict[str, int] = {}
    builders: list[TranscriptSection] = []
    current: _SectionBuilder | None = None
    current_language: str | None = None
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.removeprefix("\ufeff")

    for line_number, line in enumerate(normalized.split("\n"), start=1):
        if line.startswith("###"):
            if current is None:
                raise TranscriptError(
                    "Heading bahasa hanya boleh muncul di dalam bagian slide.",
                    source=source_name,
                    line=line_number,
                )
            current_language = _start_language(
                current,
                line,
                line_number=line_number,
                source=source_name,
            )
            continue

        if line.startswith("##"):
            if current is not None:
                builders.append(_finalize_section(current, source=source_name))
            current = _start_section(
                line,
                line_number=line_number,
                expected=expected_set,
                seen=seen_sections,
                source=source_name,
            )
            current_language = None
            continue

        if line.startswith("#"):
            if current is None and line.startswith("# "):
                continue
            raise TranscriptError(
                "Heading tidak dikenal di dalam transkrip.",
                source=source_name,
                line=line_number,
                slide_id=current.slide_id if current is not None else None,
            )

        if current is None:
            if line.strip():
                raise TranscriptError(
                    "Teks di luar bagian slide tidak diizinkan.",
                    source=source_name,
                    line=line_number,
                )
            continue

        duration = _DURATION_LINE.match(line)
        if duration is not None:
            current.duration_seconds = _parse_duration(
                duration.group("value"),
                current,
                line_number=line_number,
                source=source_name,
            )
            continue

        if current_language is None:
            if line.strip():
                raise TranscriptError(
                    "Isi bagian harus dimulai dengan '### Indonesia'.",
                    source=source_name,
                    line=line_number,
                    slide_id=current.slide_id,
                )
            continue

        _buffer_for(current, current_language).lines.append((line_number, line))

    if current is not None:
        builders.append(_finalize_section(current, source=source_name))

    missing = [slide_id for slide_id in expected if slide_id not in seen_sections]
    if missing:
        raise TranscriptError(
            f"Transkrip tidak memuat bagian untuk slide: {', '.join(missing)}.",
            source=source_name,
        )
    return TranscriptIR(sections=tuple(builders), source=source_name)


def parse_transcript_file(
    path: str | Path,
    slide_ids: Sequence[str],
) -> TranscriptIR:
    """Baca UTF-8 ``transcripts.md`` lalu parse dan validasi isinya."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise TranscriptError(
            f"Berkas transkrip tidak dapat dibaca: {error}", source=str(source)
        ) from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TranscriptError(
            f"Berkas transkrip harus UTF-8: {error}", source=str(source)
        ) from error
    return parse_transcript(text, slide_ids=slide_ids, source_name=str(source))


load_transcript = parse_transcript_file


def _start_section(
    line: str,
    *,
    line_number: int,
    expected: set[str],
    seen: dict[str, int],
    source: str | None,
) -> _SectionBuilder:
    match = _SECTION_HEADING.fullmatch(line.strip())
    if match is None:
        raise TranscriptError(
            "Heading bagian harus berbentuk '## <slide_id>. <judul slide>'.",
            source=source,
            line=line_number,
        )
    slide_id = match.group("slide_id")
    if slide_id not in expected:
        raise TranscriptError(
            f"Slide ID '{slide_id}' tidak dikenal pada deck.",
            source=source,
            line=line_number,
            slide_id=slide_id,
        )
    if slide_id in seen:
        raise TranscriptError(
            f"Slide ID '{slide_id}' duplikat; bagian pertama ada di baris {seen[slide_id]}.",
            source=source,
            line=line_number,
            slide_id=slide_id,
        )
    seen[slide_id] = line_number
    return _SectionBuilder(
        slide_id=slide_id,
        title=match.group("title").strip(),
        heading_line=line_number,
    )


def _start_language(
    builder: _SectionBuilder,
    line: str,
    *,
    line_number: int,
    source: str | None,
) -> str:
    name = line[3:].strip()
    if name == "Indonesia":
        if builder.indonesian is not None:
            raise TranscriptError(
                "Heading '### Indonesia' duplikat pada bagian ini.",
                source=source,
                line=line_number,
                slide_id=builder.slide_id,
            )
        if builder.english is not None:  # pragma: no cover - Indonesia selalu sudah ada
            raise TranscriptError(
                "Heading '### Indonesia' harus muncul sebelum '### English'.",
                source=source,
                line=line_number,
                slide_id=builder.slide_id,
            )
        builder.indonesian = _LanguageBuffer()
        return "id"
    if name == "English":
        if builder.english is not None:
            raise TranscriptError(
                "Heading '### English' duplikat pada bagian ini.",
                source=source,
                line=line_number,
                slide_id=builder.slide_id,
            )
        if builder.indonesian is None:
            raise TranscriptError(
                "Heading '### English' tidak boleh muncul sebelum '### Indonesia'.",
                source=source,
                line=line_number,
                slide_id=builder.slide_id,
            )
        builder.english = _LanguageBuffer()
        return "en"
    raise TranscriptError(
        f"Heading bahasa '{name}' tidak dikenal; hanya Indonesia dan English.",
        source=source,
        line=line_number,
        slide_id=builder.slide_id,
    )


def _parse_duration(
    value: str,
    builder: _SectionBuilder,
    *,
    line_number: int,
    source: str | None,
) -> int:
    if builder.duration_seconds is not None:
        raise TranscriptError(
            "Baris '**Perkiraan durasi:**' hanya boleh muncul sekali per bagian.",
            source=source,
            line=line_number,
            slide_id=builder.slide_id,
        )
    match = _DURATION_VALUE.fullmatch(value.strip())
    if match is None:
        raise TranscriptError(
            "Durasi harus berbentuk '<detik> detik' dengan bilangan bulat positif.",
            source=source,
            line=line_number,
            slide_id=builder.slide_id,
        )
    seconds = int(match.group("number"))
    if seconds <= 0:
        raise TranscriptError(
            "Durasi harus bilangan bulat positif.",
            source=source,
            line=line_number,
            slide_id=builder.slide_id,
        )
    return seconds


def _finalize_section(builder: _SectionBuilder, *, source: str | None) -> TranscriptSection:
    if builder.indonesian is None:
        raise TranscriptError(
            "Setiap bagian wajib memiliki '### Indonesia'.",
            source=source,
            line=builder.heading_line,
            slide_id=builder.slide_id,
        )
    indonesian = _prose(
        builder.indonesian,
        source=source,
        slide_id=builder.slide_id,
        language="Indonesia",
        heading_line=builder.heading_line,
    )
    english = None
    if builder.english is not None:
        english = _prose(
            builder.english,
            source=source,
            slide_id=builder.slide_id,
            language="English",
            heading_line=builder.heading_line,
        )
    return TranscriptSection(
        slide_id=builder.slide_id,
        title=builder.title,
        indonesian=indonesian,
        english=english,
        duration_seconds=builder.duration_seconds,
        heading_line=builder.heading_line,
    )


def _prose(
    buffer: _LanguageBuffer,
    *,
    source: str | None,
    slide_id: str,
    language: str,
    heading_line: int,
) -> TranscriptProse:
    lines = list(buffer.lines)
    while lines and not lines[0][1].strip():
        lines.pop(0)
    while lines and not lines[-1][1].strip():
        lines.pop()
    if not lines:
        raise TranscriptError(
            f"Bagian '### {language}' tidak boleh kosong; "
            f"heading bagian ada di baris {heading_line}.",
            source=source,
            line=heading_line,
            slide_id=slide_id,
        )
    text = "\n".join(line for _, line in lines)
    return TranscriptProse(text=text, line=lines[0][0])


def _buffer_for(builder: _SectionBuilder, language: str) -> _LanguageBuffer:
    if language == "id":
        if builder.indonesian is None:  # pragma: no cover - buffer dibuat saat heading
            builder.indonesian = _LanguageBuffer()
        return builder.indonesian
    if builder.english is None:  # pragma: no cover - buffer dibuat saat heading
        builder.english = _LanguageBuffer()
    return builder.english
