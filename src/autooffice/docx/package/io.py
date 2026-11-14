"""Baca/tulis ZIP untuk :mod:`docgen.docx.package`.

Modul internal package. Stage tidak boleh memakainya langsung.
"""

import contextlib
import copy
import os
import tempfile
import zipfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from autooffice.common.zip import (
    MAX_ZIP_CENTRAL_DIRECTORY_BYTES,
    MAX_ZIP_COMPRESSION_RATIO,
    MAX_ZIP_ENTRIES,
    MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES,
    MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES,
    ZIP_READ_CHUNK_BYTES,
    ZipFormatError,
    ZipLimitError,
    ZipLimits,
    ZipReader,
    check_declared_limits,
    open_zip,
)

from . import PackageError, SaveError

# Batas keamanan ZIP dibagikan dengan renderer PPTX lewat
# ``autooffice.common.zip``. Nilai ini cukup longgar untuk laporan dan deck
# besar, tetapi menolak arsip yang dapat menghabiskan memori.
ZIP_LIMIT_CODE = "PKG-ZIP-LIMIT"


@dataclass(frozen=True)
class ZipEntry:
    """Satu entry ZIP beserta metadata aslinya."""

    name: str
    data: bytes
    info: zipfile.ZipInfo


def _zip_limits() -> ZipLimits:
    """Susun batas dari konstanta modul agar test dapat menurunkannya."""

    return ZipLimits(
        max_entries=MAX_ZIP_ENTRIES,
        max_entry_bytes=MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES,
        max_total_bytes=MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES,
        max_ratio=MAX_ZIP_COMPRESSION_RATIO,
        max_central_directory_bytes=MAX_ZIP_CENTRAL_DIRECTORY_BYTES,
    )


def _as_package_error(error: ZipLimitError) -> PackageError:
    return PackageError(str(error), code=ZIP_LIMIT_CODE)


def check_zip_limits(archive: zipfile.ZipFile, *, source: str | Path) -> None:
    """Tolak metadata entry ZIP yang sudah melewati batas keamanan.

    Pemeriksaan ini hanya jaring pengaman awal. :class:`ZipReader` tetap
    menghitung byte hasil dekompresi yang sebenarnya; ``file_size`` dan
    ``compress_size`` tidak dipakai sebagai bukti keamanan.
    """

    try:
        check_declared_limits(archive, source=str(source), limits=_zip_limits())
    except ZipLimitError as error:
        raise _as_package_error(error) from error


def read_zip(path: str | Path) -> tuple[ZipEntry, ...]:
    """Baca seluruh entry ZIP dengan batas byte aktual dan ``ZipInfo`` asli."""

    try:
        with open_zip(path, limits=_zip_limits()) as archive:
            check_zip_limits(archive, source=path)
            reader = ZipReader(archive, source=str(path), limits=_zip_limits())
            entries: list[ZipEntry] = []
            seen: set[str] = set()
            for info in archive.infolist():
                if info.filename in seen:
                    raise PackageError(f"Entry ZIP duplikat: {info.filename}")
                seen.add(info.filename)
                entries.append(
                    ZipEntry(
                        name=info.filename,
                        data=reader.read(info),
                        info=info,
                    )
                )
            return tuple(entries)
    except PackageError:
        raise
    except ZipLimitError as error:
        raise _as_package_error(error) from error
    except ZipFormatError as error:
        raise PackageError(f"ZIP tidak dapat dibaca: {path}: {error}") from error
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        EOFError,
        NotImplementedError,
        OSError,
        RuntimeError,
        ValueError,
        zlib.error,
    ) as exc:
        raise PackageError(f"ZIP tidak dapat dibaca: {path}: {exc}") from exc


def _copy_info(entry: ZipEntry, compression: int) -> zipfile.ZipInfo:
    info = copy.copy(entry.info)
    info.filename = entry.name
    if info.compress_type is None:
        info.compress_type = compression  # type: ignore[unreachable]  # ZipInfo runtime bisa None
    return info


def _write_stream(
    handle: IO[bytes],
    entries: Sequence[ZipEntry],
    compression: int,
) -> None:
    with zipfile.ZipFile(
        handle,
        mode="w",
        compression=compression,
        allowZip64=True,
    ) as archive:
        for entry in entries:
            archive.writestr(_copy_info(entry, compression), entry.data)


def write_zip(
    path: str | Path,
    entries: Sequence[ZipEntry],
    *,
    compression: int = zipfile.ZIP_DEFLATED,
) -> None:
    """Tulis ZIP langsung ke path tujuan (non-atomik, internal)."""

    destination = Path(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            _write_stream(handle, entries, compression)
            handle.flush()
            os.fsync(handle.fileno())
    except SaveError:
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        NotImplementedError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        zlib.error,
    ) as exc:
        raise SaveError(f"Gagal menulis DOCX: {destination}: {exc}") from exc


def write_zip_atomic(
    path: str | Path,
    entries: Sequence[ZipEntry],
    *,
    compression: int = zipfile.ZIP_DEFLATED,
) -> None:
    """Tulis ZIP ke file sementara di direktori tujuan lalu ``os.replace``."""

    destination = Path(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SaveError(
            f"Direktori tujuan tidak dapat dibuat: {destination.parent}: {exc}"
        ) from exc

    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=str(destination.parent),
        )
    except OSError as exc:
        raise SaveError(
            f"File sementara tidak dapat dibuat di {destination.parent}: {exc}"
        ) from exc
    temporary = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "wb") as handle:
            _write_stream(handle, entries, compression)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except SaveError:
        _unlink_quietly(temporary)
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        NotImplementedError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        zlib.error,
    ) as exc:
        _unlink_quietly(temporary)
        raise SaveError(f"Gagal menyimpan DOCX: {destination}: {exc}") from exc
    except BaseException:
        _unlink_quietly(temporary)
        raise


def _unlink_quietly(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


__all__ = [
    "MAX_ZIP_CENTRAL_DIRECTORY_BYTES",
    "MAX_ZIP_COMPRESSION_RATIO",
    "MAX_ZIP_ENTRIES",
    "MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES",
    "MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES",
    "ZIP_LIMIT_CODE",
    "ZIP_READ_CHUNK_BYTES",
    "ZipEntry",
    "check_zip_limits",
    "read_zip",
    "write_zip",
    "write_zip_atomic",
]
