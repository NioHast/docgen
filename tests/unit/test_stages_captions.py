"""Tes unit stage ``captions`` dengan fixture DOCX."""

import importlib.util
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

from docgen.docx.captions import (
    CaptionError,
    CaptionKind,
    caption_style,
    ensure_caption,
    iter_captions,
    set_caption,
)
from docgen.docx.package import DOCUMENT_PART, DocumentPackage
from docgen.docx.xml import sha256_c14n
from docgen.stages.captions import CaptionsStage, apply_captions
from docgen.stages.code import apply_code

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "format_figures"
BUILDER_PATH = FIXTURES / "make_fixture.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("format_figures_make_fixture", BUILDER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_builder = _load_builder()


@pytest.fixture(scope="session")
def docs(tmp_path_factory):
    root = tmp_path_factory.mktemp("captions_stage")
    return SimpleNamespace(
        main=_builder.build_main_fixture(root / "contoh.docx"),
        oversized=_builder.build_oversized_fixture(root / "gambar_besar.docx"),
        no_heading=_builder.build_no_heading_fixture(root / "tanpa_heading.docx"),
        generic=_builder.build_generic_caption_fixture(root / "caption_generic.docx"),
        field=_builder.build_field_caption_fixture(root / "caption_field.docx"),
        pandoc=_builder.build_pandoc_caption_fixture(root / "caption_pandoc.docx"),
        missing=_builder.build_missing_caption_fixture(root / "tanpa_caption.docx"),
        below_table=_builder.build_below_table_caption_fixture(root / "caption_di_bawah.docx"),
        cover_image=_builder.build_cover_image_fixture(root / "gambar_cover.docx"),
    )


def caption_texts(path: Path, style_id: str) -> list[str]:
    document = Document(path)
    return [
        paragraph.text for paragraph in document.paragraphs if paragraph.style.style_id == style_id
    ]


def body_index(document: Document, element) -> int:
    return list(document.element.body).index(element)


def assert_caption_style(
    paragraph,
    *,
    alignment: WD_ALIGN_PARAGRAPH,
    keep_next: bool,
) -> None:
    assert paragraph.alignment == alignment
    properties = paragraph._p.pPr
    assert properties is not None
    spacing = properties.find(qn("w:spacing"))
    assert spacing is not None
    assert spacing.get(qn("w:before")) == "0"
    assert spacing.get(qn("w:after")) == "0"
    assert spacing.get(qn("w:line")) == "240"
    assert spacing.get(qn("w:lineRule")) == "auto"

    keep = properties.find(qn("w:keepNext"))
    if keep_next:
        assert keep is not None
    else:
        assert keep is None

    for run in paragraph.runs:
        assert run.font.size == Pt(10)
        assert run.bold is False
        assert run.italic is False


# ---------------------------------------------------------------------------
# 1. Nomor caption per bab dan idempotensi
# ---------------------------------------------------------------------------


def test_nomor_caption_per_bab_reset(docs, tmp_path):
    package = DocumentPackage.load(docs.main)
    report = apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert report.heading1_count == 2
    assert report.bab_headings == 2
    assert report.image_captions == 3
    assert report.table_captions == 2
    assert report.missing_captions == []

    assert caption_texts(output, "ImageCaption") == [
        "Gambar 1.1 Diagram alur",
        "Gambar 1.2 Foto hasil",
        "Gambar 2.1 Arsitektur sistem",
    ]
    assert caption_texts(output, "TableCaption") == [
        "Tabel 1.1 Data responden",
        "Tabel 2.1 Hasil pengujian",
    ]


def test_heading_arabic_dotted_memberi_nomor_bab_empat(tmp_path):
    document = Document()
    document.add_paragraph("4. Metode", style="Heading 1")
    document.styles.add_style("TableCaption", WD_STYLE_TYPE.PARAGRAPH)
    document.styles.add_style("ImageCaption", WD_STYLE_TYPE.PARAGRAPH)
    document.add_paragraph("Tabel 1.1 Data", style="TableCaption")
    document.add_paragraph("Gambar 1.1 Diagram", style="ImageCaption")

    source = tmp_path / "arabic.docx"
    document.save(source)
    package = DocumentPackage.load(source)

    report = apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert report.bab_headings == 1
    assert caption_texts(output, "TableCaption") == ["Tabel 4.1 Data"]
    assert caption_texts(output, "ImageCaption") == ["Gambar 4.1 Diagram"]


def test_prefix_lama_dihapus_dan_idempoten(docs, tmp_path):
    package = DocumentPackage.load(docs.main)
    apply_captions(package)
    first_path = tmp_path / "first.docx"
    package.save(first_path)

    second_package = DocumentPackage.load(first_path)
    second_report = apply_captions(second_package)
    second_path = tmp_path / "second.docx"
    second_package.save(second_path)

    assert caption_texts(first_path, "ImageCaption") == [
        "Gambar 1.1 Diagram alur",
        "Gambar 1.2 Foto hasil",
        "Gambar 2.1 Arsitektur sistem",
    ]
    assert caption_texts(second_path, "ImageCaption") == [
        "Gambar 1.1 Diagram alur",
        "Gambar 1.2 Foto hasil",
        "Gambar 2.1 Arsitektur sistem",
    ]
    assert second_report.changed is False
    assert sha256_c14n(DocumentPackage.load(first_path).part(DOCUMENT_PART)) == sha256_c14n(
        DocumentPackage.load(second_path).part(DOCUMENT_PART)
    )

    document = Document(first_path)
    formatted = next(
        paragraph for paragraph in document.paragraphs if paragraph.text == "Gambar 1.2 Foto hasil"
    )
    assert formatted.runs[-1].italic is False


def test_scope_document_meneruskan_counter(docs, tmp_path):
    package = DocumentPackage.load(docs.main)
    report = apply_captions(package, scope="document")
    output = tmp_path / "out.docx"
    package.save(output)

    assert report.image_captions == 3
    assert report.table_captions == 2
    assert caption_texts(output, "ImageCaption") == [
        "Gambar 1 Diagram alur",
        "Gambar 2 Foto hasil",
        "Gambar 3 Arsitektur sistem",
    ]
    assert caption_texts(output, "TableCaption") == [
        "Tabel 1 Data responden",
        "Tabel 2 Hasil pengujian",
    ]
    assert not any("Heading1" in warning for warning in report.warnings)


# ---------------------------------------------------------------------------
# 2. Caption wajib dari Pandoc dan caption di sisi yang benar
# ---------------------------------------------------------------------------


def test_caption_dari_tblcaption_paragraf_pandoc_dan_alt(docs, tmp_path):
    package = DocumentPackage.load(docs.pandoc)
    report = apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert report.created_table_captions == 1
    assert report.created_image_captions == 2
    assert report.missing_captions == []

    assert caption_texts(output, "TableCaption") == [
        "Tabel 1.1 Data responden",
        "Tabel 1.2 Hasil pengujian",
    ]
    assert caption_texts(output, "ImageCaption") == [
        "Gambar 1.1 Diagram alur",
        "Gambar 1.2 Foto hasil",
        "Gambar 1.3 Foto tambahan",
    ]

    document = Document(output)
    table_captions = [
        paragraph for paragraph in document.paragraphs if paragraph.style.style_id == "TableCaption"
    ]
    image_paragraphs = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph._p.findall(".//" + qn("w:drawing"))
    ]
    image_captions = [
        paragraph for paragraph in document.paragraphs if paragraph.style.style_id == "ImageCaption"
    ]

    for caption, table in zip(table_captions, document.tables, strict=True):
        assert body_index(document, caption._p) + 1 == body_index(document, table._tbl)
    for image, caption in zip(image_paragraphs, image_captions, strict=True):
        assert body_index(document, caption._p) == body_index(document, image._p) + 1

    assert_caption_style(
        table_captions[0],
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        keep_next=True,
    )
    assert_caption_style(
        image_captions[0],
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        keep_next=False,
    )


def test_caption_tabel_di_bawah_dipindah_ke_atas(docs, tmp_path):
    package = DocumentPackage.load(docs.below_table)
    apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert caption_texts(output, "TableCaption") == ["Tabel 1.1 Data responden"]
    document = Document(output)
    caption = next(
        paragraph for paragraph in document.paragraphs if paragraph.style.style_id == "TableCaption"
    )
    table = document.tables[0]
    assert body_index(document, caption._p) + 1 == body_index(document, table._tbl)


def test_tabel_gambar_tanpa_caption_menggagalkan_stage(docs):
    package = DocumentPackage.load(docs.missing)

    with pytest.raises(CaptionError) as caught:
        apply_captions(package)

    error = caught.value
    assert error.code == "CAPTION-MISSING"
    assert len(error.missing) == 2
    assert any(item.startswith("Tabel #1") for item in error.missing)
    assert any(item.startswith("Gambar #1") for item in error.missing)

    root = package.xml(DOCUMENT_PART)
    captions = []
    for paragraph in root.iter(qn("w:p")):
        style = paragraph.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
        if style is not None and style.get(qn("w:val")) in {
            "TableCaption",
            "ImageCaption",
        }:
            captions.append(paragraph)
    assert captions == []


def test_caption_generic_style(docs, tmp_path):
    package = DocumentPackage.load(docs.generic)
    apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert caption_texts(output, "Caption") == [
        "Gambar 4.1 Diagram generik",
        "Tabel 4.1 Data generik",
        "Paragraf biasa, bukan caption.",
    ]


def test_caption_dengan_prefix_field_dilewati(docs, tmp_path):
    package = DocumentPackage.load(docs.field)
    report = apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert report.skipped_field == 1
    assert any("prefix nomornya" in warning for warning in report.warnings)

    document = Document(output)
    captions = [
        paragraph for paragraph in document.paragraphs if paragraph.style.style_id == "ImageCaption"
    ]
    assert len(captions) == 2
    assert captions[0]._p.find(".//" + qn("w:fldSimple")) is not None
    assert captions[0].text == "Gambar 1. Diagram field"
    assert captions[1].text == "Gambar 5.2 Diagram literal"


# ---------------------------------------------------------------------------
# 3. Gambar: clamp, perataan, dan cover
# ---------------------------------------------------------------------------


def test_gambar_besar_di_clamp_proporsional(docs, tmp_path):
    package = DocumentPackage.load(docs.oversized)
    report = apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert report.images_clamped == 1
    document = Document(output)
    big, small = document.inline_shapes

    assert big.width == 14 * 360_000
    assert big.height == 2_520_000
    assert small.width == 3_600_000
    assert small.height == 1_800_000

    image_paragraphs = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph._p.findall(".//" + qn("w:drawing"))
    ]
    for paragraph in image_paragraphs:
        assert paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER
        assert paragraph.paragraph_format.space_before == 0
        assert paragraph.paragraph_format.space_after == 0


def test_gambar_cover_tidak_diwajibkan_caption(docs, tmp_path):
    package = DocumentPackage.load(docs.cover_image)
    report = apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert report.missing_captions == []
    document = Document(output)
    assert document.paragraphs[0].style.style_id == "CoverImage"
    assert caption_texts(output, "ImageCaption") == []


# ---------------------------------------------------------------------------
# 4. Tabel data dan tabel kode
# ---------------------------------------------------------------------------


def test_tabel_gaya_ilmiah(docs, tmp_path):
    package = DocumentPackage.load(docs.main)
    apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    document = Document(output)
    assert len(document.tables) == 2

    for table in document.tables:
        properties = table._tbl.tblPr
        assert properties.find(qn("w:shd")) is None

        borders = properties.find(qn("w:tblBorders"))
        assert borders is not None
        expected = {
            "top": ("single", "8"),
            "bottom": ("single", "8"),
            "left": ("nil", None),
            "right": ("nil", None),
            "insideH": ("nil", None),
            "insideV": ("nil", None),
        }
        for side, values in expected.items():
            border = borders.find(qn(f"w:{side}"))
            assert border is not None
            assert (border.get(qn("w:val")), border.get(qn("w:sz"))) == values

        cell_margins = properties.find(qn("w:tblCellMar"))
        assert cell_margins is not None
        assert {
            side: cell_margins.find(qn(f"w:{side}")).get(qn("w:w"))
            for side in ("top", "left", "bottom", "right")
        } == {"top": "0", "left": "108", "bottom": "0", "right": "108"}

        header_row = table._tbl.findall(qn("w:tr"))[0]
        for cell in header_row.findall(qn("w:tc")):
            border = cell.find(f"{qn('w:tcPr')}/{qn('w:tcBorders')}/{qn('w:bottom')}")
            assert border is not None
            assert border.get(qn("w:val")) == "single"
            assert border.get(qn("w:sz")) == "4"

        for cell in header_row.findall(qn("w:tc")):
            for paragraph in cell.findall(qn("w:p")):
                for run in paragraph.findall(qn("w:r")):
                    bold = run.find(f"{qn('w:rPr')}/{qn('w:b')}")
                    if bold is not None:
                        assert bold.get(qn("w:val")) == "0"


def test_code_table_tidak_diberi_caption(tmp_path):
    document = Document()
    code_style = document.styles.add_style("Source Code", WD_STYLE_TYPE.PARAGRAPH)
    for text in ("def main():", "    return 1"):
        paragraph = document.add_paragraph(style=code_style)
        paragraph.add_run(text)
    source = tmp_path / "kode.docx"
    document.save(source)

    package = DocumentPackage.load(source)
    code_report = apply_code(package)
    caption_report = apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    assert code_report.tables == 1
    assert caption_report.table_captions == 0
    assert caption_report.created_table_captions == 0

    result = Document(output)
    assert len(result.tables) == 1
    table = result.tables[0]
    assert len(table.rows) == 1
    assert len(table.columns) == 1
    assert not [
        paragraph for paragraph in result.paragraphs if paragraph.style.style_id == "TableCaption"
    ]


# ---------------------------------------------------------------------------
# 5. API caption, part non-target, dan metadata stage
# ---------------------------------------------------------------------------


def test_iter_captions_dan_set_caption(docs, tmp_path):
    package = DocumentPackage.load(docs.main)
    apply_captions(package)

    captions = iter_captions(package)
    assert [caption.kind for caption in captions] == [
        CaptionKind.FIGURE,
        CaptionKind.FIGURE,
        CaptionKind.TABLE,
        CaptionKind.FIGURE,
        CaptionKind.TABLE,
    ]
    first = captions[0]
    assert first.number == "1.1"
    assert first.text == "Diagram alur"

    set_caption(package, first, text="Diagram baru", number="9.9")
    assert first.paragraph.find(".//" + qn("w:t")).text == "Gambar 9.9 Diagram baru"


def test_ensure_caption_membuat_dari_alt_text(tmp_path):
    document = Document()
    heading = document.styles["Heading 1"]
    document.add_paragraph("BAB I PENDAHULUAN", style=heading)

    # Gambar tanpa caption tetapi dengan alt text.
    import struct
    import zlib
    from io import BytesIO

    def png_bytes(width=20, height=10):
        def chunk(kind, data):
            checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

        header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        row = bytes((200, 200, 200)) * width
        pixels = b"".join(b"\x00" + row for _ in range(height))
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(pixels, 9))
            + chunk(b"IEND", b"")
        )

    paragraph = document.add_paragraph()
    paragraph.add_run().add_picture(BytesIO(png_bytes()), width=Pt(80))
    for doc_pr in paragraph._p.iter(qn("wp:docPr")):
        doc_pr.set("descr", "Diagram API")

    source = tmp_path / "api.docx"
    document.save(source)

    package = DocumentPackage.load(source)
    root = package.xml(DOCUMENT_PART)
    body = root.find(qn("w:body"))
    image_paragraph = body.findall(qn("w:p"))[-1]

    caption = ensure_caption(
        package,
        kind=CaptionKind.FIGURE,
        anchor=image_paragraph,
        text="Diagram API",
    )
    assert caption.text == "Diagram API"
    assert caption_style(CaptionKind.FIGURE) == "ImageCaption"
    assert image_paragraph.getnext() is caption.paragraph
    assert (
        caption.paragraph.find(f"{qn('w:pPr')}/{qn('w:pStyle')}").get(qn("w:val")) == "ImageCaption"
    )


def test_part_non_target_byte_identik(docs, tmp_path):
    package = DocumentPackage.load(docs.main)
    original = {name: package.part(name) for name in package.part_names() if name != DOCUMENT_PART}

    apply_captions(package)
    output = tmp_path / "out.docx"
    package.save(output)

    with zipfile.ZipFile(docs.main) as _source, zipfile.ZipFile(output) as result:
        for name, payload in original.items():
            assert result.read(name) == payload


def test_caption_stage_metadata():
    stage = CaptionsStage()
    assert stage.name.value == "captions"
    assert stage.order == 70
    assert stage.mutates == frozenset({"word/document.xml"})
    assert stage.idempotent is True
