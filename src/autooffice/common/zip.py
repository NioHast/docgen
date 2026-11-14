"""Batas keamanan ZIP bersama untuk package DOCX dan renderer PPTX.

Modul ini tidak boleh mengimpor domain mana pun. Pemanggil memetakan
:class:`ZipLimitError` dan :class:`ZipFormatError` ke error domainnya sendiri.

Dua lapis pertahanan dipakai:

1. Preflight membaca EOCD/ZIP64 EOCD dan memindai central directory tanpa
   membuat ``ZipInfo``. Jumlah entry dan ukuran central directory ditolak
   sebelum ``zipfile.ZipFile`` membangun daftar entry.
2. Setiap entry dibaca bertahap lewat ``ZipFile.open`` dengan potongan 1 MiB.
   Batas per-entry dan total dihitung dari byte yang benar-benar keluar dari
   dekompresor, bukan dari ``ZipInfo.file_size``/``compress_size`` yang dapat
   direkayasa.
"""

import copy
import io
import os
import struct
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO, BinaryIO, cast

MAX_ZIP_ENTRIES = 4096
MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 200
MAX_ZIP_CENTRAL_DIRECTORY_BYTES = 16 * 1024 * 1024
ZIP_READ_CHUNK_BYTES = 1024 * 1024
# Denominator minimum mencegah rasio palsu pada entry sangat kecil yang
# compressed stream-nya hanya beberapa byte overhead.
ZIP_RATIO_MIN_COMPRESSED_BYTES = 64

type ZipSource = str | os.PathLike[str] | BinaryIO

_EOCD_SIGNATURE = b"PK\x05\x06"
_EOCD_SIZE = 22
_EOCD_MAX_SEARCH = _EOCD_SIZE + 0xFFFF
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_ZIP64_LOCATOR_SIZE = 20
_ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"
_ZIP64_EOCD_MIN_SIZE = 56
_CENTRAL_DIRECTORY_SIGNATURE = b"PK\x01\x02"
_CENTRAL_DIRECTORY_HEADER_SIZE = 46
_ZIP64_SENTINEL_16 = 0xFFFF
_ZIP64_SENTINEL_32 = 0xFFFFFFFF


class ZipLimitError(Exception):
    """Arsip ZIP melewati batas keamanan resource."""


class ZipFormatError(Exception):
    """Struktur ZIP tidak dapat dibaca sebagai arsip yang valid."""


class ZipEntryError(ZipFormatError):
    """Satu entry ZIP tidak dapat dibaca atau gagal verifikasi CRC."""


@dataclass(frozen=True, slots=True)
class ZipLimits:
    """Konfigurasi batas untuk satu operasi pembacaan ZIP."""

    max_entries: int = MAX_ZIP_ENTRIES
    max_entry_bytes: int = MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES
    max_total_bytes: int = MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES
    max_ratio: int = MAX_ZIP_COMPRESSION_RATIO
    max_central_directory_bytes: int = MAX_ZIP_CENTRAL_DIRECTORY_BYTES


DEFAULT_ZIP_LIMITS = ZipLimits()


@dataclass(frozen=True, slots=True)
class ZipStructure:
    """Metadata hasil preflight yang sudah diverifikasi."""

    entry_count: int
    central_directory_size: int
    central_directory_offset: int


def _source_label(source: ZipSource) -> str:
    if isinstance(source, (str, os.PathLike)):
        return os.fspath(source)
    return getattr(source, "name", "<stream>")


def _read_tail(source: ZipSource, size: int) -> tuple[bytes, int]:
    """Baca potongan ekor arsip tanpa mengubah posisi stream pemanggil."""

    try:
        if isinstance(source, (str, os.PathLike)):
            with open(source, "rb") as handle:
                handle.seek(0, io.SEEK_END)
                length = handle.tell()
                handle.seek(max(0, length - size))
                return handle.read(size), length
        position = source.tell()
        source.seek(0, io.SEEK_END)
        length = source.tell()
        source.seek(max(0, length - size))
        tail = source.read(size)
        source.seek(position)
        return tail, length
    except (OSError, AttributeError, ValueError) as exc:
        raise ZipFormatError(f"ZIP tidak dapat dibaca: {_source_label(source)}: {exc}") from exc


def _read_at(source: ZipSource, offset: int, size: int) -> bytes:
    """Baca rentang byte tertentu tanpa mengubah posisi stream pemanggil."""

    if size == 0:
        return b""
    try:
        if isinstance(source, (str, os.PathLike)):
            with open(source, "rb") as handle:
                handle.seek(offset)
                return handle.read(size)
        position = source.tell()
        source.seek(offset)
        data = source.read(size)
        source.seek(position)
        return data
    except (OSError, AttributeError, ValueError) as exc:
        raise ZipFormatError(f"ZIP tidak dapat dibaca: {_source_label(source)}: {exc}") from exc


def _find_eocd(tail: bytes) -> int:
    """Cari EOCD terakhir yang dipakai ``zipfile``.

    ``zipfile._EndRecData`` memakai ``rfind`` dan menerima record terakhir yang
    masih menyisakan satu header penuh. Preflight harus memilih record yang
    sama; kalau tidak, central directory yang divalidasi bisa berbeda dari
    yang nanti dibaca ``ZipFile``.
    """

    index = tail.rfind(_EOCD_SIGNATURE)
    if index < 0 or index + _EOCD_SIZE > len(tail):
        raise ZipFormatError("End of central directory ZIP tidak ditemukan")
    return index


def _has_zip64_marker(
    entries: int,
    directory_size: int,
    directory_offset: int,
) -> bool:
    return (
        entries == _ZIP64_SENTINEL_16
        or directory_size == _ZIP64_SENTINEL_32
        or directory_offset == _ZIP64_SENTINEL_32
    )


def _read_zip64_end(
    source: ZipSource,
    *,
    eocd_offset: int,
    entries: int,
    directory_size: int,
    directory_offset: int,
    limits: ZipLimits,
) -> tuple[int, int, int, int]:
    """Baca ZIP64 EOCD dan kembalikan count, size, offset, serta awal CD."""

    locator_offset = eocd_offset - _ZIP64_LOCATOR_SIZE
    if locator_offset < 0:
        if entries == _ZIP64_SENTINEL_16:
            raise ZipLimitError(
                "ZIP mengklaim sedikitnya 65535 entry tanpa ZIP64 EOCD; "
                f"maksimum {limits.max_entries} entry"
            )
        raise ZipFormatError("ZIP64 locator terpotong")
    locator = _read_at(source, locator_offset, _ZIP64_LOCATOR_SIZE)
    if len(locator) != _ZIP64_LOCATOR_SIZE or not locator.startswith(_ZIP64_LOCATOR_SIGNATURE):
        if entries == _ZIP64_SENTINEL_16:
            raise ZipLimitError(
                "ZIP mengklaim sedikitnya 65535 entry tanpa ZIP64 EOCD; "
                f"maksimum {limits.max_entries} entry"
            )
        raise ZipFormatError("ZIP64 locator tidak valid")

    record_offset = int.from_bytes(locator[8:16], "little")
    record = _read_at(source, record_offset, _ZIP64_EOCD_MIN_SIZE)
    if len(record) != _ZIP64_EOCD_MIN_SIZE or not record.startswith(_ZIP64_EOCD_SIGNATURE):
        raise ZipFormatError("ZIP64 EOCD tidak valid")
    record_size = int.from_bytes(record[4:12], "little")
    if record_size < 44:
        raise ZipFormatError("ZIP64 EOCD terpotong")

    entries = int.from_bytes(record[32:40], "little")
    directory_size = int.from_bytes(record[40:48], "little")
    directory_offset = int.from_bytes(record[48:56], "little")
    prefix = record_offset - directory_size - directory_offset
    if prefix < 0:
        raise ZipFormatError("Offset central directory ZIP64 tidak valid")
    return entries, directory_size, directory_offset, directory_offset + prefix


def _check_directory_limits(
    source: ZipSource,
    *,
    entries: int,
    directory_size: int,
    limits: ZipLimits,
) -> None:
    label = _source_label(source)
    if entries > limits.max_entries:
        raise ZipLimitError(
            f"ZIP melebihi batas keamanan: {entries} entry, maksimum {limits.max_entries}: {label}"
        )
    if directory_size > limits.max_central_directory_bytes:
        raise ZipLimitError(
            f"Central directory ZIP berukuran {directory_size} byte, "
            f"maksimum {limits.max_central_directory_bytes} byte: {label}"
        )


def _scan_central_directory(
    source: ZipSource,
    *,
    start: int,
    size: int,
    limits: ZipLimits,
) -> int:
    """Hitung record central directory tanpa membuat ``ZipInfo``.

    Jumlah entry dari EOCD tidak dipercaya: arsip dapat mengklaim satu entry
    sementara central directory memuat ribuan record.
    """

    label = _source_label(source)
    data = _read_at(source, start, size)
    if len(data) != size:
        raise ZipFormatError(f"Central directory ZIP terpotong: {label}")

    offset = 0
    seen = 0
    while offset < size:
        remaining = size - offset
        if remaining < _CENTRAL_DIRECTORY_HEADER_SIZE:
            raise ZipFormatError(f"Central directory ZIP terpotong: {label}")
        if data[offset : offset + 4] != _CENTRAL_DIRECTORY_SIGNATURE:
            raise ZipFormatError(f"Signature central directory ZIP tidak valid: {label}")
        name_length = int.from_bytes(data[offset + 28 : offset + 30], "little")
        extra_length = int.from_bytes(data[offset + 30 : offset + 32], "little")
        comment_length = int.from_bytes(data[offset + 32 : offset + 34], "little")
        record_size = _CENTRAL_DIRECTORY_HEADER_SIZE + name_length + extra_length + comment_length
        seen += 1
        if seen > limits.max_entries:
            raise ZipLimitError(
                f"ZIP melebihi batas keamanan: lebih dari {limits.max_entries} entry: {label}"
            )
        if record_size > remaining:
            raise ZipFormatError(f"Central directory ZIP terpotong: {label}")
        offset += record_size

    return seen


def preflight_zip(
    source: ZipSource,
    *,
    limits: ZipLimits = DEFAULT_ZIP_LIMITS,
) -> ZipStructure:
    """Validasi EOCD dan central directory sebelum ``zipfile.ZipFile`` dibuat."""

    tail, total_size = _read_tail(source, _EOCD_MAX_SEARCH)
    tail_start = total_size - len(tail)
    eocd_index = _find_eocd(tail)
    eocd_offset = tail_start + eocd_index
    (
        _signature,
        _disk_number,
        _directory_disk,
        _entries_disk,
        entries,
        directory_size,
        directory_offset,
        _comment_length,
    ) = struct.unpack("<4s4H2LH", tail[eocd_index : eocd_index + _EOCD_SIZE])

    if _has_zip64_marker(entries, directory_size, directory_offset):
        entries, directory_size, directory_offset, directory_start = _read_zip64_end(
            source,
            eocd_offset=eocd_offset,
            entries=entries,
            directory_size=directory_size,
            directory_offset=directory_offset,
            limits=limits,
        )
        _check_directory_limits(
            source,
            entries=entries,
            directory_size=directory_size,
            limits=limits,
        )
    else:
        _check_directory_limits(
            source,
            entries=entries,
            directory_size=directory_size,
            limits=limits,
        )
        prefix = eocd_offset - directory_size - directory_offset
        if prefix < 0:
            raise ZipFormatError(
                f"Offset central directory ZIP tidak valid: {_source_label(source)}"
            )
        directory_start = directory_offset + prefix

    if directory_start < 0 or directory_start + directory_size > total_size:
        raise ZipFormatError(
            f"Central directory ZIP berada di luar berkas: {_source_label(source)}"
        )
    actual_entries = _scan_central_directory(
        source,
        start=directory_start,
        size=directory_size,
        limits=limits,
    )
    return ZipStructure(
        entry_count=actual_entries,
        central_directory_size=directory_size,
        central_directory_offset=directory_start,
    )


def open_zip(
    source: ZipSource,
    *,
    limits: ZipLimits = DEFAULT_ZIP_LIMITS,
) -> zipfile.ZipFile:
    """Preflight lalu buka ZIP; pemanggil bertanggung jawab menutupnya."""

    preflight_zip(source, limits=limits)
    return zipfile.ZipFile(source)


def check_declared_limits(
    archive: zipfile.ZipFile,
    *,
    source: str,
    limits: ZipLimits = DEFAULT_ZIP_LIMITS,
) -> None:
    """Tolak metadata entry yang sudah terang-terangan melewati batas.

    Pemeriksaan ini hanya jaring pengaman awal. Ukuran sebenarnya tetap
    dihitung oleh :class:`ZipReader`; metadata tidak pernah dipercaya sebagai
    bukti bahwa isi entry kecil.
    """

    infos = archive.infolist()
    if len(infos) > limits.max_entries:
        raise ZipLimitError(
            f"ZIP melebihi batas keamanan: {len(infos)} entry, "
            f"maksimum {limits.max_entries}: {source}"
        )

    total = 0
    for info in infos:
        size = info.file_size
        if size > limits.max_entry_bytes:
            raise ZipLimitError(
                f"Entry ZIP '{info.filename}' berukuran {size} byte setelah "
                f"dekompresi, maksimum {limits.max_entry_bytes} byte: {source}"
            )
        if size > 0 and (info.compress_size == 0 or size > info.compress_size * limits.max_ratio):
            ratio = size // max(info.compress_size, 1)
            raise ZipLimitError(
                f"Entry ZIP '{info.filename}' memiliki rasio kompresi {ratio}:1, "
                f"maksimum {limits.max_ratio}:1: {source}"
            )
        total += size
        if total > limits.max_total_bytes:
            raise ZipLimitError(
                f"Total ukuran ZIP setelah dekompresi melebihi {total} byte, "
                f"maksimum {limits.max_total_bytes} byte: {source}"
            )


class _CountingReadFile:
    """Proxy berkas yang menghitung byte mentah yang dibaca ``ZipExtFile``."""

    def __init__(self, fileobj: IO[bytes]) -> None:
        self._fileobj = fileobj
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        data = self._fileobj.read(size)
        self.bytes_read += len(data)
        return data

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        return self._fileobj.seek(offset, whence)

    def tell(self) -> int:
        return self._fileobj.tell()

    def seekable(self) -> bool:
        return self._fileobj.seekable()

    def close(self) -> None:
        self._fileobj.close()


class ZipReader:
    """Pembaca entry ZIP yang membatasi byte hasil dekompresi.

    ``ZipExtFile`` membatasi output berdasarkan ``ZipInfo.file_size``. Nilai
    itu dapat direkayasa terlalu kecil, jadi salinan ``ZipInfo`` dipakai untuk
    membaca melewati batas deklarasi. Jumlah byte aktual yang keluar tetap
    dihitung dan ditolak segera setelah melewati batas.
    """

    def __init__(
        self,
        archive: zipfile.ZipFile,
        *,
        source: str,
        limits: ZipLimits = DEFAULT_ZIP_LIMITS,
    ) -> None:
        self._archive = archive
        self._source = source
        self._limits = limits
        self._total_bytes = 0
        if archive.fp is None:
            raise ZipFormatError(f"ZIP sudah ditutup: {source}")
        self._counter: _CountingReadFile
        if isinstance(archive.fp, _CountingReadFile):
            self._counter = archive.fp
        else:
            self._counter = _CountingReadFile(archive.fp)
            archive.fp = cast(IO[bytes], self._counter)

    @property
    def total_bytes(self) -> int:
        """Total byte aktual yang sudah dikembalikan pembaca ini."""

        return self._total_bytes

    def _iter_entry(self, info: zipfile.ZipInfo) -> Iterator[bytes]:
        """Hasilkan potongan entry sambil menegakkan batas byte aktual."""

        name = info.filename
        if info.file_size > self._limits.max_entry_bytes:
            raise ZipLimitError(
                f"Entry ZIP '{name}' berukuran {info.file_size} byte setelah "
                f"dekompresi, maksimum {self._limits.max_entry_bytes} byte: "
                f"{self._source}"
            )

        # ``ZipExtFile`` berhenti pada ``file_size`` dan memeriksa CRC saat
        # mencapai batas itu. Beri ruang dua chunk di atas batas agar limit
        # byte aktual yang memutuskan, bukan CRC dari metadata palsu.
        probe = copy.copy(info)
        probe.file_size = self._limits.max_entry_bytes + 2 * ZIP_READ_CHUNK_BYTES + 1
        entry_bytes = 0
        try:
            with self._archive.open(probe) as stream:
                compressed_start = self._counter.bytes_read
                while chunk := stream.read(ZIP_READ_CHUNK_BYTES):
                    entry_bytes += len(chunk)
                    self._total_bytes += len(chunk)
                    if entry_bytes > self._limits.max_entry_bytes:
                        raise ZipLimitError(
                            f"Entry ZIP '{name}' melebihi "
                            f"{self._limits.max_entry_bytes} byte setelah "
                            f"dekompresi (terbaca {entry_bytes} byte): "
                            f"{self._source}"
                        )
                    if self._total_bytes > self._limits.max_total_bytes:
                        raise ZipLimitError(
                            f"Total ukuran ZIP setelah dekompresi melebihi "
                            f"{self._limits.max_total_bytes} byte (terbaca "
                            f"{self._total_bytes} byte): {self._source}"
                        )
                    compressed_bytes = self._counter.bytes_read - compressed_start
                    ratio_denominator = max(
                        compressed_bytes,
                        ZIP_RATIO_MIN_COMPRESSED_BYTES,
                    )
                    if entry_bytes > ratio_denominator * self._limits.max_ratio:
                        ratio = entry_bytes // ratio_denominator
                        raise ZipLimitError(
                            f"Entry ZIP '{name}' memiliki rasio kompresi "
                            f"aktual {ratio}:1, maksimum "
                            f"{self._limits.max_ratio}:1: {self._source}"
                        )
                    yield chunk
        except (
            zipfile.BadZipFile,
            EOFError,
            NotImplementedError,
            OSError,
            RuntimeError,
            ValueError,
            zlib.error,
        ) as exc:
            raise ZipEntryError(
                f"Entry ZIP '{name}' tidak dapat dibaca: {self._source}: {exc}"
            ) from exc

    def read(self, info: zipfile.ZipInfo) -> bytes:
        """Baca satu entry penuh dengan potongan maksimum 1 MiB."""

        return b"".join(self._iter_entry(info))

    def drain(self, info: zipfile.ZipInfo) -> None:
        """Baca entry sampai habis tanpa menahan isinya di memori."""

        for _ in self._iter_entry(info):
            pass


__all__ = [
    "DEFAULT_ZIP_LIMITS",
    "MAX_ZIP_CENTRAL_DIRECTORY_BYTES",
    "MAX_ZIP_COMPRESSION_RATIO",
    "MAX_ZIP_ENTRIES",
    "MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES",
    "MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES",
    "ZIP_RATIO_MIN_COMPRESSED_BYTES",
    "ZIP_READ_CHUNK_BYTES",
    "ZipEntryError",
    "ZipFormatError",
    "ZipLimitError",
    "ZipLimits",
    "ZipReader",
    "ZipSource",
    "ZipStructure",
    "check_declared_limits",
    "open_zip",
    "preflight_zip",
]
