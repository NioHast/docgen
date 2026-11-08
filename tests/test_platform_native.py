"""Tes pemisahan toolchain Windows-native dan Debian-native.

Tes ini menjaga tiga hal:

1. ``detect_os`` hanya membedakan Windows dan Linux; WSL adalah Linux.
2. ``find_bash`` tidak pernah memilih launcher WSL di Windows dan tidak
   memakai executable Windows di Linux.
3. Skrip build tidak memuat jembatan path/perkakas lintas platform.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laporan import platform as platform_mod  # noqa: E402


NATIVE_FILES = [
    ROOT / "tools" / "env.sh",
    ROOT / "build.sh",
    ROOT / "build-docx.sh",
    ROOT / "src" / "laporan" / "platform.py",
]

FORBIDDEN_PATTERNS = {
    "wslpath": re.compile(r"wslpath", re.I),
    "cmd.exe": re.compile(r"cmd\.exe", re.I),
    "/mnt/c": re.compile(r"/mnt/c", re.I),
    "LAPORAN_PANDOC": re.compile(r"LAPORAN_PANDOC"),
    "LAPORAN_TYPST": re.compile(r"LAPORAN_TYPST"),
}


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Windows", "windows"),
        ("Linux", "linux"),
        ("Darwin", "linux"),
    ],
)
def test_detect_os_native(monkeypatch: pytest.MonkeyPatch, system: str, expected: str) -> None:
    monkeypatch.setattr(platform_mod._platform, "system", lambda: system)

    assert platform_mod.detect_os() == expected


def test_wsl_dilaporkan_sebagai_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    # WSL melaporkan system "Linux"; /proc/version tidak boleh mengubah hasil.
    monkeypatch.setattr(platform_mod._platform, "system", lambda: "Linux")

    assert platform_mod.detect_os() == "linux"


def test_tidak_ada_konversi_path_lintas_platform() -> None:
    assert not hasattr(platform_mod, "to_posix_path")


@pytest.mark.parametrize("path", NATIVE_FILES, ids=lambda item: item.name)
def test_skrip_native_tanpa_jembatan_lintas_platform(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    for label, pattern in FORBIDDEN_PATTERNS.items():
        assert not pattern.search(text), f"{path.name} masih memuat {label}"


def test_find_bash_windows_menolak_launcher_system32(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wsl_bash = tmp_path / "Windows" / "System32" / "bash.exe"
    wsl_bash.parent.mkdir(parents=True)
    wsl_bash.write_text("", encoding="utf-8")

    monkeypatch.delenv("LAPORAN_BASH", raising=False)
    monkeypatch.setattr(platform_mod, "detect_os", lambda: "windows")
    monkeypatch.setattr(platform_mod, "_windows_bash_candidates", lambda: [])
    monkeypatch.setattr(platform_mod.shutil, "which", lambda name: str(wsl_bash))

    assert platform_mod.find_bash() is None


def test_find_bash_windows_menolak_launcher_windowsapps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wsl_bash = tmp_path / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "bash.exe"
    wsl_bash.parent.mkdir(parents=True)
    wsl_bash.write_text("", encoding="utf-8")

    monkeypatch.delenv("LAPORAN_BASH", raising=False)
    monkeypatch.setattr(platform_mod, "detect_os", lambda: "windows")
    monkeypatch.setattr(platform_mod, "_windows_bash_candidates", lambda: [])
    monkeypatch.setattr(platform_mod.shutil, "which", lambda name: str(wsl_bash))

    assert platform_mod.find_bash() is None


def test_find_bash_windows_menerima_git_bash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    git_bash = tmp_path / "Program Files" / "Git" / "bin" / "bash.exe"
    git_bash.parent.mkdir(parents=True)
    git_bash.write_text("", encoding="utf-8")

    monkeypatch.delenv("LAPORAN_BASH", raising=False)
    monkeypatch.setattr(platform_mod, "detect_os", lambda: "windows")
    monkeypatch.setattr(platform_mod, "_windows_bash_candidates", lambda: [])
    monkeypatch.setattr(platform_mod.shutil, "which", lambda name: str(git_bash))

    assert platform_mod.find_bash() == str(git_bash)


def test_find_bash_linux_memakai_bash_native(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAPORAN_BASH", raising=False)
    monkeypatch.setattr(platform_mod, "detect_os", lambda: "linux")
    monkeypatch.setattr(platform_mod.shutil, "which", lambda name: "/usr/bin/bash")

    assert platform_mod.find_bash() == "/usr/bin/bash"


def test_find_bash_linux_menolak_override_executable_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    windows_bash = tmp_path / "bash.exe"
    windows_bash.write_text("", encoding="utf-8")

    monkeypatch.setenv("LAPORAN_BASH", str(windows_bash))
    monkeypatch.setattr(platform_mod, "detect_os", lambda: "linux")
    monkeypatch.setattr(platform_mod.shutil, "which", lambda name: None)

    assert platform_mod.find_bash() != str(windows_bash)


def _load_word_finalize():
    spec = importlib.util.spec_from_file_location(
        "word_finalize_uji", ROOT / "tools" / "word_finalize.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_word_finalize_linux_tidak_memanggil_word(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_word_finalize()
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(module, "is_windows", lambda: False)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    assert module.update_fields_with_word(tmp_path / "Laporan.docx", 10) is False
    assert calls == []


def test_find_tool_linux_tidak_memeriksa_lokasi_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    def fake_windows_candidates(name: str) -> list[Path]:
        called.append(name)
        return []

    monkeypatch.setattr(platform_mod, "detect_os", lambda: "linux")
    monkeypatch.setattr(platform_mod, "_windows_tool_candidates", fake_windows_candidates)
    monkeypatch.setattr(
        platform_mod.shutil, "which", lambda name: f"/usr/bin/{name}"
    )

    assert platform_mod.find_tool("pandoc") == "/usr/bin/pandoc"
    assert called == []
