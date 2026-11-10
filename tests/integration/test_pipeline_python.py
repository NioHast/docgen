"""Integrasi pipeline Python: satu pass DOCX dari contoh repo.

Tes ini menjalankan stage nyata (Pandoc, mmdc, dan Word bila tersedia) untuk
``examples/assignment-single/document.md``. Output ditulis ke ``out/`` yang
di-ignore Git, sama seperti perintah ``docgen build``.
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from docgen.document import load_project
from docgen.docx.package import DocumentPackage
from docgen.features.adeu.manifest import load_manifest
from docgen.pipeline import CANONICAL_ORDER, BuildOptions, Pipeline, StageName
from docgen.stages.mermaid import find_mmdc
from docgen.stages.pandoc import find_pandoc

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "assignment-single" / "document.md"
PANDOC = find_pandoc()
MMDC = find_mmdc()
SKIP_REASON = "Pandoc dan mmdc diperlukan untuk membangun contoh assignment"


def _record_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    commands: list[list[str]] = []
    original = subprocess.run

    def run(command, *args, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(command, (list, tuple)):
            commands.append([str(part) for part in command])
        else:
            commands.append([str(command)])
        return original(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    return commands


def _record_package_io(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Path], list[Path]]:
    loads: list[Path] = []
    saves: list[Path] = []
    real_load = DocumentPackage.load
    real_save = DocumentPackage.save

    def load(cls, path, **kwargs):  # type: ignore[no-untyped-def]
        loads.append(Path(path))
        return real_load(path, **kwargs)

    def save(self, path, **kwargs):  # type: ignore[no-untyped-def]
        saves.append(Path(path))
        return real_save(self, path, **kwargs)

    monkeypatch.setattr(DocumentPackage, "load", classmethod(load))
    monkeypatch.setattr(DocumentPackage, "save", save)
    return loads, saves


@pytest.mark.skipif(
    PANDOC is None or MMDC is None,
    reason=SKIP_REASON,
)
def test_build_contoh_assignment_lewat_pipeline_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert EXAMPLE.is_file()
    report_name = load_project(EXAMPLE).document.metadata.report_name
    commands = _record_subprocess(monkeypatch)
    loads, saves = _record_package_io(monkeypatch)

    result = Pipeline().run(EXAMPLE, BuildOptions(target="docx"))

    assert result.docx is not None
    output = result.docx
    assert output == EXAMPLE.parent / "out" / f"{report_name}.docx"
    assert output.is_file()
    assert zipfile.is_zipfile(output)

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert any(name.startswith("word/media/") for name in names)
    assert "Tabel 2.1" in document_xml
    assert "Gambar 2.1" in document_xml
    assert not any(name.endswith("docx.lua") for name in names)

    # Trust boundary: kode pipeline tidak boleh mengambil skrip dari folder
    # input. Periksa argv executable, bukan teks dokumen (contoh memang
    # menyebut build-docx.sh di naskahnya).
    for command in commands:
        executable = Path(command[0]).name.lower()
        assert executable not in {"build-docx.sh", "build.sh", "docx.lua"}
        lowered = [part.lower() for part in command]
        assert not any("docx.lua" in part for part in lowered)
        assert not any(part.startswith("--lua-filter") for part in lowered)

    # Satu load target (output Pandoc) dan satu save target. style_reference
    # boleh load/save reference.docx karena objeknya berbeda.
    target_saves = [path for path in saves if path.name == f"{report_name}.docx"]
    assert len(target_saves) == 1
    assert not any(path.name == f"{report_name}.docx" for path in loads)

    assert result.manifest is not None
    manifest_path = EXAMPLE.parent / ".laporan" / "manifest.json"
    assert result.manifest == manifest_path
    manifest = load_manifest(manifest_path)
    assert manifest.docx == f"{report_name}.docx"
    assert len(manifest) > 0
    assert manifest[0].id == "p0001"

    stages = [stage.stage for stage in result.stages]
    assert stages == [name.value for name in CANONICAL_ORDER]
    statuses = {stage.stage: stage.status for stage in result.stages}
    assert statuses[StageName.TERMS.value] == "skipped"
    assert statuses[StageName.TOC.value] == "skipped"
    assert statuses[StageName.LISTS.value] == "skipped"
    assert statuses[StageName.PDF.value] == "skipped"

    # Workspace tanpa --keep dibersihkan setelah build.
    assert not (EXAMPLE.parent / ".laporan-build").exists()


@pytest.mark.skipif(
    PANDOC is None or MMDC is None,
    reason=SKIP_REASON,
)
def test_build_no_adeu_tidak_menulis_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "proyek"
    project.mkdir()
    shutil.copyfile(EXAMPLE, project / "document.md")
    shutil.copytree(EXAMPLE.parent / "gambar", project / "gambar")
    shutil.copyfile(EXAMPLE.parent / "references.bib", project / "references.bib")

    result = Pipeline().run(
        project / "document.md",
        BuildOptions(target="docx", adeu=False),
    )

    assert result.docx is not None and result.docx.is_file()
    assert result.manifest is None
    assert not (project / ".laporan" / "manifest.json").exists()
    with zipfile.ZipFile(result.docx) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert "p0001" not in document_xml
