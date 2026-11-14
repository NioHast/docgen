"""Tes checker gaya Python 3.15 untuk setiap aturan dan komentar allow."""

import json
import subprocess
from pathlib import Path

import pytest

from tools.quality import check_python, gate


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(root: Path, relative: str, text: str) -> check_python.Result:
    _write(root, relative, text)
    return check_python.check([str(root / relative)], cwd=root)


def test_clean_file_has_no_findings(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/bersih.py",
        "def tambah(kiri: int, kanan: int) -> int:\n    return kiri + kanan\n",
    )

    assert result.file_count == 1
    assert result.findings == ()


def test_future_import_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/lama.py",
        "from __future__ import annotations\n\nnilai: int = 1\n",
    )

    assert [item.rule for item in result.findings] == ["future-annotations"]
    assert result.findings[0].line == 1


def test_future_import_is_flagged_in_tests(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "tests/test_lama.py",
        "from __future__ import annotations\n",
    )

    assert [item.rule for item in result.findings] == ["future-annotations"]


def test_default_scope_checks_autooffice_and_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "src/autooffice/lama.py", "from __future__ import annotations\n")
    _write(tmp_path, "tests/test_lama.py", "from __future__ import annotations\n")
    monkeypatch.chdir(tmp_path)

    result = check_python.check()

    assert result.file_count == 2
    assert {item.file for item in result.findings} == {
        "src/autooffice/lama.py",
        "tests/test_lama.py",
    }


def test_future_import_allow_comment_suppresses_finding(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/lama.py",
        "from __future__ import annotations  "
        "# python-style: allow future-annotations - modul masih 3.13\n",
    )

    assert result.findings == ()


@pytest.mark.parametrize(("name", "replacement"), sorted(check_python.LEGACY_TYPING.items()))
def test_legacy_typing_alias_is_flagged(tmp_path: Path, name: str, replacement: str) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/typing_lama.py",
        f"from typing import {name}\n",
    )

    assert [item.rule for item in result.findings] == ["legacy-typing"]
    assert name in result.findings[0].message
    assert replacement in result.findings[0].message


def test_typing_attribute_alias_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/typing_atribut.py",
        "import typing\n\nnilai: typing.List[int] = []\n",
    )

    assert [item.rule for item in result.findings] == ["legacy-typing"]
    assert "typing.List" in result.findings[0].message


def test_legacy_typing_allow_comment_suppresses_finding(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/typing_allowed.py",
        "from typing import List  # python-style: allow legacy-typing - batas adapter\n",
    )

    assert result.findings == ()


def test_allowed_typing_imports_are_not_flagged(tmp_path: Path) -> None:
    result = _run(
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

    assert result.findings == ()


def test_collections_abc_import_is_not_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/abc_modern.py",
        "from collections.abc import Callable, Iterable, Mapping, Sequence\n",
    )

    assert result.findings == ()


def test_datetime_utcnow_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/waktu.py",
        "import datetime\n\nnilai = datetime.datetime.utcnow()\n",
    )

    assert [item.rule for item in result.findings] == ["datetime-utcnow"]
    assert "datetime.now(UTC)" in result.findings[0].message


def test_datetime_utcnow_reference_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/waktu_ref.py",
        "import datetime\n\nfungsi = datetime.datetime.utcnow\n",
    )

    assert [item.rule for item in result.findings] == ["datetime-utcnow"]


def test_datetime_utcnow_alias_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/waktu_alias.py",
        "from datetime import datetime as dt\n\nnilai = dt.utcnow()\n",
    )

    assert [item.rule for item in result.findings] == ["datetime-utcnow"]


def test_datetime_utcfromtimestamp_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/waktu_epoch.py",
        "from datetime import datetime\n\nnilai = datetime.utcfromtimestamp(0)\n",
    )

    assert [item.rule for item in result.findings] == ["datetime-utcnow"]


def test_asyncio_get_event_loop_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/loop.py",
        "import asyncio\n\nnilai = asyncio.get_event_loop()\n",
    )

    assert [item.rule for item in result.findings] == ["asyncio-loop"]


def test_asyncio_get_event_loop_policy_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/kebijakan.py",
        "from asyncio import get_event_loop_policy\n\nnilai = get_event_loop_policy()\n",
    )

    assert [item.rule for item in result.findings] == ["asyncio-loop"]


def test_pkg_resources_import_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/sumber.py",
        "import pkg_resources\n\nnilai = pkg_resources.__name__\n",
    )

    assert [item.rule for item in result.findings] == ["pkg-resources"]


def test_pkg_resources_from_import_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/sumber_nama.py",
        "from pkg_resources import resource_filename\n",
    )

    assert [item.rule for item in result.findings] == ["pkg-resources"]


def test_codecs_open_is_flagged(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/berkas.py",
        "import codecs\n\ndengan = codecs.open('x.txt', encoding='utf-8')\n",
    )

    assert [item.rule for item in result.findings] == ["codecs-open"]
    assert "open()" in result.findings[0].message


def test_allow_comment_suppresses_other_rules(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/waktu.py",
        "import datetime\n\nnilai = datetime.datetime.utcnow()  "
        "# python-style: allow datetime-utcnow - kompatibilitas data lama\n",
    )

    assert result.findings == ()


def test_allow_comment_only_applies_to_same_line(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/waktu.py",
        "# python-style: allow datetime-utcnow\n"
        "import datetime\n\nnilai = datetime.datetime.utcnow()\n",
    )

    assert [item.rule for item in result.findings] == ["datetime-utcnow"]


def test_allow_comment_for_other_rule_does_not_suppress(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/waktu.py",
        "import datetime\n\nnilai = datetime.datetime.utcnow()  "
        "# python-style: allow codecs-open\n",
    )

    assert [item.rule for item in result.findings] == ["datetime-utcnow"]


def test_allow_comment_with_multiple_rules(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "src/autooffice/campur.py",
        "import codecs\nimport datetime\n\n"
        "nilai = datetime.datetime.utcnow()  "
        "# python-style: allow datetime-utcnow, codecs-open\n"
        "dengan = codecs.open('x.txt')\n",
    )

    assert [item.rule for item in result.findings] == ["codecs-open"]


def test_unreadable_file_is_reported(tmp_path: Path) -> None:
    result = _run(tmp_path, "src/autooffice/rusak.py", "def rusak(:\n")

    assert [item.rule for item in result.findings] == ["unreadable"]
    assert result.findings[0].line == 0


def test_cli_text_reports_findings_and_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(
        tmp_path,
        "src/autooffice/lama.py",
        "from __future__ import annotations\n",
    )

    code = check_python.main([str(path)])

    output = capsys.readouterr().out
    assert code == 1
    assert "Berkas diperiksa: 1" in output
    assert "[future-annotations]" in output


def test_cli_clean_file_returns_zero(tmp_path: Path) -> None:
    path = _write(tmp_path, "src/autooffice/bersih.py", "nilai: int = 1\n")

    assert check_python.main([str(path)]) == 0


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

    code = check_python.main(["--format", "json", "tests/test_lama.py"])

    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert data["files"] == 1
    assert data["findings"] == 1
    assert data["by_rule"] == {"future-annotations": 1}
    assert data["violations"][0]["rule"] == "future-annotations"
    assert data["violations"][0]["file"] == "tests/test_lama.py"
    assert data["violations"][0]["line"] == 1


def test_cli_list_prints_every_rule(capsys: pytest.CaptureFixture[str]) -> None:
    code = check_python.main(["--list"])

    output = capsys.readouterr().out
    assert code == 0
    for rule in check_python.RULES:
        assert rule.name in output


def test_cli_missing_path_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = check_python.main([str(tmp_path / "tidak-ada")])

    assert code == 2
    assert "path tidak ditemukan" in capsys.readouterr().err


def test_gate_python_style_step_is_blocking() -> None:
    step = next(item for item in gate.build_steps() if item.name == "python-style")

    assert step.blocking is True
    names = gate.step_names()
    assert names.index("python-style") < names.index("identifiers") < names.index("source-style")


def test_gate_blocking_step_fails_the_gate(tmp_path: Path) -> None:
    def runner(command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1)

    code = gate.run_steps(gate.select_steps(["python-style"]), tmp_path, runner=runner)

    assert code == 1
