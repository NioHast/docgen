"""Tes workflow satu berkas Markdown (``build-file``)."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laporan import manifest as manifest_mod  # noqa: E402
from laporan import mermaid as mermaid_mod  # noqa: E402
from laporan import singlefile  # noqa: E402


DEFAULT_FRONT_MATTER = """\
title: "Analisis Pipeline Markdown"
author: "Nama Mahasiswa"
nim: "30000000000000"
structure: assignment
format: undip-msi
toc: false
bibliography: references.bib
"""

DEFAULT_BODY = """\
# Pendahuluan

Latar belakang singkat dengan sitasi [@pandoc2024].

# Pembahasan

Analisis utama.

# Penutup

Kesimpulan.
"""

MERMAID_BODY = (
    "# Pendahuluan\n"
    "\n"
    "Sebelum diagram.\n"
    "\n"
    '```{.mermaid caption="Diagram alur"}\n'
    "flowchart LR\n"
    "  A --> B\n"
    "```\n"
    "\n"
    "Sesudah diagram.\n"
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

FAKE_MMDC = """\
from __future__ import annotations

import base64
import pathlib
import sys

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

arguments = sys.argv[1:]
source = pathlib.Path(arguments[arguments.index("-i") + 1])
target = pathlib.Path(arguments[arguments.index("-o") + 1])
source.read_text(encoding="utf-8")
if target.parent.name != "gambar" or not target.name.startswith("mermaid-"):
    print(f"fake mmdc: path output tidak sesuai: {target}", file=sys.stderr)
    raise SystemExit(3)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(PNG)
"""


def make_fake_mmdc(tmp_path: Path) -> Path:
    """Buat skrip mmdc palsu yang menghasilkan PNG 1x1 valid."""

    script = tmp_path / "fake_mmdc.py"
    script.write_text(FAKE_MMDC, encoding="utf-8", newline="\n")
    return script


def pandoc_available() -> bool:
    if shutil.which("pandoc"):
        return True
    local_appdata = os.environ.get("LOCALAPPDATA")
    return bool(
        local_appdata
        and (Path(local_appdata) / "Pandoc" / "pandoc.exe").is_file()
    )


def write_document(
    tmp_path: Path,
    *,
    front_matter: str = DEFAULT_FRONT_MATTER,
    body: str = DEFAULT_BODY,
    bibliography: bool = True,
) -> Path:
    document = tmp_path / "document.md"
    document.write_text(
        f"---\n{front_matter}---\n\n{body}",
        encoding="utf-8",
        newline="\n",
    )
    if bibliography:
        (tmp_path / "references.bib").write_text(
            "@manual{pandoc2024,\n"
            "  author = {MacFarlane, John},\n"
            "  title  = {Pandoc: A Universal Document Converter},\n"
            "  year   = {2024}\n"
            "}\n",
            encoding="utf-8",
        )
    return document


def fake_runner(record: list[tuple[list[str], str, dict[str, str]]] | None = None):
    def run(command, *, cwd, env, check):
        if record is not None:
            record.append((list(command), str(cwd), dict(env)))
        outdir = Path(command[-1])
        report = env["LAPORAN_REPORT_NAME"]
        (outdir / f"{report}.docx").write_bytes(b"docx-stub")
        (outdir / f"{report}.pdf").write_bytes(b"pdf-stub")
        return subprocess.CompletedProcess(command, 0)

    return run


def test_parse_front_matter_dan_body_utuh(tmp_path: Path) -> None:
    document = write_document(tmp_path)

    parsed = singlefile.parse_document(document)

    assert parsed.path == document.resolve()
    assert parsed.front_matter["title"] == "Analisis Pipeline Markdown"
    assert parsed.front_matter["author"] == "Nama Mahasiswa"
    assert "# Pendahuluan" in parsed.body
    assert "# Pembahasan" in parsed.body
    assert "# Penutup" in parsed.body
    assert "---" not in parsed.body.splitlines()[:1]


def test_materialize_metadata_dan_aset(tmp_path: Path) -> None:
    document = write_document(tmp_path)
    (tmp_path / "gambar").mkdir()
    (tmp_path / "gambar" / "diagram.png").write_bytes(b"png")

    materialized = singlefile.materialize(document)

    assert materialized.workspace == (tmp_path / singlefile.WORKSPACE_DIRNAME).resolve()
    assert materialized.metadata_path.is_file()
    assert materialized.cover_path.is_file()
    assert materialized.chapter_path.is_file()
    assert materialized.bibliography_path.is_file()
    assert (materialized.workspace / "writing" / "istilah.tsv").is_file()
    assert (materialized.images_dir / "diagram.png").is_file()

    metadata = manifest_mod.load_yaml(materialized.metadata_path)
    assert metadata["title"] == "Analisis Pipeline Markdown"
    assert metadata["author"] == [
        {"name": "Nama Mahasiswa", "nim": "30000000000000"}
    ]
    assert metadata["preset"] == "undip-msi-proposal"
    assert metadata["toc"] is False
    assert metadata["lang"] == "id-ID"
    assert "structure" not in metadata
    assert "format" not in metadata
    assert "bibliography" not in metadata

    metadata_text = materialized.metadata_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in metadata_text
    assert "C:\\" not in metadata_text
    assert "/home/" not in metadata_text

    chapter_text = materialized.chapter_path.read_text(encoding="utf-8")
    assert "# Pendahuluan" in chapter_text
    assert "# Pembahasan" in chapter_text
    assert "# Penutup" in chapter_text
    assert "[@pandoc2024]" in chapter_text


def test_front_matter_wajib(tmp_path: Path) -> None:
    document = tmp_path / "tanpa-front-matter.md"
    document.write_text("# Bab\n\nTeks.\n", encoding="utf-8")

    with pytest.raises(singlefile.SingleFileError, match="front matter wajib"):
        singlefile.parse_document(document)


def test_toc_benar_diteruskan(tmp_path: Path) -> None:
    document = write_document(
        tmp_path,
        front_matter=(
            'title: "Judul"\n'
            'author: "Nama"\n'
            "structure: assignment\n"
            "format: undip-msi\n"
            "toc: true\n"
            "bibliography: references.bib\n"
        ),
    )

    materialized = singlefile.materialize(document)

    assert materialized.toc is True
    assert manifest_mod.load_yaml(materialized.metadata_path)["toc"] is True


def test_front_matter_yaml_tidak_valid(tmp_path: Path) -> None:
    document = tmp_path / "rusak.md"
    document.write_text(
        '---\ntitle: "Judul"\n  author: "Nama"\n---\n\n# Bab\n',
        encoding="utf-8",
    )

    with pytest.raises(singlefile.SingleFileError, match="tidak valid"):
        singlefile.parse_document(document)


def test_judul_dan_author_wajib(tmp_path: Path) -> None:
    document = write_document(
        tmp_path,
        front_matter='author: "Nama"\nbibliography: references.bib\n',
    )

    with pytest.raises(singlefile.SingleFileError, match="'title'"):
        singlefile.materialize(document)

    document = write_document(
        tmp_path,
        front_matter='title: "Judul"\nbibliography: references.bib\n',
    )

    with pytest.raises(singlefile.SingleFileError, match="'author'"):
        singlefile.materialize(document)


def test_bibliografi_hilang_ditolak(tmp_path: Path) -> None:
    document = write_document(tmp_path, bibliography=False)

    with pytest.raises(singlefile.SingleFileError, match="Bibliografi tidak ditemukan"):
        singlefile.materialize(document)


def test_bibliografi_absolut_ditolak(tmp_path: Path) -> None:
    bibliography = tmp_path / "references.bib"
    bibliography.write_text("@manual{x, title={X}}\n", encoding="utf-8")
    document = write_document(
        tmp_path,
        front_matter=(
            'title: "Judul"\n'
            'author: "Nama"\n'
            "structure: assignment\n"
            "format: undip-msi\n"
            "toc: false\n"
            f'bibliography: "{bibliography.as_posix()}"\n'
        ),
        bibliography=False,
    )

    with pytest.raises(singlefile.SingleFileError, match="path relatif"):
        singlefile.materialize(document)


def test_gambar_valid_disalin(tmp_path: Path) -> None:
    document = write_document(
        tmp_path,
        body=(
            "# Bab\n\n"
            "![Diagram alur](gambar/diagram.png)\n\n"
            "Teks.\n"
        ),
    )
    (tmp_path / "gambar").mkdir()
    (tmp_path / "gambar" / "diagram.png").write_bytes(b"png")

    materialized = singlefile.materialize(document)

    assert (materialized.images_dir / "diagram.png").is_file()


def test_gambar_hilang_ditolak(tmp_path: Path) -> None:
    document = write_document(
        tmp_path,
        body="# Bab\n\n![Diagram](gambar/hilang.png)\n",
    )

    with pytest.raises(singlefile.SingleFileError, match="gambar tidak ditemukan"):
        singlefile.materialize(document)


def test_gambar_keluar_folder_ditolak(tmp_path: Path) -> None:
    document = write_document(
        tmp_path,
        body="# Bab\n\n![Diagram](../rahasia.png)\n",
    )

    with pytest.raises(singlefile.SingleFileError, match="tidak boleh keluar"):
        singlefile.materialize(document)


def test_gambar_absolut_ditolak(tmp_path: Path) -> None:
    document = write_document(
        tmp_path,
        body="# Bab\n\n![Diagram](C:/rahasia.png)\n",
    )

    with pytest.raises(singlefile.SingleFileError, match="path relatif"):
        singlefile.materialize(document)


def test_gambar_di_luar_folder_gambar_ditolak(tmp_path: Path) -> None:
    document = write_document(
        tmp_path,
        body="# Bab\n\n![Diagram](diagram.png)\n",
    )
    (tmp_path / "diagram.png").write_bytes(b"png")

    with pytest.raises(singlefile.SingleFileError, match="folder 'gambar/'"):
        singlefile.materialize(document)


def test_gambar_di_dalam_code_fence_diabaikan(tmp_path: Path) -> None:
    document = write_document(
        tmp_path,
        body=(
            "# Bab\n\n"
            "```markdown\n"
            "![Contoh](gambar/tidak-ada.png)\n"
            "```\n\n"
            "Teks.\n"
        ),
    )

    materialized = singlefile.materialize(document)

    assert materialized.chapter_path.is_file()


def test_mermaid_dirender_ke_gambar_dan_chapter(tmp_path: Path, monkeypatch) -> None:
    document = write_document(tmp_path, body=MERMAID_BODY)
    fake_mmdc = make_fake_mmdc(tmp_path)
    monkeypatch.setattr(
        mermaid_mod, "find_mmdc", lambda explicit=None: str(fake_mmdc)
    )

    materialized = singlefile.materialize(document)

    images = list((tmp_path / "gambar").glob("mermaid-*.png"))
    assert len(images) == 1
    assert images[0].read_bytes() == PNG_1X1
    assert (materialized.images_dir / images[0].name).read_bytes() == PNG_1X1

    chapter = materialized.chapter_path.read_text(encoding="utf-8")
    assert "```{.mermaid" not in chapter
    assert f"![Diagram alur](gambar/{images[0].name})" in chapter
    assert "Gambar 1.1" not in chapter


def test_tanpa_blok_mermaid_tidak_berubah(tmp_path: Path, monkeypatch) -> None:
    document = write_document(tmp_path)
    original = document.read_bytes()

    def unexpected_mmdc(explicit=None):
        raise AssertionError("mmdc tidak boleh dicari tanpa blok Mermaid")

    monkeypatch.setattr(mermaid_mod, "find_mmdc", unexpected_mmdc)

    parsed = singlefile.parse_document(document)
    materialized = singlefile.materialize(document)

    assert materialized.chapter_path.read_text(encoding="utf-8") == parsed.body
    assert document.read_bytes() == original
    assert not (tmp_path / "gambar").exists()


def test_mermaid_tanpa_mmdc_gagal_dengan_pesan_jelas(
    tmp_path: Path, monkeypatch
) -> None:
    document = write_document(tmp_path, body=MERMAID_BODY)
    monkeypatch.setattr(mermaid_mod, "find_mmdc", lambda explicit=None: None)

    with pytest.raises(singlefile.SingleFileError, match="mmdc tidak ditemukan"):
        singlefile.materialize(document)

    assert not (tmp_path / "gambar").exists()
    assert not (tmp_path / singlefile.WORKSPACE_DIRNAME).exists()


def test_workspace_dibersihkan_setelah_build(tmp_path: Path) -> None:
    document = write_document(tmp_path)

    result = singlefile.build_file(document, runner=fake_runner())

    assert result.outputs == ((tmp_path / "Tugas.docx").resolve(),)
    assert (tmp_path / "Tugas.docx").read_bytes() == b"docx-stub"
    assert not (tmp_path / singlefile.WORKSPACE_DIRNAME).exists()


def test_target_pdf_hanya_menyalin_pdf(tmp_path: Path) -> None:
    document = write_document(tmp_path)

    result = singlefile.build_file(document, target="pdf", runner=fake_runner())

    assert result.targets == ("pdf",)
    assert result.outputs == ((tmp_path / "Tugas.pdf").resolve(),)
    assert (tmp_path / "Tugas.pdf").read_bytes() == b"pdf-stub"
    assert not (tmp_path / "Tugas.docx").exists()


def test_keep_mempertahankan_workspace(tmp_path: Path) -> None:
    document = write_document(tmp_path)

    result = singlefile.build_file(document, keep=True, runner=fake_runner())

    assert result.kept is True
    assert (tmp_path / "Tugas.docx").is_file()
    assert result.workspace.is_dir()
    assert (result.workspace / "metadata.yml").is_file()
    assert (result.workspace / "chapters" / "01.md").is_file()


def test_target_both_dan_environment_pipeline(tmp_path: Path) -> None:
    document = write_document(tmp_path)
    record: list[tuple[list[str], str, dict[str, str]]] = []

    result = singlefile.build_file(
        document,
        target="both",
        runner=fake_runner(record),
    )

    assert [Path(command[1]).name for command, _, _ in record] == [
        "build-docx.sh",
        "build.sh",
    ]
    for command, cwd, env in record:
        outdir = Path(command[-1])
        assert outdir == result.workspace
        assert Path(cwd) == ROOT
        assert env["LAPORAN_METADATA"] == (outdir / "metadata.yml").as_posix()
        assert env["LAPORAN_CHAPTERS"] == (outdir / "chapters").as_posix()
        assert env["LAPORAN_REPORT_NAME"] == "Tugas"
        assert env["LAPORAN_TOC"] == "false"
        assert env["OUTDIR"] == outdir.as_posix()
        assert env["PYTHONUTF8"] == "1"

    assert result.targets == ("docx", "pdf")
    assert result.outputs == (
        (tmp_path / "Tugas.docx").resolve(),
        (tmp_path / "Tugas.pdf").resolve(),
    )


def test_build_gagal_tetapi_workspace_dibersihkan(tmp_path: Path) -> None:
    document = write_document(tmp_path)

    def failing_runner(command, *, cwd, env, check):
        return subprocess.CompletedProcess(command, 7)

    with pytest.raises(singlefile.SingleFileError, match="kode 7"):
        singlefile.build_file(document, runner=failing_runner)

    assert not (tmp_path / singlefile.WORKSPACE_DIRNAME).exists()


def test_report_name_kustom(tmp_path: Path) -> None:
    document = write_document(
        tmp_path,
        front_matter=(
            'title: "Judul"\n'
            'author: "Nama"\n'
            "structure: assignment\n"
            "format: undip-msi\n"
            "toc: false\n"
            "bibliography: references.bib\n"
            'report_name: "Laporan Uji"\n'
        ),
    )

    result = singlefile.build_file(document, runner=fake_runner())

    assert result.outputs == ((tmp_path / "Laporan Uji.docx").resolve(),)


@pytest.mark.integration
def test_mermaid_gambar_masuk_docx(tmp_path: Path, monkeypatch) -> None:
    if not pandoc_available():
        pytest.skip("pandoc tidak tersedia")
    if singlefile.platform_mod.find_bash() is None:
        pytest.skip("bash tidak tersedia")

    document = write_document(tmp_path, body=MERMAID_BODY)
    fake_mmdc = make_fake_mmdc(tmp_path)
    monkeypatch.setattr(
        mermaid_mod, "find_mmdc", lambda explicit=None: str(fake_mmdc)
    )

    result = singlefile.build_file(document)

    docx = tmp_path / "Tugas.docx"
    assert result.outputs == (docx.resolve(),)
    with zipfile.ZipFile(docx) as archive:
        media = [
            name
            for name in archive.namelist()
            if name.startswith("word/media/")
        ]
        assert media
        assert any(archive.read(name) == PNG_1X1 for name in media)
        assert b"<w:drawing" in archive.read("word/document.xml")

    images = list((tmp_path / "gambar").glob("mermaid-*.png"))
    assert len(images) == 1
    assert images[0].read_bytes() == PNG_1X1
    assert not (tmp_path / singlefile.WORKSPACE_DIRNAME).exists()


def test_cli_build_file_berkas_tidak_ada_mengembalikan_1(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "laporan.py"),
            "build-file",
            str(tmp_path / "tidak-ada.md"),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "Berkas tidak ditemukan" in completed.stderr


def test_cli_build_file_argparse_target(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "laporan.py"),
            "build-file",
            str(tmp_path / "document.md"),
            "--target",
            "tidak-ada",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--target" in completed.stderr
