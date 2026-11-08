"""Tes post-process caption, gambar, dan tabel DOCX."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from lxml import etree

import format_figures as api

FIXTURES = Path(__file__).parent / "fixtures" / "format_figures"
BUILDER_PATH = FIXTURES / "make_fixture.py"
DOCUMENT_PART = "word/document.xml"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "format_figures_make_fixture", BUILDER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_builder = _load_builder()


@pytest.fixture(scope="session")
def docs(tmp_path_factory):
    root = tmp_path_factory.mktemp("format_figures")
    return SimpleNamespace(
        main=_builder.build_main_fixture(root / "contoh.docx"),
        oversized=_builder.build_oversized_fixture(root / "gambar_besar.docx"),
        no_heading=_builder.build_no_heading_fixture(root / "tanpa_heading.docx"),
        generic=_builder.build_generic_caption_fixture(root / "caption_generic.docx"),
        field=_builder.build_field_caption_fixture(root / "caption_field.docx"),
        pandoc=_builder.build_pandoc_caption_fixture(root / "caption_pandoc.docx"),
        missing=_builder.build_missing_caption_fixture(root / "tanpa_caption.docx"),
        below_table=_builder.build_below_table_caption_fixture(
            root / "caption_di_bawah.docx"
        ),
        cover_image=_builder.build_cover_image_fixture(root / "gambar_cover.docx"),
    )


def run_tool(source: Path, tmp_path: Path, stem: str = "out") -> Path:
    output = tmp_path / f"{stem}.docx"
    assert api.main(["--docx", str(source), "--out", str(output)]) == 0
    return output


def _pandoc() -> str:
    candidates = [
        os.environ.get("PANDOC"),
        shutil.which("pandoc"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Pandoc" / "pandoc.exe"),
        str(Path(os.environ.get("PROGRAMFILES", "")) / "Pandoc" / "pandoc.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    pytest.skip("pandoc tidak tersedia")


def _body_index(document: Document, element) -> int:
    return list(document.element.body).index(element)


def _assert_caption_style(paragraph, *, alignment: WD_ALIGN_PARAGRAPH, keep_next: bool):
    assert paragraph.alignment == alignment
    properties = paragraph._p.pPr
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


def caption_texts(path: Path, style_id: str) -> list[str]:
    document = Document(path)
    return [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.style.style_id == style_id
    ]


def document_xml(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        return archive.read(DOCUMENT_PART)


def xml_text(paragraph) -> str:
    return "".join(node.text or "" for node in paragraph._p.iter(qn("w:t")))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BAB I PENDAHULUAN", 1),
        ("BAB II TINJAUAN PUSTAKA", 2),
        ("BAB IV HASIL", 4),
        ("BAB IX", 9),
        ("BAB II.", 2),
        ("BAB 12", 12),
        ("1. PENDAHULUAN", 1),
        ("3. METODE PENELITIAN", 3),
        ("2 TINJAUAN PUSTAKA", 2),
        ("1.1 Latar Belakang", None),
        ("2.3 Metode Penelitian", None),
        ("DAFTAR GAMBAR", None),
        ("BAB IVAN", None),
    ],
)
def test_nomor_bab_romawi_dan_arab(text, expected):
    assert api._chapter_number(text) == expected


# ---------------------------------------------------------------------------
# 1. Nomor caption per bab


def test_nomor_caption_per_bab_reset(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)

    assert caption_texts(output, "ImageCaption") == [
        "Gambar 1.1 Diagram alur",
        "Gambar 1.2 Foto hasil",
        "Gambar 2.1 Arsitektur sistem",
    ]
    assert caption_texts(output, "TableCaption") == [
        "Tabel 1.1 Data responden",
        "Tabel 2.1 Hasil pengujian",
    ]


def test_proposal_heading1_arab_memberi_nomor_caption(tmp_path):
    source = tmp_path / "proposal.docx"
    document = Document()
    document.add_paragraph("1. PENDAHULUAN", style="Heading 1")
    table_caption = document.styles.add_style(
        "Table Caption", WD_STYLE_TYPE.PARAGRAPH
    )
    document.add_paragraph("Tabel 1. Data awal", style=table_caption)
    document.save(source)

    output = run_tool(source, tmp_path)

    assert caption_texts(output, "TableCaption") == ["Tabel 1.1 Data awal"]


# ---------------------------------------------------------------------------
# 2. Prefix lama dihapus dan idempoten


def test_prefix_lama_dihapus_dan_idempoten(docs, tmp_path):
    assert "Gambar 1. Diagram alur" in caption_texts(docs.main, "ImageCaption")
    assert "Gambar 1.2 Foto hasil" in caption_texts(docs.main, "ImageCaption")

    first = run_tool(docs.main, tmp_path, "first")
    second = run_tool(first, tmp_path, "second")

    expected_images = [
        "Gambar 1.1 Diagram alur",
        "Gambar 1.2 Foto hasil",
        "Gambar 2.1 Arsitektur sistem",
    ]
    expected_tables = [
        "Tabel 1.1 Data responden",
        "Tabel 2.1 Hasil pengujian",
    ]

    assert caption_texts(first, "ImageCaption") == expected_images
    assert caption_texts(second, "ImageCaption") == expected_images
    assert caption_texts(first, "TableCaption") == expected_tables
    assert caption_texts(second, "TableCaption") == expected_tables

    for paragraph_text in expected_images + expected_tables:
        assert not re.match(
            r"^(Gambar|Tabel)\s+\d+(?:\.\d+)?\.?\s+(Gambar|Tabel)\b",
            paragraph_text,
        )

    # Prefix tidak dobel dan seluruh XML identik pada run kedua.
    assert document_xml(first) == document_xml(second)

    document = Document(first)
    formatted_caption = next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text == "Gambar 1.2 Foto hasil"
    )
    # Gaya caption final wajib regular, termasuk run judul yang semula italic.
    assert formatted_caption.runs[-1].italic is False


# ---------------------------------------------------------------------------
# 3. Gambar 20 cm di-clamp ke 14 cm, tinggi proporsional


def test_gambar_besar_di_clamp_proporsional(docs, tmp_path):
    output = run_tool(docs.oversized, tmp_path)
    document = Document(output)

    assert len(document.inline_shapes) == 2
    big, small = document.inline_shapes

    assert big.width == api.MAX_IMAGE_WIDTH_EMU
    assert big.height == 2_520_000
    assert small.width == 3_600_000
    assert small.height == 1_800_000

    transform_extents = [
        extent
        for extent in document.element.body.iter(qn("a:ext"))
        if extent.get("cx") and extent.get("cy")
    ]
    assert (int(transform_extents[0].get("cx")), int(transform_extents[0].get("cy"))) == (
        api.MAX_IMAGE_WIDTH_EMU,
        2_520_000,
    )

    image_paragraphs = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph._p.findall(".//" + qn("w:drawing"))
    ]
    assert len(image_paragraphs) == 2
    for paragraph in image_paragraphs:
        assert paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER
        assert paragraph.paragraph_format.space_before == 0
        assert paragraph.paragraph_format.space_after == 0


# ---------------------------------------------------------------------------
# 4. Tabel data ilmiah: tanpa vertikal, border atas/bawah 1 pt, header 0,5 pt


def test_tabel_gaya_ilmiah(docs, tmp_path):
    source = Document(docs.main)
    output = run_tool(docs.main, tmp_path)
    result = Document(output)

    assert len(source.tables) == len(result.tables) == 2

    for before, after in zip(source.tables, result.tables):
        before_pr = before._tbl.tblPr
        after_pr = after._tbl.tblPr

        # Fixture memang diberi shading di level tabel/baris/sel.
        assert before_pr.find(qn("w:shd")) is not None
        assert before_pr.find(qn("w:tblBorders")) is not None
        assert before.rows[0]._tr.trPr.find(qn("w:shd")) is not None
        assert before.cell(0, 0)._tc.tcPr.find(qn("w:shd")) is not None

        assert after_pr.find(qn("w:shd")) is None

        borders = after_pr.find(qn("w:tblBorders"))
        assert borders is not None
        expected_borders = {
            "w:top": ("single", "8"),
            "w:bottom": ("single", "8"),
            "w:left": ("nil", None),
            "w:right": ("nil", None),
            "w:insideH": ("nil", None),
            "w:insideV": ("nil", None),
        }
        assert len(borders) == len(expected_borders)
        for tag, (value, size) in expected_borders.items():
            border = borders.find(qn(tag))
            assert border is not None, f"border {tag} tidak ada"
            assert border.get(qn("w:val")) == value
            assert border.get(qn("w:sz")) == size
            assert border.get(qn("w:color")) == "000000"

        cell_margins = after_pr.find(qn("w:tblCellMar"))
        assert cell_margins is not None
        expected_margins = {
            "w:top": "0",
            "w:bottom": "0",
            "w:left": "108",
            "w:right": "108",
        }
        for tag, value in expected_margins.items():
            margin = cell_margins.find(qn(tag))
            assert margin is not None, f"cell margin {tag} tidak ada"
            assert margin.get(qn("w:w")) == value
            assert margin.get(qn("w:type")) == "dxa"

        rows = after._tbl.findall(qn("w:tr"))
        header_row = rows[0]
        for cell in header_row.findall(qn("w:tc")):
            tc_borders = cell.find(f"{qn('w:tcPr')}/{qn('w:tcBorders')}")
            assert tc_borders is not None
            bottom = tc_borders.find(qn("w:bottom"))
            assert bottom is not None
            assert bottom.get(qn("w:val")) == "single"
            assert bottom.get(qn("w:sz")) == "4"
            assert bottom.get(qn("w:color")) == "000000"

        # Baris body tidak membawa border/margin sel sendiri.
        for row in rows[1:]:
            row_properties = row.find(qn("w:trPr"))
            if row_properties is not None:
                assert row_properties.find(qn("w:shd")) is None
            for cell in row.findall(qn("w:tc")):
                cell_properties = cell.find(qn("w:tcPr"))
                if cell_properties is None:
                    continue
                assert cell_properties.find(qn("w:shd")) is None
                assert cell_properties.find(qn("w:tcBorders")) is None
                assert cell_properties.find(qn("w:tcMar")) is None

        # Header tidak bold; border header tetap 0,5 pt.
        assert any(
            run.bold
            for cell in before.rows[0].cells
            for paragraph in cell.paragraphs
            for run in paragraph.runs
        )
        for cell in after.rows[0].cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    assert run.bold is False

        assert [[cell.text for cell in row.cells] for row in before.rows] == [
            [cell.text for cell in row.cells] for row in after.rows
        ]
        assert [column.width for column in before.columns] == [
            column.width for column in after.columns
        ]
        assert before.alignment == after.alignment
        assert [
            paragraph.alignment
            for row in before.rows
            for cell in row.cells
            for paragraph in cell.paragraphs
        ] == [
            paragraph.alignment
            for row in after.rows
            for cell in row.cells
            for paragraph in cell.paragraphs
        ]


def test_tabel_ilmiah_idempoten(docs, tmp_path):
    first = run_tool(docs.main, tmp_path, "first")
    second = run_tool(first, tmp_path, "second")

    assert document_xml(first) == document_xml(second)


def test_tabel_kode_tetap_108_dan_border_kotak_penuh(tmp_path):
    document = Document()
    code_style = document.styles.add_style(
        "Source Code", WD_STYLE_TYPE.PARAGRAPH
    )
    table = document.add_table(rows=1, cols=1)
    paragraph = table.cell(0, 0).paragraphs[0]
    paragraph.style = code_style
    paragraph.add_run("nilai = 1")

    table_properties = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        borders.append(border)
    table_properties.append(borders)

    source = tmp_path / "kode.docx"
    document.save(source)
    output = run_tool(source, tmp_path)

    result = Document(output)
    assert len(result.tables) == 1
    result_properties = result.tables[0]._tbl.tblPr

    result_borders = result_properties.find(qn("w:tblBorders"))
    assert result_borders is not None
    for side in ("top", "left", "bottom", "right"):
        border = result_borders.find(qn(f"w:{side}"))
        assert border.get(qn("w:val")) == "single"
        assert border.get(qn("w:sz")) == "8"
    for side in ("insideH", "insideV"):
        assert result_borders.find(qn(f"w:{side}")).get(qn("w:val")) == "nil"

    cell_margins = result_properties.find(qn("w:tblCellMar"))
    assert cell_margins is not None
    for side in ("top", "left", "bottom", "right"):
        assert cell_margins.find(qn(f"w:{side}")).get(qn("w:w")) == "108"
    assert result.tables[0]._tbl.findall(f".//{qn('w:tcBorders')}") == []


# ---------------------------------------------------------------------------
# 5. Tanpa Heading1: tidak menomori, tidak crash


def test_tanpa_heading_tidak_menomori(docs, tmp_path, capsys):
    output = tmp_path / "tanpa_heading.docx"
    assert api.main(["--docx", str(docs.no_heading), "--out", str(output)]) == 0
    captured = capsys.readouterr()
    assert "Heading1" in captured.err

    assert caption_texts(output, "ImageCaption") == [
        "Gambar 4.2 Diagram tanpa bab"
    ]
    assert caption_texts(output, "TableCaption") == ["Tabel 4.1 Data tanpa bab"]
    assert caption_texts(output, "Caption") == ["Gambar 9.9 Caption generik"]

    # Gambar dan tabel tetap diproses walau penomoran dilewati.
    document = Document(output)
    assert document.tables[0]._tbl.tblPr.find(qn("w:tblBorders")) is not None


# ---------------------------------------------------------------------------
# 6. ZIP valid dan bisa dibuka python-docx


def test_zip_valid_dan_bisa_dibuka_python_docx(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)

    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert DOCUMENT_PART in names
        assert "[Content_Types].xml" in names

    root = etree.fromstring(document_xml(output))
    assert root.find(qn("w:body")) is not None

    document = Document(output)
    assert document.paragraphs


# ---------------------------------------------------------------------------
# Tambahan: keamanan dan varian caption


def test_part_selain_document_tidak_berubah(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)

    with zipfile.ZipFile(docs.main) as source, zipfile.ZipFile(output) as result:
        for name in source.namelist():
            if name == DOCUMENT_PART:
                continue
            assert result.read(name) == source.read(name)

    document = Document(output)
    assert document.sections[0].header.paragraphs[0].text == "Header fixture"
    assert document.sections[0].footer.paragraphs[0].text == "Footer fixture"


def test_bookmark_dan_field_tidak_rusak(docs, tmp_path):
    output = run_tool(docs.main, tmp_path)
    document = Document(output)
    body = document.element.body

    bookmark_names = [
        bookmark.get(qn("w:name"))
        for bookmark in body.iter(qn("w:bookmarkStart"))
    ]
    assert "_TocGambar1" in bookmark_names

    instructions = [node.text or "" for node in body.iter(qn("w:instrText"))]
    assert any("PAGE" in instruction for instruction in instructions)

    field_types = [
        node.get(qn("w:fldCharType"))
        for node in body.iter(qn("w:fldChar"))
    ]
    assert field_types.count("begin") == field_types.count("end")


def test_caption_generic_style(docs, tmp_path):
    output = run_tool(docs.generic, tmp_path)

    assert caption_texts(output, "Caption") == [
        "Gambar 4.1 Diagram generik",
        "Tabel 4.1 Data generik",
        "Paragraf biasa, bukan caption.",
    ]

    document = Document(output)
    first_caption = next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.style.style_id == "Caption"
    )
    # Prefix lama dipecah ke dua run; run judul menjadi regular.
    assert first_caption.runs[0].text == "Gambar 4.1 "
    assert first_caption.runs[-1].text == "Diagram generik"
    assert first_caption.runs[-1].italic is False


def test_caption_dengan_prefix_field_dilewati(docs, tmp_path, capsys):
    output = tmp_path / "caption_field.docx"
    assert api.main(["--docx", str(docs.field), "--out", str(output)]) == 0
    captured = capsys.readouterr()
    assert "prefix nomornya" in captured.err

    document = Document(output)
    captions = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.style.style_id == "ImageCaption"
    ]
    assert len(captions) == 2

    # Caption pertama punya SEQ field di prefix: teks dan field dibiarkan.
    assert xml_text(captions[0]) == "Gambar 1.1 Diagram field"
    assert captions[0]._p.find(".//" + qn("w:fldSimple")) is not None

    # Caption berikutnya tetap mendapat nomor urut berikutnya.
    assert xml_text(captions[1]) == "Gambar 5.2 Diagram literal"


# ---------------------------------------------------------------------------
# 7. Caption wajib: w:tblCaption, paragraf Pandoc, dan alt text gambar


def test_caption_dari_tblcaption_paragraf_pandoc_dan_alt(docs, tmp_path):
    output = run_tool(docs.pandoc, tmp_path)

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
        paragraph
        for paragraph in document.paragraphs
        if paragraph.style.style_id == "TableCaption"
    ]
    image_paragraphs = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph._p.findall(".//" + qn("w:drawing"))
    ]
    image_captions = [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.style.style_id == "ImageCaption"
    ]

    # Caption tabel tepat di atas tabel; caption gambar tepat di bawah gambar.
    for caption, table in zip(table_captions, document.tables):
        assert _body_index(document, caption._p) + 1 == _body_index(
            document, table._tbl
        )
    for image, caption in zip(image_paragraphs, image_captions):
        assert _body_index(document, caption._p) == _body_index(
            document, image._p
        ) + 1

    _assert_caption_style(
        table_captions[0],
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        keep_next=True,
    )
    _assert_caption_style(
        image_captions[0],
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        keep_next=False,
    )


def test_caption_pandoc_idempoten(docs, tmp_path):
    first = run_tool(docs.pandoc, tmp_path, "first")
    second = run_tool(first, tmp_path, "second")

    assert document_xml(first) == document_xml(second)


def test_tabel_gambar_tanpa_caption_menggagalkan_build(docs, tmp_path, capsys):
    output = tmp_path / "tanpa_caption_out.docx"
    assert api.main(["--docx", str(docs.missing), "--out", str(output)]) == 1
    captured = capsys.readouterr()

    assert "Tabel #1" in captured.err
    assert "Gambar #1" in captured.err
    assert "tidak memiliki caption" in captured.err
    assert "Tabel/gambar tanpa caption: 2" in captured.out

    # Caption tidak boleh dikarang saat sumbernya memang tidak ada.
    document = Document(output)
    assert not [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.style.style_id in {"TableCaption", "ImageCaption"}
    ]


def test_laporan_tanpa_caption_melaporkan_semua_temuan(docs, tmp_path):
    report = api.format_figures(docs.missing, tmp_path / "report.docx")

    assert report.created_table_captions == 0
    assert report.created_image_captions == 0
    assert len(report.missing_captions) == 2
    assert any(item.startswith("Tabel #1") for item in report.missing_captions)
    assert any(item.startswith("Gambar #1") for item in report.missing_captions)


def test_caption_tabel_di_bawah_dipindah_ke_atas(docs, tmp_path):
    output = run_tool(docs.below_table, tmp_path)

    assert caption_texts(output, "TableCaption") == ["Tabel 1.1 Data responden"]

    document = Document(output)
    caption = next(
        paragraph
        for paragraph in document.paragraphs
        if paragraph.style.style_id == "TableCaption"
    )
    table = document.tables[0]
    assert _body_index(document, caption._p) + 1 == _body_index(document, table._tbl)


def test_gambar_cover_tidak_diwajibkan_caption(docs, tmp_path):
    output = run_tool(docs.cover_image, tmp_path)

    document = Document(output)
    assert document.paragraphs[0].style.style_id == "CoverImage"
    assert caption_texts(output, "ImageCaption") == []


# ---------------------------------------------------------------------------
# 8. End-to-end Pandoc: caption Markdown menjadi nomor Tabel/Gambar


def test_pandoc_caption_markdown_end_to_end(tmp_path):
    pandoc = _pandoc()
    (tmp_path / "gambar.png").write_bytes(_builder._png_bytes())
    source = tmp_path / "bercaption.md"
    source.write_text(
        "# BAB I PENDAHULUAN\n\n"
        ": Data responden\n\n"
        "| Nama | Nilai |\n"
        "| --- | --- |\n"
        "| Ahmad | 90 |\n\n"
        "![Diagram alur](gambar.png)\n",
        encoding="utf-8",
    )
    docx = tmp_path / "bercaption.docx"
    subprocess.run(
        [pandoc, source.name, "-o", docx.name],
        cwd=tmp_path,
        check=True,
        env={**os.environ, "PYTHONUTF8": "1"},
    )

    output = run_tool(docx, tmp_path)

    assert caption_texts(output, "TableCaption") == ["Tabel 1.1 Data responden"]
    assert caption_texts(output, "ImageCaption") == ["Gambar 1.1 Diagram alur"]


def test_pandoc_markdown_tanpa_caption_gagal(tmp_path, capsys):
    pandoc = _pandoc()
    (tmp_path / "gambar.png").write_bytes(_builder._png_bytes())
    source = tmp_path / "tanpa_caption.md"
    source.write_text(
        "# BAB I PENDAHULUAN\n\n"
        "| Nama | Nilai |\n"
        "| --- | --- |\n"
        "| Ahmad | 90 |\n\n"
        "![](gambar.png)\n",
        encoding="utf-8",
    )
    docx = tmp_path / "tanpa_caption.docx"
    subprocess.run(
        [pandoc, source.name, "-o", docx.name],
        cwd=tmp_path,
        check=True,
        env={**os.environ, "PYTHONUTF8": "1"},
    )

    output = tmp_path / "tanpa_caption_out.docx"
    assert api.main(["--docx", str(docx), "--out", str(output)]) == 1
    captured = capsys.readouterr()
    assert "Tabel #1" in captured.err
    assert "Gambar #1" in captured.err
