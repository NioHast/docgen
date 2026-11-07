"""Tes eksportir DOCX -> DOTX."""

from __future__ import annotations

import codecs
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

import export_dotx as api

CONTENT_TYPES_PART = "[Content_Types].xml"
DOCUMENT_PART = "word/document.xml"
CONTENT_TYPES_NS = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W_NS = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
)
CORE_NS = (
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
)
DC_NS = "http://purl.org/dc/elements/1.1/"
APP_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)

STYLES_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.styles+xml"
)
CORE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-package.core-properties+xml"
)
APP_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "extended-properties+xml"
)


# ---------------------------------------------------------------------------
# Pembuat fixture


def _attr(name: str, value: str, quote: str) -> str:
    return f"{name}={quote}{value}{quote}"


def make_content_types(
    document_type: str = api.DOCUMENT_CONTENT_TYPE,
    *,
    quote: str = '"',
    spaced: bool = True,
    include_document_override: bool = True,
) -> bytes:
    """Buat [Content_Types].xml minimal dengan gaya penulisan tertentu."""

    close = " />" if spaced else "/>"
    overrides = [
        ("/word/styles.xml", STYLES_CONTENT_TYPE),
        ("/docProps/core.xml", CORE_CONTENT_TYPE),
        ("/docProps/app.xml", APP_CONTENT_TYPE),
    ]
    if include_document_override:
        overrides.insert(1, ("/word/document.xml", document_type))

    override_xml = "".join(
        f"<Override {_attr('PartName', part, quote)} "
        f"{_attr('ContentType', content_type, quote)}{close}"
        for part, content_type in overrides
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Types xmlns={quote}{CONTENT_TYPES_NS}{quote}>'
        f"<Default {_attr('Extension', 'rels', quote)} "
        f"{_attr('ContentType', 'application/vnd.openxmlformats-package.relationships+xml', quote)}{close}"
        f"<Default {_attr('Extension', 'xml', quote)} "
        f"{_attr('ContentType', 'application/xml', quote)}{close}"
        f"<Default {_attr('Extension', 'png', quote)} "
        f"{_attr('ContentType', 'image/png', quote)}{close}"
        f"{override_xml}"
        "</Types>"
    ).encode("utf-8")


def make_document(text: str = "Halo") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document xmlns:w="{W_NS}"><w:body>'
        f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
        "</w:body></w:document>"
    ).encode("utf-8")


def standard_parts(
    *,
    content_types: bytes | None = None,
    document: bytes | None = None,
) -> dict[str, bytes]:
    return {
        CONTENT_TYPES_PART: (
            content_types
            if content_types is not None
            else make_content_types()
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{REL_NS}"/>'
        ).encode("utf-8"),
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<cp:coreProperties xmlns:cp="{CORE_NS}" '
            f'xmlns:dc="{DC_NS}"><dc:title>Tes</dc:title>'
            "</cp:coreProperties>"
        ).encode("utf-8"),
        "docProps/app.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Properties xmlns="{APP_NS}"><Application>Tes</Application>'
            "</Properties>"
        ).encode("utf-8"),
        DOCUMENT_PART: (
            document if document is not None else make_document()
        ),
        "word/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:styles xmlns:w="{W_NS}"/>'
        ).encode("utf-8"),
        "word/media/image1.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00",
    }


def write_zip(path: Path, parts: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in parts.items():
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return path


def make_package(
    path: Path,
    *,
    content_types: bytes | None = None,
    document: bytes | None = None,
) -> Path:
    return write_zip(
        path,
        standard_parts(content_types=content_types, document=document),
    )


# ---------------------------------------------------------------------------
# Pembaca hasil


def read_part(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(name)


def part_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def document_content_type(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read(CONTENT_TYPES_PART))

    matches = []
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        if element.tag.rsplit("}", 1)[-1] != "Override":
            continue
        for name, value in element.attrib.items():
            if (
                name.rsplit("}", 1)[-1].lower() == "partname"
                and value.lower() == "/word/document.xml"
            ):
                for key, content_type in element.attrib.items():
                    if key.rsplit("}", 1)[-1].lower() == "contenttype":
                        matches.append(content_type)
    assert len(matches) == 1
    return matches[0]


def convert(source: Path, output: Path) -> api.ExportReport:
    return api.export_dotx(source, output)


# ---------------------------------------------------------------------------
# Tes utama


def test_content_type_dokumen_menjadi_template(tmp_path):
    source = make_package(tmp_path / "sumber.docx")
    output = tmp_path / "hasil.dotx"

    report = convert(source, output)

    assert document_content_type(output) == api.TEMPLATE_CONTENT_TYPE
    assert report.content_type_changed is True
    assert report.parts == len(part_names(source))


def test_jumlah_dan_urutan_part_tetap_sama(tmp_path):
    source = make_package(tmp_path / "sumber.docx")
    output = tmp_path / "hasil.dotx"

    convert(source, output)

    assert part_names(output) == part_names(source)


def test_document_xml_identik_byte_per_byte(tmp_path):
    source = make_package(tmp_path / "sumber.docx")
    output = tmp_path / "hasil.dotx"

    convert(source, output)

    assert read_part(output, DOCUMENT_PART) == read_part(
        source, DOCUMENT_PART
    )


def test_part_selain_content_types_identik(tmp_path):
    source = make_package(tmp_path / "sumber.docx")
    output = tmp_path / "hasil.dotx"

    convert(source, output)

    for name in part_names(source):
        if name == CONTENT_TYPES_PART:
            continue
        assert read_part(output, name) == read_part(source, name), name


def test_content_types_hanya_mengubah_satu_nilai(tmp_path):
    source = make_package(tmp_path / "sumber.docx")
    output = tmp_path / "hasil.dotx"

    convert(source, output)

    original = read_part(source, CONTENT_TYPES_PART)
    expected = original.replace(
        api.DOCUMENT_CONTENT_TYPE.encode("utf-8"),
        api.TEMPLATE_CONTENT_TYPE.encode("utf-8"),
        1,
    )
    assert read_part(output, CONTENT_TYPES_PART) == expected


def test_idempoten_byte_sama(tmp_path):
    source = make_package(tmp_path / "sumber.docx")
    first = tmp_path / "pertama.dotx"
    second = tmp_path / "kedua.dotx"

    first_report = convert(source, first)
    second_report = convert(first, second)

    assert first_report.content_type_changed is True
    assert second_report.content_type_changed is False
    assert first.read_bytes() == second.read_bytes()
    assert part_names(first) == part_names(second)
    for name in part_names(first):
        assert read_part(first, name) == read_part(second, name), name


def test_input_tidak_berubah(tmp_path):
    source = make_package(tmp_path / "sumber.docx")
    before = source.read_bytes()
    output = tmp_path / "hasil.dotx"

    convert(source, output)

    assert source.read_bytes() == before


def test_cli_memakai_opsi_in_dan_out(tmp_path, capsys):
    source = make_package(tmp_path / "sumber.docx")
    output = tmp_path / "hasil.dotx"

    assert api.main(["--in", str(source), "--out", str(output)]) == 0

    captured = capsys.readouterr()
    assert "DOTX:" in captured.out
    assert "template" in captured.out
    assert output.exists()
    assert document_content_type(output) == api.TEMPLATE_CONTENT_TYPE


def test_direktori_output_dibuat(tmp_path):
    source = make_package(tmp_path / "sumber.docx")
    output = tmp_path / "baru" / "nested" / "hasil.dotx"

    convert(source, output)

    assert output.exists()
    assert document_content_type(output) == api.TEMPLATE_CONTENT_TYPE


def test_dotx_yang_sudah_template_tidak_diubah(tmp_path):
    source = make_package(
        tmp_path / "sumber.dotx",
        content_types=make_content_types(api.TEMPLATE_CONTENT_TYPE),
    )
    output = tmp_path / "hasil.dotx"

    report = convert(source, output)

    assert report.content_type_changed is False
    assert read_part(output, CONTENT_TYPES_PART) == read_part(
        source, CONTENT_TYPES_PART
    )
    for name in part_names(source):
        if name == CONTENT_TYPES_PART:
            continue
        assert read_part(output, name) == read_part(source, name), name


def test_timestamp_zip_dibuat_tetap(tmp_path):
    source = make_package(tmp_path / "sumber.docx")
    output = tmp_path / "hasil.dotx"

    convert(source, output)

    with zipfile.ZipFile(output) as archive:
        assert {
            info.date_time for info in archive.infolist()
        } == {api.FIXED_ZIP_DATETIME}


def test_gaya_kutip_dan_urutan_atribut_lain(tmp_path):
    custom = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
        f"<Types xmlns='{CONTENT_TYPES_NS}'>"
        "<Default Extension='rels' "
        "ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
        f"<Override ContentType='{api.DOCUMENT_CONTENT_TYPE}' "
        "PartName='/word/document.xml'/>"
        "</Types>"
    ).encode("utf-8")
    source = make_package(tmp_path / "sumber.docx", content_types=custom)
    output = tmp_path / "hasil.dotx"

    convert(source, output)

    expected = custom.replace(
        api.DOCUMENT_CONTENT_TYPE.encode("utf-8"),
        api.TEMPLATE_CONTENT_TYPE.encode("utf-8"),
        1,
    )
    assert read_part(output, CONTENT_TYPES_PART) == expected
    assert document_content_type(output) == api.TEMPLATE_CONTENT_TYPE


def test_bom_utf8_dipertahankan(tmp_path):
    custom = codecs.BOM_UTF8 + make_content_types()
    source = make_package(tmp_path / "sumber.docx", content_types=custom)
    output = tmp_path / "hasil.dotx"

    convert(source, output)

    converted = read_part(output, CONTENT_TYPES_PART)
    assert converted.startswith(codecs.BOM_UTF8)
    expected = custom.replace(
        api.DOCUMENT_CONTENT_TYPE.encode("utf-8"),
        api.TEMPLATE_CONTENT_TYPE.encode("utf-8"),
        1,
    )
    assert converted == expected


# ---------------------------------------------------------------------------
# Tes penolakan input


@pytest.mark.parametrize(
    "case",
    [
        "bukan-zip",
        "tanpa-content-types",
        "tanpa-document",
        "tanpa-override",
        "content-type-asing",
        "document-rusak",
        "content-types-rusak",
    ],
)
def test_input_tidak_valid_ditolak(tmp_path, capsys, case):
    source = tmp_path / "rusak.docx"
    output = tmp_path / "hasil.dotx"

    if case == "bukan-zip":
        source.write_bytes(b"ini bukan berkas ZIP")
    else:
        parts = standard_parts()
        if case == "tanpa-content-types":
            parts.pop(CONTENT_TYPES_PART)
        elif case == "tanpa-document":
            parts.pop(DOCUMENT_PART)
        elif case == "tanpa-override":
            parts[CONTENT_TYPES_PART] = make_content_types(
                include_document_override=False
            )
        elif case == "content-type-asing":
            parts[CONTENT_TYPES_PART] = make_content_types(
                "application/vnd.ms-word.document.macroEnabled.main+xml"
            )
        elif case == "document-rusak":
            parts[DOCUMENT_PART] = b"<w:document"
        elif case == "content-types-rusak":
            parts[CONTENT_TYPES_PART] = b"<Types"
        else:  # pragma: no cover - jaga-jaga bila daftar berubah
            raise AssertionError(case)
        write_zip(source, parts)

    assert api.main(["--in", str(source), "--out", str(output)]) == 1

    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert not output.exists()


def test_output_lama_tidak_rusak_saat_input_gagal(tmp_path, capsys):
    source = make_package(
        tmp_path / "rusak.docx", document=b"<w:document"
    )
    output = tmp_path / "hasil.dotx"
    output.write_bytes(b"output lama")

    assert api.main(["--in", str(source), "--out", str(output)]) == 1

    assert output.read_bytes() == b"output lama"


def test_input_tidak_ada(tmp_path, capsys):
    output = tmp_path / "hasil.dotx"

    assert (
        api.main(
            [
                "--in",
                str(tmp_path / "tidak-ada.docx"),
                "--out",
                str(output),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert not output.exists()


# ---------------------------------------------------------------------------
# Berkas nyata dari repositori


REFERENCE = Path(__file__).resolve().parents[1] / "reference.docx"


@pytest.mark.skipif(
    not REFERENCE.exists(), reason="reference.docx tidak tersedia"
)
def test_reference_docx_bisa_diekspor(tmp_path):
    output = tmp_path / "reference.dotx"

    report = convert(REFERENCE, output)

    assert document_content_type(output) == api.TEMPLATE_CONTENT_TYPE
    assert report.parts == len(part_names(REFERENCE))
    assert report.document_bytes == len(
        read_part(REFERENCE, DOCUMENT_PART)
    )
    for name in part_names(REFERENCE):
        if name == CONTENT_TYPES_PART:
            continue
        assert read_part(output, name) == read_part(REFERENCE, name), name
