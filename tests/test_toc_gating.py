"""Regresi kunci struktur ``toc`` pada keluaran DOCX dan PDF.

``docx.lua`` dan ``template.typ`` tidak boleh merender DAFTAR ISI/TOC field
ketika metadata menetapkan ``toc: false``. Tanpa kunci tersebut, perilaku lama
(tesis) tetap menyisipkan daftar isi.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DOCX = ROOT / "reference.docx"
LUA_FILTER = ROOT / "docx.lua"
PANDOC_DIR = Path(r"C:\Users\nioha\AppData\Local\Pandoc")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

MARKDOWN = """\
# PENDAHULUAN

## Latar Belakang

Teks.
"""


def _pandoc() -> tuple[str, dict[str, str]]:
    """Cari Pandoc dan siapkan PATH yang menyertakan instalasi Windows."""

    env = os.environ.copy()
    search_path = env.get("PATH", "")
    if PANDOC_DIR.is_dir():
        search_path = str(PANDOC_DIR) + os.pathsep + search_path
    env["PATH"] = search_path

    candidates = [
        env.get("PANDOC"),
        shutil.which("pandoc", path=search_path),
    ]
    local_appdata = env.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(str(Path(local_appdata) / "Pandoc" / "pandoc.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate, env
    pytest.skip("pandoc tidak tersedia")


def _build_docx(tmp_path: Path, *metadata: str) -> bytes:
    source = tmp_path / "toc.md"
    source.write_text(MARKDOWN, encoding="utf-8")
    output = tmp_path / "toc.docx"
    pandoc, env = _pandoc()

    command = [
        pandoc,
        str(source),
        f"--reference-doc={REFERENCE_DOCX}",
        f"--lua-filter={LUA_FILTER}",
        *metadata,
        "-o",
        str(output),
    ]
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert output.is_file(), "pandoc tidak menghasilkan DOCX"

    with zipfile.ZipFile(output) as archive:
        return archive.read("word/document.xml")


def _style_id(paragraph: ElementTree.Element) -> str:
    ppr = paragraph.find(f"{W}pPr")
    if ppr is None:
        return ""
    style = ppr.find(f"{W}pStyle")
    return style.get(f"{W}val", "") if style is not None else ""


def _assert_no_toc(document: bytes) -> None:
    root = ElementTree.fromstring(document)
    paragraphs = list(root.iter(f"{W}p"))

    texts = [
        "".join(node.text or "" for node in paragraph.iter(f"{W}t"))
        for paragraph in paragraphs
    ]
    assert "DAFTAR ISI" not in texts
    assert all(not _style_id(paragraph).startswith("TOC") for paragraph in paragraphs)

    instructions = [node.text or "" for node in root.iter(f"{W}instrText")]
    assert all(" TOC " not in instruction for instruction in instructions)


def _assert_has_toc(document: bytes) -> None:
    root = ElementTree.fromstring(document)
    paragraphs = list(root.iter(f"{W}p"))

    texts = [
        "".join(node.text or "" for node in paragraph.iter(f"{W}t"))
        for paragraph in paragraphs
    ]
    assert "DAFTAR ISI" in texts
    assert any(_style_id(paragraph) == "TOCHeading" for paragraph in paragraphs)

    instructions = [node.text or "" for node in root.iter(f"{W}instrText")]
    assert any(" TOC " in instruction for instruction in instructions)


def test_toc_false_tidak_menyisipkan_daftar_isi(tmp_path: Path) -> None:
    document = _build_docx(tmp_path, "--metadata=toc=false")

    _assert_no_toc(document)


def test_toc_tanpa_metadata_tetap_default_tesis(tmp_path: Path) -> None:
    document = _build_docx(tmp_path)

    _assert_has_toc(document)


TEMPLATE_BODY = """\
# KATA PENGANTAR {-}

Teks.

```{=typst}
#if toc-enabled {
  pagebreak()
  daftar-isi()
  pagebreak()
}
#set page(numbering: "1")
#counter(page).update(1)
```

# PENDAHULUAN

## Latar Belakang

Teks.
"""


def _build_pdf(tmp_path: Path, toc: bool) -> Path:
    """Render template.typ ke PDF; lewati bila Typst/pypdf tidak tersedia."""

    pytest.importorskip("pypdf")
    typst = os.environ.get("TYPST") or shutil.which("typst")
    if not typst:
        pytest.skip("typst tidak tersedia")

    source = tmp_path / "body.md"
    source.write_text(TEMPLATE_BODY, encoding="utf-8")
    metadata = tmp_path / "metadata.yml"
    metadata.write_text(
        "\n".join(
            [
                'title: "Uji TOC"',
                "author:",
                '  - name: "Penulis"',
                'lecturer: "Dosen"',
                'course: "Mata Kuliah"',
                'institution: "Institusi"',
                'faculty: "Fakultas"',
                'year: "2026"',
                f"toc: {'true' if toc else 'false'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / f"toc-{toc}.pdf"
    pandoc, env = _pandoc()

    result = subprocess.run(
        [
            pandoc,
            str(source),
            "--template=template.typ",
            f"--metadata-file={metadata}",
            f"--pdf-engine={typst}",
            "--no-highlight",
            "-o",
            str(output),
        ],
        cwd=str(ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert output.is_file(), "pandoc/typst tidak menghasilkan PDF"
    return output


def test_template_toc_false_tidak_merender_daftar_isi(tmp_path: Path) -> None:
    output = _build_pdf(tmp_path, toc=False)
    PdfReader = pytest.importorskip("pypdf").PdfReader
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(output)).pages)

    assert "DAFTAR ISI" not in text
    assert "PENDAHULUAN" in text


def test_template_toc_true_merender_daftar_isi(tmp_path: Path) -> None:
    output = _build_pdf(tmp_path, toc=True)
    PdfReader = pytest.importorskip("pypdf").PdfReader
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(output)).pages)

    assert "DAFTAR ISI" in text
    assert "PENDAHULUAN" in text
