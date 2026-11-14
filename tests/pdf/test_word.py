"""Tes adapter Word COM memakai fake; tanpa Word, PowerShell, atau jaringan."""

import contextlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from autooffice.pdf import com, word

DOCX_BYTES = b"PK\x03\x04docx-source"
PDF_BYTES = b"%PDF-1.7 fake\n"


class FakeOptions:
    def __init__(self, events: list[str]) -> None:
        object.__setattr__(self, "events", events)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        self.events.append(f"options.{name}={value!r}")


class FakeFields:
    def __init__(self, word_document: FakeDocument) -> None:
        self._document = word_document

    def Update(self) -> None:
        self._document.events.append("fields_update")


class FakeToc:
    def __init__(self, word_document: FakeDocument, index: int) -> None:
        self._document = word_document
        self._index = index

    def Update(self) -> None:
        self._document.events.append(f"toc_update:{self._index}")


class FakeTocCollection:
    def __init__(self, word_document: FakeDocument) -> None:
        self._document = word_document

    @property
    def Count(self) -> int:
        self._document.events.append("toc_count")
        return self._document.word.toc_count

    def Item(self, index: int) -> FakeToc:
        self._document.events.append(f"toc_item:{index}")
        return FakeToc(self._document, index)


class FakeDocument:
    def __init__(self, parent: FakeWord, path: Path) -> None:
        self.parent = parent
        self.path = Path(path)
        self.events = parent.events
        self.word = parent
        parent.opened_path = self.path
        if parent.mutate_on_open:
            self.path.write_bytes(b"PK\x03\x04mutated-snapshot")

    @property
    def ReadOnly(self) -> bool:
        self.events.append("read_only")
        return self.word.read_only

    def Repaginate(self) -> None:
        self.events.append("repaginate")

    @property
    def Fields(self) -> FakeFields:
        self.events.append("fields")
        return FakeFields(self)

    @property
    def TablesOfContents(self) -> FakeTocCollection:
        return FakeTocCollection(self)

    def ExportAsFixedFormat(self, path: str, export_format: int) -> None:
        self.events.append(f"export:{export_format}")
        self.word.exported_pdf = Path(path)
        if self.word.write_export:
            Path(path).write_bytes(self.word.pdf_bytes)

    def Save(self) -> None:
        self.events.append("save")
        with self.path.open("ab") as handle:
            handle.write(b"-saved")

    def Close(self, save_changes: int) -> None:
        self.events.append(f"close:{save_changes}")


class FakeDocuments:
    def __init__(self, parent: FakeWord) -> None:
        self.parent = parent

    def Open(
        self,
        path: str,
        confirm_conversions: bool,
        read_only: bool,
        add_to_recent_files: bool,
    ) -> FakeDocument:
        self.parent.events.append(f"open:{Path(path).name}")
        self.parent.open_arguments = (confirm_conversions, read_only, add_to_recent_files)
        if self.parent.block_open is not None:
            self.parent.block_open.wait(5.0)
            raise RuntimeError("Word dihentikan")
        return FakeDocument(self.parent, Path(path))


class FakeWord:
    def __init__(
        self,
        events: list[str],
        control: FakeProcessControl,
        *,
        read_only: bool = False,
        mutate_on_open: bool = False,
        block_open: threading.Event | None = None,
        toc_count: int = 2,
        pdf_bytes: bytes = PDF_BYTES,
        write_export: bool = True,
        active_window_hwnd: int = 9001,
        quit_leaves_alive: bool = False,
    ) -> None:
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "control", control)
        object.__setattr__(self, "read_only", read_only)
        object.__setattr__(self, "mutate_on_open", mutate_on_open)
        object.__setattr__(self, "block_open", block_open)
        object.__setattr__(self, "toc_count", toc_count)
        object.__setattr__(self, "pdf_bytes", pdf_bytes)
        object.__setattr__(self, "write_export", write_export)
        object.__setattr__(self, "active_window_hwnd", active_window_hwnd)
        object.__setattr__(self, "quit_leaves_alive", quit_leaves_alive)
        object.__setattr__(self, "quit_event", threading.Event())
        self.Options = FakeOptions(events)
        self.Documents = FakeDocuments(self)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        if name in {"AutomationSecurity", "Visible", "DisplayAlerts", "ScreenUpdating"}:
            self.events.append(f"word.{name}={value!r}")

    @property
    def ActiveWindow(self) -> SimpleNamespace:
        """Word hanya punya ``ActiveWindow`` setelah dokumen terbuka."""

        return SimpleNamespace(Hwnd=self.active_window_hwnd)

    def Quit(self) -> None:
        self.events.append("quit")
        if not self.quit_leaves_alive:
            self.control.alive = False
        self.quit_event.set()


class FakeProcessControl:
    """Process control palsu yang meniru gating timeout SystemProcessControl.

    ``SystemProcessControl`` mengembalikan snapshot/image ``None`` dan menolak
    ``taskkill`` saat timeout-nya nol atau negatif. Fake ini meniru perilaku
    tersebut agar cleanup setelah deadline operasi habis tetap teruji.
    """

    def __init__(self, events: list[str], *, initially_alive: bool = False) -> None:
        self.events = events
        self.pid = 4242
        self.preexisting = 1111 if initially_alive else None
        self.alive = False
        self.release = threading.Event()
        self.terminated: list[int] = []
        self.snapshot_ok = True
        self.created_at = 1000
        self.timeout_s = com.CLEANUP_TIMEOUT_S
        self.timeout_at_terminate: float | None = None
        self.window_pids: dict[int, int] = {9001: self.pid}

    def set_timeout(self, timeout_s: float) -> None:
        self.timeout_s = max(0.0, timeout_s)

    def list_word_pids(self) -> set[int] | None:
        self.events.append("list_processes")
        if self.timeout_s <= 0 or not self.snapshot_ok:
            return None
        pids: set[int] = set()
        if self.preexisting is not None:
            pids.add(self.preexisting)
        if self.alive:
            pids.add(self.pid)
        return pids

    def image_name(self, pid: int) -> str | None:
        self.events.append(f"image:{pid}")
        if self.timeout_s <= 0:
            return None
        if pid == self.pid and self.alive:
            return "WINWORD.EXE"
        if pid == self.preexisting:
            return "WINWORD.EXE"
        return None

    def creation_time(self, pid: int) -> int | None:
        if self.timeout_s <= 0:
            return None
        return self.created_at

    def pid_for_window(self, hwnd: int) -> int | None:
        if not self.alive:
            return None
        return self.window_pids.get(hwnd)

    def is_running(self, pid: int) -> bool | None:
        if pid == self.pid:
            return self.alive
        return pid == self.preexisting

    def terminate(self, pid: int) -> bool:
        self.timeout_at_terminate = self.timeout_s
        if self.timeout_s <= 0:
            return False
        self.events.append(f"terminate:{pid}")
        self.terminated.append(pid)
        if pid == self.pid:
            self.alive = False
        self.release.set()
        return True


class FakeClient:
    def __init__(self, application: FakeWord) -> None:
        self.application = application

    def DispatchEx(self, name: str) -> FakeWord:
        self.application.events.append(f"dispatch:{name}")
        self.application.control.alive = True
        return self.application


class FakePythonCom:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def CoInitialize(self) -> None:
        self.events.append("co_initialize")

    def CoUninitialize(self) -> None:
        self.events.append("co_uninitialize")


@dataclass
class FakeEnvironment:
    events: list[str]
    control: FakeProcessControl
    application: FakeWord
    client: FakeClient
    pythoncom: FakePythonCom


def make_environment(**kwargs: Any) -> FakeEnvironment:
    events: list[str] = []
    control = FakeProcessControl(events, initially_alive=kwargs.pop("initially_alive", False))
    application = FakeWord(events, control, **kwargs)
    return FakeEnvironment(
        events=events,
        control=control,
        application=application,
        client=FakeClient(application),
        pythoncom=FakePythonCom(events),
    )


def install(monkeypatch: pytest.MonkeyPatch, environment: FakeEnvironment) -> None:
    monkeypatch.setattr(
        word,
        "load_com_modules",
        lambda: (environment.client, environment.pythoncom),
    )
    monkeypatch.setattr(word, "SystemProcessControl", lambda: environment.control)
    monkeypatch.setattr(word, "com_lock", lambda **_kwargs: contextlib.nullcontext())
    monkeypatch.setattr(
        word,
        "find_word_window_handle",
        lambda pid: (
            environment.application.active_window_hwnd
            if environment.control.window_pids.get(environment.application.active_window_hwnd)
            == pid
            else None
        ),
    )


def test_export_pdf_runs_expected_com_sequence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "out" / "Laporan.pdf"
    environment = make_environment(mutate_on_open=True)
    install(monkeypatch, environment)

    result = word.export_pdf(docx, pdf, timeout_s=5.0)

    assert result == pdf.resolve()
    assert pdf.read_bytes() == PDF_BYTES
    assert docx.read_bytes() == DOCX_BYTES
    assert environment.application.opened_path != docx.resolve()
    assert not environment.application.opened_path.exists()
    assert environment.application.open_arguments == (False, False, False)
    assert not hasattr(environment.application, "Hwnd")
    assert environment.events == [
        "list_processes",
        "co_initialize",
        "dispatch:Word.Application",
        "list_processes",
        "image:4242",
        "image:4242",
        "word.AutomationSecurity=3",
        "options.UpdateLinksAtOpen=False",
        "options.ConfirmConversions=False",
        "word.Visible=False",
        "word.DisplayAlerts=0",
        "word.ScreenUpdating=False",
        "open:source.docx",
        "read_only",
        "repaginate",
        "fields",
        "fields_update",
        "toc_count",
        "toc_item:1",
        "toc_update:1",
        "toc_item:2",
        "toc_update:2",
        "repaginate",
        "export:17",
        "close:0",
        "quit",
        "co_uninitialize",
        "image:4242",
    ]


def test_update_fields_replaces_source_atomically(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    environment = make_environment(toc_count=1)
    install(monkeypatch, environment)

    result = word.update_fields(docx, timeout_s=5.0, visible=True)

    assert result == docx.resolve()
    assert environment.application.opened_path != docx.resolve()
    assert not environment.application.opened_path.exists()
    assert docx.read_bytes() == DOCX_BYTES + b"-saved"
    assert environment.application.open_arguments == (False, False, False)
    assert "word.Visible=True" in environment.events
    assert "save" in environment.events
    assert "export:17" not in environment.events


def test_update_fields_keeps_source_when_com_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_dispatch(name: str) -> Any:
        raise RuntimeError("Word mati")

    monkeypatch.setattr(environment.client, "DispatchEx", fail_dispatch)

    with pytest.raises(word.PdfUnavailableError, match="Microsoft Word"):
        word.update_fields(docx, timeout_s=5.0)

    assert docx.read_bytes() == DOCX_BYTES


def test_export_pdf_timeout_cleans_tracked_word_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment()
    environment.application.block_open = environment.control.release
    claimed: list[int] = []

    # Klaim PID sebelum watchdog berjalan agar timeout tidak bergantung pada
    # balapan antara thread worker dan batas waktu.
    class PreClaimedTracker(com.WordProcessTracker):
        @classmethod
        def begin(cls, control: com.ProcessControl) -> com.WordProcessTracker:
            tracker = super().begin(control)
            environment.control.alive = True
            pid = tracker.claim(hwnd=environment.application.active_window_hwnd)
            assert pid == environment.control.pid
            claimed.append(pid)
            return tracker

    monkeypatch.setattr(word, "WordProcessTracker", PreClaimedTracker)
    install(monkeypatch, environment)

    with pytest.raises(com.WordTimeoutError, match="tidak selesai"):
        word.export_pdf(docx, pdf, timeout_s=0.5)

    assert claimed == [4242]
    assert environment.control.terminated == [4242]
    assert environment.control.timeout_s == com.CLEANUP_TIMEOUT_S
    assert environment.control.timeout_at_terminate == com.CLEANUP_TIMEOUT_S
    assert not pdf.exists()
    assert docx.read_bytes() == DOCX_BYTES
    assert "quit" in environment.events


def test_export_pdf_uses_fixed_cleanup_budget_for_short_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment()
    install(monkeypatch, environment)
    captured: list[dict[str, Any]] = []

    def fake_watchdog(*args: object, **kwargs: object) -> None:
        captured.append(dict(kwargs))
        raise com.WordComError("berhenti setelah argumen watchdog diperiksa")

    monkeypatch.setattr(word, "run_with_watchdog", fake_watchdog)

    with pytest.raises(com.WordComError, match="argumen watchdog"):
        word.export_pdf(docx, pdf, timeout_s=0.5)

    assert captured
    assert 0.0 < captured[0]["timeout_s"] <= 0.5
    assert captured[0]["cleanup_timeout_s"] == 5.0


def test_export_pdf_timeout_before_claim_reports_ambiguous_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment()
    dispatch_started = threading.Event()
    dispatch_release = threading.Event()

    # Worker tertahan sebelum tracker.claim sehingga timeout terjadi tanpa PID
    # yang dapat diidentifikasi untuk cleanup.
    def block_dispatch(name: str) -> FakeWord:
        environment.events.append(f"dispatch:{name}")
        dispatch_started.set()
        # Tahan melewati anggaran cleanup tetap 5 detik agar cleanup ambigu
        # benar-benar teruji; event dilepas di finally.
        dispatch_release.wait(30.0)
        environment.control.alive = True
        return environment.application

    monkeypatch.setattr(environment.client, "DispatchEx", block_dispatch)
    install(monkeypatch, environment)

    try:
        with pytest.raises(com.WordCleanupError, match="Cleanup ambigu") as error:
            word.export_pdf(docx, pdf, timeout_s=0.5)

        assert error.value.cleanup_ambiguous is True
        assert "image:4242" not in environment.events
        assert environment.control.terminated == []
        assert not pdf.exists()
        assert docx.read_bytes() == DOCX_BYTES
    finally:
        dispatch_release.set()

    assert dispatch_started.wait(5.0)
    assert environment.application.quit_event.wait(5.0)
    assert not pdf.exists()


def test_export_pdf_ambiguous_cleanup_preserves_work_dir_and_temp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    work_dir = tmp_path / "word-work"
    work_dir.mkdir()
    temp_pdf = pdf.with_name(".Laporan-deadbeef.pdf")
    temp_pdf.write_bytes(PDF_BYTES)
    monkeypatch.setattr(word.tempfile, "mkdtemp", lambda prefix: str(work_dir))
    monkeypatch.setattr(word.uuid, "uuid4", lambda: SimpleNamespace(hex="deadbeef"))
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_watchdog(*args: object, **kwargs: object) -> None:
        raise com.WordCleanupError("worker Word masih hidup")

    monkeypatch.setattr(word, "run_with_watchdog", fail_watchdog)

    with pytest.raises(com.WordCleanupError, match="worker Word masih hidup"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert work_dir.is_dir()
    assert (work_dir / "source.docx").is_file()
    assert temp_pdf.is_file()
    assert not pdf.exists()


def test_update_fields_ambiguous_cleanup_preserves_work_dir_and_temp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    work_dir = tmp_path / "word-work"
    work_dir.mkdir()
    temp_docx = tmp_path / ".Laporan-deadbeef.docx"
    temp_docx.write_bytes(DOCX_BYTES)
    monkeypatch.setattr(word.tempfile, "mkdtemp", lambda prefix: str(work_dir))
    monkeypatch.setattr(word.uuid, "uuid4", lambda: SimpleNamespace(hex="deadbeef"))
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_watchdog(*args: object, **kwargs: object) -> None:
        raise com.WordCleanupError("worker Word masih hidup")

    monkeypatch.setattr(word, "run_with_watchdog", fail_watchdog)

    with pytest.raises(com.WordCleanupError, match="worker Word masih hidup"):
        word.update_fields(docx, timeout_s=5.0)

    assert work_dir.is_dir()
    assert (work_dir / "source.docx").is_file()
    assert temp_docx.is_file()
    assert docx.read_bytes() == DOCX_BYTES


def test_terminate_tracker_suppresses_timeout_limit_failure() -> None:
    terminated: list[float] = []

    class BrokenControl:
        def set_timeout(self, timeout_s: float) -> None:
            raise RuntimeError("set_timeout rusak")

    class Tracker:
        control = BrokenControl()

        def terminate_owned(self, *, wait_s: float) -> bool:
            terminated.append(wait_s)
            return True

    word._terminate_tracker(Tracker())  # type: ignore[arg-type]

    assert len(terminated) == 1
    assert 0.0 < terminated[0] <= com.CLEANUP_TIMEOUT_S


def test_export_pdf_does_not_kill_preexisting_word_instance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment(initially_alive=True)
    install(monkeypatch, environment)

    result = word.export_pdf(docx, pdf, timeout_s=5.0)

    assert result == pdf.resolve()
    assert environment.control.terminated == []


def test_export_pdf_uses_new_word_pid_not_preexisting_window(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment(initially_alive=True)
    install(monkeypatch, environment)
    observed: list[int] = []

    def select_window(pid: int) -> int:
        observed.append(pid)
        return environment.application.active_window_hwnd

    monkeypatch.setattr(word, "find_word_window_handle", select_window)

    result = word.export_pdf(docx, pdf, timeout_s=5.0)

    assert result == pdf.resolve()
    assert observed == [4242]
    assert environment.control.terminated == []
    assert environment.control.is_running(1111) is True
    assert environment.control.is_running(4242) is False


def test_export_pdf_fails_safely_when_no_word_window_matches_new_pid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment()
    install(monkeypatch, environment)
    monkeypatch.setattr(word, "find_word_window_handle", lambda pid: None)

    with pytest.raises(com.WordOwnershipError, match="Tidak ada window Word"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert "quit" not in environment.events
    assert environment.control.terminated == []
    assert environment.control.is_running(4242) is True
    assert not pdf.exists()


def test_export_pdf_fails_safely_when_no_new_word_pid_appears(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment()
    install(monkeypatch, environment)

    def attach_without_new_process(name: str) -> FakeWord:
        environment.events.append(f"dispatch:{name}")
        return environment.application

    monkeypatch.setattr(environment.client, "DispatchEx", attach_without_new_process)

    with pytest.raises(com.WordOwnershipError, match="tepat satu proses"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert "quit" not in environment.events
    assert environment.control.terminated == []
    assert not pdf.exists()


def test_export_pdf_rejects_word_pid_mismatch_after_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment(active_window_hwnd=9002)
    environment.control.window_pids = {9001: 4242, 9002: 9999}
    install(monkeypatch, environment)
    monkeypatch.setattr(word, "find_word_window_handle", lambda pid: 9001)

    with pytest.raises(com.WordOwnershipError, match="setelah membuka dokumen"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert "quit" in environment.events
    assert environment.control.terminated == []
    assert not pdf.exists()


def test_export_pdf_quits_claimed_word_when_open_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_open(*args: object, **kwargs: object) -> Any:
        raise RuntimeError("open gagal")

    monkeypatch.setattr(environment.application.Documents, "Open", fail_open)

    with pytest.raises(word.WordComError, match="membuka dokumen"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert "quit" in environment.events
    assert environment.control.terminated == []
    assert environment.control.is_running(4242) is False
    assert not pdf.exists()


def test_export_pdf_aborts_before_dispatch_when_snapshot_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment()
    environment.control.snapshot_ok = False
    install(monkeypatch, environment)

    with pytest.raises(com.ProcessSnapshotError, match="Snapshot proses"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert "dispatch:Word.Application" not in environment.events
    assert environment.control.terminated == []
    assert docx.read_bytes() == DOCX_BYTES
    assert not pdf.exists()


def test_export_pdf_lock_wait_uses_derived_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    observed: list[float] = []

    def busy_lock(*, timeout_s: float = com.DEFAULT_LOCK_TIMEOUT_S) -> Any:
        observed.append(timeout_s)
        time.sleep(timeout_s)
        raise com.WordBusyError("lock penuh")

    monkeypatch.setattr(word, "com_lock", busy_lock)

    started = time.monotonic()
    with pytest.raises(com.WordBusyError, match="lock"):
        word.export_pdf(docx, pdf, timeout_s=0.5)
    elapsed = time.monotonic() - started

    assert observed
    assert 0 < observed[0] <= 0.5
    # Batas longgar agar tidak flaky saat mesin sibuk; assertion deadline di
    # atas sudah membuktikan lock memakai sisa timeout operasi.
    assert elapsed < 3.0
    assert docx.read_bytes() == DOCX_BYTES
    assert not pdf.exists()


def test_export_pdf_rejects_read_only_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment(read_only=True)
    install(monkeypatch, environment)

    with pytest.raises(word.WordComError, match="read-only"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert not pdf.exists()
    assert "quit" in environment.events


def test_export_pdf_rejects_invalid_pdf_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment(pdf_bytes=b"bukan pdf")
    install(monkeypatch, environment)

    with pytest.raises(word.WordComError, match="PDF"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert not pdf.exists()


def test_export_pdf_suppresses_temp_unlink_permission_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment(pdf_bytes=b"bukan pdf")
    install(monkeypatch, environment)
    original_unlink = Path.unlink

    def deny_temp_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.suffix.lower() == ".pdf":
            raise PermissionError("masih dipegang Word")
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_temp_unlink)

    with pytest.raises(word.WordComError, match="tidak valid atau kosong"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert not pdf.exists()
    assert docx.read_bytes() == DOCX_BYTES


def test_export_pdf_rejects_invalid_timeout(tmp_path: Path) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"

    with pytest.raises(ValueError, match="timeout_s"):
        word.export_pdf(docx, pdf, timeout_s=0)


def test_export_pdf_reports_non_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    monkeypatch.setattr(com, "_platform", lambda: "linux")
    monkeypatch.setattr(word, "com_lock", lambda **_kwargs: contextlib.nullcontext())

    with pytest.raises(com.PdfUnavailableError, match="Windows"):
        word.export_pdf(docx, pdf)


def test_update_fields_reports_missing_pywin32(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)

    def missing(name: str) -> Any:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(com, "_platform", lambda: "win32")
    monkeypatch.setattr(com, "_import_module", missing)
    monkeypatch.setattr(word, "com_lock", lambda **_kwargs: contextlib.nullcontext())

    with pytest.raises(com.PdfUnavailableError, match="pywin32"):
        word.update_fields(docx)


def test_export_pdf_rejects_missing_docx(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="tidak ditemukan"):
        word.export_pdf(tmp_path / "Hilang.docx", tmp_path / "Hilang.pdf")


def test_export_pdf_rejects_directory_as_docx(tmp_path: Path) -> None:
    folder = tmp_path / "Folder.docx"
    folder.mkdir()

    with pytest.raises(ValueError, match="bukan berkas DOCX"):
        word.export_pdf(folder, tmp_path / "out.pdf")


def test_export_pdf_rejects_non_docx_suffix(tmp_path: Path) -> None:
    source = tmp_path / "Laporan.txt"
    source.write_bytes(DOCX_BYTES)

    with pytest.raises(ValueError, match="\\.docx"):
        word.export_pdf(source, tmp_path / "out.pdf")


def test_export_pdf_rejects_non_pdf_suffix(tmp_path: Path) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)

    with pytest.raises(ValueError, match="\\.pdf"):
        word.export_pdf(docx, tmp_path / "out.txt")


def test_export_pdf_wraps_docx_resolve_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_resolve(self: Path, *args: Any, **kwargs: Any) -> Path:
        raise OSError("path rusak")

    monkeypatch.setattr(Path, "resolve", fail_resolve)

    with pytest.raises(ValueError, match="Path DOCX tidak valid"):
        word.export_pdf(tmp_path / "Laporan.docx", tmp_path / "Laporan.pdf")


def test_export_pdf_wraps_pdf_resolve_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    calls = 0

    def fail_second(self: Path, *args: Any, **kwargs: Any) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("path PDF rusak")
        return self

    monkeypatch.setattr(Path, "resolve", fail_second)

    with pytest.raises(ValueError, match="Path PDF tidak valid"):
        word.export_pdf(docx, tmp_path / "Laporan.pdf")


def test_export_pdf_reports_pdf_directory_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)

    def fail_mkdir(self: Path, *args: Any, **kwargs: Any) -> None:
        raise OSError("disk penuh")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    with pytest.raises(word.WordComError, match="Direktori PDF"):
        word.export_pdf(docx, tmp_path / "out" / "Laporan.pdf")


def test_export_pdf_reports_word_dispatch_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_dispatch(name: str) -> Any:
        raise RuntimeError("Word tidak ada")

    monkeypatch.setattr(environment.client, "DispatchEx", fail_dispatch)

    with pytest.raises(word.PdfUnavailableError, match="Microsoft Word"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert not pdf.exists()


def test_export_pdf_reports_missing_pdf_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment(write_export=False)
    install(monkeypatch, environment)

    with pytest.raises(word.WordComError, match="PDF tidak dapat dibaca"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert not pdf.exists()


def test_export_pdf_wraps_pdf_replace_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    docx = tmp_path / "Laporan.docx"
    docx.write_bytes(DOCX_BYTES)
    pdf = tmp_path / "Laporan.pdf"
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("target terkunci")

    monkeypatch.setattr(word.os, "replace", fail_replace)

    with pytest.raises(word.WordComError, match="Gagal menulis PDF"):
        word.export_pdf(docx, pdf, timeout_s=5.0)

    assert not pdf.exists()
