"""Tes checker kualitas test statis di tools/dev/check_tests.py."""

import json
from pathlib import Path
from typing import Any

import check_tests


def tulis(akar: Path, nama: str, teks: str) -> Path:
    """Tulis berkas sintetis di bawah direktori sementara."""
    jalur = akar / nama
    jalur.parent.mkdir(parents=True, exist_ok=True)
    jalur.write_text(teks, encoding="utf-8")
    return jalur


def jalankan(akar: Path, sumber: str, nama: str = "tests/test_contoh.py") -> dict[str, Any]:
    """Tulis satu berkas test sintetis lalu periksa seluruh direktori tests."""
    tulis(akar, nama, sumber)
    return check_tests.periksa([str(akar / "tests")])


def satu(akar: Path, sumber: str, nama: str = "tests/test_contoh.py") -> dict[str, Any]:
    """Kembalikan satu-satunya finding dari berkas test sintetis."""
    data = jalankan(akar, sumber, nama)
    assert len(data["tests"]) == 1
    return data["tests"][0]


def test_test_bersih_mendapat_keep(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "def test_bersih():\n    hasil = tambah(2, 3)\n    assert hasil == 5\n",
    )

    assert temuan["verdict"] == "KEEP"
    assert temuan["confidence"] == "high"
    assert temuan["signals"] == []
    assert temuan["evidence"] == "tidak ada sinyal kelemahan"
    assert temuan["duplicate_of"] is None


def test_sinyal_no_assert(tmp_path: Path) -> None:
    temuan = satu(tmp_path, "def test_kosong():\n    pass\n")

    assert temuan["signals"] == ["no_assert"]
    assert temuan["verdict"] == "REMOVE"
    assert temuan["confidence"] == "high"


def test_no_assert_mengenali_helper_lokal(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "def _cek_hasil(nilai):\n"
        "    assert nilai == 4\n"
        "\n"
        "def test_lewat_helper():\n"
        "    _cek_hasil(2 + 2)\n",
    )

    assert temuan["signals"] == []
    assert temuan["verdict"] == "KEEP"


def test_no_assert_mengenali_helper_method_class(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "class Kelas:\n"
        "    def _cek_hasil(self, nilai):\n"
        "        assert nilai == 4\n"
        "\n"
        "    def test_lewat_helper(self):\n"
        "        self._cek_hasil(2 + 2)\n",
    )

    assert temuan["signals"] == []
    assert temuan["verdict"] == "KEEP"


def test_with_pytest_raises_bukan_no_assert(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "import pytest\n"
        "\n"
        "def test_raises():\n"
        "    with pytest.raises(ValueError):\n"
        '        int("x")\n',
    )

    assert "no_assert" not in temuan["signals"]


def test_sinyal_tautology(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "def test_tautologi():\n    x = 1\n    assert x == x\n",
    )

    assert temuan["signals"] == ["tautology"]
    assert temuan["verdict"] == "REMOVE"
    assert temuan["confidence"] == "high"


def test_sinyal_expected_from_sut(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "def test_expected():\n    expected = hitung(2)\n    assert hitung(2) == expected\n",
    )

    assert temuan["signals"] == ["expected_from_sut"]
    assert temuan["verdict"] == "REMOVE"
    assert temuan["confidence"] == "medium"


def test_sinyal_existence_only(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "def test_ada():\n    assert hasil is not None\n",
    )

    assert temuan["signals"] == ["existence_only"]
    assert temuan["verdict"] == "REMOVE"
    assert temuan["confidence"] == "high"


def test_sinyal_duplicate_body(tmp_path: Path) -> None:
    sumber = (
        "def test_salin_a():\n"
        "    hasil = hitung(2)\n"
        "    assert hasil == 4\n"
        "\n"
        "def test_salin_b():\n"
        "    hasil = hitung(2)\n"
        "    assert hasil == 4\n"
    )
    data = jalankan(tmp_path, sumber)

    assert len(data["tests"]) == 2
    pertama, kedua = data["tests"]
    assert pertama["verdict"] == "KEEP"
    assert pertama["duplicate_of"] is None
    assert kedua["signals"] == ["duplicate_body"]
    assert kedua["verdict"] == "MERGE"
    assert kedua["confidence"] == "high"
    assert kedua["duplicate_of"] == pertama["id"]


def test_sinyal_private_access(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "from docgen.stages import office\n"
        "\n"
        "def test_privat():\n"
        "    assert office._docx_path(None) == 1\n",
    )

    assert temuan["signals"] == ["private_access"]
    assert temuan["verdict"] == "TRIM"
    assert temuan["confidence"] == "medium"


def test_private_access_lokal_test_bukan_sinyal(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "import pytest\n"
        "\n"
        "_ZIP_STUB = b'PK\\x03\\x04'\n"
        "\n"
        "def _helper(monkeypatch):\n"
        "    monkeypatch.setattr(object(), '_nilai', 1)\n"
        "\n"
        "def test_lokal(monkeypatch):\n"
        "    data = _ZIP_STUB\n"
        "    _helper(monkeypatch)\n"
        "    assert data == b'PK\\x03\\x04'\n",
    )

    assert temuan["signals"] == []
    assert temuan["verdict"] == "KEEP"


def test_private_access_pada_objek_tidak_dikenal_confidence_low(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "def test_privat(obj):\n    assert obj._nilai == 1\n",
    )

    assert temuan["signals"] == ["private_access"]
    assert temuan["verdict"] == "TRIM"
    assert temuan["confidence"] == "low"


def test_sinyal_broad_raises(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "import pytest\n"
        "\n"
        "def test_error():\n"
        "    with pytest.raises(ValueError):\n"
        '        int("x")\n',
    )

    assert temuan["signals"] == ["broad_raises"]
    assert temuan["verdict"] == "KEEP-WEAK"
    assert temuan["confidence"] == "medium"


def test_broad_raises_dengan_match_bukan_sinyal(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "import pytest\n"
        "\n"
        "def test_error():\n"
        '    with pytest.raises(ValueError, match="invalid"):\n'
        '        int("x")\n',
    )

    assert temuan["signals"] == []
    assert temuan["verdict"] == "KEEP"


def test_sinyal_exit_code_only(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "def test_exit():\n    hasil = jalankan()\n    assert hasil.returncode == 0\n",
    )

    assert temuan["signals"] == ["exit_code_only"]
    assert temuan["verdict"] == "KEEP-WEAK"
    assert temuan["confidence"] == "high"


def test_exit_code_dengan_pesan_bukan_sinyal(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "def test_exit():\n"
        "    hasil = jalankan()\n"
        "    assert hasil.returncode == 1\n"
        '    assert "ERROR" in hasil.stderr\n',
    )

    assert temuan["signals"] == []
    assert temuan["verdict"] == "KEEP"


def test_sinyal_exact_snapshot(tmp_path: Path) -> None:
    literal = "x" * 201
    temuan = satu(
        tmp_path,
        f"def test_snapshot():\n    assert teks == {literal!r}\n",
    )

    assert temuan["signals"] == ["exact_snapshot"]
    assert temuan["verdict"] == "TRIM"
    assert temuan["confidence"] == "medium"


def test_exact_snapshot_input_fixture_bukan_sinyal(tmp_path: Path) -> None:
    literal = "<w:body>" + "<w:p/>" * 80
    sumber = (
        "def test_input_xml():\n"
        f"    data = {literal!r}\n"
        "    hasil = parse_xml(data)\n"
        "    assert hasil == 1\n"
    )
    temuan = satu(tmp_path, sumber)

    assert temuan["signals"] == []
    assert temuan["verdict"] == "KEEP"


def test_exact_snapshot_variabel_expected_yang_diassert(tmp_path: Path) -> None:
    literal = "<w:body>" + "<w:p/>" * 80
    temuan = satu(
        tmp_path,
        f"def test_snapshot():\n"
        f"    expected = {literal!r}\n"
        f"    assert serialize_xml(parse_xml(expected)) == expected\n",
    )

    assert temuan["signals"] == ["exact_snapshot"]
    assert temuan["verdict"] == "TRIM"


def test_sinyal_env_dependent(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "import time\n\ndef test_waktu():\n    sekarang = time.time()\n    assert sekarang > 0\n",
    )

    assert temuan["signals"] == ["env_dependent"]
    assert temuan["verdict"] == "KEEP-WEAK"
    assert temuan["confidence"] == "low"


def test_sinyal_platform_skip_only(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "import sys\n"
        "\n"
        "import pytest\n"
        "\n"
        '@pytest.mark.skipif(sys.platform == "win32", reason="windows")\n'
        "def test_skip():\n"
        "    assert 2 + 2 == 4\n",
    )

    assert temuan["signals"] == ["platform_skip_only"]
    assert temuan["verdict"] == "KEEP-WEAK"
    assert temuan["confidence"] == "medium"


def test_sinyal_integration_in_unit(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "import subprocess\n"
        "\n"
        "def test_pandoc():\n"
        '    hasil = subprocess.run(["pandoc", "--version"])\n'
        "    assert hasil.stdout\n",
        nama="tests/unit/test_integrasi.py",
    )

    assert temuan["signals"] == ["integration_in_unit"]
    assert temuan["verdict"] == "MERGE"
    assert temuan["confidence"] == "medium"
    assert "tests/integration" in temuan["suggested_action"]


def test_integration_fake_subprocess_dan_timeout_expired_bukan_sinyal(tmp_path: Path) -> None:
    temuan = satu(
        tmp_path,
        "import subprocess\n"
        "\n"
        "import pytest\n"
        "\n"
        "def test_fake():\n"
        "    def runner(command, timeout):\n"
        "        raise subprocess.TimeoutExpired(command, timeout)\n"
        "\n"
        "    with pytest.raises(subprocess.TimeoutExpired):\n"
        "        runner(['mmdc'], 1)\n",
        nama="tests/unit/test_fake_subprocess.py",
    )

    assert temuan["signals"] == []
    assert temuan["verdict"] == "KEEP"


def test_fungsi_test_di_class_dikumpulkan(tmp_path: Path) -> None:
    data = jalankan(
        tmp_path,
        "class Kelas:\n"
        "    def test_di_kelas(self):\n"
        "        hasil = 2 + 2\n"
        "        assert hasil == 4\n",
    )

    assert len(data["tests"]) == 1
    temuan = data["tests"][0]
    assert temuan["id"].endswith("::Kelas::test_di_kelas")
    assert temuan["line"] == 2
    assert temuan["verdict"] == "KEEP"


def test_fixture_dan_non_test_diabaikan(tmp_path: Path) -> None:
    tulis(
        tmp_path,
        "tests/fixtures/test_tersembunyi.py",
        "def test_tersembunyi():\n    assert True\n",
    )
    tulis(
        tmp_path,
        "tests/bantuan.py",
        "def test_bantu():\n    assert True\n",
    )
    tulis(
        tmp_path,
        "tests/conftest.py",
        "def test_di_conftest():\n    assert True\n",
    )
    tulis(
        tmp_path,
        "tests/test_nyata.py",
        "def test_nyata():\n    assert 2 + 2 == 4\n",
    )

    data = check_tests.periksa([str(tmp_path / "tests")])
    langsung = check_tests.periksa([str(tmp_path / "tests" / "fixtures")])

    assert len(data["tests"]) == 1
    assert data["tests"][0]["id"].endswith("tests/test_nyata.py::test_nyata")
    assert langsung["tests"] == []


def test_schema_json_dan_determinisme(tmp_path: Path) -> None:
    tulis(
        tmp_path,
        "tests/test_b.py",
        "def test_b():\n    assert 2 + 2 == 4\n",
    )
    tulis(
        tmp_path,
        "tests/test_a.py",
        "def test_a():\n    assert 3 + 3 == 6\n",
    )

    pertama = check_tests.periksa([str(tmp_path / "tests")])
    kedua = check_tests.periksa([str(tmp_path / "tests")])
    teks_pertama = check_tests.render_json(pertama)
    teks_kedua = check_tests.render_json(kedua)
    data = json.loads(teks_pertama)

    assert teks_pertama == teks_kedua
    assert list(data) == ["schema_version", "generated_by", "summary", "tests"]
    assert data["schema_version"] == 1
    assert data["generated_by"] == "tools/dev/check_tests.py"
    assert list(data["summary"]) == [
        "total",
        "KEEP",
        "KEEP-WEAK",
        "MERGE",
        "TRIM",
        "REMOVE",
    ]
    assert data["summary"]["total"] == 2
    assert sum(data["summary"][verdict] for verdict in data["summary"] if verdict != "total") == 2
    assert list(data["tests"][0]) == [
        "id",
        "file",
        "line",
        "verdict",
        "confidence",
        "signals",
        "evidence",
        "suggested_action",
        "duplicate_of",
    ]
    posisi = [(test["file"], test["line"]) for test in data["tests"]]
    assert posisi == sorted(posisi)


def test_output_berkas_json(tmp_path: Path, capsys) -> None:
    tulis(
        tmp_path,
        "tests/test_contoh.py",
        "def test_contoh():\n    assert 2 + 2 == 4\n",
    )
    keluaran = tmp_path / "hasil.json"

    kode = check_tests.main([str(tmp_path / "tests"), "--output", str(keluaran)])
    data = json.loads(keluaran.read_text(encoding="utf-8"))

    assert kode == 0
    assert capsys.readouterr().out == ""
    assert data["summary"]["total"] == 1
    assert data["tests"][0]["verdict"] == "KEEP"


def test_fail_on_exit_code(tmp_path: Path, capsys) -> None:
    akar_tinggi = tmp_path / "tinggi"
    tulis(
        akar_tinggi,
        "tests/test_tinggi.py",
        "def test_tautologi():\n    assert True\n",
    )
    assert check_tests.main([str(akar_tinggi / "tests")]) == 0
    assert check_tests.main([str(akar_tinggi / "tests"), "--fail-on", "high"]) == 1

    akar_sedang = tmp_path / "sedang"
    tulis(
        akar_sedang,
        "tests/test_sedang.py",
        "from docgen.stages import office\n"
        "\n"
        "def test_privat():\n"
        "    assert office._docx_path(None) == 1\n",
    )
    assert check_tests.main([str(akar_sedang / "tests"), "--fail-on", "high"]) == 0
    assert check_tests.main([str(akar_sedang / "tests"), "--fail-on", "medium"]) == 1

    akar_rendah = tmp_path / "rendah"
    tulis(
        akar_rendah,
        "tests/test_rendah.py",
        "import time\n\ndef test_waktu():\n    sekarang = time.time()\n    assert sekarang > 0\n",
    )
    assert check_tests.main([str(akar_rendah / "tests"), "--fail-on", "medium"]) == 0
    assert check_tests.main([str(akar_rendah / "tests"), "--fail-on", "low"]) == 1
    capsys.readouterr()


def test_format_markdown(tmp_path: Path, capsys) -> None:
    tulis(
        tmp_path,
        "tests/test_contoh.py",
        "def test_contoh():\n    assert 2 + 2 == 4\n",
    )

    kode = check_tests.main([str(tmp_path / "tests"), "--format", "markdown"])
    keluaran = capsys.readouterr().out

    assert kode == 0
    assert "| Verdict | Jumlah |" in keluaran
    assert "| file:line | test | verdict | confidence | signals | action |" in keluaran
    assert "test_contoh" in keluaran
    assert "| KEEP | 1 |" in keluaran
