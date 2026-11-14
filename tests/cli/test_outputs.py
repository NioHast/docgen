"""Tes penamaan output dan helper tulis atomik CLI."""

from pathlib import Path

import pytest

from autooffice.cli import CliError
from autooffice.cli.outputs import (
    atomic_copy,
    atomic_write_text,
    deck_outputs,
    docx_outputs,
    planned_deck_files,
    planned_docx_files,
    resolve_output_directory,
)


def test_docx_outputs_example_uses_out_directory(tmp_path: Path) -> None:
    source = tmp_path / "examples" / "demo" / "document.md"
    outputs = docx_outputs(source, "Laporan")
    assert outputs.output_dir == source.parent / "out"
    assert outputs.docx == source.parent / "out" / "Laporan.docx"
    assert outputs.pdf == source.parent / "out" / "Laporan.pdf"
    assert outputs.manifest == source.parent / ".laporan" / "manifest.json"
    assert outputs.terms == source.parent / ".laporan" / "istilah-baru.txt"
    assert outputs.build_dir == source.parent / ".laporan-build"


def test_docx_outputs_user_document_uses_source_directory(tmp_path: Path) -> None:
    source = tmp_path / "document.md"
    outputs = docx_outputs(source, "Tugas")
    assert outputs.output_dir == tmp_path
    assert outputs.docx == tmp_path / "Tugas.docx"


def test_docx_outputs_out_overrides_only_final_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "examples" / "demo" / "document.md"
    out = tmp_path / "custom"
    outputs = docx_outputs(source, "Laporan", out)
    assert outputs.docx == out / "Laporan.docx"
    assert outputs.pdf == out / "Laporan.pdf"
    assert outputs.manifest == source.parent / ".laporan" / "manifest.json"
    assert outputs.build_dir == source.parent / ".laporan-build"


def test_deck_outputs_example_layout(tmp_path: Path) -> None:
    source = tmp_path / "examples" / "demo" / "deck.yaml"
    outputs = deck_outputs(source)
    assert outputs.output_dir == source.parent / "out"
    assert outputs.pptx == source.parent / "out" / "deck.pptx"
    assert outputs.pdf == source.parent / "out" / "deck.pdf"
    assert outputs.transcript == source.parent / "out" / "deck.transcript.md"
    assert outputs.staging == source.parent / "out" / "deck.slides-upload.pptx"
    assert outputs.state == source.parent / ".autooffice" / "state" / "deck.json"
    assert outputs.cache == source.parent / ".autooffice" / "cache"
    assert outputs.review_dir == source.parent / ".autooffice" / "review"
    assert outputs.build_dir == source.parent / ".autooffice-build" / "deck"


def test_deck_outputs_out_keeps_state_identity(tmp_path: Path) -> None:
    source = tmp_path / "deck.yaml"
    out = tmp_path / "out"
    outputs = deck_outputs(source, out)
    assert outputs.pptx == out / "deck.pptx"
    assert outputs.state == tmp_path / ".autooffice" / "state" / "deck.json"
    assert outputs.build_dir == tmp_path / ".autooffice-build" / "deck"


def test_resolve_output_directory_rejects_file(tmp_path: Path) -> None:
    target = tmp_path / "output"
    target.write_text("not a directory", encoding="utf-8")
    with pytest.raises(CliError, match="--out"):
        resolve_output_directory(tmp_path / "document.md", target)


@pytest.mark.parametrize("report_name", ["", "../escape", "a/b", "bad:name"])
def test_docx_outputs_rejects_unsafe_report_name(tmp_path: Path, report_name: str) -> None:
    with pytest.raises(CliError, match="report_name"):
        docx_outputs(tmp_path / "document.md", report_name)


@pytest.mark.parametrize("file_name", ["...yaml", "..yaml", ".. .yaml", ".yaml"])
def test_deck_outputs_rejects_dot_only_stems_without_deleting_files(
    tmp_path: Path,
    file_name: str,
) -> None:
    source = tmp_path / file_name
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("jangan hilang", encoding="utf-8")

    with pytest.raises(CliError) as error:
        deck_outputs(source)

    assert error.value.code == "CLI-INPUT-NAME"
    assert error.value.exit_code == 2
    assert source.is_file()
    assert sentinel.read_text(encoding="utf-8") == "jangan hilang"


@pytest.mark.parametrize(
    "report_name",
    ["CON", "con.txt", "NUL.report", "PRN", "AUX", "COM1", "LPT9", "clock$.txt"],
)
def test_report_name_rejects_windows_reserved_devices(
    tmp_path: Path,
    report_name: str,
) -> None:
    with pytest.raises(CliError, match="perangkat Windows") as error:
        docx_outputs(tmp_path / "document.md", report_name)

    assert error.value.code == "CLI-REPORT-NAME"


def test_deck_outputs_rejects_windows_reserved_device_name(tmp_path: Path) -> None:
    source = tmp_path / "nul.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")

    with pytest.raises(CliError, match="perangkat Windows") as error:
        deck_outputs(source)

    assert error.value.code == "CLI-INPUT-NAME"


def test_output_names_reject_excessive_length(tmp_path: Path) -> None:
    long_name = "laporan-" + "a" * 220

    with pytest.raises(CliError, match="terlalu panjang") as error:
        docx_outputs(tmp_path / "document.md", long_name)

    assert error.value.code == "CLI-REPORT-NAME"

    source = tmp_path / f"{long_name}.yaml"
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")
    with pytest.raises(CliError, match="terlalu panjang") as deck_error:
        deck_outputs(source)
    assert deck_error.value.code == "CLI-INPUT-NAME"


def test_report_name_allows_internal_dots(tmp_path: Path) -> None:
    outputs = docx_outputs(tmp_path / "document.md", "Laporan 2026.1")

    assert outputs.docx.name == "Laporan 2026.1.docx"


def test_planned_docx_files_follow_targets_and_terms(tmp_path: Path) -> None:
    outputs = docx_outputs(tmp_path / "document.md", "Tugas")
    assert planned_docx_files(outputs, ("docx", "pdf"), terms=True) == (
        outputs.docx,
        outputs.pdf,
        outputs.manifest,
        outputs.terms,
    )


def test_planned_deck_files_include_transcript_only_when_present(tmp_path: Path) -> None:
    source = tmp_path / "deck.yaml"
    outputs = deck_outputs(source)
    assert planned_deck_files(outputs, ("pptx", "pdf")) == (outputs.pptx, outputs.pdf)
    (tmp_path / "transcripts.md").write_text("# transkrip\n", encoding="utf-8")
    assert planned_deck_files(outputs, ("pptx", "pdf")) == (
        outputs.pptx,
        outputs.pdf,
        outputs.transcript,
    )


def test_planned_deck_files_slides_include_state_and_optional_staging(
    tmp_path: Path,
) -> None:
    outputs = deck_outputs(tmp_path / "deck.yaml")
    assert planned_deck_files(outputs, ("slides",)) == (outputs.state,)
    assert planned_deck_files(outputs, ("slides",), keep_intermediate=True) == (
        outputs.state,
        outputs.staging,
    )


def test_planned_deck_files_slides_sync_writes_review_file(tmp_path: Path) -> None:
    outputs = deck_outputs(tmp_path / "deck.yaml")
    diff = outputs.review_dir / "deck.diff.json"
    assert planned_deck_files(outputs, ("slides",), sync_mode="diff") == (
        diff,
        outputs.state,
    )


def test_planned_deck_files_rejects_unknown_sync_mode(tmp_path: Path) -> None:
    outputs = deck_outputs(tmp_path / "deck.yaml")

    with pytest.raises(CliError, match="mode sync tidak valid") as error:
        planned_deck_files(outputs, ("slides",), sync_mode="pulls")

    assert error.value.code == "CLI-SYNC-MODE"
    assert error.value.exit_code == 2


def test_planned_deck_files_pdf_keep_intermediate(tmp_path: Path) -> None:
    outputs = deck_outputs(tmp_path / "deck.yaml")
    assert planned_deck_files(
        outputs,
        ("pdf",),
        keep_intermediate=True,
    ) == (outputs.pdf, outputs.intermediate_pptx)


def test_atomic_write_and_copy(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.txt"
    assert atomic_write_text(target, "halo") == target
    assert target.read_text(encoding="utf-8") == "halo"

    copy = tmp_path / "nested" / "copy.txt"
    assert atomic_copy(target, copy) == copy
    assert copy.read_text(encoding="utf-8") == "halo"
