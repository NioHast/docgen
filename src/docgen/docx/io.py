"""Baca/tulis ZIP untuk :mod:`docgen.docx.package`.

Modul internal package. Stage tidak boleh memakainya langsung.
"""

from __future__ import annotations

import copy
import os
import tempfile
import zipfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from . import PackageError, SaveError


@dataclass(frozen=True)
class ZipEntry:
    """Satu entry ZIP beserta metadata aslinya."""

    name: str
    data: bytes
    info: zipfile.ZipInfo


def read_zip(path: str | Path) -> tuple[ZipEntry, ...]:
    """Baca seluruh entry ZIP dan pertahankan ``ZipInfo`` asli."""

    try:
        with zipfile.ZipFile(path, "r") as archive:
            entries: list[ZipEntry] = []
            seen: set[str] = set()
            for info in archive.infolist():
                if info.filename in seen:
                    raise PackageError(
                        f"Entry ZIP duplikat: {info.filename}"
                    )
                seen.add(info.filename)
                entries.append(
                    ZipEntry(
                        name=info.filename,
                        data=archive.read(info),
                        info=info,
                    )
                )
            return tuple(entries)
    except PackageError:
        raise
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
        info.compress_type = compression
    return info


def _write_stream(
    handle,
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
    try:
        path.unlink()
    except OSError:
        pass


__all__ = ["ZipEntry", "read_zip", "write_zip", "write_zip_atomic"]
