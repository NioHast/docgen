"""Stage ``sections``: section break, ukuran halaman, dan margin.

Stage ini memastikan dokumen hasil Pandoc memiliki section logis yang benar
sebelum stage lain bekerja:

- sampul berakhir pada section sendiri;
- front matter dan body tidak berbagi section;
- setiap Heading1 ``BAB ...`` dan back matter dimulai pada section baru;
- seluruh section memakai ukuran halaman dan margin dari ``format.yml``.

TOC, nomor halaman, dan header/footer bukan tanggung jawab stage ini. Nomor
heading juga belum diimplementasikan di WS6b dan dilaporkan sebagai gap.
"""

import re
import time

from lxml import etree

from ..docx.package import DOCUMENT_PART, DocumentPackage
from ..docx.sections import (
    HeadingError,
    NumberingSpec,
    SectionError,
    add_section_break,
    apply_heading_numbering,
    iter_sections,
    set_margins,
    set_page_size,
    set_section_type,
)
from ..docx.xml import paragraph_text, sha256_c14n
from ..errors import StageError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

PAGE_SIZES_TWIP: dict[str, tuple[int, int]] = {
    "A4": (11906, 16838),
    "Letter": (12240, 15840),
}

_CHAPTER_RE = re.compile(
    r"^(?:BAB\s+(?:[IVXLCDM]+|\d+)(?=\b|\s)|\d+\.(?=\s|$))",
    re.IGNORECASE,
)
_BACK_MATTER_RE = re.compile(
    r"^(?:DAFTAR\s+PUSTAKA|DAFTAR\s+RUJUKAN|LAMPIRAN|BIBLIOGRAFI)\b",
    re.IGNORECASE,
)


class SectionsError(SectionError):
    """Konfigurasi section tidak dapat diterapkan."""

    default_code = "SECTION-STAGE"


def _document_hash(package: DocumentPackage) -> str:
    return sha256_c14n(package.xml(DOCUMENT_PART))


def _page_size(page: object) -> tuple[int, int]:
    size = str(getattr(page, "size", "A4"))
    orientation = str(getattr(page, "orientation", "portrait"))
    try:
        width, height = PAGE_SIZES_TWIP[size]
    except KeyError as exc:
        raise SectionsError(f"Ukuran halaman tidak dikenal: {size!r}") from exc
    if orientation == "landscape":
        return height, width
    return width, height


def _style(paragraph: etree._Element) -> str | None:
    ppr = paragraph.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr")
    if ppr is None:
        return None
    style = ppr.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pStyle")
    if style is None:
        return None
    return style.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val")


def _paragraph_text(paragraph: etree._Element) -> str:
    return " ".join(paragraph_text(paragraph).split())


def _heading_level(paragraph: etree._Element) -> int | None:
    style = _style(paragraph)
    if style is None:
        return None
    match = re.fullmatch(r"Heading([1-9])", style)
    return int(match.group(1)) if match else None


def _body_children(package: DocumentPackage) -> list[etree._Element]:
    from ..docx.names import W_BODY, W_DOCUMENT

    root = package.xml(DOCUMENT_PART)
    if not isinstance(root.tag, str) or root.tag != W_DOCUMENT:
        raise SectionsError("Root document.xml bukan w:document")
    body = root.find(W_BODY)
    if body is None:
        raise SectionsError("w:body tidak ditemukan")
    return [child for child in body if isinstance(child.tag, str)]


def _first_heading_after_cover(package: DocumentPackage) -> etree._Element | None:
    """Heading1 pertama setelah paragraf bergaya Cover*."""

    from ..docx.names import W_P

    sections = iter_sections(package)
    if not sections:
        return None
    first = sections[0]
    children = _body_children(package)
    last_cover = -1
    for index in range(first.start, first.end):
        child = children[index] if index < len(children) else None
        if child is not None and child.tag == W_P:
            style = _style(child)
            if style is not None and style.casefold().startswith("cover"):
                last_cover = index
    for index in range(max(last_cover + 1, first.start), first.end):
        child = children[index] if index < len(children) else None
        if child is not None and child.tag == W_P and _heading_level(child) == 1:
            return child
    return None


def _break_headings(package: DocumentPackage) -> list[etree._Element]:
    """Heading1 yang wajib menjadi awal section baru."""

    from ..docx.names import W_P

    headings: list[etree._Element] = []
    for paragraph in _body_children(package):
        if paragraph.tag != W_P:
            continue
        if _heading_level(paragraph) != 1:
            continue
        text = _paragraph_text(paragraph)
        if _CHAPTER_RE.match(text) or _BACK_MATTER_RE.match(text):
            headings.append(paragraph)
    return headings


def _apply_page_format(package: DocumentPackage, page: object) -> int:
    width, height = _page_size(page)
    margins = getattr(page, "margins", None)
    if margins is None:
        raise SectionsError("format.page.margins tidak tersedia")
    changed = 0
    for section in iter_sections(package):
        before = sha256_c14n(section.sect_pr)
        set_page_size(
            section,
            width=width,
            height=height,
            orientation=str(getattr(page, "orientation", "portrait")),  # type: ignore[arg-type]
        )
        set_margins(
            section,
            top=int(margins.top),
            right=int(margins.right),
            bottom=int(margins.bottom),
            left=int(margins.left),
            header=int(getattr(page, "header_distance", 0)),
            footer=int(getattr(page, "footer_distance", 0)),
            gutter=int(getattr(page, "gutter", 0)),
        )
        if sha256_c14n(section.sect_pr) != before:
            changed += 1
    return changed


def _ensure_breaks(package: DocumentPackage) -> int:
    added = 0
    cover_heading = _first_heading_after_cover(package)
    if cover_heading is not None:
        sections = iter_sections(package)
        first = sections[0]
        children = _body_children(package)
        index = children.index(cover_heading)
        if first.start < index < first.end:
            add_section_break(package, before=cover_heading, kind="nextPage")
            added += 1

    for heading in _break_headings(package):
        children = _body_children(package)
        index = children.index(heading)
        sections = iter_sections(package)
        section = next(
            (item for item in sections if item.start <= index < item.end),
            None,
        )
        if section is None:
            raise SectionsError("Heading tidak berada di section mana pun")
        if section.start == index:
            continue
        add_section_break(package, before=heading, kind="nextPage")
        added += 1
    return added


class SectionsStage(BaseStage):
    """Bangun section break dan terapkan geometri halaman."""

    name = StageName.SECTIONS
    order = 50
    requires = canonical_prefix(StageName.SECTIONS)
    mutates = frozenset({DOCUMENT_PART})
    idempotent = True

    def enabled(self, ctx: object) -> bool:
        return not getattr(ctx, "dry_run", False)

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        if not self.enabled(ctx):
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                warnings=("dry-run: stage sections tidak dijalankan.",),
            )
        package = getattr(ctx, "package", None)
        if package is None:
            raise StageError(
                self.name.value,
                "package DOCX belum tersedia; stage sections membutuhkan hasil Pandoc.",
                code="STAGE-PACKAGE",
            )
        before = _document_hash(package)
        try:
            sections_before = len(iter_sections(package))
            numbering = getattr(getattr(ctx, "structure", None), "numbering", None)
            heading_report = None
            if numbering is not None:
                heading_report = apply_heading_numbering(
                    package,
                    NumberingSpec(
                        body=str(numbering.body),  # type: ignore[arg-type]
                        sub_dot=bool(getattr(numbering, "sub_dot", True)),
                        subsub_dot=bool(getattr(numbering, "subsub_dot", True)),
                    ),
                )
            added = _ensure_breaks(package)
            page = getattr(getattr(ctx, "format", None), "page", None)
            margin_sections = _apply_page_format(package, page)
            sections_after = len(iter_sections(package))
            for section in iter_sections(package):
                set_section_type(section, "nextPage")
        except (SectionError, HeadingError) as exc:
            raise StageError(
                self.name.value,
                str(exc),
                cause=exc,
                code=exc.code,
            ) from exc
        after = _document_hash(package)
        metrics: dict[str, int | str] = {
            "sections_before": sections_before,
            "sections_after": sections_after,
            "breaks_added": added,
            "margin_sections": margin_sections,
        }
        if heading_report is not None:
            metrics["headings_numbered"] = heading_report.numbered
            metrics["headings_unnumbered"] = heading_report.unnumbered
            metrics["headings_skipped"] = heading_report.skipped_without_chapter
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=before != after,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics=metrics,
        )


__all__ = [
    "PAGE_SIZES_TWIP",
    "SectionsError",
    "SectionsStage",
]
