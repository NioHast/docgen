"""Stage ``validate``: validasi caption Markdown sebelum build DOCX.

Aturan yang ditegakkan:

- setiap tabel pipa Pandoc wajib memiliki caption ``: Judul tabel`` di atas
  atau di bawah tabel;
- setiap gambar Markdown wajib memiliki alt text non-kosong
  (``![deskripsi](path)``), yang menjadi caption gambar saat build DOCX;
- contoh di dalam code fence, code span, dan ``<code>``/``<pre>`` HTML
  diabaikan.

Modul ini tidak membuka package DOCX dan tidak menulis berkas. Error
dilempar sebagai :class:`docgen.errors.ValidationError` dengan exit code 1.
"""

import argparse
import re
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..errors import DocgenError, StageError, ValidationError
from ..pipeline import BaseStage, StageName, StageResult

FENCE_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})")
CAPTION_LINE_RE = re.compile(r"^\s*:\s+\S")
IMAGE_START_RE = re.compile(r"(?<!\\)!\[(?P<alt>[^\]]*)\]")
DELIMITER_CELL_RE = re.compile(r"^:?-{3,}:?$")
INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)*?\1")
HTML_CODE_RE = re.compile(r"<code\b[^>]*>.*?</code>", re.IGNORECASE)
HTML_BLOCK_OPEN_RE = re.compile(r"<(pre|code)\b[^>]*>", re.IGNORECASE)


@dataclass(frozen=True)
class CaptionIssue:
    """Satu tabel/gambar yang tidak memenuhi aturan caption."""

    path: Path
    line: int
    kind: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.kind} {self.message}"


def _mask_inline_code(line: str) -> str:
    """Ganti isi code span dan ``<code>`` sebaris dengan spasi."""

    masked = INLINE_CODE_RE.sub(lambda match: " " * len(match.group(0)), line)
    return HTML_CODE_RE.sub(lambda match: " " * len(match.group(0)), masked)


def _mask_html_block(
    lines: list[str],
    index: int,
) -> int:
    """Samarkan blok HTML ``<pre>``/``<code>`` multi-baris.

    Mengembalikan indeks baris terakhir yang disamarkan.
    """

    opening = HTML_BLOCK_OPEN_RE.search(lines[index])
    if opening is None:
        return index

    tag = opening.group(1).lower()
    closing = f"</{tag}>"
    current = index
    lower = lines[current].lower()
    start = opening.end()
    end = lower.find(closing, start)
    if end != -1:
        prefix = lines[current][: opening.start()]
        suffix = lines[current][end + len(closing) :]
        lines[current] = prefix + " " * (end + len(closing) - opening.start()) + suffix
        return current

    lines[current] = lines[current][: opening.start()] + " " * (
        len(lines[current]) - opening.start()
    )
    current += 1
    while current < len(lines):
        lower = lines[current].lower()
        end = lower.find(closing)
        if end != -1:
            lines[current] = " " * (end + len(closing)) + lines[current][end + len(closing) :]
            return current
        lines[current] = ""
        current += 1
    return len(lines) - 1


def _masked_lines(text: str) -> list[str]:
    """Kembalikan baris dengan code fence, code span, dan HTML code disamarkan."""

    masked: list[str] = []
    fence_character = ""
    fence_length = 0
    in_fence = False

    for line in text.splitlines():
        if in_fence:
            stripped = line.lstrip()
            if (
                stripped
                and stripped[0] == fence_character
                and len(stripped) - len(stripped.lstrip(fence_character)) >= fence_length
                and not stripped.lstrip(fence_character).strip()
            ):
                in_fence = False
                fence_character = ""
                fence_length = 0
            masked.append("")
            continue

        match = FENCE_RE.match(line)
        if match is not None:
            fence = match.group("fence")
            in_fence = True
            fence_character = fence[0]
            fence_length = len(fence)
            masked.append("")
            continue

        masked.append(_mask_inline_code(line))

    index = 0
    while index < len(masked):
        index = _mask_html_block(masked, index) + 1
    return masked


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith("\\|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped)]


def _is_delimiter_row(line: str) -> bool:
    if "|" not in line:
        return False
    cells = _split_row(line)
    return all(DELIMITER_CELL_RE.fullmatch(cell.replace(" ", "")) is not None for cell in cells)


def _is_table_start(masked: Sequence[str], index: int) -> bool:
    if index < 1 or index >= len(masked):
        return False
    header = masked[index - 1]
    delimiter = masked[index]
    if "|" not in header or "|" not in delimiter:
        return False
    if not header.strip() or _is_delimiter_row(header):
        return False
    return _is_delimiter_row(delimiter)


def _skip_blank_lines(masked: Sequence[str], index: int, step: int) -> int:
    while 0 <= index < len(masked) and not masked[index].strip():
        index += step
    return index


def _has_caption_before(masked: Sequence[str], header_index: int) -> bool:
    index = _skip_blank_lines(masked, header_index - 1, -1)
    if index < 0:
        return False
    return CAPTION_LINE_RE.match(masked[index]) is not None


def _table_end(masked: Sequence[str], delimiter_index: int) -> int | None:
    """Indeks baris setelah tabel, atau ``None`` bila tabel tidak berakhir."""

    index = delimiter_index + 1
    saw_row = False
    while index < len(masked):
        line = masked[index]
        if not line.strip():
            break
        if "|" not in line:
            break
        if CAPTION_LINE_RE.match(line):
            break
        saw_row = True
        index += 1
    if not saw_row:
        return None
    return index


def _has_caption_after(masked: Sequence[str], delimiter_index: int) -> bool:
    end = _table_end(masked, delimiter_index)
    if end is None:
        return False
    index = _skip_blank_lines(masked, end, 1)
    if index >= len(masked):
        return False
    return CAPTION_LINE_RE.match(masked[index]) is not None


def _looks_like_image(line: str, match: re.Match[str]) -> bool:
    """Pastikan ``![...]`` diikuti tujuan gambar, bukan teks biasa."""

    position = match.end()
    if position >= len(line):
        return False
    return line[position] in "(["


def check_text(
    text: str,
    *,
    path: Path | str = Path("<markdown>"),
    line_offset: int = 0,
) -> list[CaptionIssue]:
    """Periksa isi Markdown dan kembalikan seluruh temuan caption."""

    resolved = Path(path)
    masked = _masked_lines(text)
    issues: list[CaptionIssue] = []

    for index, line in enumerate(masked):
        if _is_table_start(masked, index):
            header_index = index - 1
            if not _has_caption_before(masked, header_index) and not _has_caption_after(
                masked, index
            ):
                issues.append(
                    CaptionIssue(
                        path=resolved,
                        line=header_index + 1 + line_offset,
                        kind="tabel",
                        message=(
                            "tanpa caption; tambahkan baris ': Judul tabel' "
                            "sebelum atau sesudah tabel."
                        ),
                    )
                )

        for match in IMAGE_START_RE.finditer(line):
            if not _looks_like_image(line, match):
                continue
            if not match.group("alt").strip():
                issues.append(
                    CaptionIssue(
                        path=resolved,
                        line=index + 1 + line_offset,
                        kind="gambar",
                        message=(
                            "tanpa alt text; tulis ![deskripsi gambar](path) "
                            "agar caption gambar terisi."
                        ),
                    )
                )

    return issues


def check_markdown(path: Path, text: str | None = None) -> list[CaptionIssue]:
    """Periksa satu berkas Markdown dan kembalikan seluruh temuan caption."""

    resolved = Path(path)
    if text is None:
        try:
            text = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise OSError(f"tidak dapat membaca {resolved}: {exc}") from exc
    return check_text(text, path=resolved)


def validate_markdown(path: Path, text: str | None = None) -> None:
    """Periksa satu berkas dan lempar ``ValidationError`` bila ada temuan."""

    resolved = Path(path)
    issues = check_markdown(resolved, text)
    if not issues:
        return
    details = "\n".join(f"- {issue.render()}" for issue in issues)
    raise ValidationError(
        "caption Markdown tidak valid:\n"
        f"{details}\n"
        "Tambahkan ': Judul tabel' pada tabel dan alt text pada gambar.",
        code="VAL-CAPTION",
        path=resolved,
        key="caption",
    )


def expand_paths(paths: Iterable[Path]) -> list[Path]:
    """Terima berkas atau direktori; direktori diperiksa rekursif."""

    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(path.rglob("*.md")))
        else:
            expanded.append(path)
    return expanded


def _body_line_offset(path: Path) -> int:
    """Jumlah baris front matter agar nomor baris body sesuai berkas asli."""

    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return 0
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return 0
    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            return index + 1
    return 0


def validate_body(document: object) -> None:
    """Validasi caption pada body ``Document``; lempar ``ValidationError``.

    Dipakai bersama oleh stage ``validate`` dan ``docgen check`` agar aturan
    caption tidak berbeda antara perintah check dan build.
    """

    path = Path(getattr(document, "path", Path("<document>")))
    body = getattr(document, "body", "") or ""
    issues = check_text(body, path=path, line_offset=_body_line_offset(path))
    if not issues:
        return
    details = "\n".join(f"- {issue.render()}" for issue in issues)
    raise ValidationError(
        "caption Markdown tidak valid:\n"
        f"{details}\n"
        "Tambahkan ': Judul tabel' pada tabel dan alt text pada gambar.",
        code="VAL-CAPTION",
        path=path,
        key="caption",
    )


class ValidateStage(BaseStage):
    """Validasi caption Markdown tanpa membuka package DOCX."""

    name = StageName.VALIDATE
    order = 10
    requires = ()
    mutates = frozenset()
    idempotent = True

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        document = getattr(ctx, "document", None)
        path = Path(getattr(document, "path", Path("<document>")))

        try:
            validate_body(document)
        except DocgenError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise StageError(
                self.name.value,
                f"validasi caption gagal: {exc}",
                cause=exc,
                path=path,
                code="VAL-STAGE",
            ) from exc

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=False,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={"issues": 0},
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validasi caption tabel (: Judul tabel) dan alt text gambar pada "
            "Markdown sebelum build DOCX."
        )
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="berkas .md atau direktori yang berisi .md",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    files = expand_paths(args.paths)
    if not files:
        print("ERROR: tidak ada berkas .md yang diperiksa.", file=sys.stderr)
        return 2

    issues: list[CaptionIssue] = []
    failures = 0
    for path in files:
        try:
            issues.extend(check_markdown(path))
        except OSError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            failures += 1

    for issue in issues:
        print(f"[ERROR] {issue.render()}", file=sys.stderr)

    if issues or failures:
        total = len(issues) + failures
        print("", file=sys.stderr)
        print(
            f"ERROR: {total} masalah caption pada {len(files)} berkas Markdown. "
            "Build DOCX dihentikan.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[OK] {len(files)} berkas Markdown: semua tabel memiliki caption dan "
        "semua gambar memiliki alt text."
    )
    return 0


__all__ = [
    "CaptionIssue",
    "ValidateStage",
    "check_markdown",
    "check_text",
    "expand_paths",
    "main",
    "validate_markdown",
]
