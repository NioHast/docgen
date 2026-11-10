"""Tes unit stage ``front_matter`` dan perilaku cover/docx.lua yang diport."""

import re
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from docgen.config import load_format, load_structure
from docgen.document import Document
from docgen.metadata import normalize_metadata
from docgen.pipeline import ArtifactStore, Workspace
from docgen.stages.front_matter import (
    PAGE_BREAK_XML,
    FrontMatterError,
    FrontMatterStage,
    render_front_matter,
    render_template,
    spacer,
)

_TITLE = "Optimasi Pipeline Pemrosesan Dokumen Markdown untuk Laporan Tugas Akhir"
_BODY = (
    "# Pendahuluan\n\n"
    "Teks pendahuluan.\n\n"
    "## Latar Belakang\n\n"
    "Teks latar belakang.\n\n"
    "### Detail\n\n"
    "Teks detail.\n"
)

_BASE_FRONT_MATTER: dict[str, Any] = {
    "title": _TITLE,
    "author": "Nama Mahasiswa",
    "nim": "30000000000000",
    "lecturer": "Dr. Nama Dosen Pengampu, M.Kom.",
    "lecturer_label": "Dosen Pengampu:",
    "course": "Penulisan Laporan Akademik",
    "institution": "Universitas Diponegoro",
    "faculty": "Program Studi Magister Sistem Informasi",
    "year": "2026",
    "date": "Agustus 2026",
    "report_name": "Tugas",
    "abstract_id": "Abstrak baris pertama.\n\nAbstrak baris kedua.",
    "abstract_en": "First paragraph.\n\nSecond paragraph.",
    "keywords": "machine learning",
    "keywords_en": ["pipeline", "DOCX"],
    "preface": "Ucapan terima kasih.",
}


def _document(
    front_matter: Mapping[str, Any] | None = None,
    *,
    body: str = _BODY,
    structure_id: str = "thesis",
) -> Document:
    values = dict(_BASE_FRONT_MATTER)
    if front_matter:
        values.update(front_matter)
    metadata = normalize_metadata(values, source="test")
    return Document(
        path=Path("document.md"),
        front_matter=values,
        body=body,
        metadata=metadata,
        structure_id=structure_id,
        format_id="undip-msi",
        bibliography=None,
    )


def _render(
    front_matter: Mapping[str, Any] | None = None,
    *,
    body: str = _BODY,
    structure_id: str = "thesis",
    include_logo: bool = True,
    logo: str | Path | None = None,
) -> str:
    return render_front_matter(
        _document(front_matter, body=body, structure_id=structure_id),
        load_structure(structure_id),
        load_format("undip-msi"),
        body=body,
        include_logo=include_logo,
        logo=logo,
    )


def _block(output: str, style: str) -> str:
    match = re.search(
        rf'::: \{{custom-style="{re.escape(style)}"\}}\n(.*?)\n:::',
        output,
        re.S,
    )
    assert match is not None, f"blok style {style!r} tidak ditemukan"
    return match.group(1)


def test_cover_identitas_logo_dan_dosen() -> None:
    output = _render()

    assert '::: {custom-style="CoverTitle"}' in output
    assert "OPTIMASI PIPELINE" in output
    assert "**Penulisan Laporan Akademik**" in output
    assert "Dosen Pengampu: **Dr. Nama Dosen Pengampu, M.Kom.**" in output
    assert "**Nama Mahasiswa**" in output
    assert "30000000000000" in output
    assert "PROGRAM STUDI MAGISTER SISTEM INFORMASI" in output
    assert "UNIVERSITAS DIPONEGORO" in output
    assert "2026" in output
    assert "{width=4.88cm}" in output
    assert "logo.jpg" in output


def test_cover_author_scalar_tidak_dipecah_menjadi_tiga() -> None:
    output = _render({"author": "Nama Mahasiswa"})

    # Bug lama: author scalar menjadi tiga CoverName (Nama, Mahasiswa, ...).
    assert output.count('custom-style="CoverName"') == 1
    assert output.count("**Nama Mahasiswa**") == 1
    assert "**Nama**" not in output
    assert "**Mahasiswa**" not in output


def test_cover_author_list_nim_per_entri() -> None:
    output = _render(
        {
            "author": [
                {"name": "Nama Satu", "nim": "30000000000001"},
                {"name": "Nama Dua", "nim": "30000000000002"},
            ],
            "nim": None,
        }
    )

    assert output.count('custom-style="CoverName"') == 2
    assert "**Nama Satu**" in output
    assert "**Nama Dua**" in output
    assert "30000000000001" in output
    assert "30000000000002" in output


def test_cover_show_lecturer_false() -> None:
    output = _render(structure_id="assignment")

    assert "Dosen Pengampu" not in output
    assert "Dr. Nama Dosen Pengampu" not in output


def test_cover_title_split_menggunakan_dua_baris() -> None:
    output = _render()
    title_block = _block(output, "CoverTitle")

    # Paritas dengan docx.lua/balance_title untuk judul yang sama.
    assert title_block == (
        "OPTIMASI PIPELINE PEMROSESAN DOKUMEN  \nMARKDOWN UNTUK LAPORAN TUGAS AKHIR"
    )


def test_cover_judul_dua_kata_panjang_tidak_crash() -> None:
    long_title = ("A" * 30) + " " + ("B" * 30)
    output = _render({"title": long_title})
    title_block = _block(output, "CoverTitle")

    assert title_block == ("A" * 30) + "  \n" + ("B" * 30)


def test_approval_dan_statement_dari_template() -> None:
    output = _render()

    assert "# LEMBAR PENGESAHAN {-}" in output
    assert "# PERNYATAAN {-}" in output
    assert f"**Judul:** {_TITLE}" in output
    assert "**Penulis:** Nama Mahasiswa" in output
    assert "**NIM:** 30000000000000" in output
    assert "**Institusi:** Universitas Diponegoro" in output
    assert "{{" not in output
    assert "{{ title }}" not in output


def test_abstract_id_keywords_scalar_dan_paragraf() -> None:
    output = _render()

    assert "# ABSTRAK {-}" in output
    assert "Abstrak baris pertama.\n\nAbstrak baris kedua." in output
    assert "**Kata Kunci:** *machine learning*" in output
    # Kata kunci string adalah satu entri, bukan dipecah per karakter/kata.
    assert "**Kata Kunci:** *machine learning*" in output
    assert "m, a, c" not in output


def test_abstract_en_keywords_list() -> None:
    output = _render()

    assert "# ABSTRACT {-}" in output
    assert "*First paragraph.*\n\n*Second paragraph.*" in output
    assert "**Keywords:** *pipeline, DOCX*" in output


def test_urutan_front_matter_dan_tanpa_field_toc() -> None:
    output = _render()

    positions = [
        output.index('custom-style="CoverTitle"'),
        output.index("# LEMBAR PENGESAHAN {-}"),
        output.index("# PERNYATAAN {-}"),
        output.index("# KATA PENGANTAR {-}"),
        output.index("# ABSTRAK {-}"),
        output.index("# ABSTRACT {-}"),
        output.index("BAB I"),
    ]
    assert positions == sorted(positions)
    assert "w:sdt" not in output
    assert "TOC \\o" not in output
    assert "TOC \\c" not in output


def test_page_break_antar_front_matter() -> None:
    output = _render()

    # Approval, statement, preface, abstract_id, abstract_en.
    assert output.count(PAGE_BREAK_XML) == 5


def test_section_break_memakai_margin_format_yml() -> None:
    output = _render()

    assert 'w:top="2268"' in output
    assert 'w:right="1701"' in output
    assert 'w:bottom="1701"' in output
    assert 'w:left="2268"' in output
    assert 'w:header="720"' in output
    assert 'w:footer="720"' in output
    # Default Lua lama tidak boleh dipakai.
    assert 'w:top="1134"' not in output
    assert 'w:right="1417"' not in output


def test_spacer_adalah_spacing_eksplisit() -> None:
    output = _render()

    assert output.count('w:spacing w:before="640"') == 3
    assert "<w:p/><w:p/>" not in output
    assert "spacer" not in output.lower()


def test_spacer_twips_nol_kosong() -> None:
    assert spacer(0) == ""
    assert spacer(-1) == ""
    assert 'w:before="360"' in spacer(360)


def test_heading_body_dinomori_sebelum_pandoc() -> None:
    output = _render()

    assert "# BAB I`<w:br/>`{=openxml}PENDAHULUAN" in output
    assert "## 1.1.`<w:tab/>`{=openxml}Latar Belakang" in output
    assert "### 1.1.1.`<w:tab/>`{=openxml}Detail" in output


def test_heading_arabic_dotted_untuk_assignment() -> None:
    output = _render(structure_id="assignment")

    assert "# 1. PENDAHULUAN" in output
    assert "## 1.1.`<w:tab/>`{=openxml}Latar Belakang" in output


def test_template_mengganti_placeholder_dan_menolak_yang_tidak_dikenal() -> None:
    rendered = render_template("**Judul:** {{ title }}", {"title": "Contoh"})
    assert rendered == "**Judul:** Contoh"

    with pytest.raises(FrontMatterError):
        render_template("{{ tidak_ada }}", {"title": "Contoh"})


def test_placeholder_terms_tidak_diubah() -> None:
    assert render_template("teks {{?istilah?}}", {"title": "x"}) == "teks {{?istilah?}}"


def _stage_context(tmp_path: Path) -> SimpleNamespace:
    structure = load_structure("thesis")
    format_ = load_format("undip-msi")
    document = _document()
    return SimpleNamespace(
        document=document,
        structure=structure,
        format=format_,
        workspace=Workspace(root=tmp_path / ".laporan-build", keep=True),
        artifacts=ArtifactStore(),
        dry_run=False,
    )


def test_stage_front_matter_menulis_markdown_idempoten(tmp_path: Path) -> None:
    stage = FrontMatterStage()
    ctx = _stage_context(tmp_path)

    first = stage.run(ctx)
    path = ctx.workspace.path("front_matter.md")
    assert first.changed is True
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'custom-style="CoverTitle"' in text
    assert "# BAB I" in text
    assert ctx.artifacts.get("markdown") == path

    second = stage.run(ctx)
    assert second.changed is False
    assert path.read_text(encoding="utf-8") == text
