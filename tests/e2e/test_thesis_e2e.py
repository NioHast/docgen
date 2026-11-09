"""E2E thesis: perintah ``docgen check`` dan ``docgen build`` dari CLI.

Build memakai ``examples/thesis-single`` yang disalin ke direktori sementara
agar output tidak mengotori repo. PDF hanya diwajibkan bila Microsoft Word
tersedia.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from docgen.features.adeu.manifest import load_manifest
from docgen.stages.mermaid import find_mmdc
from docgen.stages.office import word_available
from docgen.stages.pandoc import find_pandoc

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "thesis-single"
FIXTURE = ROOT / "tests" / "fixtures" / "e2e" / "thesis"
PANDOC = find_pandoc()
MMDC = find_mmdc()
WORD = word_available()
TARGET = "both" if WORD else "docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
TOC_MAIN_RE = re.compile(r"^\s*TOC\s+\\o\b")
TOC_CAPTION_RE = re.compile(r'^\s*TOC\s+\\c\s+"(?P<label>[^"]+)"')


def _run_cli(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH")
    source = str(ROOT / "src")
    environment["PYTHONPATH"] = (
        source if not existing else source + os.pathsep + existing
    )
    return subprocess.run(
        [sys.executable, "-m", "docgen", *arguments],
        cwd=str(cwd or ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )


def _copy_example(destination: Path) -> Path:
    project = destination / "proyek"
    shutil.copytree(
        EXAMPLE,
        project,
        ignore=shutil.ignore_patterns("out", ".laporan*"),
    )
    return project


def _document_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/document.xml"))


def _text(root: etree._Element) -> str:
    return " ".join("".join(root.xpath("//w:t/text()", namespaces=NS)).split())


def _instructions(root: etree._Element) -> list[str]:
    return [
        node.text or ""
        for node in root.xpath("//w:instrText", namespaces=NS)
        if (node.text or "").strip()
    ]


def _headings(root: etree._Element) -> list[str]:
    values: list[str] = []
    for paragraph in root.xpath("//w:p", namespaces=NS):
        styles = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
        if styles and styles[0] == "Heading1":
            text = " ".join(
                "".join(paragraph.xpath(".//w:t/text()", namespaces=NS)).split()
            )
            values.append(text)
    return values


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def _style_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return etree.fromstring(archive.read("word/styles.xml"))


def _toc3_has_dot_leader(path: Path) -> bool:
    root = _style_root(path)
    styles = {
        style.get(f"{{{W_NS}}}styleId"): style
        for style in root.xpath("//w:style", namespaces=NS)
    }
    current = styles.get("TOC3")
    seen: set[str] = set()
    while current is not None:
        if any(
            tab.get(f"{{{W_NS}}}leader") == "dot"
            for tab in current.xpath(".//w:tab", namespaces=NS)
        ):
            return True
        based_on = current.xpath("./w:basedOn/@w:val", namespaces=NS)
        if not based_on or based_on[0] in seen:
            return False
        seen.add(based_on[0])
        current = styles.get(based_on[0])
    return False


def _toc_entry_with_prefix(
    root: etree._Element,
    style_id: str,
    prefix: str,
) -> etree._Element | None:
    for paragraph in root.xpath("//w:p", namespaces=NS):
        styles = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
        if styles and styles[0] == style_id:
            text = " ".join(_paragraph_text(paragraph).split())
            if text.startswith(prefix):
                return paragraph
    return None


@pytest.fixture(scope="module")
def built_example(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, subprocess.CompletedProcess[str]]:
    if PANDOC is None or MMDC is None:
        pytest.skip("Pandoc dan mmdc diperlukan untuk membangun contoh thesis")
    project = _copy_example(tmp_path_factory.mktemp("thesis-e2e"))
    completed = _run_cli(
        "build",
        str(project / "document.md"),
        "--target",
        TARGET,
    )
    return project, completed


def test_build_thesis_menghasilkan_docx_pdf_dan_manifest(
    built_example: tuple[Path, subprocess.CompletedProcess[str]],
) -> None:
    project, completed = built_example
    assert completed.returncode == 0, completed.stderr
    docx = project / "Tugas.docx"
    assert docx.is_file() and zipfile.is_zipfile(docx)
    if TARGET == "both":
        pdf = project / "Tugas.pdf"
        assert pdf.is_file() and pdf.read_bytes().startswith(b"%PDF-")

    manifest_path = project / ".laporan" / "manifest.json"
    assert manifest_path.is_file()
    manifest = load_manifest(manifest_path)
    assert len(manifest) > 0
    assert any(paragraph.source_file for paragraph in manifest)

    root = _document_root(docx)
    instructions = _instructions(root)
    assert len([value for value in instructions if TOC_MAIN_RE.match(value)]) == 1
    labels = {
        match.group("label")
        for value in instructions
        if (match := TOC_CAPTION_RE.match(value))
    }
    assert labels == {"Tabel", "Gambar"}

    text = _text(root)
    assert "Tabel 2.1" in text
    assert "Gambar 4.1" in text

    headings = _headings(root)
    assert any(value.casefold() == "lampiran" for value in headings)
    assert not any(value.upper().startswith("BAB VI") for value in headings)


def test_check_thesis_contoh_valid() -> None:
    completed = _run_cli("check", str(EXAMPLE / "document.md"))
    assert completed.returncode == 0, completed.stderr
    assert "[OK]" in completed.stdout


def test_check_menolak_tabel_tanpa_caption(tmp_path: Path) -> None:
    project = _copy_example(tmp_path)
    document = project / "document.md"
    content = document.read_text(encoding="utf-8")
    assert ": Pemetaan lapisan pipeline docgen" in content
    document.write_text(
        content.replace(": Pemetaan lapisan pipeline docgen\n\n", "", 1),
        encoding="utf-8",
    )

    completed = _run_cli("check", str(document))
    assert completed.returncode == 1
    output = completed.stdout + completed.stderr
    assert "caption Markdown tidak valid" in output
    assert "tabel tanpa caption" in output


@pytest.mark.word
@pytest.mark.windows
@pytest.mark.skipif(PANDOC is None, reason="Pandoc diperlukan")
@pytest.mark.skipif(not WORD, reason="Field TOC perlu diperbarui Microsoft Word")
def test_fixture_thesis_dua_tabel_gambar_dan_toc_level_tiga(
    tmp_path: Path,
) -> None:
    project = tmp_path / "fixture"
    shutil.copytree(
        FIXTURE,
        project,
        ignore=shutil.ignore_patterns("out", ".laporan*"),
    )
    completed = _run_cli(
        "build",
        str(project / "document.md"),
        "--target",
        "docx",
    )
    assert completed.returncode == 0, completed.stderr

    docx = project / "Tugas.docx"
    assert docx.is_file() and zipfile.is_zipfile(docx)
    root = _document_root(docx)
    text = _text(root)
    assert "Tabel 2.1 Perbandingan pendekatan penulisan dokumen" in text
    assert "Gambar 2.1 Arsitektur pipeline build" in text

    # Entri TOC level tiga: nomor 3.2.3, PAGEREF, dan halaman numerik.
    entry = _toc_entry_with_prefix(root, "TOC3", "3.2.3")
    assert entry is not None
    instructions = "".join(
        node.text or "" for node in entry.iter(f"{{{W_NS}}}instrText")
    )
    assert "PAGEREF" in instructions
    assert re.search(r"\d+$", " ".join(_paragraph_text(entry).split()))
    assert _toc3_has_dot_leader(docx)
