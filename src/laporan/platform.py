"""Deteksi platform, shell, dan perkakas build.

Modul ini hanya menjawab pertanyaan "apa yang tersedia di mesin ini" dan
bagaimana menerjemahkan path agar dapat dibaca shell. Logika build tetap
milik ``build-docx.sh`` dan ``build.sh``.
"""

from __future__ import annotations

import os
import platform as _platform
import shutil
import subprocess
import sys
from pathlib import Path


def detect_os() -> str:
    """Kembalikan ``windows``, ``wsl``, ``linux``, atau ``macos``."""

    system = _platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    try:
        release = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        release = ""
    if "microsoft" in release:
        return "wsl"
    return "linux"


def to_posix_path(path: str | Path) -> str:
    """Ubah path Windows menjadi bentuk yang dipahami Git Bash/Debian bash."""

    value = str(path)
    if len(value) > 1 and value[1] == ":":
        return value.replace("\\", "/")
    return value


def find_bash() -> str | None:
    """Cari shell bash native yang cocok untuk build.

    Di Windows, ``bash.exe`` di ``System32`` adalah WSL dan tidak didukung oleh
    ``build-docx.sh``. Git Bash diutamakan.
    """

    override = os.environ.get("LAPORAN_BASH")
    if override:
        path = Path(override)
        if path.is_file():
            return str(path)

    os_name = detect_os()
    candidates: list[Path] = []
    if os_name == "windows":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env_name)
            if not base:
                continue
            candidates.extend(
                [
                    Path(base) / "Git" / "bin" / "bash.exe",
                    Path(base) / "Git" / "usr" / "bin" / "bash.exe",
                    Path(base) / "Programs" / "Git" / "bin" / "bash.exe",
                ]
            )

    found = shutil.which("bash")
    if found:
        candidates.append(Path(found))

    for candidate in candidates:
        if not candidate.is_file():
            continue
        if os_name == "windows" and "system32" in str(candidate).lower():
            continue
        return str(candidate)
    return None


def _windows_tool_candidates(name: str) -> list[Path]:
    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")

    if name == "pandoc":
        if local:
            candidates.append(Path(local) / "Pandoc" / "pandoc.exe")
        for base in (program_files, program_files_x86):
            if base:
                candidates.append(Path(base) / "Pandoc" / "pandoc.exe")
    elif name == "typst":
        for base in (local,):
            if not base:
                continue
            candidates.append(Path(base) / "Microsoft" / "WinGet" / "Links" / "typst.exe")
            packages = Path(base) / "Microsoft" / "WinGet" / "Packages"
            if packages.is_dir():
                candidates.extend(sorted(packages.glob("Typst.Typst_*/*/typst.exe")))
        profile = os.environ.get("USERPROFILE")
        if profile:
            candidates.append(Path(profile) / ".cargo" / "bin" / "typst.exe")
    return candidates


def find_tool(name: str, *, windows_name: str | None = None) -> str | None:
    """Cari executable di PATH lalu di lokasi instalasi Windows yang umum."""

    if detect_os() == "windows":
        exe_name = windows_name or f"{name}.exe"
        for candidate in _windows_tool_candidates(name):
            if candidate.is_file():
                return str(candidate)
        found = shutil.which(exe_name) or shutil.which(name)
    else:
        found = shutil.which(name)
    return found


def tool_version(command: str | None, *args: str) -> str | None:
    if not command:
        return None
    try:
        completed = subprocess.run(
            [command, *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    return output[0] if output else None


def find_word() -> str | None:
    """Cari Microsoft Word di Windows (registry lalu lokasi umum)."""

    if detect_os() != "windows":
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        winreg = None  # type: ignore[assignment]

    if winreg is not None:
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE"
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, "")
            except OSError:
                continue
            if value and Path(value).is_file():
                return str(value)

    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if not base:
            continue
        office_root = Path(base) / "Microsoft Office" / "root"
        if office_root.is_dir():
            matches = sorted(office_root.glob("Office*/WINWORD.EXE"))
            if matches:
                return str(matches[-1])
    return None


def find_libreoffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found

    os_name = detect_os()
    if os_name == "windows":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env_name)
            if not base:
                continue
            candidate = Path(base) / "LibreOffice" / "program" / "soffice.exe"
            if candidate.is_file():
                return str(candidate)
    elif os_name == "macos":
        candidate = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if candidate.is_file():
            return str(candidate)
    return None


def python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def python_executable() -> str:
    return sys.executable
