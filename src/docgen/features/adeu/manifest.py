"""Model dan validasi manifest Adeu.

Manifest adalah kontrak versi 1. Field ``built_at`` sudah dihapus agar manifest
byte-deterministik; manifest lama yang masih memuat ``built_at`` tetap dapat
dibaca dan field itu diabaikan. Setiap entri wajib memiliki ``text_sha256``
yang cocok dengan ``text`` saat dimuat maupun ditulis.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...errors import ManifestError

MANIFEST_VERSION = 1
DEFAULT_MANIFEST_DIR = ".laporan"
DEFAULT_MANIFEST_NAME = "manifest.json"

PARAGRAPH_ID_RE = re.compile(r"^p\d{4,}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

KIND_VALUES = frozenset(
    {
        "heading",
        "body",
        "table",
        "caption",
        "toc",
        "bibliography",
        "cover",
    }
)

_TOP_LEVEL_KEYS = frozenset({"version", "docx", "paragraphs", "built_at"})
_PARAGRAPH_KEYS = frozenset(
    {
        "id",
        "index",
        "kind",
        "heading_path",
        "text",
        "text_sha256",
        "protected",
        "protected_reason",
        "source_file",
        "source_line",
    }
)


def _fail(
    message: str,
    *,
    path: Path | None = None,
    key: str | None = None,
    code: str = "MANIFEST-SCHEMA",
) -> ManifestError:
    return ManifestError(message, code=code, path=path, key=key)


def sha256_text(text: str) -> str:
    """Hash SHA-256 heksadesimal huruf kecil dari teks UTF-8."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_manifest_path(document_path: str | Path) -> Path:
    """Path manifest default di samping dokumen: ``.laporan/manifest.json``."""

    return Path(document_path).parent / DEFAULT_MANIFEST_DIR / DEFAULT_MANIFEST_NAME


@dataclass(frozen=True)
class ManifestParagraph:
    """Satu paragraf body yang diproyeksikan ke Adeu."""

    id: str
    index: int
    kind: str
    heading_path: tuple[str, ...]
    text: str
    text_sha256: str
    protected: bool
    protected_reason: str | None = None
    source_file: str | None = None
    source_line: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.heading_path, tuple):
            object.__setattr__(self, "heading_path", tuple(self.heading_path))

    def to_dict(self, *, include_source: bool = True) -> dict[str, object]:
        entry: dict[str, object] = {
            "id": self.id,
            "index": self.index,
            "kind": self.kind,
            "heading_path": list(self.heading_path),
            "text": self.text,
            "text_sha256": self.text_sha256,
            "protected": self.protected,
            "protected_reason": self.protected_reason,
        }
        if include_source:
            entry["source_file"] = self.source_file
            entry["source_line"] = self.source_line
        return entry


@dataclass(frozen=True)
class Manifest:
    """Manifest Adeu yang sudah tervalidasi.

    ``include_source`` hanya mengatur serialisasi: bila source scan tidak
    dijalankan, kunci ``source_file``/``source_line`` tidak ditulis agar bentuk
    manifest tetap sama dengan kontrak dasar.
    """

    version: int
    docx: str
    paragraphs: tuple[ManifestParagraph, ...]
    include_source: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.paragraphs, tuple):
            object.__setattr__(self, "paragraphs", tuple(self.paragraphs))

    def to_dict(self) -> dict[str, object]:
        return manifest_to_dict(self)

    def __iter__(self) -> Iterator[ManifestParagraph]:
        return iter(self.paragraphs)

    def __len__(self) -> int:
        return len(self.paragraphs)

    def __getitem__(self, index: int) -> ManifestParagraph:
        return self.paragraphs[index]


def make_paragraph(
    *,
    id: str,
    index: int,
    kind: str,
    heading_path: tuple[str, ...],
    text: str,
    protected: bool,
    protected_reason: str | None = None,
    source_file: str | None = None,
    source_line: int | None = None,
) -> ManifestParagraph:
    """Bangun entri manifest sekaligus menghitung ``text_sha256``."""

    return ManifestParagraph(
        id=id,
        index=index,
        kind=kind,
        heading_path=tuple(heading_path),
        text=text,
        text_sha256=sha256_text(text),
        protected=protected,
        protected_reason=protected_reason,
        source_file=source_file,
        source_line=source_line,
    )


def _require_mapping(value: Any, *, path: Path | None, key: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail(f"{key} harus berupa objek JSON", path=path, key=key)
    return value


def _reject_unknown(
    data: Mapping[str, Any],
    allowed: frozenset[str],
    *,
    path: Path | None,
    key: str,
) -> None:
    for raw_key in data:
        child = str(raw_key)
        if child in allowed:
            continue
        raise _fail(
            f"kunci tidak dikenal: {child}",
            path=path,
            key=f"{key}.{child}" if key else child,
        )


def _parse_heading_path(
    value: Any,
    *,
    path: Path | None,
    where: str,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _fail(f"{where}.heading_path harus array string", path=path, key=f"{where}.heading_path")
    result: list[str] = []
    for position, item in enumerate(value):
        if not isinstance(item, str):
            raise _fail(
                f"{where}.heading_path[{position}] harus string",
                path=path,
                key=f"{where}.heading_path[{position}]",
            )
        if item.strip():
            result.append(item)
    return tuple(result)


def _parse_source_line(value: Any, *, path: Path | None, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _fail(
            f"{where}.source_line harus bilangan bulat >= 1 atau null",
            path=path,
            key=f"{where}.source_line",
        )
    return value


def _parse_paragraph(
    item: Any,
    *,
    position: int,
    path: Path | None,
    seen_ids: set[str],
    seen_indexes: set[int],
) -> ManifestParagraph:
    where = f"paragraphs[{position}]"
    data = _require_mapping(item, path=path, key=where)
    _reject_unknown(data, _PARAGRAPH_KEYS, path=path, key=where)

    paragraph_id = data.get("id")
    if not isinstance(paragraph_id, str) or PARAGRAPH_ID_RE.fullmatch(paragraph_id) is None:
        raise _fail(
            f"{where}.id harus berformat pNNNN, ditemukan {paragraph_id!r}",
            path=path,
            key=f"{where}.id",
        )
    if paragraph_id in seen_ids:
        raise _fail(
            f"id manifest duplikat: {paragraph_id}",
            path=path,
            key=f"{where}.id",
            code="MANIFEST-DUPLICATE",
        )
    seen_ids.add(paragraph_id)

    index = data.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise _fail(
            f"{where}.index harus bilangan bulat >= 0",
            path=path,
            key=f"{where}.index",
        )
    if index in seen_indexes:
        raise _fail(
            f"index manifest duplikat: {index}",
            path=path,
            key=f"{where}.index",
            code="MANIFEST-DUPLICATE",
        )
    seen_indexes.add(index)

    kind = data.get("kind")
    if not isinstance(kind, str) or kind not in KIND_VALUES:
        raise _fail(
            f"{where}.kind tidak dikenal: {kind!r}; pilihan: {', '.join(sorted(KIND_VALUES))}",
            path=path,
            key=f"{where}.kind",
        )

    heading_path = _parse_heading_path(
        data.get("heading_path", []), path=path, where=where
    )

    text = data.get("text")
    if not isinstance(text, str):
        raise _fail(f"{where}.text harus string", path=path, key=f"{where}.text")

    digest = data.get("text_sha256")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise _fail(
            f"{where}.text_sha256 harus 64 karakter heksadesimal huruf kecil",
            path=path,
            key=f"{where}.text_sha256",
        )
    actual = sha256_text(text)
    if actual != digest:
        raise _fail(
            f"{where}.text_sha256 tidak cocok dengan text "
            f"(diharapkan {actual}, ditemukan {digest})",
            path=path,
            key=f"{where}.text_sha256",
            code="MANIFEST-HASH",
        )

    protected = data.get("protected")
    if not isinstance(protected, bool):
        raise _fail(
            f"{where}.protected harus boolean",
            path=path,
            key=f"{where}.protected",
        )

    protected_reason = data.get("protected_reason")
    if protected_reason is not None and not isinstance(protected_reason, str):
        raise _fail(
            f"{where}.protected_reason harus string atau null",
            path=path,
            key=f"{where}.protected_reason",
        )
    if protected and not (protected_reason or "").strip():
        raise _fail(
            f"{where}.protected_reason wajib diisi untuk paragraf terlindungi",
            path=path,
            key=f"{where}.protected_reason",
            code="MANIFEST-PROTECTED",
        )
    if not protected and protected_reason is not None:
        raise _fail(
            f"{where}.protected_reason harus null bila protected=false",
            path=path,
            key=f"{where}.protected_reason",
            code="MANIFEST-PROTECTED",
        )

    source_file = data.get("source_file")
    if source_file is not None and not isinstance(source_file, str):
        raise _fail(
            f"{where}.source_file harus string atau null",
            path=path,
            key=f"{where}.source_file",
        )
    if source_file is not None and not source_file.strip():
        raise _fail(
            f"{where}.source_file tidak boleh kosong",
            path=path,
            key=f"{where}.source_file",
        )
    source_line = _parse_source_line(
        data.get("source_line"), path=path, where=where
    )
    if (source_file is None) != (source_line is None):
        raise _fail(
            f"{where}.source_file dan source_line harus diisi bersama atau null bersama",
            path=path,
            key=f"{where}.source_file",
            code="MANIFEST-SOURCE",
        )

    return ManifestParagraph(
        id=paragraph_id,
        index=index,
        kind=kind,
        heading_path=heading_path,
        text=text,
        text_sha256=digest,
        protected=protected,
        protected_reason=protected_reason,
        source_file=source_file,
        source_line=source_line,
    )


def manifest_from_dict(
    data: Any,
    *,
    path: str | Path | None = None,
) -> Manifest:
    """Validasi mapping JSON mentah menjadi ``Manifest``."""

    source = Path(path) if path is not None else None
    root = _require_mapping(data, path=source, key="manifest")
    _reject_unknown(root, _TOP_LEVEL_KEYS, path=source, key="manifest")

    version = root.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise _fail("manifest.version harus bilangan bulat", path=source, key="version")
    if version != MANIFEST_VERSION:
        raise _fail(
            f"versi manifest tidak didukung: {version!r} (diharapkan {MANIFEST_VERSION})",
            path=source,
            key="version",
            code="MANIFEST-VERSION",
        )

    docx = root.get("docx")
    if not isinstance(docx, str) or not docx.strip():
        raise _fail("manifest.docx harus teks tidak kosong", path=source, key="docx")
    if Path(docx).name != docx or "/" in docx or "\\" in docx:
        raise _fail(
            "manifest.docx harus berupa nama berkas, bukan path",
            path=source,
            key="docx",
            code="MANIFEST-DOCX",
        )

    raw_paragraphs = root.get("paragraphs")
    if not isinstance(raw_paragraphs, list):
        raise _fail("manifest.paragraphs harus array", path=source, key="paragraphs")

    paragraphs: list[ManifestParagraph] = []
    seen_ids: set[str] = set()
    seen_indexes: set[int] = set()
    for position, item in enumerate(raw_paragraphs):
        paragraphs.append(
            _parse_paragraph(
                item,
                position=position,
                path=source,
                seen_ids=seen_ids,
                seen_indexes=seen_indexes,
            )
        )

    include_source = any(
        isinstance(item, Mapping)
        and ("source_file" in item or "source_line" in item)
        for item in raw_paragraphs
    )
    paragraphs.sort(key=lambda paragraph: (paragraph.index, paragraph.id))
    return Manifest(
        version=version,
        docx=docx,
        paragraphs=tuple(paragraphs),
        include_source=include_source,
    )


def validate_manifest(manifest: Manifest, *, path: str | Path | None = None) -> None:
    """Validasi ulang objek ``Manifest`` sebelum ditulis."""

    source = Path(path) if path is not None else None
    if not isinstance(manifest, Manifest):
        raise _fail("objek manifest tidak valid", path=source)
    rebuilt = manifest_from_dict(manifest_to_dict(manifest), path=source)
    if rebuilt != manifest:
        raise _fail(
            "manifest berubah saat validasi; periksa urutan dan hash paragraf",
            path=source,
            code="MANIFEST-UNSTABLE",
        )


def manifest_to_dict(manifest: Manifest) -> dict[str, object]:
    """Serialisasi manifest tanpa timestamp dan dengan urutan field stabil."""

    return {
        "version": manifest.version,
        "docx": manifest.docx,
        "paragraphs": [
            paragraph.to_dict(include_source=manifest.include_source)
            for paragraph in manifest.paragraphs
        ],
    }


def load_manifest(path: str | Path) -> Manifest:
    """Baca manifest, validasi skema, dan verifikasi setiap ``text_sha256``."""

    source = Path(path)
    try:
        payload = source.read_bytes()
    except FileNotFoundError as exc:
        raise _fail(
            f"manifest tidak ditemukan: {source}",
            path=source,
            code="MANIFEST-MISSING",
        ) from exc
    except OSError as exc:
        raise _fail(
            f"manifest tidak dapat dibaca: {exc}",
            path=source,
            code="MANIFEST-IO",
        ) from exc

    try:
        data = json.loads(payload.decode("utf-8-sig"))
    except UnicodeError as exc:
        raise _fail(
            f"manifest bukan UTF-8 valid: {exc}",
            path=source,
            key="manifest",
            code="MANIFEST-ENCODING",
        ) from exc
    except json.JSONDecodeError as exc:
        raise _fail(
            f"manifest bukan JSON valid: baris {exc.lineno}: {exc.msg}",
            path=source,
            key="manifest",
            code="MANIFEST-JSON",
        ) from exc

    return manifest_from_dict(data, path=source)


def _serialize(manifest: Manifest) -> bytes:
    validate_manifest(manifest)
    text = json.dumps(
        manifest_to_dict(manifest),
        ensure_ascii=False,
        indent=2,
        sort_keys=False,
    )
    return (text + "\n").encode("utf-8")


def dump_manifest(manifest: Manifest, path: str | Path) -> Path:
    """Tulis manifest secara atomic, deterministik, dan tanpa timestamp."""

    destination = Path(path)
    payload = _serialize(manifest)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
            os.replace(temp_name, destination)
        except BaseException:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise _fail(
            f"manifest tidak dapat ditulis: {exc}",
            path=destination,
            code="MANIFEST-WRITE",
        ) from exc
    return destination


__all__ = [
    "DEFAULT_MANIFEST_DIR",
    "DEFAULT_MANIFEST_NAME",
    "KIND_VALUES",
    "MANIFEST_VERSION",
    "PARAGRAPH_ID_RE",
    "Manifest",
    "ManifestParagraph",
    "default_manifest_path",
    "dump_manifest",
    "load_manifest",
    "make_paragraph",
    "manifest_from_dict",
    "manifest_to_dict",
    "sha256_text",
    "validate_manifest",
]
