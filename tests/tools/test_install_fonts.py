"""Tes installer font per-user tanpa menyentuh registry asli."""

from pathlib import Path

import pytest

from tools import install_fonts


class FakeRegistry:
    """Registry in-memory untuk memastikan test tidak menulis HKCU asli."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.set_calls: list[tuple[str, str]] = []

    def set_value(self, name: str, value: str) -> None:
        self.values[name] = value
        self.set_calls.append((name, value))

    def get_values(self) -> dict[str, str]:
        return dict(self.values)


def _source_dir(tmp_path: Path) -> Path:
    source = tmp_path / "bundled"
    source.mkdir()
    for index, file_name in enumerate(install_fonts.FONT_FILES):
        (source / file_name).write_bytes(f"font-{index}-{file_name}".encode())
    return source


def _local_app_data(tmp_path: Path) -> Path:
    return tmp_path / "Local"


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("PlusJakartaSans-Regular.ttf", "Plus Jakarta Sans (TrueType)"),
        ("PlusJakartaSans-SemiBold.ttf", "Plus Jakarta Sans SemiBold (TrueType)"),
        ("PlusJakartaSans-Bold.ttf", "Plus Jakarta Sans Bold (TrueType)"),
        ("PlusJakartaSans-ExtraBold.ttf", "Plus Jakarta Sans ExtraBold (TrueType)"),
    ],
)
def test_registry_value_name_uses_windows_convention(file_name: str, expected: str) -> None:
    assert install_fonts.registry_value_name(file_name) == expected


def test_registry_value_name_rejects_unknown_font() -> None:
    with pytest.raises(ValueError, match="tidak dikenal"):
        install_fonts.registry_value_name("PlusJakartaSans-Italic.ttf")


def test_paths_follow_local_app_data_layout(tmp_path: Path) -> None:
    local = _local_app_data(tmp_path)
    expected = local / "Microsoft" / "Windows" / "Fonts" / "PlusJakartaSans-Regular.ttf"

    assert install_fonts.per_user_fonts_dir(local) == local / "Microsoft" / "Windows" / "Fonts"
    assert install_fonts.installed_font_path(local, expected.name) == expected
    assert install_fonts.source_font_path(tmp_path / "bundled", expected.name) == (
        tmp_path / "bundled" / expected.name
    )


def test_install_copies_fonts_registers_values_and_broadcasts(tmp_path: Path) -> None:
    source = _source_dir(tmp_path)
    local = _local_app_data(tmp_path)
    registry = FakeRegistry()
    activated: list[Path] = []
    broadcasts: list[None] = []

    outcome = install_fonts.install_fonts(
        source_dir=source,
        local_app_data=local,
        registry=registry,
        activate=activated.append,
        broadcast=lambda: broadcasts.append(None),
        platform_name="win32",
    )

    target_dir = install_fonts.per_user_fonts_dir(local)
    assert outcome.copied == install_fonts.FONT_FILES
    assert outcome.unchanged == ()
    assert all((target_dir / name).is_file() for name in install_fonts.FONT_FILES)
    assert [path.name for path in activated] == list(install_fonts.FONT_FILES)
    assert broadcasts == [None]
    assert len(registry.set_calls) == len(install_fonts.FONT_FILES)
    assert registry.values["Plus Jakarta Sans (TrueType)"] == str(
        (target_dir / "PlusJakartaSans-Regular.ttf").resolve()
    )


def test_second_install_is_idempotent(tmp_path: Path) -> None:
    source = _source_dir(tmp_path)
    local = _local_app_data(tmp_path)
    first_registry = FakeRegistry()
    install_fonts.install_fonts(
        source_dir=source,
        local_app_data=local,
        registry=first_registry,
        activate=lambda _path: None,
        broadcast=lambda: None,
        platform_name="win32",
    )
    target_dir = install_fonts.per_user_fonts_dir(local)
    mtimes = {name: (target_dir / name).stat().st_mtime_ns for name in install_fonts.FONT_FILES}
    second_registry = FakeRegistry()

    outcome = install_fonts.install_fonts(
        source_dir=source,
        local_app_data=local,
        registry=second_registry,
        activate=lambda _path: None,
        broadcast=lambda: None,
        platform_name="win32",
    )

    assert outcome.copied == ()
    assert outcome.unchanged == install_fonts.FONT_FILES
    assert {name: (target_dir / name).stat().st_mtime_ns for name in install_fonts.FONT_FILES} == (
        mtimes
    )
    assert len(second_registry.set_calls) == len(install_fonts.FONT_FILES)


def test_mismatched_target_is_replaced(tmp_path: Path) -> None:
    source = _source_dir(tmp_path)
    local = _local_app_data(tmp_path)
    target_dir = install_fonts.per_user_fonts_dir(local)
    target_dir.mkdir(parents=True)
    target = target_dir / install_fonts.FONT_FILES[0]
    target.write_bytes(b"stale")

    outcome = install_fonts.install_fonts(
        source_dir=source,
        local_app_data=local,
        registry=FakeRegistry(),
        activate=lambda _path: None,
        broadcast=lambda: None,
        platform_name="win32",
    )

    assert install_fonts.FONT_FILES[0] in outcome.copied
    assert target.read_bytes() == (source / install_fonts.FONT_FILES[0]).read_bytes()


def test_non_windows_install_fails_without_writing(tmp_path: Path) -> None:
    source = _source_dir(tmp_path)
    local = _local_app_data(tmp_path)

    with pytest.raises(install_fonts.FontInstallError, match="Windows"):
        install_fonts.install_fonts(
            source_dir=source,
            local_app_data=local,
            registry=FakeRegistry(),
            activate=lambda _path: None,
            broadcast=lambda: None,
            platform_name="linux",
        )

    assert not install_fonts.per_user_fonts_dir(local).exists()


def test_missing_bundled_font_is_reported(tmp_path: Path) -> None:
    source = _source_dir(tmp_path)
    (source / install_fonts.FONT_FILES[0]).unlink()

    with pytest.raises(install_fonts.FontInstallError, match="tidak ditemukan"):
        install_fonts.build_install_plan(source, _local_app_data(tmp_path))


def test_dry_run_does_not_write_files_or_registry(tmp_path: Path) -> None:
    source = _source_dir(tmp_path)
    local = _local_app_data(tmp_path)
    registry = FakeRegistry()

    outcome = install_fonts.install_fonts(
        source_dir=source,
        local_app_data=local,
        registry=registry,
        activate=lambda _path: None,
        broadcast=lambda: None,
        platform_name="win32",
        dry_run=True,
    )

    assert outcome.copied == install_fonts.FONT_FILES
    assert not install_fonts.per_user_fonts_dir(local).exists()
    assert registry.set_calls == []


def test_font_statuses_report_installed_and_missing(tmp_path: Path) -> None:
    source = _source_dir(tmp_path)
    local = _local_app_data(tmp_path)
    target_dir = install_fonts.per_user_fonts_dir(local)
    target_dir.mkdir(parents=True)
    installed_name = install_fonts.FONT_FILES[0]
    (target_dir / installed_name).write_bytes((source / installed_name).read_bytes())
    registry = FakeRegistry({"Plus Jakarta Sans (TrueType)": str(target_dir / installed_name)})

    statuses = install_fonts.font_statuses(
        source_dir=source,
        local_app_data=local,
        registry=registry,
    )

    by_name = {status.file_name: status for status in statuses}
    assert by_name[installed_name].installed is True
    assert by_name[installed_name].hash_matches is True
    assert by_name[installed_name].registry_value is not None
    assert by_name[install_fonts.FONT_FILES[1]].installed is False
    assert by_name[install_fonts.FONT_FILES[1]].registry_value is None


def test_main_list_does_not_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _source_dir(tmp_path)
    local = _local_app_data(tmp_path)
    registry = FakeRegistry()
    monkeypatch.setattr(install_fonts, "SOURCE_FONT_DIR", source)
    monkeypatch.setattr(install_fonts, "_platform_name", lambda: "win32")
    monkeypatch.setattr(install_fonts, "_default_local_app_data", lambda: local)
    monkeypatch.setattr(install_fonts, "_default_registry", lambda: registry)
    monkeypatch.setattr(
        install_fonts,
        "_default_activate",
        lambda _path: pytest.fail("--list tidak boleh memuat font"),
    )
    monkeypatch.setattr(
        install_fonts,
        "_default_broadcast",
        lambda: pytest.fail("--list tidak boleh menyiarkan WM_FONTCHANGE"),
    )

    assert install_fonts.main(["--list"]) == 0
    output = capsys.readouterr().out
    assert "Plus Jakarta Sans: 4 TTF bundled" in output
    assert "belum terpasang" in output
    assert not install_fonts.per_user_fonts_dir(local).exists()
    assert registry.set_calls == []


def test_main_installs_with_injected_windows_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _source_dir(tmp_path)
    local = _local_app_data(tmp_path)
    registry = FakeRegistry()
    activated: list[Path] = []
    broadcasts: list[None] = []
    monkeypatch.setattr(install_fonts, "SOURCE_FONT_DIR", source)
    monkeypatch.setattr(install_fonts, "_platform_name", lambda: "win32")
    monkeypatch.setattr(install_fonts, "_default_local_app_data", lambda: local)
    monkeypatch.setattr(install_fonts, "_default_registry", lambda: registry)
    monkeypatch.setattr(install_fonts, "_default_activate", activated.append)
    monkeypatch.setattr(install_fonts, "_default_broadcast", lambda: broadcasts.append(None))

    assert install_fonts.main([]) == 0
    output = capsys.readouterr().out
    assert output.count("[COPY]") == len(install_fonts.FONT_FILES)
    assert "[OK]   4 disalin, 0 dilewati" in output
    assert len(activated) == len(install_fonts.FONT_FILES)
    assert broadcasts == [None]
    assert len(registry.values) == len(install_fonts.FONT_FILES)
