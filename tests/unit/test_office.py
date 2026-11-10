"""Tes unit stage ``office`` tanpa memanggil Microsoft Word.

Pemanggilan Word memakai runner palsu. Satu tes proses memakai interpreter
Python sebagai child untuk memverifikasi capture log parsial; tidak ada COM,
PowerShell, atau Word nyata yang dijalankan.
"""

import contextlib
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from docgen.errors import ToolMissingError, WordError
from docgen.pipeline import BuildOptions, StageName, canonical_prefix
from docgen.stages import office

_ZIP_STUB = b"PK\x03\x04docx-stub"
_ROOT = Path(__file__).resolve().parents[2]


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
    adapter: object | None = None,
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
        logger=logging.getLogger("test.office"),
        dry_run=False,
    )
    return ctx, docx


class FakeWordAdapter:
    def __init__(
        self,
        *,
        available: bool = True,
        error: BaseException | None = None,
        output: bytes | None = None,
    ) -> None:
        self.available_value = available
        self.error = error
        self.output = output
        self.calls: list[tuple[Path, int | None]] = []

    def available(self) -> bool:
        return self.available_value

    def update_fields(self, docx_path: str | Path, *, timeout: int | None = None) -> Path:
        self.calls.append((Path(docx_path), timeout))
        if self.error is not None:
            raise self.error
        path = Path(docx_path)
        if self.output is not None:
            path.write_bytes(self.output)
        return path


def _windows_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(office, "is_windows", lambda: True)
    monkeypatch.setattr(office, "find_word_executable", lambda: "C:/Word/WINWORD.EXE")


def _pid_file_from_command(command: list[str]) -> Path:
    return Path(command[command.index("-PidFile") + 1])


# ---------------------------------------------------------------------------
# Command builder
# ---------------------------------------------------------------------------


def test_build_update_fields_command(tmp_path: Path) -> None:
    script = tmp_path / "word.ps1"
    docx = tmp_path / "Tugas.docx"

    command = office.build_word_command("powershell", script, docx)

    assert command == [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-DocxPath",
        str(docx),
    ]


def test_build_export_pdf_command(tmp_path: Path) -> None:
    script = tmp_path / "word.ps1"
    docx = tmp_path / "Tugas.docx"
    pdf = tmp_path / "Tugas.pdf"

    command = office.build_word_command("pwsh", script, docx, pdf, visible=True)

    assert command[:7] == [
        "pwsh",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]
    assert command[-5:] == [
        "-DocxPath",
        str(docx),
        "-PdfPath",
        str(pdf),
        "-Visible",
    ]


def test_specialized_command_builders_delegate(tmp_path: Path) -> None:
    script = tmp_path / "word.ps1"
    docx = tmp_path / "Tugas.docx"
    pdf = tmp_path / "Tugas.pdf"

    assert office.build_update_fields_command("powershell", script, docx) == (
        office.build_word_command("powershell", script, docx)
    )
    assert office.build_export_pdf_command("powershell", script, docx, pdf) == (
        office.build_word_command("powershell", script, docx, pdf)
    )


# ---------------------------------------------------------------------------
# Adapter Word dengan runner palsu
# ---------------------------------------------------------------------------


def test_adapter_update_fields_sukses_tanpa_word_nyata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    calls: list[tuple[list[str], int]] = []

    def runner(command: list[str], timeout: int) -> office.WordProcessResult:
        calls.append((list(command), timeout))
        return office.WordProcessResult(0, stdout="[word] OK")

    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    assert adapter.update_fields(docx, timeout=42) == docx.resolve()
    assert len(calls) == 1
    assert calls[0][1] == 42
    command = calls[0][0]
    assert command[-4:-2] == ["-DocxPath", str(docx.resolve())]
    assert command[-2] == "-PidFile"
    pid_path = Path(command[-1])
    assert pid_path.suffix == ".pid"
    assert not pid_path.exists()
    assert "-PdfPath" not in command


def test_adapter_update_fields_gagal_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    calls: list[list[str]] = []

    def runner(command: list[str], timeout: int) -> office.WordProcessResult:
        calls.append(list(command))
        return office.WordProcessResult(1, stderr="COM Word tidak tersedia")

    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    with pytest.raises(WordError) as error:
        adapter.update_fields(docx)

    assert len(calls) == 1
    assert "kode 1" in str(error.value)
    assert "COM Word tidak tersedia" in str(error.value)


def test_adapter_update_fields_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)

    def runner(command: list[str], timeout: int) -> office.WordProcessResult:
        raise subprocess.TimeoutExpired(command, timeout)

    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    with pytest.raises(WordError, match="tidak selesai"):
        adapter.update_fields(docx, timeout=5)


def test_adapter_timeout_menyertakan_step_dan_ekor_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    logs = [f"log-{index}" for index in range(12)] + ["[word] STEP toc_update index=1"]

    def runner(command: list[str], timeout: int) -> office.WordProcessResult:
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            output="\n".join(logs) + "\n",
        )

    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    with pytest.raises(WordError) as error:
        adapter.update_fields(docx, timeout=5)

    message = str(error.value)
    assert "WORD-TIMEOUT" in message
    assert "[word] STEP toc_update" in message
    assert "log-11" in message
    assert "log-0" not in message


def test_adapter_timeout_menhentikan_pid_word(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    stopped: list[int] = []
    pid_paths: list[Path] = []

    def runner(command: list[str], timeout: int) -> office.WordProcessResult:
        pid_path = _pid_file_from_command(command)
        pid_paths.append(pid_path)
        pid_path.write_text("4242\n", encoding="ascii")
        raise subprocess.TimeoutExpired(command, timeout, output="[word] STEP save")

    def fake_image(pid: int) -> str:
        assert pid == 4242
        return "WINWORD.EXE"

    def fake_stop(pid: int) -> bool:
        stopped.append(pid)
        return True

    monkeypatch.setattr(office, "_process_image_name", fake_image)
    monkeypatch.setattr(office, "_stop_word_process", fake_stop)
    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    with pytest.raises(WordError, match="tidak selesai"):
        adapter.update_fields(docx, timeout=5)

    assert stopped == [4242]
    assert pid_paths
    assert not pid_paths[0].exists()


def test_adapter_sukses_menhentikan_pid_word_yang_masih_hidup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    stopped: list[int] = []

    def runner(command: list[str], timeout: int) -> office.WordProcessResult:
        _pid_file_from_command(command).write_text("777\n", encoding="ascii")
        return office.WordProcessResult(0)

    def fake_stop(pid: int) -> bool:
        stopped.append(pid)
        return True

    monkeypatch.setattr(office, "_process_image_name", lambda pid: "WINWORD.EXE")
    monkeypatch.setattr(office, "_stop_word_process", fake_stop)
    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    assert adapter.update_fields(docx) == docx.resolve()
    assert stopped == [777]


def test_adapter_sukses_tidak_menhentikan_pid_bukan_word(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    stopped: list[int] = []

    def runner(command: list[str], timeout: int) -> office.WordProcessResult:
        _pid_file_from_command(command).write_text("777\n", encoding="ascii")
        return office.WordProcessResult(0)

    def fake_stop(pid: int) -> bool:
        stopped.append(pid)
        return True

    monkeypatch.setattr(office, "_process_image_name", lambda pid: "notepad.exe")
    monkeypatch.setattr(office, "_stop_word_process", fake_stop)
    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    assert adapter.update_fields(docx) == docx.resolve()
    assert stopped == []


def test_adapter_sukses_melaporkan_gagal_hentikan_word(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)

    def runner(command: list[str], timeout: int) -> office.WordProcessResult:
        _pid_file_from_command(command).write_text("888\n", encoding="ascii")
        return office.WordProcessResult(0)

    monkeypatch.setattr(office, "_process_image_name", lambda pid: "WINWORD.EXE")
    monkeypatch.setattr(office, "_stop_word_process", lambda pid: False)
    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    with caplog.at_level(logging.WARNING):
        adapter.update_fields(docx)

    assert "gagal menghentikan proses Word PID 888" in caplog.text


@pytest.mark.parametrize(
    "marker",
    [
        "RPC_E_CALL_REJECTED",
        "0x80010001",
        "0x800706BE",
        "Call was rejected by callee",
    ],
)
def test_adapter_retry_transien(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    marker: str,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def runner(command: list[str], timeout: int) -> office.WordProcessResult:
        calls.append(list(command))
        if len(calls) == 1:
            return office.WordProcessResult(1, stderr=f"COM error: {marker}")
        return office.WordProcessResult(0, stdout="[word] STEP done")

    monkeypatch.setattr(office.time, "sleep", sleeps.append)
    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    assert adapter.update_fields(docx, timeout=42) == docx.resolve()
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert sleeps == [1.0]


def test_adapter_lock_busy_dipetakan_ke_word_busy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)

    def busy_lock(timeout: int) -> None:
        raise office._WordBusyError("docgen-word.lock")

    monkeypatch.setattr(office, "_word_lock", busy_lock)
    monkeypatch.setattr(
        office,
        "_run_process",
        lambda command, timeout: office.WordProcessResult(0),
    )
    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
    )

    with pytest.raises(WordError) as error:
        adapter.update_fields(docx)

    assert "WORD-BUSY" in str(error.value)


def test_adapter_runner_none_memakai_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    acquired: list[int] = []

    @contextlib.contextmanager
    def fake_lock(timeout: int):
        acquired.append(timeout)
        yield

    monkeypatch.setattr(office, "_word_lock", fake_lock)
    monkeypatch.setattr(
        office,
        "_run_process",
        lambda command, timeout: office.WordProcessResult(0),
    )
    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
    )

    assert adapter.update_fields(docx) == docx.resolve()
    assert acquired == [30]


def test_adapter_tidak_memakai_lock_untuk_runner_palsu(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)

    def forbidden_lock(timeout: int) -> None:
        raise AssertionError("lock tidak boleh dipakai untuk runner palsu")

    monkeypatch.setattr(office, "_word_lock", forbidden_lock)
    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=lambda command, timeout: office.WordProcessResult(0),
    )

    assert adapter.update_fields(docx) == docx.resolve()


def test_run_process_timeout_menyimpan_log_parsial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code = (
        "import sys, time; "
        "print('[word] STEP toc_update', flush=True); "
        "print('pesan stderr', file=sys.stderr, flush=True); "
        "time.sleep(10)"
    )

    def fake_terminate(process: subprocess.Popen[bytes]) -> None:
        process.kill()
        process.wait(timeout=5)

    monkeypatch.setattr(office, "_terminate_process_tree", fake_terminate)

    with pytest.raises(subprocess.TimeoutExpired) as error:
        office._run_process([sys.executable, "-c", code], 2)

    assert "[word] STEP toc_update" in str(error.value.output)
    assert "pesan stderr" in str(error.value.stderr)


def test_adapter_menolak_hasil_word_yang_bukan_docx(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    script = tmp_path / "word.ps1"
    script.write_text("# stub\n", encoding="utf-8")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)

    def runner(command: list[str], timeout: int) -> int:
        docx.write_bytes(b"bukan-docx")
        return 0

    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=script,
        word_executable="WINWORD.EXE",
        runner=runner,
    )

    with pytest.raises(WordError, match="bukan DOCX valid"):
        adapter.update_fields(docx)


def test_adapter_tanpa_powershell_melempar_tool_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(office, "is_windows", lambda: True)
    monkeypatch.setattr(office, "find_powershell", lambda: None)
    monkeypatch.setattr(office, "find_word_executable", lambda: "WINWORD.EXE")
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)

    adapter = office.WordAdapter(script=tmp_path / "word.ps1", runner=lambda *_: 0)

    with pytest.raises(ToolMissingError):
        adapter.update_fields(docx)


def test_adapter_script_hilang_melempar_word_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _windows_tools(monkeypatch)
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(_ZIP_STUB)
    adapter = office.WordAdapter(
        powershell="powershell.exe",
        script=tmp_path / "tidak-ada.ps1",
        word_executable="WINWORD.EXE",
        runner=lambda *_: 0,
    )

    with pytest.raises(WordError, match=r"word\.ps1 tidak ditemukan"):
        adapter.update_fields(docx)


# ---------------------------------------------------------------------------
# Stage office
# ---------------------------------------------------------------------------


def test_stage_office_sukses(tmp_path: Path) -> None:
    adapter = FakeWordAdapter()
    ctx, docx = _context(tmp_path, adapter=adapter)

    result = office.OfficeStage().run(ctx)

    assert result.stage == StageName.OFFICE.value
    assert result.status == "ok"
    assert result.changed is True
    assert result.artifacts == (docx,)
    assert adapter.calls == [(docx, None)]


def test_path_output_memakai_report_name_tanpa_fallback(tmp_path: Path) -> None:
    ctx, _ = _context(tmp_path)
    ctx.artifacts = None
    ctx.document.metadata.report_name = "Laporan"
    (tmp_path / "Laporan.docx").write_bytes(_ZIP_STUB)

    assert office._docx_path(ctx) == tmp_path / "Laporan.docx"
    assert office._pdf_path(ctx) == tmp_path / "Laporan.pdf"


def test_stage_office_meneruskan_error_word(tmp_path: Path) -> None:
    adapter = FakeWordAdapter(error=WordError("Word rusak"))
    ctx, _ = _context(tmp_path, adapter=adapter)

    with pytest.raises(WordError, match="Word rusak"):
        office.OfficeStage().run(ctx)


def test_stage_office_membungkus_error_tak_dikenal(tmp_path: Path) -> None:
    adapter = FakeWordAdapter(error=RuntimeError("COM meledak"))
    ctx, _ = _context(tmp_path, adapter=adapter)

    with pytest.raises(WordError, match="stage office gagal"):
        office.OfficeStage().run(ctx)


def test_stage_office_skip_tanpa_word_target_docx(tmp_path: Path) -> None:
    adapter = FakeWordAdapter(available=False)
    ctx, _ = _context(tmp_path, target="docx", adapter=adapter)

    result = office.OfficeStage().run(ctx)

    assert result.status == "skipped"
    assert result.changed is False
    assert result.warnings
    assert "DOCX tetap dihasilkan" in result.warnings[0]
    assert adapter.calls == []


def test_stage_office_skip_tanpa_word_target_both_allow(tmp_path: Path) -> None:
    adapter = FakeWordAdapter(available=False)
    ctx, _ = _context(
        tmp_path,
        target="both",
        allow_missing_word=True,
        adapter=adapter,
    )

    result = office.OfficeStage().run(ctx)

    assert result.status == "skipped"
    assert "PDF dilewati" in result.warnings[0]


def test_stage_office_skip_tanpa_word_tidak_butuh_docx(tmp_path: Path) -> None:
    adapter = FakeWordAdapter(available=False)
    ctx, docx = _context(tmp_path, target="docx", adapter=adapter)
    docx.unlink()

    result = office.OfficeStage().run(ctx)

    assert result.status == "skipped"
    assert result.warnings


def test_stage_office_error_tanpa_word_target_both(tmp_path: Path) -> None:
    adapter = FakeWordAdapter(available=False)
    ctx, _ = _context(tmp_path, target="both", adapter=adapter)

    with pytest.raises(ToolMissingError):
        office.OfficeStage().run(ctx)


def test_stage_office_error_tanpa_word_target_pdf_walau_allow(tmp_path: Path) -> None:
    adapter = FakeWordAdapter(available=False)
    ctx, _ = _context(
        tmp_path,
        target="pdf",
        allow_missing_word=True,
        adapter=adapter,
    )

    with pytest.raises(ToolMissingError):
        office.OfficeStage().run(ctx)


def test_stage_office_metadata_urutan() -> None:
    stage = office.OfficeStage()

    assert stage.name == StageName.OFFICE
    assert stage.order == 160
    assert stage.requires == canonical_prefix(StageName.OFFICE)
    assert stage.mutates == frozenset({"package"})
    assert stage.idempotent is False


# ---------------------------------------------------------------------------
# Script PowerShell
# ---------------------------------------------------------------------------


def test_scripts_word_ps1_menggabungkan_update_dan_export() -> None:
    script = _ROOT / "scripts" / "word.ps1"

    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "$PdfPath" in text
    assert "$doc.Fields.Update()" in text
    assert "$doc.TablesOfContents" in text
    assert "$doc.ExportAsFixedFormat($fullPdf, 17)" in text
    assert "[void]$doc.Save()" in text
    assert "ExitCode = 1" in text


def test_word_script_path_mencari_scripts_word_ps1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DOCGEN_WORD_SCRIPT", raising=False)

    assert office.word_script_path() == _ROOT / "scripts" / "word.ps1"


def test_word_script_path_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "word.ps1"
    script.write_text("# test", encoding="utf-8")
    monkeypatch.setenv("DOCGEN_WORD_SCRIPT", str(script))

    assert office.word_script_path() == script
