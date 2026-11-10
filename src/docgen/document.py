"""Parser ``document.md``, validasi front matter, dan validasi body.

Modul ini tidak menjalankan Pandoc/Word dan tidak menulis berkas. Semua
validasi yang bisa dilakukan tanpa DOCX berada di sini agar ``docgen check``
aman dijalankan di lingkungan tanpa Word.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from . import paths as path_mod
from .assets import Assets, masked_lines, resolve_assets
from .config import (
    Format,
    Structure,
    format_override_warning,
    load_format,
    load_structure,
    parse_yaml_mapping,
)
from .errors import ConfigError, DocumentError
from .metadata import Metadata, normalize_metadata

_FRONT_MATTER_START = "---"
_FRONT_MATTER_END = {"---", "..."}
_HEADING_RE = re.compile(r"^ {0,3}(?P<hashes>#{1,6})[ \t]+(?P<text>.*?)[ \t]*$")
_CLOSING_HASHES_RE = re.compile(r"[ \t]+#+[ \t]*$")
_NUMBERED_HEADING_RE = re.compile(r"^(?:BAB\s+[IVXLCDM]+|[0-9]+(?:\.[0-9]+)*\.?)(?:\s+|$)")
_INLINE_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+.!-])")

_DOCUMENT_KEYS = frozenset(
    {
        "title",
        "subtitle",
        "author",
        "nim",
        "lecturer",
        "lecturer_label",
        "course",
        "institution",
        "faculty",
        "year",
        "date",
        "lang",
        "structure",
        "format",
        "bibliography",
        "report_name",
        "preface",
        "abstract_id",
        "abstract_en",
        "keywords",
        "keywords_en",
    }
)


@dataclass(frozen=True)
class RawDocument:
    path: Path
    front_matter: Mapping[str, Any]
    body: str


@dataclass(frozen=True)
class Document:
    path: Path
    front_matter: Mapping[str, Any]
    body: str
    metadata: Metadata
    structure_id: str
    format_id: str
    bibliography: str | None


@dataclass(frozen=True)
class EffectiveCover:
    show_lecturer: bool
    logo_width: int
    title_split: bool


@dataclass(frozen=True)
class Project:
    document: Document
    structure: Structure
    format: Format
    assets: Assets
    warnings: tuple[str, ...] = ()

    @property
    def effective_cover(self) -> EffectiveCover:
        cover = self.structure.cover
        return EffectiveCover(
            show_lecturer=cover.show_lecturer,
            logo_width=cover.logo_width,
            title_split=cover.title_split,
        )


def _doc_error(
    message: str,
    *,
    code: str,
    path: Path,
    key: str | None = None,
) -> DocumentError:
    return DocumentError(message, code=code, path=path, key=key)


def _resolve_document_path(document: str | Path) -> Path:
    path = Path(document).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        path = path.resolve()
    except OSError as exc:
        raise _doc_error(
            f"path tidak dapat dibaca: {exc}",
            code="CFG-ASSET-MISSING",
            path=path,
        ) from exc
    if not path.exists():
        raise _doc_error(
            "berkas dokumen tidak ditemukan",
            code="CFG-ASSET-MISSING",
            path=path,
        )
    if not path.is_file():
        raise _doc_error(
            "dokumen harus berupa berkas biasa",
            code="CFG-ASSET-MISSING",
            path=path,
        )
    if path.suffix.lower() not in {".md", ".markdown"}:
        raise _doc_error(
            "dokumen harus berekstensi .md atau .markdown",
            code="CFG-TYPE",
            path=path,
        )
    return path


def _split_front_matter(text: str, *, path: Path) -> tuple[str, str]:
    text = text.lstrip("\ufeff")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONT_MATTER_START:
        raise _doc_error(
            "front matter wajib dimulai dengan baris '---' di awal berkas",
            code="CFG-FRONT-MATTER",
            path=path,
        )
    for index in range(1, len(lines)):
        if lines[index].strip() in _FRONT_MATTER_END:
            front = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            return front, body
    raise _doc_error(
        "front matter belum ditutup dengan '---' atau '...'",
        code="CFG-FRONT-MATTER",
        path=path,
    )


def parse_document(document: str | Path) -> RawDocument:
    """Baca satu ``document.md`` dan pisahkan YAML front matter dari body."""

    path = _resolve_document_path(document)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _doc_error(
            f"berkas harus UTF-8: {exc}",
            code="CFG-YAML",
            path=path,
        ) from exc
    except OSError as exc:
        raise _doc_error(
            f"berkas tidak dapat dibaca: {exc}",
            code="CFG-ASSET-MISSING",
            path=path,
        ) from exc

    front_text, body = _split_front_matter(text, path=path)
    if not body.strip():
        raise _doc_error(
            "body Markdown kosong setelah front matter",
            code="CFG-REQUIRED",
            path=path,
            key="body",
        )

    try:
        front_matter = parse_yaml_mapping(
            front_text,
            source=path,
            label="front matter",
        )
    except ConfigError as exc:
        # Pertahankan kode/key ConfigError, tetapi bungkus sebagai DocumentError
        # agar pemanggil document.py punya satu tipe error.
        raise _doc_error(
            exc.message,
            code=exc.code,
            path=path,
            key=exc.key,
        ) from exc

    return RawDocument(
        path=path,
        front_matter=MappingProxyType(front_matter),
        body=body,
    )


def _check_front_matter_keys(front_matter: Mapping[str, Any], *, path: Path) -> None:
    for raw_key in front_matter:
        key = str(raw_key)
        if key in _DOCUMENT_KEYS:
            continue
        raise _doc_error(
            f"kunci '{key}' tidak dikenal di front matter",
            code="CFG-UNKNOWN-KEY",
            path=path,
            key=key,
        )


def _front_text(
    front_matter: Mapping[str, Any],
    key: str,
    *,
    path: Path,
    required: bool = False,
) -> str | None:
    value = front_matter.get(key)
    if value is None:
        if required:
            raise _doc_error(
                f"kunci '{key}' wajib diisi",
                code="CFG-REQUIRED",
                path=path,
                key=key,
            )
        return None
    if not isinstance(value, str):
        raise _doc_error(
            f"kunci '{key}' harus berupa teks",
            code="CFG-TYPE",
            path=path,
            key=key,
        )
    text = value.strip()
    if required and not text:
        raise _doc_error(
            f"kunci '{key}' tidak boleh kosong",
            code="CFG-REQUIRED",
            path=path,
            key=key,
        )
    return text or None


def _required_id(
    front_matter: Mapping[str, Any],
    key: str,
    *,
    path: Path,
    kind: str,
) -> str:
    value = _front_text(front_matter, key, path=path, required=True)
    assert value is not None
    return path_mod.validate_id(value, kind=kind)


def _plain_heading(text: str) -> str:
    text = _CLOSING_HASHES_RE.sub("", text)
    text = _INLINE_LINK_RE.sub(lambda match: match.group(1), text)
    text = _HTML_TAG_RE.sub("", text)
    text = _ESCAPE_RE.sub(r"\1", text)
    text = re.sub(r"[*_~`]", "", text)
    return " ".join(text.split())


def _validate_body(body: str, *, structure: Structure, path: Path) -> None:
    chapters = structure.body
    appendices = any(item.id == "appendices" for item in structure.back_matter)
    expected_index = 0
    current_level = 0
    lampiran_seen = False

    for line_number, line in enumerate(masked_lines(body), start=1):
        match = _HEADING_RE.match(line)
        if match is None:
            continue
        level = len(match.group("hashes"))
        text = _plain_heading(match.group("text"))
        if not text:
            continue

        if level == 1:
            if text.casefold() == "lampiran":
                if not appendices:
                    raise _doc_error(
                        "# Lampiran hanya boleh muncul jika back_matter memuat appendices",
                        code="CFG-BODY-ORDER",
                        path=path,
                        key=f"body:{line_number}",
                    )
                if lampiran_seen:
                    raise _doc_error(
                        "# Lampiran hanya boleh muncul sekali",
                        code="CFG-DUPLICATE",
                        path=path,
                        key=f"body:{line_number}",
                    )
                if expected_index != len(chapters):
                    raise _doc_error(
                        "# Lampiran harus berada setelah semua bab body",
                        code="CFG-BODY-ORDER",
                        path=path,
                        key=f"body:{line_number}",
                    )
                lampiran_seen = True
                current_level = 1
                continue

            if _NUMBERED_HEADING_RE.match(text):
                raise _doc_error(
                    f"Heading 1 '{text}' sudah bernomor; tulis tanpa nomor",
                    code="CFG-BODY-NUMBER",
                    path=path,
                    key=f"body:{line_number}",
                )
            if expected_index >= len(chapters):
                raise _doc_error(
                    f"Heading 1 '{text}' tidak ada di structure.body",
                    code="CFG-BODY-ORDER",
                    path=path,
                    key=f"body:{line_number}",
                )
            expected = chapters[expected_index]
            actual_normalized = " ".join(text.split()).casefold()
            expected_normalized = " ".join(expected.title.split()).casefold()
            if actual_normalized != expected_normalized:
                raise _doc_error(
                    f"Heading 1 '{text}' tidak cocok dengan urutan body; "
                    f"diharapkan '{expected.title}'",
                    code="CFG-BODY-ORDER",
                    path=path,
                    key=f"body:{line_number}",
                )
            expected_index += 1
            current_level = 1
        elif level == 2:
            if expected_index == 0 or current_level < 1:
                raise _doc_error(
                    f"Heading 2 '{text}' muncul sebelum Heading 1",
                    code="CFG-BODY-ORDER",
                    path=path,
                    key=f"body:{line_number}",
                )
            current_level = 2
        elif level == 3:
            if current_level < 2:
                raise _doc_error(
                    f"Heading 3 '{text}' muncul sebelum Heading 2",
                    code="CFG-BODY-ORDER",
                    path=path,
                    key=f"body:{line_number}",
                )
            current_level = 3
        # Heading 4-9 tidak diklasifikasikan dan tidak mengubah counter.

    if expected_index < len(chapters):
        missing = ", ".join(chapter.title for chapter in chapters[expected_index:])
        raise _doc_error(
            f"body belum memuat bab: {missing}",
            code="CFG-BODY-ORDER",
            path=path,
            key="body",
        )
    if appendices and not lampiran_seen:
        raise _doc_error(
            "back_matter memuat appendices, tetapi body tidak memiliki '# Lampiran'",
            code="CFG-BODY-ORDER",
            path=path,
            key="body",
        )


def _validate_structure_document_fields(
    front_matter: Mapping[str, Any],
    *,
    structure: Structure,
    path: Path,
) -> None:
    for item in structure.front_matter:
        if item.source != "document":
            continue
        value = front_matter.get(item.id)
        if not isinstance(value, str) or not value.strip():
            raise _doc_error(
                f"front matter '{item.id}' wajib diisi karena structure "
                f"'{structure.id}' mendeklarasikannya sebagai source: document",
                code="CFG-CONDITIONAL",
                path=path,
                key=item.id,
            )


def load_project(document: str | Path, *, root: Path | None = None) -> Project:
    """Muat dokumen, format, struktur, aset, dan validasi silang."""

    raw = parse_document(document)
    _check_front_matter_keys(raw.front_matter, path=raw.path)

    structure_id = _required_id(
        raw.front_matter,
        "structure",
        path=raw.path,
        kind="struktur",
    )
    format_id = _required_id(
        raw.front_matter,
        "format",
        path=raw.path,
        kind="format",
    )
    structure = load_structure(structure_id, root=root)
    format_ = load_format(format_id, root=root)
    if structure.format_id != format_id:
        # Pastikan format default struktur juga merupakan format yang valid,
        # meskipun dokumen memilih format lain.
        load_format(structure.format_id, root=root)

    metadata = normalize_metadata(raw.front_matter, source=raw.path)
    _validate_structure_document_fields(
        raw.front_matter,
        structure=structure,
        path=raw.path,
    )
    _validate_body(raw.body, structure=structure, path=raw.path)

    bibliography_value = raw.front_matter.get("bibliography")
    if bibliography_value is not None and not isinstance(bibliography_value, str):
        raise _doc_error(
            "kunci 'bibliography' harus berupa teks path relatif",
            code="CFG-TYPE",
            path=raw.path,
            key="bibliography",
        )

    assets = resolve_assets(
        raw.path,
        structure=structure,
        format=format_,
        bibliography=bibliography_value,
        body=raw.body,
    )

    warnings: list[str] = []
    override_warning = format_override_warning(format_id, structure)
    if override_warning is not None:
        warnings.append(override_warning)

    document_model = Document(
        path=raw.path,
        front_matter=raw.front_matter,
        body=raw.body,
        metadata=metadata,
        structure_id=structure_id,
        format_id=format_id,
        bibliography=bibliography_value
        or (format_.citation.bibliography if assets.bibliography is not None else None),
    )
    return Project(
        document=document_model,
        structure=structure,
        format=format_,
        assets=assets,
        warnings=tuple(warnings),
    )
