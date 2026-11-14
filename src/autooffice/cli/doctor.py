"""Perintah ``doctor``: cek dependency lokal tanpa jaringan.

Pemeriksaan memakai executable lokal, registry COM Windows, dan hash aset font
yang dibundel. Tidak ada panggilan jaringan, tidak ada pembuatan file, dan
tidak ada aplikasi Office yang dijalankan.
"""

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from autooffice.errors import AutoOfficeError


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """Status satu dependency yang diperiksa ``doctor``."""

    name: str
    ok: bool
    required: bool
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Ringkasan pemeriksaan doctor."""

    checks: tuple[DoctorCheck, ...]
    targets: tuple[str, ...] | None
    ok: bool

    def to_dict(self) -> dict[str, object]:
        """Bentuk JSON deterministik untuk ``doctor --json``."""
        return {
            "ok": self.ok,
            "targets": list(self.targets) if self.targets is not None else None,
            "python": platform.python_version(),
            "platform": sys.platform,
            "checks": [
                {
                    "name": check.name,
                    "ok": check.ok,
                    "required": check.required,
                    "detail": check.detail,
                }
                for check in self.checks
            ],
        }


def doctor_report(targets: tuple[str, ...] | None) -> DoctorReport:
    """Kumpulkan seluruh hasil pemeriksaan doctor."""
    python_ok = sys.version_info >= (3, 15)
    python_detail = (
        f"{platform.python_version()} (butuh >=3.15)"
        if not python_ok
        else (platform.python_version())
    )
    pandoc = _find_tool("pandoc")
    pandoc_version = _tool_version(pandoc)
    mmdc = _find_tool("mmdc")
    mmdc_version = _tool_version(mmdc)
    word_ok = _com_registered("Word.Application")
    powerpoint_ok = _com_registered("PowerPoint.Application")
    pywin32_ok, pywin32_detail = _pywin32_status()
    font_assets_ok, font_assets_detail = _font_assets_status()
    font_install_ok, font_install_detail = _font_install_status()
    google_ok, google_detail = _google_status()
    workspace_ok = os.access(Path.cwd(), os.W_OK)

    required = _required_names(targets)
    checks = (
        DoctorCheck(
            name="python",
            ok=python_ok,
            required="python" in required,
            detail=python_detail,
        ),
        DoctorCheck(
            name="pandoc",
            ok=bool(pandoc),
            required="pandoc" in required,
            detail=(
                f"{pandoc_version} - {pandoc}"
                if pandoc and pandoc_version
                else (pandoc or "tidak ditemukan; install Pandoc untuk DOCX")
            ),
        ),
        DoctorCheck(
            name="mmdc",
            ok=bool(mmdc),
            required=False,
            detail=(
                f"{mmdc_version} - {mmdc}"
                if mmdc and mmdc_version
                else (mmdc or "tidak ditemukan; diperlukan hanya untuk blok Mermaid")
            ),
        ),
        DoctorCheck(
            name="word",
            ok=word_ok,
            required="word" in required,
            detail=_office_detail(word_ok, "Microsoft Word", "Word.Application"),
        ),
        DoctorCheck(
            name="powerpoint",
            ok=powerpoint_ok,
            required="powerpoint" in required,
            detail=_office_detail(
                powerpoint_ok,
                "Microsoft PowerPoint",
                "PowerPoint.Application",
            ),
        ),
        DoctorCheck(
            name="pywin32",
            ok=pywin32_ok,
            required="pywin32" in required,
            detail=pywin32_detail,
        ),
        DoctorCheck(
            name="font-assets",
            ok=font_assets_ok,
            required="font-assets" in required,
            detail=font_assets_detail,
        ),
        DoctorCheck(
            name="fonts",
            ok=font_install_ok,
            required="fonts" in required,
            detail=font_install_detail,
        ),
        DoctorCheck(
            name="google",
            ok=google_ok,
            required="google" in required,
            detail=google_detail,
        ),
        DoctorCheck(
            name="workspace",
            ok=workspace_ok,
            required=True,
            detail=str(Path.cwd()) if workspace_ok else f"tidak dapat ditulis: {Path.cwd()}",
        ),
    )

    required_ok = all(check.ok for check in checks if check.required)
    if targets is not None and "pdf" in targets:
        required_ok = required_ok and (word_ok or powerpoint_ok)
    return DoctorReport(checks=checks, targets=targets, ok=required_ok)


def render_doctor(report: DoctorReport, *, json_output: bool) -> int:
    """Cetak laporan doctor dan kembalikan exit code 0/1."""
    if json_output:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for check in report.checks:
            marker = "[OK]" if check.ok else "[--]"
            requirement = " wajib" if check.required else ""
            print(f"{marker} {check.name:<12} {check.detail}{requirement}")
        print()
        if report.ok:
            print("Kesimpulan: dependency wajib untuk target yang diminta tersedia.")
        else:
            print("Kesimpulan: dependency wajib belum lengkap; periksa baris berstatus [--].")
    return 0 if report.ok else 1


def _required_names(targets: tuple[str, ...] | None) -> set[str]:
    """Dependency wajib untuk kombinasi target doctor.

    ``doctor`` tidak menerima path input, sehingga target ``pdf`` tunggal
    tidak dapat membedakan sumber ``.md`` (Word) dan ``.yaml`` (PowerPoint).
    Kombinasi target dipakai sebagai petunjuk: ``docx,pdf`` mewajibkan Word,
    sedangkan ``pptx,pdf``/``slides,pdf`` mewajibkan PowerPoint. Untuk ``pdf``
    tunggal, salah satu aplikasi Office diterima (lihat ``doctor_report``).
    """

    required = {"python", "workspace"}
    if targets is None:
        required.update({"pandoc", "font-assets", "fonts"})
        return required

    target_set = set(targets)
    if "docx" in target_set:
        required.add("pandoc")
    if "pptx" in target_set:
        required.update({"powerpoint", "pywin32", "fonts"})
    if "slides" in target_set:
        required.update({"font-assets", "google"})
    if "pdf" in target_set:
        if "pptx" in target_set or "slides" in target_set:
            required.update({"powerpoint", "pywin32", "fonts"})
        if "docx" in target_set:
            required.add("word")
    return required


def _find_tool(name: str) -> str | None:
    if platform.system() != "Windows":
        return shutil.which(name)
    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    if name == "pandoc":
        if local:
            candidates.append(Path(local) / "Pandoc" / "pandoc.exe")
        if program_files:
            candidates.append(Path(program_files) / "Pandoc" / "pandoc.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(f"{name}.exe") or shutil.which(name)


def _tool_version(command: str | None) -> str | None:
    if command is None:
        return None
    try:
        completed = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    return output[0] if output else None


def _com_registered(program_id: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        winreg = importlib.import_module("winreg")
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, program_id):
            return True
    except OSError:
        return False


def _office_detail(ok: bool, label: str, program_id: str) -> str:
    if sys.platform != "win32":
        return f"tidak berlaku; COM hanya Windows ({label})"
    if ok:
        return f"COM terdaftar ({program_id})"
    return f"tidak terdaftar; install {label}"


def _pywin32_status() -> tuple[bool, str]:
    """Periksa pywin32 lokal untuk adapter COM PowerPoint/Word."""

    if sys.platform != "win32":
        return False, "tidak berlaku; pywin32 hanya Windows"
    missing = [name for name in ("win32com", "pythoncom") if importlib.util.find_spec(name) is None]
    if missing:
        return (
            False,
            "pywin32 belum terpasang: "
            + ", ".join(missing)
            + "; jalankan `uv sync --extra windows`",
        )
    return True, "pywin32 terpasang untuk adapter COM"


def _font_assets_status() -> tuple[bool, str]:
    try:
        from autooffice.design import fonts
    except ImportError as exc:  # pragma: no cover - paket rusak
        return False, f"modul font tidak dapat diimpor: {exc}"

    missing: list[str] = []
    mismatched: list[str] = []
    for name, expected in fonts.ASSET_HASHES.items():
        path = fonts.FONT_DIR / name
        if not path.is_file():
            missing.append(name)
            continue
        try:
            actual = fonts.sha256(path)
        except OSError:
            missing.append(name)
            continue
        if actual != expected:
            mismatched.append(name)
    if missing:
        return False, "aset font hilang: " + ", ".join(missing)
    if mismatched:
        return False, "hash font tidak cocok: " + ", ".join(mismatched)
    return True, f"{len(fonts.FONT_FILES)} TTF + lisensi di {fonts.FONT_DIR}"


def _font_install_status() -> tuple[bool, str]:
    try:
        from autooffice.design import fonts
    except ImportError as exc:  # pragma: no cover - paket rusak
        return False, f"modul font tidak dapat diimpor: {exc}"

    if sys.platform != "win32":
        return True, "tidak berlaku; instalasi font per-user hanya Windows"
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return False, "LOCALAPPDATA tidak ditemukan; jalankan `python tools/install_fonts.py`"
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    return evaluate_font_install(
        per_user_dir=Path(local_app_data) / "Microsoft" / "Windows" / "Fonts",
        system_dir=windows_dir / "Fonts",
        registry_values=_read_font_registry_values(),
        font_files=fonts.FONT_FILES,
    )


def evaluate_font_install(
    *,
    per_user_dir: Path,
    system_dir: Path,
    registry_values: Mapping[str, str],
    font_files: Sequence[str],
) -> tuple[bool, str]:
    """Nilai status font terpasang dari direktori dan nilai registry."""

    total = len(font_files)
    expected_names = {name.casefold() for name in font_files}
    per_user_names = {
        name.casefold() for name in font_files if _font_file_present(per_user_dir / name)
    }
    system_names = {name.casefold() for name in font_files if _font_file_present(system_dir / name)}
    registry_paths = [
        path
        for path in _matching_registry_paths(registry_values, system_dir)
        if path.name.casefold() in expected_names
    ]
    per_user_names.update(
        path.name.casefold() for path in registry_paths if path.is_relative_to(per_user_dir)
    )
    system_names.update(
        path.name.casefold() for path in registry_paths if path.is_relative_to(system_dir)
    )
    per_user_count = len(per_user_names)
    system_count = len(system_names)

    if per_user_count >= total:
        return True, f"terpasang per-user ({total}/{total}) di {per_user_dir}"
    if system_count >= total:
        return True, f"terpasang sistem ({total}/{total}) di {system_dir}"
    if per_user_count or system_count:
        return (
            False,
            "terpasang sebagian "
            f"(per-user {per_user_count}/{total}, sistem {system_count}/{total}); "
            "jalankan `python tools/install_fonts.py`",
        )
    return False, "belum terpasang; jalankan `python tools/install_fonts.py`"


def _font_file_present(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _matching_registry_paths(
    registry_values: Mapping[str, str],
    system_dir: Path,
) -> list[Path]:
    paths: list[Path] = []
    for value_name, raw_value in registry_values.items():
        if "plus jakarta sans" not in value_name.casefold():
            continue
        path = Path(raw_value)
        if not path.is_absolute():
            path = system_dir / path
        if _font_file_present(path):
            paths.append(path)
    return paths


def _read_font_registry_values() -> dict[str, str]:
    if sys.platform != "win32":
        return {}
    try:
        winreg = importlib.import_module("winreg")
    except ImportError:
        return {}
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows NT\CurrentVersion\Fonts",
        ) as key:
            count = winreg.QueryInfoKey(key)[1]
            values: dict[str, str] = {}
            for index in range(count):
                name, value, kind = winreg.EnumValue(key, index)
                if kind == winreg.REG_SZ:
                    values[str(name)] = str(value)
            return values
    except OSError:
        return {}


def _module_available(name: str) -> bool:
    """Periksa spesifikasi modul tanpa gagal saat paket induknya tidak ada."""

    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError, ValueError:
        return False


def _google_status() -> tuple[bool, str]:
    """Periksa extra Google dan kredensial OAuth lokal tanpa jaringan."""

    if not _module_available("google"):
        return False, "google extra tidak terpasang"
    missing = [name for name in ("googleapiclient", "google.auth") if not _module_available(name)]
    if missing:
        return False, "extra google belum lengkap: " + ", ".join(missing)
    try:
        from autooffice.google import OAuthSettings, TokenStore

        OAuthSettings.from_environment()
        TokenStore.from_environment().require()
    except (AutoOfficeError, ImportError, OSError, ValueError) as exc:
        return (
            False,
            f"kredensial Google belum siap: {exc}; set GOOGLE_CLIENT_ID/"
            "GOOGLE_CLIENT_SECRET dan jalankan login OAuth",
        )
    return True, "extra google dan token OAuth lokal siap (tanpa jaringan)"


__all__ = [
    "DoctorCheck",
    "DoctorReport",
    "doctor_report",
    "render_doctor",
]
