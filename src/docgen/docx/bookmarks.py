"""Bookmark paragraf ``pNNNN`` untuk integrasi Adeu.

Bookmark membungkus isi paragraf: ``w:bookmarkStart`` tepat setelah
``w:pPr`` dan ``w:bookmarkEnd`` menjadi child terakhir. Hanya
``word/document.xml`` yang berubah. Header, footer, dan footnote tidak
dihitung karena tidak berada di part tersebut.
"""

import re
from dataclasses import dataclass

from lxml import etree

from . import DocxError, paragraphs
from .names import (
    W_BOOKMARK_END,
    W_BOOKMARK_START,
    W_BR,
    W_CR,
    W_DRAWING,
    W_ID,
    W_NAME,
    W_NO_BREAK_HYPHEN,
    W_OBJECT,
    W_P,
    W_PICT,
    W_PPR,
    W_PTAB,
    W_T,
    W_TAB,
    W_TBL,
    is_caption_style,
    is_cover_style,
    is_heading_style,
    is_style,
    normalize_style_id,
)
from .package import DOCUMENT_PART

PARAGRAPH_ID_RE = re.compile(r"^p\d{4,}$")


class BookmarkError(DocxError):
    """Bookmark tidak valid atau DOCX tidak memiliki body."""

    default_code = "BOOKMARK"


@dataclass(frozen=True)
class Bookmark:
    """Bookmark beserta elemen start/end hidup di ``document.xml``."""

    name: str
    bookmark_id: int
    start: etree._Element
    end: etree._Element


@dataclass(frozen=True)
class ParagraphBookmark:
    """Bookmark satu paragraf body."""

    name: str
    paragraph_index: int
    kind: str
    text: str
    heading_level: int | None = None


def _body(package) -> etree._Element:
    try:
        return paragraphs.document_body(package)
    except paragraphs.ParagraphError as exc:
        raise BookmarkError(str(exc), path=DOCUMENT_PART) from exc


def _paragraphs(body: etree._Element) -> list[etree._Element]:
    """Semua paragraf body, termasuk tabel dan text box, dalam urutan dokumen."""

    return list(body.iter(W_P))


def _in_table(paragraph: etree._Element) -> bool:
    return any(ancestor.tag == W_TBL for ancestor in paragraph.iterancestors())


def paragraph_kind(paragraph: etree._Element) -> str:
    """Klasifikasi kasar paragraf berdasarkan style dan posisi tabel."""

    style = paragraphs.paragraph_style_id(paragraph)
    if is_heading_style(style):
        return "heading"
    if is_caption_style(style):
        return "caption"
    if is_style(style, "Bibliography"):
        return "bibliography"
    if style == "Title" or is_cover_style(style):
        return "cover"
    if style is not None and normalize_style_id(style).startswith("toc"):
        return "toc"
    if _in_table(paragraph):
        return "table"
    return "body"


def _bookmark_id(element: etree._Element) -> int:
    value = element.get(W_ID)
    if value is None:
        raise BookmarkError("bookmark tidak memiliki w:id")
    try:
        return int(value)
    except ValueError as exc:
        raise BookmarkError(f"w:id bookmark bukan bilangan bulat: {value!r}") from exc


def iter_bookmarks(package) -> tuple[Bookmark, ...]:
    """Iterasi bookmark ``pNNNN`` yang lengkap dan valid di document.xml."""

    body = _body(package)
    ends: dict[int, etree._Element] = {}
    for element in body.iter(W_BOOKMARK_END):
        identifier = _bookmark_id(element)
        if identifier in ends:
            raise BookmarkError(f"w:id bookmarkEnd duplikat: {identifier}")
        ends[identifier] = element

    bookmarks: list[Bookmark] = []
    seen_names: set[str] = set()
    seen_ids: set[int] = set()
    for start in body.iter(W_BOOKMARK_START):
        name = start.get(W_NAME) or ""
        if PARAGRAPH_ID_RE.fullmatch(name) is None:
            continue
        identifier = _bookmark_id(start)
        if identifier in seen_ids:
            raise BookmarkError(f"w:id bookmarkStart duplikat: {identifier}")
        seen_ids.add(identifier)
        if name in seen_names:
            raise BookmarkError(f"bookmark duplikat: {name}")
        seen_names.add(name)
        end = ends.get(identifier)
        if end is None:
            raise BookmarkError(f"bookmark {name} tidak memiliki bookmarkEnd")
        bookmarks.append(
            Bookmark(
                name=name,
                bookmark_id=identifier,
                start=start,
                end=end,
            )
        )
    return tuple(bookmarks)


def remove_paragraph_bookmarks(package) -> int:
    """Hapus seluruh bookmark ``pNNNN`` lama; kembalikan jumlah start dihapus."""

    body = _body(package)
    starts = [
        element
        for element in body.iter(W_BOOKMARK_START)
        if PARAGRAPH_ID_RE.fullmatch(element.get(W_NAME) or "") is not None
    ]
    if not starts:
        return 0

    removed_ids = {_bookmark_id(element) for element in starts}
    count = 0
    for element in starts:
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)
            count += 1
    for element in list(body.iter(W_BOOKMARK_END)):
        if _bookmark_id(element) in removed_ids:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
    package.set_xml(DOCUMENT_PART, package.xml(DOCUMENT_PART))
    return count


def next_bookmark_id(package) -> int:
    """ID bookmark berikutnya, di atas seluruh ``w:id`` yang sudah ada."""

    body = _body(package)
    used: list[int] = []
    for tag in (W_BOOKMARK_START, W_BOOKMARK_END):
        for element in body.iter(tag):
            used.append(_bookmark_id(element))
    return max(used, default=-1) + 1


def _insert_bookmark(
    paragraph: etree._Element,
    bookmark_id: int,
    name: str,
) -> None:
    start = etree.Element(W_BOOKMARK_START)
    start.set(W_ID, str(bookmark_id))
    start.set(W_NAME, name)
    end = etree.Element(W_BOOKMARK_END)
    end.set(W_ID, str(bookmark_id))

    ppr = paragraph.find(W_PPR)
    if ppr is None:
        paragraph.insert(0, start)
    else:
        paragraph.insert(paragraph.index(ppr) + 1, start)
    paragraph.append(end)


def add_paragraph_ids(package) -> tuple[ParagraphBookmark, ...]:
    """Ganti bookmark ``pNNNN`` lama dan beri ID pada setiap paragraf body."""

    body = _body(package)
    remove_paragraph_bookmarks(package)

    items = _paragraphs(body)
    start_id = next_bookmark_id(package)
    records: list[ParagraphBookmark] = []
    for index, paragraph in enumerate(items):
        name = f"p{index + 1:04d}"
        _insert_bookmark(paragraph, start_id + index, name)
        records.append(
            ParagraphBookmark(
                name=name,
                paragraph_index=index,
                kind=paragraph_kind(paragraph),
                text=paragraphs.paragraph_text(paragraph),
                heading_level=paragraphs.heading_level(paragraph),
            )
        )

    package.set_xml(DOCUMENT_PART, package.xml(DOCUMENT_PART))
    return tuple(records)


def bookmark_wraps_content(bookmark: Bookmark) -> bool:
    """True bila ada teks/objek di antara ``bookmarkStart`` dan ``bookmarkEnd``."""

    root = bookmark.start.getroottree().getroot()
    if root is None:
        return False
    active = False
    for element in root.iter():
        if element is bookmark.start:
            active = True
            continue
        if element is bookmark.end:
            return False
        if not active:
            continue
        tag = element.tag
        if tag == W_T and (element.text or "").strip():
            return True
        if tag in (
            W_TAB,
            W_PTAB,
            W_BR,
            W_CR,
            W_NO_BREAK_HYPHEN,
            W_DRAWING,
            W_PICT,
            W_OBJECT,
        ):
            return True
    return False


__all__ = [
    "PARAGRAPH_ID_RE",
    "Bookmark",
    "BookmarkError",
    "ParagraphBookmark",
    "add_paragraph_ids",
    "bookmark_wraps_content",
    "iter_bookmarks",
    "next_bookmark_id",
    "paragraph_kind",
    "remove_paragraph_bookmarks",
]
