"""Tes stage ``pdf`` AutoOffice: aturan target, fake Word COM, dan output.

Pemanggilan Word diganti fake pada :mod:`autooffice.pdf.word`; tidak ada COM,
PowerShell, subprocess, atau Word nyata yang dijalankan.
"""

import contextlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from autooffice.docx.errors import PdfError, ToolMissingError
from autooffice.docx.pipeline import BuildOptions, StageName, canonical_prefix
from autooffice.docx.stages import office
from autooffice.docx.stages import pdf as pdf_stage
from autooffice.pdf import com as pdf_com
from autooffice.pdf import word as pdf_word

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
        word=None,
        dry_run=dry_run,
    )
    return ctx, docx


class FakePdfModule:
    def __init__(
        self,
        *,
        error: BaseException | None = None,
        output: bytes = _PDF_STUB,
        write_output: bool = True,
    ) -> None:
        self.error = error
        self.output = output
        self.write_output = write_output
        self.calls: list[tuple[Path, Path, float, bool]] = []

    def export_pdf(
        self,
        docx: Path,
        pdf: Path,
        *,
        timeout_s: float,
        visible: bool,
    ) -> Path:
        self.calls.append((Path(docx), Path(pdf), timeout_s, visible))
        if self.error is not None:
            raise self.error
        target = Path(pdf)
        if self.write_output:
            target.write_bytes(self.output)
        return target.resolve()


def _word_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(office, "word_available", lambda: True)


def _install_pdf(monkeypatch: pytest.MonkeyPatch, fake: FakePdfModule) -> None:
    _word_ready(monkeypatch)
    monkeypatch.setattr(pdf_word, "export_pdf", fake.export_pdf)


class _FakeWordDocument:
    """Dokumen Word palsu yang memutasi path yang dibuka, seperti Word asli."""

    def __init__(self, application: _FakeWordApplication, path: Path) -> None:
        self._application = application
        self.ReadOnly = False
        application.opened_path = Path(path)
        if application.mutate_on_open:
            Path(path).write_bytes(b"PK\x03\x04mutated-snapshot")

    @property
    def Fields(self) -> SimpleNamespace:
        return SimpleNamespace(Update=lambda: None)

    @property
    def TablesOfContents(self) -> SimpleNamespace:
        return SimpleNamespace(Count=0)

    def Repaginate(self) -> None:
        pass

    def ExportAsFixedFormat(self, path: str, export_format: int) -> None:
        self._application.export_format = export_format
        Path(path).write_bytes(_PDF_STUB)

    def Close(self, save_changes: int) -> None:
        pass


class _FakeWordDocuments:
    def __init__(self, application: _FakeWordApplication) -> None:
        self._application = application

    def Open(
        self,
        path: str,
        confirm_conversions: bool,
        read_only: bool,
        add_to_recent_files: bool,
    ) -> _FakeWordDocument:
        self._application.open_arguments = (
            confirm_conversions,
            read_only,
            add_to_recent_files,
        )
        return _FakeWordDocument(self._application, Path(path))


class _FakeWordApplication:
    def __init__(self, *, mutate_on_open: bool) -> None:
        self.mutate_on_open = mutate_on_open
        self.Options = SimpleNamespace()
        self.Documents = _FakeWordDocuments(self)
        self.opened_path: Path | None = None
        self.open_arguments: tuple[bool, bool, bool] | None = None
        self.export_format: int | None = None

    @property
    def ActiveWindow(self) -> SimpleNamespace:
        return SimpleNamespace(Hwnd=9001)

    def Quit(self) -> None:
        _FakeWordProcessControl.automation_alive = False


class _FakeWordClient:
    def __init__(self, application: _FakeWordApplication) -> None:
        self._application = application
        _FakeWordProcessControl.automation_alive = False

    def DispatchEx(self, name: str) -> _FakeWordApplication:
        assert name == "Word.Application"
        _FakeWordProcessControl.automation_alive = True
        return self._application


class _FakePythonCom:
    def CoInitialize(self) -> None:
        pass

    def CoUninitialize(self) -> None:
        pass


class _FakeWordProcessControl:
    """Control palsu yang memenuhi kontrak ownership seperti adapter nyata."""

    automation_alive = False
    pid = 4242
    window_hwnd = 9001

    def set_timeout(self, timeout_s: float) -> None:
        pass

    def list_word_pids(self) -> set[int]:
        return {self.pid} if self.automation_alive else set()

    def image_name(self, pid: int) -> str | None:
        return "WINWORD.EXE" if self.automation_alive and pid == self.pid else None

    def creation_time(self, pid: int) -> int | None:
        return 1000 if self.automation_alive and pid == self.pid else None

    def pid_for_window(self, hwnd: int) -> int | None:
        return self.pid if self.automation_alive and hwnd == self.window_hwnd else None

    def is_running(self, pid: int) -> bool | None:
        return self.automation_alive if pid == self.pid else False

    def terminate(self, pid: int) -> bool:
        if pid != self.pid:
            return False
        self.automation_alive = False
        return True


# ---------------------------------------------------------------------------
# enabled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "expected"),
    [("docx", False), ("pdf", True), ("both", True)],
)
def test_stage_pdf_enabled_follows_target(
    tmp_path: Path,
    target: str,
    expected: bool,
) -> None:
    ctx, _ = _context(tmp_path, target=target)

    assert pdf_stage.PdfStage().enabled(ctx) is expected


def test_stage_pdf_disabled_during_dry_run(tmp_path: Path) -> None:
    ctx, _ = _context(tmp_path, target="both", dry_run=True)

    assert pdf_stage.PdfStage().enabled(ctx) is False


def test_stage_pdf_metadata_order() -> None:
    stage = pdf_stage.PdfStage()

    assert stage.name == StageName.PDF
    assert stage.order == 170
    assert stage.requires == canonical_prefix(StageName.PDF)
    assert stage.mutates == frozenset()
    assert stage.idempotent is False


# ---------------------------------------------------------------------------
# Eksekusi stage
# ---------------------------------------------------------------------------


def test_stage_pdf_calls_pdf_word_export_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule()
    _install_pdf(monkeypatch, fake)
    ctx, docx = _context(tmp_path)

    result = pdf_stage.PdfStage().run(ctx)

    assert result.stage == StageName.PDF.value
    assert result.status == "ok"
    assert result.changed is False
    assert result.artifacts == (tmp_path / "Tugas.pdf",)
    assert fake.calls == [(docx.resolve(), tmp_path / "Tugas.pdf", 300.0, False)]
    assert (tmp_path / "Tugas.pdf").read_bytes() == _PDF_STUB


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (pdf_com.WordComError("COM mati"), "WORD-FAILED"),
        (pdf_com.WordTimeoutError("lewat batas"), "WORD-TIMEOUT"),
        (pdf_com.WordBusyError("lock penuh"), "WORD-BUSY"),
    ],
)
def test_stage_pdf_maps_word_com_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: BaseException,
    code: str,
) -> None:
    fake = FakePdfModule(error=error)
    _install_pdf(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(PdfError, match=code) as caught:
        pdf_stage.PdfStage().run(ctx)

    assert caught.value.code == code


def test_stage_pdf_preserves_ambiguous_cleanup_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule(error=pdf_com.WordCleanupError("worker Word masih hidup"))
    _install_pdf(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(PdfError, match="PDF-CLEANUP") as caught:
        pdf_stage.PdfStage().run(ctx)

    assert caught.value.code == "PDF-CLEANUP"
    assert caught.value.cleanup_ambiguous is True
    assert isinstance(caught.value.__cause__, pdf_com.WordCleanupError)


def test_stage_pdf_maps_direct_adapter_cleanup_error(
    tmp_path: Path,
) -> None:
    class CleanupAdapter:
        def available(self) -> bool:
            return True

        def export_pdf(
            self,
            docx: str | Path,
            pdf: str | Path,
            *,
            timeout: int | None = None,
        ) -> Path:
            raise pdf_com.WordCleanupError("worker Word masih hidup")

    ctx, _ = _context(tmp_path)
    ctx.word = CleanupAdapter()

    with pytest.raises(PdfError) as caught:
        pdf_stage.PdfStage().run(ctx)

    assert caught.value.code == "PDF-CLEANUP"
    assert caught.value.cleanup_ambiguous is True


def test_stage_pdf_maps_unavailable_word_to_tool_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule(error=pdf_com.PdfUnavailableError("Microsoft Word tidak ada"))
    _install_pdf(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(ToolMissingError, match="Microsoft Word tidak ada") as caught:
        pdf_stage.PdfStage().run(ctx)

    assert caught.value.tool == "Microsoft Word"


def test_stage_pdf_skips_both_allow_when_export_com_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule(error=pdf_com.PdfUnavailableError("pywin32 tidak terpasang"))
    _install_pdf(monkeypatch, fake)
    ctx, _ = _context(tmp_path, target="both", allow_missing_word=True)

    result = pdf_stage.PdfStage().run(ctx)

    assert result.status == "skipped"
    assert "PDF dilewati" in result.warnings[0]
    assert len(fake.calls) == 1


def test_stage_pdf_skips_direct_pdf_unavailable_from_adapter(tmp_path: Path) -> None:
    class UnavailableAdapter:
        def available(self) -> bool:
            return True

        def export_pdf(
            self,
            docx: str | Path,
            pdf: str | Path,
            *,
            timeout: int | None = None,
        ) -> Path:
            raise pdf_com.PdfUnavailableError("COM tidak tersedia")

    ctx, _ = _context(tmp_path, target="both", allow_missing_word=True)
    ctx.word = UnavailableAdapter()

    result = pdf_stage.PdfStage().run(ctx)

    assert result.status == "skipped"
    assert "PDF dilewati" in result.warnings[0]


def test_stage_pdf_retries_transient_com_rejection_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[Path, Path]] = []

    def export_pdf(
        docx: Path,
        pdf: Path,
        *,
        timeout_s: float,
        visible: bool,
    ) -> Path:
        assert timeout_s == 300.0
        assert visible is False
        calls.append((Path(docx), Path(pdf)))
        if len(calls) == 1:
            raise pdf_com.WordComError("Call was rejected by callee. (0x80010001)")
        Path(pdf).write_bytes(_PDF_STUB)
        return Path(pdf).resolve()

    _word_ready(monkeypatch)
    monkeypatch.setattr(pdf_word, "export_pdf", export_pdf)
    ctx, docx = _context(tmp_path)

    result = pdf_stage.PdfStage().run(ctx)

    assert result.status == "ok"
    assert calls == [(docx.resolve(), tmp_path / "Tugas.pdf")] * 2


def test_stage_pdf_wraps_unknown_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule(error=RuntimeError("COM meledak"))
    _install_pdf(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(PdfError, match="Word gagal mengekspor PDF") as caught:
        pdf_stage.PdfStage().run(ctx)

    assert caught.value.code == "WORD-FAILED"


def test_stage_pdf_rejects_non_pdf_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule(output=b"bukan-pdf")
    _install_pdf(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(PdfError, match="bukan PDF valid") as caught:
        pdf_stage.PdfStage().run(ctx)

    assert caught.value.code == "PDF-OUTPUT"


def test_stage_pdf_rejects_missing_pdf_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule(write_output=False)
    _install_pdf(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(PdfError, match="tidak dapat dibaca") as caught:
        pdf_stage.PdfStage().run(ctx)

    assert caught.value.code == "PDF-OUTPUT"


def test_stage_pdf_skip_target_both_allow_missing_word(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule()
    monkeypatch.setattr(office, "word_available", lambda: False)
    monkeypatch.setattr(pdf_word, "export_pdf", fake.export_pdf)
    ctx, _ = _context(tmp_path, target="both", allow_missing_word=True)

    result = pdf_stage.PdfStage().run(ctx)

    assert result.status == "skipped"
    assert result.changed is False
    assert "PDF dilewati" in result.warnings[0]
    assert fake.calls == []


def test_stage_pdf_skip_does_not_need_docx(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(office, "word_available", lambda: False)
    ctx, docx = _context(tmp_path, target="both", allow_missing_word=True)
    docx.unlink()

    result = pdf_stage.PdfStage().run(ctx)

    assert result.status == "skipped"
    assert "PDF dilewati" in result.warnings[0]


def test_stage_pdf_error_target_both_without_allow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(office, "word_available", lambda: False)
    ctx, _ = _context(tmp_path, target="both")

    with pytest.raises(ToolMissingError):
        pdf_stage.PdfStage().run(ctx)


def test_stage_pdf_error_target_pdf_even_allow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(office, "word_available", lambda: False)
    ctx, _ = _context(tmp_path, target="pdf", allow_missing_word=True)

    with pytest.raises(ToolMissingError):
        pdf_stage.PdfStage().run(ctx)


def test_stage_pdf_run_directly_when_disabled_skip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule()
    monkeypatch.setattr(pdf_word, "export_pdf", fake.export_pdf)
    ctx, _ = _context(tmp_path, target="docx")

    result = pdf_stage.PdfStage().run(ctx)

    assert result.status == "skipped"
    assert "target tidak meminta PDF" in result.warnings[0]
    assert fake.calls == []


# ---------------------------------------------------------------------------
# API modul
# ---------------------------------------------------------------------------


def test_export_pdf_preserves_source_when_word_mutates_opened_copy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    pdf = tmp_path / "Tugas.pdf"
    application = _FakeWordApplication(mutate_on_open=True)
    monkeypatch.setattr(
        pdf_word,
        "load_com_modules",
        lambda: (_FakeWordClient(application), _FakePythonCom()),
    )
    monkeypatch.setattr(pdf_word, "SystemProcessControl", _FakeWordProcessControl)
    monkeypatch.setattr(pdf_word, "com_lock", lambda **_kwargs: contextlib.nullcontext())
    monkeypatch.setattr(
        pdf_word,
        "find_word_window_handle",
        lambda pid: (
            _FakeWordProcessControl.window_hwnd if pid == _FakeWordProcessControl.pid else None
        ),
    )

    assert pdf_word.export_pdf(docx, pdf, timeout_s=5.0) == pdf.resolve()

    assert application.opened_path is not None
    assert application.opened_path != docx.resolve()
    assert not application.opened_path.exists()
    assert application.open_arguments == (False, False, False)
    assert application.export_format == 17
    assert docx.read_bytes() == _ZIP_STUB
    assert pdf.read_bytes() == _PDF_STUB


def test_api_module_export_pdf_uses_pdf_word(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakePdfModule()
    monkeypatch.setattr(pdf_word, "export_pdf", fake.export_pdf)
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    pdf = tmp_path / "Tugas.pdf"

    assert office.export_pdf(docx, pdf) == pdf

    assert pdf.read_bytes() == _PDF_STUB
    assert fake.calls == [(docx.resolve(), pdf.resolve(), 300.0, False)]
