"""Tes regresi pembaca DOCX check_prose.py.

Jalankan: python -m unittest discover -s tests -v
"""

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from tools.dev import check_prose

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _paragraph(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def write_docx(path, paragraphs):
    """Buat DOCX minimal: paragraf = [teks atau (teks, gaya), ...]."""
    content = []
    for item in paragraphs:
        text, style = (item, None) if isinstance(item, str) else item
        content.append(_paragraph(text, style))
    xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{NS}"><w:body>{"".join(content)}</w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


class TestCheckProseDocx(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def check_docx(self, name, paragraphs):
        path = self.dir / name
        write_docx(path, paragraphs)
        return check_prose.periksa(check_prose.baca(path))

    def line_ids(self, findings):
        return [(x[0], x[1]) for x in findings]

    def test_docx_abstract_then_sentence_must_be_ke01(self):
        """Regresi: heading Abstract tidak boleh membuat sisa dokumen dilewati."""
        findings = self.check_docx(
            "abstract.docx",
            [
                ("Abstract", "Heading1"),
                ("Penelitian ini mengukur galat alat."),
                ("Pendahuluan", "Heading1"),
                ("Dari hasil pengujian menunjukkan bahwa galat turun.", None),
            ],
        )
        ke01 = [x for x in findings if x[1] == "KE-01"]
        self.assertEqual(len(ke01), 1, findings)
        self.assertEqual(ke01[0][0], 4)

    def test_docx_without_abstract_still_ke01(self):
        findings = self.check_docx(
            "tanpa-abstract.docx",
            [
                ("Pendahuluan", "Heading1"),
                ("Dari hasil pengujian menunjukkan bahwa galat turun.", None),
            ],
        )
        self.assertEqual(self.line_ids(findings), [(2, "KE-01")], findings)

    def test_markdown_heading_unchanged(self):
        text = "# Pendahuluan\n\nDari hasil pengujian menunjukkan bahwa galat turun.\n"
        self.assertEqual(self.line_ids(check_prose.periksa(text)), [(3, "KE-01")])

        text = (
            "# Abstract\n\nRingkasan.\n\n# Pendahuluan\n\n"
            "Dari hasil pengujian menunjukkan bahwa galat turun.\n"
        )
        self.assertEqual(self.line_ids(check_prose.periksa(text)), [(7, "KE-01")])

    def test_docx_heading_two_and_three_mapped(self):
        path = self.dir / "heading.docx"
        write_docx(
            path,
            [
                ("Satu", "Heading1"),
                ("Dua", "Heading2"),
                ("Tiga", "Heading3"),
                ("Paragraf biasa", None),
                ("Kutipan", "Quote"),
            ],
        )
        self.assertEqual(
            check_prose.baca(path), "# Satu\n## Dua\n### Tiga\nParagraf biasa\nKutipan"
        )

    def test_markdown_bibliography_skipped(self):
        text = (
            "# Hasil\n\nTeks bersih.\n\n# Daftar Pustaka\n\n"
            "Smith, J. (2020). Dari hasil pengujian menunjukkan bahwa analisa salah.\n"
        )
        self.assertEqual(check_prose.periksa(text), [])

    def test_docx_bibliography_skipped(self):
        findings = self.check_docx(
            "pustaka.docx",
            [
                ("Hasil", "Heading1"),
                ("Teks bersih."),
                ("Daftar Pustaka", "Heading1"),
                ("Smith, J. (2020). Dari hasil pengujian menunjukkan bahwa analisa salah."),
            ],
        )
        self.assertEqual(findings, [])

    def test_term_marker_produces_is01(self):
        findings = check_prose.periksa("Data ini {{?validation dataset?}} belum final.")
        is01 = [x for x in findings if x[1] == "IS-01"]
        self.assertEqual(len(is01), 1, findings)
        self.assertEqual(is01[0][2], "K")
        self.assertEqual(is01[0][3], "{{?validation dataset?}}")
        self.assertIn("putuskan lalu hapus penanda", is01[0][4])

    def test_em_dash_produces_ej11(self):
        findings = check_prose.periksa("Galat turun—akurasi naik.")
        ej11 = [x for x in findings if x[1] == "EJ-11"]
        self.assertEqual(len(ej11), 1, findings)
        self.assertEqual(ej11[0][2], "K")
        self.assertIn("em dash dilarang", ej11[0][4])


if __name__ == "__main__":
    unittest.main()
