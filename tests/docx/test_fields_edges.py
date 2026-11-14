"""Tes edge case parser, builder, dan settings field WordprocessingML."""

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from lxml import etree

import autooffice.docx.package.fields as fields_module
from autooffice.docx.package.fields import (
    FIELD_NAME_RE,
    Field,
    FieldError,
    FieldKind,
    FieldPosition,
    ensure_no_blank_page_after_toc,
    field_has_result,
    field_instruction,
    field_kind,
    field_marker_kind,
    field_name,
    field_result_text,
    field_text_ranges,
    has_field,
    insert_field,
    insert_pageref,
    insert_seq,
    insert_toc,
    is_bold_exempt,
    is_field_run,
    iter_field_instructions,
    iter_field_markers,
    iter_field_runs,
    iter_fields_in_root,
    strip_update_fields,
    update_fields_enabled,
)
from autooffice.docx.package.package import (
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    PACKAGE_RELS_PART,
    REL_TYPE_OFFICE_DOCUMENT,
    REL_TYPE_STYLES,
    DocumentPackage,
)
from autooffice.docx.package.paragraphs import paragraph_text
from autooffice.docx.package.xml import qn

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

RELS_CONTENT_TYPE = "application/vnd.openxmlformats-package.relationships+xml"
DOCUMENT_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
STYLES_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"

STYLES_XML = (
    f'<w:styles xmlns:w="{W_NS}">'
    '<w:style w:type="paragraph" w:styleId="Heading1">'
    '<w:name w:val="heading 1"/></w:style></w:styles>'
).encode()


def _root(fragment: str) -> etree._Element:
    return etree.fromstring(f'<w:root xmlns:w="{W_NS}">{fragment}</w:root>')


def _paragraph(fragment: str) -> etree._Element:
    return etree.fromstring(f'<w:p xmlns:w="{W_NS}">{fragment}</w:p>')


def _text_paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def _content_types(extra: str = "") -> bytes:
    return (
        f'<Types xmlns="{CT_NS}">'
        f'<Default Extension="rels" ContentType="{RELS_CONTENT_TYPE}"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{DOCUMENT_PART}" ContentType="{DOCUMENT_CONTENT_TYPE}"/>'
        f'<Override PartName="/word/styles.xml" ContentType="{STYLES_CONTENT_TYPE}"/>'
        f"{extra}</Types>"
    ).encode()


def _package_rels() -> bytes:
    return (
        f'<Relationships xmlns="{REL_NS}">'
        f'<Relationship Id="rId1" Type="{REL_TYPE_OFFICE_DOCUMENT}" '
        f'Target="{DOCUMENT_PART}"/>'
        "</Relationships>"
    ).encode()


def _document_rels() -> bytes:
    return (
        f'<Relationships xmlns="{REL_NS}">'
        f'<Relationship Id="rId2" Type="{REL_TYPE_STYLES}" Target="styles.xml"/>'
        "</Relationships>"
    ).encode()


def _document(body: str, *, sect_pr: str = "<w:sectPr/>") -> bytes:
    return (
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">'
        f"<w:body>{body}{sect_pr}</w:body></w:document>"
    ).encode()


def _write_package(
    tmp_path: Path,
    body: str,
    *,
    sect_pr: str = "<w:sectPr/>",
    name: str = "fields.docx",
) -> Path:
    path = tmp_path / name
    entries = {
        CONTENT_TYPES_PART: _content_types(),
        PACKAGE_RELS_PART: _package_rels(),
        DOCUMENT_PART: _document(body, sect_pr=sect_pr),
        "word/_rels/document.xml.rels": _document_rels(),
        "word/styles.xml": STYLES_XML,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry_name, payload in entries.items():
            archive.writestr(entry_name, payload)
    return path


def _heading(text: str, style: str = "Heading1") -> str:
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr><w:r><w:t>{text}</w:t></w:r></w:p>'


# ---------------------------------------------------------------------------
# Klasifikasi dan scanning
# ---------------------------------------------------------------------------


def test_field_kind_and_name_handle_empty_and_unknown_instructions() -> None:
    assert field_kind("") is FieldKind.OTHER
    assert field_kind("   ") is FieldKind.OTHER
    assert field_kind("  page  ") is FieldKind.PAGE
    assert field_kind('toc \\o "1-3"') is FieldKind.TOC
    assert field_kind("UNKNOWN token") is FieldKind.OTHER
    assert field_name("") is None
    assert field_name("  \t") is None
    assert field_name("  PAGEREF _Ref1 \\h") == "PAGEREF"
    assert FIELD_NAME_RE.pattern.startswith(r"\s*")


def test_field_marker_kind_ignores_unknown_fldchar_and_other_elements() -> None:
    assert field_marker_kind(etree.fromstring(f'<w:fldChar xmlns:w="{W_NS}"/>')) is None
    unknown = etree.fromstring(f'<w:fldChar xmlns:w="{W_NS}" w:fldCharType="dirty"/>')
    assert field_marker_kind(unknown) is None
    assert field_marker_kind(etree.fromstring(f'<w:t xmlns:w="{W_NS}">x</w:t>')) is None


def test_iter_field_markers_skips_nested_paragraphs_textboxes_and_comments() -> None:
    paragraph = etree.fromstring(
        f'<w:p xmlns:w="{W_NS}">'
        "<!-- komentar bukan marker -->"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:p><w:r><w:fldChar w:fldCharType="separate"/></w:r></w:p>'
        '<w:txbxContent><w:r><w:fldChar w:fldCharType="separate"/></w:r></w:txbxContent>'
        "<w:r><w:instrText> TOC </w:instrText></w:r>"
        "</w:p>"
    )

    markers = list(iter_field_markers(paragraph))

    assert [field_marker_kind(marker) for marker in markers] == [
        fields_module.FieldMarkerKind.BEGIN,
        fields_module.FieldMarkerKind.INSTRUCTION,
    ]
    assert has_field(paragraph) is True
    assert has_field(_paragraph("<w:r><w:t>tanpa field</w:t></w:r>")) is False


def test_iter_field_instructions_ignores_orphan_instruction_and_keeps_unclosed() -> None:
    paragraph = _paragraph(
        "<w:r><w:instrText> PAGE </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> SEQ </w:instrText></w:r>"
        "<w:r><w:instrText>Gambar </w:instrText></w:r>"
    )

    assert list(iter_field_instructions(paragraph)) == [" SEQ Gambar "]

    simple = _paragraph('<w:fldSimple w:instr=""><w:r><w:t>x</w:t></w:r></w:fldSimple>')
    assert list(iter_field_instructions(simple)) == [""]


def test_field_runs_and_is_field_run_cover_plain_and_simple_runs() -> None:
    paragraph = _paragraph(
        "<w:r><w:t>plain</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> PAGE </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>1</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:fldSimple w:instr="SEQ Tabel"><w:r><w:t>2</w:t></w:r></w:fldSimple>'
    )
    runs = paragraph.findall(qn("w:r"))
    simple_run = paragraph.find(f".//{qn('w:fldSimple')}/{qn('w:r')}")

    assert [run for run in iter_field_runs(paragraph)] == [*runs[1:], simple_run]
    assert is_field_run(runs[0]) is False
    assert is_field_run(runs[1]) is True
    assert is_field_run(simple_run) is True

    marker_outside_paragraph = etree.fromstring(
        f'<w:r xmlns:w="{W_NS}"><w:fldChar w:fldCharType="begin"/></w:r>'
    )
    assert is_field_run(marker_outside_paragraph) is True
    plain_outside_paragraph = etree.fromstring(f'<w:r xmlns:w="{W_NS}"><w:t>x</w:t></w:r>')
    assert is_field_run(plain_outside_paragraph) is False


def test_field_text_ranges_omit_empty_simple_and_complex_fields() -> None:
    paragraph = _paragraph(
        '<w:fldSimple w:instr="PAGE"></w:fldSimple>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> PAGE </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )

    assert field_text_ranges(paragraph) == ()


def test_field_result_text_reads_tabs_simple_text_and_missing_separate() -> None:
    paragraph = _paragraph(
        "<w:r><w:t>awal</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> PAGEREF p0001 \\h </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>awal</w:t><w:tab/><w:t>7</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:fldSimple w:instr="PAGE"><w:r><w:t>4</w:t></w:r></w:fldSimple>'
    )
    complex_field, simple_field = iter_fields_in_root(paragraph)
    without_separate = Field(
        kind=complex_field.kind,
        instruction=complex_field.instruction,
        paragraph=paragraph,
        begin=complex_field.begin,
        separate=None,
        end=complex_field.end,
    )

    assert field_result_text(complex_field) == "awal\t7"
    assert field_result_text(simple_field) == "4"
    assert field_result_text(without_separate) == ""
    assert field_has_result(complex_field) is True
    assert field_has_result(without_separate) is False
    assert field_instruction(complex_field) == "PAGEREF p0001 \\h"


def test_iter_fields_in_root_parses_simple_and_nested_complex_fields() -> None:
    paragraph = _paragraph(
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> TOC </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> PAGE </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>1</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:fldSimple w:instr="SEQ Gambar"><w:r><w:t>2</w:t></w:r></w:fldSimple>'
    )

    fields = iter_fields_in_root(paragraph)

    assert [field.kind for field in fields] == [FieldKind.TOC, FieldKind.SEQ]
    assert len(fields[0].nested) == 1
    assert fields[0].nested[0].kind is FieldKind.PAGE


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        ('<w:r><w:fldChar w:fldCharType="separate"/></w:r>', "separate tanpa field begin"),
        ('<w:r><w:fldChar w:fldCharType="end"/></w:r>', "end tanpa field begin"),
        (
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>',
            "lebih dari satu separate",
        ),
        (
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            "<w:r><w:instrText> TOC </w:instrText></w:r>"
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>',
            "tidak memiliki separate",
        ),
        (
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            "<w:r><w:instrText> TOC </w:instrText></w:r>"
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>',
            "tidak memiliki w:fldChar end",
        ),
    ],
)
def test_complex_field_parse_errors_are_stable(fragment: str, message: str) -> None:
    with pytest.raises(FieldError, match=message):
        iter_fields_in_root(_paragraph(fragment))


def test_field_outside_paragraph_is_rejected_for_complex_and_simple() -> None:
    complex_root = _root(
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        "<w:r><w:instrText> TOC </w:instrText></w:r>"
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )
    simple_root = _root('<w:fldSimple w:instr="PAGE"><w:r><w:t>1</w:t></w:r></w:fldSimple>')

    with pytest.raises(FieldError, match="tidak berada di dalam w:p"):
        iter_fields_in_root(complex_root)
    with pytest.raises(FieldError, match="tidak berada di dalam w:p"):
        iter_fields_in_root(simple_root)


# ---------------------------------------------------------------------------
# insert_field dan validasi argumen
# ---------------------------------------------------------------------------


def test_insert_field_rejects_invalid_switches_and_positions() -> None:
    paragraph = _paragraph("")
    other_paragraph = _paragraph("")
    body = etree.fromstring(f'<w:body xmlns:w="{W_NS}"/>')
    anchor_elsewhere = _paragraph("<w:r><w:t>x</w:t></w:r>")
    anchor = anchor_elsewhere.find(qn("w:r"))
    assert anchor is not None

    with pytest.raises(FieldError, match="Switches field harus sequence"):
        insert_field("TOC", FieldPosition(paragraph=paragraph))  # type: ignore[arg-type]
    with pytest.raises(FieldError, match="Switch field harus berupa string"):
        insert_field([1], FieldPosition(paragraph=paragraph))  # type: ignore[list-item]
    with pytest.raises(FieldError, match="Instruksi field tidak boleh kosong"):
        insert_field([], FieldPosition(paragraph=paragraph))
    with pytest.raises(FieldError, match="Instruksi field tidak boleh kosong"):
        insert_field(["   "], FieldPosition(paragraph=paragraph))
    with pytest.raises(FieldError, match="Field hanya boleh disisipkan ke paragraf"):
        insert_field(["PAGE"], FieldPosition(paragraph=body))
    with pytest.raises(FieldError, match="Paragraf akhir field harus w:p"):
        insert_field(["PAGE"], FieldPosition(paragraph=paragraph, end_paragraph=body))
    with pytest.raises(FieldError, match="Anchor penyisipan field bukan child langsung"):
        insert_field(["PAGE"], FieldPosition(paragraph=paragraph, before=anchor))
    with pytest.raises(FieldError, match="Hasil field harus berupa string"):
        insert_field(["PAGE"], FieldPosition(paragraph=paragraph), 1)  # type: ignore[arg-type]
    assert paragraph_text(other_paragraph) == ""


def test_insert_field_skips_empty_result_run_and_keeps_custom_rpr() -> None:
    paragraph = _paragraph("")
    rpr = etree.fromstring(f'<w:rPr xmlns:w="{W_NS}"><w:b/></w:rPr>')
    field = insert_field(["PAGE"], FieldPosition(paragraph=paragraph, rpr=rpr))

    assert field.kind is FieldKind.PAGE
    assert paragraph.findall(qn("w:r"))[-1] is field.end
    assert field.end.find(qn("w:rPr")) is not None
    assert paragraph.find(f".//{qn('w:t')}") is None


def test_new_paragraph_without_style_and_remove_element_without_parent() -> None:
    paragraph = fields_module._new_paragraph()
    orphan = etree.Element(qn("w:p"))

    assert paragraph.tag == qn("w:p")
    assert paragraph.find(qn("w:pPr")) is None
    fields_module._remove_element(orphan)
    assert orphan.getparent() is None


def test_insert_seq_and_pageref_reject_blank_labels() -> None:
    paragraph = _paragraph("")

    with pytest.raises(FieldError, match="Label SEQ tidak boleh kosong"):
        insert_seq(object(), paragraph=paragraph, label="")
    with pytest.raises(FieldError, match="Label SEQ tidak boleh kosong"):
        insert_seq(object(), paragraph=paragraph, label="   ")
    with pytest.raises(FieldError, match="Nama bookmark PAGEREF tidak boleh kosong"):
        insert_pageref(object(), paragraph=paragraph, bookmark="")
    with pytest.raises(FieldError, match="Nama bookmark PAGEREF tidak boleh kosong"):
        insert_pageref(object(), paragraph=paragraph, bookmark="   ")


def test_is_bold_exempt_only_for_known_field_kinds() -> None:
    paragraph = _paragraph("")
    begin = etree.Element(qn("w:fldChar"))

    def _field(kind: FieldKind) -> Field:
        return Field(kind, "x", paragraph, begin, begin, begin)

    assert is_bold_exempt(_field(FieldKind.PAGE)) is True
    assert is_bold_exempt(_field(FieldKind.TOC)) is True
    assert is_bold_exempt(_field(FieldKind.OTHER)) is False


# ---------------------------------------------------------------------------
# insert_toc dan cleanup
# ---------------------------------------------------------------------------


def test_insert_toc_validates_title_levels_and_caption() -> None:
    package = object()

    with pytest.raises(FieldError, match="Judul TOC tidak boleh kosong"):
        insert_toc(package, title="")  # type: ignore[arg-type]
    with pytest.raises(FieldError, match="Judul TOC tidak boleh kosong"):
        insert_toc(package, title="   ")  # type: ignore[arg-type]
    for levels in ((0, 3), (1, 10), (3, 2)):
        with pytest.raises(FieldError, match="levels TOC harus 1 <= low <= high <= 9"):
            insert_toc(package, title="DAFTAR ISI", levels=levels)  # type: ignore[arg-type]
    with pytest.raises(FieldError, match="Caption TOC tidak boleh kosong"):
        insert_toc(package, title="DAFTAR ISI", caption="  ")  # type: ignore[arg-type]


def test_insert_toc_replaces_legacy_fields_and_keeps_titles_inside_sdt(
    tmp_path: Path,
) -> None:
    legacy_complex = (
        "<w:p>"
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> TOC \\o "1-3" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>Entri lama</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        "</w:p>"
    )
    legacy_simple = (
        '<w:p><w:fldSimple w:instr="TOC \\c &quot;Gambar&quot;">'
        "<w:r><w:t>Gambar 1</w:t></w:r></w:fldSimple></w:p>"
    )
    old_title_inside_sdt = (
        "<w:sdt><w:sdtContent>" + _heading("DAFTAR ISI") + "</w:sdtContent></w:sdt>"
    )
    old_title_outside = _heading("DAFTAR ISI")
    path = _write_package(
        tmp_path,
        legacy_complex
        + legacy_simple
        + old_title_inside_sdt
        + old_title_outside
        + _heading("BAB I"),
    )
    package = DocumentPackage.load(path)
    body = package.xml(DOCUMENT_PART).find(qn("w:body"))
    assert body is not None
    preserved_sdt = body.find(qn("w:sdt"))
    assert preserved_sdt is not None

    insert_toc(package, title="DAFTAR ISI")

    instructions = [field_instruction(field) for field in iter_fields_in_root(body)]
    assert len(instructions) == 1
    assert instructions[0].strip().startswith("TOC")
    assert preserved_sdt.getparent() is body
    preserved_title = preserved_sdt.find(f".//{qn('w:p')}")
    assert preserved_title is not None
    assert paragraph_text(preserved_title) == "DAFTAR ISI"
    assert "Entri lama" not in "".join(node.text or "" for node in body.iter(qn("w:t")))


def test_insert_toc_appends_when_body_has_no_chapter_or_section(
    tmp_path: Path,
) -> None:
    path = _write_package(tmp_path, _text_paragraph("Sampul"), sect_pr="")
    package = DocumentPackage.load(path)
    body = package.xml(DOCUMENT_PART).find(qn("w:body"))
    assert body is not None

    insert_toc(package, title="DAFTAR ISI", gap_after_title=False)

    assert body[-1].tag == qn("w:sdt")


def test_insert_toc_rejects_anchor_outside_body(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _text_paragraph("BAB I"))
    package = DocumentPackage.load(path)
    body = package.xml(DOCUMENT_PART).find(qn("w:body"))
    assert body is not None
    paragraph = body.find(qn("w:p"))
    assert paragraph is not None
    run = paragraph.find(qn("w:r"))
    assert run is not None

    with pytest.raises(FieldError, match="bukan child langsung w:body"):
        insert_toc(package, title="DAFTAR ISI", before=run)


def test_insert_toc_respects_section_break_before_first_chapter(tmp_path: Path) -> None:
    section_paragraph = "<w:p><w:pPr><w:sectPr/></w:pPr></w:p>"
    marker = '<w:bookmarkStart w:id="7" w:name="penanda"/>'
    path = _write_package(
        tmp_path,
        section_paragraph + marker + _heading("BAB I") + _text_paragraph("Isi"),
    )
    package = DocumentPackage.load(path)
    body = package.xml(DOCUMENT_PART).find(qn("w:body"))
    assert body is not None
    insertion = body[0]

    insert_toc(package, title="DAFTAR ISI")

    sdt = next(child for child in body if child.tag == qn("w:sdt"))
    assert body.index(sdt) == body.index(insertion) - 1


def test_ensure_no_blank_page_after_toc_removes_only_break_paragraphs(
    tmp_path: Path,
) -> None:
    path = _write_package(tmp_path, _text_paragraph("Sampul"), sect_pr="")
    package = DocumentPackage.load(path)
    insert_toc(package, title="DAFTAR ISI", gap_after_title=False)
    body = package.xml(DOCUMENT_PART).find(qn("w:body"))
    assert body is not None
    page_break = etree.fromstring(f'<w:p xmlns:w="{W_NS}"><w:r><w:br w:type="page"/></w:r></w:p>')
    empty = etree.fromstring(f'<w:p xmlns:w="{W_NS}"/>')
    text = etree.fromstring(f'<w:p xmlns:w="{W_NS}"><w:r><w:t>Isi</w:t></w:r></w:p>')
    body.extend([page_break, empty, text])

    assert ensure_no_blank_page_after_toc(package) == 1

    assert page_break.getparent() is None
    assert empty.getparent() is body
    assert text.getparent() is body


def test_ensure_no_blank_page_after_toc_skips_sdt_without_toc_gallery(
    tmp_path: Path,
) -> None:
    path = _write_package(
        tmp_path,
        "<w:sdt><w:sdtContent></w:sdtContent></w:sdt>"
        '<w:sdt><w:sdtPr><w:docPartGallery w:val="Lain"/></w:sdtPr>'
        "<w:sdtContent></w:sdtContent></w:sdt>" + _text_paragraph("Isi"),
    )
    package = DocumentPackage.load(path)

    assert ensure_no_blank_page_after_toc(package) == 0


# ---------------------------------------------------------------------------
# Settings updateFields
# ---------------------------------------------------------------------------


class _SettingsPackage:
    def __init__(self, root: etree._Element | None) -> None:
        self.root = root

    def has_part(self, name: str) -> bool:
        return name == fields_module.SETTINGS_PART and self.root is not None

    def xml(self, name: str) -> etree._Element:
        assert name == fields_module.SETTINGS_PART
        assert self.root is not None
        return self.root


def _settings(inner: str) -> etree._Element:
    return etree.fromstring(f'<w:settings xmlns:w="{W_NS}">{inner}</w:settings>')


def test_update_fields_enabled_and_strip_with_missing_settings() -> None:
    package = _SettingsPackage(None)

    assert update_fields_enabled(package) is False
    assert strip_update_fields(package) is False


def test_update_fields_enabled_reads_val_and_strip_removes_all() -> None:
    package = _SettingsPackage(_settings("<w:updateFields/>"))

    assert update_fields_enabled(package) is True
    assert strip_update_fields(package) is True
    assert strip_update_fields(package) is False
    assert update_fields_enabled(package) is False


@pytest.mark.parametrize("value", ["0", "false", "OFF", "no"])
def test_update_fields_enabled_rejects_false_values(value: str) -> None:
    package = _SettingsPackage(_settings(f'<w:updateFields w:val="{value}"/>'))

    assert update_fields_enabled(package) is False


def test_update_fields_enabled_defaults_true_without_val() -> None:
    package = _SettingsPackage(_settings("<w:updateFields/>"))

    assert update_fields_enabled(package) is True


def test_settings_without_update_fields_is_disabled() -> None:
    package = _SettingsPackage(_settings("<w:zoom/>"))

    assert update_fields_enabled(package) is False
    assert strip_update_fields(package) is False


def test_simple_namespace_field_package_is_not_required_for_settings() -> None:
    package = SimpleNamespace(has_part=lambda name: False, xml=lambda name: None)

    assert update_fields_enabled(package) is False
