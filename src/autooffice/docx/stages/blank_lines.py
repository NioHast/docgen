"""Stage ``blank_lines``: sisipkan paragraf kosong fisik sesuai aturan layout.

Aturan posisi:

* satu paragraf kosong setelah Heading1;
* satu paragraf kosong sebelum Heading2/Heading3 bila blok sebelumnya berisi
  isi/tabel/gambar/persamaan;
* nol paragraf kosong antarheading tanpa isi;
* satu paragraf kosong sebelum dan sesudah tabel/gambar/persamaan;
* Heading4-9 tidak diklasifikasi sebagai heading; mengikuti aturan blok isi
  (tidak ada aturan gap heading baru).

``w:ins``/``w:del`` diperlakukan transparan: pembungkus tracked change tidak
memutus urutan blok dan paragraf yang dihapus tidak dihitung sebagai isi.
Paragraf kosong yang sudah ada tidak diduplikasi; stage idempoten.
"""

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass

from lxml import etree

from ..errors import DocgenError
from ..package.fields import field_name, iter_field_instructions
from ..package.layout import (
    COVER_PREFIX,
    TOC_STYLE_RE,
    BodyUnit,
    document_root,
    is_chapter_heading,
    iter_body_units,
    set_document_root,
)
from ..package.names import (
    W_BR,
    W_CR,
    W_DEL,
    W_DRAWING,
    W_FLDCHAR,
    W_FLDSIMPLE,
    W_INS,
    W_INSTRTEXT,
    W_MOVEFROM,
    W_OBJECT,
    W_P,
    W_PICT,
    W_PPR,
    W_SDT,
    W_SECTPR,
    W_TAB,
    W_TBL,
    W_VAL,
    normalize_style_id,
)
from ..package.package import DocumentPackage
from ..package.paragraphs import (
    EMPTY_PARAGRAPH_FONT,
    EMPTY_PARAGRAPH_HALF_POINTS,
    EMPTY_PARAGRAPH_LINE_TWIPS,
    document_body,
    heading_level,
    paragraph_style_id,
    paragraph_text,
)
from ..package.paragraphs import (
    make_empty_paragraph as _canonical_make_empty_paragraph,
)
from ..package.xml import qn, sha256_c14n
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

W_FOOTNOTE_REFERENCE = qn("w:footnoteReference")
W_ENDNOTE_REFERENCE = qn("w:endnoteReference")
M_O_MATH_PARA = qn("m:oMathPara")
M_O_MATH = qn("m:oMath")

EMPTY_FONT = EMPTY_PARAGRAPH_FONT
EMPTY_HALF_POINTS = EMPTY_PARAGRAPH_HALF_POINTS
EMPTY_LINE_TWIPS = EMPTY_PARAGRAPH_LINE_TWIPS

HEADING_STYLE_RE = re.compile(r"^heading([1-9])$")
CAPTION_LABEL_RE = re.compile(r"^\s*(tabel|table|gambar|figure)\b", re.I)
EQUATION_NUMBER_RE = re.compile(r"\(\d+\.\d+\)")

IMAGE_CAPTION_STYLES = frozenset({"imagecaption", "figurecaption"})
TABLE_CAPTION_STYLES = frozenset({"tablecaption"})
GENERIC_CAPTION_STYLES = frozenset({"caption"})

IGNORED_BODY_TAGS = frozenset(
    {
        qn("w:bookmarkStart"),
        qn("w:bookmarkEnd"),
        qn("w:proofErr"),
        qn("w:commentRangeStart"),
        qn("w:commentRangeEnd"),
        qn("w:permStart"),
        qn("w:permEnd"),
    }
)

EMPTY = "empty"
IGNORE = "ignore"
CONTENT = "content"
TABLE = "table"
IMAGE = "image"
EQUATION = "equation"
H1 = "h1"
H2 = "h2"
H3 = "h3"
TOC = "toc"
COVER = "cover"
SECTION = "section"
SECTPR = "sectpr"
OTHER = "other"
CAPTION_TABLE = "caption_table"
CAPTION_IMAGE = "caption_image"


class BlankLineError(DocgenError):
    """Kesalahan penyisipan paragraf kosong."""

    default_code = "BLANK-LINE"


@dataclass(frozen=True, slots=True)
class BlankLineSpec:
    """Format paragraf kosong yang disisipkan."""

    font: str = EMPTY_FONT
    half_points: int = EMPTY_HALF_POINTS
    line_twips: int = EMPTY_LINE_TWIPS

    def __post_init__(self) -> None:
        if not self.font:
            raise BlankLineError("font paragraf kosong tidak boleh kosong")
        if self.half_points <= 0 or self.line_twips <= 0:
            raise BlankLineError("ukuran paragraf kosong harus positif")


@dataclass
class BlankLineReport:
    """Ringkasan penyisipan paragraf kosong."""

    blocks: int = 0
    inserted: int = 0
    after_h1: int = 0
    before_heading: int = 0
    before_object: int = 0
    after_object: int = 0
    empty_paragraphs: int = 0
    skipped_toc: int = 0
    skipped_cover: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "blocks": self.blocks,
            "inserted": self.inserted,
            "after_h1": self.after_h1,
            "before_heading": self.before_heading,
            "before_object": self.before_object,
            "after_object": self.after_object,
            "empty_paragraphs": self.empty_paragraphs,
            "skipped_toc": self.skipped_toc,
            "skipped_cover": self.skipped_cover,
        }


@dataclass(frozen=True, slots=True)
class _Block:
    kind: str
    start: int
    end: int
    element: etree._Element


# ---------------------------------------------------------------------------
# Deteksi blok
# ---------------------------------------------------------------------------


def _has_toc_field(paragraph: etree._Element) -> bool:
    return any(
        field_name(instruction) == "TOC" for instruction in iter_field_instructions(paragraph)
    )


def _is_empty_paragraph(paragraph: etree._Element) -> bool:
    """True bila paragraf tidak menampilkan teks, gambar, atau line break."""

    if paragraph.find(f"{W_PPR}/{W_SECTPR}") is not None:
        return False
    if paragraph_text(paragraph).strip():
        return False
    if paragraph.find(f".//{W_TAB}") is not None:
        return False
    for tag in (
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_BR,
        W_CR,
        W_FLDCHAR,
        W_FLDSIMPLE,
        W_INSTRTEXT,
        W_FOOTNOTE_REFERENCE,
        W_ENDNOTE_REFERENCE,
    ):
        if paragraph.find(f".//{tag}") is not None:
            return False
    return True


def _only_deleted_content(paragraph: etree._Element) -> bool:
    """True untuk paragraf yang isi terlihatnya habis karena tracked delete."""

    if paragraph_text(paragraph).strip():
        return False
    return (
        paragraph.find(f".//{W_DEL}") is not None or paragraph.find(f".//{W_MOVEFROM}") is not None
    )


def _has_image(paragraph: etree._Element) -> bool:
    return any(paragraph.find(f".//{tag}") is not None for tag in (W_DRAWING, W_PICT, W_OBJECT))


def _is_equation_paragraph(paragraph: etree._Element) -> bool:
    if paragraph.find(M_O_MATH_PARA) is not None:
        return True
    if paragraph.find(M_O_MATH) is None:
        return False
    text = paragraph_text(paragraph).strip()
    return not text or EQUATION_NUMBER_RE.fullmatch(text) is not None


def _caption_kind(paragraph: etree._Element, style_id: str) -> str | None:
    if style_id in IMAGE_CAPTION_STYLES:
        return "image"
    if style_id in TABLE_CAPTION_STYLES:
        return "table"
    if style_id in GENERIC_CAPTION_STYLES:
        match = CAPTION_LABEL_RE.match(paragraph_text(paragraph))
        if match is not None:
            label = match.group(1).lower()
            return "image" if label in {"gambar", "figure"} else "table"
    return None


def _sdt_is_toc(element: etree._Element) -> bool:
    for gallery in element.iter(qn("w:docPartGallery")):
        value = (gallery.get(W_VAL) or "").strip().casefold()
        if "table of contents" in value or "daftar isi" in value:
            return True
    for paragraph in element.iter(W_P):
        style_id = normalize_style_id(paragraph_style_id(paragraph))
        if TOC_STYLE_RE.fullmatch(style_id) or _has_toc_field(paragraph):
            return True
    return False


def classify(element: etree._Element, *, deleted: bool = False) -> str:
    """Klasifikasikan satu unit body."""

    if deleted or element.tag in (W_DEL, W_MOVEFROM, W_INS):
        return IGNORE

    if element.tag == W_P:
        if element.find(f"{W_PPR}/{W_SECTPR}") is not None:
            return SECTION
        if _only_deleted_content(element):
            return IGNORE

        style_id = normalize_style_id(paragraph_style_id(element))
        level = heading_level(element)
        if level is None and is_chapter_heading(element):
            level = 1
        if level is not None:
            if level <= 3:
                return f"h{level}"
            # H4-H9 tidak diklasifikasi sebagai heading struktural; tidak ada
            # aturan gap heading baru untuk level ini.
            return CONTENT
        if TOC_STYLE_RE.fullmatch(style_id) or _has_toc_field(element):
            return TOC
        if style_id.startswith(COVER_PREFIX):
            return COVER
        if _has_image(element):
            return IMAGE
        if _is_equation_paragraph(element):
            return EQUATION
        if _is_empty_paragraph(element):
            return EMPTY
        caption = _caption_kind(element, style_id)
        if caption == "table":
            return CAPTION_TABLE
        if caption == "image":
            return CAPTION_IMAGE
        return CONTENT

    if element.tag == W_TBL:
        return TABLE
    if element.tag == W_SECTPR:
        return SECTPR
    if element.tag == W_SDT:
        return TOC if _sdt_is_toc(element) else OTHER
    if element.tag in IGNORED_BODY_TAGS:
        return IGNORE
    return OTHER


# ---------------------------------------------------------------------------
# Penyusunan blok
# ---------------------------------------------------------------------------


def _build_blocks(units: Sequence[BodyUnit], kinds: Sequence[str]) -> list[_Block]:
    """Gabungkan caption dengan tabel/gambar agar jarak tidak jatuh di tengah."""

    blocks: list[_Block] = []
    index = 0
    total = len(units)

    while index < total:
        kind = kinds[index]

        if kind in (EMPTY, IGNORE):
            index += 1
            continue

        if kind == CAPTION_TABLE:
            if index + 1 < total and kinds[index + 1] == TABLE:
                blocks.append(_Block(TABLE, index, index + 1, units[index].element))
                index += 2
                continue
            blocks.append(_Block(CONTENT, index, index, units[index].element))
            index += 1
            continue

        if kind == TABLE:
            end = index
            cursor = index + 1
            if cursor < total and kinds[cursor] == CAPTION_TABLE:
                end = cursor
            blocks.append(_Block(TABLE, index, end, units[index].element))
            index = end + 1
            continue

        if kind == IMAGE:
            end = index
            cursor = index + 1
            while cursor < total and kinds[cursor] == CAPTION_IMAGE:
                end = cursor
                cursor += 1
            blocks.append(_Block(IMAGE, index, end, units[index].element))
            index = end + 1
            continue

        if kind == CAPTION_IMAGE:
            if index + 1 < total and kinds[index + 1] == IMAGE:
                end = index + 1
                cursor = end + 1
                while cursor < total and kinds[cursor] == CAPTION_IMAGE:
                    end = cursor
                    cursor += 1
                blocks.append(_Block(IMAGE, index, end, units[index].element))
                index = end + 1
                continue
            blocks.append(_Block(CONTENT, index, index, units[index].element))
            index += 1
            continue

        blocks.append(_Block(kind, index, index, units[index].element))
        index += 1

    return blocks


def _desired_gap(previous: _Block | None, current: _Block) -> int:
    """Jumlah paragraf kosong yang seharusnya ada sebelum ``current``."""

    if current.kind in (TOC, COVER, SECTION, SECTPR, OTHER):
        return 0

    if current.kind in (H2, H3):
        if previous is None:
            return 0
        if previous.kind in (CONTENT, TABLE, IMAGE, EQUATION):
            return 1
        if previous.kind == H1:
            return 1
        return 0

    if current.kind == H1:
        if previous is not None and previous.kind in (TABLE, IMAGE, EQUATION):
            return 1
        return 0

    if current.kind in (TABLE, IMAGE, EQUATION):
        if previous is None:
            return 0
        if previous.kind in (TOC, COVER, SECTION, SECTPR, OTHER):
            return 0
        return 1

    # Blok isi biasa.
    if previous is not None and previous.kind == H1:
        return 1
    if previous is not None and previous.kind in (TABLE, IMAGE, EQUATION):
        return 1
    return 0


def _gap_reason(previous: _Block | None, current: _Block) -> str:
    if (
        current.kind in (H2, H3)
        and previous is not None
        and previous.kind in (CONTENT, TABLE, IMAGE, EQUATION)
    ):
        return "before_heading"
    if previous is not None and previous.kind == H1:
        return "after_h1"
    if current.kind in (TABLE, IMAGE, EQUATION):
        return "before_object"
    if previous is not None and previous.kind in (TABLE, IMAGE, EQUATION):
        return "after_object"
    return "other"


def make_empty_paragraph(spec: BlankLineSpec | None = None) -> etree._Element:
    """Buat paragraf kosong TNR 12 pt, line 360, before/after 0.

    Wrapper tipis stage ini: format kanonis dibangun oleh
    :func:`autooffice.docx.package.paragraphs.make_empty_paragraph` agar spec default dan
    paragraf gap TOC memakai satu sumber.
    """

    resolved = spec or BlankLineSpec()
    return _canonical_make_empty_paragraph(
        font=resolved.font,
        half_points=resolved.half_points,
        line_twips=resolved.line_twips,
    )


# ---------------------------------------------------------------------------
# API utama
# ---------------------------------------------------------------------------


def insert_blank_lines(
    package: DocumentPackage,
    *,
    spec: BlankLineSpec | None = None,
) -> BlankLineReport:
    """Sisipkan paragraf kosong pada ``DocumentPackage`` hidup."""

    spec = spec or BlankLineSpec()
    root = document_root(package)
    body = document_body(package)
    units = list(iter_body_units(body))
    kinds = [classify(unit.element, deleted=unit.deleted) for unit in units]
    blocks = _build_blocks(units, kinds)

    report = BlankLineReport(blocks=len(blocks))
    report.skipped_toc = sum(1 for kind in kinds if kind == TOC)
    report.skipped_cover = sum(1 for kind in kinds if kind == COVER)

    insertions: list[tuple[etree._Element, int, str]] = []
    previous: _Block | None = None
    for current in blocks:
        wanted = _desired_gap(previous, current)
        if wanted <= 0:
            previous = current
            continue

        actual = (
            sum(1 for index in range(previous.end + 1, current.start) if kinds[index] == EMPTY)
            if previous is not None
            else 0
        )
        needed = wanted - actual
        if needed > 0:
            insertions.append((current.element, needed, _gap_reason(previous, current)))
        previous = current

    for element, count, reason in insertions:
        for _ in range(count):
            element.addprevious(make_empty_paragraph(spec))
        report.inserted += count
        if reason == "after_h1":
            report.after_h1 += count
        elif reason == "before_heading":
            report.before_heading += count
        elif reason == "before_object":
            report.before_object += count
        elif reason == "after_object":
            report.after_object += count

    report.empty_paragraphs = sum(
        1
        for unit in iter_body_units(body)
        if unit.element.tag == W_P and _is_empty_paragraph(unit.element)
    )

    if insertions:
        set_document_root(package, root)
    return report


class BlankLinesStage(BaseStage):
    """Stage penyisipan paragraf kosong fisik."""

    name = StageName.BLANK_LINES
    order = 110
    requires = canonical_prefix(StageName.BLANK_LINES)
    mutates = frozenset({"word/document.xml"})
    idempotent = True

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        package = getattr(ctx, "package", None)
        if package is None:
            raise BlankLineError("stage blank_lines membutuhkan DocumentPackage dari stage pandoc")

        try:
            before = sha256_c14n(document_root(package))
            report = insert_blank_lines(package, spec=BlankLineSpec())
            changed = sha256_c14n(document_root(package)) != before
        except BlankLineError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise BlankLineError(
                f"stage blank_lines gagal: {exc}",
                code="BLANK-LINE-STAGE",
            ) from exc

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "blocks": report.blocks,
                "inserted": report.inserted,
                "after_h1": report.after_h1,
                "before_heading": report.before_heading,
                "before_object": report.before_object,
                "after_object": report.after_object,
                "empty_paragraphs": report.empty_paragraphs,
            },
        )


__all__ = [
    "EMPTY_FONT",
    "EMPTY_HALF_POINTS",
    "EMPTY_LINE_TWIPS",
    "BlankLineError",
    "BlankLineReport",
    "BlankLineSpec",
    "BlankLinesStage",
    "classify",
    "insert_blank_lines",
    "make_empty_paragraph",
]
