"""Render diagram Mermaid menjadi PNG melalui executable ``mmdc`` eksternal.

Modul ini tidak mengimplementasikan Mermaid di Python. Satu berkas ``.mmd``
dirender oleh Mermaid CLI menjadi PNG resolusi tinggi, lalu disimpan di cache
berbasis SHA-256. Cache key memuat isi sumber, token theme yang disuntikkan,
versi ``mmdc``, dan opsi render.

Referensi: https://github.com/mermaid-js/mermaid-cli
"""

import ctypes
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import zlib
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from autooffice.design.theme import Theme
from autooffice.errors import AutoOfficeError

MMDC_ENV_VAR = "AUTOOFFICE_MMDC"
MMDC_INSTALL_HINT = (
    "Pasang Mermaid CLI dengan `npm install -g @mermaid-js/mermaid-cli` "
    "(butuh Node.js), lalu pastikan `mmdc` ada di PATH atau set "
    f"{MMDC_ENV_VAR} ke path executable mmdc."
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CACHE_FORMAT = 1
CACHE_METADATA_SUFFIX = ".json"
DEFAULT_TIMEOUT = 180
VERSION_TIMEOUT = 30
RENDER_SIZE = 2400
RENDER_SCALE = 2.0
MAX_SOURCE_BYTES = 1_000_000
MAX_OUTPUT_BYTES = 64 * 1024
MAX_CACHE_METADATA_BYTES = 1_000_000
CAPTURE_JOIN_TIMEOUT = 5.0
TERMINATE_WAIT_TIMEOUT = 5.0

_PNG_CRC_SIZE = 4
_PNG_IHDR_SIZE = 13
_PNG_MAX_CHUNK_LENGTH = 0x7FFFFFFF
_PNG_BIT_DEPTHS = {
    0: frozenset({1, 2, 4, 8, 16}),
    2: frozenset({8, 16}),
    3: frozenset({1, 2, 4, 8}),
    4: frozenset({8, 16}),
    6: frozenset({8, 16}),
}

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_WAIT_TIMEOUT = 0x00000102

_VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")
_VERSION_CACHE: dict[tuple[str, int, int], str] = {}

_MMDC_THEME = "base"


class MermaidError(AutoOfficeError, ValueError):
    """Sumber, tool, atau output Mermaid tidak dapat dirender."""


def render_mermaid(
    source: Path,
    out: Path,
    *,
    theme: Theme,
    cache_dir: Path,
) -> Path:
    """Render satu file ``.mmd`` ke PNG dan kembalikan path output.

    ``source`` boleh berupa path relatif atau absolut. Validasi mencegah path
    remote, segmen ``..``, dan output selain PNG. Cache disimpan di
    ``cache_dir`` dengan nama berbasis SHA-256 dari isi sumber, token theme,
    versi ``mmdc``, dan opsi render.

    Cache diperiksa sebelum ``mmdc`` diwajibkan. Bila ``mmdc`` tersedia, cache
    dicari dengan cache key yang memuat versinya; bila ``mmdc`` tidak tersedia,
    metadata cache dipakai untuk menemukan render valid dari versi sebelumnya.
    """
    source_path = _validated_source(source)
    _validate_out(out)
    _validate_cache_dir(cache_dir)
    theme_fingerprint = _theme_fingerprint(theme)
    source_hash = _source_sha256(source_path)

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise MermaidError(
            f"Gagal menyiapkan folder output Mermaid {out.parent}: {error}"
        ) from error

    executable = find_mmdc()
    version: str | None = None
    version_error: MermaidError | None = None
    if executable is not None:
        try:
            version = _mmdc_version(executable)
        except MermaidError as error:
            version_error = error

    if executable is None or version is None:
        cached_path = _find_cached_png(
            cache_dir,
            source_hash=source_hash,
            theme_fingerprint=theme_fingerprint,
            background=theme.colors.background,
        )
        if cached_path is not None:
            _copy_png(cached_path, out)
            return out
        if version_error is not None:
            raise version_error
        raise _missing_mmdc_error()

    arguments, options = _output_arguments(version, theme.colors.background)
    digest = _digest_from_hash(
        source_hash,
        theme_fingerprint,
        version,
        options,
    )
    cache_path = cache_dir / f"mermaid-{digest}.png"
    metadata: dict[str, object] = {
        "format": CACHE_FORMAT,
        "digest": digest,
        "source_sha256": source_hash,
        "theme": theme_fingerprint,
        "mmdc_version": version,
        "options": options,
    }
    if _cache_png_is_valid(cache_path):
        _copy_png(cache_path, out)
        return out

    config = {"theme": _MMDC_THEME, "themeVariables": _theme_variables(theme)}
    try:
        with tempfile.TemporaryDirectory(prefix=".mermaid-", dir=cache_dir) as temporary:
            config_path = Path(temporary) / "config.json"
            config_path.write_text(
                json.dumps(config, sort_keys=True, ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="\n",
            )
            command = [
                *_mmdc_command(executable),
                "-i",
                str(source_path),
                "-o",
                str(out),
                "--theme",
                _MMDC_THEME,
                "--configFile",
                str(config_path),
                *arguments,
            ]
            _run_mmdc(command, target=out, timeout=DEFAULT_TIMEOUT)
    except OSError as error:
        out.unlink(missing_ok=True)
        raise MermaidError(f"Gagal menyiapkan render Mermaid: {error}") from error

    try:
        _validate_png(out)
    except MermaidError:
        out.unlink(missing_ok=True)
        raise
    _copy_png(out, cache_path)
    _write_cache_metadata(cache_path, metadata)
    return out


def cache_digest(source: Path, *, theme: Theme, mmdc_version: str) -> str:
    """Hitung cache key SHA-256 untuk satu sumber dan theme."""
    source_path = _validated_source(source)
    _arguments, options = _output_arguments(mmdc_version, theme.colors.background)
    return _digest_for(source_path, _theme_fingerprint(theme), mmdc_version, options)


def find_mmdc() -> Path | None:
    """Cari ``mmdc`` dari environment override atau ``PATH``."""
    override = os.environ.get(MMDC_ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        return candidate.resolve() if candidate.is_file() else None
    found = shutil.which("mmdc")
    return Path(found).resolve() if found else None


def resolve_mermaid_source(deck_root: Path, relative_path: str) -> Path:
    """Resolve field ``source`` diagram relatif terhadap root deck.

    Menolak URL remote, path absolut, backslash, segmen kosong/``.``/``..``,
    ekstensi selain ``.mmd``, dan path yang keluar dari root deck.
    """
    if not relative_path:
        raise MermaidError("Path diagram tidak boleh kosong.")
    if any(ord(character) < 32 for character in relative_path):
        raise MermaidError("Path diagram tidak boleh memuat karakter kontrol.")
    parsed = urlsplit(relative_path)
    if (parsed.scheme and len(parsed.scheme) > 1) or relative_path.startswith(("//", "\\\\")):
        raise MermaidError(f"Path diagram tidak boleh memakai URL remote: {relative_path!r}.")
    if "\\" in relative_path:
        raise MermaidError(f"Path diagram harus memakai '/': {relative_path!r}.")
    if relative_path.startswith("/") or ":" in relative_path:
        raise MermaidError(
            f"Path diagram harus relatif terhadap direktori deck: {relative_path!r}."
        )
    segments = relative_path.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise MermaidError(
            f"Path diagram tidak boleh memuat segmen kosong, '.', atau '..': {relative_path!r}."
        )
    pure = PurePosixPath(relative_path)
    if pure.suffix.lower() != ".mmd":
        raise MermaidError(
            f"Diagram '{relative_path}' harus berekstensi .mmd, bukan "
            f"'{pure.suffix or 'tanpa ekstensi'}'."
        )
    root = deck_root.resolve()
    resolved = (root / relative_path).resolve()
    if not resolved.is_relative_to(root):
        raise MermaidError(f"Path diagram keluar dari direktori deck: {relative_path!r}.")
    if not resolved.is_file():
        raise MermaidError(f"Diagram tidak ditemukan: {relative_path!r}.")
    return resolved


def _validated_source(source: Path) -> Path:
    if not str(source):
        raise MermaidError("Path diagram tidak boleh kosong.")
    if _is_remote_path(source):
        raise MermaidError(f"Path diagram tidak boleh memakai URL remote: {str(source)!r}.")
    if ":" in str(source) and not (source.drive and source.is_absolute()):
        raise MermaidError(
            f"Path diagram harus relatif terhadap deck atau absolut dengan drive: {str(source)!r}."
        )
    if ".." in source.parts:
        raise MermaidError(f"Path diagram tidak boleh memuat '..': {str(source)!r}.")
    if source.suffix.lower() != ".mmd":
        raise MermaidError(
            f"Diagram '{source}' harus berekstensi .mmd, bukan "
            f"'{source.suffix or 'tanpa ekstensi'}'."
        )
    if source.is_dir():
        raise MermaidError(f"Diagram harus berupa file, bukan direktori: {str(source)!r}.")
    if not source.is_file():
        raise MermaidError(f"Diagram tidak ditemukan: {str(source)!r}.")
    try:
        size = source.stat().st_size
    except OSError as error:
        raise MermaidError(f"Diagram tidak dapat dibaca: {source}: {error}") from error
    if size > MAX_SOURCE_BYTES:
        raise MermaidError(
            f"Diagram Mermaid terlalu besar: {size} byte, "
            f"maksimum {MAX_SOURCE_BYTES} byte untuk {source.name}."
        )
    return source.resolve()


def _is_remote_path(source: Path) -> bool:
    raw = str(source)
    if raw.startswith(("//", "\\\\")):
        return True
    if not source.parts:
        return False
    first = source.parts[0]
    if first.endswith(":") and len(first.rstrip(":")) > 1:
        return True
    return "://" in raw


def _validate_out(out: Path) -> None:
    if out.suffix.lower() != ".png":
        raise MermaidError(f"Output diagram harus PNG, bukan '{out.suffix or 'tanpa ekstensi'}'.")
    if out.exists() and out.is_dir():
        raise MermaidError(f"Output diagram harus berupa file, bukan direktori: {str(out)!r}.")


def _validate_cache_dir(cache_dir: Path) -> None:
    if cache_dir.exists() and not cache_dir.is_dir():
        raise MermaidError(f"Cache Mermaid bukan direktori: {str(cache_dir)!r}.")
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise MermaidError(f"Gagal menyiapkan cache Mermaid {cache_dir}: {error}") from error


def _missing_mmdc_error() -> MermaidError:
    override = os.environ.get(MMDC_ENV_VAR)
    if override:
        return MermaidError(f"mmdc tidak ditemukan: {override}. {MMDC_INSTALL_HINT}")
    return MermaidError(f"mmdc tidak ditemukan di PATH. {MMDC_INSTALL_HINT}")


def _mmdc_command(executable: Path) -> list[str]:
    if executable.suffix.lower() in {".py", ".pyw"}:
        return [sys.executable, str(executable)]
    return [str(executable)]


def _mmdc_version(executable: Path) -> str:
    fingerprint = _executable_fingerprint(executable)
    cached = _VERSION_CACHE.get(fingerprint)
    if cached is not None:
        return cached
    command = [*_mmdc_command(executable), "--version"]
    try:
        result = _run_captured(command, timeout=VERSION_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        raise MermaidError(
            f"mmdc --version melebihi batas waktu {VERSION_TIMEOUT} detik."
        ) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise MermaidError(f"Gagal membaca versi mmdc: {error}") from error
    if result.truncated:
        raise MermaidError(f"Output mmdc --version melebihi batas output {MAX_OUTPUT_BYTES} byte.")
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0 or not output:
        raise MermaidError(
            f"mmdc gagal melaporkan versi (kode {result.returncode}): "
            f"{output[-2000:] or 'tanpa output'}."
        )
    match = _VERSION_RE.search(output)
    version = match.group(0) if match is not None else output.splitlines()[0].strip()
    _VERSION_CACHE[fingerprint] = version
    return version


def _executable_fingerprint(executable: Path) -> tuple[str, int, int]:
    try:
        stat = executable.stat()
    except OSError:
        return (str(executable), 0, 0)
    return (str(executable), stat.st_mtime_ns, stat.st_size)


def _major_version(version: str) -> int | None:
    match = re.match(r"(\d+)\.", version)
    return int(match.group(1)) if match is not None else None


def _output_arguments(version: str, background: str) -> tuple[list[str], dict[str, object]]:
    """Pilih flag ukuran yang didukung versi mmdc dan kembalikan cache options."""
    arguments = [
        "--backgroundColor",
        background,
        "--scale",
        _format_number(RENDER_SCALE),
    ]
    options: dict[str, object] = {
        "format": "png",
        "theme": _MMDC_THEME,
        "backgroundColor": background,
        "scale": RENDER_SCALE,
    }
    major = _major_version(version)
    if major is not None and major >= 12:
        arguments.extend(["--size", str(RENDER_SIZE)])
        options["size"] = RENDER_SIZE
        options["size_flag"] = "--size"
    elif major is not None:
        arguments.extend(["--width", str(RENDER_SIZE)])
        options["size"] = RENDER_SIZE
        options["size_flag"] = "--width"
    return arguments, options


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _theme_fingerprint(theme: Theme) -> dict[str, object]:
    """Serialisasi deterministik seluruh token theme untuk cache key."""
    colors = theme.colors
    return {
        "name": theme.name,
        "mode": theme.mode,
        "colors": {
            "background": colors.background,
            "surface": colors.surface,
            "surface_alt": colors.surface_alt,
            "ink": colors.ink,
            "ink_secondary": colors.ink_secondary,
            "muted": colors.muted,
            "border": colors.border,
            "accent": colors.accent,
            "accent_deep": colors.accent_deep,
            "accent_soft": colors.accent_soft,
            "accent_line": colors.accent_line,
            "accent_ink": colors.accent_ink,
            "status": dict(colors.status),
        },
        "chart": {
            "series": list(theme.chart.series),
            "grid": theme.chart.grid,
            "axis": theme.chart.axis,
            "legend": theme.chart.legend,
            "title": theme.chart.title,
        },
        "typography": {
            "family": theme.typography.family,
            "weights": list(theme.typography.weights),
            "title_pt": theme.typography.title_pt,
            "body_pt": theme.typography.body_pt,
            "minimum_pt": theme.typography.minimum_pt,
            "line_height": theme.typography.line_height,
            "tracking_em": theme.typography.tracking_em,
        },
        "grid": {
            "columns": theme.grid.columns,
            "gutter_emu": theme.grid.gutter_emu,
            "margin_left_emu": theme.grid.margin_left_emu,
            "margin_right_emu": theme.grid.margin_right_emu,
            "margin_top_emu": theme.grid.margin_top_emu,
            "margin_bottom_emu": theme.grid.margin_bottom_emu,
            "row_gap_emu": theme.grid.row_gap_emu,
            "slide_width_emu": theme.grid.slide_width_emu,
            "slide_height_emu": theme.grid.slide_height_emu,
        },
        "spacing": {
            "sm_emu": theme.spacing.sm_emu,
            "md_emu": theme.spacing.md_emu,
            "lg_emu": theme.spacing.lg_emu,
            "card_padding_emu": theme.spacing.card_padding_emu,
            "divider_emu": theme.spacing.divider_emu,
        },
        "radius": {
            "sm_emu": theme.radius.sm_emu,
            "md_emu": theme.radius.md_emu,
            "lg_emu": theme.radius.lg_emu,
        },
        "shadow": {
            "card": theme.shadow.card,
            "overlay": theme.shadow.overlay,
            "none": theme.shadow.none,
        },
        "code": {
            "family": theme.code.family,
            "size_pt": theme.code.size_pt,
            "line_height": theme.code.line_height,
        },
    }


def _theme_variables(theme: Theme) -> dict[str, object]:
    """Terjemahkan token theme menjadi ``themeVariables`` Mermaid."""
    return {
        "darkMode": False,
        "background": theme.colors.background,
        "fontFamily": theme.typography.family,
        "fontSize": f"{theme.typography.body_pt:g}px",
        "primaryColor": theme.colors.accent_soft,
        "primaryTextColor": theme.colors.ink,
        "primaryBorderColor": theme.colors.accent,
        "secondaryColor": theme.colors.surface_alt,
        "secondaryTextColor": theme.colors.ink_secondary,
        "secondaryBorderColor": theme.colors.border,
        "tertiaryColor": theme.colors.surface,
        "tertiaryTextColor": theme.colors.ink,
        "tertiaryBorderColor": theme.colors.border,
        "lineColor": theme.colors.accent_deep,
        "textColor": theme.colors.ink,
        "mainBkg": theme.colors.surface,
        "nodeBorder": theme.colors.accent,
        "clusterBkg": theme.colors.surface_alt,
        "clusterBorder": theme.colors.border,
        "defaultLinkColor": theme.colors.accent_deep,
        "titleColor": theme.colors.ink,
        "edgeLabelBackground": theme.colors.background,
        "nodeTextColor": theme.colors.ink,
    }


def _source_sha256(source: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    try:
        with source.open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SOURCE_BYTES:
                    raise MermaidError(
                        f"Diagram Mermaid terlalu besar: lebih dari "
                        f"{MAX_SOURCE_BYTES} byte untuk {source.name}."
                    )
                digest.update(chunk)
    except OSError as error:
        raise MermaidError(f"Diagram tidak dapat dibaca: {source}: {error}") from error
    return digest.hexdigest()


def _digest_for(
    source: Path,
    theme_fingerprint: Mapping[str, object],
    version: str,
    options: Mapping[str, object],
) -> str:
    return _digest_from_hash(
        _source_sha256(source),
        theme_fingerprint,
        version,
        options,
    )


def _digest_from_hash(
    source_hash: str,
    theme_fingerprint: Mapping[str, object],
    version: str,
    options: Mapping[str, object],
) -> str:
    payload = {
        "format": CACHE_FORMAT,
        "source_sha256": source_hash,
        "theme": theme_fingerprint,
        "mmdc_version": version,
        "options": options,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_png_is_valid(path: Path) -> bool:
    """Validasi PNG cache; entri rusak dihapus agar dirender ulang."""
    if not path.is_file():
        return False
    try:
        _validate_png(path)
    except MermaidError:
        _discard_cache_entry(path)
        return False
    return True


def _discard_cache_entry(png_path: Path) -> None:
    for candidate in (png_path, _cache_metadata_path(png_path)):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            continue


def _cache_metadata_path(png_path: Path) -> Path:
    return png_path.with_suffix(CACHE_METADATA_SUFFIX)


def _find_cached_png(
    cache_dir: Path,
    *,
    source_hash: str,
    theme_fingerprint: Mapping[str, object],
    background: str,
) -> Path | None:
    """Cari PNG cache yang cocok saat versi ``mmdc`` tidak dapat dibaca.

    Pemindaian hanya memakai metadata yang ditulis oleh renderer ini; nama file
    saja tidak cukup karena cache key memuat versi ``mmdc``.
    """
    try:
        candidates = list(cache_dir.glob(f"mermaid-*{CACHE_METADATA_SUFFIX}"))
    except OSError:
        return None
    candidates.sort(key=lambda path: (_cache_mtime(path), path.name), reverse=True)
    for metadata_path in candidates:
        payload = _read_cache_metadata(metadata_path)
        if payload is None:
            with suppress(OSError):
                metadata_path.unlink(missing_ok=True)
            continue
        if not _cache_metadata_matches(
            payload,
            source_hash=source_hash,
            theme_fingerprint=theme_fingerprint,
            background=background,
        ):
            continue
        png_path = metadata_path.with_suffix(".png")
        if _cache_png_is_valid(png_path):
            return png_path
    return None


def _cache_mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _read_cache_metadata(path: Path) -> dict[str, object] | None:
    try:
        if path.stat().st_size > MAX_CACHE_METADATA_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _cache_metadata_matches(
    payload: Mapping[str, object],
    *,
    source_hash: str,
    theme_fingerprint: Mapping[str, object],
    background: str,
) -> bool:
    if payload.get("format") != CACHE_FORMAT:
        return False
    if payload.get("source_sha256") != source_hash:
        return False
    stored_theme = payload.get("theme")
    if not isinstance(stored_theme, dict) or stored_theme != theme_fingerprint:
        return False
    options = payload.get("options")
    if not isinstance(options, dict):
        return False
    return (
        options.get("format") == "png"
        and options.get("theme") == _MMDC_THEME
        and options.get("backgroundColor") == background
        and options.get("scale") == RENDER_SCALE
    )


def _write_cache_metadata(cache_path: Path, payload: Mapping[str, object]) -> None:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _write_atomic_bytes(_cache_metadata_path(cache_path), encoded)


@dataclass(frozen=True)
class _ProcessOutput:
    returncode: int
    stdout: str
    stderr: str
    truncated: bool


class _OutputCapture:
    """Tampung output proses sampai batas byte, lalu buang sisanya."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.data = bytearray()
        self.truncated = False

    def drain(self, stream: Any) -> None:
        if stream is None:
            return
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                remaining = self.limit - len(self.data)
                if remaining > 0:
                    self.data.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    self.truncated = True
        except OSError, ValueError:
            return


def _run_captured(command: list[str], *, timeout: float) -> _ProcessOutput:
    """Jalankan command dalam process group/job dan tangkap output terbatas."""
    job = _create_windows_job()
    try:
        process = _spawn_captured(command)
    except OSError:
        _close_windows_job(job)
        raise
    if job is not None and not _assign_process_to_job(job, process.pid):
        _close_windows_job(job)
        job = None
    stdout_capture = _OutputCapture(MAX_OUTPUT_BYTES)
    stderr_capture = _OutputCapture(MAX_OUTPUT_BYTES)
    threads = [
        threading.Thread(
            target=stdout_capture.drain,
            args=(process.stdout,),
            daemon=True,
        ),
        threading.Thread(
            target=stderr_capture.drain,
            args=(process.stderr,),
            daemon=True,
        ),
    ]
    try:
        for thread in threads:
            thread.start()
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process, job)
            _wait_for_exit(process)
            _join_capture_threads(threads, process)
            raise
        _join_capture_threads(threads, process)
        return _ProcessOutput(
            returncode=returncode,
            stdout=stdout_capture.data.decode("utf-8", errors="replace"),
            stderr=stderr_capture.data.decode("utf-8", errors="replace"),
            truncated=stdout_capture.truncated or stderr_capture.truncated,
        )
    finally:
        _close_windows_job(job)


def _spawn_captured(command: list[str]) -> subprocess.Popen[bytes]:
    if os.name == "nt":
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def _join_capture_threads(
    threads: list[threading.Thread],
    process: subprocess.Popen[bytes],
) -> None:
    for thread in threads:
        thread.join(timeout=CAPTURE_JOIN_TIMEOUT)
    if not any(thread.is_alive() for thread in threads):
        return
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            with suppress(OSError, ValueError):
                stream.close()
    for thread in threads:
        thread.join(timeout=CAPTURE_JOIN_TIMEOUT)


def _wait_for_exit(process: subprocess.Popen[bytes]) -> None:
    try:
        process.wait(timeout=TERMINATE_WAIT_TIMEOUT)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        process.kill()
    except OSError:
        return
    try:
        process.wait(timeout=TERMINATE_WAIT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return


def _terminate_process_tree(
    process: subprocess.Popen[bytes],
    job: int | None,
) -> None:
    if os.name == "nt":
        if job is not None and _terminate_windows_job(job):
            return
        _taskkill_tree(process.pid)
    else:
        killpg = getattr(os, "killpg", None)
        sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
        if killpg is not None:
            try:
                killpg(process.pid, sigkill)
                return
            except ProcessLookupError:
                return
            except OSError:
                pass
    try:
        process.kill()
    except OSError:
        return


def _run_mmdc(command: list[str], *, target: Path, timeout: float) -> None:
    target.unlink(missing_ok=True)
    try:
        result = _run_captured(command, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        target.unlink(missing_ok=True)
        raise MermaidError(
            f"mmdc melebihi batas waktu {timeout:g} detik untuk {target.name}."
        ) from error
    except OSError as error:
        target.unlink(missing_ok=True)
        raise MermaidError(f"Gagal menjalankan mmdc: {error}") from error
    if result.truncated:
        target.unlink(missing_ok=True)
        raise MermaidError(
            f"Output mmdc melebihi batas output {MAX_OUTPUT_BYTES} byte untuk {target.name}."
        )
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout or "").strip()
        suffix = f": {detail[-2000:]}" if detail else ""
        raise MermaidError(f"mmdc gagal (kode {result.returncode}) untuk {target.name}{suffix}")


def _is_png(path: Path) -> bool:
    """True hanya bila path berisi PNG lengkap dengan IHDR/IDAT/IEND."""
    return _png_problem(path) is None


def _validate_png(path: Path) -> None:
    if not path.is_file():
        raise MermaidError(f"mmdc tidak menghasilkan PNG untuk {path.name}.")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise MermaidError(f"PNG Mermaid tidak dapat dibaca: {path}: {error}") from error
    if size == 0:
        raise MermaidError(f"mmdc tidak menghasilkan PNG untuk {path.name}.")
    problem = _png_problem(path)
    if problem is None:
        return
    if problem.startswith("tidak dapat dibaca"):
        raise MermaidError(f"PNG Mermaid tidak dapat dibaca: {path}: {problem}")
    raise MermaidError(f"Output mmdc bukan PNG valid untuk {path.name}: {problem}.")


def _png_problem(path: Path) -> str | None:
    """Periksa struktur chunk PNG dan kembalikan alasan bila tidak lengkap."""
    try:
        size = path.stat().st_size
    except OSError as error:
        return f"tidak dapat dibaca ({error})"
    minimum = len(PNG_SIGNATURE) + 8 + _PNG_CRC_SIZE
    if size < minimum:
        return "terlalu pendek"
    try:
        with path.open("rb") as handle:
            if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                return "signature tidak valid"
            first = True
            seen_idat = False
            while True:
                header = handle.read(8)
                if not header:
                    return "IEND tidak ditemukan"
                if len(header) != 8:
                    return "chunk terpotong"
                length = int.from_bytes(header[:4], "big")
                chunk_type = header[4:]
                if length > _PNG_MAX_CHUNK_LENGTH:
                    return "panjang chunk tidak valid"
                if len(chunk_type) != 4 or not chunk_type.isalpha():
                    return "tipe chunk tidak valid"
                if first and (chunk_type != b"IHDR" or length != _PNG_IHDR_SIZE):
                    return "IHDR tidak valid"
                if not first and chunk_type == b"IHDR":
                    return "IHDR ganda"
                crc = zlib.crc32(chunk_type)
                if chunk_type == b"IHDR":
                    payload = handle.read(length)
                    if len(payload) != length:
                        return "chunk terpotong"
                    crc = zlib.crc32(payload, crc)
                    ihdr_problem = _ihdr_problem(payload)
                    if ihdr_problem is not None:
                        return ihdr_problem
                else:
                    remaining = length
                    while remaining:
                        block = handle.read(min(65536, remaining))
                        if not block:
                            return "chunk terpotong"
                        crc = zlib.crc32(block, crc)
                        remaining -= len(block)
                stored_crc = handle.read(_PNG_CRC_SIZE)
                if len(stored_crc) != _PNG_CRC_SIZE:
                    return "CRC terpotong"
                if int.from_bytes(stored_crc, "big") != crc & 0xFFFFFFFF:
                    return f"CRC chunk {chunk_type.decode('ascii', 'replace')} rusak"
                if first:
                    first = False
                if chunk_type == b"IDAT":
                    seen_idat = True
                elif chunk_type == b"IEND":
                    if length != 0:
                        return "IEND tidak valid"
                    if not seen_idat:
                        return "IDAT tidak ditemukan"
                    if handle.read(1):
                        return "data setelah IEND"
                    return None
    except OSError as error:
        return f"tidak dapat dibaca ({error})"


def _ihdr_problem(payload: bytes) -> str | None:
    width = int.from_bytes(payload[0:4], "big")
    height = int.from_bytes(payload[4:8], "big")
    bit_depth = payload[8]
    color_type = payload[9]
    compression = payload[10]
    filter_method = payload[11]
    interlace = payload[12]
    if width == 0 or height == 0:
        return "dimensi nol"
    allowed_depths = _PNG_BIT_DEPTHS.get(color_type)
    if allowed_depths is None:
        return "color type tidak valid"
    if bit_depth not in allowed_depths:
        return "bit depth tidak valid"
    if compression != 0 or filter_method != 0 or interlace not in {0, 1}:
        return "parameter IHDR tidak valid"
    return None


def _copy_png(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        return
    temporary: Path | None = None
    descriptor = -1
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as writer:
            descriptor = -1
            with source.open("rb") as reader:
                shutil.copyfileobj(reader, writer)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, target)
        temporary = None
    except OSError as error:
        raise MermaidError(f"Gagal menulis PNG Mermaid {target}: {error}") from error
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


def _write_atomic_bytes(target: Path, data: bytes) -> None:
    temporary: Path | None = None
    descriptor = -1
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as writer:
            descriptor = -1
            writer.write(data)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, target)
        temporary = None
    except OSError as error:
        raise MermaidError(f"Gagal menulis metadata cache Mermaid {target}: {error}") from error
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


class _JobBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("per_process_user_time_limit", ctypes.c_int64),
        ("per_job_user_time_limit", ctypes.c_int64),
        ("limit_flags", ctypes.c_uint32),
        ("minimum_working_set_size", ctypes.c_size_t),
        ("maximum_working_set_size", ctypes.c_size_t),
        ("active_process_limit", ctypes.c_uint32),
        ("affinity", ctypes.c_size_t),
        ("priority_class", ctypes.c_uint32),
        ("scheduling_class", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("read_operation_count", ctypes.c_uint64),
        ("write_operation_count", ctypes.c_uint64),
        ("other_operation_count", ctypes.c_uint64),
        ("read_transfer_count", ctypes.c_uint64),
        ("write_transfer_count", ctypes.c_uint64),
        ("other_transfer_count", ctypes.c_uint64),
    ]


class _JobExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("basic_limit_information", _JobBasicLimitInformation),
        ("io_info", _IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory_used", ctypes.c_size_t),
        ("peak_job_memory_used", ctypes.c_size_t),
    ]


def _kernel32() -> Any:
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _create_windows_job() -> int | None:
    if os.name != "nt":
        return None
    kernel32 = _kernel32()
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        return None
    information = _JobExtendedLimitInformation()
    information.basic_limit_information.limit_flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    configured = kernel32.SetInformationJobObject(
        handle,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(information),
        ctypes.sizeof(information),
    )
    if not configured:
        _close_windows_handle(handle)
        return None
    return int(handle)


def _assign_process_to_job(job: int, pid: int) -> bool:
    kernel32 = _kernel32()
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    process_handle = kernel32.OpenProcess(
        _PROCESS_SET_QUOTA | _PROCESS_TERMINATE,
        0,
        pid,
    )
    if not process_handle:
        return False
    try:
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel32.AssignProcessToJobObject.restype = ctypes.c_int
        return bool(kernel32.AssignProcessToJobObject(job, process_handle))
    finally:
        _close_windows_handle(process_handle)


def _terminate_windows_job(job: int) -> bool:
    kernel32 = _kernel32()
    kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.TerminateJobObject.restype = ctypes.c_int
    return bool(kernel32.TerminateJobObject(job, 1))


def _close_windows_job(job: int | None) -> None:
    if job is not None:
        _close_windows_handle(job)


def _close_windows_handle(handle: object) -> None:
    kernel32 = _kernel32()
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.CloseHandle(handle)


def _taskkill_tree(pid: int) -> None:
    """Fallback Windows: kill the tree via absolute taskkill.exe, never PATH."""
    system_root = os.environ.get("SYSTEMROOT")
    if not system_root:
        return
    executable = Path(system_root) / "System32" / "taskkill.exe"
    if not executable.is_file():
        return
    try:
        subprocess.run(
            [str(executable), "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TERMINATE_WAIT_TIMEOUT,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return


__all__ = [
    "MMDC_ENV_VAR",
    "MMDC_INSTALL_HINT",
    "MermaidError",
    "cache_digest",
    "find_mmdc",
    "render_mermaid",
    "resolve_mermaid_source",
]
