"""Tes injeksi bookmark dan manifest Adeu."""

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest
from docx import Document
from lxml import etree

from docgen.adeu.manifest import load_manifest, sha256_text
from docgen.adeu.paragraph_ids import (
    add_paragraph_ids,
    analyze_manifest,
    prepare_manifest,
    resolve_options,
    write_prepared_manifest,
)
from docgen.docx.bookmarks import bookmark_wraps_content, iter_bookmarks
from docgen.docx.package import DocumentPackage
from docgen.docx.xml import parse_xml
from docgen.errors import ManifestError

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "paragraph_ids" / "contoh.docx"
DOCUMENT_PART = "word/document.xml"
W_BODY = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body"
W_P = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
W_PPR = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr"
W_PSTYLE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pStyle"
W_BOOKMARK_START = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bookmarkStart"
W_BOOKMARK_END = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bookmarkEnd"
W_ID = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id"
W_NAME = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name"
W_VAL = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val"
PARAGRAPH_ID_RE = re.compile(r"^p\d{4,}$")


def zip_hashes(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}


def document_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return parse_xml(archive.read(DOCUMENT_PART))


def body_paragraphs(path: Path) -> list[etree._Element]:
    body = document_root(path).find(W_BODY)
    assert body is not None
    return list(body.iter(W_P))


def paragraph_bookmarks(path: Path) -> list[etree._Element]:
    body = document_root(path).find(W_BODY)
    assert body is not None
    return [
        bookmark
        for bookmark in body.iter(W_BOOKMARK_START)
        if PARAGRAPH_ID_RE.fullmatch(bookmark.get(W_NAME) or "")
    ]


def paragraph_signature(path: Path) -> list[tuple[str | None, str]]:
    document = Document(path)
    signature: list[tuple[str | None, str]] = []
    for paragraph in document.element.body.iter(W_P):
        style = paragraph.find(f"{W_PPR}/{W_PSTYLE}")
        style_id = style.get(W_VAL) if style is not None else None
        signature.append((style_id, paragraph.text))
    return signature


def canonical_without_paragraph_ids(path: Path) -> bytes:
    root = document_root(path)
    body = root.find(W_BODY)
    assert body is not None
    old_ids = set()
    for start in list(body.iter(W_BOOKMARK_START)):
        if PARAGRAPH_ID_RE.fullmatch(start.get(W_NAME) or ""):
            old_ids.add(start.get(W_ID))
            start.getparent().remove(start)
    for end in list(body.iter(W_BOOKMARK_END)):
        if end.get(W_ID) in old_ids:
            end.getparent().remove(end)
    return etree.tostring(root, method="c14n")


def load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def run_tool(
    input_path: Path,
    tmp_path: Path,
    *,
    stem: str = "out",
    docx_name: str | None = None,
    source_dir: Path | None = None,
    options=None,
) -> tuple[object, Path, Path]:
    output_path = tmp_path / f"{stem}.docx"
    manifest_path = tmp_path / f"{stem}.json"
    manifest = add_paragraph_ids(
        input_path,
        output_path,
        manifest_path,
        source_dir,
        docx_name,
        options=options,
    )
    return manifest, output_path, manifest_path


def test_injection_preserves_other_parts_and_content(tmp_path: Path) -> None:
    _, output_path, _ = run_tool(FIXTURE, tmp_path)

    before = zip_hashes(FIXTURE)
    after = zip_hashes(output_path)
    assert list(before) == list(after)
    assert before[DOCUMENT_PART] != after[DOCUMENT_PART]
    for name, digest in before.items():
        if name != DOCUMENT_PART:
            assert after[name] == digest, f"part berubah: {name}"

    assert paragraph_signature(FIXTURE) == paragraph_signature(output_path)
    assert canonical_without_paragraph_ids(FIXTURE) == canonical_without_paragraph_ids(output_path)


def test_bookmark_count_and_wrapping(tmp_path: Path) -> None:
    _, output_path, manifest_path = run_tool(FIXTURE, tmp_path)
    paragraphs = body_paragraphs(output_path)
    bookmarks = paragraph_bookmarks(output_path)
    manifest = load_json(manifest_path)

    assert len(bookmarks) == len(paragraphs) == len(manifest["paragraphs"])
    assert [bookmark.get(W_NAME) for bookmark in bookmarks] == [
        f"p{index:04d}" for index in range(1, len(paragraphs) + 1)
    ]
    assert len({bookmark.get(W_NAME) for bookmark in bookmarks}) == len(bookmarks)
    assert len({bookmark.get(W_ID) for bookmark in bookmarks}) == len(bookmarks)

    for paragraph in paragraphs:
        children = list(paragraph)
        ppr = paragraph.find(W_PPR)
        start_index = next(
            index
            for index, child in enumerate(children)
            if child.tag == W_BOOKMARK_START and PARAGRAPH_ID_RE.fullmatch(child.get(W_NAME) or "")
        )
        expected_start = 0 if ppr is None else children.index(ppr) + 1
        assert start_index == expected_start
        assert children[-1].tag == W_BOOKMARK_END
        assert children[-1].get(W_ID) == children[start_index].get(W_ID)


def test_bookmark_wraps_content_and_empty_paragraph() -> None:
    package = DocumentPackage.load(FIXTURE)
    manifest = prepare_manifest(package, docx_name="contoh.docx")
    assert manifest is not None

    bookmarks = {bookmark.name: bookmark for bookmark in iter_bookmarks(package)}
    assert bookmark_wraps_content(bookmarks["p0001"]) is True
    assert bookmark_wraps_content(bookmarks["p0003"]) is False


def test_idempotent_and_manifest_deterministic(tmp_path: Path) -> None:
    _, first_path, first_manifest_path = run_tool(
        FIXTURE, tmp_path, stem="first", docx_name="Laporan.docx"
    )
    _, second_path, second_manifest_path = run_tool(
        first_path, tmp_path, stem="second", docx_name="Laporan.docx"
    )

    first_bookmarks = paragraph_bookmarks(first_path)
    second_bookmarks = paragraph_bookmarks(second_path)
    assert [bookmark.get(W_NAME) for bookmark in first_bookmarks] == [
        bookmark.get(W_NAME) for bookmark in second_bookmarks
    ]
    assert [bookmark.get(W_ID) for bookmark in first_bookmarks] == [
        bookmark.get(W_ID) for bookmark in second_bookmarks
    ]
    assert zip_hashes(first_path)[DOCUMENT_PART] == zip_hashes(second_path)[DOCUMENT_PART]
    assert first_manifest_path.read_bytes() == second_manifest_path.read_bytes()
    assert paragraph_signature(first_path) == paragraph_signature(second_path)


def test_manifest_schema_and_text_sha256(tmp_path: Path) -> None:
    _, _output_path, manifest_path = run_tool(FIXTURE, tmp_path, docx_name="Tugas.docx")
    manifest = load_manifest(manifest_path)

    assert manifest.version == 1
    assert manifest.docx == "Tugas.docx"
    assert manifest.paragraphs
    for index, paragraph in enumerate(manifest.paragraphs):
        assert paragraph.id == f"p{index + 1:04d}"
        assert paragraph.index == index
        assert paragraph.kind in {
            "heading",
            "body",
            "table",
            "caption",
            "toc",
            "bibliography",
            "cover",
        }
        assert paragraph.text_sha256 == sha256_text(paragraph.text)
        assert paragraph.source_file is None
        assert paragraph.source_line is None

    payload = load_json(manifest_path)
    assert "built_at" not in payload
    assert "source_file" not in payload["paragraphs"][0]
    assert "source_line" not in payload["paragraphs"][0]

    payload["paragraphs"][0]["text"] = "Teks dimanipulasi."
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ManifestError) as excinfo:
        load_manifest(manifest_path)
    assert excinfo.value.code == "MANIFEST-HASH"


def test_protected_caption_sectpr_and_toc(tmp_path: Path) -> None:
    _, output_path, manifest_path = run_tool(FIXTURE, tmp_path)
    manifest = load_manifest(manifest_path)
    paragraphs = body_paragraphs(output_path)
    by_index = {entry.index: entry for entry in manifest.paragraphs}

    caption_indices = [
        index
        for index, paragraph in enumerate(paragraphs)
        if (
            (style := paragraph.find(f"{W_PPR}/{W_PSTYLE}")) is not None
            and style.get(W_VAL) in {"ImageCaption", "TableCaption"}
        )
    ]
    assert caption_indices
    for index in caption_indices:
        assert by_index[index].protected is True
        assert by_index[index].protected_reason == "caption_style"

    sectpr_indices = [
        index
        for index, paragraph in enumerate(paragraphs)
        if paragraph.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr/"
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sectPr"
        )
        is not None
    ]
    assert sectpr_indices
    for index in sectpr_indices:
        assert by_index[index].protected is True
        assert by_index[index].protected_reason == "sectpr"

    toc_style_indices = [
        index
        for index, paragraph in enumerate(paragraphs)
        if (
            (style := paragraph.find(f"{W_PPR}/{W_PSTYLE}")) is not None
            and (style.get(W_VAL) or "").startswith("TOC")
            and style.get(W_VAL) != "TOCHeading"
        )
    ]
    assert toc_style_indices
    for index in toc_style_indices:
        assert by_index[index].protected is True
        assert by_index[index].protected_reason == "toc_field"

    reasons = {entry.protected_reason for entry in manifest.paragraphs if entry.protected}
    assert {"seq_field", "page_field", "pageref_field", "toc_style"} <= reasons


def test_source_matching_uses_shared_markdown_parser(tmp_path: Path) -> None:
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    (chapters / "bab1.md").write_text(
        "# BAB I PENDAHULUAN\n\n## 1.1 Latar Belakang\n\nParagraf pertama di bawah subbab.\n",
        encoding="utf-8",
    )

    manifest, _, _ = run_tool(FIXTURE, tmp_path, stem="sourced", source_dir=chapters)
    assert manifest is not None

    first_body = next(
        paragraph
        for paragraph in manifest.paragraphs
        if paragraph.text == "Paragraf pertama di bawah subbab."
    )
    assert first_body.source_file == "bab1.md"
    assert first_body.source_line == 5
    assert first_body.heading_path == (
        "BAB I PENDAHULUAN",
        "1.1 Latar Belakang",
    )


def test_no_manifest_disables_manifest_and_source_scan(tmp_path: Path) -> None:
    missing_source = tmp_path / "tidak-ada"
    manifest, output_path, manifest_path = run_tool(
        FIXTURE,
        tmp_path,
        stem="tanpa-manifest",
        source_dir=missing_source,
        options=resolve_options(no_manifest=True),
    )

    assert manifest is None
    assert not manifest_path.exists()
    package = DocumentPackage.load(output_path)
    assert len(iter_bookmarks(package)) == len(body_paragraphs(FIXTURE))


def test_no_adeu_disables_bookmarks_manifest_and_source_scan(tmp_path: Path) -> None:
    missing_source = tmp_path / "tidak-ada"
    manifest, output_path, manifest_path = run_tool(
        FIXTURE,
        tmp_path,
        stem="tanpa-adeu",
        source_dir=missing_source,
        options=resolve_options(no_adeu=True),
    )

    assert manifest is None
    assert not manifest_path.exists()
    package = DocumentPackage.load(output_path)
    assert iter_bookmarks(package) == ()
    assert zip_hashes(FIXTURE) == zip_hashes(output_path)


def test_no_adeu_strips_existing_paragraph_bookmarks(tmp_path: Path) -> None:
    _, bookmarked_path, _ = run_tool(FIXTURE, tmp_path, stem="bookmarked")
    assert iter_bookmarks(DocumentPackage.load(bookmarked_path))

    manifest, output_path, manifest_path = run_tool(
        bookmarked_path,
        tmp_path,
        stem="stripped",
        options=resolve_options(no_adeu=True),
    )

    assert manifest is None
    assert not manifest_path.exists()
    assert iter_bookmarks(DocumentPackage.load(output_path)) == ()


def test_source_scan_can_be_disabled_on_analyze(tmp_path: Path) -> None:
    package = DocumentPackage.load(FIXTURE)
    prepared = prepare_manifest(package, docx_name="contoh.docx")
    assert prepared is not None

    without_scan = analyze_manifest(
        package,
        docx_name="contoh.docx",
        source_dir=tmp_path / "tidak-ada",
        source_scan=False,
    )
    assert all(
        paragraph.source_file is None and paragraph.source_line is None
        for paragraph in without_scan.paragraphs
    )


def test_docx_name_is_recorded_in_manifest(tmp_path: Path) -> None:
    manifest, _, manifest_path = run_tool(FIXTURE, tmp_path, docx_name="Tugas.docx")
    assert manifest is not None
    assert manifest.docx == "Tugas.docx"
    assert load_manifest(manifest_path).docx == "Tugas.docx"


def test_write_prepared_manifest_defaults_to_laporan_directory(tmp_path: Path) -> None:
    package = DocumentPackage.load(FIXTURE)
    prepared = prepare_manifest(package, docx_name="Tugas.docx")
    assert prepared is not None

    destination = write_prepared_manifest(prepared, tmp_path / "document.md")

    assert destination == tmp_path / ".laporan" / "manifest.json"
    assert destination.is_file()
    assert load_manifest(destination) == prepared
