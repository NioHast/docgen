"""Tes checker kualitas test statis di tools/dev/check_tests.py."""

import json
from pathlib import Path
from typing import Any

from tools.dev import check_tests


def write(root: Path, name: str, text: str) -> Path:
    """Tulis berkas sintetis di bawah direktori sementara."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_check(root: Path, source: str, name: str = "tests/test_contoh.py") -> dict[str, Any]:
    """Tulis satu berkas test sintetis lalu periksa seluruh direktori tests."""
    write(root, name, source)
    return check_tests.periksa([str(root / "tests")])


def one_finding(root: Path, source: str, name: str = "tests/test_contoh.py") -> dict[str, Any]:
    """Kembalikan satu-satunya finding dari berkas test sintetis."""
    data = run_check(root, source, name)
    assert len(data["tests"]) == 1
    return data["tests"][0]


def test_clean_test_gets_keep(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "def test_bersih():\n    hasil = tambah(2, 3)\n    assert hasil == 5\n",
    )

    assert finding["verdict"] == "KEEP"
    assert finding["confidence"] == "high"
    assert finding["signals"] == []
    assert finding["evidence"] == "tidak ada sinyal kelemahan"
    assert finding["duplicate_of"] is None


def test_no_assert_signal(tmp_path: Path) -> None:
    finding = one_finding(tmp_path, "def test_kosong():\n    pass\n")

    assert finding["signals"] == ["no_assert"]
    assert finding["verdict"] == "REMOVE"
    assert finding["confidence"] == "high"


def test_no_assert_recognizes_local_helper(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "def _cek_hasil(nilai):\n"
        "    assert nilai == 4\n"
        "\n"
        "def test_lewat_helper():\n"
        "    _cek_hasil(2 + 2)\n",
    )

    assert finding["signals"] == []
    assert finding["verdict"] == "KEEP"


def test_no_assert_recognizes_helper_method_class(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "class Kelas:\n"
        "    def _cek_hasil(self, nilai):\n"
        "        assert nilai == 4\n"
        "\n"
        "    def test_lewat_helper(self):\n"
        "        self._cek_hasil(2 + 2)\n",
    )

    assert finding["signals"] == []
    assert finding["verdict"] == "KEEP"


def test_with_pytest_raises_is_not_no_assert(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "import pytest\n"
        "\n"
        "def test_raises():\n"
        "    with pytest.raises(ValueError):\n"
        '        int("x")\n',
    )

    assert "no_assert" not in finding["signals"]


def test_tautology_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "def test_tautologi():\n    x = 1\n    assert x == x\n",
    )

    assert finding["signals"] == ["tautology"]
    assert finding["verdict"] == "REMOVE"
    assert finding["confidence"] == "high"


def test_expected_from_sut_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "def test_expected():\n    expected = hitung(2)\n    assert hitung(2) == expected\n",
    )

    assert finding["signals"] == ["expected_from_sut"]
    assert finding["verdict"] == "REMOVE"
    assert finding["confidence"] == "medium"


def test_existence_only_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "def test_ada():\n    assert hasil is not None\n",
    )

    assert finding["signals"] == ["existence_only"]
    assert finding["verdict"] == "REMOVE"
    assert finding["confidence"] == "high"


def test_duplicate_body_signal(tmp_path: Path) -> None:
    source = (
        "def test_salin_a():\n"
        "    hasil = hitung(2)\n"
        "    assert hasil == 4\n"
        "\n"
        "def test_salin_b():\n"
        "    hasil = hitung(2)\n"
        "    assert hasil == 4\n"
    )
    data = run_check(tmp_path, source)

    assert len(data["tests"]) == 2
    first, second = data["tests"]
    assert first["verdict"] == "KEEP"
    assert first["duplicate_of"] is None
    assert second["signals"] == ["duplicate_body"]
    assert second["verdict"] == "MERGE"
    assert second["confidence"] == "high"
    assert second["duplicate_of"] == first["id"]


def test_private_access_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "from docgen.stages import office\n"
        "\n"
        "def test_privat():\n"
        "    assert office._docx_path(None) == 1\n",
    )

    assert finding["signals"] == ["private_access"]
    assert finding["verdict"] == "TRIM"
    assert finding["confidence"] == "medium"


def test_private_access_local_test_not_signal(tmp_path: Path) -> None:
    finding = one_finding(
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

    assert finding["signals"] == []
    assert finding["verdict"] == "KEEP"


def test_private_access_on_unknown_object_confidence_low(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "def test_privat(obj):\n    assert obj._nilai == 1\n",
    )

    assert finding["signals"] == ["private_access"]
    assert finding["verdict"] == "TRIM"
    assert finding["confidence"] == "low"


def test_broad_raises_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "import pytest\n"
        "\n"
        "def test_error():\n"
        "    with pytest.raises(ValueError):\n"
        '        int("x")\n',
    )

    assert finding["signals"] == ["broad_raises"]
    assert finding["verdict"] == "KEEP-WEAK"
    assert finding["confidence"] == "medium"


def test_broad_raises_with_match_not_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "import pytest\n"
        "\n"
        "def test_error():\n"
        '    with pytest.raises(ValueError, match="invalid"):\n'
        '        int("x")\n',
    )

    assert finding["signals"] == []
    assert finding["verdict"] == "KEEP"


def test_exit_code_only_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "def test_exit():\n    hasil = jalankan()\n    assert hasil.returncode == 0\n",
    )

    assert finding["signals"] == ["exit_code_only"]
    assert finding["verdict"] == "KEEP-WEAK"
    assert finding["confidence"] == "high"


def test_exit_code_with_message_not_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "def test_exit():\n"
        "    hasil = jalankan()\n"
        "    assert hasil.returncode == 1\n"
        '    assert "ERROR" in hasil.stderr\n',
    )

    assert finding["signals"] == []
    assert finding["verdict"] == "KEEP"


def test_exact_snapshot_signal(tmp_path: Path) -> None:
    literal = "x" * 201
    finding = one_finding(
        tmp_path,
        f"def test_snapshot():\n    assert teks == {literal!r}\n",
    )

    assert finding["signals"] == ["exact_snapshot"]
    assert finding["verdict"] == "TRIM"
    assert finding["confidence"] == "medium"


def test_exact_snapshot_input_fixture_not_signal(tmp_path: Path) -> None:
    literal = "<w:body>" + "<w:p/>" * 80
    source = (
        "def test_input_xml():\n"
        f"    data = {literal!r}\n"
        "    hasil = parse_xml(data)\n"
        "    assert hasil == 1\n"
    )
    finding = one_finding(tmp_path, source)

    assert finding["signals"] == []
    assert finding["verdict"] == "KEEP"


def test_exact_snapshot_asserted_expected_variable(tmp_path: Path) -> None:
    literal = "<w:body>" + "<w:p/>" * 80
    finding = one_finding(
        tmp_path,
        f"def test_snapshot():\n"
        f"    expected = {literal!r}\n"
        f"    assert serialize_xml(parse_xml(expected)) == expected\n",
    )

    assert finding["signals"] == ["exact_snapshot"]
    assert finding["verdict"] == "TRIM"


def test_env_dependent_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "import time\n\ndef test_waktu():\n    sekarang = time.time()\n    assert sekarang > 0\n",
    )

    assert finding["signals"] == ["env_dependent"]
    assert finding["verdict"] == "KEEP-WEAK"
    assert finding["confidence"] == "low"


def test_platform_skip_only_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "import sys\n"
        "\n"
        "import pytest\n"
        "\n"
        '@pytest.mark.skipif(sys.platform == "win32", reason="windows")\n'
        "def test_skip():\n"
        "    assert 2 + 2 == 4\n",
    )

    assert finding["signals"] == ["platform_skip_only"]
    assert finding["verdict"] == "KEEP-WEAK"
    assert finding["confidence"] == "medium"


def test_integration_in_unit_signal(tmp_path: Path) -> None:
    finding = one_finding(
        tmp_path,
        "import subprocess\n"
        "\n"
        "def test_pandoc():\n"
        '    hasil = subprocess.run(["pandoc", "--version"])\n'
        "    assert hasil.stdout\n",
        name="tests/unit/test_integrasi.py",
    )

    assert finding["signals"] == ["integration_in_unit"]
    assert finding["verdict"] == "MERGE"
    assert finding["confidence"] == "medium"
    assert "tests/integration" in finding["suggested_action"]


def test_integration_fake_subprocess_and_timeout_expired_not_signal(tmp_path: Path) -> None:
    finding = one_finding(
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
        name="tests/unit/test_fake_subprocess.py",
    )

    assert finding["signals"] == []
    assert finding["verdict"] == "KEEP"


def test_test_functions_in_class_are_collected(tmp_path: Path) -> None:
    data = run_check(
        tmp_path,
        "class Kelas:\n"
        "    def test_di_kelas(self):\n"
        "        hasil = 2 + 2\n"
        "        assert hasil == 4\n",
    )

    assert len(data["tests"]) == 1
    finding = data["tests"][0]
    assert finding["id"].endswith("::Kelas::test_di_kelas")
    assert finding["line"] == 2
    assert finding["verdict"] == "KEEP"


def test_fixtures_and_non_tests_ignored(tmp_path: Path) -> None:
    write(
        tmp_path,
        "tests/fixtures/test_tersembunyi.py",
        "def test_tersembunyi():\n    assert True\n",
    )
    write(
        tmp_path,
        "tests/bantuan.py",
        "def test_bantu():\n    assert True\n",
    )
    write(
        tmp_path,
        "tests/conftest.py",
        "def test_di_conftest():\n    assert True\n",
    )
    write(
        tmp_path,
        "tests/test_nyata.py",
        "def test_nyata():\n    assert 2 + 2 == 4\n",
    )

    data = check_tests.periksa([str(tmp_path / "tests")])
    direct = check_tests.periksa([str(tmp_path / "tests" / "fixtures")])

    assert len(data["tests"]) == 1
    assert data["tests"][0]["id"].endswith("tests/test_nyata.py::test_nyata")
    assert direct["tests"] == []


def test_schema_json_and_determinism(tmp_path: Path) -> None:
    write(
        tmp_path,
        "tests/test_b.py",
        "def test_b():\n    assert 2 + 2 == 4\n",
    )
    write(
        tmp_path,
        "tests/test_a.py",
        "def test_a():\n    assert 3 + 3 == 6\n",
    )

    first = check_tests.periksa([str(tmp_path / "tests")])
    second = check_tests.periksa([str(tmp_path / "tests")])
    first_text = check_tests.render_json(first)
    second_text = check_tests.render_json(second)
    data = json.loads(first_text)

    assert first_text == second_text
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
    positions = [(test["file"], test["line"]) for test in data["tests"]]
    assert positions == sorted(positions)


def test_output_json_file(tmp_path: Path, capsys) -> None:
    write(
        tmp_path,
        "tests/test_contoh.py",
        "def test_contoh():\n    assert 2 + 2 == 4\n",
    )
    output = tmp_path / "hasil.json"

    code = check_tests.main([str(tmp_path / "tests"), "--output", str(output)])
    data = json.loads(output.read_text(encoding="utf-8"))

    assert code == 0
    assert capsys.readouterr().out == ""
    assert data["summary"]["total"] == 1
    assert data["tests"][0]["verdict"] == "KEEP"


def test_fail_on_exit_code(tmp_path: Path, capsys) -> None:
    high_root = tmp_path / "tinggi"
    write(
        high_root,
        "tests/test_tinggi.py",
        "def test_tautologi():\n    assert True\n",
    )
    assert check_tests.main([str(high_root / "tests")]) == 0
    assert check_tests.main([str(high_root / "tests"), "--fail-on", "high"]) == 1

    medium_root = tmp_path / "sedang"
    write(
        medium_root,
        "tests/test_sedang.py",
        "from docgen.stages import office\n"
        "\n"
        "def test_privat():\n"
        "    assert office._docx_path(None) == 1\n",
    )
    assert check_tests.main([str(medium_root / "tests"), "--fail-on", "high"]) == 0
    assert check_tests.main([str(medium_root / "tests"), "--fail-on", "medium"]) == 1

    low_root = tmp_path / "rendah"
    write(
        low_root,
        "tests/test_rendah.py",
        "import time\n\ndef test_waktu():\n    sekarang = time.time()\n    assert sekarang > 0\n",
    )
    assert check_tests.main([str(low_root / "tests"), "--fail-on", "medium"]) == 0
    assert check_tests.main([str(low_root / "tests"), "--fail-on", "low"]) == 1
    capsys.readouterr()


def test_format_markdown(tmp_path: Path, capsys) -> None:
    write(
        tmp_path,
        "tests/test_contoh.py",
        "def test_contoh():\n    assert 2 + 2 == 4\n",
    )

    code = check_tests.main([str(tmp_path / "tests"), "--format", "markdown"])
    output = capsys.readouterr().out

    assert code == 0
    assert "| Verdict | Jumlah |" in output
    assert "| file:line | test | verdict | confidence | signals | action |" in output
    assert "test_contoh" in output
    assert "| KEEP | 1 |" in output
