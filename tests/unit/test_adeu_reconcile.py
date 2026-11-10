"""Tes rekonsiliasi edit manual DOCX -> Markdown untuk fitur Adeu."""

import hashlib
import json
from pathlib import Path

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from docgen.features.adeu.cli import build_parser, command_reconcile
from docgen.features.adeu.reconcile import extract_bookmarks, main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "reconcile"
MANIFEST = FIXTURES / "manifest.json"

OLD_LANDASAN = (
    "Landasan teori merupakan fondasi utama dalam penyusunan laporan akademik "
    "yang dapat dipertanggungjawabkan."
)
NEW_LANDASAN = (
    "Landasan teori merupakan fondasi utama dalam penyusunan laporan akademik "
    "yang telah diperbarui."
)

BODY = (
    "# PENDAHULUAN\n"
    "\n"
    "## Latar Belakang\n"
    "\n"
    "Penulisan laporan akademik merupakan kegiatan fundamental dalam penelitian.\n"
    "\n"
    "## Rumusan Masalah\n"
    "\n"
    "Berdasarkan latar belakang di atas, rumusan masalah penelitian ini adalah "
    "bagaimana merancang pipeline dokumentasi yang konsisten.\n"
    "\n"
    "# TINJAUAN PUSTAKA\n"
    "\n"
    "## Landasan Teori\n"
    "\n"
    "Landasan teori merupakan fondasi utama dalam penyusunan laporan akademik "
    "yang dapat dipertanggungjawabkan.\n"
    "\n"
    "## Kerangka Pemikiran\n"
    "\n"
    "Kerangka pemikiran menghubungkan teori dengan kebutuhan implementasi pipeline.\n"
)


def load_fixture_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def make_document(tmp_path: Path, name: str = "document.md", report_name: str = "Laporan") -> Path:
    path = tmp_path / name
    path.write_text(
        "---\n"
        "title: Uji Rekonsiliasi\n"
        "author: Nama Mahasiswa\n"
        f"report_name: {report_name}\n"
        "---\n" + BODY,
        encoding="utf-8",
        newline="\n",
    )
    return path


def add_bookmarked_paragraph(document, bookmark_id: str, text: str, xml_id: int):
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
    manifest: dict | None = None,
    overrides: dict[str, str] | None = None,
    removed: tuple[str, ...] = (),
    extra_bookmarks: tuple[tuple[str, str], ...] = (),
    unbookmarked: tuple[str, ...] = (),
    tracked: dict[str, tuple[str, str]] | None = None,
) -> Path:
    data = manifest if manifest is not None else load_fixture_manifest()
    document = Document()
    xml_id = 1
    revision_id = 100

    for paragraph in data["paragraphs"]:
        paragraph_id = paragraph["id"]
        if paragraph_id in removed:
            continue

        text = paragraph["text"]
        if overrides and paragraph_id in overrides:
            text = overrides[paragraph_id]

        if tracked and paragraph_id in tracked:
            before, after = tracked[paragraph_id]
            add_tracked_paragraph(document, paragraph_id, before, after, xml_id, revision_id)
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


def write_manifest(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def run_cli(
    document: Path,
    *,
    docx: Path | None = None,
    manifest: Path | None = None,
    out: Path | None = None,
) -> int:
    argv = [str(document)]
    if docx is not None:
        argv.extend(["--docx", str(docx)])
    if manifest is not None:
        argv.extend(["--manifest", str(manifest)])
    if out is not None:
        argv.extend(["--out", str(out)])
    return main(argv)


def read_report(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def test_cli_registers_reconcile_subcommand(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(["reconcile", "document.md"])
    assert args.command == "reconcile"
    assert args.document == "document.md"
    assert callable(command_reconcile)


def test_matching_fixture_exits_zero(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = write_docx(tmp_path / "Laporan.docx")
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(
        document,
        docx=docx,
        manifest=MANIFEST,
        out=report_path,
    )

    assert code == 0
    report = read_report(report_path)
    assert report.startswith("# Edit Manual\n")
    assert "- Diperiksa: 7 paragraf" in report
    assert "- Berubah: 0" in report
    assert "- Dilindungi & dilanggar: 0" in report
    assert "PELANGGARAN" not in report


def test_default_paths_follow_document(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    write_docx(tmp_path / "Laporan.docx")
    (tmp_path / ".laporan").mkdir()
    write_manifest(tmp_path / ".laporan" / "manifest.json", load_fixture_manifest())

    code = run_cli(document)

    assert code == 0
    report_path = tmp_path / ".laporan" / "reconcile.md"
    assert report_path.is_file()
    assert "- Diperiksa: 7 paragraf" in read_report(report_path)


def test_default_docx_prefers_out_directory(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    (tmp_path / "out").mkdir()
    write_docx(tmp_path / "out" / "Laporan.docx")
    (tmp_path / ".laporan").mkdir()
    write_manifest(tmp_path / ".laporan" / "manifest.json", load_fixture_manifest())

    code = run_cli(document)

    assert code == 0
    report_path = tmp_path / ".laporan" / "reconcile.md"
    assert report_path.is_file()
    assert "- Diperiksa: 7 paragraf" in read_report(report_path)


def test_default_docx_falls_back_to_document_directory(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    (tmp_path / "out").mkdir()
    write_docx(tmp_path / "Laporan.docx")
    (tmp_path / ".laporan").mkdir()
    write_manifest(tmp_path / ".laporan" / "manifest.json", load_fixture_manifest())

    code = run_cli(document)

    assert code == 0
    report_path = tmp_path / ".laporan" / "reconcile.md"
    assert report_path.is_file()
    assert "- Diperiksa: 7 paragraf" in read_report(report_path)


def test_report_name_wajib_tanpa_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = make_document(tmp_path)
    document.write_text(
        document.read_text(encoding="utf-8").replace("report_name: Laporan\n", ""),
        encoding="utf-8",
        newline="\n",
    )

    assert run_cli(document) == 1
    error = capsys.readouterr().err
    assert "CFG-REQUIRED" in error
    assert "report_name" in error


def test_explicit_docx_overrides_out_default(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    (tmp_path / "out").mkdir()
    write_docx(tmp_path / "out" / "Laporan.docx")
    edited = write_docx(
        tmp_path / "suntingan.docx",
        overrides={"p0006": NEW_LANDASAN},
    )
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(document, docx=edited, manifest=MANIFEST, out=report_path)

    assert code == 3
    report = read_report(report_path)
    assert NEW_LANDASAN in report
    assert "- Berubah: 1" in report


def test_body_edit_reports_source_and_exit_three(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = write_docx(
        tmp_path / "Laporan.docx",
        overrides={"p0006": NEW_LANDASAN},
    )
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(
        document,
        docx=docx,
        manifest=MANIFEST,
        out=report_path,
    )

    assert code == 3
    report = read_report(report_path)
    assert "## p0006 — BAB II TINJAUAN PUSTAKA / 2.1 Landasan Teori" in report
    assert OLD_LANDASAN in report
    assert NEW_LANDASAN in report
    assert "Sumber: document.md (blok 8, kemiripan " in report
    assert "**Saran:** terapkan ke Markdown lalu build ulang." in report
    assert "- Berubah: 1" in report


def test_protected_caption_edit_exits_four(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = write_docx(
        tmp_path / "Laporan.docx",
        overrides={"p0005": "Tabel 2.1 Ringkasan Pipeline (diedit manual)"},
    )
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(
        document,
        docx=docx,
        manifest=MANIFEST,
        out=report_path,
    )

    assert code == 4
    report = read_report(report_path)
    assert "## PELANGGARAN p0005 — caption (protected: caption_style)" in report
    assert "Tabel 2.1 Ringkasan Pipeline" in report
    assert "Tabel 2.1 Ringkasan Pipeline (diedit manual)" in report
    assert "Blok ini tidak boleh diedit manual. Kembalikan dari build." in report
    assert "**Saran:**" not in report
    assert "- Dilindungi & dilanggar: 1" in report


def test_new_paragraph_without_id_is_reported(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    text = "Paragraf baru tanpa ID yang harus dilaporkan."
    docx = write_docx(tmp_path / "Laporan.docx", unbookmarked=(text,))
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(document, docx=docx, manifest=MANIFEST, out=report_path)

    assert code == 3
    report = read_report(report_path)
    assert "## PARAGRAF BARU — tanpa ID" in report
    assert text in report


def test_new_bookmark_absent_from_manifest_is_reported(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    text = "Paragraf baru dengan ID yang belum ada di manifest."
    docx = write_docx(
        tmp_path / "Laporan.docx",
        extra_bookmarks=(("p0099", text),),
    )
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(document, docx=docx, manifest=MANIFEST, out=report_path)

    assert code == 3
    report = read_report(report_path)
    assert "## PARAGRAF BARU p0099" in report
    assert text in report


def test_missing_manifest_id_is_reported(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = write_docx(tmp_path / "Laporan.docx", removed=("p0003",))
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(document, docx=docx, manifest=MANIFEST, out=report_path)

    assert code == 3
    report = read_report(report_path)
    assert "## PARAGRAF HILANG p0003" in report
    assert "BAB I PENDAHULUAN / 1.2 Rumusan Masalah" in report


def test_missing_protected_paragraph_is_violation(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = write_docx(tmp_path / "Laporan.docx", removed=("p0005",))
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(document, docx=docx, manifest=MANIFEST, out=report_path)

    assert code == 4
    report = read_report(report_path)
    assert "## PELANGGARAN p0005 — caption (protected: caption_style)" in report
    assert "**PARAGRAF HILANG**" in report
    assert "- Dilindungi & dilanggar: 1" in report


def test_tracked_changes_use_accepted_text(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = write_docx(
        tmp_path / "Laporan.docx",
        tracked={"p0006": (OLD_LANDASAN, NEW_LANDASAN)},
    )
    report_path = tmp_path / "review" / "manual-edits.md"

    snapshot = extract_bookmarks(docx)
    assert snapshot.bookmarks["p0006"] == NEW_LANDASAN

    code = run_cli(document, docx=docx, manifest=MANIFEST, out=report_path)
    assert code == 3
    report = read_report(report_path)
    assert NEW_LANDASAN in report
    assert "**Sebelum**" in report
    assert "**Sesudah**" in report


def test_report_is_deterministic(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = write_docx(
        tmp_path / "Laporan.docx",
        overrides={"p0006": NEW_LANDASAN},
    )
    first = tmp_path / "review" / "pertama.md"
    second = tmp_path / "review" / "kedua.md"

    assert run_cli(document, docx=docx, manifest=MANIFEST, out=first) == 3
    assert run_cli(document, docx=docx, manifest=MANIFEST, out=second) == 3
    assert first.read_bytes() == second.read_bytes()


def test_source_not_found_is_reported(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    data = load_fixture_manifest()
    for paragraph in data["paragraphs"]:
        if paragraph["id"] == "p0002":
            paragraph["heading_path"] = ["BAB IX TIDAK ADA"]
    manifest_path = write_manifest(tmp_path / "manifest.json", data)
    docx = write_docx(
        tmp_path / "Laporan.docx",
        overrides={"p0002": "Teks yang berbeda dari blok sumber mana pun."},
    )
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(document, docx=docx, manifest=manifest_path, out=report_path)

    assert code == 3
    report = read_report(report_path)
    assert "**SUMBER TIDAK DITEMUKAN**" in report
    assert "**Saran:**" in report


def test_invalid_manifest_exits_one(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{bukan json", encoding="utf-8", newline="\n")
    docx = write_docx(tmp_path / "Laporan.docx")
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(document, docx=docx, manifest=manifest_path, out=report_path)

    assert code == 1
    assert not report_path.exists()


def test_manifest_hash_tamper_exits_one(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    data = load_fixture_manifest()
    data["paragraphs"][0]["text"] = "Teks dimanipulasi."
    manifest_path = write_manifest(tmp_path / "manifest.json", data)
    docx = write_docx(tmp_path / "Laporan.docx")
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(document, docx=docx, manifest=manifest_path, out=report_path)

    assert code == 1
    assert not report_path.exists()


def test_invalid_docx_exits_one(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = tmp_path / "rusak.docx"
    docx.write_bytes(b"bukan arsip docx")
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(document, docx=docx, manifest=MANIFEST, out=report_path)

    assert code == 1
    assert not report_path.exists()


def test_missing_document_exits_one(tmp_path: Path) -> None:
    docx = write_docx(tmp_path / "Laporan.docx")
    report_path = tmp_path / "review" / "manual-edits.md"

    code = run_cli(tmp_path / "tidak-ada.md", docx=docx, manifest=MANIFEST, out=report_path)

    assert code == 1
    assert not report_path.exists()


def test_out_without_md_extension_is_rejected(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = write_docx(tmp_path / "Laporan.docx")
    forbidden = tmp_path / "review" / "manual-edits.txt"

    code = run_cli(document, docx=docx, manifest=MANIFEST, out=forbidden)

    assert code == 1
    assert not forbidden.exists()


def test_out_must_not_overwrite_inputs(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    docx = write_docx(tmp_path / "Laporan.docx")
    before = docx.read_bytes()

    code = run_cli(document, docx=docx, manifest=MANIFEST, out=docx)

    assert code == 1
    assert docx.read_bytes() == before

    code = run_cli(document, docx=docx, manifest=MANIFEST, out=document)
    assert code == 1


def test_chapters_and_document_are_never_written(tmp_path: Path) -> None:
    document = make_document(tmp_path)
    before = hashlib.sha256(document.read_bytes()).hexdigest()
    docx = write_docx(
        tmp_path / "Laporan.docx",
        overrides={"p0006": NEW_LANDASAN},
    )

    code = run_cli(
        document,
        docx=docx,
        manifest=MANIFEST,
        out=tmp_path / "review" / "manual-edits.md",
    )

    assert code == 3
    assert hashlib.sha256(document.read_bytes()).hexdigest() == before
