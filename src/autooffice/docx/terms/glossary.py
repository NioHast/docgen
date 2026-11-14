"""Glosarium istilah dan parser TSV.

Modul ini hanya memuat tipe glosarium, validasi ``istilah.tsv``, dan merge
entri. Model paragraf, pencocokan istilah, dan style berada di
:mod:`autooffice.docx.terms.model`.
"""

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..package import DocxError

_GLOSSARY_HEADER = ("term", "italic")
_TRUE = "yes"
_FALSE = "no"


class TermsError(DocxError):
    """Pelanggaran penerapan atau verifikasi istilah."""

    default_code = "TERMS"


class GlossaryError(TermsError):
    """Isi ``istilah.tsv`` tidak valid."""

    default_code = "GLOSSARY"


@dataclass(frozen=True)
class GlossaryEntry:
    """Satu istilah; hanya keputusan italic yang masih dipakai."""

    term: str
    italic: bool
    pattern: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "pattern",
            re.compile(
                rf"(?<!\w){re.escape(self.term)}(?!\w)",
                re.IGNORECASE,
            ),
        )


@dataclass(frozen=True)
class Glossary:
    """Glosarium dengan kunci casefold dan asal berkas."""

    entries: Mapping[str, GlossaryEntry]
    source: Path

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[GlossaryEntry]:
        return iter(self.entries.values())


def load_glossary(path: str | Path) -> Glossary:
    """Baca TSV dengan header wajib ``term<TAB>italic``.

    Setiap baris harus memiliki tepat dua kolom. Header dengan kolom
    ``gloss_first``/``status`` ditolak agar format glosarium seragam.
    """

    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise GlossaryError(
            f"Glosarium tidak ditemukan: {source}",
            code="GLOSSARY-MISSING",
            path=source,
        ) from exc
    except UnicodeDecodeError as exc:
        raise GlossaryError(
            f"Glosarium bukan UTF-8 yang valid: {source}",
            code="GLOSSARY-ENCODING",
            path=source,
        ) from exc
    except OSError as exc:
        raise GlossaryError(
            f"Glosarium tidak dapat dibaca: {source}: {exc}",
            code="GLOSSARY-IO",
            path=source,
        ) from exc

    entries: dict[str, GlossaryEntry] = {}
    seen: dict[str, int] = {}
    errors: list[str] = []
    header_seen = False
    expected_columns = 2

    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        columns = [column.strip() for column in line.split("\t")]
        if not header_seen:
            if tuple(columns) != _GLOSSARY_HEADER:
                raise GlossaryError(
                    f"Baris {line_number}: header harus 'term<TAB>italic'.",
                    code="GLOSSARY-HEADER",
                    path=source,
                )
            header_seen = True
            continue

        if len(columns) < expected_columns:
            errors.append(
                f"Baris {line_number}: kolom kurang ({len(columns)} dari {expected_columns})."
            )
            continue
        if len(columns) > expected_columns:
            errors.append(
                f"Baris {line_number}: kolom terlalu banyak "
                f"({len(columns)} dari {expected_columns})."
            )
            continue

        term, italic = columns[0], columns[1]
        if not term:
            errors.append(f"Baris {line_number}: term kosong.")
            continue
        if italic not in {_TRUE, _FALSE}:
            errors.append(f"Baris {line_number}: italic harus 'yes' atau 'no', bukan {italic!r}.")
            continue

        key = term.casefold()
        if key in seen:
            errors.append(
                f"Baris {line_number}: term duplikat {term!r} (sudah ada di baris {seen[key]})."
            )
            continue
        seen[key] = line_number
        entries[key] = GlossaryEntry(term=term, italic=italic == _TRUE)

    if not header_seen:
        errors.append("Header glosarium tidak ditemukan.")
    if errors:
        raise GlossaryError(
            "Glosarium tidak valid:\n" + "\n".join(errors),
            code="GLOSSARY-INVALID",
            path=source,
        )
    return Glossary(entries=entries, source=source)


def merge_glossaries(base: Glossary, override: Glossary) -> Glossary:
    """Gabungkan glosarium; entri override menang per frasa (casefold)."""

    entries = dict(base.entries)
    entries.update(override.entries)
    return Glossary(entries=entries, source=override.source)


__all__ = [
    "Glossary",
    "GlossaryEntry",
    "GlossaryError",
    "TermsError",
    "load_glossary",
    "merge_glossaries",
]
