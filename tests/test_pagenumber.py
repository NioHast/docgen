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

ROOT = Path(__file__).resolve().parents[1]
DOCX_PATH = Path(os.environ.get("LAPORAN_DOCX", ROOT / "Laporan.docx"))

SECT_RE = re.compile(r"<w:sectPr\b[^>]*>.*?</w:sectPr>", re.S)
PARA_RE = re.compile(r"<w:p\b[^>]*>(?:(?!</w:p>).)*?</w:p>", re.S)
PARA_OPEN_RE = re.compile(r"<w:p\b[^>]*>")
RUN_RE = re.compile(r"<w:r\b[^>]*>.*?</w:r>", re.S)


def _attrs(tag):
    return dict(re.findall(r'([\w:]+)="([^"]*)"', tag))


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


if __name__ == "__main__":
    unittest.main()
