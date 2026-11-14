"""Tes edge case OPC/package DOCX: nama part, rels, content type, dan save."""

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from autooffice.docx.package import (
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    PACKAGE_RELS_PART,
    REL_TYPE_IMAGE,
    REL_TYPE_OFFICE_DOCUMENT,
    REL_TYPE_STYLES,
    DocumentPackage,
    InvalidPackageError,
    PackageError,
    PartExistsError,
    PartNotFoundError,
    Relationship,
    XmlError,
)
from autooffice.docx.package.io import ZipEntry
from autooffice.docx.package.xml import qn

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
STYLES_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
RELS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"

DOCUMENT_XML = (
    f'<w:document xmlns:w="{W_NS}"><w:body>'
    "<w:p><w:r><w:t>Hello</w:t></w:r></w:p>"
    "</w:body></w:document>"
).encode()
STYLES_XML = f'<w:styles xmlns:w="{W_NS}"/>'.encode()


def _entry(name: str, data: bytes = b"", *, directory: bool = False) -> ZipEntry:
    info = zipfile.ZipInfo(name, date_time=(2020, 1, 2, 3, 4, 6))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    info.create_system = 3
    if directory:
        info.external_attr = 0o40755 << 16
    return ZipEntry(name, data, info)


def _content_types(
    *,
    defaults: tuple[tuple[str, str], ...] = (
        ("rels", RELS_CONTENT_TYPE),
        ("xml", "application/xml"),
        ("bin", "application/octet-stream"),
    ),
    overrides: tuple[tuple[str, str], ...] = (
        (DOCUMENT_PART, DOCUMENT_CONTENT_TYPE),
        ("word/styles.xml", STYLES_CONTENT_TYPE),
    ),
    extra: str = "",
) -> bytes:
    default_xml = "".join(
        f'<Default Extension="{extension}" ContentType="{content_type}"/>'
        for extension, content_type in defaults
    )
    override_xml = "".join(
        f'<Override PartName="/{part}" ContentType="{content_type}"/>'
        for part, content_type in overrides
    )
    return (f'<Types xmlns="{CT_NS}">{default_xml}{override_xml}{extra}</Types>').encode()


def _package_rels() -> bytes:
    return (
        f'<Relationships xmlns="{PR_NS}">'
        f'<Relationship Id="rId1" Type="{REL_TYPE_OFFICE_DOCUMENT}" '
        f'Target="{DOCUMENT_PART}"/>'
        "</Relationships>"
    ).encode()


def _document_rels(target: str = "styles.xml") -> bytes:
    return (
        f'<Relationships xmlns="{PR_NS}">'
        f'<Relationship Id="rId2" Type="{REL_TYPE_STYLES}" Target="{target}"/>'
        "</Relationships>"
    ).encode()


def _entries() -> dict[str, bytes]:
    return {
        CONTENT_TYPES_PART: _content_types(),
        PACKAGE_RELS_PART: _package_rels(),
        DOCUMENT_PART: DOCUMENT_XML,
        "word/_rels/document.xml.rels": _document_rels(),
        "word/styles.xml": STYLES_XML,
        "word/media/image1.bin": b"\x00image",
        "word/": b"",
    }


def _package(
    *,
    replace: dict[str, bytes] | None = None,
    extra: tuple[tuple[str, bytes], ...] = (),
) -> DocumentPackage:
    entries = _entries()
    if replace:
        entries.update(replace)
    entries.update(dict(extra))
    return DocumentPackage(
        [_entry(name, data, directory=name.endswith("/")) for name, data in entries.items()]
    )


def _rels(payload: str) -> bytes:
    return f'<Relationships xmlns="{PR_NS}">{payload}</Relationships>'.encode()


# ---------------------------------------------------------------------------
# Konstruktor, save, dan payload
# ---------------------------------------------------------------------------


def test_constructor_rejects_duplicate_entry_name() -> None:
    entries = [_entry(DOCUMENT_PART, DOCUMENT_XML), _entry(DOCUMENT_PART, DOCUMENT_XML)]

    with pytest.raises(PackageError, match="Part duplikat"):
        DocumentPackage(entries)


def test_non_atomic_save_roundtrip_and_unchanged_payload_is_reused(tmp_path: Path) -> None:
    package = _package()
    root = package.xml(DOCUMENT_PART)
    original = package.part(DOCUMENT_PART)
    assert root.tag == qn("w:document")
    assert package.part(DOCUMENT_PART) == original

    destination = tmp_path / "out.docx"
    package.save(destination, atomic=False)
    reloaded = DocumentPackage.load(destination)

    assert reloaded.part(DOCUMENT_PART) == original
    assert destination.is_file()


def test_set_part_reuses_existing_info_and_allows_missing_content_type(
    tmp_path: Path,
) -> None:
    package = _package()
    before = package.part_info(DOCUMENT_PART)
    changed_document = DOCUMENT_XML.replace(b"Hello", b"Changed")

    package.set_part(DOCUMENT_PART, changed_document)
    package.set_part("word/custom.bin", b"custom")

    assert package.part(DOCUMENT_PART) == changed_document
    assert package.part_info(DOCUMENT_PART).size == len(changed_document)
    assert package.part_info(DOCUMENT_PART).content_type == before.content_type
    assert package.part_info("word/custom.bin").content_type == "application/octet-stream"

    destination = tmp_path / "out.docx"
    package.save(destination)
    assert DocumentPackage.load(destination).part("word/custom.bin") == b"custom"


def test_set_xml_accepts_element_tree_and_rejects_non_element() -> None:
    package = _package()
    root = package.xml(DOCUMENT_PART)
    package.set_xml(DOCUMENT_PART, etree.ElementTree(root))
    text = root.find(f".//{qn('w:t')}")
    assert text is not None
    text.text = "Lewat ElementTree"
    package.set_xml(DOCUMENT_PART, root)

    assert b"Lewat ElementTree" in package.part(DOCUMENT_PART)

    with pytest.raises(XmlError, match="membutuhkan elemen XML"):
        package.set_xml(DOCUMENT_PART, None)  # type: ignore[arg-type]


def test_part_info_without_extension_has_no_content_type() -> None:
    package = _package(extra=(("word/README", b"docs"),))

    part = package.part_info("word/README")

    assert part.size == len(b"docs")
    assert part.content_type is None


def test_after_save_clears_dirty_and_recomputes_hash(tmp_path: Path) -> None:
    package = _package()
    root = package.xml(DOCUMENT_PART)
    text = root.find(f".//{qn('w:t')}")
    assert text is not None
    text.text = "Sesudah save"
    package.set_xml(DOCUMENT_PART, root)

    destination = tmp_path / "out.docx"
    package.save(destination)

    assert b"Sesudah save" in package.part(DOCUMENT_PART)
    assert package._dirty == set()


# ---------------------------------------------------------------------------
# Content types
# ---------------------------------------------------------------------------


def test_ensure_content_type_rejects_invalid_input() -> None:
    package = _package()

    with pytest.raises(PackageError, match="tidak memiliki content type"):
        package.ensure_content_type(CONTENT_TYPES_PART, "application/xml")
    with pytest.raises(PackageError, match="Content type kosong"):
        package.ensure_content_type("word/x.xml", "  ")


def test_ensure_content_type_updates_override_and_uses_matching_default() -> None:
    package = _package(extra=(("word/extra.xml", b"<x/>"),))

    package.ensure_content_type(DOCUMENT_PART, "application/custom+xml")
    package.ensure_content_type("word/extra.xml", "application/xml")

    assert package.part_info(DOCUMENT_PART).content_type == "application/custom+xml"
    assert package.part(CONTENT_TYPES_PART).count(b'PartName="/word/document.xml"') == 1
    assert b'PartName="/word/extra.xml"' not in package.part(CONTENT_TYPES_PART)


def test_part_info_without_content_types_part_returns_none() -> None:
    package = _package()
    package.remove_part(CONTENT_TYPES_PART)

    assert package.part_info(DOCUMENT_PART).content_type is None


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


def test_relationships_missing_rels_and_naming_variants() -> None:
    package = _package()

    assert package.relationships("word/styles.xml") == ()
    assert package.relationships(PACKAGE_RELS_PART) == package.relationships("")
    assert package.relationships("_rels/.rels") == package.relationships(PACKAGE_RELS_PART)
    assert package.relationships(DOCUMENT_PART) == package.relationships(
        "word/_rels/document.xml.rels"
    )


@pytest.mark.parametrize(
    ("relationship", "message"),
    [
        (Relationship("", REL_TYPE_IMAGE, "media/image1.bin"), "Id tidak boleh kosong"),
        (Relationship("rIdX", "", "media/image1.bin"), "Type kosong"),
        (Relationship("rIdX", REL_TYPE_IMAGE, ""), "Target kosong"),
        (
            Relationship("rIdX", REL_TYPE_IMAGE, "media/image1.bin", "Internal"),
            "TargetMode tidak dikenal",
        ),
    ],
)
def test_add_relationship_rejects_invalid_relationship_fields(
    relationship: Relationship,
    message: str,
) -> None:
    package = _package()

    with pytest.raises(PackageError, match=message):
        package.add_relationship(DOCUMENT_PART, relationship)


def test_add_relationship_requires_existing_source_part() -> None:
    package = _package()

    with pytest.raises(PartNotFoundError, match="Source relationship tidak ditemukan"):
        package.add_relationship(
            "word/missing.xml",
            Relationship("rIdX", REL_TYPE_IMAGE, "media/image1.bin"),
        )


def test_add_relationship_creates_new_rels_part_and_accepts_absolute_target() -> None:
    package = _package(extra=(("word/custom.xml", b"<x/>"),))

    package.add_relationship(
        "word/custom.xml",
        Relationship("rId1", REL_TYPE_IMAGE, "/word/media/image1.bin"),
    )
    relationships = package.relationships("word/custom.xml")

    assert [rel.rel_id for rel in relationships] == ["rId1"]
    assert relationships[0].target == "/word/media/image1.bin"
    assert package.has_part("word/_rels/custom.xml.rels")


def test_add_relationship_resolves_fragment_and_encoded_target() -> None:
    package = _package()

    package.add_relationship(
        DOCUMENT_PART,
        Relationship("rIdFrag", REL_TYPE_STYLES, "styles.xml#bagian?x=1"),
    )
    package.add_relationship(
        DOCUMENT_PART,
        Relationship("rIdEncoded", REL_TYPE_IMAGE, "media/image%31.bin"),
    )

    ids = {rel.rel_id for rel in package.relationships(DOCUMENT_PART)}
    assert ids == {"rId2", "rIdFrag", "rIdEncoded"}


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("..\\luar.xml", "backslash"),
        ("?x=1", "kosong setelah fragment"),
        ("/../luar.xml", "keluar package"),
        ("../../luar.xml", "keluar package"),
    ],
)
def test_add_relationship_rejects_invalid_targets(target: str, message: str) -> None:
    package = _package()

    with pytest.raises(InvalidPackageError, match=message):
        package.add_relationship(
            DOCUMENT_PART,
            Relationship("rIdBad", REL_TYPE_IMAGE, target),
        )


def test_resolve_target_rejects_empty_target() -> None:
    package = _package()

    with pytest.raises(InvalidPackageError, match="Target relationship kosong"):
        package._resolve_target(DOCUMENT_PART, "")


def test_add_relationship_rejects_invalid_rels_root() -> None:
    package = _package(
        extra=(
            ("word/custom.xml", b"<x/>"),
            ("word/_rels/custom.xml.rels", b"<bukan/>"),
        )
    )

    with pytest.raises(InvalidPackageError, match="Root rels tidak valid"):
        package.add_relationship(
            "word/custom.xml",
            Relationship("rId1", REL_TYPE_IMAGE, "media/image1.bin"),
        )


def test_remove_relationship_requires_rels_part_and_valid_root() -> None:
    package = _package()

    with pytest.raises(PartNotFoundError, match="Part rels tidak ditemukan"):
        package.remove_relationship("word/styles.xml", "rIdX")

    broken = _package(extra=(("word/_rels/custom.xml.rels", b"<bukan/>"),))
    with pytest.raises(InvalidPackageError, match="Root rels tidak valid"):
        broken.remove_relationship("word/custom.xml", "rIdX")


def test_relationship_source_can_be_the_rels_part_name() -> None:
    package = _package()

    package.add_relationship(
        "word/_rels/document.xml.rels",
        Relationship("rIdViaRels", REL_TYPE_IMAGE, "media/image1.bin"),
    )

    assert any(rel.rel_id == "rIdViaRels" for rel in package.relationships(DOCUMENT_PART))


# ---------------------------------------------------------------------------
# Validasi nama part
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "message"),
    [
        (123, "Nama part tidak boleh kosong"),
        ("", "Nama part tidak boleh kosong"),
        ("word/", "tidak boleh berakhir dengan"),
        ("/word/x.xml", "absolut tidak valid"),
        ("C:/x.xml", "absolut tidak valid"),
        ("word\\x.xml", "absolut tidak valid"),
        ("word//x.xml", "tidak valid"),
        ("word/./x.xml", "tidak valid"),
        ("word/../x.xml", "tidak valid"),
    ],
)
def test_set_part_rejects_invalid_part_names(name: object, message: str) -> None:
    package = _package()

    with pytest.raises(PackageError, match=message):
        package.set_part(name, b"x")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("entry_name", "message"),
    [
        ("../", "Nama part tidak valid"),
        ("/", "Nama part tidak valid"),
        ("/absolute.xml", "absolut tidak valid"),
        ("word//broken.xml", "tidak valid"),
    ],
)
def test_validate_rejects_invalid_zip_entry_names(
    entry_name: str,
    message: str,
) -> None:
    package = DocumentPackage(
        [
            *(
                _entry(name, data, directory=name.endswith("/"))
                for name, data in _entries().items()
            ),
            _entry(entry_name, b"", directory=True),
        ]
    )

    with pytest.raises(InvalidPackageError, match=message):
        package.validate()


# ---------------------------------------------------------------------------
# Validasi content types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content_types", "message"),
    [
        (_content_types(defaults=()), "Content type tidak ditemukan"),
        (
            _content_types(
                defaults=(
                    ("rels", RELS_CONTENT_TYPE),
                    ("xml", "application/xml"),
                    ("xml", "application/other"),
                )
            ),
            "Default content type duplikat",
        ),
        (
            _content_types(extra='<Default Extension="" ContentType="x"/>'),
            "Default content type tidak lengkap",
        ),
        (
            _content_types(extra='<Override PartName="word/x.xml" ContentType="x"/>'),
            "Override content type tidak lengkap",
        ),
        (
            _content_types(
                extra=('<Override PartName="/word/styles.xml" ContentType="application/other"/>')
            ),
            "Override content type duplikat",
        ),
        (
            _content_types(extra='<Bogus ContentType="x"/>'),
            "Elemen content types tidak dikenal",
        ),
        (
            _content_types(extra='<Override PartName="/word/../x.xml" ContentType="x"/>'),
            "Nama part tidak valid",
        ),
        (
            _content_types(extra='<Override PartName="/word/missing.xml" ContentType="x"/>'),
            "Override content type untuk part yang hilang",
        ),
        (b"<Types", "tidak valid"),
        (b"<bukan/>", "bukan Types"),
    ],
)
def test_validate_rejects_bad_content_types(
    content_types: bytes,
    message: str,
) -> None:
    package = _package(replace={CONTENT_TYPES_PART: content_types})

    with pytest.raises(InvalidPackageError, match=message):
        package.validate()


def test_validate_ignores_comment_in_content_types() -> None:
    content_types = _content_types(extra="<!-- komentar -->")
    package = _package(
        replace={
            CONTENT_TYPES_PART: content_types,
        }
    )
    part_names_before = package.part_names()

    assert package.validate() is None

    assert package.part(CONTENT_TYPES_PART) == content_types
    assert package.part_names() == part_names_before


# ---------------------------------------------------------------------------
# Validasi XML, root, dan rels
# ---------------------------------------------------------------------------


def test_validate_rejects_broken_xml_part() -> None:
    package = _package(extra=(("word/broken.xml", b"<broken"),))

    with pytest.raises(InvalidPackageError, match="Part XML tidak valid"):
        package.validate()


def test_validate_rejects_wrong_document_root() -> None:
    package = _package(replace={DOCUMENT_PART: b"<not-document/>"})

    with pytest.raises(InvalidPackageError, match="bukan w:document"):
        package.validate()


@pytest.mark.parametrize(
    ("rels_name", "payload", "message"),
    [
        (
            "word/_rels/styles.xml.rels",
            b"<bukan/>",
            "Root rels tidak valid",
        ),
        (
            "word/_rels/styles.xml.rels",
            _rels('<Relationship Id="rId1" Type="x" Target="styles.xml" TargetMode="Internal"/>'),
            "TargetMode tidak dikenal",
        ),
        (
            "word/_rels/styles.xml.rels",
            _rels('<Relationship Id="rId1" Type="x" Target="../../luar.xml"/>'),
            "keluar package",
        ),
        (
            "word/_rels/styles.xml.rels",
            _rels('<Relationship Id="rId1" Type="x" Target="missing.xml"/>'),
            "Target relationship tidak ditemukan",
        ),
    ],
)
def test_validate_rejects_bad_document_rels(
    rels_name: str,
    payload: bytes,
    message: str,
) -> None:
    package = _package(extra=((rels_name, payload),))

    with pytest.raises(InvalidPackageError, match=message):
        package.validate()


def test_validate_rejects_orphan_rels_without_source() -> None:
    package = _package(
        extra=(("word/_rels/ghost.xml.rels", _rels("")),),
    )

    with pytest.raises(InvalidPackageError, match="Rels yatim tanpa source part"):
        package.validate()


@pytest.mark.parametrize(
    ("rels_name", "message"),
    [
        ("word/_rels/not_rels/x.rels", "Path rels tidak valid"),
        ("word/_rels/.rels", "Nama rels tidak valid"),
    ],
)
def test_validate_rejects_invalid_rels_paths(rels_name: str, message: str) -> None:
    package = _package(extra=((rels_name, _rels("")),))

    with pytest.raises(InvalidPackageError, match=message):
        package.validate()


def test_remove_part_skips_malformed_and_unrelated_relationships() -> None:
    package = _package(
        extra=(
            ("word/_rels/broken.xml.rels", b"<bukan/>"),
            (
                "word/_rels/styles.xml.rels",
                _rels(
                    "<Bogus/>"
                    '<Relationship Id="rIdEmpty" Type="x"/>'
                    '<Relationship Id="rIdSlash" Type="x" Target="..\\luar.xml"/>'
                    '<Relationship Id="rIdExternal" Type="x" '
                    'Target="https://example.com" TargetMode="External"/>'
                ),
            ),
        )
    )

    package.remove_part("word/media/image1.bin")

    assert not package.has_part("word/media/image1.bin")
    assert package.has_part("word/styles.xml")


def test_remove_part_without_content_types_part_is_safe() -> None:
    package = _package()
    package.remove_part(CONTENT_TYPES_PART)

    package.remove_part("word/styles.xml")

    assert not package.has_part("word/styles.xml")


# ---------------------------------------------------------------------------
# Path/rels helpers
# ---------------------------------------------------------------------------


def test_rels_name_for_root_and_nested_sources() -> None:
    package = _package()

    assert package._rels_name("") == PACKAGE_RELS_PART
    assert package._rels_name(PACKAGE_RELS_PART) == PACKAGE_RELS_PART
    assert package._rels_name("_rels/.rels") == "_rels/.rels"
    assert package._rels_name("word/document.xml") == "word/_rels/document.xml.rels"
    assert package._rels_name("styles.xml") == "_rels/styles.xml.rels"


def test_part_operations_report_missing_parts() -> None:
    package = _package()

    for operation in (package.part, package.xml, package.part_info):
        with pytest.raises(PartNotFoundError, match="Part tidak ditemukan"):
            operation("word/missing.xml")

    with pytest.raises(PartExistsError, match="Relationship Id sudah ada"):
        package.add_relationship(
            DOCUMENT_PART,
            Relationship("rId2", REL_TYPE_IMAGE, "/word/media/image1.bin"),
        )


def test_saved_package_validates_and_directory_entries_are_ignored(tmp_path: Path) -> None:
    package = _package()
    destination = tmp_path / "out.docx"

    package.save(destination)

    assert "word/" not in package.part_names()
    assert "word/" in zipfile.ZipFile(destination).namelist()


def test_save_non_atomic_uses_direct_writer(tmp_path: Path) -> None:
    package = _package()
    destination = tmp_path / "nested" / "out.docx"

    package.save(destination, atomic=False)

    assert zipfile.is_zipfile(io.BytesIO(destination.read_bytes()))
    assert DocumentPackage.load(destination).has_part(DOCUMENT_PART)
