"""Stage ``toc``: field TOC native di dalam ``w:sdt`` dan style TOC.

Stage ini menulis field TOC kosong; Word/LibreOffice mengisi entri dan nomor
halaman pada stage ``office``. Tidak ada cache nomor halaman statis dan tidak
ada TOC ganda: field lama diganti.
"""

import time

from lxml import etree

from ..docx.fields import (
    FieldError,
    FieldKind,
    ensure_no_blank_page_after_toc,
    insert_toc,
    iter_fields,
)
from ..docx.names import W
from ..docx.package import DOCUMENT_PART, DocumentPackage
from ..docx.page import PAGE_SIZES, page_size
from ..docx.sections import SectionError, iter_sections
from ..docx.xml import parse_xml, sha256_c14n
from ..errors import StageError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

STYLES_PART = "word/styles.xml"
TOC_TITLE = "DAFTAR ISI"

TOC_STYLE_IDS = ("TOCHeading", "TOC1", "TOC2", "TOC3")

_W_NS_DECL = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


class TocError(FieldError):
    """Style TOC atau penyisipan field TOC gagal."""

    default_code = "TOC"


def _twips(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def tab_position(
    package: DocumentPackage, *, fallback: tuple[int, int, int, int] | None = None
) -> int:
    """Posisi tab kanan TOC dari geometri section pertama.

    Lebar konten dihitung dari ``w:pgSz/@w:w`` dikurangi ``w:pgMar/@w:left``,
    ``@w:right``, dan ``@w:gutter``. ``w:gutter`` opsional dan dihitung 0 bila
    tidak ada. ``fallback`` berisi ``(width, left_margin, right_margin, _)``
    dalam twip dan hanya dipakai bila geometri section tidak lengkap. Tidak ada
    angka bawaan: geometri tidak lengkap tanpa fallback eksplisit menimbulkan
    ``TocError`` berkode ``TOC-TAB``, begitu pula posisi tab <= 1000 twip.
    """

    try:
        sections = iter_sections(package)
    except SectionError as exc:
        sections = ()
        section_error: SectionError | None = exc
    else:
        section_error = None

    if sections:
        sect_pr = sections[0].sect_pr
        pg_sz = sect_pr.find(W + "pgSz")
        pg_mar = sect_pr.find(W + "pgMar")
        width = _twips(pg_sz.get(W + "w")) if pg_sz is not None else None
        left = _twips(pg_mar.get(W + "left")) if pg_mar is not None else None
        right = _twips(pg_mar.get(W + "right")) if pg_mar is not None else None
        gutter = _twips(pg_mar.get(W + "gutter")) if pg_mar is not None else None
        if width is not None and left is not None and right is not None:
            position = width - left - right - (gutter or 0)
            if position <= 1000:
                raise TocError(
                    f"posisi tab TOC tidak valid: {position} twip",
                    code="TOC-TAB",
                )
            return position

    if fallback is not None:
        width, left, right, _unused = fallback
        position = width - left - right
        if position <= 1000:
            raise TocError(
                f"posisi tab TOC dari fallback tidak valid: {position} twip",
                code="TOC-TAB",
            )
        return position

    message = "geometri section pertama tidak lengkap untuk posisi tab TOC"
    if section_error is not None:
        raise TocError(message, code="TOC-TAB") from section_error
    raise TocError(message, code="TOC-TAB")


def _style_fragment(style_id: str, tab_pos: int) -> etree._Element:
    tnr = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'
    definitions = {
        "TOCHeading": f"""<w:style {_W_NS_DECL} w:type="paragraph" w:styleId="TOCHeading">
  <w:name w:val="TOC Heading"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="Normal"/>
  <w:uiPriority w:val="39"/>
  <w:qFormat/>
  <w:pPr>
    <w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/>
    <w:ind w:firstLine="0"/>
    <w:jc w:val="center"/>
    <w:outlineLvl w:val="9"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b/>
    <w:bCs/>
  </w:rPr>
</w:style>""",
        "TOC1": f"""<w:style {_W_NS_DECL} w:type="paragraph" w:styleId="TOC1">
  <w:name w:val="toc 1"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="right" w:leader="dot" w:pos="{tab_pos}"/>
    </w:tabs>
    <w:spacing w:before="0" w:after="0" w:line="260" w:lineRule="auto"/>
    <w:ind w:left="0" w:right="0" w:firstLine="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b w:val="0"/>
    <w:bCs w:val="0"/>
  </w:rPr>
</w:style>""",
        "TOC2": f"""<w:style {_W_NS_DECL} w:type="paragraph" w:styleId="TOC2">
  <w:name w:val="toc 2"/>
  <w:basedOn w:val="TOC1"/>
  <w:next w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="left" w:pos="993"/>
      <w:tab w:val="right" w:leader="dot" w:pos="{tab_pos}"/>
    </w:tabs>
    <w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>
    <w:ind w:left="240" w:right="0" w:firstLine="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b w:val="0"/>
    <w:bCs w:val="0"/>
  </w:rPr>
</w:style>""",
        "TOC3": f"""<w:style {_W_NS_DECL} w:type="paragraph" w:styleId="TOC3">
  <w:name w:val="toc 3"/>
  <w:basedOn w:val="TOC2"/>
  <w:next w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="left" w:pos="1418"/>
      <w:tab w:val="right" w:leader="dot" w:pos="{tab_pos}"/>
    </w:tabs>
    <w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>
    <w:ind w:left="480" w:right="0" w:firstLine="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b w:val="0"/>
    <w:bCs w:val="0"/>
  </w:rPr>
</w:style>""",
    }
    try:
        return parse_xml(definitions[style_id])
    except KeyError as exc:  # pragma: no cover - daftar style internal
        raise TocError(f"Style TOC tidak dikenal: {style_id!r}") from exc


def _styles_root(package: object) -> etree._Element:
    if not package.has_part(STYLES_PART):  # type: ignore[attr-defined]
        raise TocError(f"Part style tidak ditemukan: {STYLES_PART}")
    root = package.xml(STYLES_PART)  # type: ignore[attr-defined]
    if not isinstance(root.tag, str):
        raise TocError("Root styles.xml tidak valid")
    return root


def ensure_toc_styles(package: DocumentPackage, *, tab_pos: int | None = None) -> int:
    """Pastikan style ``TOCHeading`` dan ``TOC1``/``TOC2``/``TOC3`` ada.

    Style yang sudah ada diganti agar geometri tab leader mengikuti margin
    final. Mengembalikan jumlah style yang berubah.
    """

    root = _styles_root(package)
    position = tab_pos if tab_pos is not None else tab_position(package)
    changed = 0
    for style_id in TOC_STYLE_IDS:
        new_style = _style_fragment(style_id, position)
        existing = None
        for child in root:
            if not isinstance(child.tag, str):
                continue
            if child.get(W + "styleId") == style_id:
                existing = child
                break
        if existing is not None:
            if sha256_c14n(existing) == sha256_c14n(new_style):
                continue
            root.replace(existing, new_style)
        else:
            root.append(new_style)
        changed += 1
    return changed


def _document_hash(package: object) -> str:
    return sha256_c14n(package.xml(DOCUMENT_PART))  # type: ignore[attr-defined]


def _styles_hash(package: object) -> str:
    return sha256_c14n(package.xml(STYLES_PART))  # type: ignore[attr-defined]


def _toc_field_count(package: object) -> int:
    return sum(1 for field in iter_fields(package) if field.kind is FieldKind.TOC)


def _format_fallback(ctx: object) -> tuple[int, int, int, int] | None:
    page = getattr(getattr(ctx, "format", None), "page", None)
    if page is None:
        return None
    size = str(getattr(page, "size", "A4"))
    if size not in PAGE_SIZES:
        return None
    width, _height = page_size(size, str(getattr(page, "orientation", "portrait")))
    margins = getattr(page, "margins", None)
    if margins is None:
        return None
    return (
        width,
        int(getattr(margins, "left", 0)),
        int(getattr(margins, "right", 0)),
        0,
    )


class TocStage(BaseStage):
    """Tulis field TOC native dan style TOC."""

    name = StageName.TOC
    order = 130
    requires = canonical_prefix(StageName.TOC)
    mutates = frozenset({DOCUMENT_PART, STYLES_PART})
    idempotent = True

    def enabled(self, ctx: object) -> bool:
        if getattr(ctx, "dry_run", False):
            return False
        structure = getattr(ctx, "structure", None)
        return bool(getattr(structure, "toc", False))

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        if not self.enabled(ctx):
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                warnings=("structure.toc bernilai false; field TOC tidak ditulis.",),
            )
        package = getattr(ctx, "package", None)
        if package is None:
            raise StageError(
                self.name.value,
                "package DOCX belum tersedia; stage toc membutuhkan hasil Pandoc.",
                code="STAGE-PACKAGE",
            )
        before_document = _document_hash(package)
        before_styles = _styles_hash(package)
        try:
            position = tab_position(package, fallback=_format_fallback(ctx))
            styles_changed = ensure_toc_styles(package, tab_pos=position)
            insert_toc(package, title=TOC_TITLE)
            ensure_no_blank_page_after_toc(package)
        except FieldError as exc:
            raise StageError(
                self.name.value,
                str(exc),
                cause=exc,
                code=exc.code,
            ) from exc
        changed = (
            _document_hash(package) != before_document or _styles_hash(package) != before_styles
        )
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "toc_fields": _toc_field_count(package),
                "styles_changed": styles_changed,
                "tab_pos": position,
            },
        )


__all__ = [
    "STYLES_PART",
    "TOC_STYLE_IDS",
    "TOC_TITLE",
    "TocError",
    "TocStage",
    "ensure_toc_styles",
    "tab_position",
]
