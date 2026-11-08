#!/usr/bin/env python3
"""Tes struktur penomoran halaman Laporan.docx.

Membaca DOCX hasil `build-docx.sh` (default: Laporan.docx di root repo,
bisa dioverride lewat environment variable LAPORAN_DOCX) dan memeriksa:

  - minimal tiga seksi (`w:sectPr`), sampul tanpa nomor/header/footer;
  - front matter lowerRoman mulai 1, footer tengah 12 pt, tanpa header;
  - body decimal mulai 1 dan berlanjut antar section;
  - setiap section body memakai `w:titlePg`;
  - header default body PAGE kanan 10 pt;
  - header halaman pertama bab kosong (tidak ada field PAGE);
  - footer halaman pertama bab PAGE tengah 12 pt;
  - footer default body kosong secara visual; probe PAGE tersembunyi
    (`vanish` + putih) masih diizinkan agar docx-pagenum.py dapat membaca
    nomor halaman dari baris terakhir PDF;
  - settings.xml tanpa `w:updateFields` dan compatibilityMode 15;
  - style Hyperlink hitam tanpa underline, Heading1/2/3 before/after 0;
  - style TOC1/TOC2 before/after 0 dan entri TOC tidak bold (TOCHeading
    tetap bold);
  - caption 10 pt (TableCaption rata kiri, ImageCaption tengah);
  - tabel data dan tabel kode memakai border ilmiah: garis atas/bawah
    1 pt (`w:sz 8`), tanpa garis vertikal, padding horizontal 108 twip;
  - style kode memakai Courier New 10 pt hitam tanpa shading;
  - field TOC/PAGEREF tidak rusak.

Jalankan:
  python -m unittest tests.test_pagenumber -v
  python -m pytest tests/test_pagenumber.py -v
"""

import os
import re
import unittest
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
DOCX_PATH = Path(os.environ.get("LAPORAN_DOCX", ROOT / "Laporan.docx"))

SECT_RE = re.compile(r"<w:sectPr\b[^>]*>.*?</w:sectPr>", re.S)
PARA_RE = re.compile(r"<w:p\b[^>]*>(?:(?!</w:p>).)*?</w:p>", re.S)
PARA_OPEN_RE = re.compile(r"<w:p\b[^>]*>")
RUN_RE = re.compile(r"<w:r\b[^>]*>.*?</w:r>", re.S)
STYLE_RE = re.compile(
    r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>.*?</w:style>', re.S
)
TABLE_RE = re.compile(r"<w:tbl\b[^>]*>.*?</w:tbl>", re.S)
TBL_PR_RE = re.compile(r"<w:tblPr\b[^>]*>.*?</w:tblPr>", re.S)
TBL_BORDERS_RE = re.compile(r"<w:tblBorders\b[^>]*>.*?</w:tblBorders>", re.S)
TBL_CELL_MAR_RE = re.compile(r"<w:tblCellMar\b[^>]*>.*?</w:tblCellMar>", re.S)


def _attrs(tag):
    return dict(re.findall(r'([\w:]+)="([^"]*)"', tag))


def _active_bold(xml):
    """True bila XML memuat bold aktif (bukan ``w:val="0"``)."""
    for match in re.finditer(r"<w:(?:b|bCs)\b[^>]*/>", xml):
        value = _attrs(match.group(0)).get("w:val", "true").lower()
        if value not in ("0", "false", "off"):
            return True
    return False


def _style_xml(styles, style_id):
    for match in STYLE_RE.finditer(styles):
        if match.group(1) == style_id:
            return match.group(0)
    return None


def _style_value(style_xml, tag):
    match = re.search(rf'<w:{tag}\b[^>]*w:val="([^"]*)"', style_xml)
    return match.group(1) if match else None


def _heading_positions(doc):
    """Posisi awal tiap paragraf Heading1 beserta teksnya."""
    headings = []
    for match in PARA_RE.finditer(doc):
        paragraph = match.group(0)
        if re.search(r'<w:pStyle w:val="Heading1"', paragraph):
            text = " ".join(
                re.findall(r"<w:t[^>]*>([^<]*)</w:t>", paragraph)
            ).strip()
            headings.append((match.start(), text))
    return headings


def _heading_start(doc, prefix):
    prefix = prefix.upper()
    for start, text in _heading_positions(doc):
        upper = text.upper()
        if upper == prefix or upper.startswith(prefix + " "):
            return start
    return None


def _parse_sections(doc):
    """Pecah dokumen menjadi seksi berdasarkan `w:sectPr`.

    OOXML menaruh `w:sectPr` di akhir seksi. Rentang `start`/`end` di sini
    adalah rentang konten seksi, bukan rentang tag `sectPr`.
    """
    sections = []
    current_start = 0
    for match in SECT_RE.finditer(doc):
        p_start = None
        for open_match in PARA_OPEN_RE.finditer(doc, 0, match.start()):
            p_start = open_match.start()
        p_end = None
        wrapped = False
        if p_start is not None:
            prefix = doc[p_start:match.start()]
            after = doc[match.end():match.end() + 80]
            wrapped = bool(
                re.search(r"<w:pPr(?:\s[^>]*)?>\s*$", prefix)
            ) and after.lstrip().startswith("</w:pPr>")
            if wrapped:
                paragraph = PARA_RE.match(doc, p_start)
                if paragraph:
                    p_end = paragraph.end()

        if wrapped and p_end is not None:
            # Paragraf pemuat sectPr termasuk seksi yang diakhirinya.
            end = p_end
            next_start = p_end
        else:
            end = match.start()
            next_start = match.end()

        sections.append(
            {
                "start": current_start,
                "end": end,
                "sect_start": match.start(),
                "sect_end": match.end(),
                "xml": match.group(0),
            }
        )
        current_start = next_start
    return sections


def _section_index_at(sections, pos):
    for index, section in enumerate(sections):
        if section["start"] <= pos < section["end"]:
            return index
    return None


def _pgnum(section):
    match = re.search(r"<w:pgNumType\b[^>]*/>", section["xml"])
    return _attrs(match.group(0)) if match else None


def _references(section, kind):
    refs = []
    pattern = rf"<w:{kind}Reference\b[^>]*/>"
    for match in re.finditer(pattern, section["xml"]):
        attrs = _attrs(match.group(0))
        refs.append((attrs.get("w:type", "default"), attrs.get("r:id", "")))
    return refs


def _ref_by_type(section, kind, ref_type):
    for current_type, rid in _references(section, kind):
        if current_type == ref_type:
            return rid
    return None


def _has_page_field(xml):
    return bool(
        re.search(r'<w:fldChar w:fldCharType="begin"', xml)
        and re.search(r'<w:fldChar w:fldCharType="separate"', xml)
        and re.search(r'<w:fldChar w:fldCharType="end"', xml)
        and re.search(r"<w:instrText[^>]*>\s*PAGE\s*</w:instrText>", xml)
    )


def _has_titlepg(section):
    return bool(re.search(r"<w:titlePg\b", section["xml"]))


def _part_text(xml):
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)).strip()


def _table_info(table_xml):
    """Ringkasan properti satu tabel untuk pemeriksaan border/padding."""
    rows = len(re.findall(r"<w:tr\b", table_xml))
    cells = len(re.findall(r"<w:tc\b", table_xml))
    info = {
        "rows": rows,
        "cells": cells,
        "borders": {},
        "margins": {},
        "cell_margins": [],
        "code": rows == 1
        and cells == 1
        and bool(re.search(r'<w:pStyle w:val="SourceCode"', table_xml)),
        "cell_borders": bool(re.search(r"<w:tcBorders\b", table_xml)),
        "header_bottom": bool(
            re.search(r'<w:bottom\b[^>]*w:sz="4"', table_xml)
        ),
    }

    tbl_pr = TBL_PR_RE.search(table_xml)
    if tbl_pr is None:
        return info
    tbl_pr_xml = tbl_pr.group(0)

    borders = TBL_BORDERS_RE.search(tbl_pr_xml)
    if borders is not None:
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            match = re.search(rf"<w:{side}\b[^>]*/>", borders.group(0))
            info["borders"][side] = _attrs(match.group(0)) if match else None

    margins = TBL_CELL_MAR_RE.search(tbl_pr_xml)
    if margins is not None:
        for side in ("top", "left", "bottom", "right"):
            match = re.search(rf"<w:{side}\b[^>]*/>", margins.group(0))
            info["margins"][side] = _attrs(match.group(0)) if match else None

    for cell_margin in re.finditer(
        r"<w:tcMar\b[^>]*>.*?</w:tcMar>", table_xml, re.S
    ):
        margin = {}
        for side in ("top", "left", "bottom", "right"):
            match = re.search(
                rf"<w:{side}\b[^>]*/>", cell_margin.group(0)
            )
            if match:
                margin[side] = _attrs(match.group(0))
        if margin:
            info["cell_margins"].append(margin)
    return info


def _table_margin(table, side):
    """Nilai padding efektif: tabel-level, lalu sel, lalu default 108."""
    margin = table["margins"].get(side)
    if margin is not None:
        return margin.get("w:w")
    for cell_margin in table["cell_margins"]:
        if side in cell_margin:
            return cell_margin[side].get("w:w")
    # Word menghilangkan margin 108 yang sama dengan default TableNormal.
    return "108"


def _page_field_run_sizes(xml):
    """Ukuran (half-point) semua run yang membentuk field PAGE.

    `w:sz 20` = 10 pt, `w:sz 24` = 12 pt.
    """
    sizes = set()
    for run in RUN_RE.findall(xml):
        if not re.search(r"<w:fldChar\b|<w:instrText\b|<w:t\b", run):
            continue
        for value in re.findall(r'<w:sz w:val="(\d+)"/>', run):
            sizes.add(int(value))
    return sizes


def _is_hidden_page_field(xml):
    """True bila field PAGE ada tetapi seluruh run-nya disembunyikan."""
    if not _has_page_field(xml):
        return False
    runs = [
        run
        for run in RUN_RE.findall(xml)
        if "PAGE" in run or "fldChar" in run or "<w:t" in run
    ]
    return bool(runs) and all(
        "<w:vanish/>" in run and '<w:color w:val="FFFFFF"/>' in run
        for run in runs
    )


class PageNumberTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DOCX_PATH.is_file():
            raise unittest.SkipTest(f"DOCX tidak ditemukan: {DOCX_PATH}")
        cls.zip = zipfile.ZipFile(DOCX_PATH)
        cls.document = cls.zip.read("word/document.xml").decode("utf-8")
        cls.styles = cls.zip.read("word/styles.xml").decode("utf-8")
        cls.settings = cls.zip.read("word/settings.xml").decode("utf-8")
        cls.rels = cls.zip.read("word/_rels/document.xml.rels").decode("utf-8")
        cls.sections = _parse_sections(cls.document)
        cls.targets = {}
        for match in re.finditer(r"<Relationship\b[^>]*/>", cls.rels):
            attrs = _attrs(match.group(0))
            target = attrs.get("Target", "")
            if attrs.get("TargetMode") == "External":
                continue
            if target.startswith("/"):
                part = target.lstrip("/")
            else:
                part = "word/" + target
            cls.targets[attrs.get("Id", "")] = part

    @classmethod
    def tearDownClass(cls):
        cls.zip.close()

    def part_for_ref(self, rid):
        part = self.targets.get(rid)
        self.assertIsNotNone(part, f"relasi {rid} tidak ditemukan")
        self.assertIn(part, self.zip.namelist(), f"part {part} tidak ada")
        return self.zip.read(part).decode("utf-8")

    def front_section_index(self):
        for name in ("KATA PENGANTAR", "DAFTAR ISI", "ABSTRAK", "ABSTRACT"):
            pos = _heading_start(self.document, name)
            if pos is not None:
                index = _section_index_at(self.sections, pos)
                if index is not None:
                    return index
        self.fail("heading front matter tidak ditemukan")

    def body_section_indexes(self):
        pos = _heading_start(self.document, "BAB I")
        if pos is None:
            headings = _heading_positions(self.document)
            self.assertTrue(headings, "tidak ada Heading1")
            pos = headings[-1][0]
        index = _section_index_at(self.sections, pos)
        self.assertIsNotNone(index, "section body tidak ditemukan")
        return list(range(index, len(self.sections)))

    def test_minimal_tiga_section(self):
        self.assertGreaterEqual(
            len(self.sections), 3,
            "dokumen harus memiliki minimal 3 section (sampul/front/body)",
        )

    def test_sampul_tanpa_nomor_halaman(self):
        cover = self.sections[0]
        self.assertIsNone(_pgnum(cover), "sampul tidak boleh punya pgNumType")
        self.assertEqual(_references(cover, "footer"), [], "sampul tidak boleh punya footer")
        self.assertEqual(_references(cover, "header"), [], "sampul tidak boleh punya header")

    def test_front_matter_lower_roman_mulai_1(self):
        section = self.sections[self.front_section_index()]
        pgnum = _pgnum(section)
        self.assertIsNotNone(pgnum, "front matter tidak punya pgNumType")
        self.assertEqual(pgnum.get("w:fmt"), "lowerRoman")
        self.assertEqual(pgnum.get("w:start"), "1")

    def test_front_matter_tanpa_header_dan_footer_12pt(self):
        section = self.sections[self.front_section_index()]
        self.assertEqual(
            _references(section, "header"), [],
            "front matter tidak boleh mereferensikan header",
        )
        rid = _ref_by_type(section, "footer", "default")
        self.assertIsNotNone(rid, "front matter tidak mereferensikan footer default")
        footer = self.part_for_ref(rid)
        self.assertTrue(_has_page_field(footer), "footer front matter tidak punya field PAGE")
        self.assertIn('<w:jc w:val="center"/>', footer)
        self.assertEqual(
            _page_field_run_sizes(footer), {24},
            "nomor front matter harus 12 pt (w:sz 24)",
        )

    def test_body_decimal_mulai_1(self):
        section = self.sections[self.body_section_indexes()[0]]
        pgnum = _pgnum(section)
        self.assertIsNotNone(pgnum, "body tidak punya pgNumType")
        self.assertEqual(pgnum.get("w:fmt"), "decimal")
        self.assertEqual(pgnum.get("w:start"), "1")

    def test_body_section_decimal_lanjut(self):
        for index in self.body_section_indexes()[1:]:
            pgnum = _pgnum(self.sections[index])
            if pgnum is None:
                # Section tanpa pgNumType mewarisi desimal section sebelumnya.
                continue
            self.assertEqual(
                pgnum.get("w:fmt"), "decimal",
                f"section body {index} harus memakai format decimal",
            )
            self.assertNotIn(
                "w:start", pgnum,
                f"section body {index} tidak boleh mereset nomor halaman",
            )

    def test_section_body_pakai_titlepg(self):
        for index in self.body_section_indexes():
            self.assertTrue(
                _has_titlepg(self.sections[index]),
                f"section body {index} harus memakai w:titlePg",
            )

    def test_header_body_10pt_kanan(self):
        for index in self.body_section_indexes():
            section = self.sections[index]
            rid = _ref_by_type(section, "header", "default")
            self.assertIsNotNone(
                rid, f"section body {index} tidak mereferensikan header default"
            )
            header = self.part_for_ref(rid)
            self.assertTrue(
                _has_page_field(header),
                f"header section body {index} tidak punya field PAGE",
            )
            self.assertIn('<w:jc w:val="right"/>', header)
            self.assertEqual(
                _page_field_run_sizes(header), {20},
                "nomor header body harus 10 pt (w:sz 20)",
            )

    def test_header_halaman_pertama_bab_kosong(self):
        for index in self.body_section_indexes():
            section = self.sections[index]
            rid = _ref_by_type(section, "header", "first")
            self.assertIsNotNone(
                rid,
                f"section body {index} harus punya header first-page eksplisit",
            )
            header = self.part_for_ref(rid)
            self.assertFalse(
                _has_page_field(header),
                f"header halaman pertama section body {index} tidak boleh punya PAGE",
            )
            self.assertEqual(
                _part_text(header), "",
                f"header halaman pertama section body {index} harus kosong",
            )

    def test_footer_halaman_pertama_bab_12pt_tengah(self):
        for index in self.body_section_indexes():
            section = self.sections[index]
            rid = _ref_by_type(section, "footer", "first")
            self.assertIsNotNone(
                rid,
                f"section body {index} harus punya footer first-page eksplisit",
            )
            footer = self.part_for_ref(rid)
            self.assertTrue(
                _has_page_field(footer),
                f"footer halaman pertama section body {index} tidak punya PAGE",
            )
            self.assertIn('<w:jc w:val="center"/>', footer)
            self.assertEqual(
                _page_field_run_sizes(footer), {24},
                "nomor halaman pertama bab harus 12 pt (w:sz 24)",
            )

    def test_footer_body_biasa_kosong_atau_probe_tersembunyi(self):
        for index in self.body_section_indexes():
            section = self.sections[index]
            rid = _ref_by_type(section, "footer", "default")
            self.assertIsNotNone(
                rid, f"section body {index} tidak mereferensikan footer default"
            )
            footer = self.part_for_ref(rid)
            if _has_page_field(footer):
                self.assertTrue(
                    _is_hidden_page_field(footer),
                    f"footer default section body {index} harus kosong; "
                    "field PAGE hanya boleh ada sebagai probe tersembunyi",
                )
                self.assertEqual(_page_field_run_sizes(footer), {24})
            else:
                self.assertEqual(
                    _part_text(footer), "",
                    f"footer default section body {index} harus kosong",
                )

    def test_tidak_ada_footer_part_dipakai_bersama_tanpa_titlepg(self):
        users = {}
        for index, section in enumerate(self.sections):
            for _kind, rid in _references(section, "footer"):
                users.setdefault(rid, []).append(index)
        for rid, indexes in users.items():
            if len(indexes) > 1:
                without_title = [
                    i for i in indexes if not _has_titlepg(self.sections[i])
                ]
                self.assertFalse(
                    len(without_title) > 1,
                    f"footer {rid} dipakai bersama oleh section {indexes} "
                    "tanpa titlePg",
                )

    def test_toc_dan_pageref_tetap_utuh(self):
        self.assertIn('TOC \\o "1-3"', self.document)
        self.assertGreaterEqual(
            len(re.findall(r"PAGEREF\s+\S+", self.document)), 1,
            "field PAGEREF daftar isi hilang",
        )
        # Field TOC dan PAGEREF harus tetap berupa field OpenXML asli.
        self.assertIn('w:fldCharType="begin"', self.document)
        self.assertIn('w:fldCharType="end"', self.document)

    def test_settings_tanpa_update_fields_dan_compat_15(self):
        self.assertNotIn(
            "updateFields", self.settings,
            "w:updateFields memicu prompt update field saat DOCX dibuka",
        )
        modes = [
            tag
            for tag in re.findall(r"<w:compatSetting\b[^>]*/>", self.settings)
            if 'w:name="compatibilityMode"' in tag
        ]
        self.assertEqual(
            len(modes), 1,
            "settings.xml harus punya tepat satu compatibilityMode",
        )
        self.assertRegex(modes[0], r'w:val="15"')
        self.assertIn(
            "<w:compat>", self.settings,
            "w:compat wajib ada agar Word tidak membuka Compatibility Mode",
        )

    def test_hyperlink_style_hitam_tanpa_underline(self):
        style = _style_xml(self.styles, "Hyperlink")
        self.assertIsNotNone(style, "style Hyperlink tidak ditemukan")
        self.assertEqual(_style_value(style, "color"), "000000")
        self.assertEqual(_style_value(style, "u"), "none")
        self.assertNotIn("themeColor", style)

    def test_heading1_2_3_spacing_nol(self):
        for style_id in ("Heading1", "Heading2", "Heading3"):
            style = _style_xml(self.styles, style_id)
            self.assertIsNotNone(style, f"style {style_id} tidak ditemukan")
            spacing = re.search(r"<w:spacing\b[^>]*/>", style)
            self.assertIsNotNone(spacing)
            before = re.search(r'w:before="(\d+)"', spacing.group(0))
            after = re.search(r'w:after="(\d+)"', spacing.group(0))
            self.assertIsNotNone(before, f"{style_id} tidak punya w:before")
            self.assertIsNotNone(after, f"{style_id} tidak punya w:after")
            self.assertEqual(
                int(before.group(1)), 0,
                f"{style_id} before harus 0; jarak memakai paragraf kosong",
            )
            self.assertEqual(
                int(after.group(1)), 0,
                f"{style_id} after harus 0; jarak memakai paragraf kosong",
            )
            self.assertIn('w:line="360"', spacing.group(0))

        heading1 = _style_xml(self.styles, "Heading1")
        self.assertEqual(_style_value(heading1, "jc"), "center")

    def test_toc_spacing_nol_dan_tanpa_bold(self):
        for style_id in ("TOC1", "TOC2"):
            style = _style_xml(self.styles, style_id)
            self.assertIsNotNone(style, f"style {style_id} tidak ditemukan")
            spacing = re.search(r"<w:spacing\b[^>]*/>", style)
            self.assertIsNotNone(spacing)
            spacing_attrs = _attrs(spacing.group(0))
            self.assertEqual(
                int(spacing_attrs.get("w:before", "0")), 0,
                f"{style_id} before harus 0",
            )
            self.assertEqual(
                int(spacing_attrs.get("w:after", "0")), 0,
                f"{style_id} after harus 0",
            )

        toc1 = _style_xml(self.styles, "TOC1")
        self.assertFalse(
            _active_bold(toc1), "style TOC1 tidak boleh bold",
        )
        toc_heading = _style_xml(self.styles, "TOCHeading")
        self.assertTrue(
            _active_bold(toc_heading), "TOCHeading (judul) tetap bold",
        )

        entries = [
            paragraph
            for paragraph in PARA_RE.findall(self.document)
            if re.search(r'<w:pStyle w:val="TOC[1-9]"/>', paragraph)
        ]
        self.assertTrue(entries, "tidak ada paragraf entri TOC")
        for entry in entries:
            spacing = re.search(r"<w:spacing\b[^>]*/>", entry)
            if spacing is not None:
                spacing_attrs = _attrs(spacing.group(0))
                self.assertEqual(
                    int(spacing_attrs.get("w:before", "0")), 0,
                    "spacing before entri TOC harus 0",
                )
                self.assertEqual(
                    int(spacing_attrs.get("w:after", "0")), 0,
                    "spacing after entri TOC harus 0",
                )
            for run in RUN_RE.findall(entry):
                self.assertFalse(
                    _active_bold(run),
                    "run entri TOC tidak boleh bold",
                )

    def test_caption_10pt_dan_tablecaption_kiri(self):
        image_caption = _style_xml(self.styles, "ImageCaption")
        table_caption = _style_xml(self.styles, "TableCaption")
        self.assertIsNotNone(image_caption, "style ImageCaption tidak ditemukan")
        self.assertIsNotNone(table_caption, "style TableCaption tidak ditemukan")

        for style_id, style in (
            ("ImageCaption", image_caption),
            ("TableCaption", table_caption),
        ):
            self.assertEqual(
                _style_value(style, "sz"), "20",
                f"{style_id} harus 10 pt (w:sz 20)",
            )
            spacing = re.search(r"<w:spacing\b[^>]*/>", style)
            self.assertIsNotNone(spacing)
            spacing_attrs = _attrs(spacing.group(0))
            self.assertEqual(
                int(spacing_attrs.get("w:before", "0")), 0,
                f"{style_id} before harus 0",
            )
            self.assertEqual(
                int(spacing_attrs.get("w:after", "0")), 0,
                f"{style_id} after harus 0",
            )
            self.assertEqual(spacing_attrs.get("w:line"), "240")

        self.assertEqual(_style_value(image_caption, "jc"), "center")
        self.assertEqual(_style_value(table_caption, "jc"), "left")
        self.assertIn("<w:keepNext", table_caption)

    def test_tabel_data_dan_kode_border_ilmiah(self):
        tables = [
            _table_info(match.group(0))
            for match in TABLE_RE.finditer(self.document)
        ]
        self.assertTrue(tables, "Laporan.docx tidak memiliki tabel")
        code_tables = [table for table in tables if table["code"]]
        data_tables = [table for table in tables if not table["code"]]

        self.assertTrue(data_tables, "tidak ada tabel data di Laporan.docx")
        self.assertGreaterEqual(
            len(code_tables), 5,
            "Laporan.docx harus memuat minimal 5 tabel kode 1x1",
        )

        for table in tables:
            borders = table["borders"]
            for side in ("top", "bottom"):
                self.assertIsNotNone(
                    borders.get(side), f"border {side} tabel tidak ada"
                )
                self.assertEqual(borders[side].get("w:val"), "single")
                self.assertEqual(
                    borders[side].get("w:sz"), "8",
                    f"border {side} harus 1 pt (w:sz 8)",
                )
                self.assertEqual(borders[side].get("w:color"), "000000")
            for side in ("left", "right", "insideH", "insideV"):
                self.assertIsNotNone(
                    borders.get(side), f"border {side} tabel tidak ada"
                )
                self.assertEqual(
                    borders[side].get("w:val"), "nil",
                    f"tabel ilmiah tidak boleh punya garis {side}",
                )
            for side in ("left", "right"):
                self.assertEqual(
                    _table_margin(table, side), "108",
                    f"padding horizontal {side} harus 108 twip",
                )

        for table in data_tables:
            for side in ("top", "bottom"):
                self.assertEqual(
                    _table_margin(table, side), "0",
                    f"padding vertikal tabel data {side} harus 0",
                )
            self.assertTrue(
                table["header_bottom"],
                "baris header tabel data harus punya garis bawah 0,5 pt",
            )

        for table in code_tables:
            self.assertEqual(table["rows"], 1, "tabel kode harus 1 baris")
            self.assertEqual(table["cells"], 1, "tabel kode harus 1 kolom")
            self.assertFalse(
                table["cell_borders"],
                "tabel kode tidak boleh memakai border sel langsung",
            )
            for side in ("top", "left", "bottom", "right"):
                self.assertEqual(
                    _table_margin(table, side), "108",
                    f"padding {side} tabel kode harus 108 twip",
                )

    def test_style_kode_courier_new_10pt_hitam_tanpa_shading(self):
        for style_id in (
            "SourceCode", "VerbatimChar", "HTMLCode", "HTMLPreformatted"
        ):
            style = _style_xml(self.styles, style_id)
            self.assertIsNotNone(style, f"style {style_id} tidak ditemukan")
            rfonts = re.search(r"<w:rFonts\b[^>]*/>", style)
            self.assertIsNotNone(rfonts)
            for attr in ("ascii", "hAnsi", "cs"):
                self.assertEqual(
                    re.search(rf'w:{attr}="([^"]*)"', rfonts.group(0)).group(1),
                    "Courier New",
                )
            self.assertEqual(_style_value(style, "sz"), "20")
            self.assertEqual(_style_value(style, "color"), "000000")
            self.assertNotIn("<w:shd", style)

    def test_tidak_ada_direct_font_monospace_lama(self):
        for xml in (self.styles, self.document):
            self.assertNotRegex(
                xml,
                r'w:(?:ascii|hAnsi|cs|eastAsia)="(?:Consolas|DejaVu Sans Mono)"',
                "font monospace lama masih dipakai sebagai formatting",
            )


if __name__ == "__main__":
    unittest.main()
