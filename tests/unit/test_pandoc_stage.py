"""Tes unit stage ``pandoc``: command builder, metadata, dan fake Pandoc."""

import json
import logging
import os
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from docgen.config import load_format
from docgen.docx import DocumentPackage
from docgen.pipeline import ArtifactStore, StageName, Workspace, canonical_prefix
from docgen.stages.pandoc import (
    PandocError,
    PandocStage,
    build_pandoc_command,
    build_pandoc_metadata,
    find_pandoc,
    resolve_bibliography,
    write_metadata_file,
)

FORMAT_ID = "undip-msi"


@pytest.fixture(scope="module")
def format_spec():
    return load_format(FORMAT_ID)


def _project(tmp_path: Path) -> Path:
    directory = tmp_path / "project"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "references.bib").write_text(
        "@book{pandoc2024,\n"
        "  author = {MacFarlane, John},\n"
        "  title = {Pandoc},\n"
        "  year = {2024}\n"
        "}\n",
        encoding="utf-8",
    )
    return directory


def _document(
    project: Path,
    *,
    bibliography: str | None = "references.bib",
    report_name: str = "Tugas",
):
    path = project / "document.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Pendahuluan\n\nTeks dengan sitasi [@pandoc2024].\n",
        encoding="utf-8",
    )
    return SimpleNamespace(
        path=path.resolve(),
        body="# Pendahuluan\n\nTeks dengan sitasi [@pandoc2024].\n",
        metadata=SimpleNamespace(lang="id-ID", report_name=report_name),
        bibliography=bibliography,
    )


def _reference(tmp_path: Path, format_spec) -> Path:
    reference = tmp_path / "reference.docx"
    shutil.copyfile(format_spec.assets.reference_docx, reference)
    return reference


def _fake_pandoc(
    tmp_path: Path,
    reference: Path,
    *,
    fail: bool = False,
) -> tuple[Path, Path]:
    """Buat fake Pandoc Python yang menyalin DOCX valid dan merekam argv."""

    record = tmp_path / "pandoc-argv.json"
    script = tmp_path / "fake-pandoc.py"
    script.write_text(
        "import json\n"
        "import shutil\n"
        "import sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        f"Path({str(record)!r}).write_text(json.dumps(args), encoding='utf-8')\n"
        f"if {fail!r}:\n"
        "    print('fake pandoc gagal', file=sys.stderr)\n"
        "    raise SystemExit(3)\n"
        "output = Path(args[args.index('-o') + 1])\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        f"shutil.copyfile({str(reference)!r}, output)\n",
        encoding="utf-8",
    )
    return script, record


def _context(
    tmp_path: Path,
    *,
    format_spec,
    fake_pandoc: Path,
    reference: Path,
    markdown: bool = True,
    document=None,
) -> SimpleNamespace:
    project = _project(tmp_path)
    workspace = Workspace(root=(project / ".laporan-build").resolve(), keep=True)
    workspace.ensure()
    ctx = SimpleNamespace(
        document=document or _document(project),
        format=format_spec,
        options=SimpleNamespace(target="docx", keep=True),
        workspace=workspace,
        package=None,
        artifacts=ArtifactStore(),
        reference_docx=reference,
        glossary=None,
        word=None,
        pandoc=str(fake_pandoc),
        logger=logging.getLogger("test.pandoc"),
        dry_run=False,
    )
    if markdown:
        path = workspace.path("front_matter.md")
        path.write_text(
            "# Pendahuluan\n\nTeks dengan sitasi [@pandoc2024].\n",
            encoding="utf-8",
        )
        ctx.artifacts.put("markdown", path)
    return ctx


# ---------------------------------------------------------------------------
# Metadata stage dan command builder
# ---------------------------------------------------------------------------


def test_stage_metadata_kanonik() -> None:
    assert PandocStage.name is StageName.PANDOC
    assert PandocStage.order == 40
    assert PandocStage.requires == canonical_prefix(StageName.PANDOC)
    assert PandocStage.mutates == frozenset({"package"})
    assert PandocStage.idempotent is True


def test_build_command_tanpa_lua_dan_toc_pandoc(tmp_path: Path) -> None:
    command = build_pandoc_command(
        "pandoc",
        markdown=tmp_path / "input.md",
        output=tmp_path / "output.docx",
        reference_docx=tmp_path / "reference.docx",
        bibliography=tmp_path / "references.bib",
        csl=tmp_path / "citation.csl",
        metadata_file=tmp_path / "metadata.yml",
        resource_paths=(tmp_path / "gambar", tmp_path / "workspace"),
    )

    assert command[0] == "pandoc"
    assert str(tmp_path / "input.md") in command
    assert "--top-level-division=chapter" in command
    assert "--metadata=toc=false" in command
    assert "--citeproc" in command
    assert f"--reference-doc={tmp_path / 'reference.docx'}" in command
    assert f"--bibliography={tmp_path / 'references.bib'}" in command
    assert f"--csl={tmp_path / 'citation.csl'}" in command
    assert f"--metadata-file={tmp_path / 'metadata.yml'}" in command
    assert any(item.startswith("--resource-path=") for item in command)
    assert command[-2:] == ["-o", str(tmp_path / "output.docx")]

    # TOC/daftar/heading numbering adalah milik stage post-Pandoc.
    assert "--toc" not in command
    assert not any("--lua-filter" in item for item in command)
    assert not any("docx.lua" in item for item in command)


def test_build_command_resource_path_memakai_separator_platform(
    tmp_path: Path,
) -> None:
    command = build_pandoc_command(
        "pandoc",
        markdown=tmp_path / "input.md",
        output=tmp_path / "output.docx",
        resource_paths=(tmp_path / "a", tmp_path / "b"),
    )
    resource = next(item for item in command if item.startswith("--resource-path="))
    assert resource == (f"--resource-path={tmp_path / 'a'}{os.pathsep}{tmp_path / 'b'}")


def test_build_command_citeproc_opsional(tmp_path: Path) -> None:
    command = build_pandoc_command(
        "pandoc",
        markdown=tmp_path / "input.md",
        output=tmp_path / "output.docx",
        citeproc=False,
    )
    assert "--citeproc" not in command


def test_metadata_front_matter_tidak_mengirim_title_block(
    tmp_path: Path,
    format_spec,
) -> None:
    project = _project(tmp_path)
    document = _document(project)
    metadata = build_pandoc_metadata(
        document,
        format_spec,
        bibliography=Path("references.bib"),
    )

    assert metadata["lang"] == "id-ID"
    assert metadata["reference-section-title"] == format_spec.bibliography_style.heading
    assert "title" not in metadata
    assert "author" not in metadata
    assert "date" not in metadata


def test_write_metadata_file_deterministik(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yml"
    metadata = {"lang": "id-ID", "reference-section-title": "DAFTAR PUSTAKA"}

    write_metadata_file(path, metadata)
    first = path.read_text(encoding="utf-8")
    write_metadata_file(path, metadata)
    second = path.read_text(encoding="utf-8")

    assert first == second
    assert json.loads(first) == metadata
    assert "\r" not in first


def test_find_pandoc_path_eksplisit(tmp_path: Path) -> None:
    fake = tmp_path / "fake-pandoc.py"
    fake.write_text("print('ok')\n", encoding="utf-8")
    assert find_pandoc(fake) == str(fake)
    assert find_pandoc(tmp_path / "tidak-ada-pandoc") is None


def test_resolve_bibliography_dari_dokumen_dan_format(
    tmp_path: Path,
    format_spec,
) -> None:
    project = _project(tmp_path)
    document = _document(project)
    assert resolve_bibliography(document, format_spec) == (project / "references.bib").resolve()

    # Dokumen tidak menyebut bibliography; fallback memakai nilai format yang
    # dicari relatif terhadap direktori format.
    format_dir = tmp_path / "format"
    format_dir.mkdir()
    (format_dir / "references.bib").write_text("", encoding="utf-8")
    (format_dir / "format.yml").write_text("format: test\n", encoding="utf-8")
    other_project = tmp_path / "other"
    other_project.mkdir()
    other_document = _document(other_project, bibliography=None)
    other_format = SimpleNamespace(
        path=format_dir / "format.yml",
        citation=SimpleNamespace(bibliography="references.bib", csl=Path("x.csl")),
    )
    assert (
        resolve_bibliography(other_document, other_format)
        == (format_dir / "references.bib").resolve()
    )

    # Tanpa bibliography eksplisit dan tanpa aset format, dokumen tetap boleh
    # dibangun tanpa sitasi.
    missing_project = tmp_path / "missing"
    missing_project.mkdir()
    missing_document = _document(missing_project, bibliography=None)
    only_format = SimpleNamespace(
        path=format_dir / "format.yml",
        citation=SimpleNamespace(bibliography="tidak-ada.bib", csl=Path("x.csl")),
    )
    assert resolve_bibliography(missing_document, only_format) is None


# ---------------------------------------------------------------------------
# Eksekusi dengan fake Pandoc
# ---------------------------------------------------------------------------


def test_stage_output_memakai_report_name(
    tmp_path: Path,
    format_spec,
) -> None:
    reference = _reference(tmp_path, format_spec)
    fake, _ = _fake_pandoc(tmp_path, reference)
    project = _project(tmp_path)
    ctx = _context(
        tmp_path,
        format_spec=format_spec,
        fake_pandoc=fake,
        reference=reference,
        document=_document(project, report_name="Laporan Akhir"),
    )

    PandocStage().run(ctx)

    output = Path(ctx.workspace.path("Laporan Akhir.docx"))
    assert output.is_file()
    assert ctx.artifacts.require("pandoc_docx") == output


def test_stage_menjalankan_fake_pandoc_dan_menghasilkan_docx(
    tmp_path: Path,
    format_spec,
) -> None:
    reference = _reference(tmp_path, format_spec)
    fake, record = _fake_pandoc(tmp_path, reference)
    ctx = _context(
        tmp_path,
        format_spec=format_spec,
        fake_pandoc=fake,
        reference=reference,
    )

    result = PandocStage().run(ctx)

    output = ctx.workspace.path("Tugas.docx")
    assert result.status == "ok"
    assert result.changed is True
    assert output.is_file()
    assert zipfile.is_zipfile(output)
    with zipfile.ZipFile(output) as archive:
        assert "word/document.xml" in archive.namelist()
    assert isinstance(ctx.package, DocumentPackage)
    assert "pandoc_docx" in ctx.artifacts.keys()  # noqa: SIM118 - fake artifacts bukan Mapping
    assert result.artifacts[0] == output

    args = json.loads(record.read_text(encoding="utf-8"))
    assert "--citeproc" in args
    assert "--top-level-division=chapter" in args
    assert "--metadata=toc=false" in args
    assert f"--reference-doc={reference}" in args
    assert f"--bibliography={(tmp_path / 'project' / 'references.bib').resolve()}" in args
    assert f"--csl={format_spec.citation.csl}" in args
    assert f"--metadata-file={ctx.workspace.path('pandoc-metadata.yml')}" in args
    command_output = Path(args[args.index("-o") + 1])
    assert command_output.parent == ctx.workspace.root
    assert command_output.name.endswith(".docx")
    resource = next(item for item in args if item.startswith("--resource-path="))
    assert str((tmp_path / "project").resolve()) in resource
    assert not any("--lua-filter" in item for item in args)
    assert not any("docx.lua" in item for item in args)
    assert "--toc" not in args

    # Metadata file tidak memuat title/author sehingga tidak ada title block
    # ganda di samping sampul yang sudah dirender front_matter.
    metadata_file = ctx.workspace.path("pandoc-metadata.yml")
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["lang"] == "id-ID"
    assert "title" not in metadata
    assert "author" not in metadata


def test_stage_kedua_kali_idempoten(
    tmp_path: Path,
    format_spec,
) -> None:
    reference = _reference(tmp_path, format_spec)
    fake, _ = _fake_pandoc(tmp_path, reference)
    ctx = _context(
        tmp_path,
        format_spec=format_spec,
        fake_pandoc=fake,
        reference=reference,
    )
    stage = PandocStage()

    first = stage.run(ctx)
    second = stage.run(ctx)

    assert first.changed is True
    assert second.changed is False
    assert second.status == "ok"


def test_stage_gagal_tanpa_markdown_artifact(
    tmp_path: Path,
    format_spec,
) -> None:
    reference = _reference(tmp_path, format_spec)
    fake, _ = _fake_pandoc(tmp_path, reference)
    ctx = _context(
        tmp_path,
        format_spec=format_spec,
        fake_pandoc=fake,
        reference=reference,
        markdown=False,
    )

    with pytest.raises(PandocError, match="front_matter"):
        PandocStage().run(ctx)


def test_stage_gagal_tanpa_reference_derived(
    tmp_path: Path,
    format_spec,
) -> None:
    reference = _reference(tmp_path, format_spec)
    fake, _ = _fake_pandoc(tmp_path, reference)
    ctx = _context(
        tmp_path,
        format_spec=format_spec,
        fake_pandoc=fake,
        reference=reference,
    )
    ctx.reference_docx = None

    with pytest.raises(PandocError, match="style_reference"):
        PandocStage().run(ctx)


def test_stage_gagal_bibliography_hilang(
    tmp_path: Path,
    format_spec,
) -> None:
    reference = _reference(tmp_path, format_spec)
    fake, _ = _fake_pandoc(tmp_path, reference)
    ctx = _context(
        tmp_path,
        format_spec=format_spec,
        fake_pandoc=fake,
        reference=reference,
        document=_document(tmp_path / "project", bibliography="hilang.bib"),
    )

    with pytest.raises(PandocError, match="bibliography tidak ditemukan"):
        PandocStage().run(ctx)


def test_stage_gagal_pandoc_hilang(
    tmp_path: Path,
    format_spec,
) -> None:
    reference = _reference(tmp_path, format_spec)
    fake, _ = _fake_pandoc(tmp_path, reference)
    ctx = _context(
        tmp_path,
        format_spec=format_spec,
        fake_pandoc=fake,
        reference=reference,
    )
    ctx.pandoc = "pandoc-tidak-ada-di-path-xyz"

    from docgen.errors import ToolMissingError

    with pytest.raises(ToolMissingError, match="Pandoc"):
        PandocStage().run(ctx)


def test_stage_gagal_pandoc_returncode_nonzero(
    tmp_path: Path,
    format_spec,
) -> None:
    reference = _reference(tmp_path, format_spec)
    fake, _ = _fake_pandoc(tmp_path, reference, fail=True)
    ctx = _context(
        tmp_path,
        format_spec=format_spec,
        fake_pandoc=fake,
        reference=reference,
    )

    with pytest.raises(PandocError, match="fake pandoc gagal"):
        PandocStage().run(ctx)

    assert not ctx.workspace.path("Tugas.docx").exists()
    assert not ctx.workspace.path("Tugas.tmp.docx").exists()
