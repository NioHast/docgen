"""Tes doctor tanpa jaringan: tool, COM, font, target, dan format laporan."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import autooffice.google
from autooffice.cli import doctor
from autooffice.design import fonts


def _patch_offline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tools: dict[str, str] | None = None,
    com: bool | dict[str, bool] = False,
    pywin32_status: tuple[bool, str] = (True, "pywin32 siap"),
    font_assets_status: tuple[bool, str] = (True, "aset font siap"),
    font_install_status: tuple[bool, str] = (True, "font siap"),
    google_status: tuple[bool, str] | None = (True, "google siap"),
) -> None:
    available = tools or {}

    def com_registered(program_id: str) -> bool:
        return com.get(program_id, False) if isinstance(com, dict) else com

    monkeypatch.setattr(doctor, "_find_tool", lambda name: available.get(name))
    monkeypatch.setattr(
        doctor,
        "_tool_version",
        lambda command: f"{command} 1.0" if command else None,
    )
    monkeypatch.setattr(doctor, "_com_registered", com_registered)
    monkeypatch.setattr(doctor, "_pywin32_status", lambda: pywin32_status)
    monkeypatch.setattr(doctor, "_font_assets_status", lambda: font_assets_status)
    monkeypatch.setattr(doctor, "_font_install_status", lambda: font_install_status)
    if google_status is not None:
        monkeypatch.setattr(doctor, "_google_status", lambda: google_status)
    monkeypatch.setattr(doctor.os, "access", lambda *_args: True)


@pytest.mark.parametrize(
    ("targets", "required"),
    [
        (None, {"python", "workspace", "pandoc", "font-assets", "fonts"}),
        (("docx",), {"python", "workspace", "pandoc"}),
        (
            ("pptx",),
            {"python", "workspace", "powerpoint", "pywin32", "fonts"},
        ),
        (("pdf",), {"python", "workspace"}),
        (("slides",), {"python", "workspace", "font-assets", "google"}),
        (
            ("pptx", "pdf"),
            {"python", "workspace", "powerpoint", "pywin32", "fonts"},
        ),
        (("docx", "pdf"), {"python", "workspace", "pandoc", "word"}),
        (
            ("docx", "pptx", "pdf", "slides"),
            {
                "python",
                "workspace",
                "pandoc",
                "powerpoint",
                "word",
                "pywin32",
                "font-assets",
                "fonts",
                "google",
            },
        ),
    ],
)
def test_doctor_required_checks_follow_targets(
    monkeypatch: pytest.MonkeyPatch,
    targets: tuple[str, ...] | None,
    required: set[str],
) -> None:
    _patch_offline(monkeypatch, tools={"pandoc": "pandoc", "mmdc": "mmdc"}, com=True)

    report = doctor.doctor_report(targets)

    assert {check.name for check in report.checks if check.required} == required
    assert report.ok is True
    assert report.targets == targets


def test_doctor_pdf_target_requires_powerpoint_for_deck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(
        monkeypatch,
        tools={"pandoc": "pandoc"},
        com={"Word.Application": True, "PowerPoint.Application": False},
    )

    assert doctor.doctor_report(("pptx", "pdf")).ok is False
    assert doctor.doctor_report(("docx", "pdf")).ok is True


def test_doctor_slides_requires_font_assets_but_not_installed_fonts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(
        monkeypatch,
        com=False,
        font_assets_status=(True, "aset font siap"),
        font_install_status=(False, "font belum terpasang"),
    )

    report = doctor.doctor_report(("slides",))

    assert report.ok is True
    assert next(check for check in report.checks if check.name == "fonts").required is False
    assert next(check for check in report.checks if check.name == "font-assets").required is True


def test_doctor_slides_fails_without_google_oauth_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(
        monkeypatch,
        google_status=(False, "kredensial Google belum siap: token hilang"),
    )

    report = doctor.doctor_report(("slides",))

    assert report.ok is False
    google = next(check for check in report.checks if check.name == "google")
    assert google.required is True
    assert google.ok is False
    assert "token" in google.detail


def test_doctor_pdf_target_requires_word_or_powerpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(monkeypatch, tools={"pandoc": "pandoc"}, com=False)
    without_office = doctor.doctor_report(("pdf",))

    _patch_offline(
        monkeypatch,
        tools={"pandoc": "pandoc"},
        com={"Word.Application": False, "PowerPoint.Application": True},
    )
    with_powerpoint = doctor.doctor_report(("pdf",))

    _patch_offline(
        monkeypatch,
        tools={"pandoc": "pandoc"},
        com={"Word.Application": True, "PowerPoint.Application": False},
    )
    with_word = doctor.doctor_report(("pdf",))

    assert without_office.ok is False
    assert with_powerpoint.ok is True
    assert with_word.ok is True


def test_doctor_report_fails_on_missing_required_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(monkeypatch, tools={}, com=True)

    report = doctor.doctor_report(None)

    assert report.ok is False
    pandoc = next(check for check in report.checks if check.name == "pandoc")
    assert pandoc.ok is False
    assert pandoc.required is True
    assert "tidak ditemukan" in pandoc.detail


def test_render_doctor_human_output_success(capsys: pytest.CaptureFixture[str]) -> None:
    report = doctor.DoctorReport(
        checks=(doctor.DoctorCheck("python", True, True, "3.15.2"),),
        targets=None,
        ok=True,
    )

    assert doctor.render_doctor(report, json_output=False) == 0
    output = capsys.readouterr().out
    assert "[OK] python" in output
    assert "wajib" in output
    assert "Kesimpulan: dependency wajib untuk target yang diminta tersedia." in output


def test_render_doctor_human_output_failure(capsys: pytest.CaptureFixture[str]) -> None:
    report = doctor.DoctorReport(
        checks=(doctor.DoctorCheck("pandoc", False, True, "tidak ditemukan"),),
        targets=None,
        ok=False,
    )

    assert doctor.render_doctor(report, json_output=False) == 1
    output = capsys.readouterr().out
    assert "[--] pandoc" in output
    assert "wajib" in output
    assert "dependency wajib belum lengkap" in output


def test_find_tool_non_windows_uses_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert doctor._find_tool("pandoc") == "/usr/bin/pandoc"


def test_find_tool_windows_prefers_localappdata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "local" / "Pandoc" / "pandoc.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program"))

    assert doctor._find_tool("pandoc") == str(executable)


def test_find_tool_windows_prefers_program_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "program" / "Pandoc" / "pandoc.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program"))

    assert doctor._find_tool("pandoc") == str(executable)


def test_find_tool_windows_falls_back_to_which(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program"))
    monkeypatch.setattr(
        doctor.shutil,
        "which",
        lambda name: "C:/tools/pandoc.exe" if name == "pandoc.exe" else None,
    )

    assert doctor._find_tool("pandoc") == "C:/tools/pandoc.exe"


def test_find_tool_windows_without_env_paths_uses_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "pandoc" if name == "pandoc" else None)

    assert doctor._find_tool("pandoc") == "pandoc"


def test_find_tool_windows_non_pandoc_uses_which(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program"))
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "mmdc" if name == "mmdc" else None)

    assert doctor._find_tool("mmdc") == "mmdc"


def test_tool_version_none_command_returns_none() -> None:
    assert doctor._tool_version(None) is None


def test_tool_version_handles_subprocess_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("executable hilang")

    monkeypatch.setattr(doctor.subprocess, "run", fail)

    assert doctor._tool_version("pandoc") is None


def test_com_registered_false_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "linux")

    assert doctor._com_registered("Word.Application") is False


def test_com_registered_false_without_winreg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "win32")

    def fail_import(_name: str) -> None:
        raise ImportError("winreg tidak tersedia")

    monkeypatch.setattr(doctor.importlib, "import_module", fail_import)

    assert doctor._com_registered("Word.Application") is False


def test_com_registered_false_when_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "win32")

    def fail_open(*_args: object, **_kwargs: object) -> None:
        raise OSError("key tidak ada")

    fake_winreg = SimpleNamespace(HKEY_CLASSES_ROOT=object(), OpenKey=fail_open)
    monkeypatch.setattr(doctor.importlib, "import_module", lambda _name: fake_winreg)

    assert doctor._com_registered("Word.Application") is False


def test_com_registered_true_when_key_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Key:
        def __enter__(self) -> _Key:
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

    monkeypatch.setattr(doctor.sys, "platform", "win32")
    fake_winreg = SimpleNamespace(
        HKEY_CLASSES_ROOT=object(),
        OpenKey=lambda _root, _name: _Key(),
    )
    monkeypatch.setattr(doctor.importlib, "import_module", lambda _name: fake_winreg)

    assert doctor._com_registered("Word.Application") is True


def test_office_detail_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "linux")

    detail = doctor._office_detail(False, "Microsoft Word", "Word.Application")

    assert "tidak berlaku" in detail
    assert "Microsoft Word" in detail


def test_office_detail_reports_missing_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "win32")

    detail = doctor._office_detail(False, "Microsoft PowerPoint", "PowerPoint.Application")

    assert "tidak terdaftar" in detail
    assert "Microsoft PowerPoint" in detail


def test_font_assets_status_reports_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "ASSET_HASHES", {"hilang.ttf": "hash"})

    ok, detail = doctor._font_assets_status()

    assert ok is False
    assert "aset font hilang" in detail
    assert "hilang.ttf" in detail


def test_font_assets_status_reports_unreadable_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "rusak.ttf").write_bytes(b"font")
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "ASSET_HASHES", {"rusak.ttf": "hash"})

    def fail_sha(_path: Path) -> str:
        raise OSError("tidak dapat dibaca")

    monkeypatch.setattr(fonts, "sha256", fail_sha)

    ok, detail = doctor._font_assets_status()

    assert ok is False
    assert "aset font hilang" in detail


def test_font_assets_status_reports_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "beda.ttf").write_bytes(b"font")
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "ASSET_HASHES", {"beda.ttf": "hash-asli"})
    monkeypatch.setattr(fonts, "sha256", lambda _path: "hash-lain")

    ok, detail = doctor._font_assets_status()

    assert ok is False
    assert "hash font tidak cocok" in detail
    assert "beda.ttf" in detail


def test_font_assets_status_accepts_matching_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "baik.ttf").write_bytes(b"font")
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    monkeypatch.setattr(fonts, "ASSET_HASHES", {"baik.ttf": "hash"})
    monkeypatch.setattr(fonts, "FONT_FILES", ("baik.ttf",))
    monkeypatch.setattr(fonts, "sha256", lambda _path: "hash")

    ok, detail = doctor._font_assets_status()

    assert ok is True
    assert "1 TTF + lisensi" in detail
    assert str(tmp_path) in detail


def test_font_install_status_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "linux")

    assert doctor._font_install_status() == (
        True,
        "tidak berlaku; instalasi font per-user hanya Windows",
    )


def test_font_install_status_requires_localappdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    ok, detail = doctor._font_install_status()

    assert ok is False
    assert "LOCALAPPDATA" in detail


def test_font_install_status_uses_environment_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("WINDIR", str(tmp_path / "windows"))
    monkeypatch.setattr(doctor, "_read_font_registry_values", lambda: {"PJS": "pjs.ttf"})
    captured: dict[str, object] = {}

    def fake_evaluate(
        *,
        per_user_dir: Path,
        system_dir: Path,
        registry_values: dict[str, str],
        font_files: tuple[str, ...],
    ) -> tuple[bool, str]:
        captured.update(
            {
                "per_user_dir": per_user_dir,
                "system_dir": system_dir,
                "registry_values": registry_values,
                "font_files": font_files,
            }
        )
        return True, "font terpasang"

    monkeypatch.setattr(doctor, "evaluate_font_install", fake_evaluate)

    assert doctor._font_install_status() == (True, "font terpasang")
    assert captured["per_user_dir"] == tmp_path / "local" / "Microsoft" / "Windows" / "Fonts"
    assert captured["system_dir"] == tmp_path / "windows" / "Fonts"
    assert captured["registry_values"] == {"PJS": "pjs.ttf"}
    assert captured["font_files"] == fonts.FONT_FILES


def test_font_file_present_false_when_stat_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "font.ttf"
    real_is_file = Path.is_file
    real_stat = Path.stat

    def is_file(self: Path) -> bool:
        if self.name == "font.ttf":
            return True
        return real_is_file(self)

    def stat(self: Path, *args: object, **kwargs: object) -> object:
        if self.name == "font.ttf":
            raise OSError("stat gagal")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", is_file)
    monkeypatch.setattr(Path, "stat", stat)

    assert doctor._font_file_present(path) is False


def test_matching_registry_paths_resolves_relative_value(
    tmp_path: Path,
) -> None:
    system_dir = tmp_path / "Fonts"
    system_dir.mkdir()
    (system_dir / "pjs.ttf").write_bytes(b"font")

    paths = doctor._matching_registry_paths(
        {
            "Plus Jakarta Sans (TrueType)": "pjs.ttf",
            "Plus Jakarta Sans Ghost (TrueType)": "ghost.ttf",
            "Arial (TrueType)": "arial.ttf",
        },
        system_dir,
    )

    assert paths == [system_dir / "pjs.ttf"]


def test_font_registry_values_empty_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "linux")

    assert doctor._read_font_registry_values() == {}


def test_font_registry_values_empty_without_winreg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.sys, "platform", "win32")

    def fail_import(_name: str) -> None:
        raise ImportError("winreg tidak tersedia")

    monkeypatch.setattr(doctor.importlib, "import_module", fail_import)

    assert doctor._read_font_registry_values() == {}


def test_font_registry_values_read_string_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Key:
        def __enter__(self) -> _Key:
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

    entries = [
        ("Plus Jakarta Sans (TrueType)", "pjs.ttf", 1),
        ("Arial (TrueType)", "arial.ttf", 3),
    ]
    fake_winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        REG_SZ=1,
        OpenKey=lambda _root, _path: _Key(),
        QueryInfoKey=lambda _key: (0, len(entries), 0),
        EnumValue=lambda _key, index: entries[index],
    )
    monkeypatch.setattr(doctor.sys, "platform", "win32")
    monkeypatch.setattr(doctor.importlib, "import_module", lambda _name: fake_winreg)

    assert doctor._read_font_registry_values() == {
        "Plus Jakarta Sans (TrueType)": "pjs.ttf",
    }


def test_font_registry_values_empty_when_key_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_open(*_args: object, **_kwargs: object) -> None:
        raise OSError("key tidak ada")

    fake_winreg = SimpleNamespace(HKEY_CURRENT_USER=object(), REG_SZ=1, OpenKey=fail_open)
    monkeypatch.setattr(doctor.sys, "platform", "win32")
    monkeypatch.setattr(doctor.importlib, "import_module", lambda _name: fake_winreg)

    assert doctor._read_font_registry_values() == {}


@pytest.mark.parametrize("error_type", [ModuleNotFoundError, ValueError])
def test_google_status_handles_unavailable_parent_spec(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    def fail_find_spec(_name: str) -> None:
        raise error_type("google tidak tersedia")

    monkeypatch.setattr(doctor.importlib.util, "find_spec", fail_find_spec)

    assert doctor._google_status() == (False, "google extra tidak terpasang")


def test_google_status_reports_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        doctor.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(name=name) if name == "google" else None,
    )

    ok, detail = doctor._google_status()

    assert ok is False
    assert "googleapiclient" in detail


def test_doctor_report_survives_google_auth_find_spec_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_offline(
        monkeypatch,
        tools={"pandoc": "pandoc"},
        com=True,
        google_status=None,
    )

    def fail_google_auth(name: str) -> SimpleNamespace:
        if name == "google.auth":
            raise ModuleNotFoundError("No module named 'google'")
        return SimpleNamespace(name=name)

    monkeypatch.setattr(doctor.importlib.util, "find_spec", fail_google_auth)

    report = doctor.doctor_report(("docx",))

    google = next(check for check in report.checks if check.name == "google")
    names = {check.name for check in report.checks}
    assert google.ok is False
    assert "google.auth" in google.detail
    assert {"pandoc", "mmdc", "word", "powerpoint", "fonts"} <= names
    assert report.ok is True


def test_google_status_accepts_installed_extra_and_local_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import autooffice.google

    class _Settings:
        @classmethod
        def from_environment(cls) -> _Settings:
            return cls()

    class _Tokens:
        @classmethod
        def from_environment(cls) -> _Tokens:
            return cls()

        def require(self) -> dict[str, object]:
            return {"access_token": "token"}

    monkeypatch.setattr(
        doctor.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(name=name),
    )
    monkeypatch.setattr(autooffice.google, "OAuthSettings", _Settings, raising=False)
    monkeypatch.setattr(autooffice.google, "TokenStore", _Tokens, raising=False)

    ok, detail = doctor._google_status()

    assert ok is True
    assert "tanpa jaringan" in detail


def test_google_status_reports_missing_oauth_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import autooffice.google

    class _Settings:
        @classmethod
        def from_environment(cls) -> _Settings:
            raise autooffice.google.GoogleAuthError("GOOGLE_CLIENT_ID kosong")

    monkeypatch.setattr(
        doctor.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(name=name),
    )
    monkeypatch.setattr(autooffice.google, "OAuthSettings", _Settings, raising=False)

    ok, detail = doctor._google_status()

    assert ok is False
    assert "kredensial Google" in detail
    assert "GOOGLE_CLIENT_ID" in detail


@pytest.mark.parametrize(
    ("error_type", "message"),
    [
        (autooffice.google.GoogleAuthError, "token hilang"),
        (OSError, "token tidak dapat dibaca"),
    ],
    ids=["google-auth-error", "os-error"],
)
def test_google_status_reports_token_store_failure(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
    message: str,
) -> None:
    calls: list[str] = []

    class _Settings:
        @classmethod
        def from_environment(cls) -> _Settings:
            return cls()

    class _Tokens:
        @classmethod
        def from_environment(cls) -> _Tokens:
            calls.append("from_environment")
            return cls()

        def require(self) -> dict[str, object]:
            calls.append("require")
            raise error_type(message)

    monkeypatch.setattr(
        doctor.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(name=name),
    )
    monkeypatch.setattr(autooffice.google, "OAuthSettings", _Settings, raising=False)
    monkeypatch.setattr(autooffice.google, "TokenStore", _Tokens, raising=False)

    ok, detail = doctor._google_status()

    assert ok is False
    assert "kredensial Google" in detail
    assert message in detail
    assert calls == ["from_environment", "require"]
