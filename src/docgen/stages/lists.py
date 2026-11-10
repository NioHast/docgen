r"""Stage ``lists``: daftar tabel/gambar native dan field ``SEQ`` caption.

Stage ini tidak menulis caption dari nol. Caption dan nomor bab sudah dibuat
oleh stage ``captions``; stage ini mengganti angka urutan terakhir menjadi
field ``SEQ`` agar Word dapat memperbarui daftar. Prefix bab literal
dipertahankan dan switch ``\s 1`` dipakai karena heading pipeline memakai
nomor literal, bukan ``w:numPr``. Semua field daftar ditulis lewat
:mod:`docgen.docx.fields`.
"""

import re
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from lxml import etree

from ..docx.captions import CaptionKind, is_caption_paragraph
from ..docx.fields import (
    FieldError,
    FieldKind,
    FieldPosition,
    ensure_no_blank_page_after_toc,
    field_instruction,
    insert_field,
    insert_toc,
    iter_fields_in_paragraph,
    iter_fields_in_root,
)
from ..docx.names import (
    W_HYPERLINK,
    W_R,
    W_RPR,
    W_SDT,
    W_VAL,
)
from ..docx.package import DOCUMENT_PART
from ..docx.paragraphs import (
    ParagraphError,
    document_body,
    paragraph_text,
    remove_direct_children,
)
from ..docx.runs import build_run
from ..docx.xml import (
    iter_paragraphs,
    qn,
    sha256_c14n,
)
from ..errors import StageError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

if TYPE_CHECKING:  # pragma: no cover - hanya anotasi
    from ..docx.package import DocumentPackage

CAPTION_LABEL_DEFAULTS = {"table": "Tabel", "figure": "Gambar"}
LIST_TITLES = {
    "list_of_tables": ("tables", "DAFTAR TABEL"),
    "list_of_figures": ("figures", "DAFTAR GAMBAR"),
}
_CAPTION_NUMBER_RE = re.compile(
    r"^\s*(?P<label>{label})(?P<separator>[\s.:]*)"
    r"(?P<number>\d+(?:\.\d+)*)(?P<rest>\s+.*|$)",
    re.IGNORECASE,
)
_LIST_INSTRUCTION_RE = re.compile(r"\\c\b")
_SDT_ID_BASE = 1180696142


def _body(package: DocumentPackage) -> etree._Element:
    try:
        return document_body(package)
    except ParagraphError as exc:
        raise FieldError(str(exc)) from exc


def _list_toc_sdts(body: etree._Element) -> tuple[etree._Element, ...]:
    r"""SDT TOC daftar (``TOC \c``) yang menjadi child langsung ``w:body``."""

    found: list[etree._Element] = []
    for child in body:
        if not isinstance(child.tag, str) or child.tag != W_SDT:
            continue
        if any(
            field.kind is FieldKind.TOC
            and _LIST_INSTRUCTION_RE.search(field_instruction(field)) is not None
            for field in iter_fields_in_root(child)
        ):
            found.append(child)
    return tuple(found)


def _sdt_ancestor(element: etree._Element) -> etree._Element:
    node: etree._Element | None = element
    while node is not None:
        if node.tag == W_SDT:
            return node
        node = node.getparent()
    raise FieldError("Field TOC tidak berada di dalam w:sdt")


def _next_sdt_id(body: etree._Element) -> int:
    highest = 0
    for sdt in body.iter(W_SDT):
        properties = sdt.find(qn("w:sdtPr"))
        if properties is None:
            continue
        identifier = properties.find(qn("w:id"))
        if identifier is None:
            continue
        try:
            highest = max(highest, int(identifier.get(W_VAL) or "0"))
        except ValueError:
            continue
    return max(_SDT_ID_BASE, highest + 1)


def _set_sdt_id(sdt: etree._Element, value: int) -> None:
    properties = sdt.find(qn("w:sdtPr"))
    if properties is None:
        return
    identifier = properties.find(qn("w:id"))
    if identifier is not None:
        identifier.set(W_VAL, str(value))


def _list_requests(structure: object | None) -> tuple[tuple[str, str], ...]:
    """Daftar ``(kunci lists, judul)`` sesuai urutan ``front_matter``."""

    if structure is None:
        return ()
    settings = getattr(structure, "lists", None)
    enabled = {
        "tables": bool(getattr(settings, "tables", True)),
        "figures": bool(getattr(settings, "figures", True)),
    }
    requests: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in getattr(structure, "front_matter", ()) or ():
        item_id = str(getattr(item, "id", ""))
        if item_id not in LIST_TITLES or item_id in seen:
            continue
        key, title = LIST_TITLES[item_id]
        if not enabled[key]:
            continue
        seen.add(item_id)
        requests.append((key, title))
    return tuple(requests)


def _caption_settings(format_value: object | None) -> tuple[dict[str, str], str]:
    captions = getattr(format_value, "captions", None)

    def label(kind: str) -> str:
        style = getattr(captions, kind, None)
        value = getattr(style, "label", None) if style is not None else None
        return str(value or CAPTION_LABEL_DEFAULTS[kind])

    figures = getattr(format_value, "figures", None)
    scope = str(getattr(figures, "numbering", "chapter") or "chapter")
    if scope not in {"chapter", "document"}:
        scope = "chapter"
    return {
        "table": label("table"),
        "figure": label("figure"),
    }, scope


def _caption_pattern(label: str) -> re.Pattern[str]:
    return re.compile(
        _CAPTION_NUMBER_RE.pattern.replace("{label}", re.escape(label)),
        re.IGNORECASE,
    )


def _caption_prefix(
    text: str,
    label: str,
    scope: str,
) -> tuple[str, str, str] | None:
    """Pisahkan caption menjadi ``(before, counter, after)``.

    ``before`` mempertahankan label dan prefix bab literal; ``counter`` adalah
    angka yang akan diganti field ``SEQ``.
    """

    match = _caption_pattern(label).match(text)
    if match is None:
        return None
    number = match.group("number")
    start = match.start("number")
    if scope == "chapter" and "." in number:
        head, _, _tail = number.rpartition(".")
        counter_start = start + len(head) + 1
        prefix = text[:counter_start]
        counter = text[counter_start : start + len(number)]
        after = text[start + len(number) :]
        return prefix, counter, after
    counter_start = start
    return text[:counter_start], number, text[start + len(number) :]


def _ensure_caption_seq(
    paragraph: etree._Element,
    *,
    label: str,
    scope: str,
) -> bool:
    """Ganti angka urutan caption dengan field ``SEQ`` bila belum ada."""

    if iter_fields_in_paragraph(paragraph):
        return False
    if paragraph.find(f".//{W_HYPERLINK}") is not None:
        return False

    text = paragraph_text(paragraph)
    parts = _caption_prefix(text, label, scope)
    if parts is None:
        return False
    before, counter, after = parts

    runs = list(paragraph.findall(W_R))
    template_rpr = runs[0].find(W_RPR) if runs else None
    remove_direct_children(paragraph, W_R)

    switches = ["SEQ", label, "\\*", "ARABIC"]
    if scope == "chapter":
        switches.extend(("\\s", "1"))

    paragraph.append(build_run(text=before, rpr=template_rpr))
    insert_field(
        switches,
        FieldPosition(paragraph=paragraph, rpr=template_rpr),
        counter,
    )
    if after:
        paragraph.append(build_run(text=after, rpr=template_rpr))
    return True


def _ensure_caption_seq_fields(
    package: DocumentPackage,
    labels: dict[str, str],
    scope: str,
) -> int:
    count = 0
    for paragraph in iter_paragraphs(_body(package)):
        if is_caption_paragraph(paragraph, CaptionKind.TABLE):
            if _ensure_caption_seq(
                paragraph,
                label=labels["table"],
                scope=scope,
            ):
                count += 1
            continue
        if is_caption_paragraph(paragraph, CaptionKind.FIGURE) and _ensure_caption_seq(
            paragraph,
            label=labels["figure"],
            scope=scope,
        ):
            count += 1
    return count


def _insert_list_fields(
    package: DocumentPackage,
    requests: Sequence[tuple[str, str]],
    labels: dict[str, str],
) -> int:
    """Tulis semua field daftar tanpa menghapus TOC utama yang sudah ada."""

    body = _body(package)
    for sdt in _list_toc_sdts(body):
        parent = sdt.getparent()
        if parent is not None:
            parent.remove(sdt)

    next_id = _next_sdt_id(body)
    for index, (key, title) in enumerate(requests):
        caption_label = labels["table" if key == "tables" else "figure"]
        field = insert_toc(
            package,
            title=title,
            caption=caption_label,
            keep_existing=True,
        )
        _set_sdt_id(_sdt_ancestor(field.begin), next_id + index)

    ensure_no_blank_page_after_toc(package)
    return len(requests)


class ListsStage(BaseStage):
    """Tulis daftar tabel/gambar dan field ``SEQ`` pada caption."""

    name = StageName.LISTS
    # stage-api v0.12: page_numbers (140) -> lists (150) -> office (160).
    order = 150
    requires = canonical_prefix(StageName.LISTS)
    mutates = frozenset({DOCUMENT_PART})
    idempotent = True

    def enabled(self, ctx: object) -> bool:
        if getattr(ctx, "dry_run", False):
            return False
        return bool(_list_requests(getattr(ctx, "structure", None)))

    def run(self, ctx: object) -> StageResult:
        """Tulis field daftar tabel/gambar dan field ``SEQ`` pada caption.

        Mengembalikan ``StageResult`` dengan jumlah field yang dibuat. Melempar
        ``StageError`` bila package belum tersedia atau ``FieldError`` terjadi.
        """

        started = time.monotonic()
        if not self.enabled(ctx):
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                warnings=(
                    "Tidak ada daftar tabel/gambar di structure.front_matter atau build dry-run.",
                ),
            )
        requests = _list_requests(getattr(ctx, "structure", None))
        package = getattr(ctx, "package", None)
        if package is None:
            raise StageError(
                self.name.value,
                "package DOCX belum tersedia; stage lists membutuhkan hasil Pandoc.",
                code="STAGE-PACKAGE",
            )

        before = sha256_c14n(package.xml(DOCUMENT_PART))
        labels, scope = _caption_settings(getattr(ctx, "format", None))
        try:
            seq_fields = _ensure_caption_seq_fields(package, labels, scope)
            list_fields = _insert_list_fields(package, requests, labels)
        except FieldError as exc:
            raise StageError(
                self.name.value,
                str(exc),
                cause=exc,
                code=exc.code,
            ) from exc
        changed = sha256_c14n(package.xml(DOCUMENT_PART)) != before
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "list_fields": list_fields,
                "seq_fields": seq_fields,
            },
        )


__all__ = [
    "CAPTION_LABEL_DEFAULTS",
    "LIST_TITLES",
    "ListsStage",
    "_list_requests",
]
