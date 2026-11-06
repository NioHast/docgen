#!/usr/bin/env python3
"""Tes struktur penomoran halaman Laporan.docx.

Membaca DOCX hasil `build-docx.sh` (default: Laporan.docx di root repo,
bisa dioverride lewat environment variable LAPORAN_DOCX) dan memeriksa:

  - minimal tiga seksi (`w:sectPr`);
  - front matter memakai lowerRoman mulai 1;
  - body memakai decimal mulai 1;
  - sampul tidak bernomor;
  - field PAGE asli ada di footer front matter dan header body;
  - tidak ada dua seksi berbagi part footer tanpa `w:titlePg`;
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


def _section_at(sections, pos):
    for section in sections:
        if section["start"] <= pos < section["end"]:
            return section
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


def _has_page_field(xml):
    return bool(
        re.search(r'<w:fldChar w:fldCharType="begin"', xml)
        and re.search(r'<w:fldChar w:fldCharType="separate"', xml)
        and re.search(r'<w:fldChar w:fldCharType="end"', xml)
        and re.search(r"<w:instrText[^>]*>\s*PAGE\s*</w:instrText>", xml)
    )


def _has_titlepg(section):
    return bool(re.search(r"<w:titlePg\b", section["xml"]))


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
        pos = _heading_start(self.document, "KATA PENGANTAR")
        if pos is None:
            pos = _heading_start(self.document, "DAFTAR ISI")
        self.assertIsNotNone(pos, "heading front matter tidak ditemukan")
        section = _section_at(self.sections, pos)
        self.assertIsNotNone(section, "section front matter tidak ditemukan")
        pgnum = _pgnum(section)
        self.assertIsNotNone(pgnum, "front matter tidak punya pgNumType")
        self.assertEqual(pgnum.get("w:fmt"), "lowerRoman")
        self.assertEqual(pgnum.get("w:start"), "1")

    def test_body_decimal_mulai_1(self):
        pos = _heading_start(self.document, "BAB I")
        if pos is None:
            headings = _heading_positions(self.document)
            self.assertTrue(headings, "tidak ada Heading1")
            pos = headings[-1][0]
        section = _section_at(self.sections, pos)
        self.assertIsNotNone(section, "section body tidak ditemukan")
        pgnum = _pgnum(section)
        self.assertIsNotNone(pgnum, "body tidak punya pgNumType")
        self.assertEqual(pgnum.get("w:fmt"), "decimal")
        self.assertEqual(pgnum.get("w:start"), "1")

    def test_footer_front_matter_punya_field_page(self):
        pos = _heading_start(self.document, "KATA PENGANTAR")
        if pos is None:
            pos = _heading_start(self.document, "DAFTAR ISI")
        section = _section_at(self.sections, pos)
        self.assertIsNotNone(section)
        refs = _references(section, "footer")
        self.assertTrue(refs, "front matter tidak mereferensikan footer")
        footer = self.part_for_ref(refs[0][1])
        self.assertTrue(_has_page_field(footer), "footer front matter tidak punya field PAGE")
        self.assertIn('<w:jc w:val="center"/>', footer)

    def test_header_body_punya_field_page(self):
        pos = _heading_start(self.document, "BAB I")
        if pos is None:
            headings = _heading_positions(self.document)
            pos = headings[-1][0]
        section = _section_at(self.sections, pos)
        self.assertIsNotNone(section)
        refs = _references(section, "header")
        self.assertTrue(refs, "body tidak mereferensikan header")
        header = self.part_for_ref(refs[0][1])
        self.assertTrue(_has_page_field(header), "header body tidak punya field PAGE")
        self.assertIn('<w:jc w:val="right"/>', header)

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
            len(re.findall(r"PAGEREF\s+\S+", self.document)), 10,
            "entri PAGEREF daftar isi hilang/terlalu sedikit",
        )
        # Field TOC dan PAGEREF harus tetap berupa field OpenXML asli.
        self.assertIn('w:fldCharType="begin"', self.document)
        self.assertIn('w:fldCharType="end"', self.document)


if __name__ == "__main__":
    unittest.main()
