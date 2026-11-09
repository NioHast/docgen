"""Tes integrasi opsional: Pandoc nyata menghasilkan DOCX mini yang valid.

Tes ini tidak menjadi bagian gate unit. Ia dilewati bila Pandoc tidak ada.
Input dibangun dari ``front_matter`` + ``style_reference`` yang sama dengan
pipeline, sehingga kontrak "Markdown materialized + derived reference" ikut
diuji tanpa menjalankan stage post-Pandoc.
"""

from __future__ import annotations

import logging
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from docgen.config import load_format
from docgen.document import load_project
from docgen.docx import DocumentPackage
from docgen.pipeline import ArtifactStore, Workspace
from docgen.stages.front_matter import render_front_matter
from docgen.stages.pandoc import PandocStage, find_pandoc
from docgen.stages.style_reference import build_reference_docx

pytestmark = pytest.mark.integration

PANDOC = find_pandoc()
SKIP_REASON = "Pandoc tidak tersedia untuk tes integrasi"


def _write_project(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "gambar").mkdir()
    shutil.copyfile(
        load_format("undip-msi").assets.logo,
        project / "gambar" / "body.jpg",
    )
    (project / "references.bib").write_text(
        "@book{pandoc2024,\n"
        "  author = {MacFarlane, John},\n"
        "  title = {Pandoc},\n"
        "  year = {2024}\n"
        "}\n",
        encoding="utf-8",
    )
    document = project / "document.md"
    document.write_text(
        "---\n"
        'title: "Uji Pipeline Mini"\n'
        'author: "Nama Mahasiswa"\n'
        'nim: "30000000000000"\n'
        "structure: assignment\n"
        "format: undip-msi\n"
        'year: "2026"\n'
        "---\n"
        "# Pendahuluan\n\n"
        "Teks dengan sitasi [@pandoc2024].\n\n"
        "![Logo](gambar/body.jpg)\n\n"
        "# Pembahasan\n\n"
        "Isi pembahasan.\n\n"
        "# Penutup\n\n"
        "Isi penutup.\n",
        encoding="utf-8",
    )
    return document


@pytest.mark.skipif(PANDOC is None, reason=SKIP_REASON)
def test_pandoc_nyata_menghasilkan_docx_valid(tmp_path: Path) -> None:
    document_path = _write_project(tmp_path)
    project = load_project(document_path)
    markdown_text = render_front_matter(
        project.document,
        project.structure,
        project.format,
    )

    workspace = Workspace(root=document_path.parent / ".laporan-build", keep=True)
    workspace.ensure()
    markdown_input = workspace.path("front_matter.md")
    markdown_input.write_text(markdown_text, encoding="utf-8")
    reference = workspace.path("reference.docx")
    build_reference_docx(
        project.format.assets.reference_docx,
        reference,
        project.format,
    )
    artifacts = ArtifactStore()
    artifacts.put("markdown", markdown_input)
    ctx = SimpleNamespace(
        document=project.document,
        structure=project.structure,
        format=project.format,
        options=SimpleNamespace(target="docx", keep=True),
        workspace=workspace,
        package=None,
        artifacts=artifacts,
        reference_docx=reference,
        glossary=project.assets.glossary,
        word=None,
        pandoc=PANDOC,
        logger=logging.getLogger("test.pandoc.integration"),
        dry_run=False,
    )

    result = PandocStage().run(ctx)

    output = workspace.path("Tugas.docx")
    assert result.status == "ok"
    assert output.is_file()
    assert zipfile.is_zipfile(output)
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "PENDAHULUAN" in document_xml
    assert "UJI PIPELINE MINI" in document_xml
    assert "MacFarlane" in document_xml
    assert any(name.startswith("word/media/") for name in names)
    # Sampul/front matter adalah milik stage front_matter; Pandoc tidak boleh
    # menambahkan title block dari metadata.
    assert 'w:val="Title"' not in document_xml
    # TOC field ditulis stages/toc.py, bukan Pandoc.
    assert ("TOC " + chr(92)) not in document_xml
    assert isinstance(ctx.package, DocumentPackage)
