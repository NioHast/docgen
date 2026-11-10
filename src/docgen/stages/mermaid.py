"""Render blok Mermaid inline menjadi PNG untuk pipeline ``docgen``.

Penulis menulis diagram sebagai code fence dengan caption wajib:

.. code-block:: markdown

   ```{.mermaid caption="Diagram pipeline"}
   flowchart TD
     A --> B
   ```

``render_blocks`` mengganti blok dengan gambar Markdown
``![caption](gambar/mermaid-<hash>.png)`` dan menulis PNG ke
``<base_dir>/gambar``. Nomor ``Gambar bab.n`` tidak dibuat di sini; stage
caption DOCX yang memberi nomor per bab.

Modul ini hanya menyediakan API render dan stage ``MermaidStage``; orkestrasi
urutan tetap milik ``docgen.pipeline``.

Setiap diagram di-hash dari isi Mermaid dan opsi render. Berkas PNG yang sudah
ada dipakai ulang tanpa memanggil ``mmdc`` lagi.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..errors import DocgenError, StageError, ToolMissingError
from ..pipeline import BaseStage, StageName, StageResult

IMAGE_DIR = "gambar"
HASH_LENGTH = 12
DEFAULT_TIMEOUT = 180

MMDC_INSTALL_HINT = (
    "Pasang Mermaid CLI dengan `npm install -g @mermaid-js/mermaid-cli` "
    "(butuh Node.js), lalu pastikan `mmdc` ada di PATH atau berikan "
    "path mmdc secara eksplisit."
)

_FENCE_OPEN_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_LANGUAGE_RE = re.compile(r"^\.?mermaid(?=$|[\s{])", re.IGNORECASE)
_CAPTION_RE = re.compile(
    r"""(?<![\w-])caption\s*=\s*(?:"(?P<double>(?:\\.|[^"\\])*)"|'(?P<single>(?:\\.|[^'\\])*)')""",
    re.IGNORECASE,
)


class MermaidError(DocgenError):
    """Kesalahan input atau render Mermaid yang aman ditampilkan ke pengguna."""

    default_code = "MERMAID"


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
class _BlockPlan:
    """Rencana penggantian satu blok tanpa menyentuh berkas."""

    block: MermaidBlock
    digest: str
    relative_path: str
    image_path: Path
    markdown: str


# ---------------------------------------------------------------------------
# Ekstraksi dan penggantian Markdown
# ---------------------------------------------------------------------------


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
    return re.compile(rf"^[ \t]*{re.escape(fence_character)}{{{minimum},}}[ \t]*$")


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
                raise MermaidError(f"{_location(path, line)}isi diagram Mermaid kosong.")

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
                    caption=caption,
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
            if not isinstance(value, str | int | float):
                raise TypeError(f"opsi mermaid 'size' harus angka, bukan {type(value).__name__}")
            value = int(value)
        elif key == "scale":
            if not isinstance(value, str | int | float):
                raise TypeError(f"opsi mermaid 'scale' harus angka, bukan {type(value).__name__}")
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


def _plan_blocks(
    blocks: list[MermaidBlock],
    base_dir: str | Path,
    options: RenderOptions | Mapping[str, object] | None,
) -> list[_BlockPlan]:
    out_path = Path(base_dir)
    plans: list[_BlockPlan] = []

    for block in blocks:
        digest = render_hash(block.code, options)
        filename = f"mermaid-{digest}.png"
        relative_path = f"{IMAGE_DIR}/{filename}"
        plans.append(
            _BlockPlan(
                block=block,
                digest=digest,
                relative_path=relative_path,
                image_path=out_path / IMAGE_DIR / filename,
                markdown=f"![{_escape_alt_text(block.caption)}]({relative_path})",
            )
        )

    return plans


def _rewrite_markdown(text: str, plans: list[_BlockPlan]) -> str:
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


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


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


def _as_render_options(
    options: RenderOptions | Mapping[str, object] | None,
) -> RenderOptions:
    if options is None or isinstance(options, RenderOptions):
        return options or RenderOptions()
    payload = _options_payload(options)
    theme = payload.get("theme")
    background = payload.get("background")
    size = payload.get("size")
    scale = payload.get("scale")
    return RenderOptions(
        theme=theme if isinstance(theme, str) else None,
        background=background if isinstance(background, str) else None,
        size=size if isinstance(size, int) else None,
        scale=scale if isinstance(scale, float) else None,
    )


def _render_mermaid(
    code: str,
    output_png: str | Path,
    executable: str,
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

    render_options = _as_render_options(options)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MermaidError(f"Gagal menyiapkan folder gambar {target.parent}: {exc}") from exc

    try:
        with tempfile.TemporaryDirectory(prefix="docgen-mermaid-") as temp_dir:
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
                    f"mmdc melebihi batas waktu {timeout} detik untuk {target.name}."
                ) from exc
            except OSError as exc:
                raise MermaidError(f"Gagal menjalankan mmdc: {exc}") from exc

        if completed.returncode != 0:
            raise MermaidError(
                f"mmdc gagal (kode {completed.returncode}) untuk {target.name}"
                f"{_render_error_detail(completed)}"
            )
        if not target.is_file() or target.stat().st_size == 0:
            raise MermaidError(f"mmdc tidak menghasilkan PNG untuk {target.name}.")
    except BaseException:
        target.unlink(missing_ok=True)
        raise

    return target


def render_blocks(
    markdown: str,
    base_dir: str | Path,
    *,
    mmdc: str | Path | None = None,
    options: RenderOptions | Mapping[str, object] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    path: str | Path | None = None,
) -> str:
    """Render semua blok Mermaid dan kembalikan Markdown hasil penggantian.

    PNG ditulis ke ``<base_dir>/gambar/mermaid-<hash>.png`` dan setiap blok
    diganti dengan ``![caption](gambar/mermaid-<hash>.png)``. Diagram yang
    PNG-nya sudah ada dipakai ulang tanpa memanggil ``mmdc``.

    ``MermaidError`` dilempar untuk input tidak valid atau render gagal.
    ``ToolMissingError`` dilempar bila masih ada diagram yang perlu dirender
    tetapi ``mmdc`` tidak ditemukan.
    """

    blocks = extract_blocks(markdown, path=path)
    if not blocks:
        return markdown

    base_path = Path(base_dir)
    if base_path.exists() and not base_path.is_dir():
        raise MermaidError(f"base_dir bukan direktori: {base_path}")

    plans = _plan_blocks(blocks, base_path, options)

    pending: dict[str, _BlockPlan] = {}
    for plan in plans:
        if plan.image_path.is_file():
            continue
        pending.setdefault(plan.digest, plan)

    if pending:
        executable = find_mmdc(mmdc)
        if executable is None:
            raise ToolMissingError("mmdc", _mmdc_missing_message(mmdc))
        for plan in pending.values():
            _render_mermaid(
                plan.block.code,
                plan.image_path,
                executable,
                options,
                timeout=timeout,
            )

    return _rewrite_markdown(markdown, plans)


class MermaidStage(BaseStage):
    """Materialisasi blok Mermaid sebelum ``front_matter``/Pandoc."""

    name = StageName.MERMAID
    order = 20
    requires = (StageName.VALIDATE,)
    mutates = frozenset({"workspace"})
    idempotent = True

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        document = getattr(ctx, "document", None)
        body = getattr(document, "body", "") or ""
        document_path = getattr(document, "path", None)
        blocks = extract_blocks(body, path=document_path)
        if not blocks:
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                metrics={"blocks": 0},
            )

        workspace = getattr(ctx, "workspace", None)
        if workspace is None or not callable(getattr(workspace, "ensure", None)):
            raise MermaidError("stage mermaid membutuhkan workspace untuk menyimpan gambar.")
        workspace.ensure()

        try:
            markdown = render_blocks(
                body,
                Path(workspace.root),
                path=document_path,
            )
        except DocgenError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise StageError(
                self.name.value,
                f"stage mermaid gagal: {exc}",
                cause=exc,
                path=document_path,
                code="MERMAID-STAGE",
            ) from exc

        output = Path(workspace.path("mermaid.md"))
        previous = output.read_text(encoding="utf-8") if output.is_file() else None
        changed = previous != markdown
        if changed:
            output.write_text(markdown, encoding="utf-8", newline="\n")

        artifacts = getattr(ctx, "artifacts", None)
        if artifacts is not None and "mermaid.markdown" not in artifacts.keys():  # noqa: SIM118 - Artifacts bukan Mapping
            artifacts.put("mermaid.markdown", output)

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "blocks": len(blocks),
                "markdown_bytes": len(markdown.encode("utf-8")),
            },
            artifacts=(output,),
        )


__all__ = [
    "MermaidBlock",
    "MermaidError",
    "MermaidStage",
    "RenderOptions",
    "extract_blocks",
    "find_mmdc",
    "render_blocks",
    "render_hash",
]
