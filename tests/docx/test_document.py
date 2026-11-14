"""Tes unit parser front matter dan validasi ``document.md``."""

from pathlib import Path

import pytest

from autooffice.docx.document import load_project
from autooffice.docx.errors import DocgenError

_ASSIGNMENT_BODY = """# Pendahuluan

Teks.

## Latar Belakang

Teks.

# Pembahasan

Teks.

# Penutup

Teks.
"""

_THESIS_BODY = """# Pendahuluan

Teks.

# Tinjauan Pustaka

Teks.

# Metodologi

Teks.

# Hasil dan Pembahasan

Teks.

# Penutup

Teks.

# Lampiran

Teks.
"""


def _write_document(
    root: Path,
    front_matter: str,
    body: str = _ASSIGNMENT_BODY,
    *,
    name: str = "document.md",
    bibliography: bool = True,
) -> Path:
    if bibliography:
        (root / "references.bib").write_text(
            "@article{pandoc2024,\n  title = {Pandoc},\n}\n",
            encoding="utf-8",
            newline="\n",
        )
    path = root / name
    path.write_text(
        "---\n" + front_matter.strip() + "\n---\n\n" + body,
        encoding="utf-8",
        newline="\n",
    )
    return path


def _assignment_front_matter(extra: str = "") -> str:
    return (
        'title: "Laporan Uji"\n'
        'author: "Nama Mahasiswa"\n'
        'nim: "30000000000000"\n'
        'report_name: "Tugas"\n'
        "structure: assignment\n"
        "format: undip-msi\n"
        "bibliography: references.bib\n" + extra
    )


def test_valid_scalar_author_and_nim(tmp_path: Path) -> None:
    path = _write_document(tmp_path, _assignment_front_matter())
    project = load_project(path)

    assert project.document.metadata.title == "Laporan Uji"
    assert len(project.document.metadata.authors) == 1
    assert project.document.metadata.authors[0].name == "Nama Mahasiswa"
    assert project.document.metadata.authors[0].nim == "30000000000000"
    assert project.document.structure_id == "assignment"
    assert project.document.format_id == "undip-msi"
    assert project.assets.bibliography is not None
    assert project.assets.bibliography.name == "references.bib"


def test_author_list_and_keywords_scalar(tmp_path: Path) -> None:
    front_matter = (
        'title: "Laporan Uji"\n'
        "author:\n"
        '  - name: "Nama Satu"\n'
        '    nim: "30000000000001"\n'
        '  - name: "Nama Dua"\n'
        '    nim: "30000000000002"\n'
        'report_name: "Tugas"\n'
        "structure: assignment\n"
        "format: undip-msi\n"
        "bibliography: references.bib\n"
        "abstract_id: |\n"
        "  Abstrak baris pertama.\n"
        "  Baris kedua.\n"
        'keywords: "machine learning"\n'
    )
    project = load_project(_write_document(tmp_path, front_matter))

    metadata = project.document.metadata
    assert [author.nim for author in metadata.authors] == [
        "30000000000001",
        "30000000000002",
    ]
    assert metadata.keywords == ("machine learning",)
    assert metadata.abstract_id is not None
    assert "Baris kedua." in metadata.abstract_id


def test_top_level_nim_with_multiple_authors_rejected(tmp_path: Path) -> None:
    front_matter = (
        'title: "Laporan Uji"\n'
        "author:\n"
        '  - name: "Nama Satu"\n'
        '  - name: "Nama Dua"\n'
        'nim: "30000000000000"\n'
        'report_name: "Tugas"\n'
        "structure: assignment\n"
        "format: undip-msi\n"
        "bibliography: references.bib\n"
    )
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-CONDITIONAL"


def test_conflicting_nim_rejected(tmp_path: Path) -> None:
    front_matter = (
        'title: "Laporan Uji"\n'
        "author:\n"
        '  name: "Nama Mahasiswa"\n'
        '  nim: "30000000000001"\n'
        'nim: "30000000000002"\n'
        'report_name: "Tugas"\n'
        "structure: assignment\n"
        "format: undip-msi\n"
        "bibliography: references.bib\n"
    )
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-CONFLICT"


def test_author_unknown_key_rejected(tmp_path: Path) -> None:
    front_matter = (
        'title: "Laporan Uji"\n'
        "author:\n"
        '  name: "Nama Mahasiswa"\n'
        '  gelar: "S.Kom."\n'
        'report_name: "Tugas"\n'
        "structure: assignment\n"
        "format: undip-msi\n"
        "bibliography: references.bib\n"
    )
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-UNKNOWN-KEY"


def test_keywords_without_abstract_rejected(tmp_path: Path) -> None:
    front_matter = _assignment_front_matter('keywords: "pipeline"\n')
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-CONDITIONAL"


def test_legacy_preset_rejected(tmp_path: Path) -> None:
    front_matter = _assignment_front_matter("preset: undip-skripsi\n")
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "preset"


@pytest.mark.parametrize("value", ["false", "true"])
def test_toc_front_matter_rejected(tmp_path: Path, value: str) -> None:
    front_matter = _assignment_front_matter(f"toc: {value}\n")
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "toc"


def test_unknown_document_key_rejected(tmp_path: Path) -> None:
    front_matter = _assignment_front_matter("foo: 1\n")
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-UNKNOWN-KEY"


def test_bibliography_path_escape_rejected(tmp_path: Path) -> None:
    front_matter = _assignment_front_matter().replace(
        "bibliography: references.bib", "bibliography: ../references.bib"
    )
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-PATH-ESCAPE"


def test_missing_bibliography_rejected(tmp_path: Path) -> None:
    path = _write_document(
        tmp_path,
        _assignment_front_matter().replace(
            "bibliography: references.bib", "bibliography: tidak-ada.bib"
        ),
        bibliography=False,
    )
    with pytest.raises(DocgenError) as error:
        load_project(path)
    assert error.value.code == "CFG-ASSET-MISSING"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("# Pembahasan\n\nTeks.\n", "CFG-BODY-ORDER"),
        ("## Latar Belakang\n\nTeks.\n# Pendahuluan\n", "CFG-BODY-ORDER"),
        (
            "# BAB I Pendahuluan\n\n# Pembahasan\n\n# Penutup\n",
            "CFG-BODY-NUMBER",
        ),
        ("# Pendahuluan\n\n# Pembahasan\n", "CFG-BODY-ORDER"),
        (
            "# Pendahuluan\n\n# Pembahasan\n\n# Penutup\n\n# Tambahan\n",
            "CFG-BODY-ORDER",
        ),
    ],
)
def test_body_order_errors(tmp_path: Path, body: str, code: str) -> None:
    path = _write_document(tmp_path, _assignment_front_matter(), body)
    with pytest.raises(DocgenError) as error:
        load_project(path)
    assert error.value.code == code


def test_duplicate_yaml_key_rejected(tmp_path: Path) -> None:
    front_matter = _assignment_front_matter() + 'title: "Kedua"\n'
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-YAML-DUPLICATE"


def test_missing_front_matter_close_rejected(tmp_path: Path) -> None:
    path = tmp_path / "document.md"
    path.write_text(
        '---\ntitle: "Tanpa Penutup"\n# Pendahuluan\n',
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(DocgenError) as error:
        load_project(path)
    assert error.value.code == "CFG-FRONT-MATTER"


def test_empty_body_rejected(tmp_path: Path) -> None:
    path = tmp_path / "document.md"
    path.write_text(
        "---\n" + _assignment_front_matter() + "\n---\n\n",
        encoding="utf-8",
        newline="\n",
    )
    (tmp_path / "references.bib").write_text("@book{x}\n", encoding="utf-8")
    with pytest.raises(DocgenError) as error:
        load_project(path)
    assert error.value.code == "CFG-REQUIRED"


def test_missing_image_rejected(tmp_path: Path) -> None:
    body = _ASSIGNMENT_BODY.replace(
        "Teks.",
        "![Diagram](gambar/tidak-ada.png)",
        1,
    )
    path = _write_document(tmp_path, _assignment_front_matter(), body)
    with pytest.raises(DocgenError) as error:
        load_project(path)
    assert error.value.code == "CFG-ASSET-MISSING"


def test_image_escape_rejected(tmp_path: Path) -> None:
    body = _ASSIGNMENT_BODY.replace(
        "Teks.",
        "![Diagram](../luar.png)",
        1,
    )
    path = _write_document(tmp_path, _assignment_front_matter(), body)
    with pytest.raises(DocgenError) as error:
        load_project(path)
    assert error.value.code == "CFG-PATH-ESCAPE"


def test_image_in_images_directory_accepted(tmp_path: Path) -> None:
    (tmp_path / "gambar").mkdir()
    (tmp_path / "gambar" / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    body = _ASSIGNMENT_BODY.replace(
        "Teks.",
        "![Diagram](gambar/diagram.png)",
        1,
    )
    path = _write_document(tmp_path, _assignment_front_matter(), body)
    project = load_project(path)
    assert len(project.assets.images) == 1
    assert project.assets.images_dir_exists is True


def test_user_glossary_override(tmp_path: Path) -> None:
    (tmp_path / "istilah.tsv").write_text(
        "istilah\tterjemahan\n",
        encoding="utf-8",
        newline="\n",
    )
    path = _write_document(tmp_path, _assignment_front_matter())
    project = load_project(path)
    assert project.assets.glossary_is_override is True
    assert project.assets.glossary == (tmp_path / "istilah.tsv").resolve()


def test_thesis_requires_document_front_matter(tmp_path: Path) -> None:
    front_matter = (
        'title: "Tesis Uji"\n'
        'author: "Nama Mahasiswa"\n'
        'report_name: "Tugas"\n'
        "structure: thesis\n"
        "format: undip-msi\n"
        "bibliography: references.bib\n"
    )
    path = _write_document(tmp_path, front_matter, _THESIS_BODY)
    with pytest.raises(DocgenError) as error:
        load_project(path)
    assert error.value.code == "CFG-CONDITIONAL"
    assert error.value.key in {"preface", "abstract_id", "abstract_en"}


def test_thesis_with_all_document_sources_accepted(tmp_path: Path) -> None:
    front_matter = (
        'title: "Tesis Uji"\n'
        'author: "Nama Mahasiswa"\n'
        'report_name: "Tugas"\n'
        "structure: thesis\n"
        "format: undip-msi\n"
        "bibliography: references.bib\n"
        "preface: |\n"
        "  Kata pengantar.\n"
        "abstract_id: |\n"
        "  Abstrak Indonesia.\n"
        "abstract_en: |\n"
        "  English abstract.\n"
    )
    project = load_project(_write_document(tmp_path, front_matter, _THESIS_BODY))
    assert project.structure.id == "thesis"
    assert project.document.metadata.preface is not None
    assert project.document.metadata.abstract_en is not None


def test_report_name_rejects_path_characters(tmp_path: Path) -> None:
    front_matter = _assignment_front_matter().replace(
        'report_name: "Tugas"',
        'report_name: "a/b"',
    )
    with pytest.raises(DocgenError) as error:
        load_project(_write_document(tmp_path, front_matter))
    assert error.value.code == "CFG-TYPE"
