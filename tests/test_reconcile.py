"""Tes rekonsiliasi edit manual DOCX -> Markdown.

Fixture DOCX dibuat sendiri dengan python-docx; tes tidak bergantung pada
``Laporan.docx`` hasil build.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from reconcile import extract_bookmarks, main

FIXTURES = Path(__file__).parent / "fixtures" / "reconcile"
CHAPTERS = FIXTURES / "chapters"
MANIFEST = FIXTURES / "manifest.json"

OLD_LANDASAN = (
    "Landasan teori merupakan fondasi utama dalam penyusunan laporan akademik "
    "yang dapat dipertanggungjawabkan."
)
NEW_LANDASAN = (
    "Landasan teori merupakan fondasi utama dalam penyusunan laporan akademik "
    "yang telah diperbarui."
)


# ---------------------------------------------------------------------------
# Helper fixture


def load_fixture_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def add_bookmarked_paragraph(document, bookmark_id: str, text: str, xml_id: int):
    """Tambahkan paragraf dengan bookmarkStart/End di dalamnya."""

    paragraph = document.add_paragraph()
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(xml_id))
    start.set(qn("w:name"), bookmark_id)
    paragraph._p.insert(0, start)

    if text:
        paragraph.add_run(text)

    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(xml_id))
    paragraph._p.append(end)
    return paragraph


def add_tracked_paragraph(
    document,
    bookmark_id: str,
    before: str,
    after: str,
    xml_id: int,
    revision_id: int,
):
    """Paragraf dengan Track Changes: teks lama dihapus, teks baru disisipkan."""

    prefix_length = 0
    while (
        prefix_length < min(len(before), len(after))
        and before[prefix_length] == after[prefix_length]
    ):
        prefix_length += 1

    prefix = before[:prefix_length]
    deleted = before[prefix_length:]
    inserted = after[prefix_length:]

    paragraph = document.add_paragraph()
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(xml_id))
    start.set(qn("w:name"), bookmark_id)
    paragraph._p.insert(0, start)

    if prefix:
        paragraph.add_run(prefix)

    if deleted:
        deletion = OxmlElement("w:del")
        deletion.set(qn("w:id"), str(revision_id))
        deletion.set(qn("w:author"), "Penyunting")
        run = OxmlElement("w:r")
        del_text = OxmlElement("w:delText")
        del_text.text = deleted
        run.append(del_text)
        deletion.append(run)
        paragraph._p.append(deletion)

    if inserted:
        insertion = OxmlElement("w:ins")
        insertion.set(qn("w:id"), str(revision_id + 1))
        insertion.set(qn("w:author"), "Penyunting")
        run = OxmlElement("w:r")
        text_node = OxmlElement("w:t")
        text_node.text = inserted
        run.append(text_node)
        insertion.append(run)
        paragraph._p.append(insertion)

    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(xml_id))
    paragraph._p.append(end)
    return paragraph


def write_docx(
    path: Path,
    *,
    overrides: dict[str, str] | None = None,
    removed: tuple[str, ...] = (),
    extra_bookmarks: tuple[tuple[str, str], ...] = (),
    unbookmarked: tuple[str, ...] = (),
    tracked: dict[str, tuple[str, str]] | None = None,
) -> Path:
    """Bangun DOCX dari manifest fixture, dengan variasi untuk tiap tes."""

    manifest = load_fixture_manifest()
    document = Document()
    xml_id = 1
    revision_id = 100

    for paragraph in manifest["paragraphs"]:
        paragraph_id = paragraph["id"]
        if paragraph_id in removed:
            continue

        text = paragraph["text"]
        if overrides and paragraph_id in overrides:
            text = overrides[paragraph_id]

        if tracked and paragraph_id in tracked:
            before, after = tracked[paragraph_id]
            add_tracked_paragraph(
                document, paragraph_id, before, after, xml_id, revision_id
            )
            revision_id += 2
        else:
            add_bookmarked_paragraph(document, paragraph_id, text, xml_id)
        xml_id += 1

    for bookmark_id, text in extra_bookmarks:
        add_bookmarked_paragraph(document, bookmark_id, text, xml_id)
        xml_id += 1

    for text in unbookmarked:
        document.add_paragraph(text)

    document.save(path)
    return path


def run_reconcile(
    tmp_path: Path,
    docx: Path,
    *,
    manifest: Path = MANIFEST,
    chapters: Path = CHAPTERS,
    out: Path | None = None,
) -> tuple[int, Path]:
    report_path = out or (tmp_path / "review" / "manual-edits.md")
    code = main(
        [
            "--docx",
            str(docx),
            "--manifest",
            str(manifest),
            "--chapters",
            str(chapters),
            "--out",
            str(report_path),
        ]
    )
    return code, report_path


def read_report(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def chapter_hashes() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(CHAPTERS.glob("*.md"))
    }


# ---------------------------------------------------------------------------
# Tes wajib


def test_matching_fixture_exits_zero(tmp_path):
    docx = write_docx(tmp_path / "Laporan.docx")

    code, report_path = run_reconcile(tmp_path, docx)

    assert code == 0
    report = read_report(report_path)
    assert report.startswith("# Edit Manual\n")
    assert "- Diperiksa: 7 paragraf" in report
    assert "- Berubah: 0" in report
    assert "- Dilindungi & dilanggar: 0" in report
    assert "PELANGGARAN" not in report


def test_body_edit_reports_old_new_and_source(tmp_path):
    docx = write_docx(
        tmp_path / "Laporan.docx", overrides={"p0006": NEW_LANDASAN}
    )

    code, report_path = run_reconcile(tmp_path, docx)

    assert code == 2
    report = read_report(report_path)
    assert "## p0006 — BAB II TINJAUAN PUSTAKA / 2.1 Landasan Teori" in report
    assert OLD_LANDASAN in report
    assert NEW_LANDASAN in report
    assert "Sumber: chapters/bab2-tinjauan-pustaka.md (blok 3, kemiripan " in report
    assert "**Saran:** terapkan ke Markdown lalu build ulang." in report
    assert "- Berubah: 1" in report


def test_protected_caption_edit_exits_three(tmp_path):
    docx = write_docx(
        tmp_path / "Laporan.docx",
        overrides={"p0005": "Tabel 2.1 Ringkasan Pipeline (diedit manual)"},
    )

    code, report_path = run_reconcile(tmp_path, docx)

    assert code == 3
    report = read_report(report_path)
    assert (
        "## PELANGGARAN p0005 — caption (protected: caption_style)"
        in report
    )
    assert "**Sebelum**" in report
    assert "Tabel 2.1 Ringkasan Pipeline" in report
    assert "Tabel 2.1 Ringkasan Pipeline (diedit manual)" in report
    assert "Blok ini tidak boleh diedit manual. Kembalikan dari build." in report
    assert "**Saran:**" not in report
    assert "- Dilindungi & dilanggar: 1" in report


def test_new_paragraph_without_id_is_reported(tmp_path):
    text = "Paragraf baru tanpa ID yang harus dilaporkan."
    docx = write_docx(tmp_path / "Laporan.docx", unbookmarked=(text,))

    code, report_path = run_reconcile(tmp_path, docx)

    assert code == 2
    report = read_report(report_path)
    assert "## PARAGRAF BARU — tanpa ID" in report
    assert text in report


def test_new_bookmark_absent_from_manifest_is_reported(tmp_path):
    text = "Paragraf baru dengan ID yang belum ada di manifest."
    docx = write_docx(
        tmp_path / "Laporan.docx", extra_bookmarks=(("p0099", text),)
    )

    code, report_path = run_reconcile(tmp_path, docx)

    assert code == 2
    report = read_report(report_path)
    assert "## PARAGRAF BARU p0099" in report
    assert text in report


def test_missing_manifest_id_is_reported(tmp_path):
    docx = write_docx(tmp_path / "Laporan.docx", removed=("p0003",))

    code, report_path = run_reconcile(tmp_path, docx)

    assert code == 2
    report = read_report(report_path)
    assert "## PARAGRAF HILANG p0003" in report
    assert "BAB I PENDAHULUAN / 1.2 Rumusan Masalah" in report
    assert (
        "Berdasarkan latar belakang di atas, rumusan masalah penelitian ini "
        "adalah bagaimana merancang pipeline dokumentasi yang konsisten."
        in report
    )


def test_report_is_deterministic(tmp_path):
    docx = write_docx(
        tmp_path / "Laporan.docx", overrides={"p0006": NEW_LANDASAN}
    )

    code_one, report_one = run_reconcile(
        tmp_path, docx, out=tmp_path / "review" / "pertama.md"
    )
    code_two, report_two = run_reconcile(
        tmp_path, docx, out=tmp_path / "review" / "kedua.md"
    )

    assert code_one == code_two == 2
    assert report_one.read_bytes() == report_two.read_bytes()


# ---------------------------------------------------------------------------
# Tes tambahan


def test_source_not_found_is_reported(tmp_path):
    manifest_data = load_fixture_manifest()
    for paragraph in manifest_data["paragraphs"]:
        if paragraph["id"] == "p0002":
            paragraph["heading_path"] = ["BAB IX TIDAK ADA"]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    docx = write_docx(
        tmp_path / "Laporan.docx",
        overrides={"p0002": "Teks yang berbeda dari blok sumber mana pun."},
    )
    code, report_path = run_reconcile(
        tmp_path, docx, manifest=manifest_path
    )

    assert code == 2
    report = read_report(report_path)
    assert "**SUMBER TIDAK DITEMUKAN**" in report
    assert "**Saran:**" in report


def test_tracked_changes_use_accepted_text(tmp_path):
    docx = write_docx(
        tmp_path / "Laporan.docx",
        tracked={"p0006": (OLD_LANDASAN, NEW_LANDASAN)},
    )

    snapshot = extract_bookmarks(docx)
    assert snapshot.bookmarks["p0006"] == NEW_LANDASAN

    code, report_path = run_reconcile(tmp_path, docx)
    assert code == 2
    report = read_report(report_path)
    assert NEW_LANDASAN in report
    assert "**Sebelum**" in report
    assert "**Sesudah**" in report


def test_chapters_are_never_written(tmp_path):
    before = chapter_hashes()
    docx = write_docx(
        tmp_path / "Laporan.docx", overrides={"p0006": NEW_LANDASAN}
    )

    code, _ = run_reconcile(tmp_path, docx)

    assert code == 2
    assert chapter_hashes() == before
    assert not list(CHAPTERS.glob("manual-edits.md"))


def test_missing_protected_paragraph_is_a_violation(tmp_path):
    docx = write_docx(tmp_path / "Laporan.docx", removed=("p0005",))

    code, report_path = run_reconcile(tmp_path, docx)

    assert code == 3
    report = read_report(report_path)
    assert "## PELANGGARAN p0005 — caption (protected: caption_style)" in report
    assert "**PARAGRAF HILANG**" in report
    assert "- Dilindungi & dilanggar: 1" in report


def test_output_inside_chapters_is_rejected(tmp_path):
    chapters = tmp_path / "chapters"
    chapters.mkdir()
    (chapters / "bab1.md").write_text(
        "# PENDAHULUAN\n\n## Latar Belakang\n\nTeks.\n", encoding="utf-8"
    )
    docx = write_docx(
        tmp_path / "Laporan.docx", overrides={"p0006": NEW_LANDASAN}
    )
    forbidden = chapters / "manual-edits.md"

    code, _ = run_reconcile(
        tmp_path, docx, chapters=chapters, out=forbidden
    )

    assert code == 1
    assert not forbidden.exists()


def test_docx_without_paragraph_ids_reports_missing_and_new(tmp_path):
    manifest_data = load_fixture_manifest()
    manifest_data["paragraphs"] = [
        paragraph
        for paragraph in manifest_data["paragraphs"]
        if not paragraph["protected"]
    ]
    manifest_path = tmp_path / "manifest-tanpa-protected.json"
    manifest_path.write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    docx = tmp_path / "tanpa-id.docx"
    document = Document()
    document.add_paragraph("Dokumen ini belum melalui tahap tambah ID.")
    document.save(docx)

    code, report_path = run_reconcile(
        tmp_path, docx, manifest=manifest_path
    )

    assert code == 2
    report = read_report(report_path)
    assert "## PARAGRAF HILANG p0001" in report
    assert "## PARAGRAF BARU — tanpa ID" in report
    assert "Dokumen ini belum melalui tahap tambah ID." in report


def test_invalid_manifest_exits_one(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{bukan json", encoding="utf-8", newline="\n")
    docx = write_docx(tmp_path / "Laporan.docx")

    code, report_path = run_reconcile(
        tmp_path, docx, manifest=manifest_path
    )

    assert code == 1
    assert not report_path.exists()


def test_invalid_docx_exits_one(tmp_path):
    docx = tmp_path / "rusak.docx"
    docx.write_bytes(b"bukan arsip docx")

    code, report_path = run_reconcile(tmp_path, docx)

    assert code == 1
    assert not report_path.exists()


def test_missing_chapters_dir_exits_one(tmp_path):
    docx = write_docx(tmp_path / "Laporan.docx")

    code, report_path = run_reconcile(
        tmp_path, docx, chapters=tmp_path / "tidak-ada"
    )

    assert code == 1
    assert not report_path.exists()
