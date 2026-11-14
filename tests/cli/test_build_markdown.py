"""Tes build Markdown/DOCX: hasil artefak, PDF, dan dry-run keep-intermediate."""

import shutil
from pathlib import Path

import pytest

import autooffice.pdf
from autooffice.cli import CliError
from autooffice.cli.build import build_markdown
from autooffice.docx.command import DocxResult
from autooffice.docx.errors import WordError
from autooffice.docx.stages import office
from autooffice.docx.stages.pandoc import find_pandoc
from autooffice.pdf import WordCleanupError

REPORT_NAME = "Laporan Uji"
DOCX_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "docx" / "minimal"


def _markdown(tmp_path: Path) -> Path:
    (tmp_path / "references.bib").write_text(
        "@article{pandoc2024,\n  title = {Pandoc},\n  author = {Doe, Jane},\n  year = {2024},\n}\n",
        encoding="utf-8",
    )
    source = tmp_path / "document.md"
    source.write_text(
        "---\n"
        'title: "Uji CLI"\n'
        'author: "Penulis"\n'
        f'report_name: "{REPORT_NAME}"\n'
        "structure: assignment\n"
        "format: undip-msi\n"
        "---\n\n"
        "# Pendahuluan\n\nTeks pendahuluan.\n\n"
        "# Pembahasan\n\nTeks pembahasan.\n\n"
        "# Penutup\n\nTeks penutup.\n",
        encoding="utf-8",
    )
    return source


def _install_build_docx(
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_manifest: bool = True,
    with_terms: bool = False,
    with_workspace: bool = False,
    warnings: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_build_docx(
        *,
        input: Path,
        out: Path | None = None,
        terms: bool = False,
        keep_intermediate: bool = False,
    ) -> DocxResult:
        calls.append(
            {
                "input": input,
                "out": out,
                "terms": terms,
                "keep_intermediate": keep_intermediate,
            }
        )
        output_dir = input.parent if out is None else out
        output_dir.mkdir(parents=True, exist_ok=True)
        docx = output_dir / f"{REPORT_NAME}.docx"
        docx.write_bytes(b"PK fake docx")
        manifest = None
        if with_manifest:
            manifest = input.parent / ".laporan" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text("{}", encoding="utf-8")
        terms_path = None
        if with_terms:
            terms_path = input.parent / ".laporan" / "istilah-baru.txt"
            terms_path.parent.mkdir(parents=True, exist_ok=True)
            terms_path.write_text("istilah", encoding="utf-8")
        workspace = None
        if with_workspace:
            workspace = input.parent / ".laporan-build"
            workspace.mkdir(parents=True, exist_ok=True)
        return DocxResult(
            docx=docx,
            manifest=manifest,
            terms=terms_path,
            warnings=warnings,
            workspace=workspace,
        )

    monkeypatch.setattr("autooffice.docx.command.build_docx", fake_build_docx)
    return calls


def test_build_markdown_docx_lists_manifest_terms_and_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    calls = _install_build_docx(
        monkeypatch,
        with_terms=True,
        with_workspace=True,
        warnings=("caption hilang",),
    )

    outcome = build_markdown(source, ("docx",), terms=True, keep_intermediate=True)

    docx = tmp_path / f"{REPORT_NAME}.docx"
    manifest = tmp_path / ".laporan" / "manifest.json"
    terms = tmp_path / ".laporan" / "istilah-baru.txt"
    assert outcome.files == (docx, manifest, terms)
    assert outcome.warnings == ("caption hilang",)
    assert outcome.notes == (f"workspace dipertahankan: {tmp_path / '.laporan-build'}",)
    assert outcome.dry_run is False
    assert calls == [
        {
            "input": source,
            "out": None,
            "terms": True,
            "keep_intermediate": True,
        }
    ]


def test_build_markdown_pdf_only_preserves_preexisting_docx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    final_docx = tmp_path / f"{REPORT_NAME}.docx"
    final_docx.write_bytes(b"DOCX lama")
    _install_build_docx(monkeypatch, with_manifest=False)
    exported: list[tuple[Path, Path]] = []

    def fake_export(docx: Path, pdf: Path) -> None:
        exported.append((docx, pdf))
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.7 fake\n")

    monkeypatch.setattr(autooffice.pdf, "export_pdf", fake_export)

    outcome = build_markdown(source, ("pdf",))

    pdf = tmp_path / f"{REPORT_NAME}.pdf"
    build_dir = tmp_path / ".laporan-build"
    intermediate = build_dir / f"{REPORT_NAME}.docx"
    assert outcome.files == (pdf,)
    assert pdf.read_bytes() == b"%PDF-1.7 fake\n"
    assert final_docx.read_bytes() == b"DOCX lama"
    assert not build_dir.exists()
    assert outcome.notes == (
        "DOCX intermediate dihapus dari workspace karena --keep-intermediate tidak aktif",
    )
    assert exported[0][0] == intermediate


@pytest.mark.skipif(
    find_pandoc() is None,
    reason="Pandoc diperlukan untuk build DOCX nyata",
)
def test_build_markdown_pdf_only_real_docx_keeps_workspace_until_conversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(office, "word_available", lambda: False)
    project = tmp_path / "project"
    shutil.copytree(DOCX_FIXTURE, project)
    source = project / "document.md"
    final_docx = project / "Paritas.docx"
    final_docx.write_bytes(b"DOCX lama")

    build_dir = project / ".laporan-build"
    intermediate = build_dir / "Paritas.docx"
    converted: list[Path] = []

    def fake_export(docx: Path, pdf: Path) -> Path:
        assert docx == intermediate
        assert docx.is_file()
        assert build_dir.is_dir()
        converted.append(docx)
        pdf.write_bytes(b"%PDF-1.7 fake\n")
        return pdf

    monkeypatch.setattr(autooffice.pdf, "export_pdf", fake_export)

    outcome = build_markdown(source, ("pdf",))

    pdf = project / "Paritas.pdf"
    assert converted == [intermediate]
    assert set(outcome.files) == {pdf, project / ".laporan" / "manifest.json"}
    assert pdf.read_bytes() == b"%PDF-1.7 fake\n"
    assert final_docx.read_bytes() == b"DOCX lama"
    assert not build_dir.exists()


def test_build_markdown_pdf_keep_intermediate_keeps_and_reports_docx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    final_docx = tmp_path / f"{REPORT_NAME}.docx"
    final_docx.write_bytes(b"DOCX lama")
    _install_build_docx(monkeypatch, with_manifest=False, with_workspace=True)

    def fake_export(_docx: Path, pdf: Path) -> Path:
        pdf.write_bytes(b"%PDF-1.7 fake\n")
        return pdf

    monkeypatch.setattr(autooffice.pdf, "export_pdf", fake_export)

    outcome = build_markdown(source, ("pdf",), keep_intermediate=True)

    intermediate = tmp_path / ".laporan-build" / f"{REPORT_NAME}.docx"
    assert outcome.files == (tmp_path / f"{REPORT_NAME}.pdf", intermediate)
    assert intermediate.is_file()
    assert final_docx.read_bytes() == b"DOCX lama"
    assert f"intermediate dipertahankan: {tmp_path / '.laporan-build'}" in outcome.notes
    assert f"workspace dipertahankan: {tmp_path / '.laporan-build'}" in outcome.notes


def test_build_markdown_docx_and_pdf_keep_both_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    _install_build_docx(monkeypatch, with_manifest=False)

    def fake_export(_docx: Path, pdf: Path) -> Path:
        pdf.write_bytes(b"%PDF-1.7 fake\n")
        return pdf

    monkeypatch.setattr(autooffice.pdf, "export_pdf", fake_export)

    outcome = build_markdown(source, ("docx", "pdf"))

    docx = tmp_path / f"{REPORT_NAME}.docx"
    pdf = tmp_path / f"{REPORT_NAME}.pdf"
    assert outcome.files == (docx, pdf)
    assert docx.is_file()
    assert pdf.is_file()
    assert outcome.notes == ()


def test_build_markdown_prefers_dedicated_docx_converter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    _install_build_docx(monkeypatch, with_manifest=False)
    calls: list[tuple[Path, Path]] = []

    def fake_convert(docx: Path, pdf: Path) -> None:
        calls.append((docx, pdf))
        pdf.write_bytes(b"%PDF-1.7 dedicated\n")

    monkeypatch.setattr(autooffice.pdf, "convert_docx_to_pdf", fake_convert, raising=False)

    def fail_export(_docx: Path, _pdf: Path) -> None:
        raise AssertionError("export_pdf tidak boleh dipanggil")

    monkeypatch.setattr(autooffice.pdf, "export_pdf", fail_export)

    outcome = build_markdown(source, ("pdf",))

    assert outcome.files == (tmp_path / f"{REPORT_NAME}.pdf",)
    assert calls == [
        (
            tmp_path / ".laporan-build" / f"{REPORT_NAME}.docx",
            tmp_path / f"{REPORT_NAME}.pdf",
        )
    ]


def test_build_markdown_pdf_failure_names_completed_docx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    _install_build_docx(monkeypatch, with_manifest=False)

    def fake_export(_docx: Path, _pdf: Path) -> Path:
        return tmp_path / "tidak-ada.pdf"

    monkeypatch.setattr(autooffice.pdf, "export_pdf", fake_export)

    with pytest.raises(CliError, match="DOCX selesai di") as error:
        build_markdown(source, ("pdf",))

    docx = tmp_path / ".laporan-build" / f"{REPORT_NAME}.docx"
    assert error.value.code == "CLI-LANE-F2-PDF"
    assert error.value.exit_code == 1
    assert error.value.path == str(docx)
    assert docx.is_file()


def test_build_markdown_preserves_build_dir_on_ambiguous_docx_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    build_dir = tmp_path / ".laporan-build"

    def fail_build_docx(
        *,
        input: Path,
        out: Path | None = None,
        terms: bool = False,
        keep_intermediate: bool = False,
    ) -> DocxResult:
        assert out is not None
        out.mkdir(parents=True, exist_ok=True)
        intermediate = out / f"{REPORT_NAME}.docx"
        intermediate.write_bytes(b"PK partial")
        (out / "office-temp.tmp").write_text("worker masih menulis", encoding="utf-8")
        raise WordError(
            "worker Word masih hidup",
            code="WORD-CLEANUP",
            cleanup_ambiguous=True,
        )

    monkeypatch.setattr("autooffice.docx.command.build_docx", fail_build_docx)

    with pytest.raises(WordError, match="WORD-CLEANUP") as error:
        build_markdown(source, ("pdf",))

    assert error.value.code == "WORD-CLEANUP"
    assert error.value.cleanup_ambiguous is True
    assert (build_dir / f"{REPORT_NAME}.docx").is_file()
    assert (build_dir / "office-temp.tmp").is_file()


def test_build_markdown_preserves_build_dir_on_ambiguous_pdf_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    _install_build_docx(monkeypatch, with_manifest=False)
    build_dir = tmp_path / ".laporan-build"

    def fail_export(_docx: Path, _pdf: Path) -> None:
        (build_dir / "office-temp.pdf").write_text("worker masih menulis", encoding="utf-8")
        raise WordCleanupError("worker Word masih hidup")

    monkeypatch.setattr(autooffice.pdf, "export_pdf", fail_export)

    with pytest.raises(CliError, match="PDF-CLEANUP") as error:
        build_markdown(source, ("pdf",))

    assert error.value.code == "PDF-CLEANUP"
    assert error.value.cleanup_ambiguous is True
    assert (build_dir / f"{REPORT_NAME}.docx").is_file()
    assert (build_dir / "office-temp.pdf").is_file()


def test_build_markdown_pdf_without_converter_reports_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    _install_build_docx(monkeypatch, with_manifest=False)
    monkeypatch.setattr(autooffice.pdf, "export_pdf", None)
    monkeypatch.delattr(autooffice.pdf, "convert_docx_to_pdf", raising=False)

    with pytest.raises(CliError, match="F2-PDF") as error:
        build_markdown(source, ("pdf",))

    assert error.value.code == "CLI-LANE-F2-PDF"
    assert "belum tersedia" in str(error.value)


def test_build_markdown_pdf_converter_may_return_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    _install_build_docx(monkeypatch, with_manifest=False)

    def fake_export(_docx: Path, pdf: Path) -> str:
        pdf.write_bytes(b"%PDF-1.7 fake\n")
        return str(pdf)

    monkeypatch.setattr(autooffice.pdf, "export_pdf", fake_export)

    outcome = build_markdown(source, ("pdf",))

    assert outcome.files == (tmp_path / f"{REPORT_NAME}.pdf",)


def test_build_markdown_pdf_converter_invalid_result_reports_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    _install_build_docx(monkeypatch, with_manifest=False)
    monkeypatch.setattr(autooffice.pdf, "export_pdf", lambda _docx, _pdf: object())

    with pytest.raises(CliError, match="tidak mengembalikan path") as error:
        build_markdown(source, ("pdf",))

    assert error.value.code == "CLI-LANE-F2-PDF"


def test_build_markdown_dry_run_keep_intermediate_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _markdown(tmp_path)
    calls = _install_build_docx(monkeypatch)

    outcome = build_markdown(source, ("docx",), dry_run=True, keep_intermediate=True)

    assert calls == []
    assert outcome.dry_run is True
    assert outcome.files == (
        tmp_path / f"{REPORT_NAME}.docx",
        tmp_path / ".laporan" / "manifest.json",
    )
    assert f"intermediate dipertahankan: {tmp_path / '.laporan-build'}" in outcome.notes
    assert not (tmp_path / ".laporan-build").exists()
    assert capsys.readouterr().out == ""


def test_build_markdown_requires_at_least_one_target(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="minimal satu target") as error:
        build_markdown(tmp_path / "document.md", ())

    assert error.value.code == "CLI-TARGET-MISSING"
    assert error.value.exit_code == 2


def test_build_markdown_expands_out_before_build_and_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    calls = _install_build_docx(monkeypatch, with_manifest=False)

    outcome = build_markdown(source, ("docx",), out=Path("~/records"))

    expected = home / "records"
    assert calls[0]["out"] == expected
    assert outcome.files[0] == expected / f"{REPORT_NAME}.docx"


def test_build_markdown_dry_run_requires_pdf_converter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    monkeypatch.setattr(autooffice.pdf, "export_pdf", None)
    monkeypatch.delattr(autooffice.pdf, "convert_docx_to_pdf", raising=False)

    with pytest.raises(CliError, match="F2-PDF") as error:
        build_markdown(source, ("pdf",), dry_run=True)

    assert error.value.code == "CLI-LANE-F2-PDF"
    assert error.value.exit_code == 1
    assert not (tmp_path / f"{REPORT_NAME}.pdf").exists()
    assert not (tmp_path / ".laporan-build").exists()


def test_build_markdown_pdf_os_error_is_wrapped_with_docx_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _markdown(tmp_path)
    _install_build_docx(monkeypatch, with_manifest=False)

    def fail_export(_docx: Path, _pdf: Path) -> None:
        raise OSError("Word menolak berkas")

    monkeypatch.setattr(autooffice.pdf, "export_pdf", fail_export)

    with pytest.raises(CliError, match="Word menolak berkas") as error:
        build_markdown(source, ("pdf",))

    intermediate = tmp_path / ".laporan-build" / f"{REPORT_NAME}.docx"
    assert error.value.code == "CLI-PDF"
    assert error.value.exit_code == 1
    assert error.value.path == str(intermediate)
    assert intermediate.is_file()
