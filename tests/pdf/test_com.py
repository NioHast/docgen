"""Tes guard COM, watchdog, dan cleanup proses tanpa Word nyata."""

import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from autooffice.pdf import com


class FakeClock:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class FakeApartment:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def CoInitialize(self) -> None:
        self.calls.append("init")

    def CoUninitialize(self) -> None:
        self.calls.append("uninit")


class FakeProcessControl:
    """Process control dengan snapshot, window handle, dan creation time palsu."""

    def __init__(
        self,
        snapshots: list[set[int] | None],
        *,
        image: str = "WINWORD.EXE",
        terminate_result: bool = True,
        hwnd_pid: int | None = None,
        creation_time: int = 1000,
    ) -> None:
        self._snapshots = iter(snapshots)
        self.image = image
        self.terminate_result = terminate_result
        self.hwnd_pid = hwnd_pid
        self.creation_time_value = creation_time
        self.creation_times: dict[int, int] = {}
        self.terminated: list[int] = []

    def list_word_pids(self) -> set[int] | None:
        return next(self._snapshots)

    def list_powerpoint_pids(self) -> set[int] | None:
        return next(self._snapshots)

    def image_name(self, pid: int) -> str | None:
        return self.image

    def creation_time(self, pid: int) -> int | None:
        return self.creation_times.get(pid, self.creation_time_value)

    def pid_for_window(self, hwnd: int) -> int | None:
        return self.hwnd_pid

    def terminate(self, pid: int) -> bool:
        self.terminated.append(pid)
        return self.terminate_result


def test_load_com_modules_rejects_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(com, "_platform", lambda: "linux")

    with pytest.raises(com.PdfUnavailableError, match="Windows"):
        com.load_com_modules()


def test_load_com_modules_requires_pywin32(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> Any:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(com, "_platform", lambda: "win32")
    monkeypatch.setattr(com, "_import_module", missing)

    with pytest.raises(com.PdfUnavailableError, match="pywin32"):
        com.load_com_modules()


def test_load_com_modules_imports_client_and_pythoncom(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinels = {"win32com.client": object(), "pythoncom": object()}
    calls: list[str] = []

    def fake_import(name: str) -> Any:
        calls.append(name)
        return sentinels[name]

    monkeypatch.setattr(com, "_platform", lambda: "win32")
    monkeypatch.setattr(com, "_import_module", fake_import)

    client, pythoncom = com.load_com_modules()

    assert client is sentinels["win32com.client"]
    assert pythoncom is sentinels["pythoncom"]
    assert calls == ["win32com.client", "pythoncom"]


def test_com_apartment_initializes_and_uninitializes() -> None:
    apartment = FakeApartment()

    with com.com_apartment(apartment):
        assert apartment.calls == ["init"]

    assert apartment.calls == ["init", "uninit"]


def test_com_apartment_uninitializes_on_error() -> None:
    apartment = FakeApartment()

    with (
        pytest.raises(RuntimeError, match="gagal"),
        com.com_apartment(apartment),
    ):
        raise RuntimeError("gagal")

    assert apartment.calls == ["init", "uninit"]


def test_com_apartment_wraps_initialization_failure() -> None:
    class BrokenApartment:
        def CoInitialize(self) -> None:
            raise OSError("COM rusak")

        def CoUninitialize(self) -> None:
            raise AssertionError("tidak boleh dipanggil")

    with (
        pytest.raises(com.PdfUnavailableError, match="COM Windows"),
        com.com_apartment(BrokenApartment()),
    ):
        raise AssertionError("tidak boleh masuk")


def test_deadline_check_raises_when_budget_is_exhausted() -> None:
    deadline = com.Deadline.start(1.0, clock=FakeClock(10.0, 12.0))

    with pytest.raises(com.WordTimeoutError, match="open"):
        deadline.check("open")


def test_deadline_remaining_uses_injected_clock() -> None:
    deadline = com.Deadline.start(10.0, clock=FakeClock(100.0, 102.5))

    assert deadline.remaining() == pytest.approx(7.5)


def test_deadline_check_accepts_remaining_budget() -> None:
    deadline = com.Deadline.start(10.0, clock=FakeClock(1.0, 2.0, 3.0))

    deadline.check("open")

    assert deadline.remaining() == pytest.approx(8.0)


def test_deadline_remaining_or_raise_returns_positive_budget() -> None:
    deadline = com.Deadline.start(10.0, clock=FakeClock(1.0, 2.0))

    assert deadline.remaining_or_raise("open") == pytest.approx(9.0)


def test_deadline_remaining_or_raise_rejects_race_to_negative_budget() -> None:
    deadline = com.Deadline.start(10.0, clock=FakeClock(1.0, 11.5))

    with pytest.raises(com.WordTimeoutError, match="open"):
        deadline.remaining_or_raise("open")


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("inf"), float("nan")])
def test_validate_timeout_rejects_invalid_values(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout_s"):
        com.validate_timeout(timeout)


def test_com_lock_is_noop_outside_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(com, "_is_windows", lambda: False)
    lock_path = tmp_path / "com.lock"

    with com.com_lock(lock_path=lock_path):
        assert not lock_path.exists()

    assert not lock_path.exists()


def test_com_lock_serializes_on_windows(tmp_path: Path) -> None:
    if not com._is_windows():
        pytest.skip("lock file hanya dipakai di Windows")
    lock_path = tmp_path / "com.lock"

    with com.com_lock(timeout_s=5.0, lock_path=lock_path):
        assert lock_path.exists()

    with com.com_lock(timeout_s=5.0, lock_path=lock_path):
        assert lock_path.exists()


def test_com_lock_reports_busy_after_timeout(tmp_path: Path) -> None:
    if not com._is_windows():
        pytest.skip("lock file hanya dipakai di Windows")
    lock_path = tmp_path / "com.lock"

    with (
        com.com_lock(timeout_s=5.0, lock_path=lock_path),
        pytest.raises(com.WordBusyError, match="lock"),
        com.com_lock(timeout_s=0.01, lock_path=lock_path),
    ):
        raise AssertionError("lock kedua tidak boleh masuk")


def test_tracker_claims_window_pid_not_lowest_new_pid() -> None:
    control = FakeProcessControl(
        [{100}, {100, 150, 200}],
        hwnd_pid=200,
        creation_time=500,
    )
    tracker = com.WordProcessTracker.begin(control)

    assert tracker.claim(hwnd=9001) == 200
    assert tracker.pid == 200
    assert tracker.terminate_owned() is True
    assert control.terminated == [200]
    assert tracker.terminate_owned() is False


def test_tracker_does_not_claim_when_window_pid_missing() -> None:
    control = FakeProcessControl([{100}, {100, 200}])
    tracker = com.WordProcessTracker.begin(control)

    assert tracker.claim(hwnd=None) is None
    assert tracker.claim(hwnd=9001) is None
    assert tracker.terminate_owned() is False
    assert control.terminated == []


def test_tracker_does_not_claim_when_window_lookup_fails() -> None:
    class BrokenControl(FakeProcessControl):
        def pid_for_window(self, hwnd: int) -> int | None:
            raise RuntimeError("GetWindowThreadProcessId gagal")

    control = BrokenControl([set(), {200}])
    tracker = com.WordProcessTracker.begin(control)

    assert tracker.claim(hwnd=9001) is None
    assert tracker.terminate_owned() is False
    assert control.terminated == []


def test_tracker_does_not_claim_when_after_snapshot_fails() -> None:
    control = FakeProcessControl(
        [{100}, None],
        hwnd_pid=200,
    )
    tracker = com.WordProcessTracker.begin(control)

    assert tracker.claim(hwnd=9001) is None
    assert tracker.terminate_owned() is False
    assert control.terminated == []


def test_tracker_begin_aborts_when_baseline_snapshot_fails() -> None:
    control = FakeProcessControl([None], hwnd_pid=200)

    with pytest.raises(com.ProcessSnapshotError, match="Snapshot proses"):
        com.WordProcessTracker.begin(control)


def test_tracker_ignores_user_office_started_after_begin() -> None:
    control = FakeProcessControl(
        [{100}, {100, 300, 4242}],
        hwnd_pid=4242,
        creation_time=500,
    )
    tracker = com.WordProcessTracker.begin(control)

    assert tracker.claim(hwnd=9001) == 4242
    assert tracker.terminate_owned() is True
    assert control.terminated == [4242]


def test_tracker_does_not_terminate_reused_pid_creation_time() -> None:
    control = FakeProcessControl([set(), {200}], hwnd_pid=200, creation_time=500)
    tracker = com.WordProcessTracker.begin(control)
    assert tracker.claim(hwnd=9001) == 200

    # PID 200 sudah dipakai ulang: image sama tetapi creation time berbeda.
    control.creation_times[200] = 501

    assert tracker.terminate_owned() is False
    assert control.terminated == []


def test_tracker_does_not_terminate_reused_pid_image() -> None:
    control = FakeProcessControl([set(), {200}], hwnd_pid=200)
    tracker = com.WordProcessTracker.begin(control)

    assert tracker.claim(hwnd=9001) == 200
    control.image = "EXCEL.EXE"
    assert tracker.terminate_owned() is False
    assert control.terminated == []


def test_tracker_does_not_terminate_when_creation_time_unavailable() -> None:
    control = FakeProcessControl([set(), {200}], hwnd_pid=200)
    tracker = com.WordProcessTracker.begin(control)

    assert tracker.claim(hwnd=9001) == 200
    control.creation_times[200] = None  # type: ignore[assignment]
    assert tracker.terminate_owned() is False
    assert control.terminated == []


def test_tracker_reports_failed_terminate() -> None:
    control = FakeProcessControl(
        [set(), {200}],
        hwnd_pid=200,
        terminate_result=False,
    )
    tracker = com.WordProcessTracker.begin(control)

    assert tracker.claim(hwnd=9001) == 200
    assert tracker.terminate_owned() is False
    assert control.terminated == [200]


def test_tracker_does_not_claim_preexisting_pid_from_window() -> None:
    control = FakeProcessControl([{200}, {200}], hwnd_pid=200)
    tracker = com.WordProcessTracker.begin(control)

    assert tracker.claim(hwnd=9001) is None
    assert tracker.terminate_owned() is False
    assert control.terminated == []


def test_tasklist_subprocess_timeout_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(com.subprocess, "run", fake_run)

    assert com._tasklist_rows(timeout_s=0.25) == []
    assert captured["timeout"] == pytest.approx(0.25)


def test_tasklist_timeout_does_not_exceed_small_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(com.subprocess, "run", fake_run)

    assert com._tasklist_rows(timeout_s=0.05) == []
    assert captured["timeout"] == pytest.approx(0.05)


def test_taskkill_timeout_does_not_exceed_small_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        captured.update(kwargs)
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(com.subprocess, "run", fake_run)
    control = com.SystemProcessControl(timeout_s=0.05)

    assert control.terminate(4242) is True
    assert captured["timeout"] == pytest.approx(0.05)


def test_word_cleanup_error_is_not_timeout_error() -> None:
    assert issubclass(com.WordCleanupError, com.WordComError)
    assert not issubclass(com.WordCleanupError, com.WordTimeoutError)
    assert com.WordCleanupError("cleanup ambigu").cleanup_ambiguous is True


def test_find_word_window_handle_selects_matching_pid_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("Enumerasi window hanya relevan di Windows")
    windows = {7001: 1111, 7002: 1111, 9001: 4242}
    classes = {7001: "OpusApp", 7002: "OpusApp", 9001: "OpusApp", 8001: "IEFrame"}

    class FakeWin32Gui:
        @staticmethod
        def EnumWindows(callback: Any, extra: object) -> None:
            for hwnd in [*windows, 8001]:
                callback(hwnd, extra)

        @staticmethod
        def GetClassName(hwnd: int) -> str:
            return classes[hwnd]

    monkeypatch.setattr(com, "_import_module", lambda name: FakeWin32Gui())
    monkeypatch.setattr(com, "_window_process_id", lambda hwnd: windows.get(hwnd))

    assert com.find_word_window_handle(4242) == 9001
    assert com.find_word_window_handle(1111) == 7001
    assert com.find_word_window_handle(9999) is None


def test_application_window_handle_accepts_positive_hwnd() -> None:
    assert com.application_window_handle(SimpleNamespace(Hwnd=1234)) == 1234


def test_application_window_handle_rejects_zero_and_errors() -> None:
    class Broken:
        @property
        def Hwnd(self) -> int:
            raise ValueError("tidak ada window")

    assert com.application_window_handle(SimpleNamespace(Hwnd=0)) is None
    assert com.application_window_handle(Broken()) is None
    assert com.application_window_handle(object()) is None


def test_limit_process_control_calls_set_timeout() -> None:
    calls: list[float] = []

    class Control:
        def set_timeout(self, timeout_s: float) -> None:
            calls.append(timeout_s)

    com.limit_process_control(Control(), -1.0)  # type: ignore[arg-type]

    assert calls == [0.0]


def test_system32_tool_rejects_missing_system_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("System32 hanya relevan di Windows")
    monkeypatch.delenv("SYSTEMROOT", raising=False)
    monkeypatch.delenv("WINDIR", raising=False)
    monkeypatch.setattr(com, "_windows_system_directory", lambda: None)

    with pytest.raises(OSError, match="SystemRoot"):
        com._system32_tool("tasklist.exe")


def test_system32_tool_rejects_relative_system_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("System32 hanya relevan di Windows")
    monkeypatch.setenv("SYSTEMROOT", "Windows")
    monkeypatch.delenv("WINDIR", raising=False)
    monkeypatch.setattr(com, "_windows_system_directory", lambda: None)

    with pytest.raises(OSError, match="SystemRoot"):
        com._system32_tool("tasklist.exe")


def test_system32_tool_uses_get_system_directory_for_relative_system_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("System32 hanya relevan di Windows")
    system32 = tmp_path / "Windows" / "System32"
    system32.mkdir(parents=True)
    monkeypatch.setenv("SYSTEMROOT", "Windows")
    monkeypatch.delenv("WINDIR", raising=False)
    monkeypatch.setattr(com, "_is_32bit_process", lambda: False)
    monkeypatch.setattr(com, "_windows_system_directory", lambda: system32)

    assert Path(com._system32_tool("tasklist.exe")) == system32 / "tasklist.exe"


def test_tasklist_rows_returns_none_when_tool_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(name: str) -> str:
        raise OSError("tidak ada SystemRoot")

    monkeypatch.setattr(com, "_system32_tool", fail)

    assert com._tasklist_rows() is None


def test_system_process_control_delegates_creation_and_window_seams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(com, "_process_creation_time", lambda pid: 777)
    monkeypatch.setattr(com, "_window_process_id", lambda hwnd: 888)
    control = com.SystemProcessControl(timeout_s=1.0)
    control.set_timeout(2.0)

    assert control.creation_time(10) == 777
    assert control.pid_for_window(20) == 888


def test_process_creation_time_for_current_process() -> None:
    if os.name != "nt":
        pytest.skip("creation time hanya tersedia di Windows")

    ticks = com._process_creation_time(os.getpid())

    assert ticks is not None
    assert ticks > 0


def test_window_process_id_reads_win32_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("GetWindowThreadProcessId hanya ada di Windows")
    import ctypes

    class FakeFunction:
        argtypes: object = None
        restype: object = None

        def __init__(self, result: int, pid: int = 0) -> None:
            self.result = result
            self.pid = pid

        def __call__(self, hwnd: object, pointer: Any) -> int:
            pointer._obj.value = self.pid
            return self.result

    class FakeUser32:
        def __init__(self, function: FakeFunction) -> None:
            self.GetWindowThreadProcessId = function

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *args, **kwargs: FakeUser32(FakeFunction(1, 4242)),
    )

    assert com._window_process_id(123) == 4242

    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *args, **kwargs: FakeUser32(FakeFunction(0, 0)),
    )
    assert com._window_process_id(123) is None


def test_system_process_control_parses_tasklist(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        commands.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout='"WINWORD.EXE","4242","Console","1","100 K"\n',
        )

    monkeypatch.setattr(com.subprocess, "run", fake_run)
    control = com.SystemProcessControl()

    assert control.list_word_pids() == {4242}
    assert control.image_name(4242) == "WINWORD.EXE"
    assert control.terminate(4242) is True
    assert commands[0][1:4] == ["/FI", "IMAGENAME eq WINWORD.EXE", "/FO"]
    if os.name == "nt":
        assert Path(commands[0][0]).is_absolute()


def test_system_process_control_survives_tasklist_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError("tasklist tidak tersedia")

    monkeypatch.setattr(com.subprocess, "run", fail)
    control = com.SystemProcessControl()

    assert control.list_word_pids() is None
    assert control.image_name(1) is None
    assert control.terminate(1) is False


def test_tasklist_rows_skips_non_csv_and_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = iter(
        [
            SimpleNamespace(returncode=0, stdout='INFO: tidak ada proses\n"WINWORD.EXE","1"\n'),
            SimpleNamespace(returncode=1, stdout=""),
        ]
    )

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        return next(outputs)

    monkeypatch.setattr(com.subprocess, "run", fake_run)

    assert com._tasklist_rows() == [["WINWORD.EXE", "1"]]
    assert com._tasklist_rows() is None


def test_system_process_control_skips_malformed_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> Any:
        return SimpleNamespace(
            returncode=0,
            stdout=('"EXCEL.EXE","10"\n"WINWORD.EXE","bukan-angka"\n"WINWORD.EXE"\n'),
        )

    monkeypatch.setattr(com.subprocess, "run", fake_run)
    control = com.SystemProcessControl()

    assert control.list_word_pids() == set()
    assert control.image_name(4242) is None


def test_tasklist_uses_absolute_system32_path_not_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("tasklist hanya dipakai di Windows")
    fake_in_cwd = tmp_path / "tasklist.exe"
    fake_in_cwd.write_bytes(b"fake")
    system32 = tmp_path / "Windows" / "System32"
    system32.mkdir(parents=True)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        commands.append(list(command))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setenv("SYSTEMROOT", str(tmp_path / "Windows"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(com, "_is_32bit_process", lambda: False)
    monkeypatch.setattr(com.subprocess, "run", fake_run)

    assert com._tasklist_rows() == []
    assert Path(commands[0][0]) == system32 / "tasklist.exe"
    assert Path(commands[0][0]) != fake_in_cwd
    assert Path(commands[0][0]).is_absolute()


def test_taskkill_uses_absolute_system32_path_and_force_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("taskkill hanya dipakai di Windows")
    fake_in_cwd = tmp_path / "taskkill.exe"
    fake_in_cwd.write_bytes(b"fake")
    system32 = tmp_path / "Windows" / "System32"
    system32.mkdir(parents=True)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        commands.append(list(command))
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setenv("SYSTEMROOT", str(tmp_path / "Windows"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(com, "_is_32bit_process", lambda: False)
    monkeypatch.setattr(com.subprocess, "run", fake_run)

    assert com.SystemProcessControl().terminate(4242) is True
    executable = Path(commands[0][0])
    assert executable == system32 / "taskkill.exe"
    assert executable.is_absolute()
    assert executable.parent.name in {"System32", "Sysnative"}
    assert executable != fake_in_cwd
    assert commands[0][1:] == ["/PID", "4242", "/T", "/F"]


def test_taskkill_nonzero_is_success_when_pid_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        com.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )
    monkeypatch.setattr(com, "_tasklist_rows", lambda *args, **kwargs: [])

    assert com.SystemProcessControl(timeout_s=1.0).terminate(4242) is True


def test_taskkill_nonzero_stays_failure_when_pid_is_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        com.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )
    monkeypatch.setattr(
        com,
        "_tasklist_rows",
        lambda *args, **kwargs: [["WINWORD.EXE", "4242", "Console", "1", "100 K"]],
    )

    assert com.SystemProcessControl(timeout_s=1.0).terminate(4242) is False


def test_taskkill_nonzero_stays_failure_when_pid_cannot_be_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        com.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )
    monkeypatch.setattr(com, "_tasklist_rows", lambda *args, **kwargs: None)

    assert com.SystemProcessControl(timeout_s=1.0).terminate(4242) is False


class _NonzeroTaskkillControl:
    """Control with taskkill nonzero result and a verifiable PID status."""

    def __init__(self, *, process_gone: bool) -> None:
        self.pid = 4242
        self.alive = False
        self.process_gone = process_gone
        self.terminated: list[int] = []
        self.timeout_s = com.CLEANUP_TIMEOUT_S

    def set_timeout(self, timeout_s: float) -> None:
        self.timeout_s = max(0.0, timeout_s)

    def list_word_pids(self) -> set[int] | None:
        return {self.pid} if self.alive else set()

    def image_name(self, pid: int) -> str | None:
        return com.WORD_IMAGE if self.alive else None

    def creation_time(self, pid: int) -> int | None:
        return 1000 if self.alive else None

    def pid_for_window(self, hwnd: int) -> int | None:
        return self.pid if self.alive else None

    def terminate(self, pid: int) -> bool:
        self.terminated.append(pid)
        if self.process_gone:
            self.alive = False
        return False

    def is_running(self, pid: int) -> bool | None:
        return self.alive


def _claim_control(control: _NonzeroTaskkillControl) -> com.WordProcessTracker:
    tracker = com.WordProcessTracker(
        control=control,
        image=com.WORD_IMAGE,
        before=set(),
        list_pids=control.list_word_pids,
    )
    control.alive = True
    assert tracker.claim(hwnd=1) == control.pid
    return tracker


def test_watchdog_timeout_accepts_nonzero_taskkill_when_pid_is_gone() -> None:
    control = _NonzeroTaskkillControl(process_gone=True)
    tracker = _claim_control(control)
    release = threading.Event()

    try:
        with pytest.raises(com.WordTimeoutError) as error:
            com.run_with_watchdog(
                lambda: release.wait(5.0),
                timeout_s=0.01,
                on_timeout=lambda: tracker.terminate_owned(wait_s=0.0),
                cleanup_timeout_s=0.01,
                description="uji",
            )
    finally:
        release.set()

    assert not isinstance(error.value, com.WordCleanupError)
    assert control.terminated == [4242]


def test_watchdog_timeout_raises_cleanup_error_when_pid_remains() -> None:
    control = _NonzeroTaskkillControl(process_gone=False)
    tracker = _claim_control(control)
    release = threading.Event()

    try:
        with pytest.raises(com.WordCleanupError, match="Cleanup ambigu"):
            com.run_with_watchdog(
                lambda: release.wait(5.0),
                timeout_s=0.01,
                on_timeout=lambda: tracker.terminate_owned(wait_s=0.0),
                cleanup_timeout_s=0.01,
                description="uji",
            )
    finally:
        release.set()

    assert control.terminated == [4242]


def test_system32_tool_prefers_sysnative_for_32bit_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("Sysnative hanya relevan di Windows")
    root = tmp_path / "Windows"
    (root / "Sysnative").mkdir(parents=True)
    monkeypatch.setenv("SYSTEMROOT", str(root))
    monkeypatch.setattr(com, "_is_32bit_process", lambda: True)

    assert Path(com._system32_tool("tasklist.exe")) == root / "Sysnative" / "tasklist.exe"


def test_system32_tool_falls_back_to_system32_without_sysnative(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("System32 hanya relevan di Windows")
    root = tmp_path / "Windows"
    (root / "System32").mkdir(parents=True)
    monkeypatch.setenv("SYSTEMROOT", str(root))
    monkeypatch.setattr(com, "_is_32bit_process", lambda: True)

    assert Path(com._system32_tool("tasklist.exe")) == root / "System32" / "tasklist.exe"


def test_run_with_watchdog_returns_result() -> None:
    result = com.run_with_watchdog(
        lambda: 42,
        timeout_s=1.0,
        on_timeout=lambda: None,
        description="uji",
    )

    assert result == 42


def test_run_with_watchdog_propagates_operation_error() -> None:
    def operation() -> None:
        raise ValueError("gagal")

    with pytest.raises(ValueError, match="gagal"):
        com.run_with_watchdog(
            operation,
            timeout_s=1.0,
            on_timeout=lambda: None,
            description="uji",
        )


def test_run_with_watchdog_calls_cleanup_on_timeout() -> None:
    release = threading.Event()
    cleaned: list[str] = []

    def operation() -> None:
        release.wait(5.0)

    def on_timeout() -> None:
        cleaned.append("cleanup")
        release.set()

    with pytest.raises(com.WordTimeoutError, match="uji tidak selesai"):
        com.run_with_watchdog(
            operation,
            timeout_s=0.01,
            on_timeout=on_timeout,
            description="uji",
        )

    assert cleaned == ["cleanup"]


def test_run_with_watchdog_waits_for_worker_before_return(tmp_path: Path) -> None:
    sentinel = tmp_path / "sentinel.txt"
    release = threading.Event()
    written = threading.Event()

    def operation() -> None:
        release.wait(5.0)
        sentinel.write_text("late", encoding="utf-8")
        written.set()

    def on_timeout() -> None:
        release.set()

    with pytest.raises(com.WordTimeoutError, match="tidak selesai"):
        com.run_with_watchdog(
            operation,
            timeout_s=0.01,
            on_timeout=on_timeout,
            cleanup_timeout_s=1.0,
            description="uji",
        )

    # Worker sudah selesai sebelum fungsi kembali: tulisan terjadi, dan tidak
    # ada thread autooffice-com yang masih hidup untuk menulis susulan.
    assert written.is_set()
    assert sentinel.read_text(encoding="utf-8") == "late"
    assert [
        thread.name
        for thread in threading.enumerate()
        if thread.name == "autooffice-com" and thread.is_alive()
    ] == []


def test_run_with_watchdog_raises_ambiguous_cleanup_when_worker_stays_alive(
    tmp_path: Path,
) -> None:
    release = threading.Event()
    written = threading.Event()
    sentinel = tmp_path / "sentinel.txt"

    def operation() -> None:
        release.wait(5.0)
        sentinel.write_text("late", encoding="utf-8")
        written.set()

    try:
        with pytest.raises(com.WordCleanupError, match="Cleanup ambigu"):
            com.run_with_watchdog(
                operation,
                timeout_s=0.01,
                on_timeout=lambda: None,
                cleanup_timeout_s=0.01,
                description="uji",
            )
        # Worker yang masih hidup dapat menulis setelah error; ini alasan
        # cleanup ambigu tidak boleh dilanjutkan dengan menghapus temp.
        release.set()
    finally:
        release.set()

    assert written.wait(1.0)
    assert sentinel.read_text(encoding="utf-8") == "late"
