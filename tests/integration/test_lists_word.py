"""Tes Word untuk stage ``lists`` (marker ``word``/``windows``).

Tes ini membangun DOCX kecil, menjalankan :class:`ListsStage`, memperbarui
field dengan Microsoft Word lewat ``resources/word.ps1``, lalu memeriksa cache
field di DOCX dan teks PDF. Mock bukan bukti; tes dilewati di luar Windows.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [
    pytest.mark.word,
    pytest.mark.windows,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="Microsoft Word hanya tersedia di Windows",
    ),
]

from docx import Document  # noqa: E402

from docgen.docx.fields import field_instruction, insert_toc, iter_fields  # noqa: E402
from docgen.docx.package import DocumentPackage  # noqa: E402
from docgen.docx.xml import iter_paragraphs, paragraph_text  # noqa: E402
from docgen.stages.lists import ListsStage  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORD_PS1 = ROOT / "resources" / "word.ps1"


def _word_available() -> bool:
    if sys.platform != "win32":
        return False
    if shutil.which("powershell") is None:
        return False
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows selalu punya winreg
        return False
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        if value and Path(value).is_file():
            return True
    return False


pytestmark.append(pytest.mark.skipif(not _word_available(), reason="Microsoft Word tidak tersedia"))


def _ctx(package: DocumentPackage) -> SimpleNamespace:
    return SimpleNamespace(
        package=package,
        document=SimpleNamespace(),
        structure=SimpleNamespace(
            toc=True,
            front_matter=(
                SimpleNamespace(id="cover"),
                SimpleNamespace(id="toc"),
                SimpleNamespace(id="list_of_tables"),
                SimpleNamespace(id="list_of_figures"),
            ),
            lists=SimpleNamespace(tables=True, figures=True),
        ),
        format=SimpleNamespace(
            captions=SimpleNamespace(
                table=SimpleNamespace(label="Tabel", separator=" "),
                figure=SimpleNamespace(label="Gambar", separator=" "),
            ),
            figures=SimpleNamespace(numbering="chapter"),
        ),
        options=SimpleNamespace(),
        dry_run=False,
    )


def _build_docx(path: Path) -> None:
    document = Document()
    document.add_paragraph("BAB II", style="Heading 1")
    document.add_paragraph("Isi bab kedua.")
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.cell(0, 0).text = "Kolom A"
    table.cell(0, 1).text = "Kolom B"
    table_caption = document.add_paragraph(style="Caption")
    table_caption.add_run("Tabel 2.1 Judul Tabel Satu")
    figure_caption = document.add_paragraph(style="Caption")
    figure_caption.add_run("Gambar 2.1 Diagram Alur")
    document.save(str(path))


def _run_word(docx: Path, *, pdf: Path | None = None) -> None:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(WORD_PS1),
        "-DocxPath",
        str(docx),
    ]
    if pdf is not None:
        command.extend(["-PdfPath", str(pdf)])
    subprocess.run(command, check=True, capture_output=True, text=True)


def _all_text(package: DocumentPackage) -> list[str]:
    return [
        paragraph_text(paragraph) for paragraph in iter_paragraphs(package.xml("word/document.xml"))
    ]


def test_lists_word_updates_caption_and_list_fields(tmp_path: Path) -> None:
    docx = tmp_path / "lists-word.docx"
    pdf = tmp_path / "lists-word.pdf"
    _build_docx(docx)

    package = DocumentPackage.load(docx)
    insert_toc(package, title="DAFTAR ISI")
    result = ListsStage().run(_ctx(package))
    assert result.status == "ok"
    assert result.metrics["list_fields"] == 2
    assert result.metrics["seq_fields"] == 2
    package.save(docx)

    instructions = [field_instruction(field) for field in iter_fields(package)]
    assert sum("TOC \\o" in item for item in instructions) == 1
    assert sum('TOC \\c "Tabel"' in item for item in instructions) == 1
    assert sum('TOC \\c "Gambar"' in item for item in instructions) == 1
    assert sum("SEQ Tabel \\* ARABIC \\s 1" in item for item in instructions) == 1
    assert sum("SEQ Gambar \\* ARABIC \\s 1" in item for item in instructions) == 1

    _run_word(docx)
    updated = DocumentPackage.load(docx)
    texts = [text for text in _all_text(updated) if text.strip()]
    flattened = "\n".join(texts)
    assert "DAFTAR ISI" in flattened
    assert "DAFTAR TABEL" in flattened
    assert "DAFTAR GAMBAR" in flattened
    assert sum(text.split("\t")[0] == "Tabel 2.1 Judul Tabel Satu" for text in texts) >= 2
    assert sum(text.split("\t")[0] == "Gambar 2.1 Diagram Alur" for text in texts) >= 2

    _run_word(docx, pdf=pdf)
    assert pdf.is_file() and pdf.stat().st_size > 0
    pypdf = pytest.importorskip("pypdf")
    text = "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(str(pdf)).pages)
    assert "DAFTAR TABEL" in text
    assert "Tabel 2.1 Judul Tabel Satu" in text
    assert "DAFTAR GAMBAR" in text
    assert "Gambar 2.1 Diagram Alur" in text
