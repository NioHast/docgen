"""Tes unit field TOC, ``w:sdt``, style TOC, dan stage ``toc``."""

import html
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import docgen.docx.fields as fields_module
from docgen.docx.fields import (
    Field,
    FieldKind,
    FieldPosition,
    ensure_no_blank_page_after_toc,
    field_instruction,
    field_result_text,
    field_text_ranges,
    insert_field,
    insert_pageref,
    insert_seq,
    insert_toc,
    iter_field_instructions,
    iter_fields,
    iter_fields_in_paragraph,
)
from docgen.docx.package import (
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    PACKAGE_RELS_PART,
    REL_TYPE_OFFICE_DOCUMENT,
    REL_TYPE_STYLES,
    DocumentPackage,
)
from docgen.docx.paragraphs import paragraph_text
from docgen.docx.xml import qn
from docgen.pipeline import StageName
from docgen.stages.toc import (
    TOC_STYLE_IDS,
    TocError,
    TocStage,
    _format_fallback,
    ensure_toc_styles,
    tab_position,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "fixtures" / "golden" / "laporan-baseline.docx"

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
    '<w:style w:type="paragraph" w:styleId="Normal">'
    '<w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1">'
    '<w:name w:val="heading 1"/></w:style>'
    "</w:styles>"
).encode()


# ---------------------------------------------------------------------------
# Helper package minimal
# ---------------------------------------------------------------------------


def _content_types() -> bytes:
    return (
        f'<Types xmlns="{CT_NS}">'
        f'<Default Extension="rels" ContentType="{RELS_CONTENT_TYPE}"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{DOCUMENT_PART}" '
        f'ContentType="{DOCUMENT_CONTENT_TYPE}"/>'
        '<Override PartName="/word/styles.xml" '
        f'ContentType="{STYLES_CONTENT_TYPE}"/>'
        "</Types>"
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
        f'<Relationship Id="rId2" Type="{REL_TYPE_STYLES}" '
        'Target="styles.xml"/>'
        "</Relationships>"
    ).encode()


def _paragraph(
    text: str = "",
    *,
    style: str | None = None,
    extra_runs: str = "",
) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{html.escape(style)}"/></w:pPr>' if style else ""
    runs = ""
    if text:
        runs += f"<w:r><w:t>{html.escape(text)}</w:t></w:r>"
    runs += extra_runs
    return f"<w:p>{ppr}{runs}</w:p>"


def _page_break_paragraph() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def _document(
    body: str,
    *,
    styles: bytes = STYLES_XML,
    sect_pr: str = "<w:sectPr/>",
) -> tuple[bytes, bytes]:
    document = (
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">'
        f"<w:body>{body}{sect_pr}</w:body></w:document>"
    ).encode()
    return document, styles


def _write_package(
    tmp_path: Path,
    body: str,
    *,
    styles: bytes = STYLES_XML,
    sect_pr: str = "<w:sectPr/>",
    name: str = "test.docx",
) -> Path:
    path = tmp_path / name
    document, styles_payload = _document(body, styles=styles, sect_pr=sect_pr)
    entries = {
        CONTENT_TYPES_PART: _content_types(),
        PACKAGE_RELS_PART: _package_rels(),
        DOCUMENT_PART: document,
        "word/_rels/document.xml.rels": _document_rels(),
        "word/styles.xml": styles_payload,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry_name, data in entries.items():
            archive.writestr(entry_name, data)
    return path


def _fake_ctx(package: DocumentPackage, *, toc: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        package=package,
        document=SimpleNamespace(),
        structure=SimpleNamespace(toc=toc),
        format=SimpleNamespace(
            page=SimpleNamespace(
                size="A4",
                orientation="portrait",
                margins=SimpleNamespace(
                    top=1440,
                    right=1440,
                    bottom=1440,
                    left=1440,
                ),
                header_distance=720,
                footer_distance=720,
                gutter=0,
            )
        ),
        options=SimpleNamespace(),
        dry_run=False,
    )


def _sdt_gallery(root) -> list:
    galleries = []
    for sdt in root.iter(qn("w:sdt")):
        pr = sdt.find(qn("w:sdtPr"))
        if pr is None:
            continue
        gallery = pr.find(".//" + qn("w:docPartGallery"))
        if gallery is not None and gallery.get(qn("w:val")) == "Table of Contents":
            galleries.append(sdt)
    return galleries


def _style_ids(styles_root) -> set[str]:
    return {
        style.get(qn("w:styleId"))
        for style in styles_root
        if isinstance(style.tag, str) and style.tag == qn("w:style") and style.get(qn("w:styleId"))
    }


def _has_page_break(paragraph) -> bool:
    for br in paragraph.iter(qn("w:br")):
        if (br.get(qn("w:type")) or "").casefold() == "page":
            return True
    ppr = paragraph.find(qn("w:pPr"))
    return ppr is not None and ppr.find(qn("w:pageBreakBefore")) is not None


def _assert_no_dirty(root) -> None:
    dirty = qn("w:dirty")
    offenders = [element.tag for element in root.iter() if dirty in element.attrib]
    assert offenders == []


def _assert_complex_field_order(field: Field) -> None:
    root = field.begin.getroottree().getroot()
    assert root is not None
    sequence: list[str] = []
    for element in root.iter():
        if element is field.begin:
            sequence.append("begin")
        elif element is field.separate:
            sequence.append("separate")
        elif element is field.end:
            sequence.append("end")
        elif element.tag == qn("w:instrText") and element.text == field.instruction:
            sequence.append("instrText")
    assert sequence == ["begin", "instrText", "separate", "end"]


# ---------------------------------------------------------------------------
# Golden baseline
# ---------------------------------------------------------------------------


def test_golden_toc_field_count_and_instructions() -> None:
    package = DocumentPackage.load(GOLDEN)
    fields = [field for field in iter_fields(package) if field.kind is FieldKind.TOC]
    assert len(fields) == 3
    instructions = [field_instruction(field) for field in fields]
    assert sum(value.startswith("TOC \\o") for value in instructions) == 1
    assert sum('TOC \\c "Tabel"' in value for value in instructions) == 1
    assert sum('TOC \\c "Gambar"' in value for value in instructions) == 1


def test_golden_toc_sdt_count() -> None:
    package = DocumentPackage.load(GOLDEN)
    root = package.xml(DOCUMENT_PART)
    galleries = _sdt_gallery(root)
    assert len(galleries) == 3
    assert all(
        gallery.find(qn("w:sdtPr")).find(".//" + qn("w:docPartGallery")).get(qn("w:val"))
        == "Table of Contents"
        for gallery in galleries
    )


def test_golden_toc_styles_toc1_toc2_toc3() -> None:
    package = DocumentPackage.load(GOLDEN)
    styles = package.xml("word/styles.xml")
    ids = _style_ids(styles)
    assert {"TOCHeading", "TOC1", "TOC2", "TOC3"} <= ids
    for style_id in ("TOC1", "TOC2", "TOC3"):
        assert next(item for item in styles if item.get(qn("w:styleId")) == style_id) is not None
    toc1 = next(item for item in styles if item.get(qn("w:styleId")) == "TOC1")
    assert any(tab.get(qn("w:leader")) == "dot" for tab in toc1.findall(".//" + qn("w:tab")))


def test_golden_toc_entry_2_1_page_3() -> None:
    package = DocumentPackage.load(GOLDEN)
    root = package.xml(DOCUMENT_PART)
    entry = None
    for paragraph in root.iter(qn("w:p")):
        ppr = paragraph.find(qn("w:pPr"))
        if ppr is None:
            continue
        style = ppr.find(qn("w:pStyle"))
        if style is None or style.get(qn("w:val")) != "TOC2":
            continue
        text = " ".join(paragraph_text(paragraph).split())
        if text.startswith("2.1."):
            entry = paragraph
            break
    assert entry is not None
    text = " ".join(paragraph_text(entry).split())
    assert text.startswith("2.1.")
    assert text.endswith("3")
    fields = iter_fields_in_paragraph(entry)
    pageref = [field for field in fields if field.kind is FieldKind.PAGEREF]
    assert pageref
    assert field_result_text(pageref[0]) == "3"


# ---------------------------------------------------------------------------
# insert_toc / style
# ---------------------------------------------------------------------------


def test_insert_toc_writes_single_field_inside_sdt(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        _paragraph("Sampul", style="CoverTitle") + _paragraph("BAB I", style="Heading1"),
    )
    package = DocumentPackage.load(path)
    first = insert_toc(package, title="DAFTAR ISI")
    assert first.kind is FieldKind.TOC

    second = insert_toc(package, title="DAFTAR ISI")
    assert second.kind is FieldKind.TOC

    fields = [field for field in iter_fields(package) if field.kind is FieldKind.TOC]
    assert len(fields) == 1
    root = package.xml(DOCUMENT_PART)
    assert len(_sdt_gallery(root)) == 1
    title = [
        paragraph
        for paragraph in root.iter(qn("w:p"))
        if paragraph_text(paragraph).strip() == "DAFTAR ISI"
    ]
    assert len(title) == 1
    ppr = title[0].find(qn("w:pPr"))
    assert ppr.find(qn("w:pStyle")).get(qn("w:val")) == "TOCHeading"


def test_insert_toc_caption_uses_c_field(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        _paragraph("BAB I", style="Heading1"),
    )
    package = DocumentPackage.load(path)
    field = insert_toc(package, title="DAFTAR GAMBAR", caption="Gambar")
    assert 'TOC \\c "Gambar"' in field_instruction(field)


def test_insert_toc_field_is_not_dirty(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        _paragraph("Sampul", style="CoverTitle") + _paragraph("BAB I", style="Heading1"),
    )
    package = DocumentPackage.load(path)
    field = insert_toc(package, title="DAFTAR ISI")

    _assert_no_dirty(package.xml(DOCUMENT_PART))
    _assert_complex_field_order(field)


def test_insert_toc_caption_field_is_not_dirty(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    field = insert_toc(package, title="DAFTAR TABEL", caption="Tabel")

    _assert_no_dirty(package.xml(DOCUMENT_PART))
    _assert_complex_field_order(field)


def test_insert_seq_field_is_not_dirty(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("Tabel 1 Judul", style="TableCaption"))
    package = DocumentPackage.load(path)
    paragraph = next(package.xml(DOCUMENT_PART).iter(qn("w:p")))
    field = insert_seq(package, paragraph=paragraph, label="Tabel")

    _assert_no_dirty(package.xml(DOCUMENT_PART))
    _assert_complex_field_order(field)


def test_insert_pageref_field_is_not_dirty(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("Lihat halaman"))
    package = DocumentPackage.load(path)
    paragraph = next(package.xml(DOCUMENT_PART).iter(qn("w:p")))
    field = insert_pageref(package, paragraph=paragraph, bookmark="_Ref1")

    _assert_no_dirty(package.xml(DOCUMENT_PART))
    _assert_complex_field_order(field)


def test_insert_toc_keep_existing_preserves_old_field(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    first = insert_toc(package, title="DAFTAR ISI")
    first_instruction = field_instruction(first)
    second = insert_toc(
        package,
        title="DAFTAR TABEL",
        caption="Tabel",
        keep_existing=True,
    )

    root = package.xml(DOCUMENT_PART)
    fields = [field for field in iter_fields(package) if field.kind is FieldKind.TOC]
    assert len(fields) == 2
    assert len(_sdt_gallery(root)) == 2
    assert first.begin.getroottree().getroot() is root
    assert first_instruction in [field_instruction(field) for field in fields]
    assert 'TOC \\c "Tabel"' in field_instruction(second)


def test_insert_toc_before_uses_explicit_anchor(tmp_path: Path) -> None:
    body_xml = (
        _paragraph("Sampul", style="CoverTitle")
        + _paragraph("BAB I", style="Heading1")
        + _paragraph("Anchor")
    )
    path = _write_package(tmp_path, body_xml)
    package = DocumentPackage.load(path)
    root = package.xml(DOCUMENT_PART)
    body = root.find(qn("w:body"))
    assert body is not None
    heading = next(
        child
        for child in body
        if child.tag == qn("w:p") and paragraph_text(child).strip() == "BAB I"
    )
    anchor = next(
        child
        for child in body
        if child.tag == qn("w:p") and paragraph_text(child).strip() == "Anchor"
    )

    insert_toc(package, title="DAFTAR ISI", before=anchor)

    sdt = _sdt_gallery(root)[0]
    assert body.index(sdt) == body.index(anchor) - 1
    assert body.index(sdt) > body.index(heading)


def test_insert_field_inserts_runs_before_anchor(tmp_path: Path) -> None:
    paragraph_xml = "<w:p><w:r><w:t>Awal</w:t></w:r><w:r><w:t>Akhir</w:t></w:r></w:p>"
    path = _write_package(tmp_path, paragraph_xml)
    package = DocumentPackage.load(path)
    paragraph = next(package.xml(DOCUMENT_PART).iter(qn("w:p")))
    anchor = paragraph.findall(qn("w:r"))[1]

    field = insert_field(
        ["SEQ", "Tabel"],
        FieldPosition(paragraph=paragraph, before=anchor),
        "1",
    )

    _assert_no_dirty(package.xml(DOCUMENT_PART))
    _assert_complex_field_order(field)
    assert paragraph.index(field.end) == paragraph.index(anchor) - 1
    assert paragraph.findall(qn("w:r"))[-1] is anchor


def test_insert_seq_is_thin_insert_field_wrapper(monkeypatch, tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("Tabel 1 Judul", style="TableCaption"))
    package = DocumentPackage.load(path)
    paragraph = next(package.xml(DOCUMENT_PART).iter(qn("w:p")))
    calls: list[tuple[tuple[str, ...], FieldPosition, str]] = []
    sentinel = object()

    def fake_insert_field(
        switches,
        position: FieldPosition,
        result: str = "",
    ):
        calls.append((tuple(switches), position, result))
        return sentinel

    monkeypatch.setattr(fields_module, "insert_field", fake_insert_field)

    assert insert_seq(package, paragraph=paragraph, label="Tabel") is sentinel
    assert len(calls) == 1
    switches, position, result = calls[0]
    assert switches == ("SEQ", "Tabel")
    assert position.paragraph is paragraph
    assert position.before is None
    assert position.end_paragraph is None
    assert result == "1"


def test_field_scanner_reads_split_instruction_and_simple_field(tmp_path: Path) -> None:
    extra_runs = (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> TOC </w:instrText></w:r>'
        '<w:r><w:instrText xml:space="preserve">\\o "1-3" </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>X</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:fldSimple w:instr=" PAGE "><w:r><w:t>3</w:t></w:r></w:fldSimple>'
    )
    path = _write_package(tmp_path, _paragraph(extra_runs=extra_runs))
    package = DocumentPackage.load(path)
    paragraph = next(package.xml(DOCUMENT_PART).iter(qn("w:p")))

    assert list(iter_field_instructions(paragraph)) == [' TOC \\o "1-3" ', " PAGE "]
    assert field_text_ranges(paragraph) == ((0, 1), (1, 2))


def test_ensure_toc_styles_is_idempotent(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    assert ensure_toc_styles(package, tab_pos=9026) == 4
    styles = package.xml("word/styles.xml")
    assert set(TOC_STYLE_IDS) <= _style_ids(styles)
    toc1 = next(style for style in styles if style.get(qn("w:styleId")) == "TOC1")
    tab = toc1.find(".//" + qn("w:tab"))
    assert tab.get(qn("w:pos")) == "9026"
    assert ensure_toc_styles(package, tab_pos=9026) == 0


def test_no_blank_page_between_toc_and_bab_i(tmp_path: Path) -> None:
    page_break = _page_break_paragraph()
    path = _write_package(
        tmp_path,
        _paragraph("Sampul", style="CoverTitle")
        + page_break
        + _paragraph("")
        + _paragraph("BAB I", style="Heading1"),
    )
    package = DocumentPackage.load(path)
    root = package.xml(DOCUMENT_PART)
    body = root.find(qn("w:body"))
    target = next(
        child
        for child in body
        if child.tag == qn("w:p") and paragraph_text(child).strip() == "BAB I"
    )
    page_break_element = next(
        child for child in body if child.tag == qn("w:p") and _has_page_break(child)
    )

    insert_toc(package, title="DAFTAR ISI", before=page_break_element)
    assert ensure_no_blank_page_after_toc(package) == 0

    sdt = _sdt_gallery(root)[0]
    index = body.index(sdt)
    between = [child for child in body[index + 1 : body.index(target)]]
    assert all(not _has_page_break(child) for child in between)
    assert all(
        "".join(node.text or "" for node in child.iter(qn("w:t"))).strip() == ""
        for child in between
    )


def _page_geometry(*, gutter: str | None = None) -> str:
    gutter_attr = f' w:gutter="{gutter}"' if gutter is not None else ""
    return (
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" '
        f'w:left="1440" w:header="720" w:footer="720"{gutter_attr}/>'
        "</w:sectPr>"
    )


def test_tab_position_uses_first_section_geometry(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        _paragraph("BAB I", style="Heading1"),
        sect_pr=_page_geometry(),
    )
    package = DocumentPackage.load(path)
    assert tab_position(package) == 9026


def test_tab_position_mengurangi_gutter(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        _paragraph("BAB I", style="Heading1"),
        sect_pr=_page_geometry(gutter="720"),
    )
    package = DocumentPackage.load(path)
    assert tab_position(package) == 8306


def test_tab_position_geometry_tidak_lengkap_menimbulkan_toc_tab(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    with pytest.raises(TocError) as excinfo:
        tab_position(package)
    assert excinfo.value.code == "TOC-TAB"


def test_tab_position_memakai_fallback_eksplisit(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    assert tab_position(package, fallback=(11906, 1440, 1440, 0)) == 9026


def test_tab_position_fallback_tidak_valid_menimbulkan_toc_tab(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    with pytest.raises(TocError) as excinfo:
        tab_position(package, fallback=(11906, 6000, 6000, 0))
    assert excinfo.value.code == "TOC-TAB"


def _format_ctx(size: str, orientation: str) -> SimpleNamespace:
    return SimpleNamespace(
        format=SimpleNamespace(
            page=SimpleNamespace(
                size=size,
                orientation=orientation,
                margins=SimpleNamespace(left=1440, right=1440),
            )
        )
    )


def test_format_fallback_memakai_ukuran_kanonis_dan_landscape() -> None:
    assert _format_fallback(_format_ctx("A4", "portrait")) == (11906, 1440, 1440, 0)
    assert _format_fallback(_format_ctx("Letter", "landscape")) == (15840, 1440, 1440, 0)


def test_format_fallback_mengembalikan_none_untuk_ukuran_tidak_dikenal() -> None:
    assert _format_fallback(_format_ctx("A5", "portrait")) is None
    assert _format_fallback(_format_ctx("LETTER", "portrait")) is None


# ---------------------------------------------------------------------------
# Stage toc
# ---------------------------------------------------------------------------


def test_toc_stage_skipped_when_disabled(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    result = TocStage().run(_fake_ctx(package, toc=False))
    assert result.status == "skipped"
    assert result.changed is False
    assert not _sdt_gallery(package.xml(DOCUMENT_PART))


def test_toc_stage_writes_field_and_styles_idempotently(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        _paragraph("Sampul", style="CoverTitle") + _paragraph("BAB I", style="Heading1"),
    )
    package = DocumentPackage.load(path)
    ctx = _fake_ctx(package, toc=True)

    result = TocStage().run(ctx)
    assert result.stage == StageName.TOC.value
    assert result.status == "ok"
    assert result.changed is True
    fields = [field for field in iter_fields(package) if field.kind is FieldKind.TOC]
    assert len(fields) == 1
    assert len(_sdt_gallery(package.xml(DOCUMENT_PART))) == 1
    assert set(TOC_STYLE_IDS) <= _style_ids(package.xml("word/styles.xml"))

    second = TocStage().run(ctx)
    assert second.changed is False
    assert len(_sdt_gallery(package.xml(DOCUMENT_PART))) == 1
