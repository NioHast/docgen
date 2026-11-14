# mypy: disable-error-code="import-untyped"
"""Tes fake-COM harness visual PPTX; tidak membutuhkan Microsoft PowerPoint."""

import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from autooffice.pdf import com
from autooffice.pdf.com import PowerPointProcessTracker, WordCleanupError, WordComError
from tools.visual import render_pptx

pytestmark = pytest.mark.unit

_APPLICATION_HWND = 9001
_AUTOMATION_PID = 4242


class _FakeSlide:
    def __init__(self, presentation: _FakePresentation, index: int) -> None:
        self._presentation = presentation
        self._index = index

    def Export(self, path: str, image_filter: str, width: int, height: int) -> None:
        self._presentation.export_slide(
            self._index,
            Path(path),
            image_filter,
            width,
            height,
        )


class _FakeSlides:
    def __init__(self, presentation: _FakePresentation) -> None:
        self._presentation = presentation
        self.Count = presentation.slide_count

    def Item(self, index: int) -> _FakeSlide:
        return _FakeSlide(self._presentation, index)


class _FakePresentation:
    def __init__(self, application: _FakePowerPoint) -> None:
        self._application = application
        self.slide_count = application.slide_count
        self.Slides = _FakeSlides(self)

    def Close(self) -> None:
        self._application.events.append("close")

    def export_slide(
        self,
        index: int,
        path: Path,
        image_filter: str,
        width: int,
        height: int,
    ) -> None:
        self._application.events.append(f"export:{index}")
        if index == self._application.fail_on_slide:
            raise RuntimeError("export gagal")
        if index == self._application.block_on_slide:
            self._application.export_started.set()
            self._application.release_export.wait()
        path.write_bytes(f"fake-png-{index}".encode())


class _FakePresentations:
    def __init__(self, application: _FakePowerPoint) -> None:
        self._application = application

    def Open(
        self,
        path: str,
        read_only: bool,
        untitled: bool,
        with_window: bool,
    ) -> _FakePresentation:
        self._application.events.append(f"open:{Path(path).name}")
        self._application.open_arguments = (read_only, untitled, with_window)
        return self._application.presentation


class _FakePowerPoint:
    def __init__(
        self,
        control: _FakeProcessControl,
        *,
        slide_count: int = 2,
        fail_on_slide: int | None = None,
        block_on_slide: int | None = None,
    ) -> None:
        self.Hwnd = _APPLICATION_HWND
        self.events: list[str] = []
        self.control = control
        self.slide_count = slide_count
        self.fail_on_slide = fail_on_slide
        self.block_on_slide = block_on_slide
        self.export_started = threading.Event()
        self.release_export = threading.Event()
        self.quit_event = threading.Event()
        self.presentation = _FakePresentation(self)
        self.Presentations = _FakePresentations(self)
        self.DisplayAlerts: int | None = None
        self.open_arguments: tuple[bool, bool, bool] | None = None

    def Quit(self) -> None:
        self.events.append("quit")
        self.control.automation_alive = False
        self.quit_event.set()


class _FakeProcessControl:
    def __init__(self) -> None:
        self.pid = _AUTOMATION_PID
        self.automation_alive = False
        self.terminated: list[int] = []
        self.window_handles: list[int] = []

    def list_powerpoint_pids(self) -> set[int] | None:
        return {self.pid} if self.automation_alive else set()

    def image_name(self, pid: int) -> str | None:
        if self.automation_alive and pid == self.pid:
            return "POWERPNT.EXE"
        return None

    def creation_time(self, pid: int) -> int | None:
        return 1000 if pid == self.pid else None

    def pid_for_window(self, hwnd: int) -> int | None:
        self.window_handles.append(hwnd)
        return self.pid if self.automation_alive else None

    def terminate(self, pid: int) -> bool:
        self.terminated.append(pid)
        self.automation_alive = False
        return True


class _FakeClient:
    def __init__(self, application: _FakePowerPoint) -> None:
        self.application = application

    def DispatchEx(self, name: str) -> _FakePowerPoint:
        self.application.events.append(f"dispatch:{name}")
        self.application.control.automation_alive = True
        return self.application


class _FakePythonCom:
    def CoInitialize(self) -> None:
        pass

    def CoUninitialize(self) -> None:
        pass


@dataclass(frozen=True, slots=True)
class _FakeEnvironment:
    control: _FakeProcessControl
    application: _FakePowerPoint
    client: _FakeClient
    pythoncom: _FakePythonCom


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    slide_count: int = 2,
    fail_on_slide: int | None = None,
    block_on_slide: int | None = None,
) -> _FakeEnvironment:
    control = _FakeProcessControl()
    application = _FakePowerPoint(
        control,
        slide_count=slide_count,
        fail_on_slide=fail_on_slide,
        block_on_slide=block_on_slide,
    )
    environment = _FakeEnvironment(
        control=control,
        application=application,
        client=_FakeClient(application),
        pythoncom=_FakePythonCom(),
    )
    monkeypatch.setattr(
        render_pptx,
        "load_com_modules",
        lambda: (environment.client, environment.pythoncom),
    )
    monkeypatch.setattr(render_pptx, "SystemProcessControl", lambda: environment.control)
    monkeypatch.setattr(render_pptx, "com_lock", lambda **_kwargs: contextlib.nullcontext())
    return environment


def _write_pptx(tmp_path: Path) -> Path:
    pptx = tmp_path / "deck.pptx"
    pptx.write_bytes(b"fake-pptx")
    return pptx


def test_render_slides_claims_new_powerpoint_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = _install(monkeypatch)
    claimed_pids: list[int] = []
    original_claim: Callable[[Any], int] = PowerPointProcessTracker.claim_new_process

    def record_claim(self: Any) -> int:
        pid = original_claim(self)
        claimed_pids.append(pid)
        return pid

    monkeypatch.setattr(PowerPointProcessTracker, "claim_new_process", record_claim)

    rendered = render_pptx.render_slides(
        _write_pptx(tmp_path),
        tmp_path / "png",
        width=320,
        height=180,
    )

    assert claimed_pids == [_AUTOMATION_PID]
    assert [path.name for path in rendered] == ["slide-001.png", "slide-002.png"]
    assert all(path.is_file() for path in rendered)
    assert environment.control.terminated == []


def test_render_slides_preserves_partial_output_when_cleanup_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    environment = _install(monkeypatch, block_on_slide=2)
    monkeypatch.setattr(render_pptx, "_COM_TIMEOUT_S", 0.5)
    monkeypatch.setattr(com, "CLEANUP_TIMEOUT_S", 0.01)
    out_dir = tmp_path / "png"

    try:
        with pytest.raises(
            WordCleanupError,
            match="parsial dipertahankan",
        ) as excinfo:
            render_pptx.render_slides(_write_pptx(tmp_path), out_dir)

        assert environment.application.export_started.wait(timeout=5.0)
        assert (out_dir / "slide-001.png").is_file()
        assert not (out_dir / "slide-002.png").exists()
        assert environment.control.terminated == [_AUTOMATION_PID]
        assert "Cleanup ambigu" in str(excinfo.value)
        assert str(out_dir.resolve()) in str(excinfo.value)
    finally:
        environment.application.release_export.set()
        environment.application.quit_event.wait(timeout=5.0)


def test_render_slides_removes_partial_output_on_normal_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install(monkeypatch, fail_on_slide=2)
    out_dir = tmp_path / "png"

    with pytest.raises(WordComError, match="export gagal"):
        render_pptx.render_slides(_write_pptx(tmp_path), out_dir)

    assert list(out_dir.glob("slide-*.png")) == []
