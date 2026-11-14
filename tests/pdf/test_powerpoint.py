"""Tes adapter PowerPoint COM memakai fake; tanpa PowerPoint atau jaringan."""

import contextlib
import io
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from xml.etree import ElementTree

import pytest
from pptx import Presentation

from autooffice.pdf import com, embed_pptx_fonts, export_pptx_pdf, powerpoint

PDF_BYTES = b"%PDF-1.7 fake\n"
_PRESENTATIONML_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def _without_entry(data: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        entries = [
            (info, source.read(info.filename))
            for info in source.infolist()
            if info.filename != name
        ]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, payload in entries:
            archive.writestr(info, payload)
    return output.getvalue()


def _minimal_pptx(
    *,
    font_part: bool,
    embedded_font_list: bool,
    font_family: str = "Plus Jakarta Sans",
    roles: tuple[str, ...] = ("regular", "bold"),
    with_markers: bool = False,
    with_timing: bool = False,
    with_transition: bool = False,
    font_targets: tuple[str, ...] | None = None,
    relationship_ids: tuple[str, ...] | None = None,
    relationship_type: str = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
    ),
    write_font_relationships: bool = True,
    write_font_content_type: bool = True,
) -> bytes:
    """Buat PPTX minimal yang bisa dibuka python-pptx untuk fake COM.

    ``with_markers`` menambahkan shape key beserta alt text. ``font_part``
    menambahkan dua part fntdata; ``embedded_font_list`` menambahkan
    ``p:embeddedFontLst`` dengan relasi regular/bold yang menunjuk part
    tersebut. Opsi ``font_targets``, ``relationship_ids``,
    ``relationship_type``, ``write_font_relationships``, dan
    ``write_font_content_type`` dipakai tes verifikasi edge.
    """

    presentation = Presentation()
    if with_markers or with_timing or with_transition:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        if with_markers:
            shape = slide.shapes.add_textbox(0, 0, 914400, 914400)
            shape.name = "autooffice:key:s01.title.text"
            shape._element.nvSpPr.cNvPr.set("descr", "Judul slide")
    stream = io.BytesIO()
    presentation.save(stream)
    source = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
    font_parts = ["ppt/fonts/font1.fntdata", "ppt/fonts/font2.fntdata"] if font_part else []
    targets = (
        list(font_targets)
        if font_targets is not None
        else [part_name.removeprefix("ppt/") for part_name in font_parts]
    )
    role_ids = (
        list(relationship_ids)
        if relationship_ids is not None
        else [f"rId{900 + index}" for index in range(len(roles))]
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, data in entries:
            if info.filename == "ppt/presentation.xml" and embedded_font_list:
                root = ElementTree.fromstring(data)
                embedded = ElementTree.Element(f"{{{_PRESENTATIONML_NS}}}embeddedFontLst")
                embedded_font = ElementTree.SubElement(
                    embedded, f"{{{_PRESENTATIONML_NS}}}embeddedFont"
                )
                font = ElementTree.SubElement(embedded_font, f"{{{_PRESENTATIONML_NS}}}font")
                font.set("typeface", font_family)
                for index, role_name in enumerate(roles):
                    role = ElementTree.SubElement(
                        embedded_font,
                        f"{{{_PRESENTATIONML_NS}}}{role_name}",
                    )
                    role.set(f"{{{_RELATIONSHIP_NS}}}id", role_ids[index])
                root.append(embedded)
                data = ElementTree.tostring(
                    root,
                    encoding="UTF-8",
                    xml_declaration=True,
                )
            elif (
                info.filename == "ppt/_rels/presentation.xml.rels"
                and embedded_font_list
                and font_parts
                and write_font_relationships
            ):
                root = ElementTree.fromstring(data)
                for index, target in enumerate(targets):
                    relationship = ElementTree.SubElement(
                        root,
                        f"{{{_PACKAGE_RELATIONSHIP_NS}}}Relationship",
                    )
                    relationship.set("Id", f"rId{900 + index}")
                    relationship.set("Type", relationship_type)
                    relationship.set("Target", target)
                data = ElementTree.tostring(
                    root,
                    encoding="UTF-8",
                    xml_declaration=True,
                )
            elif info.filename == "[Content_Types].xml" and font_parts:
                root = ElementTree.fromstring(data)
                if write_font_content_type and not any(
                    default.get("Extension") == "fntdata"
                    for default in root.findall(f"{{{_CONTENT_TYPES_NS}}}Default")
                ):
                    ElementTree.SubElement(
                        root,
                        f"{{{_CONTENT_TYPES_NS}}}Default",
                        {
                            "Extension": "fntdata",
                            "ContentType": "application/x-fontdata",
                        },
                    )
                data = ElementTree.tostring(
                    root,
                    encoding="UTF-8",
                    xml_declaration=True,
                )
            elif (
                info.filename.startswith("ppt/slides/")
                and info.filename.endswith(".xml")
                and (with_timing or with_transition)
            ):
                root = ElementTree.fromstring(data)
                if with_timing:
                    ElementTree.SubElement(root, f"{{{_PRESENTATIONML_NS}}}timing")
                if with_transition:
                    ElementTree.SubElement(root, f"{{{_PRESENTATIONML_NS}}}transition")
                data = ElementTree.tostring(
                    root,
                    encoding="UTF-8",
                    xml_declaration=True,
                )
            archive.writestr(info, data)
        for part_name in font_parts:
            archive.writestr(part_name, b"fake-fntdata")
    return output.getvalue()


PPTX_BYTES = _minimal_pptx(font_part=False, embedded_font_list=False, with_markers=True)
EMBEDDED_PPTX_BYTES = _minimal_pptx(
    font_part=True,
    embedded_font_list=True,
    with_markers=True,
)


def _unopenable_pptx_with_font_parts() -> bytes:
    """Paket lolos verifikasi font tetapi tanpa rels paket untuk python-pptx."""

    return _without_entry(
        _minimal_pptx(
            font_part=True,
            embedded_font_list=True,
            with_markers=True,
        ),
        "_rels/.rels",
    )


class FakePresentation:
    def __init__(self, parent: FakePowerPoint, path: Path) -> None:
        self.parent = parent
        self.path = Path(path)
        self.events = parent.events
        self.powerpoint = parent
        parent.opened_path = self.path
        if parent.mutate_on_open:
            self.path.write_bytes(b"PK\x03\x04mutated-snapshot")

    def Save(self) -> None:
        self.events.append("save")

    def SaveAs(self, path: str, file_format: int) -> None:
        self.events.append(f"save_as:{file_format}")
        self.powerpoint.exported_pdf = Path(path)
        if self.powerpoint.write_export:
            Path(path).write_bytes(self.powerpoint.pdf_bytes)

    def SaveCopyAs(self, path: str, file_format: int, embed_true_type_fonts: int) -> None:
        self.events.append(f"save_copy_as:{file_format}:{embed_true_type_fonts}")
        self.powerpoint.saved_copy = Path(path)
        if self.powerpoint.fail_save_copy is not None:
            raise RuntimeError(self.powerpoint.fail_save_copy)
        if self.powerpoint.write_saved_copy:
            Path(path).write_bytes(self.powerpoint.embedded_bytes)

    def Close(self) -> None:
        self.events.append("close")


class FakePresentations:
    def __init__(self, parent: FakePowerPoint) -> None:
        self.parent = parent

    def Open(
        self,
        path: str,
        read_only: bool,
        untitled: bool,
        with_window: bool,
    ) -> FakePresentation:
        self.parent.events.append(f"open:{Path(path).name}")
        self.parent.open_arguments = (read_only, untitled, with_window)
        if self.parent.block_open is not None:
            self.parent.block_open.wait(5.0)
            raise RuntimeError("PowerPoint dihentikan")
        if self.parent.fail_open is not None:
            raise RuntimeError(self.parent.fail_open)
        return FakePresentation(self.parent, Path(path))


class FakePowerPoint:
    def __init__(
        self,
        events: list[str],
        control: FakeProcessControl,
        *,
        mutate_on_open: bool = False,
        block_open: threading.Event | None = None,
        fail_open: str | None = None,
        pdf_bytes: bytes = PDF_BYTES,
        write_export: bool = True,
        embedded_bytes: bytes = EMBEDDED_PPTX_BYTES,
        write_saved_copy: bool = True,
        fail_save_copy: str | None = None,
        quit_leaves_alive: bool = False,
    ) -> None:
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "control", control)
        object.__setattr__(self, "mutate_on_open", mutate_on_open)
        object.__setattr__(self, "block_open", block_open)
        object.__setattr__(self, "fail_open", fail_open)
        object.__setattr__(self, "pdf_bytes", pdf_bytes)
        object.__setattr__(self, "write_export", write_export)
        object.__setattr__(self, "embedded_bytes", embedded_bytes)
        object.__setattr__(self, "write_saved_copy", write_saved_copy)
        object.__setattr__(self, "fail_save_copy", fail_save_copy)
        object.__setattr__(self, "quit_leaves_alive", quit_leaves_alive)
        object.__setattr__(self, "saved_copy", None)
        self.Presentations = FakePresentations(self)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        if name in {"DisplayAlerts", "Visible"}:
            self.events.append(f"powerpoint.{name}={value!r}")

    def Quit(self) -> None:
        self.events.append("quit")
        if not self.quit_leaves_alive:
            self.control.automation_alive = False


class FakeProcessControl:
    """Process control palsu yang meniru gating timeout SystemProcessControl."""

    def __init__(self, events: list[str], *, initially_alive: bool = False) -> None:
        self.events = events
        self.pid = 4242
        self.preexisting = 1111 if initially_alive else None
        self.automation_alive = False
        self.release = threading.Event()
        self.terminated: list[int] = []
        self.created_at = 1000
        self.timeout_s = com.CLEANUP_TIMEOUT_S
        self.timeout_at_terminate: float | None = None

    def set_timeout(self, timeout_s: float) -> None:
        self.timeout_s = max(0.0, timeout_s)

    def list_powerpoint_pids(self) -> set[int] | None:
        self.events.append("list_powerpoint_pids")
        if self.timeout_s <= 0:
            return None
        pids: set[int] = set()
        if self.preexisting is not None:
            pids.add(self.preexisting)
        if self.automation_alive:
            pids.add(self.pid)
        return pids

    def image_name(self, pid: int) -> str | None:
        self.events.append(f"image:{pid}")
        if self.timeout_s <= 0:
            return None
        if self.automation_alive and pid == self.pid:
            return "POWERPNT.EXE"
        if pid == self.preexisting:
            return "POWERPNT.EXE"
        return None

    def creation_time(self, pid: int) -> int | None:
        if self.timeout_s <= 0:
            return None
        return self.created_at

    def pid_for_window(self, hwnd: int) -> int | None:
        return self.pid if self.automation_alive else None

    def is_running(self, pid: int) -> bool | None:
        if pid == self.pid:
            return self.automation_alive
        return pid == self.preexisting

    def terminate(self, pid: int) -> bool:
        self.timeout_at_terminate = self.timeout_s
        if self.timeout_s <= 0:
            return False
        self.events.append(f"terminate:{pid}")
        self.terminated.append(pid)
        self.automation_alive = False
        self.release.set()
        return True


class FakeClient:
    def __init__(self, application: FakePowerPoint) -> None:
        self.application = application

    def DispatchEx(self, name: str) -> FakePowerPoint:
        self.application.events.append(f"dispatch:{name}")
        self.application.control.automation_alive = True
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
    application: FakePowerPoint
    client: FakeClient
    pythoncom: FakePythonCom


def make_environment(**kwargs: Any) -> FakeEnvironment:
    events: list[str] = []
    control = FakeProcessControl(events, initially_alive=kwargs.pop("initially_alive", False))
    application = FakePowerPoint(events, control, **kwargs)
    return FakeEnvironment(
        events=events,
        control=control,
        application=application,
        client=FakeClient(application),
        pythoncom=FakePythonCom(events),
    )


def install(monkeypatch: pytest.MonkeyPatch, environment: FakeEnvironment) -> None:
    monkeypatch.setattr(
        powerpoint,
        "load_com_modules",
        lambda: (environment.client, environment.pythoncom),
    )
    monkeypatch.setattr(powerpoint, "SystemProcessControl", lambda: environment.control)
    monkeypatch.setattr(powerpoint, "com_lock", lambda **_kwargs: contextlib.nullcontext())


def test_export_pdf_runs_expected_com_sequence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "out" / "Deck.pdf"
    environment = make_environment(mutate_on_open=True)
    install(monkeypatch, environment)

    result = powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert result == pdf.resolve()
    assert pdf.read_bytes() == PDF_BYTES
    assert pptx.read_bytes() == PPTX_BYTES
    assert environment.application.opened_path != pptx.resolve()
    assert not environment.application.opened_path.exists()
    assert environment.application.open_arguments == (True, False, False)
    assert environment.events == [
        "list_powerpoint_pids",
        "co_initialize",
        "dispatch:PowerPoint.Application",
        "list_powerpoint_pids",
        "image:4242",
        "powerpoint.DisplayAlerts=1",
        "open:source.pptx",
        "save_as:32",
        "close",
        "quit",
        "co_uninitialize",
        "image:4242",
    ]
    assert "save" not in environment.events
    assert not any(event.startswith("powerpoint.Visible") for event in environment.events)


def test_export_pdf_uses_global_com_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment()
    install(monkeypatch, environment)
    lock_events: list[str] = []

    @contextlib.contextmanager
    def recording_lock(**_kwargs: Any) -> Any:
        lock_events.append("lock_enter")
        try:
            yield
        finally:
            lock_events.append("lock_exit")

    monkeypatch.setattr(powerpoint, "com_lock", recording_lock)

    powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert lock_events == ["lock_enter", "lock_exit"]
    assert "dispatch:PowerPoint.Application" in environment.events


def test_export_pdf_timeout_cleans_tracked_powerpoint_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment()
    environment.application.block_open = environment.control.release
    install(monkeypatch, environment)

    with pytest.raises(com.WordTimeoutError, match="tidak selesai"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=0.5)

    assert environment.control.terminated == [4242]
    assert environment.control.timeout_s == com.CLEANUP_TIMEOUT_S
    assert environment.control.timeout_at_terminate == com.CLEANUP_TIMEOUT_S
    assert not pdf.exists()
    assert pptx.read_bytes() == PPTX_BYTES
    assert "quit" in environment.events


def test_export_pdf_uses_fixed_cleanup_budget_for_short_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment()
    install(monkeypatch, environment)
    captured: list[dict[str, Any]] = []

    def fake_watchdog(*args: object, **kwargs: object) -> None:
        captured.append(dict(kwargs))
        raise com.WordComError("berhenti setelah argumen watchdog diperiksa")

    monkeypatch.setattr(powerpoint, "run_with_watchdog", fake_watchdog)

    with pytest.raises(com.WordComError, match="argumen watchdog"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=0.5)

    assert captured
    assert 0.0 < captured[0]["timeout_s"] <= 0.5
    assert captured[0]["cleanup_timeout_s"] == 5.0


def test_embed_fonts_ambiguous_cleanup_preserves_work_dir_and_temp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    work_dir = tmp_path / "font-work"
    work_dir.mkdir()
    temp_pptx = tmp_path / ".Deck-deadbeef.pptx"
    temp_pptx.write_bytes(EMBEDDED_PPTX_BYTES)
    monkeypatch.setattr(powerpoint.tempfile, "mkdtemp", lambda prefix: str(work_dir))
    monkeypatch.setattr(powerpoint.uuid, "uuid4", lambda: SimpleNamespace(hex="deadbeef"))
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_watchdog(*args: object, **kwargs: object) -> None:
        raise com.WordCleanupError("worker PowerPoint masih hidup")

    monkeypatch.setattr(powerpoint, "run_with_watchdog", fail_watchdog)

    with pytest.raises(com.WordCleanupError, match="worker PowerPoint masih hidup"):
        powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert work_dir.is_dir()
    assert (work_dir / "source.pptx").is_file()
    assert temp_pptx.is_file()
    assert pptx.read_bytes() == PPTX_BYTES


def test_export_pdf_fails_safely_on_shared_powerpoint_attach(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment()
    install(monkeypatch, environment)

    def attach_without_new_process(name: str) -> FakePowerPoint:
        environment.events.append(f"dispatch:{name}")
        return environment.application

    monkeypatch.setattr(environment.client, "DispatchEx", attach_without_new_process)

    with pytest.raises(com.WordOwnershipError, match="tepat satu proses"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert "quit" not in environment.events
    assert environment.control.terminated == []
    assert environment.control.automation_alive is False
    assert not pdf.exists()


def test_export_pdf_kills_owned_powerpoint_when_quit_does_not_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment(quit_leaves_alive=True)
    install(monkeypatch, environment)
    monkeypatch.setattr(com, "QUIT_VERIFY_TIMEOUT_S", 0.05)

    result = powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert result == pdf.resolve()
    assert "quit" in environment.events
    assert environment.control.terminated == [4242]
    assert environment.control.automation_alive is False


def test_export_pdf_refuses_preexisting_powerpoint_instance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment(initially_alive=True)
    install(monkeypatch, environment)

    with pytest.raises(com.PdfUnavailableError, match="sudah berjalan"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert "dispatch:PowerPoint.Application" not in environment.events
    assert "quit" not in environment.events
    assert environment.control.terminated == []
    assert environment.control.preexisting == 1111
    assert environment.control.automation_alive is False
    assert not pdf.exists()


def test_export_pdf_reports_missing_powerpoint_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_dispatch(name: str) -> Any:
        raise RuntimeError("PowerPoint tidak ada")

    monkeypatch.setattr(environment.client, "DispatchEx", fail_dispatch)

    with pytest.raises(powerpoint.PdfUnavailableError, match="Microsoft PowerPoint"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert not pdf.exists()


def test_export_pdf_reports_presentation_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment(fail_open="presentasi rusak")
    install(monkeypatch, environment)

    with pytest.raises(powerpoint.WordComError, match="membuka presentasi"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert not pdf.exists()
    assert "quit" in environment.events


def test_export_pdf_reports_missing_pdf_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment(write_export=False)
    install(monkeypatch, environment)

    with pytest.raises(powerpoint.WordComError, match="PDF tidak dapat dibaca"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert not pdf.exists()


def test_export_pdf_rejects_invalid_pdf_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment(pdf_bytes=b"bukan pdf")
    install(monkeypatch, environment)

    with pytest.raises(powerpoint.WordComError, match="tidak valid atau kosong"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert not pdf.exists()


def test_export_pdf_rejects_empty_pdf_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment(pdf_bytes=b"")
    install(monkeypatch, environment)

    with pytest.raises(powerpoint.WordComError, match="tidak valid atau kosong"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert not pdf.exists()


def test_export_pdf_wraps_pdf_replace_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("target terkunci")

    monkeypatch.setattr(powerpoint.os, "replace", fail_replace)

    with pytest.raises(powerpoint.WordComError, match="Gagal menulis PDF"):
        powerpoint.export_pdf(pptx, pdf, timeout_s=5.0)

    assert not pdf.exists()


def test_export_pdf_rejects_invalid_timeout(tmp_path: Path) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)

    with pytest.raises(ValueError, match="timeout_s"):
        powerpoint.export_pdf(pptx, tmp_path / "Deck.pdf", timeout_s=0)


def test_export_pdf_reports_non_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    monkeypatch.setattr(com, "_platform", lambda: "linux")
    monkeypatch.setattr(powerpoint, "com_lock", lambda **_kwargs: contextlib.nullcontext())

    with pytest.raises(powerpoint.PdfUnavailableError, match="Windows"):
        powerpoint.export_pdf(pptx, tmp_path / "Deck.pdf")


def test_export_pdf_reports_missing_pywin32(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)

    def missing(name: str) -> Any:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(com, "_platform", lambda: "win32")
    monkeypatch.setattr(com, "_import_module", missing)
    monkeypatch.setattr(powerpoint, "com_lock", lambda **_kwargs: contextlib.nullcontext())

    with pytest.raises(powerpoint.PdfUnavailableError, match="pywin32"):
        powerpoint.export_pdf(pptx, tmp_path / "Deck.pdf")


def test_export_pdf_rejects_missing_pptx(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="tidak ditemukan"):
        powerpoint.export_pdf(tmp_path / "Hilang.pptx", tmp_path / "Hilang.pdf")


def test_export_pdf_rejects_directory_as_pptx(tmp_path: Path) -> None:
    folder = tmp_path / "Folder.pptx"
    folder.mkdir()

    with pytest.raises(ValueError, match="bukan berkas PPTX"):
        powerpoint.export_pdf(folder, tmp_path / "out.pdf")


def test_export_pdf_rejects_non_pptx_suffix(tmp_path: Path) -> None:
    source = tmp_path / "Deck.txt"
    source.write_bytes(PPTX_BYTES)

    with pytest.raises(ValueError, match="\\.pptx"):
        powerpoint.export_pdf(source, tmp_path / "out.pdf")


def test_export_pdf_rejects_non_pdf_suffix(tmp_path: Path) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)

    with pytest.raises(ValueError, match="\\.pdf"):
        powerpoint.export_pdf(pptx, tmp_path / "out.txt")


def test_export_pdf_wraps_pptx_resolve_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_resolve(self: Path, *args: Any, **kwargs: Any) -> Path:
        raise OSError("path rusak")

    monkeypatch.setattr(Path, "resolve", fail_resolve)

    with pytest.raises(ValueError, match="Path PPTX tidak valid"):
        powerpoint.export_pdf(tmp_path / "Deck.pptx", tmp_path / "Deck.pdf")


def test_export_pdf_wraps_pdf_resolve_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    calls = 0

    def fail_second(self: Path, *args: Any, **kwargs: Any) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("path PDF rusak")
        return self

    monkeypatch.setattr(Path, "resolve", fail_second)

    with pytest.raises(ValueError, match="Path PDF tidak valid"):
        powerpoint.export_pdf(pptx, tmp_path / "Deck.pdf")


def test_export_pdf_reports_pdf_directory_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)

    def fail_mkdir(self: Path, *args: Any, **kwargs: Any) -> None:
        raise OSError("disk penuh")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)

    with pytest.raises(powerpoint.WordComError, match="Direktori PDF"):
        powerpoint.export_pdf(pptx, tmp_path / "out" / "Deck.pdf")


def test_export_pdf_visible_sets_powerpoint_window(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    pdf = tmp_path / "Deck.pdf"
    environment = make_environment()
    install(monkeypatch, environment)

    result = powerpoint.export_pdf(pptx, pdf, timeout_s=5.0, visible=True)

    assert result == pdf.resolve()
    assert "powerpoint.Visible=True" in environment.events


def test_embed_fonts_runs_expected_com_sequence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment(mutate_on_open=True)
    install(monkeypatch, environment)

    result = powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert result == pptx.resolve()
    assert pptx.read_bytes() == EMBEDDED_PPTX_BYTES
    assert environment.application.opened_path != pptx.resolve()
    assert not environment.application.opened_path.exists()
    assert environment.application.open_arguments == (False, False, False)
    assert environment.application.saved_copy is not None
    assert environment.application.saved_copy.parent == pptx.parent
    assert environment.application.saved_copy.suffix == ".pptx"
    assert not environment.application.saved_copy.exists()
    assert environment.events == [
        "list_powerpoint_pids",
        "co_initialize",
        "dispatch:PowerPoint.Application",
        "list_powerpoint_pids",
        "image:4242",
        "powerpoint.DisplayAlerts=1",
        "open:source.pptx",
        "save_copy_as:24:-1",
        "close",
        "quit",
        "co_uninitialize",
        "image:4242",
    ]
    assert "save" not in environment.events


def test_embed_fonts_preserves_source_when_save_copy_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment(
        mutate_on_open=True,
        fail_save_copy="font tidak bisa ditanam",
    )
    install(monkeypatch, environment)

    with pytest.raises(powerpoint.WordComError, match="menanam font"):
        powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert pptx.read_bytes() == PPTX_BYTES
    assert environment.application.saved_copy is not None
    assert not environment.application.saved_copy.exists()
    assert "quit" in environment.events


def test_embed_fonts_preserves_source_when_copy_not_written(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment(write_saved_copy=False)
    install(monkeypatch, environment)

    with pytest.raises(powerpoint.WordComError, match="tidak dapat dibaca"):
        powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert pptx.read_bytes() == PPTX_BYTES


def test_embed_fonts_preserves_source_when_replace_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("target terkunci")

    monkeypatch.setattr(powerpoint.os, "replace", fail_replace)

    with pytest.raises(powerpoint.WordComError, match="Gagal mengganti PPTX"):
        powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert pptx.read_bytes() == PPTX_BYTES
    assert environment.application.saved_copy is not None
    assert not environment.application.saved_copy.exists()


def test_embed_fonts_rejects_result_without_fntdata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment(
        embedded_bytes=_minimal_pptx(font_part=False, embedded_font_list=True)
    )
    install(monkeypatch, environment)

    with pytest.raises(powerpoint.WordComError, match="fntdata"):
        powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert pptx.read_bytes() == PPTX_BYTES


def test_embed_fonts_rejects_result_without_embedded_font_list(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment(
        embedded_bytes=_minimal_pptx(font_part=True, embedded_font_list=False)
    )
    install(monkeypatch, environment)

    with pytest.raises(powerpoint.WordComError, match="embeddedFontLst"):
        powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert pptx.read_bytes() == PPTX_BYTES


def test_embed_fonts_rejects_result_not_openable_by_python_pptx(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment(embedded_bytes=_unopenable_pptx_with_font_parts())
    install(monkeypatch, environment)

    with pytest.raises(powerpoint.WordComError, match="tidak dapat dibuka"):
        powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert pptx.read_bytes() == PPTX_BYTES


def test_embed_fonts_reports_missing_powerpoint_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment()
    install(monkeypatch, environment)

    def fail_dispatch(name: str) -> Any:
        raise RuntimeError("PowerPoint tidak ada")

    monkeypatch.setattr(environment.client, "DispatchEx", fail_dispatch)

    with pytest.raises(powerpoint.PdfUnavailableError, match="Microsoft PowerPoint"):
        powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert pptx.read_bytes() == PPTX_BYTES


def test_embed_fonts_uses_global_com_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment()
    install(monkeypatch, environment)
    lock_events: list[str] = []

    @contextlib.contextmanager
    def recording_lock(**_kwargs: Any) -> Any:
        lock_events.append("lock_enter")
        try:
            yield
        finally:
            lock_events.append("lock_exit")

    monkeypatch.setattr(powerpoint, "com_lock", recording_lock)

    powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert lock_events == ["lock_enter", "lock_exit"]
    assert "save_copy_as:24:-1" in environment.events


def test_embed_fonts_rejects_invalid_timeout(tmp_path: Path) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)

    with pytest.raises(ValueError, match="timeout_s"):
        powerpoint.embed_fonts(pptx, timeout_s=0)


def test_package_exports_font_embedding_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    calls: list[tuple[Path, float]] = []

    def fake_embed(path: Path, *, timeout_s: float) -> Path:
        calls.append((Path(path), timeout_s))
        return Path(path)

    monkeypatch.setattr(powerpoint, "embed_fonts", fake_embed)

    assert embed_pptx_fonts(pptx, timeout_s=7.0) == pptx
    assert calls == [(pptx, 7.0)]


def test_system_process_control_lists_powerpoint_pids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        com,
        "_tasklist_rows",
        lambda *filters, **kwargs: [["POWERPNT.EXE", "4242"]],
    )
    control = com.SystemProcessControl()

    assert control.list_powerpoint_pids() == {4242}


def test_package_exports_powerpoint_adapter() -> None:
    assert export_pptx_pdf is powerpoint.export_pdf
