"""Tes unit untuk loader ``format.yml`` dan ``structure.yml``."""

import re
import shutil
from pathlib import Path

import pytest

from docgen import paths
from docgen.config import load_format, load_structure
from docgen.errors import ConfigError


def _copy_format(tmp_path: Path, name: str = "undip-msi") -> Path:
    data_root = tmp_path / "data"
    target = data_root / "formats" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(paths.format_dir("undip-msi"), target)
    return data_root


def _write_structure(root: Path, name: str, text: str) -> Path:
    directory = root / "structures" / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "structure.yml"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _minimal_structure(extra: str = "") -> str:
    return (
        "format: undip-msi\n\n"
        "front_matter:\n"
        "  - {id: cover, source: generated}\n\n"
        "body:\n"
        '  - {id: pendahuluan, title: "Pendahuluan"}\n\n'
        "back_matter:\n"
        "  - {id: bibliography, source: generated}\n\n"
        "toc: false\n\n"
        "numbering:\n"
        "  body: ARABIC_DOTTED\n\n"
        "lists:\n"
        "  figures: false\n"
        "  tables: false\n" + extra
    )


def test_load_builtin_format() -> None:
    format_ = load_format("undip-msi")

    assert format_.id == "undip-msi"
    assert format_.page.margins.top == 2268  # 4 cm
    assert format_.page.margins.bottom == 1701  # 3 cm
    assert format_.font.body.size_half_points == 24  # 12 pt
    assert format_.font.body.line_spacing == 1.5
    assert format_.font.body.alignment == "justify"
    assert format_.figures.caption_alignment == "center"
    assert format_.figures.image_alignment == "center"
    assert format_.figures.numbering == "chapter"
    assert format_.figures.space_before == 0
    assert format_.figures.space_after == 0
    assert format_.figures.first_line_indent == 0
    assert format_.code.alignment == "left"
    assert format_.toc_heading.heading_style == "TOCHeading"
    assert format_.toc_heading.font_family == "Times New Roman"
    assert format_.toc_heading.color == "000000"
    assert format_.toc_heading.alignment == "center"
    assert format_.toc_heading.first_line_indent == 0
    assert format_.bibliography_style.heading == "DAFTAR PUSTAKA"
    assert format_.bibliography_style.indent_left == 720
    assert format_.bibliography_style.indent_hanging == 720
    assert format_.citation.bibliography == "references.bib"
    assert format_.citation.csl.is_file()
    assert format_.assets.reference_docx.is_file()
    assert format_.assets.logo.is_file()
    assert not hasattr(format_.assets, "cover")
    assert not hasattr(format_.assets, "logo_width")


def test_data_root_uses_package_not_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    root = paths.data_root()
    assert root == paths.package_root() / "data"
    assert root.is_dir()


def test_all_builtin_structures_load() -> None:
    assignment = load_structure("assignment")
    assert assignment.toc is False
    assert assignment.lists.figures is False
    assert assignment.cover.show_lecturer is False
    assert assignment.cover.title_split is True
    assert [item.id for item in assignment.front_matter] == ["cover"]

    proposal = load_structure("proposal")
    assert proposal.toc is True
    assert proposal.lists.figures is False
    assert any(item.source == "template" for item in proposal.front_matter)

    thesis = load_structure("thesis")
    assert thesis.toc is True
    assert thesis.lists.figures is True
    assert thesis.lists.tables is True
    assert next(item.id for item in thesis.front_matter) == "cover"
    assert any(item.id == "appendices" for item in thesis.back_matter)


def test_unknown_format_key_rejected(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yml = data_root / "formats" / "undip-msi" / "format.yml"
    format_yml.write_text(
        format_yml.read_text(encoding="utf-8") + "\nbogus_key: 1\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"


def test_legacy_format_key_rejected(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yml = data_root / "formats" / "undip-msi" / "format.yml"
    format_yml.write_text(
        format_yml.read_text(encoding="utf-8") + "\npresets: []\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "format.presets"


def test_missing_margin_rejected(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yml = data_root / "formats" / "undip-msi" / "format.yml"
    text = format_yml.read_text(encoding="utf-8")
    text = re.sub(r"^\s*top:\s*4cm\s*$\n", "", text, count=1, flags=re.MULTILINE)
    format_yml.write_text(text, encoding="utf-8", newline="\n")

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-REQUIRED"
    assert "margins" in (error.value.key or "")


def test_format_id_must_match_directory(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path, name="wrong-name")

    with pytest.raises(ConfigError) as error:
        load_format("wrong-name", root=data_root)
    assert error.value.code == "CFG-TYPE"
    assert "format" in (error.value.key or "")


def test_format_assets_reject_logo_width(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yml = data_root / "formats" / "undip-msi" / "format.yml"
    text = format_yml.read_text(encoding="utf-8")
    format_yml.write_text(
        text.replace(
            "  reference_docx: reference.docx\n",
            "  reference_docx: reference.docx\n  logo_width: 4.88cm\n",
        ),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "assets.logo_width"


def test_format_assets_reject_cover(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yml = data_root / "formats" / "undip-msi" / "format.yml"
    text = format_yml.read_text(encoding="utf-8")
    format_yml.write_text(
        text.replace(
            "  reference_docx: reference.docx\n",
            "  reference_docx: reference.docx\n  cover:\n    show_lecturer: true\n",
        ),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "assets.cover"


def test_figures_legacy_alignment_rejected(tmp_path: Path) -> None:
    data_root = _copy_format(tmp_path)
    format_yml = data_root / "formats" / "undip-msi" / "format.yml"
    text = format_yml.read_text(encoding="utf-8")
    format_yml.write_text(
        text.replace("  caption_alignment: center\n", "  alignment: center\n"),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ConfigError) as error:
        load_format("undip-msi", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "figures.alignment"


def test_structure_cover_defaults(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(data_root, "contoh", _minimal_structure())

    structure = load_structure("contoh", root=data_root)
    assert structure.cover.show_lecturer is True
    assert structure.cover.logo_width == 2767  # 4.88 cm
    assert structure.cover.title_split is True


def test_structure_template_missing(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "contoh",
        _minimal_structure().replace(
            "  - {id: cover, source: generated}\n",
            "  - {id: cover, source: generated}\n"
            "  - {id: approval, source: template, template: approval.md}\n",
        ),
    )

    with pytest.raises(ConfigError) as error:
        load_structure("contoh", root=data_root)
    assert error.value.code == "CFG-TEMPLATE-MISSING"


def test_structure_toc_consistency(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "contoh",
        _minimal_structure().replace("toc: false", "toc: true"),
    )

    with pytest.raises(ConfigError) as error:
        load_structure("contoh", root=data_root)
    assert error.value.code == "CFG-CONDITIONAL"


def test_structure_unknown_keys(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "contoh",
        _minimal_structure() + "\nfoo: 1\n",
    )
    with pytest.raises(ConfigError) as error:
        load_structure("contoh", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"

    _write_structure(
        data_root,
        "contoh",
        _minimal_structure() + "\nchapters: []\n",
    )
    with pytest.raises(ConfigError) as error:
        load_structure("contoh", root=data_root)
    assert error.value.code == "CFG-UNKNOWN-KEY"
    assert error.value.key == "structure.chapters"


def test_structure_cover_title_split_and_path_escape(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "contoh",
        _minimal_structure()
        + "\ncover:\n  show_lecturer: false\n  logo_width: 4.7cm\n  title_split: false\n",
    )
    structure = load_structure("contoh", root=data_root)
    assert structure.cover.title_split is False
    assert structure.cover.logo_width == 2665
    assert structure.cover.show_lecturer is False

    _write_structure(
        data_root,
        "contoh",
        _minimal_structure().replace(
            "  - {id: cover, source: generated}\n",
            "  - {id: cover, source: generated}\n"
            "  - {id: approval, source: template, template: ../approval.md}\n",
        ),
    )
    with pytest.raises(ConfigError) as error:
        load_structure("contoh", root=data_root)
    assert error.value.code == "CFG-PATH-ESCAPE"


def test_structure_body_unique(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_structure(
        data_root,
        "contoh",
        _minimal_structure().replace(
            '  - {id: pendahuluan, title: "Pendahuluan"}\n',
            '  - {id: pendahuluan, title: "Pendahuluan"}\n'
            '  - {id: pendahuluan, title: "Pendahuluan"}\n',
        ),
    )

    with pytest.raises(ConfigError) as error:
        load_structure("contoh", root=data_root)
    assert error.value.code == "CFG-DUPLICATE"
