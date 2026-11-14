"""Tes stage ``office`` AutoOffice tanpa Microsoft Word nyata.

Semua pemanggilan Word diganti fake pada :mod:`autooffice.pdf.word`; tidak ada
COM, PowerShell, subprocess, atau Word nyata yang dijalankan.
"""

import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from autooffice.docx.errors import ToolMissingError, WordError
from autooffice.docx.pipeline import BuildOptions, StageName, canonical_prefix
from autooffice.docx.stages import office
from autooffice.pdf import com as pdf_com
from autooffice.pdf import word as pdf_word

_ZIP_STUB = b"PK\x03\x04docx-stub"


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
    target: str = "docx",
    allow_missing_word: bool = False,
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
        dry_run=False,
    )
    return ctx, docx


class FakeWordModule:
    def __init__(
        self,
        *,
        error: BaseException | None = None,
        output: bytes = _ZIP_STUB,
    ) -> None:
        self.error = error
        self.output = output
        self.calls: list[tuple[Path, float, bool]] = []

    def update_fields(self, docx: Path, *, timeout_s: float, visible: bool) -> Path:
        self.calls.append((Path(docx), timeout_s, visible))
        if self.error is not None:
            raise self.error
        path = Path(docx)
        path.write_bytes(self.output)
        return path.resolve()


def _word_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(office, "word_available", lambda: True)


def _install_word(monkeypatch: pytest.MonkeyPatch, fake: FakeWordModule) -> None:
    _word_ready(monkeypatch)
    monkeypatch.setattr(pdf_word, "update_fields", fake.update_fields)


# ---------------------------------------------------------------------------
# Deteksi Word
# ---------------------------------------------------------------------------


def test_word_available_requires_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(office, "is_windows", lambda: False)

    assert office.word_available() is False


def test_word_available_requires_word_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(office, "is_windows", lambda: True)
    monkeypatch.setattr(office, "find_word_executable", lambda: None)
    monkeypatch.setattr(office, "_com_available", lambda: True)

    assert office.word_available() is False


def test_word_available_requires_com(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(office, "is_windows", lambda: True)
    monkeypatch.setattr(office, "find_word_executable", lambda: "C:/Word/WINWORD.EXE")
    monkeypatch.setattr(office, "_com_available", lambda: False)

    assert office.word_available() is False


def test_com_available_false_without_pywin32(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(office, "is_windows", lambda: True)

    def unavailable() -> None:
        raise pdf_com.PdfUnavailableError("pywin32 tidak terpasang")

    monkeypatch.setattr(pdf_com, "load_com_modules", unavailable)

    assert office._com_available() is False


def test_word_available_when_word_executable_and_com_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(office, "is_windows", lambda: True)
    monkeypatch.setattr(office, "find_word_executable", lambda: "C:/Word/WINWORD.EXE")
    monkeypatch.setattr(office, "_com_available", lambda: True)

    assert office.word_available() is True


def test_find_word_executable_env_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "WINWORD.EXE"
    executable.write_bytes(b"stub")
    monkeypatch.setenv("DOCGEN_WINWORD", str(executable))

    assert office.find_word_executable() == str(executable)


# ---------------------------------------------------------------------------
# Stage office
# ---------------------------------------------------------------------------


def test_stage_office_calls_pdf_word_update_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule()
    _install_word(monkeypatch, fake)
    ctx, docx = _context(tmp_path)

    result = office.OfficeStage().run(ctx)

    assert result.stage == StageName.OFFICE.value
    assert result.status == "ok"
    assert result.changed is True
    assert result.artifacts == (docx.resolve(),)
    assert fake.calls == [(docx.resolve(), 300.0, False)]


def test_stage_office_passes_explicit_adapter_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule()
    monkeypatch.setattr(pdf_word, "update_fields", fake.update_fields)
    _ctx, docx = _context(tmp_path)

    result = office.WordAdapter(timeout=42, visible=True).update_fields(docx)

    assert result == docx.resolve()
    assert fake.calls == [(docx.resolve(), 42.0, True)]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (pdf_com.WordComError("COM rusak"), "WORD-FAILED"),
        (pdf_com.WordTimeoutError("lewat batas"), "WORD-TIMEOUT"),
        (pdf_com.WordBusyError("lock penuh"), "WORD-BUSY"),
    ],
)
def test_stage_office_maps_word_com_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: BaseException,
    code: str,
) -> None:
    fake = FakeWordModule(error=error)
    _install_word(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(WordError, match=code) as caught:
        office.OfficeStage().run(ctx)

    assert caught.value.code == code


def test_stage_office_preserves_ambiguous_cleanup_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule(error=pdf_com.WordCleanupError("worker Word masih hidup"))
    _install_word(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(WordError, match="WORD-CLEANUP") as caught:
        office.OfficeStage().run(ctx)

    assert caught.value.code == "WORD-CLEANUP"
    assert caught.value.cleanup_ambiguous is True
    assert isinstance(caught.value.__cause__, pdf_com.WordCleanupError)


def test_stage_office_maps_direct_adapter_cleanup_error(
    tmp_path: Path,
) -> None:
    class CleanupAdapter:
        def available(self) -> bool:
            return True

        def update_fields(self, docx: str | Path, *, timeout: int | None = None) -> Path:
            raise pdf_com.WordCleanupError("worker Word masih hidup")

    ctx, _ = _context(tmp_path)
    ctx.word = CleanupAdapter()

    with pytest.raises(WordError) as caught:
        office.OfficeStage().run(ctx)

    assert caught.value.code == "WORD-CLEANUP"
    assert caught.value.cleanup_ambiguous is True


def test_stage_office_maps_unavailable_word_to_tool_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule(error=pdf_com.PdfUnavailableError("Microsoft Word tidak ada"))
    _install_word(monkeypatch, fake)
    ctx, _ = _context(tmp_path, target="pdf")

    with pytest.raises(ToolMissingError, match="Microsoft Word tidak ada") as caught:
        office.OfficeStage().run(ctx)

    assert caught.value.tool == "Microsoft Word"


def test_stage_office_skips_docx_when_update_fields_com_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule(error=pdf_com.PdfUnavailableError("pywin32 tidak terpasang"))
    _install_word(monkeypatch, fake)
    ctx, _ = _context(tmp_path, target="docx")

    result = office.OfficeStage().run(ctx)

    assert result.status == "skipped"
    assert result.changed is False
    assert "DOCX tetap dihasilkan" in result.warnings[0]
    assert len(fake.calls) == 1


def test_stage_office_skips_both_allow_when_update_fields_com_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule(error=pdf_com.PdfUnavailableError("COM tidak tersedia"))
    _install_word(monkeypatch, fake)
    ctx, _ = _context(tmp_path, target="both", allow_missing_word=True)

    result = office.OfficeStage().run(ctx)

    assert result.status == "skipped"
    assert "PDF dilewati" in result.warnings[0]
    assert len(fake.calls) == 1


def test_stage_office_both_without_allow_rejects_com_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule(error=pdf_com.PdfUnavailableError("COM tidak tersedia"))
    _install_word(monkeypatch, fake)
    ctx, _ = _context(tmp_path, target="both")

    with pytest.raises(ToolMissingError, match="COM tidak tersedia"):
        office.OfficeStage().run(ctx)


def test_stage_office_skips_direct_pdf_unavailable_from_adapter(tmp_path: Path) -> None:
    class UnavailableAdapter:
        def available(self) -> bool:
            return True

        def update_fields(self, docx: str | Path, *, timeout: int | None = None) -> Path:
            raise pdf_com.PdfUnavailableError("COM tidak tersedia")

    ctx, _ = _context(tmp_path, target="docx")
    ctx.word = UnavailableAdapter()

    result = office.OfficeStage().run(ctx)

    assert result.status == "skipped"
    assert "DOCX tetap dihasilkan" in result.warnings[0]


def test_stage_office_retries_transient_com_rejection_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[Path] = []

    def update_fields(docx: Path, *, timeout_s: float, visible: bool) -> Path:
        assert timeout_s == 300.0
        assert visible is False
        calls.append(Path(docx))
        if len(calls) == 1:
            raise pdf_com.WordComError("Call was rejected by callee. (0x80010001)")
        path = Path(docx)
        path.write_bytes(_ZIP_STUB)
        return path.resolve()

    _word_ready(monkeypatch)
    monkeypatch.setattr(pdf_word, "update_fields", update_fields)
    ctx, docx = _context(tmp_path)

    result = office.OfficeStage().run(ctx)

    assert result.status == "ok"
    assert calls == [docx.resolve(), docx.resolve()]


def test_stage_office_does_not_retry_non_transient_com_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule(error=pdf_com.WordComError("COM rusak permanen"))
    _install_word(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(WordError, match="COM rusak permanen"):
        office.OfficeStage().run(ctx)

    assert len(fake.calls) == 1


def test_stage_office_wraps_unknown_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule(error=RuntimeError("COM meledak"))
    _install_word(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(WordError, match="Word gagal memperbarui field DOCX") as caught:
        office.OfficeStage().run(ctx)

    assert caught.value.code == "WORD-FAILED"


def test_stage_office_rejects_non_docx_word_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule(output=b"bukan-docx")
    _install_word(monkeypatch, fake)
    ctx, _ = _context(tmp_path)

    with pytest.raises(WordError, match="bukan DOCX valid") as caught:
        office.OfficeStage().run(ctx)

    assert caught.value.code == "WORD-OUTPUT"


def test_stage_office_skip_without_word_target_docx(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule()
    monkeypatch.setattr(office, "word_available", lambda: False)
    monkeypatch.setattr(pdf_word, "update_fields", fake.update_fields)
    ctx, _ = _context(tmp_path, target="docx")

    result = office.OfficeStage().run(ctx)

    assert result.status == "skipped"
    assert result.changed is False
    assert result.warnings
    assert "DOCX tetap dihasilkan" in result.warnings[0]
    assert fake.calls == []


def test_stage_office_skip_without_word_target_both_allow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule()
    monkeypatch.setattr(office, "word_available", lambda: False)
    monkeypatch.setattr(pdf_word, "update_fields", fake.update_fields)
    ctx, _ = _context(tmp_path, target="both", allow_missing_word=True)

    result = office.OfficeStage().run(ctx)

    assert result.status == "skipped"
    assert "PDF dilewati" in result.warnings[0]
    assert fake.calls == []


def test_stage_office_skip_without_word_does_not_need_docx(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(office, "word_available", lambda: False)
    ctx, docx = _context(tmp_path, target="docx")
    docx.unlink()

    result = office.OfficeStage().run(ctx)

    assert result.status == "skipped"
    assert result.warnings


def test_stage_office_error_without_word_target_both(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(office, "word_available", lambda: False)
    ctx, _ = _context(tmp_path, target="both")

    with pytest.raises(ToolMissingError):
        office.OfficeStage().run(ctx)


def test_stage_office_error_without_word_target_pdf_even_allow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(office, "word_available", lambda: False)
    ctx, _ = _context(tmp_path, target="pdf", allow_missing_word=True)

    with pytest.raises(ToolMissingError):
        office.OfficeStage().run(ctx)


def test_path_output_uses_report_name_without_fallback(tmp_path: Path) -> None:
    ctx, _ = _context(tmp_path)
    ctx.artifacts = None
    ctx.document.metadata.report_name = "Laporan"
    (tmp_path / "Laporan.docx").write_bytes(_ZIP_STUB)

    assert office._docx_path(ctx) == tmp_path / "Laporan.docx"
    assert office._pdf_path(ctx) == tmp_path / "Laporan.pdf"


def test_stage_office_metadata_order() -> None:
    stage = office.OfficeStage()

    assert stage.name == StageName.OFFICE
    assert stage.order == 160
    assert stage.requires == canonical_prefix(StageName.OFFICE)
    assert stage.mutates == frozenset({"package"})
    assert stage.idempotent is False


# ---------------------------------------------------------------------------
# Batas trust: tidak ada subprocess atau PowerShell
# ---------------------------------------------------------------------------


def test_office_module_never_imports_subprocess_or_powershell() -> None:
    source = Path(office.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])

    assert "subprocess" not in imported
    assert "subprocess" not in vars(office)
    lowered = source.casefold()
    for forbidden in ("powershell", "word.ps1", "docgen_powershell", "docgen_word_script"):
        assert forbidden not in lowered


def test_stage_office_does_not_invoke_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = FakeWordModule()
    _install_word(monkeypatch, fake)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess tidak boleh dipanggil")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    ctx, _ = _context(tmp_path)

    assert office.OfficeStage().run(ctx).status == "ok"
