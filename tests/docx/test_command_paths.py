"""Tes kontrak path API ``build_docx``: expanduser dan output yang hilang."""

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from autooffice.docx import command
from autooffice.docx.command import build_docx
from autooffice.docx.errors import OutputError
from autooffice.docx.stages import office

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "docx" / "minimal"


class FakePipeline:
    """Pipeline palsu yang mencatat path masuk dan membuat DOCX tiruan."""

    def __init__(self, *, write_docx: bool = True) -> None:
        self.write_docx = write_docx
        self.calls: list[tuple[Path, Path | None]] = []

    def run(
        self,
        document_path: Path,
        options: object,
        *,
        output_dir: Path | None = None,
    ) -> SimpleNamespace:
        self.calls.append((Path(document_path), output_dir))
        directory = Path(output_dir) if output_dir is not None else Path(document_path).parent
        docx_path = directory / "Tugas.docx"
        if self.write_docx:
            directory.mkdir(parents=True, exist_ok=True)
            docx_path.write_bytes(b"PK\x03\x04stub")
        return SimpleNamespace(
            document=Path(document_path),
            docx=docx_path,
            manifest=None,
            warnings=(),
            kept_workspace=None,
        )


def test_build_docx_expands_input_and_output_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    (home / "project").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    fake = FakePipeline()
    monkeypatch.setattr(command, "Pipeline", lambda: fake)

    result = build_docx(Path("~/project/document.md"), out=Path("~/out"))

    expected_document = Path("~/project/document.md").expanduser()
    expected_output = Path("~/out").expanduser()
    assert fake.calls == [(expected_document, expected_output)]
    assert result.docx == expected_output / "Tugas.docx"
    assert result.terms is None


def test_build_docx_raises_when_result_docx_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakePipeline(write_docx=False)
    monkeypatch.setattr(command, "Pipeline", lambda: fake)

    with pytest.raises(OutputError, match="DOCX tidak terbentuk") as excinfo:
        build_docx(tmp_path / "document.md", out=tmp_path / "out")

    assert excinfo.value.code == "OUTPUT-DOCX"


def test_build_docx_rejects_output_dir_inside_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(office, "word_available", lambda: False)
    document = tmp_path / "project" / "document.md"
    shutil.copytree(FIXTURE, document.parent)
    workspace = document.parent / ".laporan-build"

    with pytest.raises(OutputError, match="tidak boleh berada di dalam workspace") as excinfo:
        build_docx(document, out=workspace, keep_intermediate=False)

    assert excinfo.value.code == "OUTPUT-WORKSPACE"
    assert not workspace.exists()
