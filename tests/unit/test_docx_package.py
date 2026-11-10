"""Tes unit package DOCX/OPC."""

import warnings
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest

import docgen.docx.io as docx_io
from docgen.docx import (
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    MAIN_DOCUMENT_CONTENT_TYPE,
    PACKAGE_RELS_PART,
    REL_TYPE_HYPERLINK,
    REL_TYPE_IMAGE,
    REL_TYPE_OFFICE_DOCUMENT,
    REL_TYPE_STYLES,
    DocumentPackage,
    DocxError,
    DocxPackage,
    InvalidPackageError,
    PackageError,
    PartExistsError,
    PartNotFoundError,
    Relationship,
    SaveError,
    paragraph_text,
    sha256_c14n,
)
from docgen.docx.xml import qn
from docgen.errors import DocgenError

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
STYLES_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
RELS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"

GOLDEN = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "golden" / "laporan-baseline.docx"
)

DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    f'<w:document xmlns:w="{W_NS}"><w:body>'
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
    "<w:r><w:t>Hello</w:t></w:r></w:p>"
    "</w:body></w:document>"
).encode()

STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    f'<w:styles xmlns:w="{W_NS}">'
    '<w:style w:type="paragraph" w:styleId="Heading1">'
    '<w:name w:val="heading 1"/></w:style></w:styles>'
).encode()


def _content_types(*, include_bin: bool = True, extra: str = "") -> bytes:
    defaults = (
        f'<Default Extension="rels" ContentType="{RELS_CONTENT_TYPE}"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
    )
    if include_bin:
        defaults += '<Default Extension="bin" ContentType="application/octet-stream"/>'
    overrides = (
        f'<Override PartName="/{DOCUMENT_PART}" '
        f'ContentType="{DOCUMENT_CONTENT_TYPE}"/>'
        '<Override PartName="/word/styles.xml" '
        f'ContentType="{STYLES_CONTENT_TYPE}"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Types xmlns="{CT_NS}">{defaults}{overrides}{extra}</Types>'
    ).encode()


def _package_rels() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Relationships xmlns="{PR_NS}">'
        f'<Relationship Id="rId1" Type="{REL_TYPE_OFFICE_DOCUMENT}" '
        f'Target="{DOCUMENT_PART}"/>'
        "</Relationships>"
    ).encode()


def _document_rels(target: str = "styles.xml") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Relationships xmlns="{PR_NS}">'
        f'<Relationship Id="rId2" Type="{REL_TYPE_STYLES}" '
        f'Target="{target}"/>'
        "</Relationships>"
    ).encode()


def _write_entries(
    path: Path,
    entries: Sequence[tuple[str, bytes, bool, bytes]],
) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data, deflated, comment in entries:
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 2, 3, 4, 6))
            info.compress_type = zipfile.ZIP_DEFLATED if deflated else zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            info.comment = comment
            archive.writestr(info, data)
    return path


def _build_docx(
    path: Path,
    *,
    content_types: bytes | None = None,
    package_rels: bytes | None = None,
    document_rels: bytes | None = None,
    document: bytes | None = None,
    styles: bytes | None = None,
    extra_entries: Sequence[tuple[str, bytes, bool, bytes]] = (),
    include_binary: bool = True,
) -> Path:
    entries: list[tuple[str, bytes, bool, bytes]] = [
        (
            CONTENT_TYPES_PART,
            content_types if content_types is not None else _content_types(),
            False,
            b"content-types",
        ),
        (
            PACKAGE_RELS_PART,
            package_rels if package_rels is not None else _package_rels(),
            True,
            b"",
        ),
        (
            DOCUMENT_PART,
            document if document is not None else DOCUMENT_XML,
            True,
            b"",
        ),
        (
            "word/_rels/document.xml.rels",
            document_rels if document_rels is not None else _document_rels(),
            True,
            b"",
        ),
        (
            "word/styles.xml",
            styles if styles is not None else STYLES_XML,
            True,
            b"",
        ),
        ("word/", b"", False, b"dir"),
    ]
    if include_binary:
        entries.append(
            (
                "word/media/image1.bin",
                b"\x00binary-payload",
                False,
                b"image",
            )
        )
    entries.extend(extra_entries)
    return _write_entries(path, entries)


def _snapshot(path: Path) -> list[tuple[object, ...]]:
    with zipfile.ZipFile(path) as archive:
        return [
            (
                info.filename,
                archive.read(info),
                info.date_time,
                info.compress_type,
                info.external_attr,
                info.create_system,
                info.comment,
            )
            for info in archive.infolist()
        ]


def test_docxpackage_alias_and_error_hierarchy() -> None:
    assert DocxPackage is DocumentPackage
    assert issubclass(DocxError, DocgenError)
    assert issubclass(InvalidPackageError, DocxError)
    assert issubclass(SaveError, DocxError)


def test_load_save_golden_fixture_preserves_all_parts(tmp_path: Path) -> None:
    original_bytes = GOLDEN.read_bytes()
    before = _snapshot(GOLDEN)

    package = DocumentPackage.load(GOLDEN)
    destination = tmp_path / "out.docx"
    package.save(destination)

    assert _snapshot(destination) == before
    assert GOLDEN.read_bytes() == original_bytes
    assert len(package.part_names()) == len(
        [entry for entry in before if not str(entry[0]).endswith("/")]
    )
    assert package.part_info(DOCUMENT_PART).content_type == MAIN_DOCUMENT_CONTENT_TYPE


def test_mutating_document_keeps_other_parts_byte_identical(
    tmp_path: Path,
) -> None:
    source = _build_docx(tmp_path / "source.docx")
    before = _snapshot(source)

    package = DocumentPackage.load(source)
    root = package.xml(DOCUMENT_PART)
    text = root.find(f".//{qn('w:t')}")
    assert text is not None
    text.text = "Changed"

    destination = tmp_path / "out.docx"
    package.save(destination)
    after = _snapshot(destination)

    assert [entry[0] for entry in after] == [entry[0] for entry in before]
    for old, new in zip(before, after, strict=True):
        if old[0] != DOCUMENT_PART:
            assert new == old
    assert after[2][1] != before[2][1]
    assert after[2][2:] == before[2][2:]

    reloaded = DocumentPackage.load(destination)
    paragraph = next(iter(reloaded.xml(DOCUMENT_PART).iter(f"{{{W_NS}}}p")))
    assert paragraph_text(paragraph) == "Changed"


def test_document_xml_c14n_sha256_roundtrip(tmp_path: Path) -> None:
    source = _build_docx(tmp_path / "source.docx")
    package = DocumentPackage.load(source)
    before = sha256_c14n(package.part(DOCUMENT_PART))

    destination = tmp_path / "out.docx"
    package.save(destination)
    reloaded = DocumentPackage.load(destination)

    assert sha256_c14n(reloaded.part(DOCUMENT_PART)) == before


def test_set_xml_roundtrip(tmp_path: Path) -> None:
    source = _build_docx(tmp_path / "source.docx")
    package = DocumentPackage.load(source)
    root = package.xml(DOCUMENT_PART)
    text = root.find(f".//{qn('w:t')}")
    assert text is not None
    text.text = "Via set_xml"
    package.set_xml(DOCUMENT_PART, root)

    destination = tmp_path / "out.docx"
    package.save(destination)
    reloaded = DocumentPackage.load(destination)
    paragraph = next(iter(reloaded.xml(DOCUMENT_PART).iter(f"{{{W_NS}}}p")))
    assert paragraph_text(paragraph) == "Via set_xml"


def test_atomic_save_failure_leaves_destination_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _build_docx(tmp_path / "source.docx")
    destination = tmp_path / "out.docx"
    destination.write_bytes(b"sentinel")

    def fail_replace(*args, **kwargs):
        raise OSError("replace gagal")

    monkeypatch.setattr(docx_io.os, "replace", fail_replace)

    package = DocumentPackage.load(source)
    with pytest.raises(SaveError):
        package.save(destination)

    assert destination.read_bytes() == b"sentinel"
    assert not list(tmp_path.glob(f".{destination.name}.*"))


def test_save_validation_failure_does_not_touch_destination(
    tmp_path: Path,
) -> None:
    source = _build_docx(tmp_path / "source.docx")
    destination = tmp_path / "out.docx"
    destination.write_bytes(b"sentinel")

    package = DocumentPackage.load(source)
    package.remove_part(DOCUMENT_PART)

    with pytest.raises(InvalidPackageError):
        package.save(destination)

    assert destination.read_bytes() == b"sentinel"
    assert not list(tmp_path.glob(f".{destination.name}.*"))


def test_content_type_for_new_part_roundtrip(tmp_path: Path) -> None:
    source = _build_docx(tmp_path / "source.docx")
    package = DocumentPackage.load(source)

    package.set_part(
        "word/media/image2.png",
        b"\x89PNG\r\n\x1a\npayload",
        content_type="image/png",
    )
    assert package.part_info("word/media/image2.png").content_type == "image/png"
    assert b'PartName="/word/media/image2.png"' in package.part(CONTENT_TYPES_PART)

    package.ensure_content_type("word/media/image2.png", "image/png")
    assert package.part(CONTENT_TYPES_PART).count(b'PartName="/word/media/image2.png"') == 1

    destination = tmp_path / "out.docx"
    package.save(destination)
    reloaded = DocumentPackage.load(destination)
    assert reloaded.has_part("word/media/image2.png")
    assert reloaded.part_info("word/media/image2.png").content_type == "image/png"


def test_relationship_roundtrip_removal_and_duplicate(tmp_path: Path) -> None:
    source = _build_docx(tmp_path / "source.docx")
    package = DocumentPackage.load(source)

    root_relationships = package.relationships("")
    assert any(
        relationship.rel_type == REL_TYPE_OFFICE_DOCUMENT and relationship.target == DOCUMENT_PART
        for relationship in root_relationships
    )
    styles_relationship = next(
        relationship
        for relationship in package.relationships(DOCUMENT_PART)
        if relationship.rel_type == REL_TYPE_STYLES
    )
    assert styles_relationship.target == "styles.xml"

    package.set_part(
        "word/media/image2.png",
        b"\x89PNG",
        content_type="image/png",
    )
    image_relationship = Relationship(
        "rId99",
        REL_TYPE_IMAGE,
        "media/image2.png",
    )
    package.add_relationship(DOCUMENT_PART, image_relationship)
    assert any(
        relationship.rel_id == "rId99" for relationship in package.relationships(DOCUMENT_PART)
    )

    with pytest.raises(PartExistsError):
        package.add_relationship(DOCUMENT_PART, image_relationship)
    with pytest.raises(PartNotFoundError):
        package.add_relationship(
            DOCUMENT_PART,
            Relationship("rId100", REL_TYPE_IMAGE, "media/missing.png"),
        )

    external = Relationship(
        "rId101",
        REL_TYPE_HYPERLINK,
        "https://example.com",
        "External",
    )
    package.add_relationship(DOCUMENT_PART, external)

    destination = tmp_path / "out.docx"
    package.save(destination)
    reloaded = DocumentPackage.load(destination)
    loaded_relationships = {
        relationship.rel_id: relationship for relationship in reloaded.relationships(DOCUMENT_PART)
    }
    assert loaded_relationships["rId99"].target == "media/image2.png"
    assert loaded_relationships["rId101"].target_mode == "External"

    reloaded.remove_relationship(DOCUMENT_PART, "rId99")
    assert "rId99" not in {
        relationship.rel_id for relationship in reloaded.relationships(DOCUMENT_PART)
    }

    reloaded.remove_part("word/media/image2.png")
    assert not reloaded.has_part("word/media/image2.png")
    assert b'PartName="/word/media/image2.png"' not in reloaded.part(CONTENT_TYPES_PART)
    reloaded.save(destination)
    DocumentPackage.load(destination)


def test_remove_part_removes_incoming_relationship(tmp_path: Path) -> None:
    source = _build_docx(tmp_path / "source.docx")
    package = DocumentPackage.load(source)
    package.set_part(
        "word/media/image3.png",
        b"\x89PNG",
        content_type="image/png",
    )
    package.add_relationship(
        DOCUMENT_PART,
        Relationship("rId102", REL_TYPE_IMAGE, "media/image3.png"),
    )

    package.remove_part("word/media/image3.png")

    assert not any(
        relationship.rel_id == "rId102" for relationship in package.relationships(DOCUMENT_PART)
    )
    assert b'PartName="/word/media/image3.png"' not in package.part(CONTENT_TYPES_PART)

    destination = tmp_path / "out.docx"
    package.save(destination)
    DocumentPackage.load(destination)


def test_validate_rejects_missing_content_type(tmp_path: Path) -> None:
    path = _build_docx(
        tmp_path / "bad.docx",
        content_types=_content_types(include_bin=False),
    )

    with pytest.raises(InvalidPackageError):
        DocumentPackage.load(path)

    package = DocumentPackage.load(path, validate=False)
    with pytest.raises(InvalidPackageError):
        package.validate()


def test_validate_rejects_missing_relationship_target(tmp_path: Path) -> None:
    path = _build_docx(
        tmp_path / "bad.docx",
        document_rels=_document_rels("missing-styles.xml"),
    )
    with pytest.raises(InvalidPackageError):
        DocumentPackage.load(path)


def test_validate_rejects_missing_required_part(tmp_path: Path) -> None:
    path = _build_docx(tmp_path / "bad.docx")
    package = DocumentPackage.load(path, validate=False)
    package.remove_part(CONTENT_TYPES_PART)
    with pytest.raises(InvalidPackageError):
        package.validate()


def test_invalid_zip_raises_package_error(tmp_path: Path) -> None:
    path = tmp_path / "not.docx"
    path.write_bytes(b"bukan zip")
    with pytest.raises(PackageError):
        DocumentPackage.load(path)


def test_duplicate_zip_entry_raises_package_error(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.docx"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", DOCUMENT_XML)
            archive.writestr("word/document.xml", DOCUMENT_XML)
    with pytest.raises(PackageError):
        DocumentPackage.load(path)


def test_part_operation_errors(tmp_path: Path) -> None:
    source = _build_docx(tmp_path / "source.docx")
    package = DocumentPackage.load(source)

    for operation in (package.part, package.xml, package.part_info):
        with pytest.raises(PartNotFoundError):
            operation("word/missing.xml")

    with pytest.raises(PartNotFoundError):
        package.remove_part("word/missing.xml")

    with pytest.raises(PartNotFoundError):
        package.remove_relationship(DOCUMENT_PART, "rIdMissing")
