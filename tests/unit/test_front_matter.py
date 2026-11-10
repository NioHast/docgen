"""Tes unit stage ``front_matter`` dan perilaku cover."""

import re
from collections.abc import Mapping
from dataclasses import replace
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
from docgen.stages.mermaid import MermaidStage

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


def _render_with_page(**page_overrides: Any) -> str:
    format_ = load_format("undip-msi")
    return render_front_matter(
        _document(),
        load_structure("thesis"),
        replace(format_, page=replace(format_.page, **page_overrides)),
        body=_BODY,
        include_logo=False,
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

    # Author scalar harus menjadi satu CoverName, bukan tiga entri.
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

    # Judul panjang dipecah seimbang menjadi dua baris.
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
    # Nilai default berasal dari ``format.yml``, bukan bawaan Word.
    assert 'w:top="1134"' not in output
    assert 'w:right="1417"' not in output


def test_section_break_menormalisasi_alias_ukuran_lama() -> None:
    portrait = _render_with_page(size="LETTER", orientation="portrait")
    assert 'w:w="12240"' in portrait
    assert 'w:h="15840"' in portrait
    assert 'w:orient="landscape"' not in portrait

    landscape = _render_with_page(size="LETTER", orientation="landscape")
    assert 'w:w="15840"' in landscape
    assert 'w:h="12240"' in landscape
    assert 'w:orient="landscape"' in landscape

    lowercase = _render_with_page(size="a4", orientation="portrait")
    assert 'w:w="11906"' in lowercase
    assert 'w:h="16838"' in lowercase


@pytest.mark.parametrize(
    ("size", "orientation"),
    [
        ("A5", "portrait"),
        ("A4", "diagonal"),
    ],
)
def test_section_break_menolak_ukuran_atau_orientasi_tidak_valid(
    size: str,
    orientation: str,
) -> None:
    with pytest.raises(FrontMatterError) as excinfo:
        _render_with_page(size=size, orientation=orientation)

    assert excinfo.value.code == "FRONT-MATTER-PAGE"
    assert size in str(excinfo.value)
    assert orientation in str(excinfo.value)


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


def _stage_context(
    tmp_path: Path,
    *,
    with_mermaid: bool = True,
    artifact_body: str = _BODY,
    document_body: str = _BODY,
) -> SimpleNamespace:
    structure = load_structure("thesis")
    format_ = load_format("undip-msi")
    document = _document(body=document_body)
    artifacts = ArtifactStore()
    if with_mermaid:
        source = tmp_path / "mermaid.md"
        source.write_text(artifact_body, encoding="utf-8", newline="\n")
        artifacts.put("mermaid.markdown", source)
    return SimpleNamespace(
        document=document,
        structure=structure,
        format=format_,
        workspace=Workspace(root=tmp_path / ".laporan-build", keep=True),
        artifacts=artifacts,
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


def test_stage_membaca_artifact_mermaid_bukan_body_dokumen(tmp_path: Path) -> None:
    ctx = _stage_context(
        tmp_path,
        artifact_body="# Pendahuluan\n\nTeks dari artifact.\n",
        document_body="# Pendahuluan\n\nTeks dari body mentah.\n",
    )

    FrontMatterStage().run(ctx)

    text = ctx.workspace.path("front_matter.md").read_text(encoding="utf-8")
    assert "Teks dari artifact." in text
    assert "Teks dari body mentah." not in text


def test_stage_menolak_artifact_mermaid_yang_hilang(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_mermaid=False)

    with pytest.raises(FrontMatterError) as excinfo:
        FrontMatterStage().run(ctx)

    assert excinfo.value.code == "FRONT-MATTER-INPUT"
    assert not ctx.workspace.path("front_matter.md").exists()


def test_stage_menolak_artifact_mermaid_yang_menunjuk_file_tidak_ada(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_mermaid=False)
    missing = tmp_path / "mermaid-hilang.md"
    ctx.artifacts.put("mermaid.markdown", missing)

    with pytest.raises(FrontMatterError) as excinfo:
        FrontMatterStage().run(ctx)

    assert excinfo.value.code == "FRONT-MATTER-INPUT"
    assert excinfo.value.path == missing
    assert str(missing) in str(excinfo.value)


def test_stage_menolak_artifact_mermaid_berupa_direktori(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_mermaid=False)
    directory = tmp_path / "mermaid-dir"
    directory.mkdir()
    ctx.artifacts.put("mermaid.markdown", directory)

    with pytest.raises(FrontMatterError) as excinfo:
        FrontMatterStage().run(ctx)

    assert excinfo.value.code == "FRONT-MATTER-INPUT"
    assert excinfo.value.path == directory


def test_stage_menolak_artifact_markdown_lama_tanpa_mermaid(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_mermaid=False)
    legacy = tmp_path / "front_matter-lama.md"
    legacy.write_text(_BODY, encoding="utf-8", newline="\n")
    ctx.artifacts.put("markdown", legacy)

    with pytest.raises(FrontMatterError) as excinfo:
        FrontMatterStage().run(ctx)

    assert excinfo.value.code == "FRONT-MATTER-INPUT"


def test_dokumen_tanpa_mermaid_tetap_bisa_melewati_front_matter(tmp_path: Path) -> None:
    ctx = _stage_context(tmp_path, with_mermaid=False)
    ctx.document = replace(
        ctx.document,
        body="# Pendahuluan\n\nTeks tanpa diagram.\n",
    )

    mermaid = MermaidStage().run(ctx)

    assert mermaid.status == "ok"
    assert mermaid.metrics["blocks"] == 0
    source = ctx.workspace.path("mermaid.md")
    assert ctx.artifacts.get("mermaid.markdown") == source
    assert source.read_text(encoding="utf-8") == ctx.document.body

    result = FrontMatterStage().run(ctx)

    assert result.status == "ok"
    front_matter = ctx.workspace.path("front_matter.md")
    text = front_matter.read_text(encoding="utf-8")
    assert "# BAB I" in text
    assert "Teks tanpa diagram." in text
    assert ctx.artifacts.get("markdown") == front_matter
