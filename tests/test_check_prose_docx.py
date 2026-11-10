"""Tes regresi pembaca DOCX check_prose.py.

Jalankan: python -m unittest discover -s tests -v
"""

import io
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from xml.sax.saxutils import escape

AKAR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR / "tools" / "dev"))

import check_prose  # noqa: E402

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _paragraf(teks, gaya=None):
    ppr = f'<w:pPr><w:pStyle w:val="{gaya}"/></w:pPr>' if gaya else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(teks)}</w:t></w:r></w:p>'


def tulis_docx(jalur, paragraf):
    """Buat DOCX minimal: paragraf = [teks atau (teks, gaya), ...]."""
    isi = []
    for item in paragraf:
        teks, gaya = (item, None) if isinstance(item, str) else item
        isi.append(_paragraf(teks, gaya))
    xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{NS}"><w:body>{"".join(isi)}</w:body></w:document>'
    )
    with zipfile.ZipFile(jalur, "w") as z:
        z.writestr("word/document.xml", xml)


class TesCheckProseDocx(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def periksa_docx(self, nama, paragraf):
        jalur = self.dir / nama
        tulis_docx(jalur, paragraf)
        return check_prose.periksa(check_prose.baca(jalur))

    def id_baris(self, hasil):
        return [(x[0], x[1]) for x in hasil]

    def test_docx_abstract_lalu_kalimat_harus_ke01(self):
        """Regresi: heading Abstract tidak boleh membuat sisa dokumen dilewati."""
        hasil = self.periksa_docx(
            "abstract.docx",
            [
                ("Abstract", "Heading1"),
                ("Penelitian ini mengukur galat alat."),
                ("Pendahuluan", "Heading1"),
                ("Dari hasil pengujian menunjukkan bahwa galat turun.", None),
            ],
        )
        ke01 = [x for x in hasil if x[1] == "KE-01"]
        self.assertEqual(len(ke01), 1, hasil)
        self.assertEqual(ke01[0][0], 4)

    def test_docx_tanpa_abstract_tetap_ke01(self):
        hasil = self.periksa_docx(
            "tanpa-abstract.docx",
            [
                ("Pendahuluan", "Heading1"),
                ("Dari hasil pengujian menunjukkan bahwa galat turun.", None),
            ],
        )
        self.assertEqual(self.id_baris(hasil), [(2, "KE-01")], hasil)

    def test_markdown_heading_tidak_berubah(self):
        teks = "# Pendahuluan\n\nDari hasil pengujian menunjukkan bahwa galat turun.\n"
        self.assertEqual(self.id_baris(check_prose.periksa(teks)), [(3, "KE-01")])

        teks = (
            "# Abstract\n\nRingkasan.\n\n# Pendahuluan\n\n"
            "Dari hasil pengujian menunjukkan bahwa galat turun.\n"
        )
        self.assertEqual(self.id_baris(check_prose.periksa(teks)), [(7, "KE-01")])

    def test_docx_heading_dua_dan_tiga_dipetakan(self):
        jalur = self.dir / "heading.docx"
        tulis_docx(
            jalur,
            [
                ("Satu", "Heading1"),
                ("Dua", "Heading2"),
                ("Tiga", "Heading3"),
                ("Paragraf biasa", None),
                ("Kutipan", "Quote"),
            ],
        )
        self.assertEqual(
            check_prose.baca(jalur), "# Satu\n## Dua\n### Tiga\nParagraf biasa\nKutipan"
        )

    def test_daftar_pustaka_markdown_dilewati(self):
        teks = (
            "# Hasil\n\nTeks bersih.\n\n# Daftar Pustaka\n\n"
            "Smith, J. (2020). Dari hasil pengujian menunjukkan bahwa analisa salah.\n"
        )
        self.assertEqual(check_prose.periksa(teks), [])

    def test_daftar_pustaka_docx_dilewati(self):
        hasil = self.periksa_docx(
            "pustaka.docx",
            [
                ("Hasil", "Heading1"),
                ("Teks bersih."),
                ("Daftar Pustaka", "Heading1"),
                ("Smith, J. (2020). Dari hasil pengujian menunjukkan bahwa analisa salah."),
            ],
        )
        self.assertEqual(hasil, [])

    def test_penanda_istilah_menghasilkan_is01(self):
        hasil = check_prose.periksa("Data ini {{?validation dataset?}} belum final.")
        is01 = [x for x in hasil if x[1] == "IS-01"]
        self.assertEqual(len(is01), 1, hasil)
        self.assertEqual(is01[0][2], "K")
        self.assertEqual(is01[0][3], "{{?validation dataset?}}")
        self.assertIn("putuskan lalu hapus penanda", is01[0][4])

    def test_em_dash_menghasilkan_ej11(self):
        hasil = check_prose.periksa("Galat turun—akurasi naik.")
        ej11 = [x for x in hasil if x[1] == "EJ-11"]
        self.assertEqual(len(ej11), 1, hasil)
        self.assertEqual(ej11[0][2], "K")
        self.assertIn("em dash dilarang", ej11[0][4])

    def test_tes_bawaan_tetap_109(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            kode = check_prose.main(["--tes"])
        keluaran = buf.getvalue()
        self.assertEqual(kode, 0, keluaran)
        self.assertIn("109/109 kasus lulus", keluaran)


if __name__ == "__main__":
    unittest.main()
