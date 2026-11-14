"""Tes identitas root workspace internal terhadap symlink dan junction."""

import os
from pathlib import Path

import pytest

from autooffice.cli import CliError
from autooffice.cli.outputs import (
    deck_outputs,
    docx_outputs,
    require_safe_build_directory,
)

_SENTINEL = "jangan hilang"
_OUTSIDE = "sentinel luar"


def _junction_or_skip(link: Path, target: Path) -> None:
    """Buat junction Windows atau lewati tes bila tidak tersedia."""

    if os.name != "nt":
        pytest.skip("junction hanya tersedia di Windows")
    try:
        import _winapi

        _winapi.CreateJunction(str(target.resolve()), str(link))
    except (AttributeError, ImportError, OSError) as exc:  # pragma: no cover - platform
        pytest.skip(f"junction tidak tersedia: {exc}")


def _dir_link_or_skip(link: Path, target: Path) -> None:
    """Buat junction di Windows, symlink direktori di platform lain."""

    if os.name == "nt":
        _junction_or_skip(link, target)
        return
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - izin symlink
        pytest.skip(f"symlink tidak tersedia: {exc}")


def _remove_dir_link(link: Path) -> None:
    if not link.exists() and not link.is_symlink():
        return
    try:
        link.unlink()
    except OSError:  # pragma: no cover - junction Windows lama
        link.rmdir()


def _source_with_sentinel(tmp_path: Path, name: str = "document.md") -> tuple[Path, Path]:
    document = tmp_path / "document"
    document.mkdir()
    source = document / name
    source.write_text("sumber", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text(_OUTSIDE, encoding="utf-8")
    return source, outside


def _target_with_sentinel(document: Path, target_name: str) -> tuple[Path, Path]:
    if target_name == ".":
        target = document
    else:
        target = document / target_name
        target.mkdir()
    sentinel = target / "sentinel.txt"
    sentinel.write_text(_SENTINEL, encoding="utf-8")
    return target, sentinel


@pytest.mark.parametrize("target_name", [".git", "assets", "."])
def test_docx_outputs_rejects_report_build_link_to_internal_target(
    tmp_path: Path,
    target_name: str,
) -> None:
    source, outside = _source_with_sentinel(tmp_path)
    target, sentinel = _target_with_sentinel(source.parent, target_name)
    link = source.parent / ".laporan-build"
    _dir_link_or_skip(link, target)
    try:
        with pytest.raises(CliError) as error:
            docx_outputs(source, "Laporan")

        assert error.value.code == "CLI-BUILD-PATH"
        assert source.read_text(encoding="utf-8") == "sumber"
        assert outside.read_text(encoding="utf-8") == _OUTSIDE
        assert sentinel.read_text(encoding="utf-8") == _SENTINEL
    finally:
        _remove_dir_link(link)


@pytest.mark.parametrize("target_name", [".git", "."])
def test_deck_outputs_rejects_autooffice_build_link_to_internal_target(
    tmp_path: Path,
    target_name: str,
) -> None:
    source, outside = _source_with_sentinel(tmp_path, "deck.yaml")
    target, sentinel = _target_with_sentinel(source.parent, target_name)
    link = source.parent / ".autooffice-build"
    _dir_link_or_skip(link, target)
    try:
        with pytest.raises(CliError) as error:
            deck_outputs(source)

        assert error.value.code == "CLI-BUILD-PATH"
        assert source.read_text(encoding="utf-8") == "sumber"
        assert outside.read_text(encoding="utf-8") == _OUTSIDE
        assert sentinel.read_text(encoding="utf-8") == _SENTINEL
    finally:
        _remove_dir_link(link)


def test_deck_outputs_rejects_per_stem_link_to_internal_target(tmp_path: Path) -> None:
    source, outside = _source_with_sentinel(tmp_path, "deck.yaml")
    document = source.parent
    target, sentinel = _target_with_sentinel(document, ".git")
    build_root = document / ".autooffice-build"
    build_root.mkdir()
    link = build_root / "deck"
    _dir_link_or_skip(link, target)
    try:
        with pytest.raises(CliError) as error:
            deck_outputs(source)

        assert error.value.code == "CLI-BUILD-PATH"
        assert source.read_text(encoding="utf-8") == "sumber"
        assert outside.read_text(encoding="utf-8") == _OUTSIDE
        assert sentinel.read_text(encoding="utf-8") == _SENTINEL
    finally:
        _remove_dir_link(link)


@pytest.mark.parametrize("target_name", [".git", "."])
def test_deck_outputs_rejects_state_root_link_to_internal_target(
    tmp_path: Path,
    target_name: str,
) -> None:
    source, outside = _source_with_sentinel(tmp_path, "deck.yaml")
    target, sentinel = _target_with_sentinel(source.parent, target_name)
    link = source.parent / ".autooffice"
    _dir_link_or_skip(link, target)
    try:
        with pytest.raises(CliError) as error:
            deck_outputs(source)

        assert error.value.code == "CLI-STATE-PATH"
        assert source.read_text(encoding="utf-8") == "sumber"
        assert outside.read_text(encoding="utf-8") == _OUTSIDE
        assert sentinel.read_text(encoding="utf-8") == _SENTINEL
    finally:
        _remove_dir_link(link)


@pytest.mark.parametrize("child", ["state", "cache", "review"])
def test_deck_outputs_rejects_state_child_link_to_git(tmp_path: Path, child: str) -> None:
    source, outside = _source_with_sentinel(tmp_path, "deck.yaml")
    document = source.parent
    state_root = document / ".autooffice"
    state_root.mkdir()
    target, sentinel = _target_with_sentinel(document, ".git")
    link = state_root / child
    _dir_link_or_skip(link, target)
    try:
        with pytest.raises(CliError) as error:
            deck_outputs(source)

        assert error.value.code == "CLI-STATE-PATH"
        assert source.read_text(encoding="utf-8") == "sumber"
        assert outside.read_text(encoding="utf-8") == _OUTSIDE
        assert sentinel.read_text(encoding="utf-8") == _SENTINEL
    finally:
        _remove_dir_link(link)


def test_normal_internal_workspace_directories_are_accepted(tmp_path: Path) -> None:
    source, _ = _source_with_sentinel(tmp_path, "deck.yaml")
    document = source.parent
    (document / ".laporan-build").mkdir()
    (document / ".autooffice-build" / "deck").mkdir(parents=True)
    (document / ".autooffice" / "state").mkdir(parents=True)
    markdown = document / "document.md"
    markdown.write_text("sumber", encoding="utf-8")

    assert docx_outputs(markdown, "Laporan").build_dir == document / ".laporan-build"
    assert deck_outputs(source).build_dir == document / ".autooffice-build" / "deck"


def test_require_safe_build_directory_revalidates_replaced_report_root(
    tmp_path: Path,
) -> None:
    source, _ = _source_with_sentinel(tmp_path)
    document = source.parent
    outputs = docx_outputs(source, "Laporan")
    target, sentinel = _target_with_sentinel(document, ".git")
    link = document / ".laporan-build"
    _dir_link_or_skip(link, target)
    try:
        with pytest.raises(CliError) as error:
            require_safe_build_directory(
                source,
                outputs.build_dir,
                ".laporan-build",
                per_stem=False,
            )

        assert error.value.code == "CLI-BUILD-PATH"
        assert sentinel.read_text(encoding="utf-8") == _SENTINEL
    finally:
        _remove_dir_link(link)


def test_require_safe_build_directory_revalidates_replaced_stem_link(
    tmp_path: Path,
) -> None:
    source, _ = _source_with_sentinel(tmp_path, "deck.yaml")
    document = source.parent
    build_dir = document / ".autooffice-build" / "deck"
    build_dir.mkdir(parents=True)
    outputs = deck_outputs(source)
    build_dir.rmdir()
    target, sentinel = _target_with_sentinel(document, ".git")
    _dir_link_or_skip(build_dir, target)
    try:
        with pytest.raises(CliError) as error:
            require_safe_build_directory(source, outputs.build_dir, ".autooffice-build")

        assert error.value.code == "CLI-BUILD-PATH"
        assert sentinel.read_text(encoding="utf-8") == _SENTINEL
    finally:
        _remove_dir_link(build_dir)


@pytest.mark.skipif(os.name != "nt", reason="junction hanya tersedia di Windows")
def test_windows_junction_report_build_to_git_is_rejected(tmp_path: Path) -> None:
    source, outside = _source_with_sentinel(tmp_path)
    document = source.parent
    target = document / ".git"
    target.mkdir()
    sentinel = target / "config"
    sentinel.write_text(_SENTINEL, encoding="utf-8")
    link = document / ".laporan-build"
    _junction_or_skip(link, target)
    try:
        assert link.is_junction()
        with pytest.raises(CliError) as error:
            docx_outputs(source, "Laporan")

        assert error.value.code == "CLI-BUILD-PATH"
        assert source.is_file()
        assert outside.read_text(encoding="utf-8") == _OUTSIDE
        assert sentinel.read_text(encoding="utf-8") == _SENTINEL
    finally:
        _remove_dir_link(link)
