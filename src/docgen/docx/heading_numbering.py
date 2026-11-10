"""Penomoran heading body DOCX.

Modul ini memisahkan penomoran H1/H2/H3 dari model section: membaca heading,
menentukan heading unnumbered, memformat nomor, dan menulis ulang run judul.
Konversi angka Romawi memakai :func:`docgen.docx.numbering.format_roman` agar
tidak ada tabel Romawi kedua. Modul ini tidak menangani ``w:sectPr``,
header/footer, atau geometri halaman.
"""

import re
from dataclasses import dataclass
from typing import Literal

from lxml import etree

from ..errors import DocgenError
from . import paragraphs
from .names import W_BR, W_CR, W_PPR, W_T, W_TAB, W, local_name
from .numbering import format_roman
from .package import DOCUMENT_PART, DocumentPackage
from .runs import build_run, clone_run
from .xml import iter_paragraphs, iter_runs, run_text, sha256_c14n


class HeadingError(DocgenError):
    """Heading tidak valid atau level tidak didukung."""

    default_code = "HEADING"


@dataclass(frozen=True)
class Heading:
    """Satu heading body beserta nomor hasil pembacaan."""

    level: int
    paragraph: etree._Element
    text: str
    number: str | None
    unnumbered: bool


@dataclass(frozen=True)
class NumberingSpec:
    """Konfigurasi penomoran heading dari ``structure.numbering``."""

    body: Literal["BAB_ROMAN", "ARABIC_DOTTED"]
    sub_dot: bool = True
    subsub_dot: bool = True


@dataclass(frozen=True)
class HeadingReport:
    """Ringkasan hasil :func:`apply_heading_numbering`."""

    changed: bool
    numbered: int
    unnumbered: int
    skipped_without_chapter: int
    headings: tuple[Heading, ...]


_FRONT_MATTER_NAMES = frozenset(
    {
        "KATA PENGANTAR",
        "PRAKATA",
        "UCAPAN TERIMA KASIH",
        "ABSTRAK",
        "ABSTRACT",
        "DAFTAR ISI",
        "DAFTAR TABEL",
        "DAFTAR GAMBAR",
        "DAFTAR LAMPIRAN",
        "DAFTAR SINGKATAN",
        "DAFTAR SIMBOL",
        "DAFTAR PUSTAKA",
        "DAFTAR RUJUKAN",
        "BIBLIOGRAFI",
        "MOTTO",
        "PERSEMBAHAN",
    }
)
_UNNUMBERED_PREFIXES = (
    "LEMBAR PENGESAHAN",
    "HALAMAN PENGESAHAN",
    "LEMBAR PERSETUJUAN",
    "HALAMAN PERSETUJUAN",
    "LEMBAR PERNYATAAN",
    "HALAMAN PERNYATAAN",
    "PERNYATAAN ",
    "LAMPIRAN",
)
_HEADING_NUMBER_RE = re.compile(
    r"^\s*(?P<number>BAB\s+(?:[IVXLCDM]+|\d+)|\d+(?:\.\d+)*\.?)",
    re.IGNORECASE,
)
_H1_NUMBER_RE = re.compile(
    r"^\s*(?:BAB\s+(?P<bab>[IVXLCDM]+|\d+)\s*|(?P<arabic>\d+\.)\s*)",
    re.IGNORECASE,
)
_H2_H3_NUMBER_RE = re.compile(r"^\s*\d+(?:\.\d+)+(?:\.)?\s*")
_EXPLICIT_UNNUMBERED_RE = re.compile(r"^\s*\{-\}\s*")


def _roman_chapter(number: int) -> str:
    """Format nomor bab Romawi dengan validasi rentang heading."""

    if number <= 0 or number >= 4000:
        raise HeadingError(f"Nomor bab Romawi di luar rentang: {number}")
    return format_roman(number)


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _number_from_text(level: int, text: str) -> str | None:
    if level == 1:
        match = _H1_NUMBER_RE.match(text)
        if match is None:
            return None
        number = match.group("bab") or match.group("arabic")
        if number is None:
            return None
        if match.group("arabic") is not None:
            return number.strip()
        return f"BAB {' '.join(number.split())}"
    match = _HEADING_NUMBER_RE.match(text)
    if match is None:
        return None
    number = match.group("number")
    return " ".join(number.split())


def is_unnumbered(paragraph: etree._Element) -> bool:
    """True untuk heading yang tidak boleh mendapat nomor bab.

    Mendukung marker eksplisit ``{-}``, style yang mengandung
    ``unnumbered``, serta heading front/back matter yang lazim.
    """

    if paragraphs.heading_level(paragraph) is None:
        return False
    style = paragraphs.paragraph_style_id(paragraph) or ""
    if "unnumbered" in style.casefold():
        return True
    text = paragraphs.paragraph_text(paragraph).strip()
    if _EXPLICIT_UNNUMBERED_RE.match(text):
        return True
    normalized = _normalized(text).upper()
    if not normalized:
        return True
    if normalized in _FRONT_MATTER_NAMES:
        return True
    return any(
        normalized == prefix.rstrip() or normalized.startswith(prefix)
        for prefix in _UNNUMBERED_PREFIXES
    )


def heading_text(
    paragraph: etree._Element,
    *,
    include_number: bool = True,
) -> str:
    """Teks heading; ``include_number=False`` membuang prefix nomor lama."""

    full = paragraphs.paragraph_text(paragraph).strip()
    if include_number:
        return full
    level = paragraphs.heading_level(paragraph) or 0
    if level == 1:
        stripped = _H1_NUMBER_RE.sub("", full)
    elif level in (2, 3):
        stripped = _H2_H3_NUMBER_RE.sub("", full)
    else:
        stripped = full
    return stripped.strip("\t \n")


def iter_headings(package: DocumentPackage) -> tuple[Heading, ...]:
    """Iterasi heading body dalam urutan dokumen."""

    root = package.xml(DOCUMENT_PART)
    headings: list[Heading] = []
    for paragraph in iter_paragraphs(root):
        level = paragraphs.heading_level(paragraph)
        if level is None:
            continue
        text = paragraphs.paragraph_text(paragraph).strip()
        headings.append(
            Heading(
                level=level,
                paragraph=paragraph,
                text=text,
                number=_number_from_text(level, text),
                unnumbered=is_unnumbered(paragraph),
            )
        )
    return tuple(headings)


def _strip_prefix_from_runs(
    runs: list[etree._Element],
    prefix: str,
) -> list[etree._Element]:
    remaining = len(prefix)
    result: list[etree._Element] = []
    for run in runs:
        clone = clone_run(run)
        for child in list(clone):
            if not isinstance(child.tag, str):
                continue
            if remaining <= 0:
                break
            if child.tag == W_T:
                text = child.text or ""
                take = min(len(text), remaining)
                child.text = text[take:]
                remaining -= take
                if not child.text:
                    clone.remove(child)
            elif child.tag in (W_TAB, W_BR, W_CR):
                clone.remove(child)
                remaining -= 1
        has_content = bool(run_text(clone)) or any(
            isinstance(child.tag, str)
            and child.tag in (W_TAB, W_BR, W_CR, W + "drawing", W + "pict", W + "object")
            for child in clone
        )
        if has_content:
            result.append(clone)
    # Buang tab/break kosong di awal.
    while result:
        text = run_text(result[0])
        has_break = (
            result[0].find(W_TAB) is not None
            or result[0].find(W_BR) is not None
            or result[0].find(W_CR) is not None
        )
        if text or not has_break:
            break
        result.pop(0)
    return result


def _uppercase_runs(runs: list[etree._Element]) -> None:
    for run in runs:
        for text in run.iter(W_T):
            if text.text:
                text.text = text.text.upper()


def _template_rpr(template: etree._Element | None) -> etree._Element | None:
    return template.find(W + "rPr") if template is not None else None


def _detached_run(
    template: etree._Element | None,
    *,
    text: str | None = None,
) -> etree._Element:
    """Run baru ber-``rPr`` templat, belum terpasang di paragraf mana pun."""

    return build_run(text=text, rpr=_template_rpr(template))


def _run_with_text(template: etree._Element | None, text: str) -> etree._Element:
    return _detached_run(template, text=text)


def _run_with_break(template: etree._Element | None, tag: str) -> etree._Element:
    run = build_run(rpr=_template_rpr(template))
    etree.SubElement(run, tag)
    return run


def _replace_heading_content(
    paragraph: etree._Element,
    prefix_runs: list[etree._Element],
    title_runs: list[etree._Element],
) -> None:
    """Ganti run heading tanpa menghapus bookmark/proofErr."""

    ppr = paragraph.find(W_PPR)
    preserved = {
        "bookmarkStart",
        "bookmarkEnd",
        "proofErr",
        "permStart",
        "permEnd",
        "commentRangeStart",
        "commentRangeEnd",
    }
    for child in list(paragraph):
        if child is ppr:
            continue
        if local_name(child.tag) in preserved:
            continue
        paragraph.remove(child)
    insert_at = 1 if ppr is not None else 0
    while insert_at < len(paragraph) and local_name(paragraph[insert_at].tag) in (
        "bookmarkStart",
        "proofErr",
    ):
        insert_at += 1
    for run in prefix_runs + title_runs:
        paragraph.insert(insert_at, run)
        insert_at += 1


def _strip_leading_separators(
    runs: list[etree._Element],
) -> list[etree._Element]:
    """Buang tab/break/spasi di awal title runs setelah prefix nomor."""

    result: list[etree._Element] = []
    stripping = True
    for run in runs:
        clone = run
        if stripping:
            for child in list(clone):
                if not isinstance(child.tag, str):
                    continue
                if child.tag in (W_TAB, W_BR, W_CR):
                    clone.remove(child)
                    continue
                if child.tag == W_T:
                    text = child.text or ""
                    stripped = text.lstrip(" \t\r\n")
                    if stripped:
                        child.text = stripped
                        stripping = False
                    else:
                        clone.remove(child)
                    continue
                if child.tag == W + "rPr":
                    continue
                # Elemen lain (mis. drawing) adalah konten judul.
                stripping = False
                break
            if not run_text(clone) and clone.find(".//" + W_TAB) is None:
                has_visual = any(
                    isinstance(child.tag, str)
                    and child.tag in (W_TAB, W_BR, W_CR, W + "drawing", W + "pict", W + "object")
                    for child in clone
                )
                if not has_visual:
                    continue
        result.append(clone)
    return result


def _heading_title_runs(
    paragraph: etree._Element,
    *,
    level: int,
    uppercase: bool,
) -> list[etree._Element]:
    text = paragraphs.paragraph_text(paragraph)
    if level == 1:
        match = _H1_NUMBER_RE.match(text)
    elif level in (2, 3):
        match = _H2_H3_NUMBER_RE.match(text)
    else:
        match = None
    prefix = match.group(0) if match is not None else ""
    # Prefix dari regex boleh memuat tab/line-break yang di DOCX tersimpan
    # sebagai elemen ``w:tab``/``w:br`` di luar run. Hanya karakter teks yang
    # boleh dihitung agar huruf pertama judul tidak ikut terpotong.
    prefix = prefix.rstrip(" \t\r\n")
    runs = list(iter_runs(paragraph))
    title_runs = _strip_prefix_from_runs(runs, prefix)
    title_runs = _strip_leading_separators(title_runs)
    if not any(run_text(run) for run in title_runs):
        fallback_text = heading_text(paragraph, include_number=False)
        if fallback_text:
            title_runs = [_run_with_text(runs[0] if runs else None, fallback_text)]
    if uppercase:
        _uppercase_runs(title_runs)
    return title_runs


def _numbered_runs(
    paragraph: etree._Element,
    number: str,
    *,
    level: int,
    kind: str,
) -> list[etree._Element]:
    runs = list(iter_runs(paragraph))
    template = runs[0] if runs else None
    prefix: list[etree._Element] = [_run_with_text(template, number)]
    if level == 1 and kind == "BAB_ROMAN":
        prefix.append(_run_with_break(template, W_BR))
    elif level == 1:
        prefix.append(_run_with_text(template, " "))
    else:
        prefix.append(_run_with_break(template, W_TAB))
    return prefix


def apply_heading_numbering(
    package: DocumentPackage,
    spec: NumberingSpec,
) -> HeadingReport:
    """Nomori H1/H2/H3 dan pertahankan format inline judul.

    H1 ``BAB_ROMAN`` menjadi ``BAB I`` + line break + judul kapital.
    H1 ``ARABIC_DOTTED`` menjadi ``1.`` + spasi + judul kapital. H2/H3
    memakai nomor bertingkat + tab. H4-H9 dan heading unnumbered tidak
    mengubah counter.
    """

    if spec.body not in ("BAB_ROMAN", "ARABIC_DOTTED"):
        raise HeadingError(f"Format penomoran body tidak dikenal: {spec.body!r}")

    before = sha256_c14n(package.xml(DOCUMENT_PART))
    chapter = 0
    sub = 0
    subsub = 0
    numbered = 0
    unnumbered = 0
    skipped = 0
    in_unnumbered_section = False

    for heading in iter_headings(package):
        paragraph = heading.paragraph
        level = heading.level
        if level not in (1, 2, 3):
            continue
        if heading.unnumbered:
            if level == 1:
                in_unnumbered_section = True
            unnumbered += 1
            continue
        if level == 1:
            in_unnumbered_section = False
            chapter += 1
            sub = 0
            subsub = 0
            number = f"BAB {_roman_chapter(chapter)}" if spec.body == "BAB_ROMAN" else f"{chapter}."
            prefix = _numbered_runs(
                paragraph,
                number,
                level=1,
                kind=spec.body,
            )
            title_runs = _heading_title_runs(
                paragraph,
                level=1,
                uppercase=True,
            )
            _replace_heading_content(paragraph, prefix, title_runs)
            numbered += 1
            continue
        if in_unnumbered_section:
            unnumbered += 1
            continue
        if chapter == 0:
            skipped += 1
            continue
        if level == 2:
            sub += 1
            subsub = 0
            suffix = "." if spec.sub_dot else ""
            number = f"{chapter}.{sub}{suffix}"
        else:
            subsub += 1
            suffix = "." if spec.subsub_dot else ""
            number = f"{chapter}.{sub}.{subsub}{suffix}"
        prefix = _numbered_runs(
            paragraph,
            number,
            level=level,
            kind=spec.body,
        )
        title_runs = _heading_title_runs(paragraph, level=level, uppercase=False)
        _replace_heading_content(paragraph, prefix, title_runs)
        numbered += 1

    after = sha256_c14n(package.xml(DOCUMENT_PART))
    return HeadingReport(
        changed=before != after,
        numbered=numbered,
        unnumbered=unnumbered,
        skipped_without_chapter=skipped,
        headings=iter_headings(package),
    )


def heading_bookmark_name(heading: Heading) -> str:
    """Nama bookmark stabil untuk PAGEREF/TOC."""

    if heading.number:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", heading.number).strip("_")
        if safe:
            return f"_Toc{safe}"
    safe = re.sub(r"[^A-Za-z0-9]+", "_", heading.text).strip("_")
    if safe:
        return f"_Toc{safe[:40]}"
    return f"_TocHeading{heading.level}"


__all__ = [
    "Heading",
    "HeadingError",
    "HeadingReport",
    "NumberingSpec",
    "apply_heading_numbering",
    "heading_bookmark_name",
    "heading_text",
    "is_unnumbered",
    "iter_headings",
]
