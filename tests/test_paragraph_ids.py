"""Tes injeksi ID paragraf dan manifest Adeu."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

import add_paragraph_ids as api

FIXTURES = Path(__file__).parent / "fixtures" / "paragraph_ids"
FIXTURE = FIXTURES / "contoh.docx"
DOCUMENT_PART = "word/document.xml"
W_BODY = qn("w:body")
W_P = qn("w:p")
W_PPR = qn("w:pPr")
W_PSTYLE = qn("w:pStyle")
W_BOOKMARK_START = qn("w:bookmarkStart")
W_BOOKMARK_END = qn("w:bookmarkEnd")
W_ID = qn("w:id")
W_NAME = qn("w:name")
W_VAL = qn("w:val")
W_T = qn("w:t")
PARAGRAPH_ID_RE = re.compile(r"^p\d{4,}$")

MANIFEST_KEYS = {
    "id",
    "index",
    "kind",
    "heading_path",
    "text",
    "text_sha256",
    "protected",
    "protected_reason",
}


def run_tool(input_path: Path, tmp_path: Path, stem: str = "out") -> tuple[Path, Path]:
    output_path = tmp_path / f"{stem}.docx"
    manifest_path = tmp_path / f"{stem}.json"
    assert (
        api.main(
            [
                str(input_path),
                "--out-docx",
                str(output_path),
                "--manifest",
                str(manifest_path),
            ]
        )
        == 0
    )
    return output_path, manifest_path


def zip_hashes(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
        }


def document_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read(DOCUMENT_PART))


def body_paragraphs(path: Path) -> list[etree._Element]:
    root = document_root(path)
    body = root.find(W_BODY)
    assert body is not None
    return list(body.iter(W_P))


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


def paragraph_bookmarks(path: Path) -> list[etree._Element]:
    body = document_root(path).find(W_BODY)
    assert body is not None
    return [
        bookmark
        for bookmark in body.iter(W_BOOKMARK_START)
        if PARAGRAPH_ID_RE.fullmatch(bookmark.get(W_NAME) or "")
    ]


def load_manifest(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_injection_preserves_other_parts_and_paragraph_content(tmp_path: Path) -> None:
    output_path, _ = run_tool(FIXTURE, tmp_path)

    before = zip_hashes(FIXTURE)
    after = zip_hashes(output_path)
    assert list(before) == list(after)
    assert before[DOCUMENT_PART] != after[DOCUMENT_PART]
    for name, digest in before.items():
        if name != DOCUMENT_PART:
            assert after[name] == digest, f"part berubah: {name}"

    assert paragraph_signature(FIXTURE) == paragraph_signature(output_path)
    assert canonical_without_paragraph_ids(FIXTURE) == canonical_without_paragraph_ids(
        output_path
    )


def test_bookmark_count_and_wrapping(tmp_path: Path) -> None:
    output_path, manifest_path = run_tool(FIXTURE, tmp_path)
    paragraphs = body_paragraphs(output_path)
    bookmarks = paragraph_bookmarks(output_path)
    manifest = load_manifest(manifest_path)

    assert len(bookmarks) == len(paragraphs) == len(manifest["paragraphs"])
    assert len({bookmark.get(W_NAME) for bookmark in bookmarks}) == len(bookmarks)
    assert [bookmark.get(W_NAME) for bookmark in bookmarks] == [
        f"p{index:04d}" for index in range(1, len(paragraphs) + 1)
    ]

    for paragraph in paragraphs:
        children = list(paragraph)
        ppr = paragraph.find(W_PPR)
        start_index = next(
            index
            for index, child in enumerate(children)
            if child.tag == W_BOOKMARK_START
            and PARAGRAPH_ID_RE.fullmatch(child.get(W_NAME) or "")
        )
        expected_start = 0 if ppr is None else children.index(ppr) + 1
        assert start_index == expected_start
        assert children[-1].tag == W_BOOKMARK_END
        assert children[-1].get(W_ID) == children[start_index].get(W_ID)


def test_idempotent(tmp_path: Path) -> None:
    first_path, first_manifest_path = run_tool(FIXTURE, tmp_path, stem="first")
    second_path, second_manifest_path = run_tool(
        first_path, tmp_path, stem="second"
    )

    first_bookmarks = paragraph_bookmarks(first_path)
    second_bookmarks = paragraph_bookmarks(second_path)
    assert len(first_bookmarks) == len(second_bookmarks)
    assert [bookmark.get(W_NAME) for bookmark in first_bookmarks] == [
        bookmark.get(W_NAME) for bookmark in second_bookmarks
    ]
    assert len({bookmark.get(W_NAME) for bookmark in second_bookmarks}) == len(
        second_bookmarks
    )
    assert len({bookmark.get(W_ID) for bookmark in second_bookmarks}) == len(
        second_bookmarks
    )
    assert paragraph_signature(first_path) == paragraph_signature(second_path)
    assert load_manifest(first_manifest_path)["paragraphs"] == load_manifest(
        second_manifest_path
    )["paragraphs"]


def test_protected_caption_sectpr_and_toc(tmp_path: Path) -> None:
    output_path, manifest_path = run_tool(FIXTURE, tmp_path)
    manifest = load_manifest(manifest_path)
    entries = manifest["paragraphs"]
    paragraphs = body_paragraphs(output_path)
    by_index = {entry["index"]: entry for entry in entries}

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
        assert by_index[index]["protected"] is True
        assert by_index[index]["protected_reason"] == "caption_style"

    sectpr_indices = [
        index
        for index, paragraph in enumerate(paragraphs)
        if paragraph.find(f"{W_PPR}/{qn('w:sectPr')}") is not None
    ]
    assert sectpr_indices
    for index in sectpr_indices:
        assert by_index[index]["protected"] is True
        assert by_index[index]["protected_reason"] == "sectpr"

    toc_indices = [
        index
        for index, paragraph in enumerate(paragraphs)
        if (
            (style := paragraph.find(f"{W_PPR}/{W_PSTYLE}")) is not None
            and (style.get(W_VAL) or "").startswith("TOC")
            and style.get(W_VAL) != "TOCHeading"
        )
    ]
    assert toc_indices
    for index in toc_indices:
        assert by_index[index]["protected"] is True
        assert by_index[index]["protected_reason"] == "toc_field"

    # Field body non-TOC juga harus terlindungi dengan alasan yang tepat.
    reasons = {
        entry["protected_reason"]
        for entry in entries
        if entry["protected"]
    }
    assert {"seq_field", "page_field", "pageref_field"} <= reasons


def test_manifest_is_valid_and_hashes_match(tmp_path: Path) -> None:
    output_path, manifest_path = run_tool(FIXTURE, tmp_path)
    manifest = load_manifest(manifest_path)

    assert manifest["version"] == 1
    assert manifest["docx"] == output_path.name
    datetime.fromisoformat(manifest["built_at"])
    paragraphs = manifest["paragraphs"]
    assert paragraphs
    for index, entry in enumerate(paragraphs):
        assert set(entry) == MANIFEST_KEYS
        assert entry["id"] == f"p{index + 1:04d}"
        assert entry["index"] == index
        assert entry["kind"] in {
            "heading",
            "body",
            "table",
            "caption",
            "toc",
            "bibliography",
            "cover",
        }
        assert isinstance(entry["heading_path"], list)
        assert isinstance(entry["text"], str)
        assert (
            hashlib.sha256(entry["text"].encode("utf-8")).hexdigest()
            == entry["text_sha256"]
        )


def test_output_opens_with_python_docx_and_zip_is_clean(tmp_path: Path) -> None:
    output_path, _ = run_tool(FIXTURE, tmp_path)

    with zipfile.ZipFile(output_path) as archive:
        assert archive.testzip() is None
    document = Document(output_path)
    assert document.paragraphs
    assert len(document.tables) == 1
    assert document.paragraphs[0].text == "JUDUL SAMPUL"


def test_optional_source_matching(tmp_path: Path) -> None:
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    (chapters / "bab1.md").write_text(
        "# BAB I PENDAHULUAN\n"
        "\n"
        "## 1.1 Latar Belakang\n"
        "\n"
        "Paragraf pertama di bawah subbab.\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "sourced.docx"
    manifest_path = tmp_path / "sourced.json"
    assert (
        api.main(
            [
                str(FIXTURE),
                "--out-docx",
                str(output_path),
                "--manifest",
                str(manifest_path),
                "--source-dir",
                str(chapters),
            ]
        )
        == 0
    )
    manifest = load_manifest(manifest_path)
    paragraphs = manifest["paragraphs"]
    assert all("source_file" in entry and "source_line" in entry for entry in paragraphs)

    first_body = next(
        entry
        for entry in paragraphs
        if entry["text"] == "Paragraf pertama di bawah subbab."
    )
    assert first_body["source_file"] == "bab1.md"
    assert first_body["source_line"] == 5
    assert first_body["heading_path"] == [
        "BAB I PENDAHULUAN",
        "1.1 Latar Belakang",
    ]
