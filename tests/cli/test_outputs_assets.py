"""Tes aset deck, penamaan output, dan kegagalan tulis atomik CLI."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from autooffice.cli import CliError
from autooffice.cli.outputs import (
    AssetReference,
    atomic_copy,
    atomic_write_bytes,
    atomic_write_text,
    deck_asset_references,
    deck_outputs,
    docx_outputs,
    ensure_directory,
    missing_deck_assets,
    planned_deck_files,
    planned_docx_files,
    stage_deck_assets,
)


def _symlink_dir_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - izin symlink Windows
        pytest.skip(f"symlink tidak tersedia: {exc}")


def _deck_with_images(*paths: str) -> SimpleNamespace:
    blocks = tuple(
        SimpleNamespace(
            block_id=f"image{index}",
            block_type="image",
            fields={"path": path},
        )
        for index, path in enumerate(paths)
    )
    return SimpleNamespace(slides=(SimpleNamespace(slide_id="s04", blocks=blocks),))


def test_deck_outputs_rejects_source_without_stem() -> None:
    with pytest.raises(CliError, match="tidak memiliki stem") as error:
        deck_outputs(Path("."))

    assert error.value.code == "CLI-INPUT-NAME"
    assert error.value.exit_code == 2


def test_planned_docx_files_pdf_only_omits_docx(tmp_path: Path) -> None:
    outputs = docx_outputs(tmp_path / "document.md", "Tugas")

    assert planned_docx_files(outputs, ("pdf",), terms=False) == (
        outputs.pdf,
        outputs.manifest,
    )


def test_deck_asset_references_skip_blocks_without_string_fields() -> None:
    deck = SimpleNamespace(
        slides=(
            SimpleNamespace(
                slide_id="s04",
                blocks=(
                    SimpleNamespace(
                        block_id="image0",
                        block_type="image",
                        fields={"path": "assets/hero.png"},
                    ),
                    SimpleNamespace(
                        block_id="image1",
                        block_type="image",
                        fields=[("path", "assets/lain.png")],
                    ),
                    SimpleNamespace(
                        block_id="image2",
                        block_type="image",
                        fields={"path": 7},
                    ),
                    SimpleNamespace(
                        block_id="chart1",
                        block_type="chart",
                        fields={"path": "assets/hero.png"},
                    ),
                    SimpleNamespace(block_id="title", block_type="text", fields={}),
                ),
            ),
        )
    )

    references = deck_asset_references(deck)

    assert references == (
        AssetReference(
            relative_path="assets/hero.png",
            slide_id="s04",
            block_id="image0",
            block_type="image",
        ),
    )
    assert references[0].key == "s04.image0"


@pytest.mark.parametrize(
    ("relative_path", "reason"),
    [
        ("../escape.png", "path aset keluar dari direktori deck"),
        ("/absolute.png", "path aset keluar dari direktori deck"),
        (".", "path aset keluar dari direktori deck"),
        ("./hero.png", "aset tidak ditemukan"),
    ],
)
def test_missing_deck_assets_rejects_paths_outside_deck(
    tmp_path: Path,
    relative_path: str,
    reason: str,
) -> None:
    deck = _deck_with_images(relative_path)

    missing = missing_deck_assets(deck, tmp_path)

    assert len(missing) == 1
    assert missing[0].reason == reason
    formatted = missing[0].format()
    assert "slide 's04'" in formatted
    assert "block 'image0'" in formatted
    assert relative_path in formatted


def test_missing_deck_assets_reports_unresolvable_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deck = _deck_with_images("boom.png")
    real_resolve = Path.resolve

    def resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "boom.png":
            raise OSError("tidak dapat resolve")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)

    missing = missing_deck_assets(deck, tmp_path)

    assert len(missing) == 1
    assert missing[0].reason == "path aset tidak dapat di-resolve"
    assert missing[0].absolute_path == (tmp_path / "boom.png").absolute()


def test_missing_deck_assets_reports_resolved_path_outside_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deck = _deck_with_images("escape.png")
    outside = tmp_path.parent / "outside.png"
    real_resolve = Path.resolve

    def resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self.name == "escape.png":
            return outside
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)

    missing = missing_deck_assets(deck, tmp_path)

    assert len(missing) == 1
    assert missing[0].reason == "path aset keluar dari direktori deck"
    assert missing[0].absolute_path == outside


def test_stage_deck_assets_rejects_missing_asset_before_workspace(
    tmp_path: Path,
) -> None:
    deck = _deck_with_images("assets/missing.png")
    workspace = tmp_path / "workspace"

    with pytest.raises(CliError, match=r"assets/missing\.png") as error:
        stage_deck_assets(tmp_path / "deck.yaml", deck, workspace)

    assert error.value.code == "CLI-ASSET"
    assert not workspace.exists()


def test_stage_deck_assets_copies_referenced_file_outside_standard_roots(
    tmp_path: Path,
) -> None:
    deck_root = tmp_path / "deck"
    (deck_root / "img").mkdir(parents=True)
    (deck_root / "img" / "hero.png").write_bytes(b"hero-bytes")
    deck = _deck_with_images("img/hero.png")
    workspace = tmp_path / "workspace"

    staged = stage_deck_assets(deck_root / "deck.yaml", deck, workspace)

    destination = workspace / "img" / "hero.png"
    assert destination.read_bytes() == b"hero-bytes"
    assert destination in staged
    assert not (workspace / "assets").exists()


def test_stage_deck_assets_rejects_destination_that_is_a_file(tmp_path: Path) -> None:
    deck_root = tmp_path / "deck"
    (deck_root / "assets").mkdir(parents=True)
    (deck_root / "assets" / "hero.png").write_bytes(b"hero")
    deck = _deck_with_images("assets/hero.png")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "assets").write_text("bukan direktori", encoding="utf-8")

    with pytest.raises(CliError, match="tujuan bukan direktori") as error:
        stage_deck_assets(deck_root / "deck.yaml", deck, workspace)

    assert error.value.code == "CLI-ASSET-STAGE"


def test_stage_deck_assets_wraps_copytree_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deck_root = tmp_path / "deck"
    (deck_root / "assets").mkdir(parents=True)
    deck = SimpleNamespace(slides=())

    def fail_copytree(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk penuh")

    monkeypatch.setattr("autooffice.cli.outputs.shutil.copytree", fail_copytree)

    with pytest.raises(CliError, match="pohon aset") as error:
        stage_deck_assets(deck_root / "deck.yaml", deck, tmp_path / "workspace")

    assert error.value.code == "CLI-ASSET-STAGE"


def test_stage_deck_assets_wraps_copy_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deck_root = tmp_path / "deck"
    (deck_root / "img").mkdir(parents=True)
    (deck_root / "img" / "hero.png").write_bytes(b"hero")
    deck = _deck_with_images("img/hero.png")

    def fail_copy(*_args: object, **_kwargs: object) -> None:
        raise OSError("akses ditolak")

    monkeypatch.setattr("autooffice.cli.outputs.shutil.copy2", fail_copy)

    with pytest.raises(CliError, match="tidak dapat disalin") as error:
        stage_deck_assets(deck_root / "deck.yaml", deck, tmp_path / "workspace")

    assert error.value.code == "CLI-ASSET-STAGE"


def test_ensure_directory_wraps_mkdir_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")

    with pytest.raises(CliError, match="tidak dapat dibuat") as error:
        ensure_directory(blocker / "sub")

    assert error.value.code == "CLI-OUT-CREATE"
    assert error.value.exit_code == 2


def test_ensure_directory_rejects_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "file"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(Path, "mkdir", lambda self, *args, **kwargs: None)

    with pytest.raises(CliError, match="bukan direktori") as error:
        ensure_directory(target)

    assert error.value.code == "CLI-OUT-NOT-DIR"


def test_atomic_write_cleans_temporary_file_on_replace_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "out.txt"

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk penuh")

    monkeypatch.setattr("autooffice.cli.outputs.os.replace", fail_replace)

    with pytest.raises(CliError, match="tidak dapat ditulis") as error:
        atomic_write_text(target, "isi")

    assert error.value.code == "CLI-OUT-WRITE"
    assert error.value.exit_code == 1
    assert not target.exists()
    assert list(tmp_path.glob(".out.txt.*.tmp")) == []


def test_atomic_copy_reports_unreadable_source(tmp_path: Path) -> None:
    destination = tmp_path / "copy.txt"

    with pytest.raises(CliError, match="tidak dapat disalin") as error:
        atomic_copy(tmp_path / "missing.txt", destination)

    assert error.value.code == "CLI-OUT-COPY"
    assert not destination.exists()


def test_atomic_write_and_copy_report_temporary_file_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "out.txt"
    source = tmp_path / "source.txt"
    source.write_text("isi", encoding="utf-8")

    def fail_temporary(*_args: object, **_kwargs: object) -> None:
        raise OSError("tidak dapat membuat file sementara")

    monkeypatch.setattr("autooffice.cli.outputs.tempfile.NamedTemporaryFile", fail_temporary)

    with pytest.raises(CliError, match="tidak dapat ditulis") as write_error:
        atomic_write_text(target, "isi")

    with pytest.raises(CliError, match="tidak dapat disalin") as copy_error:
        atomic_copy(source, target)

    assert write_error.value.code == "CLI-OUT-WRITE"
    assert copy_error.value.code == "CLI-OUT-COPY"
    assert not target.exists()


def test_planned_deck_files_deduplicate_shared_paths(tmp_path: Path) -> None:
    outputs = deck_outputs(tmp_path / "deck.yaml")
    duplicated = replace(outputs, pptx=outputs.pdf)

    assert planned_deck_files(duplicated, ("pptx", "pdf")) == (outputs.pdf,)


def test_deck_outputs_rejects_state_symlink_outside_deck(
    tmp_path: Path,
) -> None:
    deck_root = tmp_path / "deck"
    deck_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_dir_or_skip(deck_root / ".autooffice", outside)

    source = deck_root / "deck.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")

    with pytest.raises(CliError, match="keluar dari direktori deck") as error:
        deck_outputs(source)

    assert error.value.code == "CLI-STATE-PATH"
    assert list(outside.iterdir()) == []


def test_deck_outputs_rejects_cache_subdir_symlink_outside_deck(
    tmp_path: Path,
) -> None:
    deck_root = tmp_path / "deck"
    deck_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    cache_root = deck_root / ".autooffice" / "cache"
    cache_root.mkdir(parents=True)
    _symlink_dir_or_skip(cache_root / "mermaid", outside)

    source = deck_root / "deck.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")

    with pytest.raises(CliError, match="keluar dari direktori deck") as error:
        deck_outputs(source)

    assert error.value.code == "CLI-STATE-PATH"
    assert list(outside.iterdir()) == []


def test_deck_outputs_rejects_build_symlink_outside_deck(
    tmp_path: Path,
) -> None:
    deck_root = tmp_path / "deck"
    deck_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_dir_or_skip(deck_root / ".autooffice-build", outside)

    source = deck_root / "deck.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")

    with pytest.raises(CliError, match="keluar dari direktori deck") as error:
        deck_outputs(source)

    assert error.value.code == "CLI-BUILD-PATH"
    assert list(outside.iterdir()) == []


def test_deck_outputs_rejects_build_stem_symlink_outside_deck(
    tmp_path: Path,
) -> None:
    deck_root = tmp_path / "deck"
    deck_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    build_root = deck_root / ".autooffice-build"
    build_root.mkdir()
    _symlink_dir_or_skip(build_root / "deck", outside)

    source = deck_root / "deck.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")

    with pytest.raises(CliError, match="keluar dari direktori deck") as error:
        deck_outputs(source)

    assert error.value.code == "CLI-BUILD-PATH"
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("asset_root", ["assets", "diagrams"])
def test_stage_deck_assets_rejects_symlinked_asset_root(
    tmp_path: Path,
    asset_root: str,
) -> None:
    deck_root = tmp_path / "deck"
    deck_root.mkdir()
    outside = tmp_path / "outside"
    (outside / "assets").mkdir(parents=True)
    (outside / "assets" / "hero.png").write_bytes(b"outside")
    _symlink_dir_or_skip(deck_root / asset_root, outside / "assets")
    deck = SimpleNamespace(slides=())
    workspace = tmp_path / "workspace"

    with pytest.raises(CliError, match="symlink/junction") as error:
        stage_deck_assets(deck_root / "deck.yaml", deck, workspace)

    assert error.value.code == "CLI-ASSET-LINK"
    assert not workspace.exists()
    assert (outside / "assets" / "hero.png").read_bytes() == b"outside"


def test_stage_deck_assets_rejects_destination_symlink_outside_workspace(
    tmp_path: Path,
) -> None:
    deck_root = tmp_path / "deck"
    (deck_root / "assets").mkdir(parents=True)
    (deck_root / "assets" / "hero.png").write_bytes(b"hero")
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _symlink_dir_or_skip(workspace / "assets", outside)
    deck = _deck_with_images("assets/hero.png")

    with pytest.raises(CliError, match="keluar dari direktori build") as error:
        stage_deck_assets(deck_root / "deck.yaml", deck, workspace)

    assert error.value.code == "CLI-ASSET-STAGE"
    assert list(outside.iterdir()) == []


def test_atomic_write_and_copy_fsync_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    source = tmp_path / "source.txt"
    source.write_text("isi", encoding="utf-8")
    target = tmp_path / "out.txt"

    monkeypatch.setattr(
        "autooffice.cli.outputs.os.fsync",
        lambda _descriptor: events.append("fsync"),
    )

    atomic_write_text(target, "halo")
    atomic_copy(source, target)

    assert events == ["fsync", "fsync"]
    assert target.read_text(encoding="utf-8") == "isi"


def test_atomic_write_cleans_temporary_file_on_type_error(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"

    with pytest.raises(CliError, match="tidak dapat ditulis") as error:
        atomic_write_bytes(target, object())  # type: ignore[arg-type]

    assert error.value.code == "CLI-OUT-WRITE"
    assert not target.exists()
    assert list(tmp_path.glob(".out.bin.*.tmp")) == []


def test_atomic_copy_cleans_temporary_file_on_serialization_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("isi", encoding="utf-8")
    target = tmp_path / "out.txt"

    def fail_copy(*_args: object, **_kwargs: object) -> None:
        raise ValueError("serialisasi gagal")

    monkeypatch.setattr("autooffice.cli.outputs.shutil.copyfileobj", fail_copy)

    with pytest.raises(CliError, match="tidak dapat disalin") as error:
        atomic_copy(source, target)

    assert error.value.code == "CLI-OUT-COPY"
    assert not target.exists()
    assert list(tmp_path.glob(".out.txt.*.tmp")) == []
