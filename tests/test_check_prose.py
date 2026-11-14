"""Tes pemeriksa prosa terintegrasi: registry, self-lint, dan AI-20.

Jalankan: .venv/Scripts/python.exe -m pytest tests/test_check_prose.py -q
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.dev import check_prose

ROOT = Path(__file__).resolve().parents[1]


def findings(text, code):
    return [x for x in check_prose.periksa(text) if x[1] == code]


class TestRegistry(unittest.TestCase):
    def test_old_codes_remain_and_ai20_is_new(self):
        old_codes = (
            {f"KE-{i:02d}" for i in range(1, 18)}
            | {"NM-01", "KK-01"}
            | {f"SG-{i:02d}" for i in range(1, 7)}
            | {f"EJ-{i:02d}" for i in range(1, 12)}
            | {f"AI-{i:02d}" for i in range(1, 20)}
            | {"KB-01", "KL-01", "IS-01"}
        )
        self.assertEqual(len(old_codes), 58)
        self.assertEqual(set(check_prose._PETA), old_codes | {"AI-20"})

    def test_rule_types_unchanged(self):
        count = {}
        for rule in check_prose.ATURAN:
            count[rule["jenis"]] = count.get(rule["jenis"], 0) + 1
        self.assertEqual(
            count, {"regex": 52, "regex_mentah": 1, "dinamis": 4, "kamus": 1, "akronim": 1}
        )

    def test_dictionary_and_acronyms(self):
        self.assertEqual(len(check_prose.KATA_BAKU), 129)
        self.assertEqual(len(check_prose.AKRONIM), 32)

    def test_checker_does_not_copy_regex(self):
        source = Path(check_prose.__file__).read_text(encoding="utf-8")
        for rule in check_prose.ATURAN:
            if rule["jenis"] in ("regex", "regex_mentah") and len(rule["pola"]) >= 4:
                self.assertNotIn(rule["pola"], source, rule["kode"])

    def test_ai20_minimum_two_and_has_stoplist(self):
        rule = check_prose._PETA["AI-20"]
        self.assertEqual(rule["min"], 2)
        self.assertIn("Langkah", rule["henti_label"])
        self.assertIn("adalah", rule["henti_awal"])


class TestAI20(unittest.TestCase):
    def test_two_labeled_items_reported(self):
        text = "- **Kecepatan Tinggi**: Sistem cepat.\n- **Ukuran Kecil**: Berkas kecil."
        result = findings(text, "AI-20")
        self.assertEqual([x[0] for x in result], [1, 2])
        self.assertEqual([x[3] for x in result], ["Kecepatan Tinggi", "Ukuran Kecil"])
        self.assertEqual({x[2] for x in result}, {"AI"})

    def test_one_item_not_enough(self):
        self.assertEqual(findings("- **Kecepatan Tinggi**: Sistem cepat.", "AI-20"), [])

    def test_procedure_and_definition_labels_excluded(self):
        text = (
            "- **Langkah 1**: Jalankan build.\n"
            "- **Seksi Sampul**: Bagian awal.\n"
            "- **Sensor**: adalah alat ukur.\n"
            "- **Aktuator**: merupakan penggerak."
        )
        self.assertEqual(findings(text, "AI-20"), [])

    def test_table_paragraph_and_file_paths_excluded(self):
        text = (
            "| **Kecepatan Tinggi** | Sistem cepat |\n"
            "| **Ukuran Kecil** | Berkas kecil |\n\n"
            "Kecepatan Tinggi: sistem ini cepat.\n"
            "Ukuran Kecil: berkas ini kecil.\n\n"
            "- **scripts/scan-preset.py**: Alat pemindai.\n"
            "- **scripts/validate-preset.py**: Alat validasi."
        )
        self.assertEqual(findings(text, "AI-20"), [])

    def test_before_marker_and_ignore(self):
        text = (
            "**Sebelum:** - **Kecepatan Tinggi**: Sistem cepat.\n"
            "**Sebelum:** - **Ukuran Kecil**: Berkas kecil.\n"
            "<!-- periksa:abaikan -->\n"
            "- **Kecepatan Tinggi**: Sistem cepat.\n"
            "- **Ukuran Kecil**: Berkas kecil.\n"
            "<!-- periksa:lanjut -->"
        )
        self.assertEqual(findings(text, "AI-20"), [])

    def test_ignore_ai20_code(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "butir.md"
            path.write_text(
                "- **Kecepatan Tinggi**: Sistem cepat.\n- **Ukuran Kecil**: Berkas kecil.\n",
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = check_prose.main(["--abaikan", "AI-20", str(path)])
        self.assertEqual(code, 0)
        self.assertNotIn("AI-20", buf.getvalue())


class TestKE13(unittest.TestCase):
    def test_not_only_still_accepted(self):
        self.assertEqual(findings("Bukan hanya murah, tetapi juga awet.", "KE-13"), [])

    def test_not_but_reported(self):
        result = findings("Ini bukan galat acak, tetapi galat sistematis.", "KE-13")
        self.assertEqual(len(result), 1)

    def test_not_but_colloquial_reported(self):
        for text in ("Bukan kualitas, tapi harga.", "Bukan kualitas, TAPI harga."):
            with self.subTest(text=text):
                result = findings(text, "KE-13")
                self.assertEqual(len(result), 1)

    def test_not_but_rather_still_accepted(self):
        self.assertEqual(findings("Ini bukan solusi murah, melainkan solusi cepat.", "KE-13"), [])


class TestSelfLint(unittest.TestCase):
    def test_guide_and_docs_clean(self):
        for name in ("docs/user/writing-rules.md", "docs/dev/contributing.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertEqual(check_prose.periksa(text), [], name)

    def test_self_test_still_109(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_prose.main(["--self-test"])
        output = buf.getvalue()
        self.assertEqual(code, 0, output)
        self.assertIn("109/109 kasus lulus", output)


if __name__ == "__main__":
    unittest.main()
