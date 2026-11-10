"""Injeksi ID paragraf Adeu dan penyusunan manifest.

Modul ini adalah port ``tools/add_paragraph_ids.py`` ke atas API
``docgen.docx`` dan parser Markdown bersama. Bookmark ``pNNNN`` ditangani
``docgen.docx.bookmarks``; modul ini hanya menambahkan klasifikasi, proteksi,
pencocokan sumber, dan manifest deterministik.
"""

import argparse
import re
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from ...docx import DOCUMENT_PART
from ...docx import bookmarks as bookmark_mod
from ...docx.names import (
    W_BODY,
    W_FLDCHAR,
    W_FLDCHARTYPE,
    W_FLDSIMPLE,
    W_INSTR,
    W_INSTRTEXT,
    W_P,
    W_PPR,
    W_SECTPR,
    W_TXBXCONTENT,
)
from ...docx.package import DocumentPackage
from ...docx.xml import paragraph_text
from ...errors import DocgenError
from ...markdown.blocks import (
    iter_candidate_texts,
    load_markdown_directory,
    normalize_for_match,
    normalize_heading,
    normalize_path,
)
from .manifest import (
    MANIFEST_VERSION,
    Manifest,
    ManifestParagraph,
    default_manifest_path,
    dump_manifest,
    make_paragraph,
)

TOC_FIELD = "TOC"

_PROTECTED_FIELD_ORDER = (
    ("SEQ", "seq_field"),
    ("PAGEREF", "pageref_field"),
    ("PAGE", "page_field"),
)
_FIELD_NAME_RE = re.compile(r"\s*([A-Za-z]+)")
_SOURCE_SCAN_EXCLUDED_DIRS = frozenset({"out", "build", "review"})


def _is_generated_source_dir(part: str) -> bool:
    """Direktori workspace/output yang bukan sumber konten Markdown."""

    return part in _SOURCE_SCAN_EXCLUDED_DIRS or part.startswith(".laporan")


@dataclass(frozen=True)
class AdeuOptions:
    """Saklar Adeu yang dipetakan dari ``--no-manifest``/``--no-adeu``."""

    bookmarks: bool = True
    manifest: bool = True
    source_scan: bool = True

    def __post_init__(self) -> None:
        if self.manifest and not self.bookmarks:
            raise ValueError("manifest membutuhkan bookmark")
        if self.source_scan and not self.manifest:
            raise ValueError("source scan membutuhkan manifest")


def resolve_options(
    *,
    no_manifest: bool = False,
    no_adeu: bool = False,
) -> AdeuOptions:
    """Petakan flag build ke saklar bookmark/manifest/source scan.

    - default: bookmark + manifest + source scan.
    - ``--no-manifest``: bookmark tetap, manifest dan source scan mati.
    - ``--no-adeu``: bookmark, manifest, dan source scan mati.
    """

    if no_adeu:
        return AdeuOptions(bookmarks=False, manifest=False, source_scan=False)
    if no_manifest:
        return AdeuOptions(bookmarks=True, manifest=False, source_scan=False)
    return AdeuOptions(bookmarks=True, manifest=True, source_scan=True)


@dataclass
class _FieldFrame:
    start_index: int
    instruction_parts: list[str]

    def __init__(self, start_index: int) -> None:
        self.start_index = start_index
        self.instruction_parts = []


def _field_name(instruction: str) -> str | None:
    match = _FIELD_NAME_RE.match(instruction)
    return match.group(1).upper() if match is not None else None


def _iter_field_markers(paragraph: etree._Element) -> Iterator[etree._Element]:
    def walk(element: etree._Element) -> Iterator[etree._Element]:
        for child in element:
            tag = child.tag
            if tag in (W_P, W_TXBXCONTENT):
                continue
            if tag in (W_FLDCHAR, W_INSTRTEXT, W_FLDSIMPLE):
                yield child
            yield from walk(child)

    yield from walk(paragraph)


def _scan_fields(
    paragraphs: Sequence[etree._Element],
) -> tuple[set[int], list[set[str]]]:
    """Kembalikan indeks paragraf dalam field TOC dan nama field per paragraf."""

    if not paragraphs:
        return set(), []

    stack: list[_FieldFrame] = []
    spans: list[tuple[str, int, int]] = []
    direct_names: list[set[str]] = [set() for _ in paragraphs]

    for index, paragraph in enumerate(paragraphs):
        for marker in _iter_field_markers(paragraph):
            if marker.tag == W_FLDCHAR:
                field_type = marker.get(W_FLDCHARTYPE)
                if field_type == "begin":
                    stack.append(_FieldFrame(index))
                elif field_type == "end" and stack:
                    frame = stack.pop()
                    name = _field_name("".join(frame.instruction_parts))
                    if name is not None:
                        spans.append((name, frame.start_index, index))
            elif marker.tag == W_INSTRTEXT:
                text = marker.text or ""
                if stack:
                    stack[-1].instruction_parts.append(text)
                name = _field_name(text)
                if name is not None:
                    direct_names[index].add(name)
            elif marker.tag == W_FLDSIMPLE:
                name = _field_name(marker.get(W_INSTR) or "")
                if name is not None:
                    spans.append((name, index, index))
                    direct_names[index].add(name)

    for frame in stack:
        name = _field_name("".join(frame.instruction_parts))
        if name is not None:
            spans.append((name, frame.start_index, len(paragraphs) - 1))

    field_names: list[set[str]] = [set() for _ in paragraphs]
    toc_indices: set[int] = set()
    for name, start, end in spans:
        for index in range(max(start, 0), min(end, len(paragraphs) - 1) + 1):
            field_names[index].add(name)
            if name == TOC_FIELD:
                toc_indices.add(index)
    for index, names in enumerate(direct_names):
        field_names[index].update(names)
        if TOC_FIELD in names:
            toc_indices.add(index)
    return toc_indices, field_names


def _has_sectpr(paragraph: etree._Element) -> bool:
    return paragraph.find(f"{W_PPR}/{W_SECTPR}") is not None or paragraph.find(W_SECTPR) is not None


def _protected_reason(
    kind: str,
    field_names: set[str],
    *,
    in_toc: bool,
    contains_sectpr: bool,
) -> str | None:
    if in_toc or TOC_FIELD in field_names:
        return "toc_field"
    if contains_sectpr:
        return "sectpr"
    for field, reason in _PROTECTED_FIELD_ORDER:
        if field in field_names:
            return reason
    if kind == "caption":
        return "caption_style"
    if kind == "toc":
        return "toc_style"
    if kind == "bibliography":
        return "bibliography"
    if kind == "cover":
        return "cover_style"
    return None


def _body(package: DocumentPackage) -> etree._Element:
    root = package.xml(DOCUMENT_PART)
    body = root.find(W_BODY)
    if body is None:
        raise bookmark_mod.BookmarkError(
            f"{DOCUMENT_PART} tidak memiliki elemen w:body",
            path=DOCUMENT_PART,
        )
    return body


def _body_paragraphs(package: DocumentPackage) -> list[etree._Element]:
    return list(_body(package).iter(W_P))


def analyze_manifest(
    package: DocumentPackage,
    *,
    docx_name: str,
    source_dir: str | Path | None = None,
    source_scan: bool = True,
) -> Manifest:
    """Susun manifest dari bookmark ``pNNNN`` yang sudah ada di package."""

    paragraphs = _body_paragraphs(package)
    expected_names = tuple(f"p{index + 1:04d}" for index in range(len(paragraphs)))
    actual_names = tuple(bookmark.name for bookmark in bookmark_mod.iter_bookmarks(package))
    if actual_names != expected_names:
        raise bookmark_mod.BookmarkError(
            "manifest hanya boleh disusun setelah bookmark pNNNN lengkap; "
            f"ditemukan {len(actual_names)} bookmark untuk {len(paragraphs)} paragraf",
            path=DOCUMENT_PART,
        )
    toc_indices, field_names = _scan_fields(paragraphs)

    heading_state: dict[int, str] = {}
    entries: list[ManifestParagraph] = []
    for index, paragraph in enumerate(paragraphs):
        kind = bookmark_mod.paragraph_kind(paragraph)
        if index in toc_indices:
            kind = "toc"
        text = paragraph_text(paragraph)
        level = bookmark_mod.paragraph_heading_level(paragraph)
        if kind == "heading" and level is not None:
            for existing in list(heading_state):
                if existing >= level:
                    del heading_state[existing]
            heading_state[level] = text
        heading_path = tuple(heading_state[item] for item in sorted(heading_state))
        reason = _protected_reason(
            kind,
            field_names[index],
            in_toc=index in toc_indices,
            contains_sectpr=_has_sectpr(paragraph),
        )
        entries.append(
            make_paragraph(
                id=f"p{index + 1:04d}",
                index=index,
                kind=kind,
                heading_path=heading_path,
                text=text,
                protected=reason is not None,
                protected_reason=reason,
            )
        )

    include_source = source_scan and source_dir is not None
    manifest = Manifest(
        version=MANIFEST_VERSION,
        docx=docx_name,
        paragraphs=tuple(entries),
        include_source=include_source,
    )
    if include_source:
        assert source_dir is not None
        manifest = _attach_sources(manifest, Path(source_dir))
    return manifest


def _attach_sources(manifest: Manifest, source_dir: Path) -> Manifest:
    """Isi ``source_file``/``source_line`` bila pasangan blok unik.

    ``Manifest`` immutable, jadi fungsi ini memutasi daftar entri baru dan
    mengembalikan manifest baru. Pemanggil memakai nilai kembaliannya.
    """

    blocks = load_markdown_directory(source_dir)
    candidates: dict[tuple[tuple[str, ...], str], list[tuple[str, int]]] = {}
    for block in blocks:
        try:
            relative_path = block.path.relative_to(source_dir)
        except ValueError:
            relative_path = block.path
        if any(_is_generated_source_dir(part) for part in relative_path.parts[:-1]):
            # Artefak workspace (front_matter.md/mermaid.md), output, dan
            # laporan review bukan sumber konten dan tidak boleh membuat
            # kandidat duplikat.
            continue
        relative = relative_path.as_posix()
        for candidate in iter_candidate_texts(block):
            if block.kind == "heading":
                normalized = normalize_heading(candidate)
            else:
                normalized = normalize_for_match(candidate)
            if not normalized:
                continue
            key = (block.heading_path, normalized)
            candidates.setdefault(key, []).append((relative, block.line))

    updated: list[ManifestParagraph] = []
    for paragraph in manifest.paragraphs:
        if paragraph.kind == "heading":
            wanted_text = normalize_heading(paragraph.text)
        else:
            wanted_text = normalize_for_match(paragraph.text)
        wanted_path = normalize_path(paragraph.heading_path)
        matches = candidates.get((wanted_path, wanted_text), []) if wanted_text else []
        if len(matches) == 1:
            source_file, source_line = matches[0]
            updated.append(
                ManifestParagraph(
                    id=paragraph.id,
                    index=paragraph.index,
                    kind=paragraph.kind,
                    heading_path=paragraph.heading_path,
                    text=paragraph.text,
                    text_sha256=paragraph.text_sha256,
                    protected=paragraph.protected,
                    protected_reason=paragraph.protected_reason,
                    source_file=source_file,
                    source_line=source_line,
                )
            )
        else:
            updated.append(paragraph)
    return Manifest(
        version=manifest.version,
        docx=manifest.docx,
        paragraphs=tuple(updated),
        include_source=manifest.include_source,
    )


def prepare_manifest(
    package: DocumentPackage,
    *,
    docx_name: str,
    options: AdeuOptions | None = None,
    source_dir: str | Path | None = None,
) -> Manifest | None:
    """Hook build: tambah bookmark lalu siapkan manifest di memori.

    Manifest tidak ditulis di sini karena kontrak menulisnya setelah package
    disimpan. Kembalian ``None`` berarti manifest dimatikan.
    """

    resolved = options or AdeuOptions()
    if not resolved.bookmarks:
        # Pastikan DOCX yang sudah pernah diberi ID tidak membawa bookmark
        # Adeu saat fitur dimatikan.
        bookmark_mod.remove_paragraph_bookmarks(package)
        return None
    bookmark_mod.add_paragraph_ids(package)
    if not resolved.manifest:
        return None
    return analyze_manifest(
        package,
        docx_name=docx_name,
        source_dir=source_dir if resolved.source_scan else None,
        source_scan=resolved.source_scan,
    )


def write_prepared_manifest(
    manifest: Manifest | None,
    document_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> Path | None:
    """Tulis manifest setelah package disimpan.

    Default lokasi adalah ``<document.parent>/.laporan/manifest.json``.
    Kembalian ``None`` berarti manifest dimatikan (``--no-manifest`` /
    ``--no-adeu``) atau tidak ada manifest yang disiapkan.
    """

    if manifest is None:
        return None
    destination = (
        Path(manifest_path) if manifest_path is not None else default_manifest_path(document_path)
    )
    return dump_manifest(manifest, destination)


def add_paragraph_ids(
    docx_path: str | Path,
    out_docx: str | Path,
    manifest_path: str | Path | None = None,
    source_dir: str | Path | None = None,
    docx_name: str | None = None,
    *,
    options: AdeuOptions | None = None,
) -> Manifest | None:
    """Port API lama: baca DOCX, injeksi ID, simpan DOCX, tulis manifest."""

    resolved = options or AdeuOptions()
    input_path = Path(docx_path)
    output_path = Path(out_docx)
    package = DocumentPackage.load(input_path)
    prepared = prepare_manifest(
        package,
        docx_name=docx_name if docx_name is not None else output_path.name,
        options=resolved,
        source_dir=source_dir,
    )
    package.save(output_path)
    if prepared is not None and resolved.manifest:
        destination = (
            Path(manifest_path) if manifest_path is not None else default_manifest_path(output_path)
        )
        dump_manifest(prepared, destination)
    return prepared


def run_docx(
    docx_path: str | Path,
    out_docx: str | Path,
    manifest_path: str | Path | None = None,
    source_dir: str | Path | None = None,
    docx_name: str | None = None,
    *,
    options: AdeuOptions | None = None,
) -> Manifest | None:
    """Alias eksplisit untuk ``add_paragraph_ids``."""

    return add_paragraph_ids(
        docx_path,
        out_docx,
        manifest_path,
        source_dir,
        docx_name,
        options=options,
    )


def _summary(manifest: Manifest) -> str:
    kinds = Counter(paragraph.kind for paragraph in manifest.paragraphs)
    protected = sum(1 for paragraph in manifest.paragraphs if paragraph.protected)
    ids = [paragraph.id for paragraph in manifest.paragraphs]
    id_range = f"{ids[0]}..{ids[-1]}" if ids else "-"
    kind_text = ", ".join(f"{name}={count}" for name, count in sorted(kinds.items()))
    return (
        f"Paragraf body: {len(manifest.paragraphs)} ({kind_text})\n"
        f"Protected: {protected}\n"
        f"Bookmark: {id_range}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docgen-adeu-add",
        description=(
            "Injeksi bookmark pNNNN ke setiap paragraf body DOCX dan tulis manifest JSON Adeu."
        ),
    )
    parser.add_argument("docx", type=Path, help="file DOCX input")
    parser.add_argument(
        "--out-docx",
        type=Path,
        required=True,
        help="lokasi DOCX hasil",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="lokasi manifest JSON (default: .laporan/manifest.json)",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="direktori Markdown untuk mengisi source_file/source_line",
    )
    parser.add_argument(
        "--docx-name",
        help="nama DOCX yang dicatat di manifest (default: nama --out-docx)",
    )
    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="matikan manifest dan source scan; bookmark tetap ditambahkan",
    )
    parser.add_argument(
        "--no-adeu",
        action="store_true",
        help="matikan bookmark, manifest, dan source scan",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    options = resolve_options(
        no_manifest=args.no_manifest,
        no_adeu=args.no_adeu,
    )
    try:
        manifest = add_paragraph_ids(
            args.docx,
            args.out_docx,
            args.manifest,
            args.source_dir,
            args.docx_name,
            options=options,
        )
    except (DocgenError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if manifest is None:
        print("Manifest dimatikan.")
    else:
        print(_summary(manifest))
        destination = (
            args.manifest if args.manifest is not None else default_manifest_path(args.out_docx)
        )
        print(f"Manifest: {destination}")
    print(f"DOCX: {args.out_docx}")
    return 0


__all__ = [
    "AdeuOptions",
    "add_paragraph_ids",
    "analyze_manifest",
    "build_parser",
    "main",
    "prepare_manifest",
    "resolve_options",
    "run_docx",
    "write_prepared_manifest",
]


if __name__ == "__main__":  # pragma: no cover - titik masuk manual
    raise SystemExit(main())
