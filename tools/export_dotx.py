"""Ekspor DOCX menjadi DOTX (template Microsoft Word).

Perbedaan utama keduanya hanya pada content type part utama: DOCX memakai
``...wordprocessingml.document.main+xml``, sedangkan DOTX memakai
``...wordprocessingml.template.main+xml``.

Alat ini menyalin seluruh isi ZIP apa adanya, lalu hanya mengganti nilai
``ContentType`` pada Override ``/word/document.xml`` di
``[Content_Types].xml``. Part lain tidak diubah. Stempel waktu ZIP dibuat
tetap agar hasilnya deterministik dan konversi ulang menghasilkan byte yang
sama.

Pemakaian:

    python tools/export_dotx.py --in Laporan.docx --out template.dotx

Hasil ditulis ke file sementara, divalidasi, baru dipindahkan ke ``--out``
sehingga output lama tidak rusak bila konversi gagal.
"""

from __future__ import annotations

import argparse
import codecs
import copy
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

CONTENT_TYPES_PART = "[Content_Types].xml"
DOCUMENT_PART = "word/document.xml"

DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document.main+xml"
)
TEMPLATE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.template.main+xml"
)

# ZIP tidak mendukung tanggal sebelum 1980. Nilai tetap ini membuat hasil
# ekspor reproducible dan idempoten (byte sama saat dikonversi ulang).
FIXED_ZIP_DATETIME = (1980, 1, 1, 0, 0, 0)

_OVERRIDE_TAG_RE = re.compile(
    r"<(?P<prefix>(?:[A-Za-z_][\w.-]*:)?)Override\b"
    r"(?P<attrs>[^<>]*?)(?P<self_close>/?)>",
    re.DOTALL,
)
_ATTRIBUTE_RE = re.compile(
    r"(?P<name>[A-Za-z_][\w.:-]*)\s*=\s*"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.DOTALL,
)


class ExportDotxError(RuntimeError):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


@dataclass(frozen=True)
class ExportReport:
    """Ringkasan hasil ekspor."""

    parts: int
    document_bytes: int
    content_type_changed: bool


@dataclass(frozen=True)
class _ValidationReport:
    parts: int
    document_bytes: int


def _local_name(name: str) -> str:
    """Ambil nama lokal dari nama XML ber-namespace."""

    return name.rsplit("}", 1)[-1]


def _get_attribute(element: ElementTree.Element, local_name: str) -> str | None:
    """Ambil atribut berdasarkan nama lokal (namespace diabaikan)."""

    wanted = local_name.lower()
    for name, value in element.attrib.items():
        if _local_name(name).lower() == wanted:
            return value
    return None


def _document_override(data: bytes) -> ElementTree.Element:
    """Kembalikan elemen Override untuk ``/word/document.xml``.

    Tepat satu Override harus ada. XML yang tidak valid atau jumlahnya tidak
    sesuai dianggap sebagai input yang tidak bisa dikonversi.
    """

    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ExportDotxError(
            "[Content_Types].xml bukan XML yang valid"
        ) from exc

    overrides = [
        element
        for element in root.iter()
        if isinstance(element.tag, str)
        and _local_name(element.tag) == "Override"
        and (_get_attribute(element, "PartName") or "").lower()
        == "/word/document.xml"
    ]
    if not overrides:
        raise ExportDotxError(
            "Override part /word/document.xml tidak ditemukan di "
            "[Content_Types].xml"
        )
    if len(overrides) > 1:
        raise ExportDotxError(
            "Override part /word/document.xml ditemukan lebih dari sekali"
        )
    return overrides[0]


def _document_content_type(data: bytes) -> str:
    """Baca dan validasi content type part dokumen."""

    element = _document_override(data)
    value = _get_attribute(element, "ContentType")
    if not value:
        raise ExportDotxError(
            "Override /word/document.xml tidak memiliki atribut ContentType"
        )
    return value


def _decode_xml(data: bytes) -> tuple[str, str, bytes]:
    """Decode XML dengan mempertahankan BOM dan encoding aslinya."""

    if data.startswith(codecs.BOM_UTF8):
        return (
            data[len(codecs.BOM_UTF8) :].decode("utf-8"),
            "utf-8",
            codecs.BOM_UTF8,
        )
    if data.startswith(codecs.BOM_UTF16_LE):
        return data[2:].decode("utf-16-le"), "utf-16-le", codecs.BOM_UTF16_LE
    if data.startswith(codecs.BOM_UTF16_BE):
        return data[2:].decode("utf-16-be"), "utf-16-be", codecs.BOM_UTF16_BE
    return data.decode("utf-8"), "utf-8", b""


def _patch_content_types(data: bytes) -> bytes:
    """Ganti hanya nilai ContentType pada Override dokumen.

    Pendekatan berbasis teks dipakai agar byte lain di ``[Content_Types].xml``
    tidak berubah (deklarasi XML, urutan atribut, kutip, spasi, dan newline
    tetap dipertahankan).
    """

    try:
        text, encoding, bom = _decode_xml(data)
    except UnicodeDecodeError as exc:
        raise ExportDotxError(
            "[Content_Types].xml tidak dapat dibaca sebagai UTF-8/UTF-16"
        ) from exc

    edits: list[tuple[int, int]] = []
    for tag in _OVERRIDE_TAG_RE.finditer(text):
        attrs_text = tag.group("attrs")
        attrs_offset = tag.start("attrs")
        attributes = {
            match.group("name").rsplit(":", 1)[-1].lower(): match
            for match in _ATTRIBUTE_RE.finditer(attrs_text)
        }

        part_name = attributes.get("partname")
        if (
            part_name is None
            or part_name.group("value").lower() != "/word/document.xml"
        ):
            continue

        content_type = attributes.get("contenttype")
        if content_type is None:
            raise ExportDotxError(
                "Override /word/document.xml tidak memiliki atribut "
                "ContentType"
            )
        if content_type.group("value") != TEMPLATE_CONTENT_TYPE:
            edits.append(
                (
                    attrs_offset + content_type.start("value"),
                    attrs_offset + content_type.end("value"),
                )
            )

    if len(edits) != 1:
        raise ExportDotxError(
            "Override /word/document.xml tidak dapat diganti dengan aman"
        )

    start, end = edits[0]
    patched = text[:start] + TEMPLATE_CONTENT_TYPE + text[end:]
    return bom + patched.encode(encoding)


def _convert_content_types(data: bytes) -> bytes:
    """Ubah content type dokumen menjadi template, atau biarkan bila sudah."""

    current = _document_content_type(data)
    if current == TEMPLATE_CONTENT_TYPE:
        return data
    if current != DOCUMENT_CONTENT_TYPE:
        raise ExportDotxError(
            "Content type /word/document.xml tidak didukung: "
            f"{current!r}. Hanya DOCX biasa yang bisa dijadikan DOTX."
        )
    return _patch_content_types(data)


def _single_part(
    infos: list[zipfile.ZipInfo], name: str
) -> zipfile.ZipInfo:
    """Pastikan sebuah part wajib ada tepat satu kali."""

    matches = [info for info in infos if info.filename == name]
    if not matches:
        raise ExportDotxError(f"Part wajib tidak ditemukan: {name}")
    if len(matches) > 1:
        raise ExportDotxError(f"Part ditemukan lebih dari sekali: {name}")
    return matches[0]


def _parse_document(data: bytes, description: str) -> None:
    """Pastikan XML dokumen well-formed."""

    try:
        ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ExportDotxError(f"{description} bukan XML yang valid") from exc


def _validate_dotx(path: Path) -> _ValidationReport:
    """Validasi hasil: ZIP sehat, content type template, XML well-formed."""

    try:
        with zipfile.ZipFile(path) as archive:
            bad_part = archive.testzip()
            if bad_part is not None:
                raise ExportDotxError(f"ZIP rusak pada part: {bad_part}")

            names = archive.namelist()
            if names.count(CONTENT_TYPES_PART) != 1:
                raise ExportDotxError(
                    f"{CONTENT_TYPES_PART} harus ada tepat satu kali"
                )
            if names.count(DOCUMENT_PART) != 1:
                raise ExportDotxError(
                    f"{DOCUMENT_PART} harus ada tepat satu kali"
                )

            content_types = archive.read(CONTENT_TYPES_PART)
            actual = _document_content_type(content_types)
            if actual != TEMPLATE_CONTENT_TYPE:
                raise ExportDotxError(
                    "Content type hasil bukan content type template: "
                    f"{actual!r}"
                )

            document = archive.read(DOCUMENT_PART)
            _parse_document(document, DOCUMENT_PART)
    except zipfile.BadZipFile as exc:
        raise ExportDotxError(f"ZIP tidak valid: {exc}") from exc

    return _ValidationReport(
        parts=len(names),
        document_bytes=len(document),
    )


def export_dotx(
    input_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
) -> ExportReport:
    """Ekspor ``input_path`` (DOCX) menjadi ``output_path`` (DOTX)."""

    source_path = Path(input_path)
    target_path = Path(output_path)
    if not source_path.is_file():
        raise ExportDotxError(f"Input bukan file: {source_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with zipfile.ZipFile(source_path) as source:
            infos = source.infolist()
            content_types_info = _single_part(infos, CONTENT_TYPES_PART)
            document_info = _single_part(infos, DOCUMENT_PART)

            original_content_types = source.read(content_types_info)
            patched_content_types = _convert_content_types(
                original_content_types
            )
            content_type_changed = (
                patched_content_types != original_content_types
            )

            # Validasi input lebih awal agar tidak menulis output yang pasti
            # gagal divalidasi.
            _parse_document(source.read(document_info), DOCUMENT_PART)

            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target_path.name}.",
                suffix=".tmp",
                dir=target_path.parent,
            )
            os.close(file_descriptor)
            temporary_path = Path(temporary_name)

            with zipfile.ZipFile(temporary_path, "w") as target:
                target.comment = source.comment
                for info in infos:
                    data = source.read(info)
                    if info.filename == CONTENT_TYPES_PART:
                        data = patched_content_types
                    output_info = copy.copy(info)
                    output_info.date_time = FIXED_ZIP_DATETIME
                    target.writestr(output_info, data)

        validation = _validate_dotx(temporary_path)
        os.replace(temporary_path, target_path)
        temporary_path = None
    except zipfile.BadZipFile as exc:
        raise ExportDotxError(f"ZIP input tidak valid: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    return ExportReport(
        parts=validation.parts,
        document_bytes=validation.document_bytes,
        content_type_changed=content_type_changed,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ekspor DOCX menjadi DOTX dengan mengganti content type part "
            "dokumen; seluruh part lain disalin apa adanya."
        )
    )
    parser.add_argument(
        "--in",
        dest="input_path",
        type=Path,
        required=True,
        help="file DOCX input",
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        required=True,
        help="lokasi file DOTX hasil",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        report = export_dotx(args.input_path, args.output_path)
    except (ExportDotxError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Part disalin: {report.parts}")
    if report.content_type_changed:
        print("Content type document.xml: dokumen -> template")
    else:
        print("Content type document.xml: sudah template (tidak berubah)")
    print(f"document.xml: {report.document_bytes} byte (well-formed)")
    print(f"DOTX: {args.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
