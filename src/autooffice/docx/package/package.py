"""Model package DOCX/OPC: satu load, satu save.

``DocumentPackage`` adalah satu-satunya pemilik ZIP. Stage memutasi part di
memori dan hanya pipeline yang memanggil ``load()``/``save()``.

Referensi: https://ecma-international.org/publications-and-standards/standards/ecma-376/
"""

import copy
import posixpath
import re
import time
import urllib.parse
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from . import (
    DocxError,
    InvalidPackageError,
    PackageError,
    PartExistsError,
    PartNotFoundError,
    SaveError,
    XmlError,
)
from .io import ZipEntry, read_zip, write_zip, write_zip_atomic
from .names import (
    CT_DEFAULT,
    CT_OVERRIDE,
    CT_TYPES,
    PKG_REL_NS,
    PR_RELATIONSHIP,
    PR_RELATIONSHIPS,
    W_DOCUMENT,
)
from .xml import parse_xml, serialize_xml, sha256_c14n

CONTENT_TYPES_PART = "[Content_Types].xml"
PACKAGE_RELS_PART = "_rels/.rels"
DOCUMENT_PART = "word/document.xml"

RELATIONSHIPS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"
MAIN_DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)

REL_TYPE_OFFICE_DOCUMENT = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)
REL_TYPE_STYLES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
REL_TYPE_HEADER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
REL_TYPE_FOOTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"
REL_TYPE_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
REL_TYPE_HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"

_DEFAULT_COMPRESSION = zipfile.ZIP_DEFLATED
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class PartInfo:
    """Metadata satu part tanpa payload."""

    name: str
    size: int
    content_type: str | None


@dataclass(frozen=True)
class Relationship:
    """Satu relationship OPC."""

    rel_id: str
    rel_type: str
    target: str
    target_mode: str | None = None


class DocumentPackage:
    """Package DOCX di memori dengan invariant satu load/satu save."""

    def __init__(self, entries: Sequence[ZipEntry]) -> None:
        self._entries: dict[str, ZipEntry] = {}
        for entry in entries:
            if entry.name in self._entries:
                raise PackageError(f"Part duplikat: {entry.name}")
            self._entries[entry.name] = entry
        self._xml: dict[str, etree._Element] = {}
        self._original_hash: dict[str, str] = {}
        self._dirty: set[str] = set()

    # ------------------------------------------------------------------
    # Load/save
    # ------------------------------------------------------------------

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        validate: bool = True,
    ) -> DocumentPackage:
        """Muat DOCX; file sumber tidak diubah."""

        package = cls(read_zip(path))
        if validate:
            package.validate()
        return package

    def save(self, path: str | Path, *, atomic: bool = True) -> None:
        """Validasi lalu tulis package ke ``path``."""

        self.validate()
        materialized = self._materialize()
        if atomic:
            write_zip_atomic(
                path,
                materialized,
                compression=_DEFAULT_COMPRESSION,
            )
        else:
            write_zip(path, materialized, compression=_DEFAULT_COMPRESSION)
        self._after_save(materialized)

    def _materialize(self) -> list[ZipEntry]:
        entries: list[ZipEntry] = []
        for name, entry in self._entries.items():
            if name.endswith("/"):
                entries.append(entry)
                continue
            entries.append(
                ZipEntry(
                    name=name,
                    data=self._payload(name),
                    info=copy.copy(entry.info),
                )
            )
        return entries

    def _after_save(self, entries: Sequence[ZipEntry]) -> None:
        for entry in entries:
            self._entries[entry.name] = entry
        self._dirty.clear()
        for name in self._xml:
            stored = self._entries.get(name)
            if stored is not None:
                self._original_hash[name] = sha256_c14n(stored.data)

    # ------------------------------------------------------------------
    # Part
    # ------------------------------------------------------------------

    def part(self, name: str) -> bytes:
        """Payload part tanpa mengubah package."""

        self._require_part(name)
        return self._payload(name)

    def xml(self, name: str) -> etree._Element:
        """Parse part XML dan kembalikan elemen hidup."""

        self._require_part(name)
        cached = self._xml.get(name)
        if cached is not None:
            return cached
        data = self._entries[name].data
        root = parse_xml(data)
        self._xml[name] = root
        self._original_hash[name] = sha256_c14n(data)
        return root

    def set_part(
        self,
        name: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        """Ganti payload part; part baru ditambahkan di akhir ZIP."""

        _validate_part_name(name)
        payload = bytes(data)
        existing = self._entries.get(name)
        if existing is None:
            info = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
            info.compress_type = _DEFAULT_COMPRESSION
            info.external_attr = 0o644 << 16
            info.create_system = 3
        else:
            info = existing.info
        self._entries[name] = ZipEntry(name, payload, info)
        self._xml.pop(name, None)
        self._original_hash.pop(name, None)
        self._dirty.discard(name)
        if content_type is not None and name != CONTENT_TYPES_PART:
            self.ensure_content_type(name, content_type)

    def set_xml(self, name: str, root: etree._Element) -> None:
        """Simpan elemen XML sebagai payload part."""

        self._require_part(name)
        if isinstance(root, etree._ElementTree):
            root = root.getroot()
        if not isinstance(root, etree._Element):
            raise XmlError("set_xml membutuhkan elemen XML")
        self._xml[name] = root
        self._dirty.add(name)

    def has_part(self, name: str) -> bool:
        return name in self._entries and not name.endswith("/")

    def remove_part(self, name: str) -> None:
        """Hapus part beserta content type, relasi, dan rels miliknya."""

        self._require_part(name)

        if name == CONTENT_TYPES_PART:
            self._drop_raw(name)
            return

        self._drop_raw(name)
        self._remove_content_type_override(name)
        self._remove_relationships_to(name)

        own_rels = self._rels_name(name)
        if own_rels != PACKAGE_RELS_PART and self.has_part(own_rels):
            self._drop_raw(own_rels)
            self._remove_content_type_override(own_rels)

    def part_names(self) -> tuple[str, ...]:
        return tuple(name for name in self._entries if not name.endswith("/"))

    def part_info(self, name: str) -> PartInfo:
        payload = self.part(name)
        return PartInfo(
            name=name,
            size=len(payload),
            content_type=self._content_type(name),
        )

    # ------------------------------------------------------------------
    # Content types
    # ------------------------------------------------------------------

    def ensure_content_type(self, part: str, content_type: str) -> None:
        """Pastikan part memiliki content type yang diminta."""

        _validate_part_name(part)
        if part == CONTENT_TYPES_PART:
            raise PackageError(f"{CONTENT_TYPES_PART} tidak memiliki content type")
        if not isinstance(content_type, str) or not content_type.strip():
            raise PackageError(f"Content type kosong untuk part: {part}")
        root = self._content_types_root()
        override = self._find_override(root, part)
        if override is not None:
            if override.get("ContentType") != content_type:
                override.set("ContentType", content_type)
                self.set_xml(CONTENT_TYPES_PART, root)
            return

        defaults, _ = self._content_type_maps(root)
        extension = _part_extension(part)
        if extension and defaults.get(extension) == content_type:
            return

        node = etree.SubElement(root, CT_OVERRIDE)
        node.set("PartName", f"/{part}")
        node.set("ContentType", content_type)
        self.set_xml(CONTENT_TYPES_PART, root)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    def relationships(self, source: str) -> tuple[Relationship, ...]:
        """Kembalikan relationship milik ``source``."""

        rels_name = self._rels_name(source)
        if not self.has_part(rels_name):
            return ()
        return self._read_relationships(rels_name)

    def add_relationship(self, source: str, rel: Relationship) -> None:
        """Tambah relationship ke part ``source``."""

        if not rel.rel_id:
            raise PackageError("Relationship Id tidak boleh kosong")
        if not rel.rel_type:
            raise PackageError(f"Relationship Type kosong untuk {rel.rel_id}")
        if not rel.target:
            raise PackageError(f"Relationship Target kosong untuk {rel.rel_id}")
        if rel.target_mode is not None and rel.target_mode != "External":
            raise PackageError(f"TargetMode tidak dikenal: {rel.target_mode!r}")

        rels_name = self._rels_name(source)
        source_part = self._source_part_for(source)
        if source_part and not self.has_part(source_part):
            raise PartNotFoundError(f"Source relationship tidak ditemukan: {source_part}")

        if not self.has_part(rels_name):
            root = etree.Element(
                PR_RELATIONSHIPS,
                nsmap={None: PKG_REL_NS},
            )
            self.set_part(
                rels_name,
                serialize_xml(root),
                content_type=RELATIONSHIPS_CONTENT_TYPE,
            )
        else:
            root = self.xml(rels_name)

        if root.tag != PR_RELATIONSHIPS:
            raise InvalidPackageError(f"Root rels tidak valid: {rels_name}")

        for child in root:
            if (
                isinstance(child.tag, str)
                and child.tag == PR_RELATIONSHIP
                and child.get("Id") == rel.rel_id
            ):
                raise PartExistsError(f"Relationship Id sudah ada di {rels_name}: {rel.rel_id}")

        if rel.target_mode != "External":
            target = self._resolve_target(source_part, rel.target)
            if not self.has_part(target):
                raise PartNotFoundError(f"Target relationship tidak ditemukan: {target}")

        child = etree.SubElement(root, PR_RELATIONSHIP)
        child.set("Id", rel.rel_id)
        child.set("Type", rel.rel_type)
        child.set("Target", rel.target)
        if rel.target_mode is not None:
            child.set("TargetMode", rel.target_mode)
        self.set_xml(rels_name, root)

    def remove_relationship(self, source: str, rel_id: str) -> None:
        """Hapus relationship dengan Id ``rel_id``."""

        rels_name = self._rels_name(source)
        if not self.has_part(rels_name):
            raise PartNotFoundError(f"Part rels tidak ditemukan: {rels_name}")
        root = self.xml(rels_name)
        if root.tag != PR_RELATIONSHIPS:
            raise InvalidPackageError(f"Root rels tidak valid: {rels_name}")
        for child in root:
            if (
                isinstance(child.tag, str)
                and child.tag == PR_RELATIONSHIP
                and child.get("Id") == rel_id
            ):
                root.remove(child)
                self.set_xml(rels_name, root)
                return
        raise PartNotFoundError(f"Relationship tidak ditemukan di {rels_name}: {rel_id}")

    # ------------------------------------------------------------------
    # Validasi OPC
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Validasi struktur OPC; tidak menulis apa pun."""

        for name in self._entries:
            if name.endswith("/"):
                try:
                    _validate_part_name(name, allow_directory=True)
                except PackageError as exc:
                    raise InvalidPackageError(str(exc)) from exc
            else:
                try:
                    _validate_part_name(name)
                except PackageError as exc:
                    raise InvalidPackageError(str(exc)) from exc

        for required in (
            CONTENT_TYPES_PART,
            PACKAGE_RELS_PART,
            DOCUMENT_PART,
        ):
            if not self.has_part(required):
                raise InvalidPackageError(f"Part wajib hilang: {required}")

        try:
            content_types = self._content_types_root()
            defaults, overrides = self._content_type_maps(content_types)
        except XmlError as exc:
            raise InvalidPackageError(f"{CONTENT_TYPES_PART} tidak valid: {exc}") from exc
        except PackageError as exc:
            raise InvalidPackageError(str(exc)) from exc

        part_names_by_case = {name.casefold(): name for name in self.part_names()}
        for key in overrides:
            if key not in part_names_by_case:
                raise InvalidPackageError(f"Override content type untuk part yang hilang: {key}")

        for name in self.part_names():
            if name == CONTENT_TYPES_PART:
                continue
            content_type = overrides.get(name.casefold())
            if content_type is None:
                extension = _part_extension(name)
                content_type = defaults.get(extension) if extension else None
            if not content_type:
                raise InvalidPackageError(f"Content type tidak ditemukan untuk part: {name}")

        for name in self.part_names():
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            try:
                parse_xml(self.part(name))
            except XmlError as exc:
                raise InvalidPackageError(f"Part XML tidak valid: {name}: {exc}") from exc

        try:
            document = parse_xml(self.part(DOCUMENT_PART))
        except XmlError as exc:
            raise InvalidPackageError(f"{DOCUMENT_PART} tidak valid: {exc}") from exc
        if document.tag != W_DOCUMENT:
            raise InvalidPackageError(f"Root {DOCUMENT_PART} bukan w:document")

        for rels_name in self.part_names():
            if not rels_name.endswith(".rels"):
                continue
            try:
                relationships = self._read_relationships(rels_name)
            except XmlError as exc:
                raise InvalidPackageError(f"Part rels tidak valid: {rels_name}: {exc}") from exc
            source = self._source_for_rels(rels_name)
            if source and not self.has_part(source):
                raise InvalidPackageError(f"Rels yatim tanpa source part: {rels_name}")
            seen_ids: set[str] = set()
            for rel in relationships:
                if rel.rel_id in seen_ids:
                    raise InvalidPackageError(
                        f"Relationship Id duplikat di {rels_name}: {rel.rel_id}"
                    )
                seen_ids.add(rel.rel_id)
                if rel.target_mode is not None and rel.target_mode != "External":
                    raise InvalidPackageError(
                        f"TargetMode tidak dikenal di {rels_name}: {rel.target_mode!r}"
                    )
                if rel.target_mode == "External":
                    continue
                target = self._resolve_target(source, rel.target)
                if not self.has_part(target):
                    raise InvalidPackageError(
                        f"Target relationship tidak ditemukan: {rels_name} -> {target}"
                    )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_part(self, name: str) -> None:
        if not self.has_part(name):
            raise PartNotFoundError(f"Part tidak ditemukan: {name}")

    def _payload(self, name: str) -> bytes:
        entry = self._entries[name]
        root = self._xml.get(name)
        if root is None:
            return entry.data
        serialized = serialize_xml(root)
        if name in self._dirty:
            return serialized
        baseline = self._original_hash.get(name)
        if baseline is None:
            baseline = sha256_c14n(entry.data)
            self._original_hash[name] = baseline
        if sha256_c14n(serialized) == baseline:
            return entry.data
        return serialized

    def _drop_raw(self, name: str) -> None:
        self._entries.pop(name, None)
        self._xml.pop(name, None)
        self._original_hash.pop(name, None)
        self._dirty.discard(name)

    def _content_types_root(self) -> etree._Element:
        if not self.has_part(CONTENT_TYPES_PART):
            raise InvalidPackageError(f"Part wajib hilang: {CONTENT_TYPES_PART}")
        root = self.xml(CONTENT_TYPES_PART)
        if root.tag != CT_TYPES:
            raise InvalidPackageError(f"Root {CONTENT_TYPES_PART} bukan Types")
        return root

    def _content_type_maps(
        self,
        root: etree._Element,
    ) -> tuple[dict[str, str], dict[str, str]]:
        defaults: dict[str, str] = {}
        overrides: dict[str, str] = {}
        for child in root:
            if not isinstance(child.tag, str):
                continue
            if child.tag == CT_DEFAULT:
                extension = (child.get("Extension") or "").casefold()
                content_type = child.get("ContentType") or ""
                if not extension or not content_type:
                    raise InvalidPackageError("Default content type tidak lengkap")
                if extension in defaults:
                    raise InvalidPackageError(f"Default content type duplikat: {extension}")
                defaults[extension] = content_type
            elif child.tag == CT_OVERRIDE:
                part_name = child.get("PartName") or ""
                content_type = child.get("ContentType") or ""
                if not part_name.startswith("/") or not content_type:
                    raise InvalidPackageError(f"Override content type tidak lengkap: {part_name!r}")
                part = part_name[1:]
                _validate_part_name(part)
                key = part.casefold()
                if key in overrides:
                    raise InvalidPackageError(f"Override content type duplikat: {part}")
                overrides[key] = content_type
            else:
                raise InvalidPackageError(f"Elemen content types tidak dikenal: {child.tag}")
        return defaults, overrides

    def _content_type(self, name: str) -> str | None:
        if not self.has_part(CONTENT_TYPES_PART):
            return None
        root = self._content_types_root()
        defaults, overrides = self._content_type_maps(root)
        content_type = overrides.get(name.casefold())
        if content_type is not None:
            return content_type
        extension = _part_extension(name)
        return defaults.get(extension) if extension else None

    def _find_override(
        self,
        root: etree._Element,
        part: str,
    ) -> etree._Element | None:
        target = part.casefold()
        for child in root:
            if not isinstance(child.tag, str) or child.tag != CT_OVERRIDE:
                continue
            name = (child.get("PartName") or "").lstrip("/")
            if name.casefold() == target:
                return child
        return None

    def _remove_content_type_override(self, part: str) -> None:
        if not self.has_part(CONTENT_TYPES_PART):
            return
        root = self._content_types_root()
        override = self._find_override(root, part)
        if override is not None:
            root.remove(override)
            self.set_xml(CONTENT_TYPES_PART, root)

    def _read_relationships(
        self,
        rels_name: str,
    ) -> tuple[Relationship, ...]:
        root = self.xml(rels_name)
        if root.tag != PR_RELATIONSHIPS:
            raise InvalidPackageError(f"Root rels tidak valid: {rels_name}")
        result: list[Relationship] = []
        seen: set[str] = set()
        for child in root:
            if not isinstance(child.tag, str):
                continue
            if child.tag != PR_RELATIONSHIP:
                raise InvalidPackageError(f"Elemen rels tidak dikenal di {rels_name}: {child.tag}")
            rel_id = child.get("Id") or ""
            rel_type = child.get("Type") or ""
            target = child.get("Target")
            if not rel_id or not rel_type or not target:
                raise InvalidPackageError(f"Relationship tidak lengkap di {rels_name}")
            if rel_id in seen:
                raise InvalidPackageError(f"Relationship Id duplikat di {rels_name}: {rel_id}")
            seen.add(rel_id)
            result.append(
                Relationship(
                    rel_id=rel_id,
                    rel_type=rel_type,
                    target=target,
                    target_mode=child.get("TargetMode"),
                )
            )
        return tuple(result)

    def _remove_relationships_to(self, part: str) -> None:
        target = part.casefold()
        for rels_name in [name for name in self.part_names() if name.endswith(".rels")]:
            if not self.has_part(rels_name):
                continue
            source = self._source_for_rels(rels_name)
            root = self.xml(rels_name)
            if root.tag != PR_RELATIONSHIPS:
                continue
            changed = False
            for child in list(root):
                if not isinstance(child.tag, str) or child.tag != PR_RELATIONSHIP:
                    continue
                if child.get("TargetMode") == "External":
                    continue
                target_value = child.get("Target") or ""
                if not target_value:
                    continue
                try:
                    resolved = self._resolve_target(source, target_value)
                except InvalidPackageError:
                    continue
                if resolved.casefold() == target:
                    root.remove(child)
                    changed = True
            if changed:
                self.set_xml(rels_name, root)

    def _rels_name(self, source: str) -> str:
        if source in ("", PACKAGE_RELS_PART):
            return PACKAGE_RELS_PART
        if source.endswith(".rels") and (
            source == PACKAGE_RELS_PART or "/_rels/" in source or source.startswith("_rels/")
        ):
            return source
        directory, filename = posixpath.split(source)
        if directory:
            return posixpath.join(directory, "_rels", f"{filename}.rels")
        return f"_rels/{filename}.rels"

    def _source_part_for(self, source: str) -> str:
        if source in ("", PACKAGE_RELS_PART):
            return ""
        if source.endswith(".rels") and (
            source == PACKAGE_RELS_PART or "/_rels/" in source or source.startswith("_rels/")
        ):
            return self._source_for_rels(source)
        return source

    def _source_for_rels(self, rels_name: str) -> str:
        if rels_name == PACKAGE_RELS_PART:
            return ""
        directory, filename = posixpath.split(rels_name)
        if posixpath.basename(directory) != "_rels":
            raise InvalidPackageError(f"Path rels tidak valid: {rels_name}")
        if not filename.endswith(".rels") or filename == ".rels":
            raise InvalidPackageError(f"Nama rels tidak valid: {rels_name}")
        source_name = filename[:-5]
        parent = posixpath.dirname(directory)
        return posixpath.join(parent, source_name) if parent else source_name

    def _resolve_target(self, source: str, target: str) -> str:
        if not isinstance(target, str) or not target:
            raise InvalidPackageError("Target relationship kosong")
        if "\\" in target:
            raise InvalidPackageError(f"Target relationship memakai backslash: {target}")
        raw = target.split("#", 1)[0].split("?", 1)[0]
        raw = urllib.parse.unquote(raw)
        if not raw:
            raise InvalidPackageError(f"Target relationship kosong setelah fragment: {target}")
        if raw.startswith("/"):
            resolved = posixpath.normpath(raw[1:])
        else:
            base = posixpath.dirname(source) if source else ""
            resolved = posixpath.normpath(posixpath.join(base, raw))
        if resolved in ("", ".", "..") or resolved.startswith("../") or resolved.startswith("/"):
            raise InvalidPackageError(f"Target relationship keluar package: {target}")
        _validate_part_name(resolved)
        return resolved


# Nama singkat yang diminta sebagian pemanggil; kontrak memakai DocumentPackage.
DocxPackage = DocumentPackage


def _part_extension(name: str) -> str:
    basename = posixpath.basename(name)
    if "." not in basename:
        return ""
    return basename.rsplit(".", 1)[1].casefold()


def _validate_part_name(
    name: str,
    *,
    allow_directory: bool = False,
) -> None:
    if not isinstance(name, str) or not name:
        raise PackageError("Nama part tidak boleh kosong")
    candidate = name
    if name.endswith("/"):
        if not allow_directory:
            raise PackageError(f"Nama part tidak boleh berakhir dengan '/': {name}")
        candidate = name[:-1]
    if not candidate:
        raise PackageError(f"Nama part tidak valid: {name!r}")
    if candidate.startswith("/") or "\\" in candidate or _DRIVE_RE.match(candidate):
        raise PackageError(f"Nama part absolut tidak valid: {name}")
    segments = candidate.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise PackageError(f"Nama part tidak valid: {name}")
    if name.endswith("/") and allow_directory:
        return


__all__ = [
    "CONTENT_TYPES_PART",
    "DOCUMENT_PART",
    "MAIN_DOCUMENT_CONTENT_TYPE",
    "PACKAGE_RELS_PART",
    "RELATIONSHIPS_CONTENT_TYPE",
    "REL_TYPE_FOOTER",
    "REL_TYPE_HEADER",
    "REL_TYPE_HYPERLINK",
    "REL_TYPE_IMAGE",
    "REL_TYPE_OFFICE_DOCUMENT",
    "REL_TYPE_STYLES",
    "DocumentPackage",
    "DocxError",
    "DocxPackage",
    "InvalidPackageError",
    "PackageError",
    "PartExistsError",
    "PartInfo",
    "PartNotFoundError",
    "Relationship",
    "SaveError",
    "XmlError",
]
