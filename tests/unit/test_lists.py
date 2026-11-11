"""Tes unit stage ``lists``: field daftar, field ``SEQ`` caption, idempotensi."""

import html
import zipfile
from pathlib import Path
from types import SimpleNamespace

from docgen.docx.fields import (
    FieldKind,
    field_instruction,
    insert_seq,
    insert_toc,
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
from docgen.docx.xml import qn, sha256_c14n
from docgen.pipeline import StageName, canonical_prefix
from docgen.stages import lists as lists_module
from docgen.stages.lists import ListsStage

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
    '<w:style w:type="paragraph" w:styleId="TableCaption">'
    '<w:name w:val="Table Caption"/><w:basedOn w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="ImageCaption">'
    '<w:name w:val="Image Caption"/><w:basedOn w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="TOCHeading">'
    '<w:name w:val="TOC Heading"/><w:basedOn w:val="Normal"/></w:style>'
    "</w:styles>"
).encode()

SECT_PR = (
    "<w:sectPr>"
    '<w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" '
    'w:left="1440" w:header="720" w:footer="720"/>'
    "</w:sectPr>"
)
CONTENT_WIDTH = 11906 - 1440 - 1440


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


def _paragraph(text: str = "", *, style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{html.escape(style)}"/></w:pPr>' if style else ""
    runs = f"<w:r><w:t>{html.escape(text)}</w:t></w:r>" if text else ""
    return f"<w:p>{ppr}{runs}</w:p>"


def _document(body: str, *, sect_pr: str = SECT_PR) -> bytes:
    return (
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">'
        f"<w:body>{body}{sect_pr}</w:body></w:document>"
    ).encode()


def _write_package(
    tmp_path: Path,
    body: str,
    *,
    name: str = "lists.docx",
    sect_pr: str = SECT_PR,
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
        for entry_name, data in entries.items():
            archive.writestr(entry_name, data)
    return path


def _a4_page() -> SimpleNamespace:
    return SimpleNamespace(
        size="A4",
        orientation="portrait",
        margins=SimpleNamespace(top=1440, right=1440, bottom=1440, left=1440),
    )


def _ctx(
    package: DocumentPackage,
    *,
    front_matter: tuple[str, ...] = (
        "cover",
        "toc",
        "list_of_tables",
        "list_of_figures",
    ),
    tables: bool = True,
    figures: bool = True,
    numbering: str = "chapter",
    page: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        package=package,
        document=SimpleNamespace(),
        structure=SimpleNamespace(
            toc=True,
            front_matter=tuple(SimpleNamespace(id=item) for item in front_matter),
            lists=SimpleNamespace(tables=tables, figures=figures),
        ),
        format=SimpleNamespace(
            captions=SimpleNamespace(
                table=SimpleNamespace(label="Tabel", separator=" "),
                figure=SimpleNamespace(label="Gambar", separator=" "),
            ),
            figures=SimpleNamespace(numbering=numbering),
            page=page,
        ),
        options=SimpleNamespace(),
        dry_run=False,
    )


def _body(package: DocumentPackage):
    body = package.xml(DOCUMENT_PART).find(qn("w:body"))
    assert body is not None
    return body


def _toc_sdts(package: DocumentPackage):
    return [
        child for child in _body(package) if isinstance(child.tag, str) and child.tag == qn("w:sdt")
    ]


def _sdt_title(sdt) -> str:
    return " ".join("".join(paragraph_text(item) for item in sdt.iter(qn("w:p"))).split())


def _sdt_heading(sdt):
    content = sdt.find(qn("w:sdtContent"))
    assert content is not None
    return content.find(qn("w:p"))


def _has_page_break_before(paragraph) -> bool:
    ppr = paragraph.find(qn("w:pPr"))
    return ppr is not None and ppr.find(qn("w:pageBreakBefore")) is not None


def _style(package: DocumentPackage, style_id: str):
    styles = package.xml("word/styles.xml")
    return next(style for style in styles if style.get(qn("w:styleId")) == style_id)


def _caption(package: DocumentPackage, text: str):
    for paragraph in package.xml(DOCUMENT_PART).iter(qn("w:p")):
        if paragraph_text(paragraph) == text:
            return paragraph
    raise AssertionError(f"caption tidak ditemukan: {text}")


def _instructions(package: DocumentPackage) -> list[str]:
    return [field_instruction(field) for field in iter_fields(package)]


def _build_package(tmp_path: Path, *, with_main_toc: bool = True) -> DocumentPackage:
    body = "".join(
        [
            _paragraph("BAB II", style="Heading1"),
            _paragraph("Isi bab kedua."),
            _paragraph("Tabel 2.1 Judul Tabel Satu", style="TableCaption"),
            _paragraph("Gambar 2.1 Diagram Alur", style="ImageCaption"),
        ]
    )
    path = _write_package(tmp_path, body)
    package = DocumentPackage.load(path)
    if with_main_toc:
        insert_toc(package, title="DAFTAR ISI")
    return package


# ---------------------------------------------------------------------------
# Metadata dan field
# ---------------------------------------------------------------------------


def test_stage_metadata() -> None:
    stage = ListsStage()
    assert stage.name is StageName.LISTS
    assert stage.order == 150
    assert stage.requires == canonical_prefix(StageName.LISTS)
    assert stage.mutates == frozenset({"word/document.xml", "word/styles.xml"})
    assert stage.idempotent is True


def test_inserts_two_list_fields_and_preserves_main_toc(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    result = ListsStage().run(_ctx(package))
    assert result.status == "ok"
    assert result.changed is True

    instructions = _instructions(package)
    assert sum("\\o" in item for item in instructions) == 1
    assert sum('TOC \\c "Tabel"' in item for item in instructions) == 1
    assert sum('TOC \\c "Gambar"' in item for item in instructions) == 1

    titles = [_sdt_title(sdt) for sdt in _toc_sdts(package)]
    assert titles == ["DAFTAR ISI", "DAFTAR TABEL", "DAFTAR GAMBAR"]


def test_list_headings_start_on_new_page(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    ListsStage().run(_ctx(package))

    sdts = _toc_sdts(package)
    assert [_sdt_title(sdt) for sdt in sdts] == ["DAFTAR ISI", "DAFTAR TABEL", "DAFTAR GAMBAR"]
    assert _has_page_break_before(_sdt_heading(sdts[0])) is False
    assert _has_page_break_before(_sdt_heading(sdts[1])) is True
    assert _has_page_break_before(_sdt_heading(sdts[2])) is True


def test_list_entry_style_is_flush_left_with_content_width_tab(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    ListsStage().run(_ctx(package))

    style = _style(package, "TableofFigures")
    assert style.find(qn("w:basedOn")).get(qn("w:val")) == "Normal"
    assert style.find(qn("w:next")).get(qn("w:val")) == "Normal"
    assert style.find(qn("w:name")).get(qn("w:val")) == "table of figures"

    ppr = style.find(qn("w:pPr"))
    assert ppr is not None
    ind = ppr.find(qn("w:ind"))
    assert (
        ind.get(qn("w:left")),
        ind.get(qn("w:right")),
        ind.get(qn("w:firstLine")),
    ) == ("0", "0", "0")
    tab = ppr.find(f"{qn('w:tabs')}/{qn('w:tab')}")
    assert tab.get(qn("w:val")) == "right"
    assert tab.get(qn("w:leader")) == "dot"
    assert tab.get(qn("w:pos")) == str(CONTENT_WIDTH)


def test_list_entry_style_without_page_geometry_has_no_tabs(tmp_path: Path) -> None:
    body = _paragraph("BAB II", style="Heading1")
    path = _write_package(tmp_path, body, sect_pr="<w:sectPr/>")
    package = DocumentPackage.load(path)

    result = ListsStage().run(_ctx(package, front_matter=("cover", "toc", "list_of_tables")))
    assert result.status == "ok"
    assert result.changed is True

    style = _style(package, "TableofFigures")
    assert style.find(f"{qn('w:pPr')}/{qn('w:tabs')}") is None


def test_list_entry_style_uses_format_fallback_without_page_geometry(tmp_path: Path) -> None:
    body = _paragraph("BAB II", style="Heading1")
    path = _write_package(tmp_path, body, sect_pr="<w:sectPr/>")
    package = DocumentPackage.load(path)

    result = ListsStage().run(
        _ctx(
            package,
            front_matter=("cover", "toc", "list_of_tables"),
            page=_a4_page(),
        )
    )
    assert result.status == "ok"

    style = _style(package, "TableofFigures")
    tab = style.find(f"{qn('w:pPr')}/{qn('w:tabs')}/{qn('w:tab')}")
    assert tab is not None
    assert tab.get(qn("w:val")) == "right"
    assert tab.get(qn("w:leader")) == "dot"
    assert tab.get(qn("w:pos")) == str(CONTENT_WIDTH)


def test_caption_seq_fields_are_hybrid_chapter(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    ListsStage().run(_ctx(package))

    table = _caption(package, "Tabel 2.1 Judul Tabel Satu")
    figure = _caption(package, "Gambar 2.1 Diagram Alur")
    table_fields = [
        field for field in iter_fields_in_paragraph(table) if field.kind is FieldKind.SEQ
    ]
    figure_fields = [
        field for field in iter_fields_in_paragraph(figure) if field.kind is FieldKind.SEQ
    ]
    assert len(table_fields) == 1
    assert len(figure_fields) == 1
    assert "SEQ Tabel \\* ARABIC \\s 1" in field_instruction(table_fields[0])
    assert "SEQ Gambar \\* ARABIC \\s 1" in field_instruction(figure_fields[0])
    assert paragraph_text(table) == "Tabel 2.1 Judul Tabel Satu"
    assert paragraph_text(figure) == "Gambar 2.1 Diagram Alur"


def test_caption_seq_uses_canonical_insert_field(monkeypatch, tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    calls: list[tuple[tuple[str, ...], str]] = []
    real_insert_field = lists_module.insert_field

    def record(switches, position, result=""):
        calls.append((tuple(switches), result))
        return real_insert_field(switches, position, result)

    monkeypatch.setattr(lists_module, "insert_field", record)
    ListsStage().run(_ctx(package))

    assert calls == [
        (("SEQ", "Tabel", "\\*", "ARABIC", "\\s", "1"), "1"),
        (("SEQ", "Gambar", "\\*", "ARABIC", "\\s", "1"), "1"),
    ]


def test_list_toc_keeps_main_toc_with_keep_existing(monkeypatch, tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    main_toc = _toc_sdts(package)[0]
    calls: list[dict[str, object]] = []
    real_insert_toc = lists_module.insert_toc

    def record(pkg, **kwargs):
        calls.append(kwargs)
        return real_insert_toc(pkg, **kwargs)

    monkeypatch.setattr(lists_module, "insert_toc", record)
    ListsStage().run(_ctx(package))

    assert [call["caption"] for call in calls] == ["Tabel", "Gambar"]
    assert all(call["keep_existing"] is True for call in calls)
    assert _toc_sdts(package)[0] is main_toc


def test_document_scope_uses_plain_seq_arabic(tmp_path: Path) -> None:
    body = "".join(
        [
            _paragraph("BAB II", style="Heading1"),
            _paragraph("Tabel 5 Judul Tabel Satu", style="TableCaption"),
        ]
    )
    package = DocumentPackage.load(_write_package(tmp_path, body))
    ListsStage().run(
        _ctx(package, front_matter=("cover", "toc", "list_of_tables"), numbering="document")
    )
    table = _caption(package, "Tabel 5 Judul Tabel Satu")
    fields = [field for field in iter_fields_in_paragraph(table) if field.kind is FieldKind.SEQ]
    assert len(fields) == 1
    assert field_instruction(fields[0]) == "SEQ Tabel \\* ARABIC"
    assert paragraph_text(table) == "Tabel 5 Judul Tabel Satu"


def test_existing_caption_field_is_not_duplicated(tmp_path: Path) -> None:
    body = "".join(
        [
            _paragraph("BAB II", style="Heading1"),
            _paragraph("Tabel 2.1 Judul Tabel Satu", style="TableCaption"),
        ]
    )
    package = DocumentPackage.load(_write_package(tmp_path, body))
    caption = _caption(package, "Tabel 2.1 Judul Tabel Satu")
    insert_seq(package, paragraph=caption, label="Tabel")
    before = len(iter_fields_in_paragraph(caption))

    ListsStage().run(_ctx(package, front_matter=("cover", "toc", "list_of_tables")))
    fields = iter_fields_in_paragraph(caption)
    assert len(fields) == before
    assert sum(field.kind is FieldKind.SEQ for field in fields) == 1


def test_front_matter_order_is_preserved(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    ListsStage().run(
        _ctx(
            package,
            front_matter=("cover", "toc", "list_of_figures", "list_of_tables"),
        )
    )
    titles = [_sdt_title(sdt) for sdt in _toc_sdts(package)]
    assert titles == ["DAFTAR ISI", "DAFTAR GAMBAR", "DAFTAR TABEL"]


def test_no_main_toc_still_inserts_lists(tmp_path: Path) -> None:
    package = _build_package(tmp_path, with_main_toc=False)
    ListsStage().run(_ctx(package))
    titles = [_sdt_title(sdt) for sdt in _toc_sdts(package)]
    assert titles == ["DAFTAR TABEL", "DAFTAR GAMBAR"]


def test_stage_is_idempotent(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    ctx = _ctx(package)
    stage = ListsStage()
    before_styles = sha256_c14n(package.xml("word/styles.xml"))
    stage.run(ctx)
    assert sha256_c14n(package.xml("word/styles.xml")) != before_styles
    first = sha256_c14n(package.xml(DOCUMENT_PART))
    first_styles = sha256_c14n(package.xml("word/styles.xml"))
    result = stage.run(ctx)
    second = sha256_c14n(package.xml(DOCUMENT_PART))
    assert result.changed is False
    assert result.metrics["seq_fields"] == 0
    assert second == first
    assert sha256_c14n(package.xml("word/styles.xml")) == first_styles
    instructions = _instructions(package)
    assert sum('TOC \\c "Tabel"' in item for item in instructions) == 1
    assert sum('TOC \\c "Gambar"' in item for item in instructions) == 1


def test_no_lists_means_skipped(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    before = sha256_c14n(package.xml(DOCUMENT_PART))
    ctx = _ctx(package, front_matter=("cover", "toc"), tables=False, figures=False)
    stage = ListsStage()
    assert stage.enabled(ctx) is False
    result = stage.run(ctx)
    assert result.status == "skipped"
    assert result.changed is False
    assert sha256_c14n(package.xml(DOCUMENT_PART)) == before


def test_dry_run_skips_without_mutation(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    before = sha256_c14n(package.xml(DOCUMENT_PART))
    ctx = _ctx(package)
    ctx.dry_run = True
    result = ListsStage().run(ctx)
    assert result.status == "skipped"
    assert result.changed is False
    assert sha256_c14n(package.xml(DOCUMENT_PART)) == before
