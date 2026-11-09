"""Penomoran heading Markdown sebelum Pandoc.

Modul ini memindahkan perilaku ``Header`` dan ``balance_title`` dari
``docx.lua`` ke Python tanpa bergantung pada Pandoc. Semua fungsi bersifat
murni: menerima teks Markdown dan mengembalikan teks Markdown, atau menerima
level/judul dan mengembalikan nomor. Tidak ada akses ZIP, XML, atau package.

Nomor yang ditulis ke Markdown memakai raw inline OpenXML untuk line break dan
tab, sehingga Pandoc menghasilkan ``w:br``/``w:tab`` yang sama seperti filter
Lua lama:

- H1 ``BAB_ROMAN``: ``BAB I`` + line break + judul kapital.
- H1 ``ARABIC_DOTTED``: ``1.`` + spasi + judul kapital.
- H2: ``1.1.`` + tab + judul.
- H3: ``1.1.1.`` + tab + judul.
- H4-H6 dan heading berkelas ``unnumbered`` tidak dinomori dan tidak
  mengubah counter.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from . import DocxError

__all__ = [
    "Heading",
    "HeadingError",
    "HeadingNumberer",
    "MarkdownHeading",
    "NumberingSpec",
    "balance_title",
    "format_chapter_number",
    "heading_level",
    "is_unnumbered",
    "number_markdown",
    "number_markdown_headings",
    "parse_heading",
    "render_heading",
    "roman",
    "uppercase_markdown",
]

NumberingBody = Literal["BAB_ROMAN", "ARABIC_DOTTED"]
_SUPPORTED_BODY = frozenset({"BAB_ROMAN", "ARABIC_DOTTED"})

_HEADING_RE = re.compile(
    r"^(?P<indent> {0,3})(?P<hashes>#{1,6})(?P<space>[ \t]+)(?P<body>.*)$"
)
_CLOSING_HASHES_RE = re.compile(r"[ \t]+#+[ \t]*$")
_ATTRIBUTE_RE = re.compile(r"(?P<space>[ \t]+)(?P<attributes>\{[^{}]*\})[ \t]*$")
_FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
_LINK_RE = re.compile(r"(?P<open>!?\[)(?P<label>[^\]]*)(?P<close>\]\([^)]*\))")
_CODE_SPAN_RE = re.compile(r"(?P<ticks>`+)(?:(?!(?P=ticks)).)*?(?P=ticks)")
_HTML_TAG_RE = re.compile(r"<[^>]*>")

# Raw inline yang setara dengan pandoc.LineBreak() dan <w:tab/> pada docx.lua.
LINE_BREAK = "`<w:br/>`{=openxml}"
TAB = "`<w:tab/>`{=openxml}"

_ROMAN_MAP = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


class HeadingError(DocxError):
    """Level, atribut, atau format nomor heading tidak valid."""

    default_code = "HEADING"


@dataclass(frozen=True, slots=True)
class NumberingSpec:
    """Spesifikasi penomoran dari ``structure.numbering``."""

    body: NumberingBody = "BAB_ROMAN"
    sub_dot: bool = True
    subsub_dot: bool = True

    def __post_init__(self) -> None:
        if self.body not in _SUPPORTED_BODY:
            raise HeadingError(
                f"format penomoran body tidak dikenal: {self.body!r}",
                code="HEADING-SPEC",
                key="numbering.body",
            )


@dataclass(frozen=True, slots=True)
class Heading:
    """Hasil penomoran satu heading."""

    level: int
    text: str
    number: str | None
    unnumbered: bool

    @property
    def numbered(self) -> bool:
        return self.number is not None


@dataclass(frozen=True, slots=True)
class MarkdownHeading:
    """Hasil parsing satu baris heading ATX."""

    level: int
    text: str
    attributes: str
    indent: str
    unnumbered: bool
    raw: str


def roman(value: int) -> str:
    """Ubah bilangan bulat positif menjadi angka Romawi kapital."""

    if value <= 0:
        return ""
    remaining = value
    out: list[str] = []
    for number, symbol in _ROMAN_MAP:
        while remaining >= number:
            out.append(symbol)
            remaining -= number
    return "".join(out)


def format_chapter_number(value: int, spec: NumberingSpec) -> str:
    """Nomor H1 lengkap: ``BAB I`` atau ``1.``."""

    if value <= 0:
        raise HeadingError(
            f"nomor bab harus positif, bukan {value}",
            code="HEADING-NUMBER",
        )
    if spec.body == "ARABIC_DOTTED":
        return f"{value}."
    return f"BAB {roman(value)}"


class HeadingNumberer:
    """State machine penomoran H1/H2/H3 yang setara dengan ``docx.lua``.

    Heading H2 sebelum H1 memakai bab implisit 1 sehingga tidak pernah
    menghasilkan ``0.1.``. Heading H1 unnumbered tidak mereset counter, sesuai
    perilaku lama: H2 setelahnya melanjutkan nomor subbab bab terakhir.
    """

    def __init__(self, spec: NumberingSpec | None = None) -> None:
        self.spec = spec or NumberingSpec()
        self.chapter = 0
        self.sub = 0
        self.subsub = 0

    def reset(self) -> None:
        self.chapter = 0
        self.sub = 0
        self.subsub = 0

    def number(
        self,
        level: int,
        text: str,
        *,
        unnumbered: bool = False,
    ) -> Heading:
        """Kembalikan heading bernomor tanpa mengubah teks aslinya."""

        if level not in {1, 2, 3}:
            return Heading(level=level, text=text, number=None, unnumbered=unnumbered)
        if unnumbered:
            # Jangan reset counter: heading unnumbered bukan batas bab.
            return Heading(level=level, text=text, number=None, unnumbered=True)

        if level == 1:
            self.chapter += 1
            self.sub = 0
            self.subsub = 0
            number = format_chapter_number(self.chapter, self.spec)
        elif level == 2:
            chapter = self.chapter or 1
            self.sub += 1
            self.subsub = 0
            suffix = "." if self.spec.sub_dot else ""
            number = f"{chapter}.{self.sub}{suffix}"
        else:
            chapter = self.chapter or 1
            if self.sub == 0:
                # H3 sebelum H2: pakai subbab implisit 1, bukan 0.
                self.sub = 1
                self.subsub = 0
            self.subsub += 1
            suffix = "." if self.spec.subsub_dot else ""
            number = f"{chapter}.{self.sub}.{self.subsub}{suffix}"

        return Heading(level=level, text=text, number=number, unnumbered=False)


def _protect_inline(text: str) -> tuple[str, list[str]]:
    """Ganti code span dan tujuan link dengan placeholder agar aman di-upper."""

    protected: list[str] = []

    def store(value: str) -> str:
        protected.append(value)
        return f"\x00{len(protected) - 1}\x00"

    text = _CODE_SPAN_RE.sub(lambda match: store(match.group(0)), text)
    text = _HTML_TAG_RE.sub(lambda match: store(match.group(0)), text)
    text = _LINK_RE.sub(
        lambda match: match.group("open")
        + match.group("label").upper()
        + store(match.group("close")),
        text,
    )
    return text, protected


def uppercase_markdown(text: str) -> str:
    """Uppercase teks Markdown tanpa mengubah code span/tujuan link.

    Judul H1 lama di-uppercase setelah inline formatting dipertahankan.
    Code span, tag HTML, dan URL di dalam link tidak boleh ikut berubah.
    """

    protected_text, protected = _protect_inline(text)
    upper = protected_text.upper()
    for index, value in enumerate(protected):
        upper = upper.replace(f"\x00{index}\x00", value)
    return upper


def _has_unnumbered_class(attributes: str) -> bool:
    inner = attributes.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]
    tokens = inner.split()
    return "-" in tokens or ".unnumbered" in tokens or "unnumbered" in tokens


def parse_heading(line: str) -> MarkdownHeading | None:
    """Parse satu baris heading ATX; ``None`` jika bukan heading."""

    content = line.rstrip("\r\n")
    match = _HEADING_RE.match(content)
    if match is None:
        return None

    body = match.group("body")
    closing = _CLOSING_HASHES_RE.search(body)
    if closing is not None:
        body = body[: closing.start()]

    attributes = ""
    attribute_match = _ATTRIBUTE_RE.search(body)
    if attribute_match is not None:
        attributes = attribute_match.group("attributes")
        body = body[: attribute_match.start()]

    text = body.strip()
    return MarkdownHeading(
        level=len(match.group("hashes")),
        text=text,
        attributes=attributes,
        indent=match.group("indent"),
        unnumbered=_has_unnumbered_class(attributes),
        raw=line,
    )


def heading_level(line: str) -> int | None:
    """Level heading ATX pada baris, atau ``None``."""

    parsed = parse_heading(line)
    return parsed.level if parsed is not None else None


def is_unnumbered(line: str) -> bool:
    """True jika heading memakai ``{-}``/``.unnumbered``."""

    parsed = parse_heading(line)
    return bool(parsed is not None and parsed.unnumbered)


def render_heading(heading: Heading, spec: NumberingSpec | None = None) -> str:
    """Render isi heading (tanpa ``#`` dan atribut) dari hasil nomor."""

    spec = spec or NumberingSpec()
    if heading.number is None or not heading.text:
        return heading.text
    if heading.level == 1:
        if spec.body == "BAB_ROMAN":
            return (
                f"{heading.number}{LINE_BREAK}"
                f"{uppercase_markdown(heading.text)}"
            )
        return f"{heading.number} {uppercase_markdown(heading.text)}"
    if heading.level == 2:
        return f"{heading.number}{TAB}{heading.text}"
    if heading.level == 3:
        return f"{heading.number}{TAB}{heading.text}"
    return heading.text


def _strip_line_ending(line: str) -> tuple[str, str]:
    content = line.rstrip("\r\n")
    return content, line[len(content) :]


def _fence_opening(line: str) -> tuple[str, int] | None:
    match = _FENCE_RE.match(line)
    if match is None:
        return None
    fence = match.group("fence")
    return fence[0], len(fence)


def _fence_closing(line: str, character: str, length: int) -> bool:
    pattern = re.compile(
        rf"^ {{0,3}}{re.escape(character)}{{{length},}}[ \t]*$"
    )
    return pattern.match(line) is not None


def number_markdown_headings(
    markdown: str,
    spec: NumberingSpec | None = None,
) -> str:
    """Nomori seluruh heading ATX di ``markdown`` dan kembalikan teks baru.

    Fenced code block dilewati agar contoh Markdown di dalam dokumen tidak
    ikut berubah. Atribut heading (``{#id}``, ``{-}``) dipertahankan.
    """

    spec = spec or NumberingSpec()
    numberer = HeadingNumberer(spec)
    output: list[str] = []
    fence_character: str | None = None
    fence_length = 0

    for line in markdown.splitlines(keepends=True):
        content, ending = _strip_line_ending(line)

        if fence_character is not None:
            output.append(line)
            if _fence_closing(content, fence_character, fence_length):
                fence_character = None
                fence_length = 0
            continue

        opening = _fence_opening(content)
        if opening is not None:
            fence_character, fence_length = opening
            output.append(line)
            continue

        parsed = parse_heading(content)
        if parsed is None or not parsed.text:
            output.append(line)
            continue

        heading = numberer.number(
            parsed.level,
            parsed.text,
            unnumbered=parsed.unnumbered,
        )
        rendered = render_heading(heading, spec)
        if rendered == parsed.text:
            output.append(line)
            continue
        attributes = f" {parsed.attributes}" if parsed.attributes else ""
        output.append(
            f"{parsed.indent}{'#' * parsed.level} {rendered}{attributes}{ending}"
        )

    return "".join(output)


# Alias yang lebih pendek untuk pemakaian stage.
number_markdown = number_markdown_headings


def _count_words(text: str) -> int:
    return len(text.split())


def _max_line_length(lines: tuple[str, ...]) -> int:
    return max((len(line) for line in lines), default=0)


def _has_orphan(lines: tuple[str, ...]) -> bool:
    return any(_count_words(line) <= 1 for line in lines)


def _best_partition(words: list[str], line_count: int) -> tuple[str, ...] | None:
    """Partisi kata menjadi ``line_count`` baris dengan biaya minimum.

    Biaya sama dengan ``balance_title`` Lua: lebar baris terpanjang ditambah
    100 untuk setiap baris yatim (satu kata).
    """

    total = len(words)
    if line_count <= 0 or line_count > total:
        return None

    best: tuple[str, ...] | None = None
    best_cost = math.inf

    def recurse(
        start: int,
        remaining: int,
        current: tuple[str, ...],
        widest: int,
        orphans: int,
    ) -> None:
        nonlocal best, best_cost

        if remaining == 1:
            line = " ".join(words[start:])
            lines = current + (line,)
            width = max(widest, len(line))
            orphan_count = orphans + (1 if _count_words(line) <= 1 else 0)
            cost = width + 100 * orphan_count
            if cost < best_cost:
                best = lines
                best_cost = cost
            return

        # Sisakan minimal satu kata untuk setiap baris berikutnya.
        for end in range(start, total - remaining + 1):
            line = " ".join(words[start : end + 1])
            recurse(
                end + 1,
                remaining - 1,
                current + (line,),
                max(widest, len(line)),
                orphans + (1 if _count_words(line) <= 1 else 0),
            )

    recurse(0, line_count, (), 0, 0)
    return best


def balance_title(
    text: str,
    *,
    max_length: int = 55,
    max_line_width: int = 50,
) -> tuple[str, ...]:
    """Pecah judul menjadi baris seimbang, port dari ``balance_title`` Lua.

    Guard khusus: judul dua kata yang lebih panjang dari ``max_length``
    dikembalikan sebagai dua baris, bukan ``None`` seperti perilaku Lua lama
    yang berakhir dengan crash saat diindeks.
    """

    stripped = text.strip()
    words = stripped.split()
    if not words:
        return ("",)
    if len(words) <= 1 or len(stripped) <= max_length:
        return (stripped,)

    two = _best_partition(words, 2)
    if two is not None and not _has_orphan(two) and _max_line_length(two) <= max_line_width:
        return two

    if len(words) >= 3:
        three = _best_partition(words, 3)
        if three is not None:
            return three

    # Guard: dua kata panjang tidak punya partisi tiga baris. Kembalikan
    # partisi dua baris agar pemanggil tidak menerima None/IndexError.
    if two is not None:
        return two
    return (stripped,)
