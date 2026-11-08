"""Tes generator reference.docx terhadap spesifikasi acuan/re.

Mencakup nilai Normal, Heading1-3, TOCHeading, caption, SourceCode, dan
Bibliography, margin 4/3/4/3, kelestarian style, serta override preset.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "build_style.py"
UNDIP_PRESET = ROOT / "presets" / "undip-skripsi.yml"
BASE_REFERENCE = ROOT / "reference.docx"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def run_generator(preset: Path, out_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--preset",
            str(preset),
            "--out",
            str(out_path),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def read_xml(docx_path: Path, member: str) -> ElementTree.Element:
    with zipfile.ZipFile(docx_path) as archive:
        return ElementTree.fromstring(archive.read(member))


def style_ids(styles_root: ElementTree.Element) -> list[str]:
    return [
        style.get(f"{W}styleId", "")
        for style in styles_root.findall(f"{W}style")
    ]


def get_style(styles_root: ElementTree.Element, style_id: str) -> ElementTree.Element:
    for style in styles_root.findall(f"{W}style"):
        if style.get(f"{W}styleId") == style_id:
            return style
    raise AssertionError(f"Style '{style_id}' tidak ditemukan")


def get_ppr(style: ElementTree.Element) -> ElementTree.Element:
    ppr = style.find(f"{W}pPr")
    assert ppr is not None, "w:pPr tidak ditemukan"
    return ppr


def get_rpr(style: ElementTree.Element) -> ElementTree.Element:
    rpr = style.find(f"{W}rPr")
    assert rpr is not None, "w:rPr tidak ditemukan"
    return rpr


def child(parent: ElementTree.Element, tag: str) -> ElementTree.Element:
    element = parent.find(f"{W}{tag}")
    assert element is not None, f"w:{tag} tidak ditemukan"
    return element


def val(parent: ElementTree.Element, tag: str) -> str:
    value = child(parent, tag).get(f"{W}val")
    assert value is not None, f"w:{tag} tidak punya w:val"
    return value


def on_off(parent: ElementTree.Element, tag: str) -> bool:
    element = parent.find(f"{W}{tag}")
    assert element is not None, f"w:{tag} tidak ditemukan"
    value = element.get(f"{W}val")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "off"}


def assert_spacing(
    style: ElementTree.Element, *, before: int, after: int, line: int | None = None
) -> None:
    spacing = child(get_ppr(style), "spacing")
    assert int(spacing.get(f"{W}before", "-1")) == before
    assert int(spacing.get(f"{W}after", "-1")) == after
    if line is not None:
        assert int(spacing.get(f"{W}line", "-1")) == line
        assert spacing.get(f"{W}lineRule") == "auto"


def assert_alignment(style: ElementTree.Element, expected: str) -> None:
    assert val(get_ppr(style), "jc") == expected


def assert_font(style: ElementTree.Element, font: str) -> None:
    rfonts = child(get_rpr(style), "rFonts")
    assert rfonts.get(f"{W}ascii") == font
    assert rfonts.get(f"{W}hAnsi") == font
    assert rfonts.get(f"{W}cs") == font


def assert_size(style: ElementTree.Element, half_points: int) -> None:
    rpr = get_rpr(style)
    assert int(val(rpr, "sz")) == half_points
    assert int(val(rpr, "szCs")) == half_points


def assert_indent(
    style: ElementTree.Element, *, first_line: int | None = None,
    left: int | None = None, hanging: int | None = None,
) -> None:
    ind = child(get_ppr(style), "ind")
    if first_line is not None:
        assert int(ind.get(f"{W}firstLine", "-1")) == first_line
    if left is not None:
        assert int(ind.get(f"{W}left", "-1")) == left
    if hanging is not None:
        assert int(ind.get(f"{W}hanging", "-1")) == hanging


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_path = tmp_path_factory.mktemp("build-style") / "reference-undip.docx"
    result = run_generator(UNDIP_PRESET, out_path)
    assert result.returncode == 0, result.stderr
    assert out_path.is_file()
    return out_path


def test_undip_matches_reference_spec(generated: Path) -> None:
    styles = read_xml(generated, "word/styles.xml")

    normal = get_style(styles, "Normal")
    assert_font(normal, "Times New Roman")
    assert_size(normal, 24)
    assert_spacing(normal, before=0, after=0, line=360)
    assert_alignment(normal, "both")
    assert_indent(normal, first_line=709)

    heading1 = get_style(styles, "Heading1")
    assert_font(heading1, "Times New Roman")
    assert_size(heading1, 24)
    assert on_off(get_rpr(heading1), "b") is True
    assert val(get_rpr(heading1), "color") == "000000"
    assert_alignment(heading1, "center")
    assert_spacing(heading1, before=0, after=0, line=360)
    assert on_off(get_ppr(heading1), "keepNext") is True
    assert on_off(get_ppr(heading1), "keepLines") is True
    assert val(get_ppr(heading1), "outlineLvl") == "0"
    assert_indent(heading1, first_line=0)

    for style_id, outline_level in (("Heading2", "1"), ("Heading3", "2")):
        heading = get_style(styles, style_id)
        assert_font(heading, "Times New Roman")
        assert_size(heading, 24)
        assert on_off(get_rpr(heading), "b") is True
        assert val(get_rpr(heading), "color") == "000000"
        assert_alignment(heading, "both")
        # Jarak antarsubbab memakai paragraf kosong fisik, bukan spacing style.
        assert_spacing(heading, before=0, after=0, line=360)
        assert on_off(get_ppr(heading), "keepNext") is True
        assert val(get_ppr(heading), "outlineLvl") == outline_level
        assert_indent(heading, left=709, hanging=709)

    toc_heading = get_style(styles, "TOCHeading")
    assert_font(toc_heading, "Times New Roman")
    assert_size(toc_heading, 24)
    assert on_off(get_rpr(toc_heading), "b") is True
    assert_alignment(toc_heading, "center")
    assert_spacing(toc_heading, before=0, after=0, line=360)

    image_caption = get_style(styles, "ImageCaption")
    assert_font(image_caption, "Times New Roman")
    assert_size(image_caption, 20)
    assert on_off(get_rpr(image_caption), "b") is False
    assert on_off(get_rpr(image_caption), "i") is False
    assert_alignment(image_caption, "center")
    assert_spacing(image_caption, before=0, after=0, line=240)

    table_caption = get_style(styles, "TableCaption")
    assert_font(table_caption, "Times New Roman")
    assert_size(table_caption, 20)
    assert on_off(get_rpr(table_caption), "b") is False
    assert on_off(get_rpr(table_caption), "i") is False
    assert_alignment(table_caption, "left")
    assert_spacing(table_caption, before=0, after=0, line=240)
    assert on_off(get_ppr(table_caption), "keepNext") is True

    source_code = get_style(styles, "SourceCode")
    assert_font(source_code, "Courier New")
    assert_size(source_code, 20)
    assert_spacing(source_code, before=0, after=0, line=240)
    assert_alignment(source_code, "left")
    assert val(get_rpr(source_code), "color") == "000000"
    assert source_code.find(f".//{W}shd") is None

    for style_id in ("VerbatimChar", "HTMLCode", "HTMLPreformatted"):
        code_style = get_style(styles, style_id)
        assert_font(code_style, "Courier New")
        assert_size(code_style, 20)
        assert val(get_rpr(code_style), "color") == "000000"
        assert code_style.find(f".//{W}shd") is None

    hyperlink = get_style(styles, "Hyperlink")
    assert val(get_rpr(hyperlink), "color") == "000000"
    assert val(get_rpr(hyperlink), "u") == "none"

    bibliography = get_style(styles, "Bibliography")
    assert_font(bibliography, "Times New Roman")
    assert_size(bibliography, 24)
    assert_spacing(bibliography, before=0, after=0, line=360)
    assert_indent(bibliography, left=720, hanging=720)

    figure = get_style(styles, "Figure")
    assert_alignment(figure, "center")
    assert_spacing(figure, before=0, after=0)


def test_no_legacy_monospace_fonts(generated: Path) -> None:
    with zipfile.ZipFile(generated) as archive:
        for member in ("word/styles.xml", "word/document.xml"):
            xml = archive.read(member).decode("utf-8")
            assert not re.search(
                r'w:(?:ascii|hAnsi|cs|eastAsia)="(?:Consolas|DejaVu Sans Mono)"',
                xml,
                re.I,
            ), f"font monospace lama masih ada di {member}"


def test_margins_remain_4_3_4_3(generated: Path) -> None:
    document = read_xml(generated, "word/document.xml")
    page_margin = document.find(f".//{W}pgMar")
    assert page_margin is not None, "w:pgMar tidak ditemukan"

    assert int(page_margin.get(f"{W}top", "-1")) == 2268
    assert int(page_margin.get(f"{W}right", "-1")) == 1701
    assert int(page_margin.get(f"{W}bottom", "-1")) == 1701
    assert int(page_margin.get(f"{W}left", "-1")) == 2268


def test_all_styles_preserved(generated: Path) -> None:
    base_styles = style_ids(read_xml(BASE_REFERENCE, "word/styles.xml"))
    out_styles = style_ids(read_xml(generated, "word/styles.xml"))

    assert len(out_styles) >= len(base_styles)
    assert set(base_styles) <= set(out_styles)
    assert "IstilahAsing" in out_styles
    assert "IstilahReview" in out_styles


def test_preset_override_heading1_size(tmp_path: Path) -> None:
    preset_text = UNDIP_PRESET.read_text(encoding="utf-8")
    assert "heading1_font_size: 12pt" in preset_text
    override_text = preset_text.replace(
        "heading1_font_size: 12pt", "heading1_font_size: 11pt", 1
    )

    override_preset = tmp_path / "undip-heading1-11pt.yml"
    override_preset.write_text(override_text, encoding="utf-8")
    out_path = tmp_path / "reference-override.docx"

    result = run_generator(override_preset, out_path)
    assert result.returncode == 0, result.stderr

    styles = read_xml(out_path, "word/styles.xml")
    heading1 = get_style(styles, "Heading1")
    assert_size(heading1, 22)
    # Style lain tidak boleh ikut berubah.
    assert_size(get_style(styles, "Normal"), 24)
    assert_size(get_style(styles, "Heading2"), 24)
