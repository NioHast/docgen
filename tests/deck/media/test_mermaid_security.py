"""Tes branch keamanan renderer Mermaid: PNG, cache, proses, dan batas output."""

import io
import json
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import autooffice.deck.media.mermaid as mermaid_module
from autooffice.deck.media.mermaid import (
    CACHE_FORMAT,
    PNG_SIGNATURE,
    MermaidError,
    _cache_metadata_matches,
    _cache_mtime,
    _close_windows_job,
    _copy_png,
    _create_windows_job,
    _discard_cache_entry,
    _find_cached_png,
    _join_capture_threads,
    _mmdc_command,
    _mmdc_version,
    _output_arguments,
    _OutputCapture,
    _png_problem,
    _read_cache_metadata,
    _run_captured,
    _source_sha256,
    _spawn_captured,
    _taskkill_tree,
    _terminate_process_tree,
    _theme_fingerprint,
    _validate_png,
    _validated_source,
    _wait_for_exit,
    _write_atomic_bytes,
    _write_cache_metadata,
    render_mermaid,
)
from autooffice.design.theme import resolve_theme


@pytest.fixture(scope="module")
def theme():
    """Theme indigo untuk fingerprint cache."""
    return resolve_theme("indigo")


def _chunk(kind: bytes, payload: bytes = b"") -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return len(payload).to_bytes(4, "big") + kind + payload + crc.to_bytes(4, "big")


def _ihdr(
    *,
    width: int = 1,
    height: int = 1,
    bit_depth: int = 8,
    color_type: int = 6,
    compression: int = 0,
    filter_method: int = 0,
    interlace: int = 0,
) -> bytes:
    return struct.pack(
        ">IIBBBBB",
        width,
        height,
        bit_depth,
        color_type,
        compression,
        filter_method,
        interlace,
    )


def _png(*chunks: bytes) -> bytes:
    return PNG_SIGNATURE + b"".join(chunks)


VALID_IHDR = _chunk(b"IHDR", _ihdr())
VALID_IDAT = _chunk(b"IDAT", b"")
VALID_IEND = _chunk(b"IEND", b"")
MINIMAL_PNG = _png(VALID_IHDR, VALID_IDAT, VALID_IEND)


def _completed(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    truncated: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        truncated=truncated,
    )


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        pytest.param(b"\x89PNG", "terlalu pendek", id="too-short"),
        pytest.param(
            b"\x00" * 8 + MINIMAL_PNG[8:],
            "signature tidak valid",
            id="bad-signature",
        ),
        pytest.param(
            _png(_chunk(b"IDAT", b""), VALID_IEND),
            "IHDR tidak valid",
            id="missing-ihdr",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", b"\x00" * 12), VALID_IDAT, VALID_IEND),
            "IHDR tidak valid",
            id="bad-ihdr-length",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(width=0)), VALID_IDAT, VALID_IEND),
            "dimensi nol",
            id="zero-dimension",
        ),
        pytest.param(
            _png(VALID_IHDR, VALID_IHDR, VALID_IDAT, VALID_IEND),
            "IHDR ganda",
            id="double-ihdr",
        ),
        pytest.param(
            _png(VALID_IHDR, VALID_IEND),
            "IDAT tidak ditemukan",
            id="missing-idat",
        ),
        pytest.param(
            _png(VALID_IHDR, VALID_IDAT),
            "IEND tidak ditemukan",
            id="missing-iend",
        ),
        pytest.param(MINIMAL_PNG + b"x", "data setelah IEND", id="trailing-data"),
        pytest.param(
            MINIMAL_PNG[:-1] + bytes([MINIMAL_PNG[-1] ^ 0xFF]),
            "CRC chunk IEND rusak",
            id="bad-crc",
        ),
        pytest.param(_png(VALID_IHDR) + b"\x00\x00", "chunk terpotong", id="cut-header"),
        pytest.param(
            PNG_SIGNATURE + (0x80000000).to_bytes(4, "big") + b"IDAT" + b"\x00" * 4,
            "panjang chunk tidak valid",
            id="huge-length",
        ),
        pytest.param(
            PNG_SIGNATURE + (0).to_bytes(4, "big") + b"\x00\x00\x00\x00" + b"\x00" * 4,
            "tipe chunk tidak valid",
            id="bad-type",
        ),
        pytest.param(
            PNG_SIGNATURE + (13).to_bytes(4, "big") + b"IHDR" + b"\x00" * 5,
            "chunk terpotong",
            id="cut-ihdr-payload",
        ),
        pytest.param(
            _png(VALID_IHDR) + (10).to_bytes(4, "big") + b"IDAT" + b"abc",
            "chunk terpotong",
            id="cut-idat-payload",
        ),
        pytest.param(
            _png(VALID_IHDR) + (4).to_bytes(4, "big") + b"IDAT" + b"abcd" + b"\x00\x00",
            "CRC terpotong",
            id="cut-crc",
        ),
        pytest.param(
            _png(VALID_IHDR, VALID_IDAT, _chunk(b"IEND", b"x")),
            "IEND tidak valid",
            id="iend-with-payload",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(color_type=1)), VALID_IDAT, VALID_IEND),
            "color type tidak valid",
            id="bad-color-type",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(color_type=0, bit_depth=3)), VALID_IDAT, VALID_IEND),
            "bit depth tidak valid",
            id="bad-bit-depth",
        ),
        pytest.param(
            _png(_chunk(b"IHDR", _ihdr(compression=1)), VALID_IDAT, VALID_IEND),
            "parameter IHDR tidak valid",
            id="bad-ihdr-parameter",
        ),
    ],
)
def test_png_problem_rejects_malformed_chunks(
    tmp_path: Path,
    payload: bytes,
    reason: str,
) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(payload)

    assert _png_problem(path) == reason


def test_png_problem_reports_stat_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(MINIMAL_PNG)
    real_stat = Path.stat

    def fail_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == path:
            raise OSError("stat gagal disengaja")
        return real_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", fail_stat)

    problem = _png_problem(path)

    assert problem is not None
    assert problem.startswith("tidak dapat dibaca")


def test_validate_png_reports_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(MINIMAL_PNG)
    real_open = Path.open

    def fail_open(self: Path, *args: object, **kwargs: object) -> Any:
        if self == path:
            raise OSError("buka gagal disengaja")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_open)

    with pytest.raises(MermaidError, match="tidak dapat dibaca") as error:
        _validate_png(path)

    assert str(path) in str(error.value)


def test_valid_png_passes_validation(tmp_path: Path) -> None:
    path = tmp_path / "flow.png"
    path.write_bytes(MINIMAL_PNG)

    assert _png_problem(path) is None


def test_validated_source_reports_stat_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "flow.mmd"
    path.write_text("flowchart TD\n", encoding="utf-8")
    real_stat = Path.stat
    real_is_file = Path.is_file

    def fail_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == path:
            raise OSError("stat gagal disengaja")
        return real_stat(self, follow_symlinks=follow_symlinks)

    def existing_is_file(self: Path) -> bool:
        if self == path:
            return True
        return real_is_file(self)

    monkeypatch.setattr(Path, "stat", fail_stat)
    monkeypatch.setattr(Path, "is_file", existing_is_file)

    with pytest.raises(MermaidError, match="tidak dapat dibaca") as error:
        _validated_source(path)

    assert str(path) in str(error.value)


def test_source_sha256_streaming_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mermaid_module, "MAX_SOURCE_BYTES", 8)
    source = tmp_path / "flow.mmd"
    source.write_bytes(b"a" * 9)

    with pytest.raises(MermaidError, match="terlalu besar"):
        _source_sha256(source)


def test_mmdc_command_handles_python_and_binary_executables() -> None:
    assert _mmdc_command(Path("tool.py")) == [sys.executable, "tool.py"]
    assert _mmdc_command(Path("tool.pyw")) == [sys.executable, "tool.pyw"]
    assert _mmdc_command(Path("mmdc.exe")) == ["mmdc.exe"]


def test_mmdc_version_timeout_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "mmdc_timeout.py"
    script.write_text("# fake\n", encoding="utf-8")

    def run(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("mmdc", 30)

    monkeypatch.setattr(mermaid_module, "_run_captured", run)

    with pytest.raises(MermaidError, match="melebihi batas waktu"):
        _mmdc_version(script)


def test_mmdc_version_truncated_output_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "mmdc_truncated.py"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setattr(
        mermaid_module,
        "_run_captured",
        lambda *_args, **_kwargs: _completed(stdout="12.2.0", truncated=True),
    )

    with pytest.raises(MermaidError, match="batas output"):
        _mmdc_version(script)


def test_cache_metadata_roundtrip(tmp_path: Path) -> None:
    cache_path = tmp_path / "mermaid-abc.png"
    payload = {
        "format": CACHE_FORMAT,
        "digest": "abc",
        "source_sha256": "a" * 64,
        "theme": {"name": "indigo"},
        "mmdc_version": "12.2.0",
        "options": {"format": "png"},
    }

    _write_cache_metadata(cache_path, payload)

    sidecar = cache_path.with_suffix(".json")
    assert json.loads(sidecar.read_text(encoding="utf-8")) == payload
    assert _read_cache_metadata(sidecar) == payload


def test_read_cache_metadata_rejects_oversized_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mermaid_module, "MAX_CACHE_METADATA_BYTES", 3)
    path = tmp_path / "mermaid-abc.json"
    path.write_text("1234", encoding="utf-8")

    assert _read_cache_metadata(path) is None


def test_read_cache_metadata_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "mermaid-abc.json"
    path.write_text("{", encoding="utf-8")

    assert _read_cache_metadata(path) is None


def test_read_cache_metadata_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "mermaid-abc.json"
    path.write_text("[]", encoding="utf-8")

    assert _read_cache_metadata(path) is None


def test_cache_metadata_matches_rejects_mismatches(theme) -> None:
    fingerprint = _theme_fingerprint(theme)
    background = theme.colors.background
    _arguments, options = _output_arguments("12.2.0", background)
    payload: dict[str, object] = {
        "format": CACHE_FORMAT,
        "source_sha256": "a" * 64,
        "theme": fingerprint,
        "options": options,
    }
    expected = {
        "source_hash": "a" * 64,
        "theme_fingerprint": fingerprint,
        "background": background,
    }

    assert _cache_metadata_matches(payload, **expected)

    mismatches = [
        {**payload, "format": CACHE_FORMAT + 1},
        {**payload, "source_sha256": "b" * 64},
        {**payload, "theme": None},
        {**payload, "theme": {"name": "lain"}},
        {**payload, "options": None},
        {**payload, "options": {**options, "format": "svg"}},
    ]
    for mismatch in mismatches:
        assert _cache_metadata_matches(mismatch, **expected) is False


def test_find_cached_png_returns_none_on_glob_error(
    tmp_path: Path,
    theme,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_glob(*_args: object, **_kwargs: object) -> None:
        raise OSError("glob gagal disengaja")

    monkeypatch.setattr(Path, "glob", fail_glob)

    assert (
        _find_cached_png(
            tmp_path,
            source_hash="a" * 64,
            theme_fingerprint=_theme_fingerprint(theme),
            background=theme.colors.background,
        )
        is None
    )


def test_find_cached_png_removes_unreadable_metadata(
    tmp_path: Path,
    theme,
) -> None:
    metadata = tmp_path / "mermaid-rusak.json"
    metadata.write_text("{", encoding="utf-8")

    result = _find_cached_png(
        tmp_path,
        source_hash="a" * 64,
        theme_fingerprint=_theme_fingerprint(theme),
        background=theme.colors.background,
    )

    assert result is None
    assert not metadata.exists()


def test_find_cached_png_skips_matching_metadata_with_invalid_png(
    tmp_path: Path,
    theme,
) -> None:
    fingerprint = _theme_fingerprint(theme)
    background = theme.colors.background
    _arguments, options = _output_arguments("12.2.0", background)
    source_hash = "a" * 64
    cache_path = tmp_path / "mermaid-abc.png"
    cache_path.write_bytes(b"bukan png")
    _write_cache_metadata(
        cache_path,
        {
            "format": CACHE_FORMAT,
            "digest": "abc",
            "source_sha256": source_hash,
            "theme": fingerprint,
            "mmdc_version": "12.2.0",
            "options": options,
        },
    )

    result = _find_cached_png(
        tmp_path,
        source_hash=source_hash,
        theme_fingerprint=fingerprint,
        background=background,
    )

    assert result is None
    assert not cache_path.exists()
    assert not cache_path.with_suffix(".json").exists()


def test_find_cached_png_returns_valid_match(tmp_path: Path, theme) -> None:
    fingerprint = _theme_fingerprint(theme)
    background = theme.colors.background
    _arguments, options = _output_arguments("12.2.0", background)
    source_hash = "a" * 64
    cache_path = tmp_path / "mermaid-abc.png"
    cache_path.write_bytes(MINIMAL_PNG)
    _write_cache_metadata(
        cache_path,
        {
            "format": CACHE_FORMAT,
            "digest": "abc",
            "source_sha256": source_hash,
            "theme": fingerprint,
            "mmdc_version": "12.2.0",
            "options": options,
        },
    )

    assert (
        _find_cached_png(
            tmp_path,
            source_hash=source_hash,
            theme_fingerprint=fingerprint,
            background=background,
        )
        == cache_path
    )
    assert (
        _find_cached_png(
            tmp_path,
            source_hash="b" * 64,
            theme_fingerprint=fingerprint,
            background=background,
        )
        is None
    )


def test_cache_mtime_returns_zero_on_stat_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_stat(*_args: object, **_kwargs: object) -> None:
        raise OSError("stat gagal disengaja")

    monkeypatch.setattr(Path, "stat", fail_stat)

    assert _cache_mtime(tmp_path / "hilang.json") == 0


def test_discard_cache_entry_ignores_unlink_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / "mermaid-abc.png"
    cache_path.write_bytes(MINIMAL_PNG)
    metadata_path = cache_path.with_suffix(".json")
    metadata_path.write_text("{}", encoding="utf-8")
    attempted: list[Path] = []

    def fail_unlink(self: Path, *_args: object, **_kwargs: object) -> None:
        attempted.append(self)
        raise OSError("hapus gagal disengaja")

    monkeypatch.setattr(Path, "unlink", fail_unlink)

    _discard_cache_entry(cache_path)

    assert attempted == [cache_path, metadata_path]
    assert cache_path.exists()
    assert metadata_path.exists()


def test_output_capture_handles_missing_and_broken_streams() -> None:
    capture = _OutputCapture(4)
    capture.drain(None)
    assert capture.data == b""
    assert capture.truncated is False

    class BrokenStream:
        def __init__(self, error: Exception) -> None:
            self.error = error

        def read(self, _size: int) -> bytes:
            raise self.error

    capture.drain(BrokenStream(OSError("baca gagal")))
    capture.drain(BrokenStream(ValueError("stream tertutup")))

    assert capture.data == b""
    assert capture.truncated is False


def test_output_capture_truncates_at_limit() -> None:
    capture = _OutputCapture(4)

    capture.drain(io.BytesIO(b"abcdef"))

    assert capture.data == b"abcd"
    assert capture.truncated is True


class _FakeThread:
    def __init__(self) -> None:
        self.joins = 0

    def join(self, timeout: float | None = None) -> None:
        self.joins += 1

    def is_alive(self) -> bool:
        return True


class _FakeStream:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False

    def close(self) -> None:
        self.closed = True
        if self.error is not None:
            raise self.error


def test_join_capture_threads_closes_streams_on_stuck_threads() -> None:
    threads = [_FakeThread(), _FakeThread()]
    stream = _FakeStream(error=OSError("tutup gagal"))
    process = SimpleNamespace(stdout=None, stderr=stream)

    _join_capture_threads(threads, process)

    assert [thread.joins for thread in threads] == [2, 2]
    assert stream.closed is True


class _WaitProcess:
    def __init__(self, outcomes: list[Exception | int], *, kill_error: Exception | None = None):
        self.outcomes = list(outcomes)
        self.kill_error = kill_error
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def kill(self) -> None:
        self.killed = True
        if self.kill_error is not None:
            raise self.kill_error


def test_wait_for_exit_kills_after_timeout() -> None:
    process = _WaitProcess([subprocess.TimeoutExpired("mmdc", 5), 0])

    _wait_for_exit(process)

    assert process.killed is True


def test_wait_for_exit_gives_up_after_second_timeout() -> None:
    process = _WaitProcess(
        [
            subprocess.TimeoutExpired("mmdc", 5),
            subprocess.TimeoutExpired("mmdc", 5),
        ]
    )

    _wait_for_exit(process)

    assert process.killed is True


def test_wait_for_exit_returns_when_kill_fails() -> None:
    process = _WaitProcess(
        [subprocess.TimeoutExpired("mmdc", 5)],
        kill_error=OSError("kill gagal"),
    )

    _wait_for_exit(process)

    assert process.killed is True


class _KillableProcess:
    pid = 4321

    def __init__(self) -> None:
        self.killed = False

    def kill(self) -> None:
        self.killed = True


def test_terminate_process_tree_uses_windows_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mermaid_module.os, "name", "nt")
    monkeypatch.setattr(mermaid_module, "_terminate_windows_job", lambda _job: True)
    taskkills: list[int] = []
    monkeypatch.setattr(mermaid_module, "_taskkill_tree", taskkills.append)
    process = _KillableProcess()

    _terminate_process_tree(process, 7)

    assert taskkills == []
    assert process.killed is False


@pytest.mark.parametrize("job", [7, None])
def test_terminate_process_tree_falls_back_to_taskkill(
    monkeypatch: pytest.MonkeyPatch,
    job: int | None,
) -> None:
    monkeypatch.setattr(mermaid_module.os, "name", "nt")
    monkeypatch.setattr(mermaid_module, "_terminate_windows_job", lambda _job: False)
    taskkills: list[int] = []
    monkeypatch.setattr(mermaid_module, "_taskkill_tree", taskkills.append)
    process = _KillableProcess()

    _terminate_process_tree(process, job)

    assert taskkills == [4321]
    assert process.killed is True


def test_terminate_process_tree_posix_uses_killpg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mermaid_module.os, "name", "posix")
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        mermaid_module.os,
        "killpg",
        lambda pid, sig: calls.append((pid, sig)),
        raising=False,
    )
    process = _KillableProcess()

    _terminate_process_tree(process, None)

    expected_signal = getattr(mermaid_module.signal, "SIGKILL", mermaid_module.signal.SIGTERM)
    assert calls == [(4321, expected_signal)]
    assert process.killed is False


def test_terminate_process_tree_posix_process_already_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mermaid_module.os, "name", "posix")
    monkeypatch.delattr(mermaid_module.os, "killpg", raising=False)
    process = _KillableProcess()

    _terminate_process_tree(process, None)

    assert process.killed is True


def test_terminate_process_tree_posix_killpg_raises_process_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mermaid_module.os, "name", "posix")

    def gone(_pid: int, _sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(mermaid_module.os, "killpg", gone, raising=False)
    process = _KillableProcess()

    _terminate_process_tree(process, None)

    assert process.killed is False


def test_terminate_process_tree_posix_falls_back_to_process_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mermaid_module.os, "name", "posix")

    def fail(_pid: int, _sig: int) -> None:
        raise OSError("killpg gagal")

    monkeypatch.setattr(mermaid_module.os, "killpg", fail, raising=False)
    process = _KillableProcess()

    _terminate_process_tree(process, None)

    assert process.killed is True


def test_terminate_process_tree_ignores_process_kill_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mermaid_module.os, "name", "posix")
    monkeypatch.delattr(mermaid_module.os, "killpg", raising=False)

    class KillFailProcess:
        pid = 4321

        def __init__(self) -> None:
            self.kill_calls = 0

        def kill(self) -> None:
            self.kill_calls += 1
            raise OSError("kill gagal")

    process = KillFailProcess()

    _terminate_process_tree(process, None)

    assert process.kill_calls == 1


def test_run_captured_closes_job_when_spawn_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int | None] = []
    monkeypatch.setattr(mermaid_module, "_create_windows_job", lambda: 7)

    def fail_spawn(_command: list[str]) -> None:
        raise OSError("spawn gagal disengaja")

    monkeypatch.setattr(mermaid_module, "_spawn_captured", fail_spawn)
    monkeypatch.setattr(mermaid_module, "_close_windows_job", closed.append)

    with pytest.raises(OSError, match="spawn gagal"):
        _run_captured(["mmdc"], timeout=1)

    assert closed == [7]


class _FakeProcess:
    pid = 1234

    def __init__(self) -> None:
        self.stdout = None
        self.stderr = None
        self.waits = 0

    def wait(self, timeout: float | None = None) -> int:
        self.waits += 1
        return 0


def test_run_captured_closes_job_when_assignment_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int | None] = []
    process = _FakeProcess()
    monkeypatch.setattr(mermaid_module, "_create_windows_job", lambda: 11)
    monkeypatch.setattr(mermaid_module, "_spawn_captured", lambda _command: process)
    monkeypatch.setattr(mermaid_module, "_assign_process_to_job", lambda _job, _pid: False)
    monkeypatch.setattr(mermaid_module, "_close_windows_job", closed.append)

    result = _run_captured(["mmdc"], timeout=1)

    assert result.returncode == 0
    assert closed == [11, None]


def test_spawn_captured_uses_posix_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}

    class FakePopen:
        def __init__(self, command: list[str], **kwargs: Any) -> None:
            recorded["command"] = command
            recorded["kwargs"] = kwargs

    monkeypatch.setattr(mermaid_module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(mermaid_module.os, "name", "posix")

    process = _spawn_captured(["mmdc"])

    assert isinstance(process, FakePopen)
    assert recorded["command"] == ["mmdc"]
    assert recorded["kwargs"]["start_new_session"] is True
    assert "creationflags" not in recorded["kwargs"]


class _FakeFunction:
    def __init__(self, result: int) -> None:
        self.result = result
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.argtypes: list[Any] = []
        self.restype: Any = None

    def __call__(self, *args: Any, **kwargs: Any) -> int:
        self.calls.append((args, kwargs))
        return self.result


def _fake_kernel(**results: int) -> SimpleNamespace:
    return SimpleNamespace(
        CreateJobObjectW=_FakeFunction(results.get("create", 1)),
        SetInformationJobObject=_FakeFunction(results.get("configure", 1)),
        CloseHandle=_FakeFunction(results.get("close", 1)),
        OpenProcess=_FakeFunction(results.get("open", 1)),
        AssignProcessToJobObject=_FakeFunction(results.get("assign", 1)),
        TerminateJobObject=_FakeFunction(results.get("terminate", 1)),
    )


def test_create_windows_job_returns_none_off_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mermaid_module.os, "name", "posix")

    assert _create_windows_job() is None


def test_create_windows_job_returns_none_when_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(create=0)
    monkeypatch.setattr(mermaid_module.os, "name", "nt")
    monkeypatch.setattr(mermaid_module, "_kernel32", lambda: kernel)

    assert _create_windows_job() is None
    assert kernel.CloseHandle.calls == []


def test_create_windows_job_closes_handle_when_configuration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(configure=0)
    monkeypatch.setattr(mermaid_module.os, "name", "nt")
    monkeypatch.setattr(mermaid_module, "_kernel32", lambda: kernel)

    assert _create_windows_job() is None
    assert kernel.CloseHandle.calls == [((1,), {})]


def test_create_windows_job_returns_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(configure=1)
    monkeypatch.setattr(mermaid_module.os, "name", "nt")
    monkeypatch.setattr(mermaid_module, "_kernel32", lambda: kernel)

    assert _create_windows_job() == 1


def test_close_windows_job_ignores_none_and_closes_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel()
    monkeypatch.setattr(mermaid_module, "_kernel32", lambda: kernel)

    _close_windows_job(None)
    assert kernel.CloseHandle.calls == []

    _close_windows_job(7)
    assert kernel.CloseHandle.calls == [((7,), {})]


def test_assign_process_to_job_reports_missing_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(open=0)
    monkeypatch.setattr(mermaid_module, "_kernel32", lambda: kernel)

    assert mermaid_module._assign_process_to_job(1, 2) is False


def test_assign_process_to_job_closes_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(open=2, assign=1)
    monkeypatch.setattr(mermaid_module, "_kernel32", lambda: kernel)

    assert mermaid_module._assign_process_to_job(1, 2) is True
    assert kernel.CloseHandle.calls == [((2,), {})]


def test_terminate_windows_job_returns_success_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _fake_kernel(terminate=1)
    monkeypatch.setattr(mermaid_module, "_kernel32", lambda: kernel)
    assert mermaid_module._terminate_windows_job(1) is True

    kernel = _fake_kernel(terminate=0)
    monkeypatch.setattr(mermaid_module, "_kernel32", lambda: kernel)
    assert mermaid_module._terminate_windows_job(1) is False


def test_taskkill_tree_requires_systemroot(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.delenv("SYSTEMROOT", raising=False)
    monkeypatch.setattr(mermaid_module.subprocess, "run", calls.append)

    _taskkill_tree(1234)

    assert calls == []


def test_taskkill_tree_ignores_missing_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setenv("SYSTEMROOT", str(tmp_path / "Windows"))
    monkeypatch.setattr(mermaid_module.subprocess, "run", calls.append)

    _taskkill_tree(1234)

    assert calls == []


def test_taskkill_tree_uses_absolute_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_root = tmp_path / "Windows"
    executable = system_root / "System32" / "taskkill.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("SYSTEMROOT", str(system_root))
    monkeypatch.setattr(mermaid_module.subprocess, "run", fake_run)

    _taskkill_tree(4321)

    assert calls == [
        (
            [str(executable), "/PID", "4321", "/T", "/F"],
            {
                "stdin": subprocess.DEVNULL,
                "capture_output": True,
                "timeout": mermaid_module.TERMINATE_WAIT_TIMEOUT,
                "check": False,
            },
        )
    ]


@pytest.mark.parametrize("error", [OSError("run gagal"), subprocess.SubprocessError("gagal")])
def test_taskkill_tree_ignores_run_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    system_root = tmp_path / "Windows"
    executable = system_root / "System32" / "taskkill.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")

    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fail_run(command: list[str], **kwargs: Any) -> None:
        calls.append((command, kwargs))
        raise error

    monkeypatch.setenv("SYSTEMROOT", str(system_root))
    monkeypatch.setattr(mermaid_module.subprocess, "run", fail_run)

    _taskkill_tree(4321)

    assert calls == [
        (
            [str(executable), "/PID", "4321", "/T", "/F"],
            {
                "stdin": subprocess.DEVNULL,
                "capture_output": True,
                "timeout": mermaid_module.TERMINATE_WAIT_TIMEOUT,
                "check": False,
            },
        )
    ]


def test_copy_png_fsync_failure_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(MINIMAL_PNG)
    target = tmp_path / "out" / "target.png"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("fsync gagal")

    monkeypatch.setattr(mermaid_module.os, "fsync", fail_fsync)

    with pytest.raises(MermaidError, match="Gagal menulis PNG"):
        _copy_png(source, target)

    assert not target.exists()
    assert list(target.parent.glob(".*.tmp")) == []


def test_copy_png_fdopen_failure_closes_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(MINIMAL_PNG)
    target = tmp_path / "out" / "target.png"

    def fail_fdopen(*_args: object, **_kwargs: object) -> None:
        raise OSError("fdopen gagal")

    monkeypatch.setattr(mermaid_module.os, "fdopen", fail_fdopen)

    with pytest.raises(MermaidError, match="Gagal menulis PNG"):
        _copy_png(source, target)

    assert not target.exists()
    assert list(target.parent.glob(".*.tmp")) == []


def test_write_atomic_bytes_fsync_failure_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "metadata.json"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("fsync gagal")

    monkeypatch.setattr(mermaid_module.os, "fsync", fail_fsync)

    with pytest.raises(MermaidError, match="metadata cache"):
        _write_atomic_bytes(target, b"{}")

    assert not target.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_write_atomic_bytes_fdopen_failure_closes_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "metadata.json"

    def fail_fdopen(*_args: object, **_kwargs: object) -> None:
        raise OSError("fdopen gagal")

    monkeypatch.setattr(mermaid_module.os, "fdopen", fail_fdopen)

    with pytest.raises(MermaidError, match="metadata cache"):
        _write_atomic_bytes(target, b"{}")

    assert not target.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_render_mermaid_writes_cache_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    theme,
) -> None:
    script = tmp_path / "fake_mmdc.py"
    script.write_text(
        "import base64, pathlib, sys\n"
        "arguments = sys.argv[1:]\n"
        "if arguments == ['--version']:\n"
        "    print('12.2.0')\n"
        "    raise SystemExit(0)\n"
        "target = pathlib.Path(arguments[arguments.index('-o') + 1])\n"
        "target.write_bytes(base64.b64decode(\n"
        "    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk'\n"
        "    '+A8AAQUBAScY42YAAAAASUVORK5CYII='\n"
        "))\n",
        encoding="utf-8",
        newline="\n",
    )
    monkeypatch.setenv(mermaid_module.MMDC_ENV_VAR, str(script))
    source = tmp_path / "flow.mmd"
    source.write_text("flowchart TD\n", encoding="utf-8")
    cache = tmp_path / "cache"

    render_mermaid(source, tmp_path / "flow.png", theme=theme, cache_dir=cache)

    sidecars = list(cache.glob("mermaid-*.json"))
    assert len(sidecars) == 1
    payload = _read_cache_metadata(sidecars[0])
    assert payload is not None
    assert payload["format"] == CACHE_FORMAT
