"""Tes batas keamanan ZIP untuk package DOCX."""

import random
import struct
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest

import autooffice.common.zip as common_zip
import autooffice.docx.package.io as package_io
from autooffice.docx.package import PackageError
from autooffice.docx.package.io import (
    MAX_ZIP_CENTRAL_DIRECTORY_BYTES,
    MAX_ZIP_ENTRIES,
    MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES,
    MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES,
    read_zip,
)


def _write_zip(path: Path, entries: Mapping[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def _patch_declared_sizes(path: Path, sizes: Mapping[str, tuple[int, int]]) -> None:
    """Ubah ukuran compressed/uncompressed di header lokal dan central directory.

    Fixture tetap kecil di disk, tetapi metadata ZIP mengklaim entry raksasa.
    ``read_zip`` harus menolaknya dari metadata sebelum ``archive.read``.
    """

    data = bytearray(path.read_bytes())
    offset = 0
    patched: set[str] = set()
    while (signature := data.find(b"PK\x01\x02", offset)) != -1:
        name_length = int.from_bytes(data[signature + 28 : signature + 30], "little")
        extra_length = int.from_bytes(data[signature + 30 : signature + 32], "little")
        comment_length = int.from_bytes(data[signature + 32 : signature + 34], "little")
        name_bytes = bytes(data[signature + 46 : signature + 46 + name_length])
        name = name_bytes.decode("utf-8")
        if name in sizes:
            compressed, uncompressed = sizes[name]
            struct.pack_into("<I", data, signature + 20, compressed)
            struct.pack_into("<I", data, signature + 24, uncompressed)
            local_offset = int.from_bytes(data[signature + 42 : signature + 46], "little")
            struct.pack_into("<I", data, local_offset + 18, compressed)
            struct.pack_into("<I", data, local_offset + 22, uncompressed)
            patched.add(name)
        offset = signature + 46 + name_length + extra_length + comment_length
    assert patched == set(sizes)
    path.write_bytes(bytes(data))


def _patch_eocd(
    path: Path,
    *,
    entries: int | None = None,
    directory_size: int | None = None,
) -> None:
    """Ubah field EOCD tanpa menyentuh central directory sebenarnya."""

    data = bytearray(path.read_bytes())
    offset = data.rfind(b"PK\x05\x06")
    assert offset != -1
    if entries is not None:
        struct.pack_into("<H", data, offset + 10, entries)
    if directory_size is not None:
        struct.pack_into("<I", data, offset + 12, directory_size)
    path.write_bytes(bytes(data))


def _declare_small_sizes(path: Path, names: Mapping[str, int]) -> None:
    """Pertahankan compressed size asli tetapi klaim file_size nol/tiny."""

    with zipfile.ZipFile(path) as archive:
        compressed = {name: archive.getinfo(name).compress_size for name in names}
    _patch_declared_sizes(path, {name: (compressed[name], 0) for name in names})


def _forbid_archive_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def _read(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("archive.read dipanggil sebelum batas ZIP diperiksa")

    monkeypatch.setattr(zipfile.ZipFile, "read", _read)


def _forbid_zipfile(monkeypatch: pytest.MonkeyPatch) -> None:
    def _zipfile(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("ZipFile dibuat sebelum preflight central directory")

    monkeypatch.setattr(zipfile, "ZipFile", _zipfile)


def _track_chunk_reads(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    sizes: list[int] = []
    real_read = zipfile.ZipExtFile.read

    def _read(stream: zipfile.ZipExtFile, size: int = -1) -> bytes:
        data = real_read(stream, size)
        sizes.append(len(data))
        return data

    monkeypatch.setattr(zipfile.ZipExtFile, "read", _read)
    return sizes


def test_read_zip_rejects_100mb_bomb_before_reading(tmp_path: Path, monkeypatch) -> None:
    path = _write_zip(tmp_path / "bomb.docx", {"word/media/bomb.bin": b"\0" * 1024})
    _patch_declared_sizes(path, {"word/media/bomb.bin": (1024, 100 * 1024 * 1024)})
    assert path.stat().st_size < 1024

    _forbid_archive_read(monkeypatch)

    with pytest.raises(PackageError, match="rasio kompresi") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"


def test_read_zip_rejects_zero_compressed_size(tmp_path: Path, monkeypatch) -> None:
    path = _write_zip(tmp_path / "nol.docx", {"word/document.xml": b"<document/>"})
    _patch_declared_sizes(path, {"word/document.xml": (0, 1024)})

    _forbid_archive_read(monkeypatch)

    with pytest.raises(PackageError, match="rasio kompresi") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"


def test_read_zip_rejects_entry_over_uncompressed_limit(tmp_path: Path, monkeypatch) -> None:
    path = _write_zip(tmp_path / "besar.docx", {"word/document.xml": b"<document/>"})
    declared = MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES + 1
    _patch_declared_sizes(path, {"word/document.xml": (declared, declared)})

    _forbid_archive_read(monkeypatch)

    with pytest.raises(PackageError, match="setelah dekompresi") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"


def test_read_zip_rejects_total_uncompressed_limit(tmp_path: Path, monkeypatch) -> None:
    names = [f"word/media/image{index}.bin" for index in range(5)]
    path = _write_zip(tmp_path / "total.docx", {name: b"x" for name in names})
    per_entry = MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES - 1
    assert per_entry * len(names) > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES
    _patch_declared_sizes(path, {name: (per_entry, per_entry) for name in names})

    _forbid_archive_read(monkeypatch)

    with pytest.raises(PackageError, match="Total ukuran ZIP") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"


def test_read_zip_rejects_too_many_entries_before_zipfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = {f"part{index}.xml": b"" for index in range(MAX_ZIP_ENTRIES + 1)}
    path = _write_zip(tmp_path / "banyak.docx", entries)

    _forbid_archive_read(monkeypatch)
    _forbid_zipfile(monkeypatch)

    with pytest.raises(PackageError, match="entry") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"


def test_read_zip_rejects_many_entries_despite_forged_eocd_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = {f"part{index}.xml": b"" for index in range(MAX_ZIP_ENTRIES + 1)}
    path = _write_zip(tmp_path / "banyak-palsu.docx", entries)
    _patch_eocd(path, entries=1)

    _forbid_zipfile(monkeypatch)

    with pytest.raises(PackageError, match="entry") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"


def test_read_zip_rejects_oversized_central_directory_before_zipfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_zip(tmp_path / "cd-besar.docx", {"word/document.xml": b"<document/>"})
    _patch_eocd(path, directory_size=MAX_ZIP_CENTRAL_DIRECTORY_BYTES + 1)

    _forbid_zipfile(monkeypatch)

    with pytest.raises(PackageError, match="Central directory") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"


def test_read_zip_rejects_fake_eocd_in_comment_before_zipfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_zip(tmp_path / "eocd-palsu.docx", {"word/document.xml": b"<document/>"})
    fake_eocd = (
        b"PK\x05\x06"
        + struct.pack("<HHHH", 0, 0, 1, 1)
        + struct.pack("<II", MAX_ZIP_CENTRAL_DIRECTORY_BYTES + 1, 0)
        + struct.pack("<H", 0)
    )
    path.write_bytes(path.read_bytes() + fake_eocd)

    _forbid_zipfile(monkeypatch)

    with pytest.raises(PackageError, match="Central directory") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"


def test_read_zip_rejects_understated_file_size_bomb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "word/media/bomb.bin"
    payload = b"\0" * (2 * 1024 * 1024)
    path = _write_zip(tmp_path / "bomb-nyata.docx", {name: payload})
    _declare_small_sizes(path, {name: 0})
    monkeypatch.setattr(package_io, "MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES", 64 * 1024)
    monkeypatch.setattr(common_zip, "ZIP_READ_CHUNK_BYTES", 16 * 1024)
    read_sizes = _track_chunk_reads(monkeypatch)

    with zipfile.ZipFile(path) as archive:
        assert archive.getinfo(name).file_size == 0
    assert path.stat().st_size < 64 * 1024

    with pytest.raises(PackageError, match="setelah dekompresi") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"
    assert read_sizes
    assert max(read_sizes) <= 16 * 1024
    assert sum(read_sizes) <= 64 * 1024 + 16 * 1024
    assert 0 < sum(read_sizes) < len(payload)


def test_read_zip_rejects_actual_compression_ratio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "word/media/ratio.bin"
    payload = b"\0" * (2 * 1024 * 1024)
    path = _write_zip(tmp_path / "rasio-aktual.docx", {name: payload})
    _declare_small_sizes(path, {name: 0})
    monkeypatch.setattr(common_zip, "ZIP_READ_CHUNK_BYTES", 16 * 1024)

    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(name)
        assert info.file_size == 0
        assert len(payload) // info.compress_size > 200
    read_sizes = _track_chunk_reads(monkeypatch)

    with pytest.raises(PackageError, match="rasio kompresi") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"
    assert read_sizes
    assert 0 < sum(read_sizes) < len(payload)


def test_read_zip_rejects_actual_total_over_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = ("word/media/a.bin", "word/media/b.bin")
    payload = random.Random(7).randbytes(32 * 1024)
    path = _write_zip(
        tmp_path / "total-nyata.docx",
        dict.fromkeys(names, payload),
    )
    _declare_small_sizes(path, dict.fromkeys(names, 0))
    monkeypatch.setattr(package_io, "MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES", 128 * 1024)
    monkeypatch.setattr(package_io, "MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES", 48 * 1024)
    monkeypatch.setattr(common_zip, "ZIP_READ_CHUNK_BYTES", 16 * 1024)

    with pytest.raises(PackageError, match="Total ukuran ZIP") as excinfo:
        read_zip(path)

    assert excinfo.value.code == "PKG-ZIP-LIMIT"


def test_read_zip_accepts_zip64_directory(tmp_path: Path) -> None:
    path = _write_zip(tmp_path / "zip64.docx", {"word/document.xml": b"<document/>"})
    data = bytearray(path.read_bytes())
    eocd_offset = data.rfind(b"PK\x05\x06")
    entries = int.from_bytes(data[eocd_offset + 10 : eocd_offset + 12], "little")
    directory_size = int.from_bytes(data[eocd_offset + 12 : eocd_offset + 16], "little")
    directory_offset = int.from_bytes(data[eocd_offset + 16 : eocd_offset + 20], "little")

    zip64_end = b"".join(
        (
            b"PK\x06\x06",
            struct.pack("<Q", 44),
            struct.pack("<HH", 45, 45),
            struct.pack("<II", 0, 0),
            struct.pack("<QQ", entries, entries),
            struct.pack("<QQ", directory_size, directory_offset),
        )
    )
    locator = (
        b"PK\x06\x07" + struct.pack("<I", 0) + struct.pack("<Q", eocd_offset) + struct.pack("<I", 1)
    )
    zip64_eocd = (
        b"PK\x05\x06"
        + struct.pack("<HHHH", 0, 0, 0xFFFF, 0xFFFF)
        + struct.pack("<II", 0xFFFFFFFF, 0xFFFFFFFF)
        + struct.pack("<H", 0)
    )
    path.write_bytes(bytes(data[:eocd_offset]) + zip64_end + locator + zip64_eocd)

    entries_read = read_zip(path)

    assert [(entry.name, entry.data) for entry in entries_read] == [
        ("word/document.xml", b"<document/>")
    ]


def test_read_zip_accepts_small_archive(tmp_path: Path) -> None:
    path = _write_zip(
        tmp_path / "kecil.docx",
        {"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<document/>"},
    )

    entries = read_zip(path)

    assert [entry.name for entry in entries] == [
        "[Content_Types].xml",
        "word/document.xml",
    ]
