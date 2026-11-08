#!/usr/bin/env python3
"""Validasi caption wajib pada sumber Markdown.

Aturan yang ditegakkan:

- setiap tabel pipa Pandoc wajib memiliki caption ``: Judul tabel`` di atas
  atau di bawah tabel;
- setiap gambar Markdown wajib memiliki alt text non-kosong
  (``![deskripsi](path)``), yang menjadi caption gambar saat build DOCX.

Pemeriksaan ini murni stdlib dan tidak mengubah berkas. Kode keluar ``0`` bila
semua tabel/gambar valid, ``1`` bila ada temuan (daftar dicetak ke stderr),
dan ``2`` untuk kesalahan pemakaian/berkas.

Jalankan:

    python tools/check_captions.py chapters/*.md
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

FENCE_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})")
CAPTION_LINE_RE = re.compile(r"^\s*:\s+\S")
IMAGE_START_RE = re.compile(r"(?<!\\)!\[(?P<alt>[^\]]*)\]")
DELIMITER_CELL_RE = re.compile(r"^:?-{3,}:?$")
INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)*?\1")
HTML_CODE_RE = re.compile(r"<code\b[^>]*>.*?</code>", re.IGNORECASE)


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
    """Ganti isi code span dengan spasi agar ``![...]`` di dalamnya diabaikan."""

    masked = INLINE_CODE_RE.sub(lambda match: " " * len(match.group(0)), line)
    return HTML_CODE_RE.sub(lambda match: " " * len(match.group(0)), masked)


def _masked_lines(text: str) -> list[str]:
    """Kembalikan baris dengan blok kode dan code span disamarkan."""

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
                and len(stripped) - len(stripped.lstrip(fence_character))
                >= fence_length
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
    if not cells:
        return False
    return all(
        DELIMITER_CELL_RE.fullmatch(cell.replace(" ", "")) is not None
        for cell in cells
    )


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


def check_markdown(path: Path, text: str | None = None) -> list[CaptionIssue]:
    """Periksa satu berkas Markdown dan kembalikan seluruh temuan caption."""

    if text is None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise OSError(f"tidak dapat membaca {path}: {exc}") from exc

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
                        path=path,
                        line=header_index + 1,
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
                        path=path,
                        line=index + 1,
                        kind="gambar",
                        message=(
                            "tanpa alt text; tulis ![deskripsi gambar](path) "
                            "agar caption gambar terisi."
                        ),
                    )
                )

    return issues


def expand_paths(paths: Iterable[Path]) -> list[Path]:
    """Terima berkas atau direktori; direktori diperiksa rekursif."""

    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(path.rglob("*.md")))
        else:
            expanded.append(path)
    return expanded


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


if __name__ == "__main__":
    raise SystemExit(main())
