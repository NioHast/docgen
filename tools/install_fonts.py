#!/usr/bin/env python3
r"""Pasang Plus Jakarta Sans per-user di Windows tanpa hak administrator.

Skrip ini menyalin empat TTF yang dibundel ke
``%LOCALAPPDATA%\\Microsoft\\Windows\\Fonts``, menulis nilai registry
``HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts``, memuat font
ke sesi berjalan, lalu menyiarkan ``WM_FONTCHANGE``. Tidak memakai PowerShell,
pywin32, atau hak administrator.

Pemakaian:
    python tools/install_fonts.py
    python tools/install_fonts.py --list
"""

import argparse
import ctypes
import hashlib
import os
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FONT_DIR = REPO_ROOT / "src" / "autooffice" / "assets" / "fonts" / "plus-jakarta-sans"
FONT_FAMILY = "Plus Jakarta Sans"
FONT_FILES: tuple[str, ...] = (
    "PlusJakartaSans-Regular.ttf",
    "PlusJakartaSans-SemiBold.ttf",
    "PlusJakartaSans-Bold.ttf",
    "PlusJakartaSans-ExtraBold.ttf",
)
REGISTRY_SUBKEY = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"
WM_FONTCHANGE = 0x001D
HWND_BROADCAST = 0xFFFF
SMTO_ABORTIFHUNG = 0x0002
BROADCAST_TIMEOUT_MS = 1000


class FontInstallError(RuntimeError):
    """Kegagalan instalasi font yang dapat ditampilkan tanpa traceback."""


class FontRegistry(Protocol):
    """Antarmuka minimal registry font agar test tidak menyentuh registry asli."""

    def set_value(self, name: str, value: str) -> None:
        """Tulis satu nilai REG_SZ di bawah key font per-user."""
        ...

    def get_values(self) -> dict[str, str]:
        """Kembalikan seluruh nilai string di bawah key font per-user."""
        ...


@dataclass(frozen=True, slots=True)
class FontInstallPlan:
    """Satu font yang akan dipasang beserta metadata registry-nya."""

    file_name: str
    source: Path
    target: Path
    registry_name: str
    registry_value: str
    source_sha256: str
    copy_needed: bool


@dataclass(frozen=True, slots=True)
class InstallOutcome:
    """Ringkasan satu kali instalasi font."""

    entries: tuple[FontInstallPlan, ...]
    copied: tuple[str, ...]
    unchanged: tuple[str, ...]
    registry_entries: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class FontStatus:
    """Status satu font untuk ``--list``."""

    file_name: str
    source: Path
    target: Path
    registry_name: str
    installed: bool
    hash_matches: bool
    registry_value: str | None


def sha256_file(path: Path) -> str:
    """Hitung digest SHA256 sebuah berkas."""

    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def file_hash_matches(source: Path, target: Path) -> bool:
    """True bila target ada dan hash-nya sama dengan source."""

    if not target.is_file():
        return False
    try:
        return sha256_file(source) == sha256_file(target)
    except OSError:
        return False


def per_user_fonts_dir(local_app_data: Path | str) -> Path:
    """Kembalikan direktori font per-user dari nilai ``%LOCALAPPDATA%``."""

    return Path(local_app_data) / "Microsoft" / "Windows" / "Fonts"


def installed_font_path(local_app_data: Path | str, file_name: str) -> Path:
    """Kembalikan path tujuan satu font per-user."""

    return per_user_fonts_dir(local_app_data) / file_name


def source_font_path(source_dir: Path | str, file_name: str) -> Path:
    """Kembalikan path aset font yang dibundel."""

    return Path(source_dir) / file_name


def registry_value_name(file_name: str) -> str:
    """Bentuk nama nilai registry dari nama berkas TTF.

    Gaya ``Regular`` mengikuti konvensi Windows ``Family (TrueType)``; gaya
    lain memakai ``Family Style (TrueType)`` agar empat weight tidak saling
    menimpa.
    """

    if file_name not in FONT_FILES:
        raise ValueError(f"nama berkas font tidak dikenal: {file_name}")
    stem = Path(file_name).stem
    prefix = "PlusJakartaSans-"
    style = stem[len(prefix) :]
    if style == "Regular":
        return f"{FONT_FAMILY} (TrueType)"
    return f"{FONT_FAMILY} {style} (TrueType)"


def registry_value_data(target: Path) -> str:
    """Bentuk data registry REG_SZ berupa path absolut font terpasang."""

    return str(Path(target).resolve())


def build_install_plan(
    source_dir: Path | str,
    local_app_data: Path | str,
) -> tuple[FontInstallPlan, ...]:
    """Susun rencana instalasi tanpa menulis berkas atau registry."""

    missing = [name for name in FONT_FILES if not source_font_path(source_dir, name).is_file()]
    if missing:
        raise FontInstallError(
            f"aset font tidak ditemukan di {Path(source_dir)}: {', '.join(missing)}"
        )
    plan: list[FontInstallPlan] = []
    for file_name in FONT_FILES:
        source = source_font_path(source_dir, file_name)
        target = installed_font_path(local_app_data, file_name)
        plan.append(
            FontInstallPlan(
                file_name=file_name,
                source=source,
                target=target,
                registry_name=registry_value_name(file_name),
                registry_value=registry_value_data(target),
                source_sha256=sha256_file(source),
                copy_needed=not file_hash_matches(source, target),
            )
        )
    return tuple(plan)


def _local_app_data_from_env() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if not value:
        raise FontInstallError(
            "LOCALAPPDATA tidak ditemukan; jalankan skrip ini di sesi pengguna Windows."
        )
    return Path(value)


def _copy_with_verification(source: Path, target: Path) -> None:
    """Salin font lewat berkas sementara lalu ganti target secara atomik."""

    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, temporary)
        if sha256_file(source) != sha256_file(temporary):
            raise FontInstallError(f"hasil salinan font tidak cocok dengan aset: {source}")
        os.replace(temporary, target)
    except OSError as exc:
        raise FontInstallError(f"gagal menyalin font ke {target}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


class WindowsFontRegistry:
    """Registry font per-user memakai ``winreg`` stdlib, tanpa pywin32."""

    def set_value(self, name: str, value: str) -> None:
        winreg = _winreg_module()
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_SUBKEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        except OSError as exc:
            raise FontInstallError(f"gagal menulis registry font '{name}': {exc}") from exc

    def get_values(self) -> dict[str, str]:
        winreg = _winreg_module()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_SUBKEY) as key:
                count = winreg.QueryInfoKey(key)[1]
                values: dict[str, str] = {}
                for index in range(count):
                    name, value, kind = winreg.EnumValue(key, index)
                    if kind == winreg.REG_SZ:
                        values[str(name)] = str(value)
                return values
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise FontInstallError(f"gagal membaca registry font: {exc}") from exc


def _winreg_module() -> Any:
    try:
        import winreg
    except ImportError as exc:  # pragma: no cover - hanya Windows yang diuji
        raise FontInstallError("modul winreg hanya tersedia di Windows.") from exc
    return winreg


def load_font_resource(path: Path) -> None:
    """Muat satu font ke sesi berjalan dengan ``AddFontResourceW``."""

    if sys.platform != "win32":
        return
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    add_font = gdi32.AddFontResourceW
    add_font.argtypes = [ctypes.c_wchar_p]
    add_font.restype = ctypes.c_int
    add_font(str(path))


def broadcast_font_change() -> None:
    """Siarkan ``WM_FONTCHANGE`` ke seluruh jendela lewat ``ctypes``."""

    if sys.platform != "win32":
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send_message = user32.SendMessageTimeoutW
    send_message.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_void_p,
    ]
    send_message.restype = ctypes.c_size_t
    result = send_message(
        ctypes.c_void_p(HWND_BROADCAST),
        WM_FONTCHANGE,
        0,
        None,
        SMTO_ABORTIFHUNG,
        BROADCAST_TIMEOUT_MS,
        None,
    )
    if result == 0:
        raise FontInstallError("gagal menyiarkan WM_FONTCHANGE ke sesi Windows.")


def install_fonts(
    *,
    source_dir: Path | str = SOURCE_FONT_DIR,
    local_app_data: Path | str | None = None,
    registry: FontRegistry | None = None,
    activate: Callable[[Path], None] | None = None,
    broadcast: Callable[[], None] | None = None,
    platform_name: str | None = None,
    dry_run: bool = False,
) -> InstallOutcome:
    """Pasang empat TTF per-user dan perbarui registry HKCU.

    Operasi dapat diuji tanpa registry asli dengan menginjeksi ``registry``,
    ``activate``, dan ``broadcast``. ``dry_run`` hanya menyusun rencana.
    """

    resolved_platform = platform_name if platform_name is not None else sys.platform
    if resolved_platform != "win32":
        raise FontInstallError("instalasi font per-user hanya didukung di Windows.")
    local = Path(local_app_data) if local_app_data is not None else _local_app_data_from_env()
    plan = build_install_plan(source_dir, local)
    copied: list[str] = []
    unchanged: list[str] = []
    if not dry_run:
        target_dir = per_user_fonts_dir(local)
        target_dir.mkdir(parents=True, exist_ok=True)
        font_registry = registry if registry is not None else WindowsFontRegistry()
        activate_font = activate if activate is not None else load_font_resource
        notify = broadcast if broadcast is not None else broadcast_font_change
        for entry in plan:
            if entry.copy_needed:
                _copy_with_verification(entry.source, entry.target)
                copied.append(entry.file_name)
                activate_font(entry.target)
            else:
                unchanged.append(entry.file_name)
            font_registry.set_value(entry.registry_name, entry.registry_value)
        notify()
    else:
        copied = [entry.file_name for entry in plan if entry.copy_needed]
        unchanged = [entry.file_name for entry in plan if not entry.copy_needed]
    return InstallOutcome(
        entries=plan,
        copied=tuple(copied),
        unchanged=tuple(unchanged),
        registry_entries=tuple((entry.registry_name, entry.registry_value) for entry in plan),
    )


def font_statuses(
    *,
    source_dir: Path | str = SOURCE_FONT_DIR,
    local_app_data: Path | str,
    registry: FontRegistry,
) -> tuple[FontStatus, ...]:
    """Baca status instalasi tanpa menulis berkas atau registry."""

    plan = build_install_plan(source_dir, local_app_data)
    values = registry.get_values()
    statuses: list[FontStatus] = []
    for entry in plan:
        installed = entry.target.is_file()
        statuses.append(
            FontStatus(
                file_name=entry.file_name,
                source=entry.source,
                target=entry.target,
                registry_name=entry.registry_name,
                installed=installed,
                hash_matches=installed and not entry.copy_needed,
                registry_value=values.get(entry.registry_name),
            )
        )
    return tuple(statuses)


def _render_status(status: FontStatus) -> str:
    if not status.installed:
        state = "belum terpasang"
    elif status.hash_matches:
        state = "terpasang, hash cocok"
    else:
        state = "terpasang, hash berbeda"
    registry_state = "registry cocok" if status.registry_value else "registry belum ada"
    return f"{status.file_name}: {state}; {registry_state}; {status.target}"


def _platform_name() -> str:
    return sys.platform


def _default_local_app_data() -> Path:
    return _local_app_data_from_env()


def _default_registry() -> FontRegistry:
    return WindowsFontRegistry()


def _default_activate(path: Path) -> None:
    load_font_resource(path)


def _default_broadcast() -> None:
    broadcast_font_change()


def main(argv: Sequence[str] | None = None) -> int:
    """Jalankan installer atau tampilkan status ``--list``."""

    parser = argparse.ArgumentParser(
        prog="install_fonts.py",
        description="Pasang Plus Jakarta Sans per-user di Windows tanpa admin.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_fonts",
        help="Tampilkan status instalasi tanpa mengubah berkas atau registry.",
    )
    args = parser.parse_args(argv)
    try:
        platform_name = _platform_name()
        registry = _default_registry()
        local_app_data = _default_local_app_data()
        if args.list_fonts:
            statuses = font_statuses(
                source_dir=SOURCE_FONT_DIR,
                local_app_data=local_app_data,
                registry=registry,
            )
            print(f"Plus Jakarta Sans: {len(FONT_FILES)} TTF bundled")
            for status in statuses:
                print(_render_status(status))
            return 0
        outcome = install_fonts(
            source_dir=SOURCE_FONT_DIR,
            local_app_data=local_app_data,
            registry=registry,
            activate=_default_activate,
            broadcast=_default_broadcast,
            platform_name=platform_name,
        )
    except (FontInstallError, OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    for name in outcome.copied:
        print(f"[COPY] {name}")
    for name in outcome.unchanged:
        print(f"[SKIP] {name} (hash sudah cocok)")
    for name, value in outcome.registry_entries:
        print(f"[REG]  {name} = {value}")
    print(
        f"[OK]   {len(outcome.copied)} disalin, {len(outcome.unchanged)} dilewati; "
        "WM_FONTCHANGE disiarkan."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
