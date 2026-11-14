"""Tes render Mermaid memakai executable ``mmdc`` palsu dan smoke asli."""

import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import autooffice.deck.media.mermaid as mermaid_module
from autooffice.deck.media.mermaid import (
    MMDC_ENV_VAR,
    MMDC_INSTALL_HINT,
    PNG_SIGNATURE,
    MermaidError,
    _copy_png,
    _is_png,
    _is_remote_path,
    _validate_png,
    cache_digest,
    find_mmdc,
    render_mermaid,
    resolve_mermaid_source,
)
from autooffice.design.theme import resolve_theme

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

FAKE_MMDC = """\
import base64
import json
import os
import pathlib
import sys

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

arguments = sys.argv[1:]
log = os.environ.get("FAKE_MMDC_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(arguments) + "\\n")

if arguments == ["--version"]:
    if os.environ.get("FAKE_MMDC_EMPTY_VERSION"):
        raise SystemExit(0)
    print(os.environ.get("FAKE_MMDC_VERSION", "12.2.0"))
    raise SystemExit(0)


def option(flag):
    try:
        return arguments[arguments.index(flag) + 1]
    except (ValueError, IndexError):
        return None


source = option("-i")
target = option("-o")
if source is None or target is None:
    print("fake mmdc: butuh -i dan -o", file=sys.stderr)
    raise SystemExit(2)

# Fake harus membaca sumber agar renderer tidak lolos dengan file hantu.
pathlib.Path(source).read_text(encoding="utf-8")
output = pathlib.Path(target)
output.parent.mkdir(parents=True, exist_ok=True)

if os.environ.get("FAKE_MMDC_FAIL"):
    output.write_bytes(b"partial")
    print("fake mmdc gagal disengaja", file=sys.stderr)
    raise SystemExit(3)
if os.environ.get("FAKE_MMDC_INVALID_PNG"):
    output.write_bytes(b"bukan png")
    raise SystemExit(0)

output.write_bytes(PNG)

stdout_bytes = os.environ.get("FAKE_MMDC_STDOUT_BYTES")
if stdout_bytes:
    sys.stdout.write("x" * int(stdout_bytes))
    sys.stdout.flush()
stderr_bytes = os.environ.get("FAKE_MMDC_STDERR_BYTES")
if stderr_bytes:
    sys.stderr.write("x" * int(stderr_bytes))
    sys.stderr.flush()
"""


@pytest.fixture(scope="module")
def theme():
    """Theme indigo untuk render Mermaid."""
    return resolve_theme("indigo")


def make_fake_mmdc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str = "12.2.0",
) -> tuple[Path, Path]:
    """Tulis skrip mmdc palsu dan aktifkan lewat environment override."""
    log = tmp_path / "mmdc-log.jsonl"
    monkeypatch.setenv("FAKE_MMDC_LOG", str(log))
    monkeypatch.setenv("FAKE_MMDC_VERSION", version)
    script = tmp_path / f"fake_mmdc_{version.replace('.', '_')}.py"
    script.write_text(FAKE_MMDC, encoding="utf-8", newline="\n")
    monkeypatch.setenv(MMDC_ENV_VAR, str(script))
    return script, log


def read_calls(log: Path) -> list[list[str]]:
    """Baca seluruh invocation yang dicatat fake mmdc."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def render_calls(log: Path) -> list[list[str]]:
    """Ambil invocation render, bukan invocation ``--version``."""
    return [call for call in read_calls(log) if "-i" in call]


def option(arguments: list[str], flag: str) -> str:
    """Ambil nilai satu flag dari daftar argumen."""
    return arguments[arguments.index(flag) + 1]


def test_resolve_mermaid_source_accepts_relative_file(tmp_path: Path) -> None:
    diagram = tmp_path / "diagrams" / "flow.mmd"
    diagram.parent.mkdir()
    diagram.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")

    resolved = resolve_mermaid_source(tmp_path, "diagrams/flow.mmd")

    assert resolved == diagram.resolve()


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("../flow.mmd", ".."),
        ("https://example.com/flow.mmd", "remote"),
        ("/absolute/flow.mmd", "relatif"),
        ("C:/diagrams/flow.mmd", "relatif"),
        ("diagrams\\flow.mmd", "memakai '/'"),
        ("diagrams//flow.mmd", "segmen"),
        ("diagrams/flow.png", ".mmd"),
    ],
)
def test_resolve_mermaid_source_rejects_invalid_paths(
    tmp_path: Path,
    relative: str,
    message: str,
) -> None:
    with pytest.raises(MermaidError, match=message):
        resolve_mermaid_source(tmp_path, relative)


def test_render_mermaid_passes_mmdc_arguments_and_writes_png(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    out = tmp_path / "out" / "flow.png"

    result = render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert result == out
    assert out.read_bytes() == PNG_1X1
    calls = render_calls(log)
    assert len(calls) == 1
    arguments = calls[0]
    assert option(arguments, "-i") == str(source.resolve())
    assert option(arguments, "-o") == str(out)
    assert option(arguments, "--theme") == "base"
    assert option(arguments, "--backgroundColor") == theme.colors.background
    assert option(arguments, "--scale") == "2"
    assert option(arguments, "--size") == "2400"
    assert Path(option(arguments, "--configFile")).name == "config.json"


def test_render_mermaid_uses_older_width_flag_for_mmdc_11(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_mmdc(tmp_path, monkeypatch, version="11.4.0")
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart LR\n  A --> B\n", encoding="utf-8")

    render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")

    arguments = render_calls(log)[0]
    assert option(arguments, "--width") == "2400"
    assert "--size" not in arguments


def test_cache_hit_does_not_run_mmdc_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    out = tmp_path / "flow.png"
    cache = tmp_path / "cache"

    first = render_mermaid(source, out, theme=theme, cache_dir=cache)
    calls = read_calls(log)
    second = render_mermaid(source, out, theme=theme, cache_dir=cache)

    assert first == second == out
    assert read_calls(log) == calls
    assert len(list(cache.glob("mermaid-*.png"))) == 1


def test_cache_hit_works_without_mmdc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    script, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    cache = tmp_path / "cache"
    first_out = tmp_path / "first.png"

    render_mermaid(source, first_out, theme=theme, cache_dir=cache)
    calls = read_calls(log)
    script.unlink()
    monkeypatch.delenv(MMDC_ENV_VAR, raising=False)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    second_out = tmp_path / "second.png"

    assert find_mmdc() is None
    result = render_mermaid(source, second_out, theme=theme, cache_dir=cache)

    assert result == second_out
    assert second_out.read_bytes() == PNG_1X1
    assert read_calls(log) == calls


def test_cache_first_without_mmdc_does_not_use_other_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    script, _log = make_fake_mmdc(tmp_path, monkeypatch)
    first_source = tmp_path / "first.mmd"
    first_source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    cache = tmp_path / "cache"
    render_mermaid(first_source, tmp_path / "first.png", theme=theme, cache_dir=cache)

    script.unlink()
    monkeypatch.delenv(MMDC_ENV_VAR, raising=False)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    second_source = tmp_path / "second.mmd"
    second_source.write_text("flowchart TD\n  A --> C\n", encoding="utf-8")
    out = tmp_path / "second.png"

    with pytest.raises(MermaidError, match="tidak ditemukan"):
        render_mermaid(second_source, out, theme=theme, cache_dir=cache)

    assert not out.exists()


def test_source_change_invalidates_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    cache = tmp_path / "cache"
    out = tmp_path / "flow.png"

    render_mermaid(source, out, theme=theme, cache_dir=cache)
    source.write_text("flowchart TD\n  A --> C\n", encoding="utf-8")
    render_mermaid(source, out, theme=theme, cache_dir=cache)

    assert len(render_calls(log)) == 2
    assert len(list(cache.glob("mermaid-*.png"))) == 2


def test_theme_and_version_change_invalidate_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    cache = tmp_path / "cache"
    out = tmp_path / "flow.png"

    render_mermaid(source, out, theme=theme, cache_dir=cache)
    render_mermaid(source, out, theme=resolve_theme("hitam"), cache_dir=cache)
    make_fake_mmdc(tmp_path, monkeypatch, version="13.0.0")
    render_mermaid(source, out, theme=theme, cache_dir=cache)

    assert len(render_calls(log)) == 3
    assert len(list(cache.glob("mermaid-*.png"))) == 3


def test_cache_digest_depends_on_theme_tokens(
    tmp_path: Path,
    theme,
) -> None:
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")

    indigo = cache_digest(source, theme=theme, mmdc_version="12.2.0")
    hitam = cache_digest(source, theme=resolve_theme("hitam"), mmdc_version="12.2.0")
    newer = cache_digest(source, theme=theme, mmdc_version="13.0.0")

    assert len(indigo) == 64
    assert len({indigo, hitam, newer}) == 3


def test_missing_mmdc_raises_install_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    monkeypatch.setenv(MMDC_ENV_VAR, str(tmp_path / "tidak-ada-mmdc.exe"))
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")

    with pytest.raises(MermaidError) as error:
        render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")

    message = str(error.value)
    assert "mmdc tidak ditemukan" in message
    assert MMDC_INSTALL_HINT in message
    assert find_mmdc() is None
    assert not (tmp_path / "flow.png").exists()


def test_mmdc_failure_removes_partial_png(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_mmdc(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MMDC_FAIL", "1")
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    out = tmp_path / "flow.png"

    with pytest.raises(MermaidError, match="mmdc gagal"):
        render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert not out.exists()
    assert list((tmp_path / "cache").glob("mermaid-*.png")) == []


def test_invalid_png_output_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_mmdc(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MMDC_INVALID_PNG", "1")
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")
    out = tmp_path / "flow.png"

    with pytest.raises(MermaidError, match="bukan PNG"):
        render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert not out.exists()
    assert list((tmp_path / "cache").glob("mermaid-*.png")) == []


def test_output_must_be_png(tmp_path: Path, theme) -> None:
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n  A --> B\n", encoding="utf-8")

    with pytest.raises(MermaidError, match="harus PNG"):
        render_mermaid(source, tmp_path / "flow.svg", theme=theme, cache_dir=tmp_path / "cache")


@pytest.mark.parametrize("source", ["../flow.mmd", "https://example.com/flow.mmd"])
def test_render_mermaid_rejects_invalid_source_path(source: str, tmp_path: Path, theme) -> None:
    with pytest.raises(MermaidError):
        render_mermaid(
            Path(source),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


@pytest.mark.integration
@pytest.mark.slow
def test_real_mmdc_renders_high_resolution_png(tmp_path: Path, theme) -> None:
    if shutil.which("mmdc") is None:
        pytest.skip("mmdc tidak terpasang")
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart LR\n  A --> B\n  B --> C\n", encoding="utf-8")
    out = tmp_path / "flow.png"

    result = render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert result == out
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(out) as image:
        assert max(image.size) >= 1600


class EmptyPath(type(Path())):
    """Path defensif dengan ``str`` kosong; ``Path`` normal tidak pernah kosong."""

    def __str__(self) -> str:
        return ""


class PartlessPath(type(Path())):
    """Path defensif tanpa komponen; ``Path`` normal selalu punya komponen."""

    @property
    def parts(self) -> tuple[str, ...]:
        return ()


class StatFailPath(type(Path())):
    """Path yang ada tetapi gagal di-``stat`` saat validasi PNG."""

    def is_file(self) -> bool:
        return True

    def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
        raise OSError("stat gagal disengaja")


def completed(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    truncated: bool = False,
) -> SimpleNamespace:
    """Hasil proses palsu yang cukup untuk modul Mermaid."""
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=truncated,
    )


def raise_os_error(*_args: object, **_kwargs: object) -> None:
    """Gagalkan pemanggilan subprocess secara disengaja."""
    raise OSError("spawn gagal disengaja")


@pytest.mark.parametrize(
    ("relative", "message"),
    [
        ("", "kosong"),
        ("diagrams/\x01flow.mmd", "kontrol"),
        ("hilang.mmd", "tidak ditemukan"),
    ],
    ids=["empty", "control", "missing"],
)
def test_resolve_mermaid_source_rejects_empty_control_and_missing(
    tmp_path: Path,
    relative: str,
    message: str,
) -> None:
    with pytest.raises(MermaidError, match=message):
        resolve_mermaid_source(tmp_path, relative)


def test_resolve_mermaid_source_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "deck"
    root.mkdir()
    outside = tmp_path / "luar"
    outside.mkdir()
    (outside / "flow.mmd").write_text("flowchart TD\n", encoding="utf-8")
    try:
        os.symlink(outside, root / "link", target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink tidak didukung: {error}")

    with pytest.raises(MermaidError, match="keluar"):
        resolve_mermaid_source(root, "link/flow.mmd")


def test_defensive_render_mermaid_rejects_empty_source_string(
    tmp_path: Path,
    theme,
) -> None:
    """Input ``Path`` cacat dengan ``str`` kosong tetap ditolak dengan pesan jelas."""
    with pytest.raises(MermaidError, match="kosong"):
        render_mermaid(
            EmptyPath("flow.mmd"),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_render_mermaid_rejects_relative_path_with_drive_separator(
    tmp_path: Path,
    theme,
) -> None:
    with pytest.raises(MermaidError, match="drive"):
        render_mermaid(
            Path("a:b.mmd"),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_render_mermaid_rejects_non_mmd_source(tmp_path: Path, theme) -> None:
    with pytest.raises(MermaidError, match=r"berekstensi \.mmd"):
        render_mermaid(
            Path("flow.svg"),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_render_mermaid_rejects_source_directory(tmp_path: Path, theme) -> None:
    source = tmp_path / "diagram.mmd"
    source.mkdir()

    with pytest.raises(MermaidError, match="berupa file, bukan direktori"):
        render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")


def test_render_mermaid_rejects_missing_source(tmp_path: Path, theme) -> None:
    with pytest.raises(MermaidError, match="tidak ditemukan"):
        render_mermaid(
            tmp_path / "hilang.mmd",
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_render_mermaid_rejects_unc_network_path(tmp_path: Path, theme) -> None:
    with pytest.raises(MermaidError, match="remote"):
        render_mermaid(
            Path("//server/share/flow.mmd"),
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


def test_defensive_is_remote_path_accepts_path_without_parts() -> None:
    """``Path`` normal selalu punya komponen; subclass tanpa ``parts`` bukan remote."""
    assert _is_remote_path(PartlessPath("flow.mmd")) is False


def test_render_mermaid_reports_output_parent_file(tmp_path: Path, monkeypatch, theme) -> None:
    make_fake_mmdc(tmp_path, monkeypatch)
    blocker = tmp_path / "blocker"
    blocker.write_text("bukan folder", encoding="utf-8")
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")

    with pytest.raises(MermaidError, match="folder output"):
        render_mermaid(source, blocker / "flow.png", theme=theme, cache_dir=tmp_path / "cache")


def test_render_mermaid_rejects_output_directory(tmp_path: Path, theme) -> None:
    out = tmp_path / "flow.png"
    out.mkdir()
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")

    with pytest.raises(MermaidError, match="berupa file"):
        render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")


def test_render_mermaid_rejects_cache_file(tmp_path: Path, monkeypatch, theme) -> None:
    make_fake_mmdc(tmp_path, monkeypatch)
    cache = tmp_path / "cache"
    cache.write_text("bukan folder", encoding="utf-8")
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")

    with pytest.raises(MermaidError, match="bukan direktori"):
        render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=cache)


def test_render_mermaid_reports_cache_parent_file(tmp_path: Path, monkeypatch, theme) -> None:
    make_fake_mmdc(tmp_path, monkeypatch)
    blocker = tmp_path / "blocker"
    blocker.write_text("bukan folder", encoding="utf-8")
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")

    with pytest.raises(MermaidError, match="Gagal menyiapkan cache"):
        render_mermaid(
            source,
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=blocker / "cache",
        )


def test_missing_mmdc_without_override_raises_path_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    monkeypatch.delenv(MMDC_ENV_VAR, raising=False)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")

    assert find_mmdc() is None
    with pytest.raises(MermaidError, match="tidak ditemukan di PATH") as error:
        render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")

    assert MMDC_INSTALL_HINT in str(error.value)


def test_source_over_size_limit_is_rejected(
    tmp_path: Path,
    theme,
) -> None:
    source = tmp_path / "huge.mmd"
    source.write_bytes(b"a" * (mermaid_module.MAX_SOURCE_BYTES + 1))

    with pytest.raises(MermaidError, match="terlalu besar"):
        render_mermaid(
            source,
            tmp_path / "flow.png",
            theme=theme,
            cache_dir=tmp_path / "cache",
        )


@pytest.mark.parametrize(
    "variable",
    ["FAKE_MMDC_STDOUT_BYTES", "FAKE_MMDC_STDERR_BYTES"],
)
def test_mmdc_output_over_capture_limit_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
    variable: str,
) -> None:
    make_fake_mmdc(tmp_path, monkeypatch)
    monkeypatch.setenv(variable, str(mermaid_module.MAX_OUTPUT_BYTES + 1))
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")
    out = tmp_path / "flow.png"

    with pytest.raises(MermaidError, match="melebihi batas output"):
        render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert not out.exists()


TREE_MMDC = """\
import os
import pathlib
import subprocess
import sys
import time

if "--version" in sys.argv:
    print("12.2.0")
    raise SystemExit(0)

child_code = (
    "import os, pathlib, time; "
    "pathlib.Path(os.environ['FAKE_MMDC_CHILD_READY']).write_text('siap'); "
    "time.sleep(60)"
)
child = subprocess.Popen([sys.executable, "-c", child_code])
pathlib.Path(os.environ["FAKE_MMDC_CHILD_PID"]).write_text(
    str(child.pid), encoding="utf-8"
)
time.sleep(60)
"""


def process_running(pid: int) -> bool:
    """True bila proses masih hidup, tanpa mengirim sinyal mematikan."""
    if os.name == "nt":
        import ctypes

        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 0x00000102
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_process_exit(pid: int, *, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_running(pid):
            return True
        time.sleep(0.05)
    return False


def test_timeout_terminates_child_process_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    script = tmp_path / "tree_mmdc.py"
    script.write_text(TREE_MMDC, encoding="utf-8", newline="\n")
    pid_file = tmp_path / "child.pid"
    ready_file = tmp_path / "child.ready"
    monkeypatch.setenv(MMDC_ENV_VAR, str(script))
    monkeypatch.setenv("FAKE_MMDC_CHILD_PID", str(pid_file))
    monkeypatch.setenv("FAKE_MMDC_CHILD_READY", str(ready_file))
    monkeypatch.setattr(mermaid_module, "DEFAULT_TIMEOUT", 2.0)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")
    out = tmp_path / "flow.png"

    with pytest.raises(MermaidError, match="melebihi batas waktu"):
        render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert pid_file.exists()
    assert ready_file.exists()
    child_pid = int(pid_file.read_text(encoding="utf-8"))
    assert wait_for_process_exit(child_pid), f"child process {child_pid} masih hidup"
    assert not out.exists()


def test_version_probe_failure_when_executable_disappears(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    missing = tmp_path / "hilang.py"
    monkeypatch.setattr(mermaid_module, "find_mmdc", lambda: missing)
    monkeypatch.setattr(mermaid_module, "_run_captured", raise_os_error)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")

    with pytest.raises(MermaidError, match="Gagal membaca versi"):
        render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")


def test_version_probe_without_output_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_mmdc(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MMDC_EMPTY_VERSION", "1")
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")

    with pytest.raises(MermaidError, match="gagal melaporkan versi"):
        render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")


def test_render_mermaid_reports_temporary_directory_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    make_fake_mmdc(tmp_path, monkeypatch)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("temp gagal disengaja")

    monkeypatch.setattr(mermaid_module.tempfile, "TemporaryDirectory", fail)

    with pytest.raises(MermaidError, match="Gagal menyiapkan render"):
        render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")


def test_version_without_major_omits_size_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_mmdc(tmp_path, monkeypatch, version="dev")
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")

    render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=tmp_path / "cache")

    arguments = render_calls(log)[0]
    assert "--size" not in arguments
    assert "--width" not in arguments


def test_cache_digest_reports_unreadable_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")
    resolved = source.resolve()
    original_open = Path.open

    def open_path(path: Path, *args: object, **kwargs: object):
        if path == resolved:
            raise OSError("izin ditolak")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)

    with pytest.raises(MermaidError, match="tidak dapat dibaca"):
        cache_digest(source, theme=theme, mmdc_version="12.2.0")


def _prepare_render_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    executable = tmp_path / "fake_mmdc.py"
    executable.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setenv(MMDC_ENV_VAR, str(executable))
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")
    return source, tmp_path / "flow.png"


def test_render_mermaid_timeout_removes_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    source, out = _prepare_render_input(tmp_path, monkeypatch)

    def run(command: list[str], *, timeout: float) -> SimpleNamespace:
        if "--version" in command:
            return completed(stdout="12.2.0\n")
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(mermaid_module, "_run_captured", run)

    with pytest.raises(MermaidError, match="melebihi batas waktu"):
        render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert not out.exists()


def test_render_mermaid_spawn_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    source, out = _prepare_render_input(tmp_path, monkeypatch)

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if "--version" in command:
            return completed(stdout="12.2.0\n")
        raise OSError("spawn gagal disengaja")

    monkeypatch.setattr(mermaid_module, "_run_captured", run)

    with pytest.raises(MermaidError, match="Gagal menjalankan mmdc"):
        render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")

    assert not out.exists()


def test_render_mermaid_missing_output_file_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    source, out = _prepare_render_input(tmp_path, monkeypatch)

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if "--version" in command:
            return completed(stdout="12.2.0\n")
        return completed()

    monkeypatch.setattr(mermaid_module, "_run_captured", run)

    with pytest.raises(MermaidError, match="tidak menghasilkan PNG"):
        render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")


def test_render_mermaid_empty_output_file_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    source, out = _prepare_render_input(tmp_path, monkeypatch)

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if "--version" in command:
            return completed(stdout="12.2.0\n")
        target = Path(command[command.index("-o") + 1])
        target.write_bytes(b"")
        return completed()

    monkeypatch.setattr(mermaid_module, "_run_captured", run)

    with pytest.raises(MermaidError, match="tidak menghasilkan PNG"):
        render_mermaid(source, out, theme=theme, cache_dir=tmp_path / "cache")


def test_truncated_cache_entry_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    digest = cache_digest(source, theme=theme, mmdc_version="12.2.0")
    cache_path = cache / f"mermaid-{digest}.png"
    cache_path.write_bytes(b"\x89PNG")

    out = tmp_path / "flow.png"
    render_mermaid(source, out, theme=theme, cache_dir=cache)

    assert out.read_bytes() == PNG_1X1
    assert _is_png(cache_path)
    assert len(render_calls(log)) == 1


def test_cache_entry_with_only_png_signature_is_rerendered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    digest = cache_digest(source, theme=theme, mmdc_version="12.2.0")
    cache_path = cache / f"mermaid-{digest}.png"
    cache_path.write_bytes(PNG_SIGNATURE)

    out = tmp_path / "flow.png"
    render_mermaid(source, out, theme=theme, cache_dir=cache)

    assert out.read_bytes() == PNG_1X1
    assert cache_path.read_bytes() == PNG_1X1
    assert len(render_calls(log)) == 1


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(PNG_SIGNATURE, id="signature-only"),
        pytest.param(PNG_1X1[:-12], id="missing-iend"),
    ],
)
def test_is_png_requires_complete_png(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(payload)

    assert _is_png(path) is False
    with pytest.raises(MermaidError, match="bukan PNG"):
        _validate_png(path)


def test_is_png_accepts_complete_png(tmp_path: Path) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(PNG_1X1)

    assert _is_png(path) is True
    _validate_png(path)


def test_cache_hit_when_output_is_cache_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    _script, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    digest = cache_digest(source, theme=theme, mmdc_version="12.2.0")
    out = cache / f"mermaid-{digest}.png"
    out.write_bytes(PNG_1X1)

    result = render_mermaid(source, out, theme=theme, cache_dir=cache)

    assert result == out
    assert out.read_bytes() == PNG_1X1
    assert render_calls(log) == []


def test_copy_png_reports_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG_1X1)
    target = tmp_path / "nested" / "target.png"

    def copyfileobj(_source: object, _target: object) -> None:
        raise OSError("disk penuh")

    monkeypatch.setattr(mermaid_module.shutil, "copyfileobj", copyfileobj)

    with pytest.raises(MermaidError, match="Gagal menulis PNG"):
        _copy_png(source, target)

    assert not target.exists()
    assert list(target.parent.glob(".*.tmp")) == []


def test_copy_png_ignores_predictable_stale_temp_symlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG_1X1)
    target = tmp_path / "out" / "target.png"
    target.parent.mkdir()
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("jangan diubah", encoding="utf-8")
    stale = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        stale.symlink_to(sentinel)
    except OSError as error:
        pytest.skip(f"symlink tidak didukung: {error}")

    _copy_png(source, target)

    assert sentinel.read_text(encoding="utf-8") == "jangan diubah"
    assert target.read_bytes() == PNG_1X1
    assert stale.is_symlink()


def test_validate_png_reports_stat_failure(tmp_path: Path) -> None:
    path = StatFailPath(tmp_path / "flow.png")

    with pytest.raises(MermaidError, match="tidak dapat dibaca"):
        _validate_png(path)
