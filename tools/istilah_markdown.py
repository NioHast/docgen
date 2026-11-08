"""Preprocessing istilah glosarium untuk Markdown.

Build PDF memakai Pandoc + Typst dan tidak melewati ``tools/istilah.py``
(pemroses DOCX). Modul ini menyalin ``*.md`` ke direktori keluaran sambil
membungkus istilah glosarium ``italic=yes`` dengan ``*...*`` agar PDF memakai
penulisan istilah yang sama dengan DOCX.

Aturan utama:

- frasa terpanjang menang;
- pencocokan case-insensitive, teks asli dipertahankan;
- isi code fence, inline code, tautan, dan teks yang sudah italic tidak diubah;
- YAML frontmatter tidak diubah;
- hasilnya idempoten.

Pemakaian::

    python tools/istilah_markdown.py \
        --src chapters --glossary writing/istilah.tsv --out /tmp/chapters-pre
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

HEADER = ("term", "italic", "gloss_first", "status")
TRUE_FALSE = {"yes", "no"}
STATUS_VALUES = {"confirmed", "review"}


class IstilahMarkdownError(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna CLI."""


class GlossaryError(IstilahMarkdownError):
    """Isi istilah.tsv tidak valid."""


@dataclass
class GlossaryEntry:
    term: str
    italic: bool
    gloss_first: bool
    status: str
    line_no: int
    pattern: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Batas \w sama dengan tools/istilah.py agar "data" tidak cocok di
        # dalam "datang" atau "metadata". Spasi dibiarkan literal.
        body = re.escape(self.term)
        self.pattern = re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


@dataclass
class Glossary:
    entries: list[GlossaryEntry]


@dataclass(frozen=True)
class TermMatch:
    entry: GlossaryEntry
    start: int
    end: int


def load_glossary(path: Path) -> Glossary:
    """Baca dan validasi glosarium TSV dengan format yang sama seperti DOCX."""

    if not path.exists():
        raise GlossaryError(f"Glosarium tidak ditemukan: {path}")

    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GlossaryError(f"Glosarium bukan UTF-8 yang valid: {path}") from exc

    entries: list[GlossaryEntry] = []
    seen: dict[str, int] = {}
    header_seen = False
    errors: list[str] = []

    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        if not header_seen:
            columns = [column.strip() for column in line.split("\t")]
            if tuple(columns) != HEADER:
                raise GlossaryError(
                    f"Baris {line_no}: header harus "
                    "'term<TAB>italic<TAB>gloss_first<TAB>status'."
                )
            header_seen = True
            continue

        columns = line.split("\t")
        if len(columns) != len(HEADER):
            errors.append(
                f"Baris {line_no}: kolom harus {len(HEADER)}, "
                f"bukan {len(columns)}."
            )
            continue

        term, italic, gloss_first, status = (column.strip() for column in columns)
        if not term:
            errors.append(f"Baris {line_no}: term kosong.")
            continue
        if italic not in TRUE_FALSE:
            errors.append(
                f"Baris {line_no}: italic harus 'yes' atau 'no', "
                f"bukan {italic!r}."
            )
            continue
        if gloss_first not in TRUE_FALSE:
            errors.append(
                f"Baris {line_no}: gloss_first harus 'yes' atau 'no', "
                f"bukan {gloss_first!r}."
            )
            continue
        if status not in STATUS_VALUES:
            errors.append(
                f"Baris {line_no}: status harus 'confirmed' atau 'review', "
                f"bukan {status!r}."
            )
            continue

        key = term.casefold()
        if key in seen:
            errors.append(
                f"Baris {line_no}: term duplikat {term!r} "
                f"(sudah ada di baris {seen[key]})."
            )
            continue

        seen[key] = line_no
        entries.append(
            GlossaryEntry(
                term=term,
                italic=italic == "yes",
                gloss_first=gloss_first == "yes",
                status=status,
                line_no=line_no,
            )
        )

    if not header_seen:
        errors.append("Header glosarium tidak ditemukan.")
    if errors:
        raise GlossaryError("Glosarium tidak valid:\n" + "\n".join(errors))
    return Glossary(entries=entries)


def find_term_matches(text: str, glossary: Glossary) -> list[TermMatch]:
    """Pilih match terpanjang yang tidak bertumpang tindih.

    Istilah ``italic=no`` tetap ikut dipertimbangkan sebagai penghalang,
    sehingga ``big data`` (yes) mengalahkan ``data`` (no) di dalamnya. Hanya
    match dengan ``italic=yes`` yang nantinya dibungkus.
    """

    candidates: list[TermMatch] = []
    for entry in glossary.entries:
        for match in entry.pattern.finditer(text):
            candidates.append(TermMatch(entry, match.start(), match.end()))

    candidates.sort(
        key=lambda match: (
            -(match.end - match.start),
            match.start,
            match.entry.term.casefold(),
        )
    )

    occupied = bytearray(len(text))
    selected: list[TermMatch] = []
    for match in candidates:
        if any(occupied[match.start : match.end]):
            continue
        occupied[match.start : match.end] = b"\x01" * (match.end - match.start)
        selected.append(match)

    selected.sort(key=lambda match: match.start)
    return selected


# ---------------------------------------------------------------------------
# Penanda area yang tidak boleh diubah


def _mark(protected: bytearray, start: int, end: int) -> None:
    if end > start:
        protected[start:end] = b"\x01" * (end - start)


def _line_ranges(text: str) -> Iterator[tuple[int, int]]:
    """Rentang setiap baris termasuk newline-nya."""

    start = 0
    for line in text.splitlines(keepends=True):
        end = start + len(line)
        yield start, end
        start = end
    if start < len(text):
        yield start, len(text)


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _mark_frontmatter(text: str, protected: bytearray) -> None:
    """Lindungi YAML frontmatter di awal berkas."""

    lines = list(_line_ranges(text))
    if not lines:
        return

    first_start, first_end = lines[0]
    if text[first_start:first_end].strip() != "---":
        return

    for start, end in lines[1:]:
        if text[start:end].strip() in {"---", "..."}:
            _mark(protected, 0, end)
            return

    # Frontmatter tidak tertutup: jangan sentuh apa pun agar YAML aman.
    _mark(protected, 0, len(text))


_FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_BARE_URL_RE = re.compile(
    r"(?:https?://|ftp://|www\.)[^\s<>\"']+"
    r"|(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
)


def _fence_info(line: str) -> tuple[str, int, str] | None:
    match = _FENCE_RE.match(line)
    if not match:
        return None
    fence = match.group(2)
    return fence[0], len(fence), match.group(3)


def _mark_fenced_code(text: str, protected: bytearray) -> None:
    fence_char = ""
    fence_len = 0

    for start, end in _line_ranges(text):
        if protected[start]:
            continue
        line = text[start:end].rstrip("\r\n")
        info = _fence_info(line)

        if not fence_char:
            if info is not None:
                fence_char, fence_len, _ = info
                _mark(protected, start, end)
            continue

        _mark(protected, start, end)
        if info is None:
            continue
        char, length, rest = info
        if char == fence_char and length >= fence_len and not rest.strip():
            fence_char = ""
            fence_len = 0


def _mark_inline_code(text: str, protected: bytearray) -> None:
    for line_start, line_end in _line_ranges(text):
        cursor = line_start
        while cursor < line_end:
            if protected[cursor] or text[cursor] != "`":
                cursor += 1
                continue

            opening = cursor
            while cursor < line_end and text[cursor] == "`":
                cursor += 1
            run_length = cursor - opening

            closing = -1
            probe = cursor
            while probe < line_end:
                if text[probe] != "`":
                    probe += 1
                    continue
                run_start = probe
                while probe < line_end and text[probe] == "`":
                    probe += 1
                if probe - run_start == run_length:
                    closing = probe
                    break

            if closing != -1:
                _mark(protected, opening, closing)
                cursor = closing


def _find_closing(
    text: str, opening: int, open_char: str, close_char: str, limit: int
) -> int:
    depth = 1
    cursor = opening + 1
    while cursor < limit:
        char = text[cursor]
        if _is_escaped(text, cursor):
            cursor += 1
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return cursor
        cursor += 1
    return -1


def _mark_links(text: str, protected: bytearray) -> None:
    """Lindungi tautan inline, gambar, autolink, sitasi, dan footnote."""
    for line_start, line_end in _line_ranges(text):
        cursor = line_start
        while cursor < line_end:
            if protected[cursor]:
                cursor += 1
                continue

            char = text[cursor]

            if char == "<":
                closing = text.find(">", cursor + 1, line_end)
                if closing != -1:
                    content = text[cursor + 1 : closing]
                    if "://" in content or "@" in content or content.startswith(
                        "mailto:"
                    ):
                        _mark(protected, cursor, closing + 1)
                        cursor = closing + 1
                        continue
                cursor += 1
                continue

            if char != "[":
                cursor += 1
                continue

            closing_bracket = _find_closing(text, cursor, "[", "]", line_end)
            if closing_bracket == -1:
                cursor += 1
                continue

            mark_start = cursor
            if (
                cursor > line_start
                and text[cursor - 1] == "!"
                and not protected[cursor - 1]
                and not _is_escaped(text, cursor - 1)
            ):
                mark_start = cursor - 1

            after = closing_bracket + 1
            if after < line_end and text[after] == "(":
                closing = _find_closing(text, after, "(", ")", line_end)
                if closing != -1:
                    _mark(protected, mark_start, closing + 1)
                    cursor = closing + 1
                    continue
            elif after < line_end and text[after] == "[":
                closing = _find_closing(text, after, "[", "]", line_end)
                if closing != -1:
                    _mark(protected, mark_start, closing + 1)
                    cursor = closing + 1
                    continue
            else:
                content = text[cursor + 1 : closing_bracket]
                if content.lstrip().startswith(("@", "-@", "^")):
                    _mark(protected, cursor, closing_bracket + 1)
                    cursor = closing_bracket + 1
                    continue

            cursor = closing_bracket + 1


def _mark_bare_urls(text: str, protected: bytearray) -> None:
    """Lindungi URL/email telanjang agar istilah di dalamnya tidak diubah."""

    for start, end in list(_iter_unprotected(text, protected)):
        segment = text[start:end]
        for match in _BARE_URL_RE.finditer(segment):
            _mark(protected, start + match.start(), start + match.end())


def _mark_emphasis(text: str, protected: bytearray) -> None:
    """Lindungi teks yang sudah berada di dalam *...* atau _..._.

    Run ``*``/``_`` dipasangkan dengan stack. Hanya pasangan ganjil (italic)
    yang ditandai; bold (``**...**``) tetap boleh diproses agar istilah di
    dalamnya bisa menjadi bold-italic. Pasangan tetap dilacak melewati tautan
    dan inline code yang sudah dilindungi.
    """

    for line_start, line_end in _line_ranges(text):
        for marker in ("*", "_"):
            stack: list[tuple[int, int]] = []
            cursor = line_start
            while cursor < line_end:
                if protected[cursor] or text[cursor] != marker:
                    cursor += 1
                    continue

                run_start = cursor
                while cursor < line_end and text[cursor] == marker:
                    cursor += 1
                run_length = cursor - run_start

                if _is_escaped(text, run_start):
                    continue

                previous = text[run_start - 1] if run_start > line_start else ""
                following = text[cursor] if cursor < line_end else ""

                if (
                    marker == "_"
                    and previous.isalnum()
                    and following.isalnum()
                ):
                    # snake_case bukan penanda emphasis.
                    continue

                can_open = bool(following) and not following.isspace()
                can_close = bool(previous) and not previous.isspace()

                if can_close and stack and stack[-1][1] == run_length:
                    opening, _ = stack.pop()
                    if run_length % 2 == 1:
                        _mark(protected, opening, cursor)
                elif can_open:
                    stack.append((run_start, run_length))


def _iter_unprotected(
    text: str, protected: bytearray
) -> Iterator[tuple[int, int]]:
    cursor = 0
    length = len(text)
    while cursor < length:
        if protected[cursor]:
            cursor += 1
            continue
        start = cursor
        while cursor < length and not protected[cursor]:
            cursor += 1
        yield start, cursor


def _wrap_segment(
    segment: str, glossary: Glossary, before: str = "", after: str = ""
) -> str:
    matches = [
        match for match in find_term_matches(segment, glossary) if match.entry.italic
    ]
    # Jangan menempelkan *baru* tepat di samping penanda * atau _ yang sudah
    # ada: deretan ** yang dihasilkan bisa ambigu dan tidak idempoten.
    matches = [
        match
        for match in matches
        if not (match.start == 0 and before in ("*", "_"))
        and not (match.end == len(segment) and after in ("*", "_"))
        and not (match.start > 0 and segment[match.start - 1] in ("*", "_"))
        and not (match.end < len(segment) and segment[match.end] in ("*", "_"))
    ]
    if not matches:
        return segment

    pieces: list[str] = []
    cursor = 0
    for match in matches:
        pieces.append(segment[cursor : match.start])
        pieces.append("*")
        pieces.append(segment[match.start : match.end])
        pieces.append("*")
        cursor = match.end
    pieces.append(segment[cursor:])
    return "".join(pieces)


def wrap_glossary_terms(text: str, glossary: Glossary) -> str:
    """Bungkus istilah italic=yes pada teks Markdown."""

    protected = bytearray(len(text))
    _mark_frontmatter(text, protected)
    _mark_fenced_code(text, protected)
    _mark_inline_code(text, protected)
    _mark_links(text, protected)
    _mark_bare_urls(text, protected)
    _mark_emphasis(text, protected)

    pieces: list[str] = []
    cursor = 0
    for start, end in _iter_unprotected(text, protected):
        pieces.append(text[cursor:start])
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        pieces.append(_wrap_segment(text[start:end], glossary, before, after))
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


# ---------------------------------------------------------------------------
# CLI


def _read_markdown(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        return raw.decode("utf-8-sig"), has_bom
    except UnicodeDecodeError as exc:
        raise IstilahMarkdownError(
            f"Markdown bukan UTF-8 yang valid: {path}"
        ) from exc


def _write_markdown(path: Path, text: str, bom: bool = False) -> None:
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def preprocess_directory(src: Path, glossary_path: Path, out: Path) -> int:
    """Salin dan proses semua ``*.md`` dari ``src`` ke ``out``."""

    src_resolved = src.resolve()
    out_resolved = out.resolve()
    if src_resolved == out_resolved:
        raise IstilahMarkdownError(
            "Direktori --out tidak boleh sama dengan --src agar sumber tidak tertimpa."
        )
    if not src_resolved.is_dir():
        raise IstilahMarkdownError(f"Direktori sumber tidak ditemukan: {src}")
    if out_resolved.exists() and not out_resolved.is_dir():
        raise IstilahMarkdownError(f"Path --out bukan direktori: {out}")

    files = sorted(
        path for path in src_resolved.glob("*.md") if path.is_file()
    )
    if not files:
        raise IstilahMarkdownError(
            f"Tidak ada berkas .md di direktori sumber: {src}"
        )

    glossary = load_glossary(glossary_path)
    out_resolved.mkdir(parents=True, exist_ok=True)

    for path in files:
        text, bom = _read_markdown(path)
        output = wrap_glossary_terms(text, glossary)
        _write_markdown(out_resolved / path.name, output, bom)

    return len(files)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Salin Markdown ke direktori keluaran dan bungkus istilah "
            "glosarium italic=yes dengan *...*."
        )
    )
    parser.add_argument("--src", required=True, type=Path, help="Direktori sumber *.md")
    parser.add_argument(
        "--glossary", required=True, type=Path, help="Berkas istilah.tsv"
    )
    parser.add_argument("--out", required=True, type=Path, help="Direktori keluaran")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(
        None if argv is None else [str(item) for item in argv]
    )

    try:
        count = preprocess_directory(args.src, args.glossary, args.out)
    except (IstilahMarkdownError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Preprocessing istilah: {count} berkas -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
