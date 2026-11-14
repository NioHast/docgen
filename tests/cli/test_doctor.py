"""Tes pemeriksaan font terpasang di ``autooffice doctor``."""

from pathlib import Path

import pytest

from autooffice.cli import doctor
from autooffice.design.fonts import FONT_FILES


def _write_fonts(directory: Path, names: tuple[str, ...]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_bytes(b"font")


def test_font_install_detects_per_user_store(tmp_path: Path) -> None:
    per_user = tmp_path / "user-fonts"
    system = tmp_path / "system-fonts"
    _write_fonts(per_user, FONT_FILES)

    ok, detail = doctor.evaluate_font_install(
        per_user_dir=per_user,
        system_dir=system,
        registry_values={},
        font_files=FONT_FILES,
    )

    assert ok is True
    assert "per-user" in detail
    assert str(per_user) in detail


def test_font_install_detects_system_store(tmp_path: Path) -> None:
    per_user = tmp_path / "user-fonts"
    system = tmp_path / "system-fonts"
    _write_fonts(system, FONT_FILES)

    ok, detail = doctor.evaluate_font_install(
        per_user_dir=per_user,
        system_dir=system,
        registry_values={},
        font_files=FONT_FILES,
    )

    assert ok is True
    assert "sistem" in detail
    assert str(system) in detail


def test_font_install_detects_registry_with_absolute_path(tmp_path: Path) -> None:
    per_user = tmp_path / "user-fonts"
    system = tmp_path / "system-fonts"
    _write_fonts(per_user, FONT_FILES)
    values = {
        "Plus Jakarta Sans (TrueType)": str(per_user / FONT_FILES[0]),
        "Plus Jakarta Sans SemiBold (TrueType)": str(per_user / FONT_FILES[1]),
        "Plus Jakarta Sans Bold (TrueType)": str(per_user / FONT_FILES[2]),
        "Plus Jakarta Sans ExtraBold (TrueType)": str(per_user / FONT_FILES[3]),
    }

    ok, detail = doctor.evaluate_font_install(
        per_user_dir=per_user,
        system_dir=system,
        registry_values=values,
        font_files=FONT_FILES,
    )

    assert ok is True
    assert "per-user" in detail


def test_font_install_ignores_unrelated_weights(tmp_path: Path) -> None:
    per_user = tmp_path / "user-fonts"
    system = tmp_path / "system-fonts"
    _write_fonts(per_user, ("PlusJakartaSans-Light.ttf", "PlusJakartaSans-Medium.ttf"))
    values = {
        "Plus Jakarta Sans Light (TrueType)": str(per_user / "PlusJakartaSans-Light.ttf"),
        "Plus Jakarta Sans Medium (TrueType)": str(per_user / "PlusJakartaSans-Medium.ttf"),
    }

    ok, detail = doctor.evaluate_font_install(
        per_user_dir=per_user,
        system_dir=system,
        registry_values=values,
        font_files=FONT_FILES,
    )

    assert ok is False
    assert "belum terpasang" in detail
    assert "0/4" not in detail


def test_font_install_reports_partial_install_with_command(tmp_path: Path) -> None:
    per_user = tmp_path / "user-fonts"
    system = tmp_path / "system-fonts"
    _write_fonts(per_user, (FONT_FILES[0],))

    ok, detail = doctor.evaluate_font_install(
        per_user_dir=per_user,
        system_dir=system,
        registry_values={},
        font_files=FONT_FILES,
    )

    assert ok is False
    assert "sebagian" in detail
    assert "python tools/install_fonts.py" in detail


def test_font_install_reports_missing_with_command(tmp_path: Path) -> None:
    ok, detail = doctor.evaluate_font_install(
        per_user_dir=tmp_path / "user-fonts",
        system_dir=tmp_path / "system-fonts",
        registry_values={},
        font_files=FONT_FILES,
    )

    assert ok is False
    assert "belum terpasang" in detail
    assert "python tools/install_fonts.py" in detail


def test_doctor_fonts_check_reports_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "_font_assets_status", lambda: (True, "aset font lengkap"))
    monkeypatch.setattr(
        doctor,
        "_font_install_status",
        lambda: (False, "belum terpasang; jalankan `python tools/install_fonts.py`"),
    )

    report = doctor.doctor_report(("pptx",))
    check = next(item for item in report.checks if item.name == "fonts")

    assert check.required is True
    assert check.ok is False
    assert "python tools/install_fonts.py" in check.detail
    assert report.ok is False


def test_doctor_fonts_check_accepts_installed_font(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "_font_assets_status", lambda: (True, "aset font lengkap"))
    monkeypatch.setattr(doctor, "_font_install_status", lambda: (True, "terpasang per-user"))

    report = doctor.doctor_report(("pptx",))
    check = next(item for item in report.checks if item.name == "fonts")

    assert check.ok is True
