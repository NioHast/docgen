"""Tes unit stage ``pdf``: aturan target, mock Word, dan output atomic."""

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from docgen.errors import PdfError, ToolMissingError
from docgen.pipeline import BuildOptions, StageName, canonical_prefix
from docgen.stages import office
from docgen.stages import pdf as pdf_stage

_ZIP_STUB = b"PK\x03\x04docx-stub"
_PDF_STUB = b"%PDF-1.7\nstub\n"


class FakeArtifacts:
    def __init__(self, docx: Path) -> None:
        self._docx = docx

    def keys(self) -> tuple[str, ...]:
        return ("docx",)

    def require(self, key: str) -> Path:
        assert key == "docx"
        return self._docx


def _context(
    tmp_path: Path,
    *,
    target: str = "both",
    allow_missing_word: bool = False,
    adapter: object | None = None,
    dry_run: bool = False,
) -> tuple[SimpleNamespace, Path]:
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    ctx = SimpleNamespace(
        options=BuildOptions(
            target=target,
            allow_missing_word=allow_missing_word,
        ),
        artifacts=FakeArtifacts(docx),
        output_dir=tmp_path,
        document=SimpleNamespace(metadata=SimpleNamespace(report_name="Tugas")),
        workspace=SimpleNamespace(path=lambda name: tmp_path / name),
        word=adapter,
        logger=logging.getLogger("test.pdf"),
        dry_run=dry_run,
    )
    return ctx, docx


class FakePdfAdapter:
    def __init__(
        self,
        *,
        available: bool = True,
        error: BaseException | None = None,
        output: bytes = _PDF_STUB,
    ) -> None:
        self.available_value = available
        self.error = error
        self.output = output
        self.calls: list[tuple[Path, Path, int | None]] = []

    def available(self) -> bool:
        return self.available_value

    def export_pdf(
        self,
        docx_path: str | Path,
        pdf_path: str | Path,
        *,
        timeout: int | None = None,
    ) -> Path:
        self.calls.append((Path(docx_path), Path(pdf_path), timeout))
        if self.error is not None:
            raise self.error
        target = Path(pdf_path)
        target.write_bytes(self.output)
        return target


def _windows_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(office, "is_windows", lambda: True)
    monkeypatch.setattr(office, "find_word_executable", lambda: "C:/Word/WINWORD.EXE")


# ---------------------------------------------------------------------------
# enabled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "expected"),
    [("docx", False), ("pdf", True), ("both", True)],
)
def test_stage_pdf_enabled_mengikuti_target(
    tmp_path: Path,
    target: str,
    expected: bool,
) -> None:
    ctx, _ = _context(tmp_path, target=target, adapter=FakePdfAdapter())
    assert pdf_stage.PdfStage().enabled(ctx) is expected


def test_stage_pdf_disabled_saat_dry_run(tmp_path: Path) -> None:
    ctx, _ = _context(tmp_path, target="both", dry_run=True, adapter=FakePdfAdapter())
    assert pdf_stage.PdfStage().enabled(ctx) is False


def test_stage_pdf_metadata_urutan() -> None:
    stage = pdf_stage.PdfStage()

    assert stage.name == StageName.PDF
    assert stage.order == 170
    assert stage.requires == canonical_prefix(StageName.PDF)
    assert stage.mutates == frozenset()
    assert stage.idempotent is False


# ---------------------------------------------------------------------------
# Eksekusi stage
# ---------------------------------------------------------------------------


def test_stage_pdf_sukses(tmp_path: Path) -> None:
    adapter = FakePdfAdapter()
    ctx, docx = _context(tmp_path, adapter=adapter)

    result = pdf_stage.PdfStage().run(ctx)

    assert result.stage == StageName.PDF.value
    assert result.status == "ok"
    assert result.changed is False
    assert result.artifacts == (tmp_path / "Tugas.pdf",)
    assert adapter.calls == [(docx, tmp_path / "Tugas.pdf", None)]
    assert (tmp_path / "Tugas.pdf").read_bytes() == _PDF_STUB


def test_stage_pdf_meneruskan_error_pdf(tmp_path: Path) -> None:
    adapter = FakePdfAdapter(error=PdfError("ekspor gagal"))
    ctx, _ = _context(tmp_path, adapter=adapter)

    with pytest.raises(PdfError, match="ekspor gagal"):
        pdf_stage.PdfStage().run(ctx)


def test_stage_pdf_membungkus_error_tak_dikenal(tmp_path: Path) -> None:
    adapter = FakePdfAdapter(error=RuntimeError("COM mati"))
    ctx, _ = _context(tmp_path, adapter=adapter)

    with pytest.raises(PdfError, match="stage pdf gagal"):
        pdf_stage.PdfStage().run(ctx)


def test_stage_pdf_skip_target_both_allow_missing_word(tmp_path: Path) -> None:
    adapter = FakePdfAdapter(available=False)
    ctx, _ = _context(tmp_path, target="both", allow_missing_word=True, adapter=adapter)

    result = pdf_stage.PdfStage().run(ctx)

    assert result.status == "skipped"
    assert result.changed is False
    assert "PDF dilewati" in result.warnings[0]
    assert adapter.calls == []


def test_stage_pdf_skip_tidak_butuh_docx(tmp_path: Path) -> None:
    adapter = FakePdfAdapter(available=False)
    ctx, docx = _context(
        tmp_path,
        target="both",
        allow_missing_word=True,
        adapter=adapter,
    )
    docx.unlink()

    result = pdf_stage.PdfStage().run(ctx)

    assert result.status == "skipped"
    assert "PDF dilewati" in result.warnings[0]


def test_stage_pdf_error_target_both_tanpa_allow(tmp_path: Path) -> None:
    adapter = FakePdfAdapter(available=False)
    ctx, _ = _context(tmp_path, target="both", adapter=adapter)

    with pytest.raises(ToolMissingError):
        pdf_stage.PdfStage().run(ctx)


def test_stage_pdf_error_target_pdf_walau_allow(tmp_path: Path) -> None:
    adapter = FakePdfAdapter(available=False)
    ctx, _ = _context(
        tmp_path,
        target="pdf",
        allow_missing_word=True,
        adapter=adapter,
    )

    with pytest.raises(ToolMissingError):
        pdf_stage.PdfStage().run(ctx)


def test_stage_pdf_run_langsung_saat_disabled_skip(tmp_path: Path) -> None:
    adapter = FakePdfAdapter()
    ctx, _ = _context(tmp_path, target="docx", adapter=adapter)

    result = pdf_stage.PdfStage().run(ctx)

    assert result.status == "skipped"
    assert "target tidak meminta PDF" in result.warnings[0]
    assert adapter.calls == []


# ---------------------------------------------------------------------------
# Adapter atomic
# ---------------------------------------------------------------------------


def test_adapter_export_pdf_atomic_dan_memeriksa_hasil(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    pdf = tmp_path / "out" / "Tugas.pdf"
    seen: list[Path] = []

    def runner(command: list[str], timeout: int) -> int:
        temporary = Path(command[command.index("-PdfPath") + 1])
        seen.append(temporary)
        assert temporary != pdf
        assert temporary.suffix == ".pdf"
        temporary.write_bytes(_PDF_STUB)
        return 0

    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    assert adapter.export_pdf(docx, pdf, timeout=7) == pdf.resolve()
    assert pdf.read_bytes() == _PDF_STUB
    assert seen
    assert not seen[0].exists()


def test_adapter_export_pdf_menolak_hasil_bukan_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    pdf = tmp_path / "Tugas.pdf"

    def runner(command: list[str], timeout: int) -> int:
        Path(command[command.index("-PdfPath") + 1]).write_bytes(b"bukan-pdf")
        return 0

    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    with pytest.raises(PdfError, match="bukan PDF valid"):
        adapter.export_pdf(docx, pdf)
    assert not pdf.exists()


def test_adapter_export_pdf_gagal_tidak_menimpa_pdf_lama(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    pdf = tmp_path / "Tugas.pdf"
    pdf.write_bytes(b"%PDF-1.7\nlama\n")

    def runner(command: list[str], timeout: int) -> int:
        return 1

    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    with pytest.raises(PdfError, match="kode 1"):
        adapter.export_pdf(docx, pdf)
    assert pdf.read_bytes() == b"%PDF-1.7\nlama\n"


def test_adapter_export_pdf_tanpa_word_melempar_tool_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(office, "is_windows", lambda: False)
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)

    adapter = office.WordAdapter(
        script=tmp_path / "word.ps1",
        runner=lambda *_: 0,
    )

    with pytest.raises(ToolMissingError):
        adapter.export_pdf(docx, tmp_path / "Tugas.pdf")


def test_api_modul_export_pdf_memakai_adapter(
    tmp_path: Path,
) -> None:
    adapter = FakePdfAdapter()
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    pdf = tmp_path / "Tugas.pdf"

    assert office.export_pdf(docx, pdf, adapter=adapter) == pdf
    assert pdf.read_bytes() == _PDF_STUB
