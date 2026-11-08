"""Render diagram Mermaid inline menjadi PNG untuk pipeline laporan.

Penulis menulis diagram sebagai code fence dengan caption wajib:

.. code-block:: markdown

   ```{.mermaid caption="Diagram pipeline"}
   flowchart TD
     A --> B
   ```

Blok diganti dengan gambar Markdown ``![caption](gambar/mermaid-<hash>.png)``.
PNG ditulis ke ``<folder tugas>/gambar``. Nomor ``Gambar bab.n`` tidak dibuat
di sini; pipeline caption DOCX yang sudah ada mengambil alt text gambar dan
memberi nomor per bab.

Pemakaian dari akar repositori::

    python src/laporan/mermaid.py --src chapters --out-dir . --mmdc mmdc

``mmdc`` default-nya dicari di ``PATH``. Setiap diagram di-hash dari isi
Mermaid dan opsi render; berkas PNG yang sudah ada dipakai ulang tanpa
memanggil ``mmdc`` lagi.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

IMAGE_DIR = "gambar"
HASH_LENGTH = 12
DEFAULT_TIMEOUT = 180
UTF8_BOM = b"\xef\xbb\xbf"

MMDC_INSTALL_HINT = (
    "Pasang Mermaid CLI dengan `npm install -g @mermaid-js/mermaid-cli` "
    "(butuh Node.js), lalu pastikan `mmdc` ada di PATH atau berikan "
    "--mmdc <path>."
)

_FENCE_OPEN_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$"
)
_LANGUAGE_RE = re.compile(r"^\.?mermaid(?=$|[\s{])", re.IGNORECASE)
_CAPTION_RE = re.compile(
    r"""(?<![\w-])caption\s*=\s*(?:"(?P<double>(?:\\.|[^"\\])*)"|'(?P<single>(?:\\.|[^'\\])*)')""",
    re.IGNORECASE,
)


class MermaidError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Opsi visual yang diteruskan ke ``mmdc`` dan ikut di-hash."""

    theme: str | None = None
    background: str | None = None
    size: int | None = None
    scale: float | None = None

    def as_dict(self) -> dict[str, object]:
        options: dict[str, object] = {}
        if self.theme is not None:
            options["theme"] = self.theme
        if self.background is not None:
            options["background"] = self.background
        if self.size is not None:
            options["size"] = int(self.size)
        if self.scale is not None:
            options["scale"] = float(self.scale)
        return options

    def arguments(self) -> list[str]:
        arguments: list[str] = []
        if self.theme is not None:
            arguments.extend(["--theme", self.theme])
        if self.background is not None:
            arguments.extend(["--backgroundColor", self.background])
        if self.size is not None:
            arguments.extend(["--size", str(self.size)])
        if self.scale is not None:
            arguments.extend(["--scale", str(self.scale)])
        return arguments


@dataclass(frozen=True, slots=True)
class MermaidBlock:
    """Satu code fence Mermaid beserta posisinya di daftar baris."""

    start: int
    """Indeks baris pembuka (0-based)."""

    end: int
    """Indeks baris setelah penutup (0-based, eksklusif)."""

    line: int
    """Nomor baris pembuka (1-based) untuk pesan kesalahan."""

    code: str
    caption: str
    info: str
    indent: str

    @property
    def content(self) -> str:
        """Alias isi Mermaid, memudahkan pemakaian sebagai API."""

        return self.code


@dataclass(frozen=True, slots=True)
class BlockPlan:
    """Rencana penggantian satu blok tanpa menyentuh berkas."""

    block: MermaidBlock
    digest: str
    relative_path: str
    image_path: Path
    markdown: str


@dataclass(frozen=True, slots=True)
class FileResult:
    path: Path
    diagrams: int
    rendered: int
    reused: int
    changed: bool


@dataclass(frozen=True, slots=True)
class ProcessReport:
    files: tuple[FileResult, ...]
    diagrams: int
    rendered: int
    reused: int

    @property
    def changed_files(self) -> int:
        return sum(1 for result in self.files if result.changed)


# ---------------------------------------------------------------------------
# Ekstraksi dan penggantian Markdown


def _strip_eol(line: str) -> str:
    return line.rstrip("\r\n")


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return ""


def _default_line_ending(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    if "\n" in text:
        return "\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _location(path: str | Path | None, line: int) -> str:
    if path is None:
        return f"baris {line}: "
    return f"{path}:{line}: "


def _mermaid_attributes(info: str) -> str | None:
    """Kembalikan atribut bila info string adalah fence Mermaid.

    Bentuk yang didukung: ``{.mermaid caption="..."}``, ``.mermaid
    caption="..."``, dan ``mermaid``. ``None`` berarti fence biasa.
    """

    text = info.strip()
    if not text:
        return None
    if text.startswith("{"):
        if not text.endswith("}"):
            return None
        text = text[1:-1].strip()

    match = _LANGUAGE_RE.match(text)
    if match is None:
        return None

    attributes = text[match.end() :].strip()
    if attributes.startswith("{") and attributes.endswith("}"):
        attributes = attributes[1:-1].strip()
    return attributes


def _caption_from_attributes(attributes: str) -> str | None:
    match = _CAPTION_RE.search(attributes)
    if match is None:
        return None
    value = match.group("double")
    if value is None:
        value = match.group("single") or ""
    return value.replace('\\"', '"').replace("\\'", "'").strip()


def _closing_fence_re(fence_character: str, minimum: int) -> re.Pattern[str]:
    return re.compile(
        rf"^[ \t]*{re.escape(fence_character)}{{{minimum},}}[ \t]*$"
    )


def extract_blocks(
    text: str,
    path: str | Path | None = None,
) -> list[MermaidBlock]:
    """Ekstrak seluruh blok Mermaid dari ``text``.

    ``MermaidError`` dilempar bila caption wajib tidak ada, caption kosong,
    isi diagram kosong, atau blok Mermaid tidak ditutup. Fence non-Mermaid
    diabaikan sepenuhnya.
    """

    lines = text.splitlines(keepends=True)
    blocks: list[MermaidBlock] = []
    index = 0

    while index < len(lines):
        opener = _FENCE_OPEN_RE.match(_strip_eol(lines[index]))
        if opener is None:
            index += 1
            continue

        fence = opener.group("fence")
        closing = _closing_fence_re(fence[0], len(fence))
        info = opener.group("info")
        start = index
        content: list[str] = []
        index += 1
        closed = False

        while index < len(lines):
            current = _strip_eol(lines[index])
            if closing.fullmatch(current):
                closed = True
                break
            content.append(current)
            index += 1

        attributes = _mermaid_attributes(info)
        line = start + 1

        if not closed:
            if attributes is not None:
                raise MermaidError(
                    f"{_location(path, line)}blok Mermaid tidak ditutup; "
                    f"tambahkan fence penutup {fence}."
                )
            break

        end = index + 1
        if attributes is not None:
            code = "\n".join(content)
            if not code.strip():
                raise MermaidError(
                    f"{_location(path, line)}isi diagram Mermaid kosong."
                )

            caption = _caption_from_attributes(attributes)
            if not caption:
                raise MermaidError(
                    f"{_location(path, line)}blok Mermaid wajib memiliki "
                    'caption; tulis caption="..." pada pembuka blok, mis. '
                    '```{.mermaid caption="Diagram pipeline"}.'
                )

            blocks.append(
                MermaidBlock(
                    start=start,
                    end=end,
                    line=line,
                    code=code,
                    caption=caption or "",
                    info=info.strip(),
                    indent=opener.group("indent"),
                )
            )

        index = end

    return blocks


def _normalize_code(code: str) -> str:
    normalized = code.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _options_payload(
    options: RenderOptions | Mapping[str, object] | None,
) -> dict[str, object]:
    if options is None:
        return {}
    if isinstance(options, RenderOptions):
        return options.as_dict()
    payload: dict[str, object] = {}
    for key in sorted(options, key=str):
        value = options[key]
        if value is None:
            continue
        if key == "size":
            value = int(value)
        elif key == "scale":
            value = float(value)
        payload[str(key)] = value
    return payload


def render_hash(
    code: str,
    options: RenderOptions | Mapping[str, object] | None = None,
) -> str:
    """Hash isi Mermaid dan opsi render; stabil untuk isi yang sama."""

    payload = json.dumps(
        {
            "version": 1,
            "code": _normalize_code(code),
            "options": _options_payload(options),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:HASH_LENGTH]


def _escape_alt_text(caption: str) -> str:
    return caption.replace("\\", "\\\\").replace("]", "\\]")


def plan_blocks(
    text: str,
    out_dir: str | Path,
    options: RenderOptions | Mapping[str, object] | None = None,
    *,
    path: str | Path | None = None,
) -> list[BlockPlan]:
    """Hitung hash, path gambar, dan baris Markdown pengganti."""

    out_path = Path(out_dir)
    plans: list[BlockPlan] = []

    for block in extract_blocks(text, path=path):
        digest = render_hash(block.code, options)
        filename = f"mermaid-{digest}.png"
        relative_path = f"{IMAGE_DIR}/{filename}"
        plans.append(
            BlockPlan(
                block=block,
                digest=digest,
                relative_path=relative_path,
                image_path=out_path / IMAGE_DIR / filename,
                markdown=f"![{_escape_alt_text(block.caption)}]({relative_path})",
            )
        )

    return plans


def rewrite_markdown(text: str, plans: Sequence[BlockPlan]) -> str:
    """Ganti blok Mermaid dengan gambar Markdown tanpa mengubah baris lain."""

    if not plans:
        return text

    lines = text.splitlines(keepends=True)
    default_ending = _default_line_ending(text)
    pieces: list[str] = []
    cursor = 0

    for plan in sorted(plans, key=lambda item: item.block.start):
        block = plan.block
        if block.start < cursor or block.end < block.start:
            raise MermaidError("Rencana penggantian Mermaid tumpang tindih.")
        if block.end > len(lines):
            raise MermaidError("Rencana penggantian Mermaid di luar batas berkas.")

        pieces.extend(lines[cursor : block.start])
        ending = _line_ending(lines[block.start]) or default_ending
        if block.end == len(lines) and not _line_ending(lines[block.end - 1]):
            ending = ""
        pieces.append(f"{block.indent}{plan.markdown}{ending}")
        cursor = block.end

    pieces.extend(lines[cursor:])
    return "".join(pieces)


def replace_markdown_blocks(
    text: str,
    out_dir: str | Path,
    options: RenderOptions | Mapping[str, object] | None = None,
    *,
    path: str | Path | None = None,
) -> str:
    """Versi murni: ganti blok dengan gambar Markdown tanpa render."""

    return rewrite_markdown(text, plan_blocks(text, out_dir, options, path=path))


# ---------------------------------------------------------------------------
# Render


def find_mmdc(explicit: str | Path | None = None) -> str | None:
    """Cari ``mmdc`` eksplisit atau di ``PATH``."""

    if explicit is not None:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
        return shutil.which(str(explicit))
    return shutil.which("mmdc")


def _mmdc_missing_message(explicit: str | Path | None = None) -> str:
    if explicit is None:
        return f"mmdc tidak ditemukan di PATH. {MMDC_INSTALL_HINT}"
    return f"mmdc tidak ditemukan: {explicit}. {MMDC_INSTALL_HINT}"


def _render_error_detail(completed: subprocess.CompletedProcess[str]) -> str:
    output = (completed.stderr or completed.stdout or "").strip()
    if not output:
        return ""
    return f": {output[-2000:]}"


def _mmdc_command(executable: str) -> list[str]:
    """Prefix perintah; skrip Python tetap bisa dipakai di Windows untuk tes."""

    if Path(executable).suffix.lower() in {".py", ".pyw"}:
        return [sys.executable, executable]
    return [executable]


def render_mermaid(
    code: str,
    output_png: str | Path,
    mmdc: str | Path | None = None,
    options: RenderOptions | Mapping[str, object] | None = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> Path:
    """Render satu diagram ke ``output_png`` memakai ``mmdc``.

    ``output_png`` diberikan langsung ke ``mmdc`` sebagai ``-o`` agar nama
    berkas akhir persis ``mermaid-<hash>.png``. Bila render gagal, berkas
    parsial dibersihkan.
    """

    target = Path(output_png)
    if target.is_file():
        return target

    executable = find_mmdc(mmdc)
    if executable is None:
        raise MermaidError(_mmdc_missing_message(mmdc))

    if isinstance(options, Mapping):
        render_options = RenderOptions(**dict(options))
    else:
        render_options = options or RenderOptions()

    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="laporan-mermaid-") as temp_dir:
            source = Path(temp_dir) / "diagram.mmd"
            source.write_text(_normalize_code(code), encoding="utf-8", newline="\n")
            command = [
                *_mmdc_command(executable),
                "-i",
                str(source),
                "-o",
                str(target),
                *render_options.arguments(),
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise MermaidError(
                    f"mmdc melebihi batas waktu {timeout} detik untuk "
                    f"{target.name}."
                ) from exc
            except OSError as exc:
                raise MermaidError(f"Gagal menjalankan mmdc: {exc}") from exc

        if completed.returncode != 0:
            raise MermaidError(
                f"mmdc gagal (kode {completed.returncode}) untuk {target.name}"
                f"{_render_error_detail(completed)}"
            )
        if not target.is_file() or target.stat().st_size == 0:
            raise MermaidError(
                f"mmdc tidak menghasilkan PNG untuk {target.name}."
            )
    except BaseException:
        target.unlink(missing_ok=True)
        raise

    return target


# ---------------------------------------------------------------------------
# Pemrosesan berkas


def expand_sources(src: str | Path) -> list[Path]:
    """Terima satu berkas ``.md`` atau direktori; direktori rekursif."""

    source = Path(src)
    if source.is_dir():
        files = sorted(
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.lower() == ".md"
        )
    elif source.is_file():
        if source.suffix.lower() != ".md":
            raise MermaidError(
                f"--src harus berkas .md atau direktori: {source}"
            )
        files = [source]
    else:
        raise MermaidError(f"Sumber tidak ditemukan: {source}")

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _read_markdown(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(UTF8_BOM)
    try:
        return raw.decode("utf-8-sig"), has_bom
    except UnicodeDecodeError as exc:
        raise MermaidError(f"Markdown bukan UTF-8 yang valid: {path}") from exc


def _write_markdown(path: Path, text: str, has_bom: bool) -> None:
    data = text.encode("utf-8")
    if has_bom:
        data = UTF8_BOM + data

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        if path.exists():
            shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def process_files(
    files: Iterable[str | Path],
    out_dir: str | Path,
    mmdc: str | Path | None = None,
    options: RenderOptions | Mapping[str, object] | None = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> ProcessReport:
    """Render seluruh diagram lalu tulis Markdown yang berubah.

    Semua berkas diekstrak lebih dulu. Bila ada caption yang hilang, tidak
    ada PNG yang dirender dan tidak ada Markdown yang ditulis.
    """

    out_path = Path(out_dir)
    if out_path.exists() and not out_path.is_dir():
        raise MermaidError(f"--out-dir bukan direktori: {out_path}")

    prepared: list[tuple[Path, str, bool, list[BlockPlan]]] = []
    for item in files:
        path = Path(item)
        text, has_bom = _read_markdown(path)
        plans = plan_blocks(text, out_path, options, path=path)
        prepared.append((path, text, has_bom, plans))

    render_queue: list[BlockPlan] = []
    queued: set[str] = set()
    for _path, _text, _bom, plans in prepared:
        for plan in plans:
            if plan.image_path.is_file() or plan.digest in queued:
                continue
            queued.add(plan.digest)
            render_queue.append(plan)

    if render_queue:
        executable = find_mmdc(mmdc)
        if executable is None:
            raise MermaidError(_mmdc_missing_message(mmdc))
        for plan in render_queue:
            render_mermaid(
                plan.block.code,
                plan.image_path,
                executable,
                options,
                timeout=timeout,
            )

    new_digests = {plan.digest for plan in render_queue}
    results: list[FileResult] = []
    total_diagrams = 0

    for path, text, has_bom, plans in prepared:
        total_diagrams += len(plans)
        new_text = rewrite_markdown(text, plans)
        changed = new_text != text
        if changed:
            _write_markdown(path, new_text, has_bom)

        rendered = len({plan.digest for plan in plans if plan.digest in new_digests})
        reused = len(plans) - rendered
        results.append(
            FileResult(
                path=path,
                diagrams=len(plans),
                rendered=rendered,
                reused=reused,
                changed=changed,
            )
        )

    return ProcessReport(
        files=tuple(results),
        diagrams=total_diagrams,
        rendered=len(render_queue),
        reused=total_diagrams - len(render_queue),
    )


def process(
    src: str | Path,
    out_dir: str | Path,
    mmdc: str | Path | None = None,
    options: RenderOptions | Mapping[str, object] | None = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> ProcessReport:
    """Proses satu berkas atau direktori sumber Markdown."""

    return process_files(
        expand_sources(src), out_dir, mmdc, options, timeout=timeout
    )


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="laporan.mermaid",
        description=(
            "Render blok ```{.mermaid caption=\"...\"} menjadi PNG dan "
            "ganti blok dengan gambar Markdown."
        ),
    )
    parser.add_argument(
        "--src", required=True, type=Path, help="berkas .md atau direktori sumber"
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="folder tugas; PNG ditulis ke <out-dir>/gambar",
    )
    parser.add_argument(
        "--mmdc",
        type=Path,
        help="path executable mmdc (default: cari di PATH)",
    )
    parser.add_argument("--theme", help="tema Mermaid, mis. default, dark, forest")
    parser.add_argument("--background", help="warna latar PNG")
    parser.add_argument(
        "--size", type=int, help="ukuran maksimum PNG dalam piksel (--size mmdc)"
    )
    parser.add_argument("--scale", type=float, help="skala render mmdc")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"batas waktu per diagram dalam detik (default: {DEFAULT_TIMEOUT})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(
        None if argv is None else [str(item) for item in argv]
    )

    options = RenderOptions(
        theme=args.theme,
        background=args.background,
        size=args.size,
        scale=args.scale,
    )

    try:
        report = process(
            args.src,
            args.out_dir,
            args.mmdc,
            options,
            timeout=args.timeout,
        )
    except (MermaidError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: Dibatalkan oleh pengguna.", file=sys.stderr)
        return 130

    if report.diagrams == 0:
        print(
            f"[OK] Tidak ada blok Mermaid pada {len(report.files)} "
            "berkas Markdown."
        )
        return 0

    print(
        f"[OK] {report.diagrams} diagram Mermaid di {len(report.files)} "
        f"berkas: {report.rendered} dirender, {report.reused} memakai cache; "
        f"{report.changed_files} berkas diperbarui."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
