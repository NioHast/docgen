"""Tes pemeriksa prosa terintegrasi: registry, self-lint, dan AI-20.

Jalankan: .venv/Scripts/python.exe -m pytest tests/test_check_prose.py -q
"""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

AKAR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR / "tools" / "dev"))

import check_prose  # noqa: E402


def temuan(teks, kode):
    return [x for x in check_prose.periksa(teks) if x[1] == kode]


class TesRegistry(unittest.TestCase):
    def test_kode_lama_tetap_ada_dan_ai20_baru(self):
        lama = (
            {f"KE-{i:02d}" for i in range(1, 18)}
            | {"NM-01", "KK-01"}
            | {f"SG-{i:02d}" for i in range(1, 7)}
            | {f"EJ-{i:02d}" for i in range(1, 12)}
            | {f"AI-{i:02d}" for i in range(1, 20)}
            | {"KB-01", "KL-01", "IS-01"}
        )
        self.assertEqual(len(lama), 58)
        self.assertEqual(set(check_prose._PETA), lama | {"AI-20"})

    def test_jenis_aturan_tidak_berubah(self):
        jumlah = {}
        for aturan in check_prose.ATURAN:
            jumlah[aturan["jenis"]] = jumlah.get(aturan["jenis"], 0) + 1
        self.assertEqual(
            jumlah, {"regex": 52, "regex_mentah": 1, "dinamis": 4, "kamus": 1, "akronim": 1}
        )

    def test_kamus_dan_akronim(self):
        self.assertEqual(len(check_prose.KATA_BAKU), 129)
        self.assertEqual(len(check_prose.AKRONIM), 32)

    def test_checker_tidak_menyalin_regex(self):
        sumber = Path(check_prose.__file__).read_text(encoding="utf-8")
        for aturan in check_prose.ATURAN:
            if aturan["jenis"] in ("regex", "regex_mentah") and len(aturan["pola"]) >= 4:
                self.assertNotIn(aturan["pola"], sumber, aturan["kode"])

    def test_ai20_minimal_dua_dan_punya_stoplist(self):
        aturan = check_prose._PETA["AI-20"]
        self.assertEqual(aturan["min"], 2)
        self.assertIn("Langkah", aturan["henti_label"])
        self.assertIn("adalah", aturan["henti_awal"])


class TesAI20(unittest.TestCase):
    def test_dua_butir_berlabel_dilaporkan(self):
        teks = "- **Kecepatan Tinggi**: Sistem cepat.\n- **Ukuran Kecil**: Berkas kecil."
        hasil = temuan(teks, "AI-20")
        self.assertEqual([x[0] for x in hasil], [1, 2])
        self.assertEqual([x[3] for x in hasil], ["Kecepatan Tinggi", "Ukuran Kecil"])
        self.assertEqual({x[2] for x in hasil}, {"AI"})

    def test_satu_butir_tidak_cukup(self):
        self.assertEqual(temuan("- **Kecepatan Tinggi**: Sistem cepat.", "AI-20"), [])

    def test_label_prosedur_dan_definisi_dikecualikan(self):
        teks = (
            "- **Langkah 1**: Jalankan build.\n"
            "- **Seksi Sampul**: Bagian awal.\n"
            "- **Sensor**: adalah alat ukur.\n"
            "- **Aktuator**: merupakan penggerak."
        )
        self.assertEqual(temuan(teks, "AI-20"), [])

    def test_tabel_paragraf_dan_jalur_berkas_dikecualikan(self):
        teks = (
            "| **Kecepatan Tinggi** | Sistem cepat |\n"
            "| **Ukuran Kecil** | Berkas kecil |\n\n"
            "Kecepatan Tinggi: sistem ini cepat.\n"
            "Ukuran Kecil: berkas ini kecil.\n\n"
            "- **scripts/scan-preset.py**: Alat pemindai.\n"
            "- **scripts/validate-preset.py**: Alat validasi."
        )
        self.assertEqual(temuan(teks, "AI-20"), [])

    def test_penanda_sebelum_dan_abaikan(self):
        teks = (
            "**Sebelum:** - **Kecepatan Tinggi**: Sistem cepat.\n"
            "**Sebelum:** - **Ukuran Kecil**: Berkas kecil.\n"
            "<!-- periksa:abaikan -->\n"
            "- **Kecepatan Tinggi**: Sistem cepat.\n"
            "- **Ukuran Kecil**: Berkas kecil.\n"
            "<!-- periksa:lanjut -->"
        )
        self.assertEqual(temuan(teks, "AI-20"), [])

    def test_abaikan_kode_ai20(self):
        with tempfile.TemporaryDirectory() as d:
            jalur = Path(d) / "butir.md"
            jalur.write_text(
                "- **Kecepatan Tinggi**: Sistem cepat.\n- **Ukuran Kecil**: Berkas kecil.\n",
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                kode = check_prose.main(["--abaikan", "AI-20", str(jalur)])
        self.assertEqual(kode, 0)
        self.assertNotIn("AI-20", buf.getvalue())


class TesKE13(unittest.TestCase):
    def test_bukan_hanya_tetap_diterima(self):
        self.assertEqual(temuan("Bukan hanya murah, tetapi juga awet.", "KE-13"), [])

    def test_bukan_tetapi_dilaporkan(self):
        hasil = temuan("Ini bukan galat acak, tetapi galat sistematis.", "KE-13")
        self.assertEqual(len(hasil), 1)

    def test_bukan_tapi_dilaporkan(self):
        for teks in ("Bukan kualitas, tapi harga.", "Bukan kualitas, TAPI harga."):
            with self.subTest(teks=teks):
                hasil = temuan(teks, "KE-13")
                self.assertEqual(len(hasil), 1)

    def test_bukan_melainkan_tetap_diterima(self):
        self.assertEqual(temuan("Ini bukan solusi murah, melainkan solusi cepat.", "KE-13"), [])


class TesSelfLint(unittest.TestCase):
    def test_guide_dan_docs_bersih(self):
        for nama in ("docs/user/writing-rules.md", "docs/dev/contributing.md"):
            teks = (AKAR / nama).read_text(encoding="utf-8")
            self.assertEqual(check_prose.periksa(teks), [], nama)

    def test_self_test_tetap_109(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            kode = check_prose.main(["--self-test"])
        keluaran = buf.getvalue()
        self.assertEqual(kode, 0, keluaran)
        self.assertIn("109/109 kasus lulus", keluaran)


if __name__ == "__main__":
    unittest.main()
