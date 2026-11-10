"""Normalisasi metadata front matter ``document.md``.

Semua aturan bentuk penulis, NIM, abstrak, dan kata kunci berada di sini agar
``document.py`` hanya mengurus potongan front matter/body dan validasi silang
dengan struktur.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import MetadataError

_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
_REPORT_NAME_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

DEFAULT_REPORT_NAME = "Tugas"
DEFAULT_LANG = "id-ID"


@dataclass(frozen=True)
class Author:
    """Satu penulis ternormalisasi."""

    name: str
    nim: str | None = None


@dataclass(frozen=True)
class Metadata:
    """Metadata dokumen yang sudah divalidasi dan dinormalisasi."""

    title: str
    authors: tuple[Author, ...]
    subtitle: str | None = None
    lecturer: str | None = None
    lecturer_label: str = "Dosen Pengampu:"
    course: str | None = None
    institution: str | None = None
    faculty: str | None = None
    year: str | None = None
    date: str | None = None
    lang: str = DEFAULT_LANG
    abstract_id: str | None = None
    abstract_en: str | None = None
    preface: str | None = None
    keywords: tuple[str, ...] = ()
    keywords_en: tuple[str, ...] = ()
    report_name: str = DEFAULT_REPORT_NAME

    @property
    def author_names(self) -> tuple[str, ...]:
        return tuple(author.name for author in self.authors)

    @property
    def nim(self) -> str | None:
        if len(self.authors) == 1:
            return self.authors[0].nim
        return None


def _error(message: str, *, code: str, key: str, source: object) -> MetadataError:
    return MetadataError(message, code=code, path=str(source) if source else None, key=key)


def _text(
    value: Any,
    *,
    key: str,
    source: object,
    required: bool = False,
    allow_number: bool = True,
) -> str | None:
    if value is None:
        if required:
            raise _error(f"kunci '{key}' wajib diisi", code="CFG-REQUIRED", key=key, source=source)
        return None
    if isinstance(value, bool):
        raise _error(
            f"kunci '{key}' harus berupa teks",
            code="CFG-TYPE",
            key=key,
            source=source,
        )
    if isinstance(value, (int, float)) and allow_number:
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise _error(
            f"kunci '{key}' harus berupa teks",
            code="CFG-TYPE",
            key=key,
            source=source,
        )
    if required and not text:
        raise _error(
            f"kunci '{key}' tidak boleh kosong",
            code="CFG-REQUIRED",
            key=key,
            source=source,
        )
    if not text:
        return None
    return text


def _multiline(
    value: Any,
    *,
    key: str,
    source: object,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _error(
            f"kunci '{key}' harus berupa teks Markdown",
            code="CFG-TYPE",
            key=key,
            source=source,
        )
    if not value.strip():
        raise _error(
            f"kunci '{key}' tidak boleh kosong",
            code="CFG-REQUIRED",
            key=key,
            source=source,
        )
    return value


def normalize_keywords(value: Any, *, key: str, source: object) -> tuple[str, ...]:
    """String adalah satu kata kunci; daftar dipertahankan berurutan."""

    if value is None:
        return ()
    if isinstance(value, str):
        items: list[Any] = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise _error(
            f"kunci '{key}' harus berupa teks atau daftar teks",
            code="CFG-TYPE",
            key=key,
            source=source,
        )

    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, str):
            raise _error(
                f"kata kunci ke-{index} pada '{key}' harus berupa teks",
                code="CFG-TYPE",
                key=f"{key}[{index}]",
                source=source,
            )
        text = item.strip()
        if not text:
            raise _error(
                f"kata kunci ke-{index} pada '{key}' tidak boleh kosong",
                code="CFG-REQUIRED",
                key=f"{key}[{index}]",
                source=source,
            )
        folded = text.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        result.append(text)
    return tuple(result)


def _normalize_author_entry(entry: Any, *, index: int, source: object) -> Author:
    if isinstance(entry, str):
        name = entry.strip()
        if not name:
            raise _error(
                f"author ke-{index} tidak memiliki nama",
                code="CFG-REQUIRED",
                key=f"author[{index}].name",
                source=source,
            )
        return Author(name=name)
    if not isinstance(entry, Mapping):
        raise _error(
            f"author ke-{index} harus berupa teks atau pemetaan",
            code="CFG-TYPE",
            key=f"author[{index}]",
            source=source,
        )
    unknown = sorted(str(key) for key in entry if str(key) not in {"name", "nim"})
    if unknown:
        raise _error(
            f"author ke-{index} memuat kunci tidak dikenal: {', '.join(unknown)}",
            code="CFG-UNKNOWN-KEY",
            key=f"author[{index}]",
            source=source,
        )
    author_name = _text(
        entry.get("name"),
        key=f"author[{index}].name",
        source=source,
        required=True,
    )
    assert author_name is not None
    nim = _text(
        entry.get("nim"),
        key=f"author[{index}].nim",
        source=source,
    )
    return Author(name=author_name, nim=nim)


def normalize_author(
    value: Any,
    *,
    nim: Any = None,
    source: object = "metadata",
) -> tuple[Author, ...]:
    """Alias publik untuk normalisasi satu/daftar author."""

    return normalize_authors(value, top_level_nim=nim, source=source)


def normalize_authors(
    value: Any,
    *,
    top_level_nim: Any = None,
    source: object,
) -> tuple[Author, ...]:
    """Normalisasi ``author`` scalar/mapping/list dan aturan NIM."""

    if value is None:
        raise _error(
            "kunci 'author' wajib diisi",
            code="CFG-REQUIRED",
            key="author",
            source=source,
        )
    if isinstance(value, (str, Mapping)):
        entries: list[Any] = [value]
    elif isinstance(value, (list, tuple)):
        entries = list(value)
    else:
        raise _error(
            "kunci 'author' harus berupa teks, pemetaan, atau daftar",
            code="CFG-TYPE",
            key="author",
            source=source,
        )
    if not entries:
        raise _error(
            "daftar 'author' tidak boleh kosong",
            code="CFG-REQUIRED",
            key="author",
            source=source,
        )

    nim = _text(top_level_nim, key="nim", source=source)
    if nim is not None and len(entries) != 1:
        raise _error(
            "kunci 'nim' tingkat atas hanya boleh dipakai untuk satu author; "
            "tulis NIM di setiap entri author",
            code="CFG-CONDITIONAL",
            key="nim",
            source=source,
        )

    authors = [
        _normalize_author_entry(entry, index=index, source=source)
        for index, entry in enumerate(entries, start=1)
    ]
    if nim is not None:
        author = authors[0]
        if author.nim is not None and author.nim != nim:
            raise _error(
                f"NIM tingkat atas '{nim}' bertentangan dengan NIM author '{author.nim}'",
                code="CFG-CONFLICT",
                key="nim",
                source=source,
            )
        authors[0] = Author(name=author.name, nim=nim)
    return tuple(authors)


def _report_name(value: Any, *, source: object) -> str:
    text = _text(value, key="report_name", source=source) or DEFAULT_REPORT_NAME
    if text in {".", ".."} or _REPORT_NAME_FORBIDDEN.search(text):
        raise _error(
            f"report_name '{text}' tidak aman sebagai nama berkas",
            code="CFG-TYPE",
            key="report_name",
            source=source,
        )
    if text.endswith((".", " ")):
        raise _error(
            f"report_name '{text}' tidak boleh berakhir dengan titik atau spasi",
            code="CFG-TYPE",
            key="report_name",
            source=source,
        )
    return text


def normalize_metadata(front_matter: Mapping[str, Any], *, source: object) -> Metadata:
    """Bangun ``Metadata`` dari front matter yang sudah lolos skema kunci."""

    title = _text(
        front_matter.get("title"),
        key="title",
        source=source,
        required=True,
    )
    assert title is not None

    authors = normalize_authors(
        front_matter.get("author"),
        top_level_nim=front_matter.get("nim"),
        source=source,
    )

    subtitle = _text(front_matter.get("subtitle"), key="subtitle", source=source)
    lecturer = _text(front_matter.get("lecturer"), key="lecturer", source=source)
    lecturer_label = (
        _text(front_matter.get("lecturer_label"), key="lecturer_label", source=source)
        or "Dosen Pengampu:"
    )
    course = _text(front_matter.get("course"), key="course", source=source)
    institution = _text(front_matter.get("institution"), key="institution", source=source)
    faculty = _text(front_matter.get("faculty"), key="faculty", source=source)
    year = _text(front_matter.get("year"), key="year", source=source)
    date = _text(front_matter.get("date"), key="date", source=source)
    lang = _text(front_matter.get("lang"), key="lang", source=source) or DEFAULT_LANG
    if not _LANG_RE.fullmatch(lang):
        raise _error(
            f"lang '{lang}' bukan locale BCP-47 yang valid",
            code="CFG-TYPE",
            key="lang",
            source=source,
        )

    abstract_id = _multiline(front_matter.get("abstract_id"), key="abstract_id", source=source)
    abstract_en = _multiline(front_matter.get("abstract_en"), key="abstract_en", source=source)
    preface = _multiline(front_matter.get("preface"), key="preface", source=source)

    keywords = normalize_keywords(front_matter.get("keywords"), key="keywords", source=source)
    keywords_en = normalize_keywords(
        front_matter.get("keywords_en"), key="keywords_en", source=source
    )
    if keywords and abstract_id is None:
        raise _error(
            "kunci 'keywords' hanya boleh dipakai jika 'abstract_id' ada",
            code="CFG-CONDITIONAL",
            key="keywords",
            source=source,
        )
    if keywords_en and abstract_en is None:
        raise _error(
            "kunci 'keywords_en' hanya boleh dipakai jika 'abstract_en' ada",
            code="CFG-CONDITIONAL",
            key="keywords_en",
            source=source,
        )

    return Metadata(
        title=title,
        authors=authors,
        subtitle=subtitle,
        lecturer=lecturer,
        lecturer_label=lecturer_label,
        course=course,
        institution=institution,
        faculty=faculty,
        year=year,
        date=date,
        lang=lang,
        abstract_id=abstract_id,
        abstract_en=abstract_en,
        preface=preface,
        keywords=keywords,
        keywords_en=keywords_en,
        report_name=_report_name(front_matter.get("report_name"), source=source),
    )
