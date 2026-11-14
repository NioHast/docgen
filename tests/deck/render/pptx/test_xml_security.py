"""Tes batas ZIP dan parser XML aman untuk helper PPTX."""

import struct
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from lxml import etree

import autooffice.common.zip as common_zip
import autooffice.deck.render.pptx.xml as xml_module
from autooffice.deck.render.pptx.shapes import PptxRenderError
from autooffice.deck.render.pptx.xml import (
    MAX_ZIP_CENTRAL_DIRECTORY_BYTES,
    MAX_ZIP_ENTRIES,
    MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES,
    MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES,
    content_hash,
    forbidden_node_paths,
    normalize_embedded_workbooks,
    validate_package,
)

_PPTX_NAMESPACE = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _write_zip(path: Path, entries: Mapping[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def _patch_declared_sizes(path: Path, sizes: Mapping[str, tuple[int, int]]) -> None:
    """Ubah ukuran compressed/uncompressed tanpa menambah isi arsip."""

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


@pytest.mark.parametrize(
    "reader",
    [
        forbidden_node_paths,
        validate_package,
        normalize_embedded_workbooks,
        content_hash,
    ],
)
def test_pptx_readers_reject_100mb_bomb_before_reading(
    reader: Callable[[Path], object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_zip(
        tmp_path / "bomb.pptx",
        {"ppt/slides/slide1.xml": b"<p:sld/>"},
    )
    _patch_declared_sizes(path, {"ppt/slides/slide1.xml": (1024, 100 * 1024 * 1024)})
    assert path.stat().st_size < 1024

    _forbid_archive_read(monkeypatch)

    with pytest.raises(PptxRenderError, match=r"rasio kompresi.*PPTX-ZIP-LIMIT"):
        reader(path)


def test_pptx_reader_rejects_entry_over_uncompressed_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_zip(
        tmp_path / "besar.pptx",
        {"ppt/slides/slide1.xml": b"<p:sld/>"},
    )
    declared = MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES + 1
    _patch_declared_sizes(path, {"ppt/slides/slide1.xml": (declared, declared)})

    _forbid_archive_read(monkeypatch)

    with pytest.raises(PptxRenderError, match=r"setelah dekompresi.*PPTX-ZIP-LIMIT"):
        forbidden_node_paths(path)


def test_pptx_reader_rejects_total_uncompressed_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = [f"ppt/media/image{index}.bin" for index in range(5)]
    path = _write_zip(tmp_path / "total.pptx", dict.fromkeys(names, b"x"))
    per_entry = MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES - 1
    assert per_entry * len(names) > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES
    _patch_declared_sizes(path, {name: (per_entry, per_entry) for name in names})

    _forbid_archive_read(monkeypatch)

    with pytest.raises(PptxRenderError, match=r"Total ukuran ZIP.*PPTX-ZIP-LIMIT"):
        content_hash(path)


def test_pptx_reader_rejects_too_many_entries_before_zipfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = {f"ppt/part{index}.xml": b"" for index in range(MAX_ZIP_ENTRIES + 1)}
    path = _write_zip(tmp_path / "banyak.pptx", entries)

    _forbid_archive_read(monkeypatch)
    _forbid_zipfile(monkeypatch)

    with pytest.raises(PptxRenderError, match=r"entry.*PPTX-ZIP-LIMIT"):
        validate_package(path)


def test_pptx_reader_rejects_forged_low_entry_count_before_zipfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = {f"ppt/part{index}.xml": b"" for index in range(MAX_ZIP_ENTRIES + 1)}
    path = _write_zip(tmp_path / "banyak-palsu.pptx", entries)
    _patch_eocd(path, entries=1)

    _forbid_zipfile(monkeypatch)

    with pytest.raises(PptxRenderError, match=r"entry.*PPTX-ZIP-LIMIT"):
        content_hash(path)


def test_pptx_reader_rejects_oversized_central_directory_before_zipfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_zip(tmp_path / "cd-besar.pptx", {"ppt/slides/slide1.xml": b"<p:sld/>"})
    _patch_eocd(path, directory_size=MAX_ZIP_CENTRAL_DIRECTORY_BYTES + 1)

    _forbid_zipfile(monkeypatch)

    with pytest.raises(PptxRenderError, match=r"Central directory.*PPTX-ZIP-LIMIT"):
        content_hash(path)


def test_content_hash_rejects_understated_file_size_bomb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "ppt/media/bomb.bin"
    payload = b"\0" * (2 * 1024 * 1024)
    path = _write_zip(tmp_path / "bomb-nyata.pptx", {name: payload})
    _declare_small_sizes(path, {name: 0})
    monkeypatch.setattr(xml_module, "MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES", 64 * 1024)
    monkeypatch.setattr(common_zip, "ZIP_READ_CHUNK_BYTES", 16 * 1024)
    read_sizes = _track_chunk_reads(monkeypatch)

    with zipfile.ZipFile(path) as archive:
        assert archive.getinfo(name).file_size == 0
    assert path.stat().st_size < 64 * 1024

    with pytest.raises(PptxRenderError, match=r"setelah dekompresi.*PPTX-ZIP-LIMIT"):
        content_hash(path)

    assert read_sizes
    assert max(read_sizes) <= 16 * 1024
    assert sum(read_sizes) <= 64 * 1024 + 16 * 1024
    assert 0 < sum(read_sizes) < len(payload)


def test_content_hash_rejects_actual_compression_ratio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "ppt/media/ratio.bin"
    payload = b"\0" * (2 * 1024 * 1024)
    path = _write_zip(tmp_path / "rasio-aktual.pptx", {name: payload})
    _declare_small_sizes(path, {name: 0})
    monkeypatch.setattr(common_zip, "ZIP_READ_CHUNK_BYTES", 16 * 1024)

    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(name)
        assert info.file_size == 0
        assert len(payload) // info.compress_size > 200
    read_sizes = _track_chunk_reads(monkeypatch)

    with pytest.raises(PptxRenderError, match=r"rasio kompresi.*aktual.*PPTX-ZIP-LIMIT"):
        content_hash(path)

    assert read_sizes
    assert 0 < sum(read_sizes) < len(payload)


def test_forbidden_node_paths_rejects_understated_file_size_bomb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "ppt/slides/slide1.xml"
    path = _write_zip(tmp_path / "bomb-slide.pptx", {name: b"\0" * (1024 * 1024)})
    _declare_small_sizes(path, {name: 0})
    monkeypatch.setattr(xml_module, "MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES", 64 * 1024)
    monkeypatch.setattr(common_zip, "ZIP_READ_CHUNK_BYTES", 16 * 1024)

    with pytest.raises(PptxRenderError, match=r"setelah dekompresi.*PPTX-ZIP-LIMIT"):
        forbidden_node_paths(path)


def test_validate_package_rejects_understated_file_size_bomb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "ppt/presentation.xml"
    path = _write_zip(tmp_path / "bomb-validate.pptx", {name: b"\0" * (1024 * 1024)})
    _declare_small_sizes(path, {name: 0})
    monkeypatch.setattr(xml_module, "MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES", 64 * 1024)
    monkeypatch.setattr(common_zip, "ZIP_READ_CHUNK_BYTES", 16 * 1024)

    with pytest.raises(PptxRenderError, match=r"setelah dekompresi.*PPTX-ZIP-LIMIT"):
        validate_package(path)


def test_normalize_embedded_workbooks_rejects_understated_inner_bomb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _write_zip(
        tmp_path / "book1.xlsx",
        {"docProps/core.xml": b"\0" * (2 * 1024 * 1024)},
    )
    _declare_small_sizes(workbook_path, {"docProps/core.xml": 0})
    package = _write_zip(
        tmp_path / "workbook-bomb-nyata.pptx",
        {"ppt/embeddings/book1.xlsx": workbook_path.read_bytes()},
    )
    monkeypatch.setattr(xml_module, "MAX_ZIP_ENTRY_UNCOMPRESSED_BYTES", 64 * 1024)
    monkeypatch.setattr(common_zip, "ZIP_READ_CHUNK_BYTES", 16 * 1024)

    with pytest.raises(
        PptxRenderError,
        match=r"setelah dekompresi.*workbook tertanam.*PPTX-ZIP-LIMIT",
    ):
        normalize_embedded_workbooks(package)


def test_normalize_embedded_workbooks_rejects_inner_zip_bomb(tmp_path: Path) -> None:
    workbook_path = _write_zip(
        tmp_path / "book1.xlsx",
        {"docProps/core.xml": b"<cp:coreProperties/>"},
    )
    _patch_declared_sizes(
        workbook_path,
        {"docProps/core.xml": (1024, 100 * 1024 * 1024)},
    )
    package = _write_zip(
        tmp_path / "workbook-bomb.pptx",
        {"ppt/embeddings/book1.xlsx": workbook_path.read_bytes()},
    )

    with pytest.raises(PptxRenderError, match=r"workbook tertanam.*PPTX-ZIP-LIMIT"):
        normalize_embedded_workbooks(package)


def test_xml_parser_disables_external_entity_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "sentinel-rahasia.txt"
    sentinel.write_text("ISI-RAHASIA-TIDAK-BOLEH-TERBACA", encoding="utf-8")
    part = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<!DOCTYPE p:sld [<!ENTITY xxe SYSTEM "'
        + sentinel.as_uri().encode()
        + b'">]>'
        + f'<p:sld xmlns:p="{_PPTX_NAMESPACE}">&xxe;</p:sld>'.encode()
    )
    path = _write_zip(tmp_path / "xxe-sentinel.pptx", {"ppt/slides/slide1.xml": part})

    captured: dict[str, object] = {}
    real_parser = etree.XMLParser

    def _spy(*args: object, **kwargs: object) -> etree.XMLParser:
        captured.update(kwargs)
        return real_parser(*args, **kwargs)

    monkeypatch.setattr(xml_module.etree, "XMLParser", _spy)

    with pytest.raises(PptxRenderError, match=r"DOCTYPE/entity.*PPTX-XML-UNSAFE"):
        forbidden_node_paths(path)

    assert captured["resolve_entities"] is False
    assert captured["no_network"] is True
    assert captured["load_dtd"] is False
    assert captured["dtd_validation"] is False
    assert captured["huge_tree"] is False
    assert sentinel.read_text(encoding="utf-8") == "ISI-RAHASIA-TIDAK-BOLEH-TERBACA"


def test_forbidden_node_paths_rejects_doctype_and_entity(tmp_path: Path) -> None:
    part = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE p:sld [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        f'<p:sld xmlns:p="{_PPTX_NAMESPACE}">&xxe;</p:sld>'
    ).encode()
    path = _write_zip(tmp_path / "xxe.pptx", {"ppt/slides/slide1.xml": part})

    with pytest.raises(PptxRenderError, match=r"DOCTYPE/entity.*PPTX-XML-UNSAFE"):
        forbidden_node_paths(path)


def test_normalize_embedded_workbooks_rejects_doctype_core_part(tmp_path: Path) -> None:
    core = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<!DOCTYPE cp:coreProperties [<!ENTITY xxe "boom">]>'
        b'<cp:coreProperties xmlns:cp="urn:test">&xxe;</cp:coreProperties>'
    )
    workbook_path = _write_zip(tmp_path / "book-core.xlsx", {"docProps/core.xml": core})
    package = _write_zip(
        tmp_path / "workbook-core-doctype.pptx",
        {"ppt/embeddings/book1.xlsx": workbook_path.read_bytes()},
    )

    with pytest.raises(PptxRenderError, match=r"DOCTYPE/entity.*PPTX-XML-UNSAFE"):
        normalize_embedded_workbooks(package)


def test_forbidden_node_paths_accepts_well_formed_part(tmp_path: Path) -> None:
    part = f'<p:sld xmlns:p="{_PPTX_NAMESPACE}"><p:cSld/></p:sld>'.encode()
    path = _write_zip(tmp_path / "bersih.pptx", {"ppt/slides/slide1.xml": part})

    assert forbidden_node_paths(path) == ()


def test_content_hash_accepts_small_package(tmp_path: Path) -> None:
    path = _write_zip(tmp_path / "kecil.pptx", {"ppt/slides/slide1.xml": b"<p:sld/>"})

    digest = content_hash(path)

    assert len(digest) == 64
