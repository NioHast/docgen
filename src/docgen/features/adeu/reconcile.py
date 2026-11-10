"""Rekonsiliasi edit manual DOCX terhadap manifest Adeu dan Markdown.

Alat ini hanya membaca DOCX, manifest, dan ``document.md``. Satu-satunya
berkas yang ditulis adalah laporan Markdown. Exit code mengikuti kontrak stage:

- ``0`` tidak ada perubahan;
- ``3`` ada perubahan manual yang perlu ditinjau;
- ``4`` ada pelanggaran paragraf terlindungi;
- ``1`` error input.
"""

import argparse
import contextlib
import os
import re
import sys
import tempfile
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from lxml import etree

from ...document import parse_document
from ...docx import DOCUMENT_PART, DocxError
from ...docx.names import (
    W_BODY,
    W_BOOKMARK_END,
    W_BOOKMARK_START,
    W_BR,
    W_CR,
    W_DEL,
    W_DRAWING,
    W_ID,
    W_INSTRTEXT,
    W_MOVEFROM,
    W_NAME,
    W_NO_BREAK_HYPHEN,
    W_OBJECT,
    W_P,
    W_PICT,
    W_PPR,
    W_PTAB,
    W_T,
    W_TAB,
    W_TXBXCONTENT,
    W,
)
from ...docx.package import DocumentPackage
from ...errors import DocgenError, ReconcileError
from ...markdown.blocks import (
    MarkdownBlock,
    normalize_for_match,
    normalize_heading,
    normalize_path,
    parse_markdown_blocks,
)
from .manifest import (
    ManifestParagraph,
    default_manifest_path,
    load_manifest,
)

W_SOFT_HYPHEN = W + "softHyphen"
BOOKMARK_RE = re.compile(r"^p\d{4,}$")
SIMILARITY_THRESHOLD = 0.35
_REPORT_NAME_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass(frozen=True)
class DocxSnapshot:
    """Teks paragraf ber-bookmark, urutan bookmark, dan paragraf tanpa ID."""

    bookmarks: dict[str, str]
    order: tuple[str, ...]
    unbookmarked: tuple[str, ...]


@dataclass(frozen=True)
class SourceMatch:
    """Blok Markdown yang dianggap sumber sebuah paragraf."""

    block: MarkdownBlock
    similarity: float
    display_path: str


@dataclass(frozen=True)
class ReconcileResult:
    """Hasil rekonsiliasi beserta exit code kontrak."""

    report: str
    exit_code: int
    checked: int
    changed: int
    violations: int
    report_path: Path | None = None


@dataclass
class _OpenBookmark:
    name: str
    chunks: list[str]


def _clean_visible(text: str) -> str:
    """Normalisasi aman untuk perbandingan dan tampilan laporan."""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2011", "-")
    return text.strip()


# ---------------------------------------------------------------------------
# Ekstraksi DOCX
# ---------------------------------------------------------------------------


def _visible_text(element: etree._Element) -> str:
    """Teks yang terlihat pada state accepted Track Changes."""

    tag = element.tag
    if tag in (
        W_P,
        W_PPR,
        W_DEL,
        W_MOVEFROM,
        W_INSTRTEXT,
        W_DRAWING,
        W_PICT,
        W_OBJECT,
        W_TXBXCONTENT,
    ):
        return ""
    if tag == W_T:
        return element.text or ""
    if tag in (W_TAB, W_PTAB):
        return "\t"
    if tag in (W_BR, W_CR):
        return "\n"
    if tag == W_NO_BREAK_HYPHEN:
        return "\u2011"
    if tag == W_SOFT_HYPHEN:
        return ""
    return "".join(_visible_text(child) for child in element)


def _outer_paragraphs(container: etree._Element) -> list[etree._Element]:
    """Paragraf dalam container, tanpa paragraf yang bersarang di paragraf."""

    result: list[etree._Element] = []
    for paragraph in container.iter(W_P):
        parent = paragraph.getparent()
        nested = False
        while parent is not None and parent is not container:
            if parent.tag == W_P:
                nested = True
                break
            parent = parent.getparent()
        if not nested:
            result.append(paragraph)
    return result


def _walk_nested_paragraphs(
    container: etree._Element,
    closed: list[tuple[str, str]],
    unbookmarked: list[str],
    started: list[str],
) -> None:
    for paragraph in _outer_paragraphs(container):
        _walk_xml(paragraph, {}, closed, unbookmarked, started)


def _paragraph_visible_text(paragraph: etree._Element) -> str:
    parts: list[str] = []
    for child in paragraph:
        if child.tag in (W_P, W_PPR, W_DRAWING, W_PICT, W_OBJECT, W_TXBXCONTENT):
            continue
        parts.append(_visible_text(child))
    return "".join(parts)


def _has_bookmark_start(element: etree._Element) -> bool:
    for candidate in element.iter(W_BOOKMARK_START):
        name = candidate.get(W_NAME)
        if name and BOOKMARK_RE.fullmatch(name):
            return True
    return False


def _walk_xml(
    element: etree._Element,
    active: dict[str, _OpenBookmark],
    closed: list[tuple[str, str]],
    unbookmarked: list[str],
    started: list[str],
) -> None:
    tag = element.tag

    if tag in (W_DEL, W_MOVEFROM):
        return

    if tag == W_BOOKMARK_START:
        name = element.get(W_NAME)
        if name and BOOKMARK_RE.fullmatch(name):
            bookmark_id = element.get(W_ID)
            if bookmark_id is None:
                raise ReconcileError(f"bookmark {name} tidak memiliki w:id")
            if bookmark_id in active:
                raise ReconcileError(f"bookmark id ganda di DOCX: {bookmark_id}")
            active[bookmark_id] = _OpenBookmark(name=name, chunks=[])
            started.append(name)
        return

    if tag == W_BOOKMARK_END:
        bookmark_id = element.get(W_ID)
        if bookmark_id in active:
            bookmark = active.pop(bookmark_id)
            closed.append((bookmark.name, "".join(bookmark.chunks)))
        return

    if tag == W_P:
        covered = bool(active) or _has_bookmark_start(element)

        for child in element:
            _walk_xml(child, active, closed, unbookmarked, started)

        if active:
            for bookmark in active.values():
                bookmark.chunks.append("\n")

        if not covered:
            text = _clean_visible(_paragraph_visible_text(element))
            if text:
                unbookmarked.append(text)
        return

    if tag == W_T:
        text = element.text or ""
        if text:
            for bookmark in active.values():
                bookmark.chunks.append(text)
        return

    if tag in (W_TAB, W_PTAB):
        for bookmark in active.values():
            bookmark.chunks.append("\t")
        return

    if tag in (W_BR, W_CR):
        for bookmark in active.values():
            bookmark.chunks.append("\n")
        return

    if tag == W_NO_BREAK_HYPHEN:
        for bookmark in active.values():
            bookmark.chunks.append("\u2011")
        return

    if tag == W_SOFT_HYPHEN:
        return

    if tag in (W_DRAWING, W_PICT, W_OBJECT, W_TXBXCONTENT):
        _walk_nested_paragraphs(element, closed, unbookmarked, started)
        return

    for child in element:
        _walk_xml(child, active, closed, unbookmarked, started)


def extract_bookmarks(docx_path: str | Path) -> DocxSnapshot:
    """Ekstrak teks untuk setiap bookmark ``pNNNN`` dari body DOCX."""

    path = Path(docx_path)
    try:
        package = DocumentPackage.load(path)
        root = package.xml(DOCUMENT_PART)
    except (DocxError, OSError) as exc:
        raise ReconcileError(
            f"DOCX tidak dapat dibaca: {path}: {exc}",
            code="RECONCILE-DOCX",
            path=path,
        ) from exc

    body = root.find(W_BODY)
    if body is None:
        raise ReconcileError(
            f"DOCX tidak memiliki w:body: {path}",
            code="RECONCILE-DOCX",
            path=path,
        )

    active: dict[str, _OpenBookmark] = {}
    closed: list[tuple[str, str]] = []
    unbookmarked: list[str] = []
    started: list[str] = []
    _walk_xml(body, active, closed, unbookmarked, started)

    if active:
        names = ", ".join(sorted(bookmark.name for bookmark in active.values()))
        raise ReconcileError(
            f"bookmark tidak ditutup di DOCX: {names}",
            code="RECONCILE-BOOKMARK",
            path=path,
        )

    closed_text: dict[str, str] = {}
    for name, text in closed:
        if name in closed_text:
            raise ReconcileError(
                f"bookmark duplikat di DOCX: {name}",
                code="RECONCILE-BOOKMARK",
                path=path,
            )
        closed_text[name] = _clean_visible(text)

    bookmarks: dict[str, str] = {}
    order: list[str] = []
    for name in started:
        if name in bookmarks:
            raise ReconcileError(
                f"bookmark duplikat di DOCX: {name}",
                code="RECONCILE-BOOKMARK",
                path=path,
            )
        if name not in closed_text:
            raise ReconcileError(
                f"bookmark tidak ditutup di DOCX: {name}",
                code="RECONCILE-BOOKMARK",
                path=path,
            )
        bookmarks[name] = closed_text[name]
        order.append(name)

    return DocxSnapshot(
        bookmarks=bookmarks,
        order=tuple(order),
        unbookmarked=tuple(unbookmarked),
    )


# ---------------------------------------------------------------------------
# Pencarian sumber Markdown
# ---------------------------------------------------------------------------


def find_source(
    paragraph: ManifestParagraph,
    blocks: Sequence[MarkdownBlock],
    source_root: Path,
) -> SourceMatch | None:
    """Cari blok Markdown sumber berdasarkan heading_path lalu difflib."""

    wanted_path = normalize_path(paragraph.heading_path)
    if not wanted_path:
        return None

    candidates = [block for block in blocks if block.heading_path == wanted_path]
    if not candidates:
        candidates = [
            block
            for block in blocks
            if len(block.heading_path) >= len(wanted_path)
            and block.heading_path[-len(wanted_path) :] == wanted_path
        ]
    if not candidates:
        candidates = [
            block
            for block in blocks
            if len(wanted_path) >= len(block.heading_path)
            and wanted_path[-len(block.heading_path) :] == block.heading_path
        ]
    if not candidates:
        return None

    if paragraph.kind == "heading":
        target = normalize_heading(paragraph.text)
    else:
        target = normalize_for_match(paragraph.text)
    scored: list[tuple[float, MarkdownBlock]] = []
    for block in candidates:
        if paragraph.kind == "heading":
            candidate_text = normalize_heading(block.text)
        else:
            candidate_text = normalize_for_match(block.text)
        ratio = SequenceMatcher(None, target, candidate_text, autojunk=False).ratio()
        scored.append((ratio, block))

    best_ratio, best_block = max(scored, key=lambda item: (item[0], -item[1].index))
    if best_ratio < SIMILARITY_THRESHOLD:
        return None

    try:
        relative = best_block.path.resolve().relative_to(source_root.resolve())
        display_path = relative.as_posix()
    except OSError, ValueError:
        display_path = best_block.path.as_posix()

    return SourceMatch(
        block=best_block,
        similarity=best_ratio,
        display_path=display_path,
    )


# ---------------------------------------------------------------------------
# Laporan
# ---------------------------------------------------------------------------


def _quote(text: str) -> str:
    value = _clean_visible(text)
    if not value:
        return ">"
    return "\n".join(f"> {line}" if line else ">" for line in value.split("\n"))


def _heading_label(paragraph: ManifestParagraph) -> str:
    if not paragraph.heading_path:
        return paragraph.kind
    parts = (re.sub(r"\s+", " ", part).strip() for part in paragraph.heading_path)
    return " / ".join(part for part in parts if part) or paragraph.kind


def _protected_label(paragraph: ManifestParagraph) -> str:
    if paragraph.protected_reason:
        return f"{paragraph.kind} (protected: {paragraph.protected_reason})"
    return f"{paragraph.kind} (protected)"


def _change_section(
    paragraph: ManifestParagraph,
    before: str,
    after: str,
    source: SourceMatch | None,
) -> list[str]:
    if paragraph.protected:
        return [
            f"## PELANGGARAN {paragraph.id} — {_protected_label(paragraph)}",
            "",
            "**Sebelum**",
            _quote(before),
            "",
            "**Sesudah**",
            _quote(after),
            "",
            "> Blok ini tidak boleh diedit manual. Kembalikan dari build.",
        ]

    lines = [f"## {paragraph.id} — {_heading_label(paragraph)}", ""]
    if source is not None:
        lines.append(
            f"Sumber: {source.display_path} "
            f"(blok {source.block.index}, kemiripan {source.similarity:.2f})"
        )
    else:
        lines.append(
            "**SUMBER TIDAK DITEMUKAN** — tidak ada blok Markdown yang cocok "
            "dengan heading_path dan teks lama."
        )
    lines.extend(
        [
            "",
            "**Sebelum**",
            _quote(before),
            "",
            "**Sesudah**",
            _quote(after),
            "",
            "**Saran:** terapkan ke Markdown lalu build ulang.",
        ]
    )
    return lines


def _new_bookmark_section(paragraph_id: str, text: str) -> list[str]:
    return [
        f"## PARAGRAF BARU {paragraph_id}",
        "",
        "ID ini ada di DOCX tetapi tidak ada di manifest.",
        "",
        "**Sesudah**",
        _quote(text),
    ]


def _new_unbookmarked_section(text: str) -> list[str]:
    return [
        "## PARAGRAF BARU — tanpa ID",
        "",
        "Paragraf ini tidak berada di dalam bookmark pNNNN mana pun.",
        "",
        "**Sesudah**",
        _quote(text),
    ]


def _missing_section(paragraph: ManifestParagraph) -> list[str]:
    label = _heading_label(paragraph)
    if paragraph.protected:
        return [
            f"## PELANGGARAN {paragraph.id} — {_protected_label(paragraph)}",
            "",
            "**PARAGRAF HILANG** — ID ini ada di manifest tetapi tidak ditemukan di DOCX.",
            "",
            "**Sebelum**",
            _quote(paragraph.text),
            "",
            "> Blok terlindungi ini hilang dari DOCX. Kembalikan dari build.",
        ]
    return [
        f"## PARAGRAF HILANG {paragraph.id} — {label}",
        "",
        "ID ini ada di manifest tetapi tidak ditemukan di DOCX.",
        "",
        "**Sebelum**",
        _quote(paragraph.text),
    ]


def build_report(
    snapshot: DocxSnapshot,
    paragraphs: Sequence[ManifestParagraph],
    blocks: Sequence[MarkdownBlock],
    source_root: Path,
) -> ReconcileResult:
    """Susun laporan dan tentukan exit code kontrak."""

    manifest_by_id = {paragraph.id: paragraph for paragraph in paragraphs}
    docx_ids = set(snapshot.bookmarks)

    changed_paragraphs: list[tuple[ManifestParagraph, str, str]] = []
    for paragraph in paragraphs:
        if paragraph.id not in snapshot.bookmarks:
            continue
        current = snapshot.bookmarks[paragraph.id]
        if _clean_visible(paragraph.text) != _clean_visible(current):
            changed_paragraphs.append((paragraph, paragraph.text, current))

    protected_changes = [item for item in changed_paragraphs if item[0].protected]
    missing_paragraphs = [paragraph for paragraph in paragraphs if paragraph.id not in docx_ids]
    protected_missing = [paragraph for paragraph in missing_paragraphs if paragraph.protected]
    new_ids = [bookmark_id for bookmark_id in snapshot.order if bookmark_id not in manifest_by_id]

    sections: list[list[str]] = []

    for paragraph, before, after in changed_paragraphs:
        source = None
        if not paragraph.protected:
            source = find_source(paragraph, blocks, source_root)
        sections.append(_change_section(paragraph, before, after, source))

    for bookmark_id in new_ids:
        sections.append(_new_bookmark_section(bookmark_id, snapshot.bookmarks[bookmark_id]))

    for text in snapshot.unbookmarked:
        sections.append(_new_unbookmarked_section(text))

    for paragraph in missing_paragraphs:
        sections.append(_missing_section(paragraph))

    violations = len(protected_changes) + len(protected_missing)
    changed_count = len(changed_paragraphs)

    lines = [
        "# Edit Manual",
        "",
        "## Ringkasan",
        f"- Diperiksa: {len(paragraphs)} paragraf",
        f"- Berubah: {changed_count}",
        f"- Dilindungi & dilanggar: {violations}",
    ]

    for position, section in enumerate(sections):
        lines.append("")
        if position:
            lines.append("---")
            lines.append("")
        lines.extend(section)

    report = "\n".join(lines).rstrip("\n") + "\n"

    if violations:
        exit_code = 4
    elif changed_count or new_ids or snapshot.unbookmarked or missing_paragraphs:
        exit_code = 3
    else:
        exit_code = 0

    return ReconcileResult(
        report=report,
        exit_code=exit_code,
        checked=len(paragraphs),
        changed=changed_count,
        violations=violations,
    )


def write_report(path: str | Path, report: str) -> Path:
    """Tulis laporan secara atomic dengan akhir baris LF."""

    destination = Path(path)
    payload = report.encode("utf-8")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
            os.replace(temp_name, destination)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)
            raise
    except OSError as exc:
        raise ReconcileError(
            f"laporan tidak dapat ditulis ke {destination}: {exc}",
            code="RECONCILE-WRITE",
            path=destination,
        ) from exc
    return destination


def _report_name(front_matter) -> str:
    value = front_matter.get("report_name") if front_matter is not None else None
    if not isinstance(value, str):
        return "Tugas"
    text = value.strip()
    if not text or text in {".", ".."} or _REPORT_NAME_FORBIDDEN.search(text):
        return "Tugas"
    return text


def _default_docx_path(document_file: Path, report_name: str) -> Path:
    """DOCX hasil build: ``out/<report_name>.docx`` lalu di samping dokumen."""

    built = document_file.parent / "out" / f"{report_name}.docx"
    if built.is_file():
        return built
    return document_file.parent / f"{report_name}.docx"


def run(
    document_path: str | Path,
    *,
    docx_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    out_path: str | Path | None = None,
) -> ReconcileResult:
    """Jalankan rekonsiliasi lengkap dan tulis laporan Markdown."""

    raw = parse_document(document_path)
    document_file = raw.path
    report_name = _report_name(raw.front_matter)
    docx = (
        Path(docx_path) if docx_path is not None else _default_docx_path(document_file, report_name)
    )
    manifest_file = (
        Path(manifest_path) if manifest_path is not None else default_manifest_path(document_file)
    )
    out = (
        Path(out_path)
        if out_path is not None
        else document_file.parent / ".laporan" / "reconcile.md"
    )

    try:
        out_resolved = out.resolve()
        docx_resolved = docx.resolve()
        manifest_resolved = manifest_file.resolve()
        document_resolved = document_file.resolve()
    except OSError as exc:
        raise ReconcileError(
            f"path tidak dapat diselesaikan: {exc}",
            code="RECONCILE-PATH",
        ) from exc

    if out_resolved in (docx_resolved, manifest_resolved, document_resolved):
        raise ReconcileError(
            "--out tidak boleh menimpa document.md, --docx, atau --manifest",
            code="RECONCILE-OUTPUT",
            path=out,
        )
    if out.suffix.lower() != ".md":
        raise ReconcileError(
            "--out harus berekstensi .md; gunakan .laporan/reconcile.md",
            code="RECONCILE-OUTPUT",
            path=out,
        )

    paragraphs = load_manifest(manifest_file).paragraphs
    snapshot = extract_bookmarks(docx)
    blocks = parse_markdown_blocks(raw.body, document_file)
    result = build_report(snapshot, paragraphs, blocks, document_file.parent)
    report_path = write_report(out, result.report)
    return ReconcileResult(
        report=result.report,
        exit_code=result.exit_code,
        checked=result.checked,
        changed=result.changed,
        violations=result.violations,
        report_path=report_path,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("document", help="Berkas document.md.")
    parser.add_argument("--docx", type=Path, help="DOCX hasil edit.")
    parser.add_argument("--manifest", type=Path, help="manifest.json hasil build.")
    parser.add_argument("--out", type=Path, help="Laporan Markdown hasil.")


def command(args: argparse.Namespace) -> int:
    result = run(
        args.document,
        docx_path=args.docx,
        manifest_path=args.manifest,
        out_path=args.out,
    )
    print(
        f"Diperiksa {result.checked} paragraf; berubah {result.changed}; "
        f"pelanggaran {result.violations}. Laporan: {result.report_path}"
    )
    return result.exit_code


def build_parser(prog: str = "docgen reconcile") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Rekonsiliasi edit manual DOCX dengan manifest Adeu dan "
            "document.md. Hanya menulis laporan, tidak mengubah sumber."
        ),
    )
    configure_parser(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return command(args)
    except DocgenError as exc:
        print(f"[ERROR] {exc.format()}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("[ERROR] Dibatalkan oleh pengguna.", file=sys.stderr)
        return 130


__all__ = [
    "DocxSnapshot",
    "MarkdownBlock",
    "ReconcileResult",
    "SourceMatch",
    "build_parser",
    "build_report",
    "command",
    "configure_parser",
    "extract_bookmarks",
    "find_source",
    "main",
    "run",
    "write_report",
]
