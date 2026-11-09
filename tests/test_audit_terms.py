"""Tes pipeline audit italic istilah (tools/dev/audit_terms.py).

Fixture DOCX dibuat dengan python-docx agar tes tidak bergantung pada hasil
build. Glosarium tes ditulis sebagai TSV sementara.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE

from audit_terms import (
    CATEGORY_GLOSSARY_ITALIC,
    CATEGORY_GLOSSARY_PLAIN,
    CATEGORY_ITALIC_MISSING,
    CATEGORY_MIXED_CASE_NAME,
    CATEGORY_PLAIN_BUT_ITALIC,
    CATEGORY_UNKNOWN,
    audit_docx,
    main,
    render_report,
)
from docgen.docx.terms import load_glossary


# ---------------------------------------------------------------------------
# Helper fixture


def write_glossary(tmp_path: Path, rows: list[tuple[str, str]]) -> Path:
    """Tulis glosarium TSV minimal dengan header yang valid."""

    path = tmp_path / "istilah.tsv"
    lines = ["term\titalic\tgloss_first\tstatus"]
    for term, italic in rows:
        lines.append(f"{term}\t{italic}\tno\tconfirmed")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ensure_istilah_style(doc: Document) -> None:
    """Buat character style IstilahAsing yang italic."""

    style = doc.styles.add_style("IstilahAsing", WD_STYLE_TYPE.CHARACTER)
    style.font.italic = True


def add_paragraph(doc: Document, runs: list[tuple[str, str | None]]) -> None:
    """Tambah paragraf dari pasangan (teks, gaya)."""

    paragraph = doc.add_paragraph()
    for text, style in runs:
        run = paragraph.add_run(text)
        if style == "italic":
            run.italic = True
        elif style is not None:
            run.style = style


def save(doc: Document, path: Path) -> Path:
    doc.save(path)
    return path


def groups_by_key(result) -> dict[str, object]:
    return {group.key: group for group in result.groups}


# ---------------------------------------------------------------------------
# Tes perilaku


def test_kategori_dasar_dan_abbreviation(tmp_path: Path) -> None:
    """training data italic, data tegak, Graphical unknown, CNN diabaikan."""

    glossary_path = write_glossary(
        tmp_path, [("training data", "yes"), ("data", "no")]
    )

    doc = Document()
    ensure_istilah_style(doc)
    add_paragraph(
        doc,
        [
            ("Model ini memakai ", None),
            ("training data", "IstilahAsing"),
            (" dan data mentah. ", None),
            ("Graphical", None),
            (" hasilnya. CNN dipakai.", None),
        ],
    )
    docx_path = save(doc, tmp_path / "dasar.docx")

    result = audit_docx(docx_path, load_glossary(glossary_path))
    groups = groups_by_key(result)

    assert groups["training data"].category == CATEGORY_GLOSSARY_ITALIC
    assert groups["training data"].occurrences[0].italic is True
    assert groups["data"].category == CATEGORY_GLOSSARY_PLAIN
    assert groups["graphical"].category == CATEGORY_UNKNOWN
    assert groups["graphical"].occurrences[0].italic is False
    assert "cnn" not in groups
    assert result.abbreviation_count == 1
    assert [group.key for group in result.needs_fix] == []
    assert [group.key for group in result.needs_decision] == ["graphical"]


def test_abbreviation_di_glosarium_tetap_diproses(tmp_path: Path) -> None:
    """Akronim yang ada di glosarium tidak diabaikan."""

    glossary_path = write_glossary(tmp_path, [("CNN", "yes")])
    doc = Document()
    add_paragraph(doc, [("CNN", None)])
    docx_path = save(doc, tmp_path / "akronim.docx")

    result = audit_docx(docx_path, load_glossary(glossary_path))
    group = groups_by_key(result)["cnn"]

    assert group.category == CATEGORY_ITALIC_MISSING
    assert group in result.needs_fix


def test_glossary_italic_missing(tmp_path: Path) -> None:
    """Istilah italic=yes yang tegak harus masuk glossary_italic_missing."""

    glossary_path = write_glossary(tmp_path, [("training data", "yes")])
    doc = Document()
    add_paragraph(doc, [("training data", None)])
    docx_path = save(doc, tmp_path / "missing.docx")

    result = audit_docx(docx_path, load_glossary(glossary_path))
    group = groups_by_key(result)["training data"]

    assert group.category == CATEGORY_ITALIC_MISSING
    assert group in result.needs_fix


def test_glossary_plain_but_italic(tmp_path: Path) -> None:
    """Istilah italic=no yang miring harus masuk glossary_plain_but_italic."""

    glossary_path = write_glossary(tmp_path, [("data", "no")])
    doc = Document()
    add_paragraph(doc, [("data", "italic")])
    docx_path = save(doc, tmp_path / "plain.docx")

    result = audit_docx(docx_path, load_glossary(glossary_path))
    group = groups_by_key(result)["data"]

    assert group.category == CATEGORY_PLAIN_BUT_ITALIC
    assert group in result.needs_fix


def test_istilah_terpotong_run_dengan_spasi_tegak(tmp_path: Path) -> None:
    """Spasi di run tegak tidak membuat istilah italic dianggap missing."""

    glossary_path = write_glossary(tmp_path, [("training data", "yes")])
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("training").italic = True
    paragraph.add_run(" ")
    paragraph.add_run("data").italic = True
    docx_path = save(doc, tmp_path / "terpotong.docx")

    result = audit_docx(docx_path, load_glossary(glossary_path))
    group = groups_by_key(result)["training data"]

    assert group.category == CATEGORY_GLOSSARY_ITALIC
    assert result.needs_fix == []


def test_mixed_case_name_ditandai_name(tmp_path: Path) -> None:
    """CamelCase menjadi mixed_case_name; Graphical tetap unknown."""

    glossary_path = write_glossary(tmp_path, [])
    doc = Document()
    add_paragraph(doc, [("PostgreSQL dan Graphical", None)])
    docx_path = save(doc, tmp_path / "nama.docx")

    result = audit_docx(docx_path, load_glossary(glossary_path))
    groups = groups_by_key(result)

    assert groups["postgresql"].category == CATEGORY_MIXED_CASE_NAME
    assert groups["postgresql"].is_name is True
    assert groups["graphical"].category == CATEGORY_UNKNOWN
    assert groups["graphical"].is_name is False


def test_ekstraksi_body_tabel_header_footer(tmp_path: Path) -> None:
    """Paragraf body, sel tabel, header, dan footer semuanya dipindai."""

    glossary_path = write_glossary(tmp_path, [])
    doc = Document()
    doc.add_paragraph("Graphical body")

    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Graphical tabel"
    table.cell(0, 1).text = "CNN tabel"

    section = doc.sections[0]
    section.header.paragraphs[0].text = "Graphical header"
    section.footer.paragraphs[0].text = "Graphical footer"

    docx_path = save(doc, tmp_path / "area.docx")
    result = audit_docx(docx_path, load_glossary(glossary_path))

    graphical = groups_by_key(result)["graphical"]
    assert graphical.count == 4
    assert result.abbreviation_count == 1


def test_konteks_maksimal_delapan_kata(tmp_path: Path) -> None:
    """Konteks mengambil 8 kata sebelum dan 8 kata sesudah."""

    glossary_path = write_glossary(tmp_path, [])
    before = [f"kata{i}" for i in range(1, 10)]
    after = [f"kata{i}" for i in range(10, 19)]
    text = " ".join(before + ["Graphical"] + after)

    doc = Document()
    add_paragraph(doc, [(text, None)])
    docx_path = save(doc, tmp_path / "konteks.docx")

    result = audit_docx(docx_path, load_glossary(glossary_path))
    context = groups_by_key(result)["graphical"].occurrences[0].context

    assert context.startswith("… kata2")
    assert context.endswith("kata17 …")
    assert "kata1 " not in context
    assert "kata18" not in context
    assert context.count("kata") == 16


def test_laporan_deterministik(tmp_path: Path) -> None:
    """Dua pemanggilan menghasilkan laporan byte-identik."""

    glossary_path = write_glossary(
        tmp_path, [("training data", "yes"), ("data", "no")]
    )
    doc = Document()
    add_paragraph(
        doc,
        [
            ("training data", None),
            (" dan data ", None),
            ("Graphical", None),
        ],
    )
    docx_path = save(doc, tmp_path / "laporan.docx")

    out_a = tmp_path / "audit-a.md"
    out_b = tmp_path / "audit-b.md"
    argv_a = [
        "--docx",
        str(docx_path),
        "--glossary",
        str(glossary_path),
        "--out",
        str(out_a),
    ]
    argv_b = [
        "--docx",
        str(docx_path),
        "--glossary",
        str(glossary_path),
        "--out",
        str(out_b),
    ]

    assert main(argv_a) == 2
    assert main(argv_b) == 2
    assert out_a.read_bytes() == out_b.read_bytes()

    result = audit_docx(docx_path, load_glossary(glossary_path))
    assert render_report(result, docx_path, glossary_path) == render_report(
        result, docx_path, glossary_path
    )


def test_laporan_memuat_bagian_wajib(tmp_path: Path) -> None:
    """Laporan memuat ringkasan dan kedua tabel tindak lanjut."""

    glossary_path = write_glossary(
        tmp_path, [("training data", "yes"), ("data", "no")]
    )
    doc = Document()
    add_paragraph(doc, [("training data dan data. ", None), ("Graphical", None)])
    docx_path = save(doc, tmp_path / "bagian.docx")

    result = audit_docx(docx_path, load_glossary(glossary_path))
    report = render_report(result, docx_path, glossary_path)

    assert "# Audit Italic Istilah" in report
    assert "## Ringkasan" in report
    assert "## PERLU DIPERBAIKI" in report
    assert "## PERLU KEPUTUSAN" in report
    assert "## OK" in report
    assert "## Cara menindaklanjuti" in report
    assert "`glossary_italic_missing`" in report
    assert "`Graphical`" in report


def test_exit_code_dua_dan_nol(tmp_path: Path) -> None:
    """Exit 2 saat ada temuan; exit 0 saat bersih."""

    glossary_path = write_glossary(tmp_path, [("data", "no")])

    finding = Document()
    add_paragraph(finding, [("Graphical", None)])
    finding_path = save(finding, tmp_path / "finding.docx")
    finding_out = tmp_path / "finding.md"
    assert (
        main(
            [
                "--docx",
                str(finding_path),
                "--glossary",
                str(glossary_path),
                "--out",
                str(finding_out),
            ]
        )
        == 2
    )

    clean = Document()
    add_paragraph(clean, [("Data", None)])
    clean_path = save(clean, tmp_path / "clean.docx")
    clean_out = tmp_path / "clean.md"
    assert (
        main(
            [
                "--docx",
                str(clean_path),
                "--glossary",
                str(glossary_path),
                "--out",
                str(clean_out),
            ]
        )
        == 0
    )
