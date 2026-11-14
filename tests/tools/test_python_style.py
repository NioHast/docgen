"""Tes checker gaya Python 3.15 untuk setiap aturan dan komentar allow."""

import json
import subprocess
from pathlib import Path

import pytest

from tools.quality import check_python, gate


def _write(root: Path, relative: str, teks: str) -> Path:
    jalur = root / relative
    jalur.parent.mkdir(parents=True, exist_ok=True)
    jalur.write_text(teks, encoding="utf-8")
    return jalur


def _jalankan(root: Path, relative: str, teks: str) -> check_python.Hasil:
    _write(root, relative, teks)
    return check_python.periksa([str(root / relative)], cwd=root)


def test_clean_file_has_no_findings(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/bersih.py",
        "def tambah(kiri: int, kanan: int) -> int:\n    return kiri + kanan\n",
    )

    assert hasil.berkas == 1
    assert hasil.temuan == ()


def test_future_import_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/lama.py",
        "from __future__ import annotations\n\nnilai: int = 1\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["future-annotations"]
    assert hasil.temuan[0].baris == 1


def test_future_import_is_flagged_in_tests(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "tests/test_lama.py",
        "from __future__ import annotations\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["future-annotations"]


def test_default_scope_skips_src_docgen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "src/autooffice/lama.py", "from __future__ import annotations\n")
    _write(tmp_path, "tests/test_lama.py", "from __future__ import annotations\n")
    _write(tmp_path, "src/docgen/lama.py", "from __future__ import annotations\n")
    monkeypatch.chdir(tmp_path)

    hasil = check_python.periksa()

    assert hasil.berkas == 2
    assert {item.berkas for item in hasil.temuan} == {
        "src/autooffice/lama.py",
        "tests/test_lama.py",
    }


def test_future_import_allow_comment_suppresses_finding(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/lama.py",
        "from __future__ import annotations  "
        "# python-style: allow future-annotations - modul masih 3.13\n",
    )

    assert hasil.temuan == ()


@pytest.mark.parametrize(("nama", "pengganti"), sorted(check_python.LEGACY_TYPING.items()))
def test_legacy_typing_alias_is_flagged(tmp_path: Path, nama: str, pengganti: str) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/typing_lama.py",
        f"from typing import {nama}\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["legacy-typing"]
    assert nama in hasil.temuan[0].pesan
    assert pengganti in hasil.temuan[0].pesan


def test_typing_attribute_alias_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/typing_atribut.py",
        "import typing\n\nnilai: typing.List[int] = []\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["legacy-typing"]
    assert "typing.List" in hasil.temuan[0].pesan


def test_legacy_typing_allow_comment_suppresses_finding(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/typing_allowed.py",
        "from typing import List  # python-style: allow legacy-typing - batas adapter\n",
    )

    assert hasil.temuan == ()


def test_allowed_typing_imports_are_not_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/typing_modern.py",
        "from typing import (\n"
        "    IO,\n"
        "    TYPE_CHECKING,\n"
        "    Any,\n"
        "    BinaryIO,\n"
        "    ClassVar,\n"
        "    Literal,\n"
        "    NamedTuple,\n"
        "    Never,\n"
        "    NotRequired,\n"
        "    Protocol,\n"
        "    ReadOnly,\n"
        "    Required,\n"
        "    TypedDict,\n"
        "    TypeIs,\n"
        "    Unpack,\n"
        "    cast,\n"
        "    override,\n"
        ")\n",
    )

    assert hasil.temuan == ()


def test_collections_abc_import_is_not_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/abc_modern.py",
        "from collections.abc import Callable, Iterable, Mapping, Sequence\n",
    )

    assert hasil.temuan == ()


def test_datetime_utcnow_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/waktu.py",
        "import datetime\n\nnilai = datetime.datetime.utcnow()\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["datetime-utcnow"]
    assert "datetime.now(UTC)" in hasil.temuan[0].pesan


def test_datetime_utcnow_reference_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/waktu_ref.py",
        "import datetime\n\nfungsi = datetime.datetime.utcnow\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["datetime-utcnow"]


def test_datetime_utcnow_alias_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/waktu_alias.py",
        "from datetime import datetime as dt\n\nnilai = dt.utcnow()\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["datetime-utcnow"]


def test_datetime_utcfromtimestamp_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/waktu_epoch.py",
        "from datetime import datetime\n\nnilai = datetime.utcfromtimestamp(0)\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["datetime-utcnow"]


def test_asyncio_get_event_loop_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/loop.py",
        "import asyncio\n\nnilai = asyncio.get_event_loop()\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["asyncio-loop"]


def test_asyncio_get_event_loop_policy_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/kebijakan.py",
        "from asyncio import get_event_loop_policy\n\nnilai = get_event_loop_policy()\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["asyncio-loop"]


def test_pkg_resources_import_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/sumber.py",
        "import pkg_resources\n\nnilai = pkg_resources.__name__\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["pkg-resources"]


def test_pkg_resources_from_import_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/sumber_nama.py",
        "from pkg_resources import resource_filename\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["pkg-resources"]


def test_codecs_open_is_flagged(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/berkas.py",
        "import codecs\n\ndengan = codecs.open('x.txt', encoding='utf-8')\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["codecs-open"]
    assert "open()" in hasil.temuan[0].pesan


def test_allow_comment_suppresses_other_rules(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/waktu.py",
        "import datetime\n\nnilai = datetime.datetime.utcnow()  "
        "# python-style: allow datetime-utcnow - kompatibilitas data lama\n",
    )

    assert hasil.temuan == ()


def test_allow_comment_only_applies_to_same_line(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/waktu.py",
        "# python-style: allow datetime-utcnow\n"
        "import datetime\n\nnilai = datetime.datetime.utcnow()\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["datetime-utcnow"]


def test_allow_comment_for_other_rule_does_not_suppress(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/waktu.py",
        "import datetime\n\nnilai = datetime.datetime.utcnow()  "
        "# python-style: allow codecs-open\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["datetime-utcnow"]


def test_allow_comment_with_multiple_rules(tmp_path: Path) -> None:
    hasil = _jalankan(
        tmp_path,
        "src/autooffice/campur.py",
        "import codecs\nimport datetime\n\n"
        "nilai = datetime.datetime.utcnow()  "
        "# python-style: allow datetime-utcnow, codecs-open\n"
        "dengan = codecs.open('x.txt')\n",
    )

    assert [item.aturan for item in hasil.temuan] == ["codecs-open"]


def test_unreadable_file_is_reported(tmp_path: Path) -> None:
    hasil = _jalankan(tmp_path, "src/autooffice/rusak.py", "def rusak(:\n")

    assert [item.aturan for item in hasil.temuan] == ["unreadable"]
    assert hasil.temuan[0].baris == 0


def test_cli_text_reports_findings_and_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    jalur = _write(
        tmp_path,
        "src/autooffice/lama.py",
        "from __future__ import annotations\n",
    )

    kode = check_python.main([str(jalur)])

    keluaran = capsys.readouterr().out
    assert kode == 1
    assert "Berkas diperiksa: 1" in keluaran
    assert "[future-annotations]" in keluaran


def test_cli_clean_file_returns_zero(tmp_path: Path) -> None:
    jalur = _write(tmp_path, "src/autooffice/bersih.py", "nilai: int = 1\n")

    assert check_python.main([str(jalur)]) == 0


def test_cli_json_output_is_machine_readable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(
        tmp_path,
        "tests/test_lama.py",
        "from __future__ import annotations\n",
    )
    monkeypatch.chdir(tmp_path)

    kode = check_python.main(["--format", "json", "tests/test_lama.py"])

    data = json.loads(capsys.readouterr().out)
    assert kode == 1
    assert data["files"] == 1
    assert data["findings"] == 1
    assert data["by_rule"] == {"future-annotations": 1}
    assert data["violations"][0]["rule"] == "future-annotations"
    assert data["violations"][0]["file"] == "tests/test_lama.py"
    assert data["violations"][0]["line"] == 1


def test_cli_list_prints_every_rule(capsys: pytest.CaptureFixture[str]) -> None:
    kode = check_python.main(["--list"])

    keluaran = capsys.readouterr().out
    assert kode == 0
    for aturan in check_python.ATURAN:
        assert aturan.nama in keluaran


def test_cli_missing_path_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kode = check_python.main([str(tmp_path / "tidak-ada")])

    assert kode == 2
    assert "path tidak ditemukan" in capsys.readouterr().err


def test_gate_python_style_step_is_blocking() -> None:
    step = next(item for item in gate.build_steps() if item.nama == "python-style")

    assert step.memblokir is True
    assert gate.step_names()[-1] == "python-style"


def test_gate_blocking_step_fails_the_gate(tmp_path: Path) -> None:
    def runner(command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1)

    kode = gate.run_steps(gate.select_steps(["python-style"]), tmp_path, runner=runner)

    assert kode == 1
