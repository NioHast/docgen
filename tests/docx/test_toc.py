"""Tes unit field TOC, ``w:sdt``, style TOC, dan stage ``toc``."""

import html
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from autooffice.docx.package.fields import (
    Field,
    FieldError,
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
from autooffice.docx.package.package import (
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    PACKAGE_RELS_PART,
    REL_TYPE_OFFICE_DOCUMENT,
    REL_TYPE_STYLES,
    DocumentPackage,
)
from autooffice.docx.package.paragraphs import paragraph_text
from autooffice.docx.package.xml import RPR_ORDER, qn
from autooffice.docx.pipeline import StageName
from autooffice.docx.stages.toc import (
    LIST_ENTRY_STYLE_ID,
    TOC_STYLE_IDS,
    TocError,
    TocStage,
    ensure_list_entry_style,
    ensure_toc_styles,
    format_tab_fallback,
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


def _sdt_content_paragraphs(sdt) -> list:
    content = sdt.find(qn("w:sdtContent"))
    assert content is not None
    return [child for child in content if child.tag == qn("w:p")]


def _sdt_heading(sdt):
    return _sdt_content_paragraphs(sdt)[0]


def _pstyle_id(paragraph) -> str | None:
    style = paragraph.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    return None if style is None else style.get(qn("w:val"))


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
    for gallery in galleries:
        assert _sdt_content_paragraphs(gallery)


def test_golden_toc_styles_toc1_toc2_toc3() -> None:
    package = DocumentPackage.load(GOLDEN)
    styles = package.xml("word/styles.xml")
    ids = _style_ids(styles)
    assert {"TOCHeading", "TOC1", "TOC2", "TOC3"} <= ids
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


def test_insert_toc_adds_single_canonical_gap_after_title(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    insert_toc(package, title="DAFTAR ISI")

    sdt = _sdt_gallery(package.xml(DOCUMENT_PART))[0]
    paragraphs = _sdt_content_paragraphs(sdt)
    assert len(paragraphs) == 4
    assert paragraph_text(paragraphs[0]).strip() == "DAFTAR ISI"

    gap = paragraphs[1]
    assert paragraph_text(gap) == ""
    assert gap.find(".//" + qn("w:fldChar")) is None
    assert paragraphs[2].find(".//" + qn("w:fldChar")) is not None
    assert paragraphs[3].find(".//" + qn("w:fldChar")) is not None

    ppr = gap.find(qn("w:pPr"))
    assert ppr is not None
    spacing = ppr.find(qn("w:spacing"))
    assert spacing.get(qn("w:before")) == "0"
    assert spacing.get(qn("w:after")) == "0"
    assert spacing.get(qn("w:line")) == "360"
    assert spacing.get(qn("w:lineRule")) == "auto"
    rpr = ppr.find(qn("w:rPr"))
    assert rpr is not None
    fonts = rpr.find(qn("w:rFonts"))
    assert fonts is not None
    for attribute in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        assert fonts.get(qn(attribute)) == "Times New Roman"
    assert rpr.find(qn("w:sz")).get(qn("w:val")) == "24"
    assert rpr.find(qn("w:szCs")).get(qn("w:val")) == "24"


def test_insert_toc_gap_after_title_can_be_disabled(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    insert_toc(package, title="DAFTAR ISI", gap_after_title=False)

    sdt = _sdt_gallery(package.xml(DOCUMENT_PART))[0]
    paragraphs = _sdt_content_paragraphs(sdt)
    assert len(paragraphs) == 3
    assert paragraph_text(paragraphs[0]).strip() == "DAFTAR ISI"
    assert paragraphs[1].find(".//" + qn("w:fldChar")) is not None


def test_insert_toc_page_break_before_on_heading_in_ppr_order(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    insert_toc(
        package,
        title="DAFTAR TABEL",
        caption="Tabel",
        page_break_before=True,
    )

    sdt = _sdt_gallery(package.xml(DOCUMENT_PART))[0]
    heading = _sdt_heading(sdt)
    assert _pstyle_id(heading) == "TOCHeading"
    ppr = heading.find(qn("w:pPr"))
    assert ppr is not None
    tags = [child.tag for child in ppr if isinstance(child.tag, str)]
    break_index = tags.index(qn("w:pageBreakBefore"))
    assert break_index == 1
    assert break_index < tags.index(qn("w:jc"))
    assert break_index < tags.index(qn("w:outlineLvl"))


def test_insert_toc_page_break_before_default_absent(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    insert_toc(package, title="DAFTAR ISI")

    sdt = _sdt_gallery(package.xml(DOCUMENT_PART))[0]
    heading = _sdt_heading(sdt)
    ppr = heading.find(qn("w:pPr"))
    assert ppr is not None
    assert ppr.find(qn("w:pageBreakBefore")) is None


def test_cleanup_keeps_toc_gap_and_page_break(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    insert_toc(package, title="DAFTAR TABEL", caption="Tabel", page_break_before=True)

    assert ensure_no_blank_page_after_toc(package) == 0

    sdt = _sdt_gallery(package.xml(DOCUMENT_PART))[0]
    paragraphs = _sdt_content_paragraphs(sdt)
    assert len(paragraphs) == 4
    assert paragraph_text(paragraphs[1]) == ""
    heading = _sdt_heading(sdt)
    assert heading.find(f"{qn('w:pPr')}/{qn('w:pageBreakBefore')}") is not None


def test_insert_toc_caption_uses_c_field(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        _paragraph("BAB I", style="Heading1"),
    )
    package = DocumentPackage.load(path)
    field = insert_toc(package, title="DAFTAR GAMBAR", caption="Gambar")
    assert 'TOC \\c "Gambar"' in field_instruction(field)


@pytest.mark.parametrize("field_kind", ["toc", "toc_caption", "seq", "pageref"])
def test_inserted_fields_are_clean_and_ordered(tmp_path: Path, field_kind: str) -> None:
    if field_kind == "toc":
        path = _write_package(
            tmp_path,
            _paragraph("Sampul", style="CoverTitle") + _paragraph("BAB I", style="Heading1"),
        )
        package = DocumentPackage.load(path)
        field = insert_toc(package, title="DAFTAR ISI")
    elif field_kind == "toc_caption":
        path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
        package = DocumentPackage.load(path)
        field = insert_toc(package, title="DAFTAR TABEL", caption="Tabel")
    elif field_kind == "seq":
        path = _write_package(tmp_path, _paragraph("Tabel 1 Judul", style="TableCaption"))
        package = DocumentPackage.load(path)
        paragraph = next(package.xml(DOCUMENT_PART).iter(qn("w:p")))
        field = insert_seq(package, paragraph=paragraph, label="Tabel")
    else:
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


def test_insert_toc_before_existing_toc_reuses_anchor_position(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        _paragraph("Sampul", style="CoverTitle") + _paragraph("BAB I", style="Heading1"),
    )
    package = DocumentPackage.load(path)
    insert_toc(package, title="DAFTAR ISI")
    root = package.xml(DOCUMENT_PART)
    body = root.find(qn("w:body"))
    assert body is not None
    old_sdt = _sdt_gallery(root)[0]
    old_index = body.index(old_sdt)

    insert_toc(package, title="DAFTAR ISI", before=old_sdt)

    galleries = _sdt_gallery(root)
    assert len(galleries) == 1
    assert body.index(galleries[0]) == old_index
    assert old_sdt.getparent() is None


def test_insert_toc_rejects_anchor_inside_old_toc_before_removal(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    insert_toc(package, title="DAFTAR ISI")
    root = package.xml(DOCUMENT_PART)
    old_sdt = _sdt_gallery(root)[0]
    inner_paragraph = old_sdt.find(".//" + qn("w:p"))
    assert inner_paragraph is not None

    with pytest.raises(FieldError, match="bukan child langsung w:body"):
        insert_toc(package, title="DAFTAR ISI", before=inner_paragraph)

    assert len(_sdt_gallery(root)) == 1
    assert old_sdt.getparent() is not None


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


def _style_by_id(styles_root, style_id: str):
    return next(style for style in styles_root if style.get(qn("w:styleId")) == style_id)


def test_ensure_list_entry_style_is_idempotent(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    assert ensure_list_entry_style(package, tab_pos=9026) == 1

    styles = package.xml("word/styles.xml")
    style = _style_by_id(styles, LIST_ENTRY_STYLE_ID)
    assert style.find(qn("w:basedOn")).get(qn("w:val")) == "Normal"
    assert style.find(qn("w:next")).get(qn("w:val")) == "Normal"
    assert style.find(qn("w:name")).get(qn("w:val")) == "table of figures"

    ppr = style.find(qn("w:pPr"))
    assert ppr is not None
    spacing = ppr.find(qn("w:spacing"))
    assert spacing.get(qn("w:before")) == "0"
    assert spacing.get(qn("w:after")) == "0"
    assert spacing.get(qn("w:line")) == "360"
    assert spacing.get(qn("w:lineRule")) == "auto"
    ind = ppr.find(qn("w:ind"))
    assert ind.get(qn("w:left")) == "0"
    assert ind.get(qn("w:right")) == "0"
    assert ind.get(qn("w:firstLine")) == "0"
    assert ppr.find(qn("w:jc")).get(qn("w:val")) == "left"
    tab = ppr.find(f"{qn('w:tabs')}/{qn('w:tab')}")
    assert tab.get(qn("w:val")) == "right"
    assert tab.get(qn("w:leader")) == "dot"
    assert tab.get(qn("w:pos")) == "9026"

    assert ensure_list_entry_style(package, tab_pos=9026) == 0
    assert ensure_list_entry_style(package, tab_pos=8500) == 1
    updated = _style_by_id(package.xml("word/styles.xml"), LIST_ENTRY_STYLE_ID)
    assert updated.find(".//" + qn("w:tab")).get(qn("w:pos")) == "8500"


def test_ensure_list_entry_style_without_tab_position(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    assert ensure_list_entry_style(package, tab_pos=None) == 1

    style = _style_by_id(package.xml("word/styles.xml"), LIST_ENTRY_STYLE_ID)
    assert style.find(f"{qn('w:pPr')}/{qn('w:tabs')}") is None
    assert ensure_list_entry_style(package, tab_pos=None) == 0


def _assert_rpr_order(style) -> None:
    rpr = style.find(qn("w:rPr"))
    assert rpr is not None
    names = [child.tag.rsplit("}", 1)[-1] for child in rpr if isinstance(child.tag, str)]
    indices = [RPR_ORDER.index(name) for name in names]
    assert indices == sorted(indices), f"urutan rPr tidak sesuai RPR_ORDER: {names}"


def test_toc_style_rpr_children_follow_rpr_order(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    ensure_toc_styles(package, tab_pos=9026)
    ensure_list_entry_style(package, tab_pos=9026)

    styles = package.xml("word/styles.xml")
    for style_id in (*TOC_STYLE_IDS, LIST_ENTRY_STYLE_ID):
        _assert_rpr_order(_style_by_id(styles, style_id))


def test_no_blank_page_between_toc_and_chapter_i(tmp_path: Path) -> None:
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


def test_tab_position_subtracts_gutter(tmp_path: Path) -> None:
    path = _write_package(
        tmp_path,
        _paragraph("BAB I", style="Heading1"),
        sect_pr=_page_geometry(gutter="720"),
    )
    package = DocumentPackage.load(path)
    assert tab_position(package) == 8306


def test_tab_position_incomplete_geometry_causes_toc_tab(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    with pytest.raises(TocError) as excinfo:
        tab_position(package)
    assert excinfo.value.code == "TOC-TAB"


def test_tab_position_uses_explicit_fallback(tmp_path: Path) -> None:
    path = _write_package(tmp_path, _paragraph("BAB I", style="Heading1"))
    package = DocumentPackage.load(path)
    assert tab_position(package, fallback=(11906, 1440, 1440, 0)) == 9026


def test_tab_position_invalid_fallback_causes_toc_tab(tmp_path: Path) -> None:
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


def test_format_fallback_uses_canonical_size_and_landscape() -> None:
    assert format_tab_fallback(_format_ctx("A4", "portrait")) == (11906, 1440, 1440, 0)
    assert format_tab_fallback(_format_ctx("Letter", "landscape")) == (15840, 1440, 1440, 0)


def test_format_fallback_returns_none_for_unknown_size() -> None:
    assert format_tab_fallback(_format_ctx("A5", "portrait")) is None
    assert format_tab_fallback(_format_ctx("LETTER", "portrait")) is None


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
