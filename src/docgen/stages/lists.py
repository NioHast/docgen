r"""Stage ``lists``: daftar tabel/gambar native dan field ``SEQ`` caption.

Spike WS11 (Microsoft Word 16.0, Windows) menunjukkan:

- ``STYLEREF 1 \\s`` menghasilkan ``0`` karena heading pipeline memakai nomor
  literal (``BAB II``), bukan ``w:numPr``.
- ``STYLEREF "Heading 1"`` menghasilkan seluruh teks heading (``BAB II``).
- Varian yang benar adalah hybrid: prefix bab Arab literal dari caption WS4
  (``Tabel 2.``) + ``SEQ Tabel \\* ARABIC \\s 1``; Word menampilkan
  ``Tabel 2.1`` dan mengisi ``TOC \\c "Tabel"``.

Stage ini tidak menulis caption dari nol. Caption dan nomor bab sudah dibuat
oleh stage ``captions`` (WS4); stage ini mengganti angka urutan
terakhir menjadi field ``SEQ`` agar Word dapat memperbarui daftar. Semua field
daftar ditulis lewat :mod:`docgen.docx.fields`.
"""

import re
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from lxml import etree

from ..docx.captions import CaptionKind, is_caption_paragraph
from ..docx.fields import (
    FieldError,
    ensure_no_blank_page_after_toc,
    insert_seq,
    insert_toc,
    iter_fields_in_paragraph,
)
from ..docx.names import (
    W_HYPERLINK,
    W_INSTRTEXT,
    W_R,
    W_RPR,
    W_SDT,
    W_T,
    W_VAL,
)
from ..docx.package import DOCUMENT_PART
from ..docx.paragraphs import ParagraphError, document_body, paragraph_text
from ..docx.runs import build_run, copy_rpr
from ..docx.xml import (
    iter_paragraphs,
    qn,
    sha256_c14n,
)
from ..errors import StageError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

if TYPE_CHECKING:  # pragma: no cover - hanya anotasi
    from ..docx.package import DocumentPackage

TOC_GALLERY = "Table of Contents"
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


def _sdt_gallery(sdt: etree._Element) -> str | None:
    properties = sdt.find(qn("w:sdtPr"))
    if properties is None:
        return None
    gallery = properties.find(".//" + qn("w:docPartGallery"))
    if gallery is None:
        return None
    return gallery.get(qn("w:val"))


def _sdt_instruction(sdt: etree._Element) -> str:
    return "".join(node.text or "" for node in sdt.iter(W_INSTRTEXT) if isinstance(node.tag, str))


def _is_list_sdt(sdt: etree._Element) -> bool:
    return _LIST_INSTRUCTION_RE.search(_sdt_instruction(sdt)) is not None


def _body_toc_sdts(body: etree._Element) -> tuple[etree._Element, ...]:
    return tuple(
        child
        for child in body
        if isinstance(child.tag, str) and child.tag == W_SDT and _sdt_gallery(child) == TOC_GALLERY
    )


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


def _run_of(element: etree._Element) -> etree._Element:
    """Kembalikan run pemilik elemen field.

    ``insert_seq`` mengembalikan ``Field`` yang menunjuk run, sedangkan
    parser :func:`iter_fields` menunjuk ``w:fldChar``. Keduanya didukung.
    """

    if element.tag == W_R:
        return element
    parent = element.getparent()
    if parent is None:
        raise FieldError("Elemen field tidak memiliki run induk")
    return parent


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
    package: DocumentPackage,
    paragraph: etree._Element,
    *,
    label: str,
    scope: str,
) -> bool:
    """Ganti angka urutan caption dengan field ``SEQ`` bila belum ada."""

    existing = iter_fields_in_paragraph(paragraph)
    if existing:
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
    for run in runs:
        paragraph.remove(run)

    instruction = f" SEQ {label} \\* ARABIC"
    if scope == "chapter":
        instruction += " \\s 1"
    field = insert_seq(package, paragraph=paragraph, label=label)
    for node in paragraph.findall(".//" + W_INSTRTEXT):
        node.text = instruction + " "

    separate_run = _run_of(field.separate) if field.separate is not None else None
    result_run = separate_run.getnext() if separate_run is not None else None
    if result_run is not None:
        result_text = result_run.find(W_T)
        if result_text is None:
            result_text = etree.SubElement(result_run, W_T)
        result_text.text = counter
        if counter != counter.strip():
            result_text.set(qn("xml:space"), "preserve")
        for extra in result_run.findall(W_T)[1:]:
            extra.text = ""

    begin_run = _run_of(field.begin)
    end_run = _run_of(field.end)

    before_run = build_run(text=before, rpr=template_rpr)
    begin_run.addprevious(before_run)
    if after:
        end_run.addnext(build_run(text=after, rpr=template_rpr))

    for run in (
        before_run,
        begin_run,
        begin_run.getnext(),
        separate_run,
        result_run,
        end_run,
    ):
        if run is not None and template_rpr is not None and run.find(W_RPR) is None:
            run.insert(0, copy_rpr(template_rpr))
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
                package,
                paragraph,
                label=labels["table"],
                scope=scope,
            ):
                count += 1
            continue
        if is_caption_paragraph(paragraph, CaptionKind.FIGURE) and _ensure_caption_seq(
            package,
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
    toc_sdts = list(_body_toc_sdts(body))
    main_sdts = [sdt for sdt in toc_sdts if not _is_list_sdt(sdt)]
    for sdt in toc_sdts:
        parent = sdt.getparent()
        if parent is not None:
            parent.remove(sdt)

    next_id = _next_sdt_id(body)
    created: list[etree._Element] = []
    last: etree._Element | None = None
    for index, (key, title) in enumerate(requests):
        caption_label = labels["table" if key == "tables" else "figure"]
        field = insert_toc(package, title=title, caption=caption_label)
        sdt = _sdt_ancestor(field.begin)
        _set_sdt_id(sdt, next_id + index)
        if index < len(requests) - 1:
            parent = sdt.getparent()
            if parent is not None:
                parent.remove(sdt)
            created.append(sdt)
        else:
            last = sdt

    if last is None:  # pragma: no cover - dijaga oleh caller
        raise FieldError("Tidak ada field daftar yang dibuat")

    for sdt in created:
        last.addprevious(sdt)
    anchor = created[0] if created else last
    for sdt in main_sdts:
        anchor.addprevious(sdt)

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
    "TOC_GALLERY",
    "ListsStage",
    "_list_requests",
]
