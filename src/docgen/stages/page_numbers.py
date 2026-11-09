"""Stage ``page_numbers``: Romawi untuk front matter, Arab untuk body.

Stage ini menulis ``w:pgNumType`` per section, membuat part header/footer
baru beserta relationship dan content type, lalu mengisi field ``PAGE``
native. Tidak ada probe tersembunyi untuk ``docx-pagenum``; Word/LibreOffice
yang mengisi nilai field saat dokumen dibuka.
"""

from __future__ import annotations

import time

from lxml import etree

from ..docx.fields import FieldKind, iter_fields_in_part
from ..docx.names import R_ID, W, local_name
from ..docx.package import DOCUMENT_PART
from ..docx.sections import (
    Section,
    SectionError,
    clear_header_footer_references,
    create_header_footer_part,
    header_footer_part,
    iter_sections,
    remove_unused_header_footer_parts,
    section_header_footer,
    set_header_footer_reference,
    set_page_number_format,
    set_part_xml,
    set_title_page,
)
from ..docx.xml import sha256_c14n
from ..errors import StageError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

PAGE_FIELD_INSTRUCTION = " PAGE "

FRONT_FOOTER_SIZE_HALF_POINTS = 24
BODY_HEADER_SIZE_HALF_POINTS = 20
BODY_FOOTER_SIZE_HALF_POINTS = 24


def _root(kind: str) -> etree._Element:
    tag = "hdr" if kind == "header" else "ftr"
    return etree.Element(W + tag)


def _run_properties(
    *,
    hidden: bool,
    size_half_points: int,
) -> etree._Element:
    rpr = etree.Element(W + "rPr")
    if hidden:
        etree.SubElement(rpr, W + "vanish")
    if hidden:
        color = etree.SubElement(rpr, W + "color")
        color.set(W + "val", "FFFFFF")
    sz = etree.SubElement(rpr, W + "sz")
    sz.set(W + "val", str(size_half_points))
    sz_cs = etree.SubElement(rpr, W + "szCs")
    sz_cs.set(W + "val", str(size_half_points))
    return rpr


def _append_page_run(
    paragraph: etree._Element,
    *,
    text: str | None = None,
    instr: str | None = None,
    fld_char: str | None = None,
    rpr: etree._Element,
) -> None:
    run = etree.SubElement(paragraph, W + "r")
    run.append(_copy_rpr(rpr))
    if fld_char is not None:
        element = etree.SubElement(run, W + "fldChar")
        element.set(W + "fldCharType", fld_char)
    if instr is not None:
        element = etree.SubElement(run, W + "instrText")
        element.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        element.text = instr
    if text is not None:
        element = etree.SubElement(run, W + "t")
        element.text = text


def _copy_rpr(rpr: etree._Element) -> etree._Element:
    import copy

    return copy.deepcopy(rpr)


def page_part(
    kind: str,
    *,
    align: str,
    hidden: bool = False,
    size_half_points: int,
) -> etree._Element:
    """Buat root part header/footer berisi field PAGE native."""

    if kind not in ("header", "footer"):
        raise SectionError(f"Jenis part tidak dikenal: {kind!r}")
    if align not in ("left", "center", "right"):
        raise SectionError(f"Alignment halaman tidak dikenal: {align!r}")
    root = _root(kind)
    paragraph = etree.SubElement(root, W + "p")
    ppr = etree.SubElement(paragraph, W + "pPr")
    spacing = etree.SubElement(ppr, W + "spacing")
    spacing.set(W + "after", "0")
    spacing.set(W + "line", "240")
    spacing.set(W + "lineRule", "auto")
    indent = etree.SubElement(ppr, W + "ind")
    indent.set(W + "firstLine", "0")
    jc = etree.SubElement(ppr, W + "jc")
    jc.set(W + "val", align)
    rpr = _run_properties(
        hidden=hidden,
        size_half_points=size_half_points,
    )
    ppr.append(_copy_rpr(rpr))
    _append_page_run(paragraph, fld_char="begin", rpr=rpr)
    _append_page_run(paragraph, instr=PAGE_FIELD_INSTRUCTION, rpr=rpr)
    _append_page_run(paragraph, fld_char="separate", rpr=rpr)
    _append_page_run(paragraph, text="1", rpr=rpr)
    _append_page_run(paragraph, fld_char="end", rpr=rpr)
    return root


def empty_part(kind: str) -> etree._Element:
    """Part header/footer kosong untuk halaman pertama bab."""

    if kind not in ("header", "footer"):
        raise SectionError(f"Jenis part tidak dikenal: {kind!r}")
    root = _root(kind)
    etree.SubElement(root, W + "p")
    return root


def _ensure_part(
    package: object,
    *,
    kind: str,
    rel_id: str | None,
    root: etree._Element,
) -> tuple[str, bool]:
    """Tulis part header/footer; buat relationship bila belum ada."""

    if rel_id is None:
        return (
            create_header_footer_part(package, kind=kind, content=root),  # type: ignore[arg-type]
            True,
        )
    part_name, current = header_footer_part(package, rel_id)
    if sha256_c14n(current) == sha256_c14n(root):
        return rel_id, False
    set_part_xml(package, part_name, root)
    return rel_id, True


def _configure_cover(section: Section) -> bool:
    before = sha256_c14n(section.sect_pr)
    clear_header_footer_references(section)
    for tag in ("pgNumType", "titlePg"):
        for element in list(section.sect_pr.findall(W + tag)):
            section.sect_pr.remove(element)
    return sha256_c14n(section.sect_pr) != before


def _configure_front_matter(
    package: object,
    section: Section,
    *,
    start: int | None,
) -> bool:
    before = sha256_c14n(section.sect_pr)
    refs = section_header_footer(section)
    footer_root = page_part(
        "footer",
        align="center",
        size_half_points=FRONT_FOOTER_SIZE_HALF_POINTS,
    )
    footer_id, part_changed = _ensure_part(
        package,
        kind="footer",
        rel_id=refs.footer,
        root=footer_root,
    )
    clear_header_footer_references(section)
    set_header_footer_reference(
        section,
        kind="footer",
        reference_type="default",
        rel_id=footer_id,
    )
    set_title_page(section, False)
    set_page_number_format(section, fmt="lowerRoman", start=start)
    return part_changed or sha256_c14n(section.sect_pr) != before


def _configure_body(
    package: object,
    section: Section,
    *,
    start: int | None,
) -> bool:
    before = sha256_c14n(section.sect_pr)
    refs = section_header_footer(section)

    header_root = page_part(
        "header",
        align="right",
        size_half_points=BODY_HEADER_SIZE_HALF_POINTS,
    )
    header_id, changed_header = _ensure_part(
        package, kind="header", rel_id=refs.header, root=header_root
    )
    first_header_root = empty_part("header")
    first_header_id, changed_first_header = _ensure_part(
        package,
        kind="header",
        rel_id=refs.first_page_header,
        root=first_header_root,
    )
    hidden_footer_root = page_part(
        "footer",
        align="center",
        hidden=True,
        size_half_points=BODY_FOOTER_SIZE_HALF_POINTS,
    )
    hidden_footer_id, changed_footer = _ensure_part(
        package,
        kind="footer",
        rel_id=refs.footer,
        root=hidden_footer_root,
    )
    first_footer_root = page_part(
        "footer",
        align="center",
        size_half_points=BODY_FOOTER_SIZE_HALF_POINTS,
    )
    first_footer_id, changed_first_footer = _ensure_part(
        package,
        kind="footer",
        rel_id=refs.first_page_footer,
        root=first_footer_root,
    )

    clear_header_footer_references(section)
    set_header_footer_reference(
        section, kind="header", reference_type="default", rel_id=header_id
    )
    set_header_footer_reference(
        section,
        kind="header",
        reference_type="first",
        rel_id=first_header_id,
    )
    set_header_footer_reference(
        section, kind="footer", reference_type="default", rel_id=hidden_footer_id
    )
    set_header_footer_reference(
        section,
        kind="footer",
        reference_type="first",
        rel_id=first_footer_id,
    )
    set_title_page(section, True)
    set_page_number_format(section, fmt="decimal", start=start)
    return (
        changed_header
        or changed_first_header
        or changed_footer
        or changed_first_footer
        or sha256_c14n(section.sect_pr) != before
    )


def _page_field_count(package: object) -> int:
    count = 0
    seen: set[str] = set()
    for section in iter_sections(package):
        for reference in section.sect_pr:
            if not isinstance(reference.tag, str):
                continue
            if local_name(reference.tag) not in (
                "headerReference",
                "footerReference",
            ):
                continue
            rel_id = reference.get(R_ID)
            if not rel_id or rel_id in seen:
                continue
            seen.add(rel_id)
            try:
                part_name, _root_element = header_footer_part(package, rel_id)
            except SectionError:
                continue
            fields = iter_fields_in_part(package, part_name)
            count += sum(1 for field in fields if field.kind is FieldKind.PAGE)
    return count


class PageNumbersStage(BaseStage):
    """Set format nomor halaman dan part header/footer per section."""

    name = StageName.PAGE_NUMBERS
    order = 140
    requires = canonical_prefix(StageName.PAGE_NUMBERS)
    mutates = frozenset(
        {
            DOCUMENT_PART,
            "word/header*.xml",
            "word/footer*.xml",
            "word/_rels/document.xml.rels",
            "[Content_Types].xml",
        }
    )
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
                warnings=("dry-run: stage page_numbers tidak dijalankan.",),
            )
        package = getattr(ctx, "package", None)
        if package is None:
            raise StageError(
                self.name.value,
                "package DOCX belum tersedia; stage page_numbers membutuhkan "
                "hasil Pandoc.",
                code="STAGE-PACKAGE",
            )

        before_document = sha256_c14n(package.xml(DOCUMENT_PART))
        front_seen = 0
        body_seen = 0
        changed = False
        sections = iter_sections(package)
        try:
            for section in sections:
                if section.kind == "cover":
                    changed = _configure_cover(section) or changed
                elif section.kind == "front_matter":
                    start = 1 if front_seen == 0 else None
                    changed = (
                        _configure_front_matter(
                            package,
                            section,
                            start=start,  # type: ignore[arg-type]
                        )
                        or changed
                    )
                    front_seen += 1
                else:
                    start = 1 if body_seen == 0 else None
                    changed = (
                        _configure_body(package, section, start=start) or changed
                    )
                    body_seen += 1
            if remove_unused_header_footer_parts(package):
                changed = True
        except SectionError as exc:
            raise StageError(
                self.name.value,
                str(exc),
                cause=exc,
                code=exc.code,
            ) from exc

        if sha256_c14n(package.xml(DOCUMENT_PART)) != before_document:
            changed = True
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "sections": len(sections),
                "front_matter_sections": front_seen,
                "body_sections": body_seen,
                "page_fields": _page_field_count(package),
            },
        )


__all__ = [
    "BODY_FOOTER_SIZE_HALF_POINTS",
    "BODY_HEADER_SIZE_HALF_POINTS",
    "FRONT_FOOTER_SIZE_HALF_POINTS",
    "PageNumbersStage",
    "empty_part",
    "page_part",
]
