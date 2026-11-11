"""Tes unit stage ``style_reference`` dan helper ``docx/styles.py``."""

import hashlib
import zipfile
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from docgen.config import Format, load_format
from docgen.docx import DocumentPackage
from docgen.docx.styles import (
    StyleError,
    apply_page_layout,
    build_style_patch,
    ensure_character_style,
    patch_style,
    verify_style_contract,
)
from docgen.pipeline import ArtifactStore, Workspace
from docgen.stages.style_reference import (
    StyleReferenceStage,
    build_reference_docx,
    style_specs_for_format,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_xml(docx_path: Path, member: str) -> ElementTree.Element:
    with zipfile.ZipFile(docx_path) as archive:
        return ElementTree.fromstring(archive.read(member))


def style_ids(styles_root: ElementTree.Element) -> list[str]:
    return [style.get(f"{W}styleId", "") for style in styles_root.findall(f"{W}style")]


def get_style(styles_root: ElementTree.Element, style_id: str) -> ElementTree.Element:
    for style in styles_root.findall(f"{W}style"):
        if style.get(f"{W}styleId") == style_id:
            return style
    raise AssertionError(f"style '{style_id}' tidak ditemukan")


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
    return value is None or value.casefold() not in {"0", "false", "off"}


def assert_font(style: ElementTree.Element, family: str) -> None:
    rfonts = child(style.find(f"{W}rPr"), "rFonts")  # type: ignore[arg-type]
    assert rfonts.get(f"{W}ascii") == family
    assert rfonts.get(f"{W}hAnsi") == family
    assert rfonts.get(f"{W}cs") == family


def assert_size(style: ElementTree.Element, half_points: int) -> None:
    rpr = style.find(f"{W}rPr")
    assert rpr is not None
    assert int(val(rpr, "sz")) == half_points
    assert int(val(rpr, "szCs")) == half_points


def assert_spacing(
    style: ElementTree.Element,
    *,
    before: int,
    after: int,
    line: int,
) -> None:
    ppr = style.find(f"{W}pPr")
    assert ppr is not None
    spacing = child(ppr, "spacing")
    assert int(spacing.get(f"{W}before", "-1")) == before
    assert int(spacing.get(f"{W}after", "-1")) == after
    assert int(spacing.get(f"{W}line", "-1")) == line
    assert spacing.get(f"{W}lineRule") == "auto"


def assert_indent(style: ElementTree.Element, *, first_line: int) -> None:
    ppr = style.find(f"{W}pPr")
    assert ppr is not None
    ind = child(ppr, "ind")
    assert set(ind.attrib) == {f"{W}left", f"{W}right", f"{W}firstLine"}
    assert int(ind.get(f"{W}left", "-1")) == 0
    assert int(ind.get(f"{W}right", "-1")) == 0
    assert int(ind.get(f"{W}firstLine", "-1")) == first_line


@pytest.fixture(scope="module")
def undip_format() -> Format:
    return load_format("undip-msi")


def make_reference(tmp_path: Path, format_spec: Format) -> tuple[Path, Path]:
    source = Path(format_spec.assets.reference_docx)
    output = tmp_path / ".laporan-build" / "reference.docx"
    build_reference_docx(source, output, format_spec)
    return source, output


def test_reference_source_unchanged(tmp_path: Path, undip_format: Format) -> None:
    source = Path(undip_format.assets.reference_docx)
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    _, output = make_reference(tmp_path, undip_format)

    assert output != source
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_normal_tnr_12_spacing_15(tmp_path: Path, undip_format: Format) -> None:
    _, output = make_reference(tmp_path, undip_format)
    styles = read_xml(output, "word/styles.xml")

    normal = get_style(styles, "Normal")
    assert_font(normal, "Times New Roman")
    assert_size(normal, 24)
    assert_spacing(normal, before=0, after=0, line=360)
    assert child(normal.find(f"{W}pPr"), "jc").get(f"{W}val") == "both"
    assert int(child(normal.find(f"{W}pPr"), "ind").get(f"{W}firstLine", "-1")) == 709


def test_heading_tnr_12_and_margin(tmp_path: Path, undip_format: Format) -> None:
    _, output = make_reference(tmp_path, undip_format)
    styles = read_xml(output, "word/styles.xml")

    for style_id, alignment in (("Heading1", "center"), ("Heading2", "both")):
        heading = get_style(styles, style_id)
        assert_font(heading, "Times New Roman")
        assert_size(heading, 24)
        assert on_off(heading.find(f"{W}rPr"), "b") is True
        assert_spacing(heading, before=0, after=0, line=360)
        assert child(heading.find(f"{W}pPr"), "jc").get(f"{W}val") == alignment

    document = read_xml(output, "word/document.xml")
    page_margin = document.find(f".//{W}pgMar")
    assert page_margin is not None
    assert page_margin.get(f"{W}top") == "2268"
    assert page_margin.get(f"{W}right") == "1701"
    assert page_margin.get(f"{W}bottom") == "1701"
    assert page_margin.get(f"{W}left") == "2268"


def test_apply_page_layout_uses_canonical_map_and_landscape(
    undip_format: Format,
) -> None:
    package = DocumentPackage.load(Path(undip_format.assets.reference_docx))

    apply_page_layout(
        package,
        size="Letter",
        orientation="landscape",
        margins={"top": 2268, "right": 1701, "bottom": 1701, "left": 2268},
        header=720,
        footer=720,
        gutter=0,
    )

    page_sizes = package.xml("word/document.xml").findall(f".//{W}pgSz")
    assert page_sizes
    assert {element.get(f"{W}w") for element in page_sizes} == {"15840"}
    assert {element.get(f"{W}h") for element in page_sizes} == {"12240"}
    assert {element.get(f"{W}orient") for element in page_sizes} == {"landscape"}


@pytest.mark.parametrize(
    ("size", "orientation", "key"),
    [
        ("A5", "portrait", "page.size"),
        ("LETTER", "portrait", "page.size"),
        ("A4", "diagonal", "page.orientation"),
    ],
)
def test_apply_page_layout_rejects_invalid_input(
    undip_format: Format,
    size: str,
    orientation: str,
    key: str,
) -> None:
    package = DocumentPackage.load(Path(undip_format.assets.reference_docx))

    with pytest.raises(StyleError) as excinfo:
        apply_page_layout(
            package,
            size=size,
            orientation=orientation,
            margins={"top": 2268, "right": 1701, "bottom": 1701, "left": 2268},
            header=720,
            footer=720,
            gutter=0,
        )

    assert excinfo.value.code == "STYLE-PAGE"
    assert excinfo.value.key == key


def test_caption_10pt(tmp_path: Path, undip_format: Format) -> None:
    _, output = make_reference(tmp_path, undip_format)
    styles = read_xml(output, "word/styles.xml")

    image = get_style(styles, "ImageCaption")
    assert_font(image, "Times New Roman")
    assert_size(image, 20)
    assert on_off(image.find(f"{W}rPr"), "b") is False
    assert on_off(image.find(f"{W}rPr"), "i") is False
    assert child(image.find(f"{W}pPr"), "jc").get(f"{W}val") == "center"
    assert_spacing(image, before=0, after=0, line=240)

    table = get_style(styles, "TableCaption")
    assert_font(table, "Times New Roman")
    assert_size(table, 20)
    assert child(table.find(f"{W}pPr"), "jc").get(f"{W}val") == "left"
    assert_spacing(table, before=0, after=0, line=240)
    assert table.find(f"{W}pPr/{W}keepNext") is not None


def test_abstract_10pt_spacing_10_and_indent(tmp_path: Path, undip_format: Format) -> None:
    _, output = make_reference(tmp_path, undip_format)
    styles = read_xml(output, "word/styles.xml")

    body = get_style(styles, "AbstractBody")
    assert_font(body, "Times New Roman")
    assert_size(body, 20)
    assert_spacing(body, before=0, after=0, line=240)
    body_ppr = body.find(f"{W}pPr")
    assert body_ppr is not None
    assert child(body_ppr, "jc").get(f"{W}val") == "both"
    assert_indent(body, first_line=709)

    keywords = get_style(styles, "AbstractKeywords")
    assert_font(keywords, "Times New Roman")
    assert_size(keywords, 20)
    assert_spacing(keywords, before=0, after=0, line=240)
    keywords_ppr = keywords.find(f"{W}pPr")
    assert keywords_ppr is not None
    assert child(keywords_ppr, "jc").get(f"{W}val") == "both"
    assert_indent(keywords, first_line=0)


def test_all_cover_styles_centered_and_without_indent(
    tmp_path: Path,
    undip_format: Format,
) -> None:
    _, output = make_reference(tmp_path, undip_format)
    styles = read_xml(output, "word/styles.xml")

    cover_styles = (
        "CoverTitle",
        "CoverSubtitle",
        "CoverCourse",
        "CoverLecturer",
        "CoverName",
        "CoverLine",
        "CoverInstitution",
        "CoverImage",
    )
    for style_id in cover_styles:
        style = get_style(styles, style_id)
        ppr = style.find(f"{W}pPr")
        assert ppr is not None, style_id
        assert child(ppr, "jc").get(f"{W}val") == "center", style_id
        assert_indent(style, first_line=0)

    title = get_style(styles, "CoverTitle")
    assert on_off(title.find(f"{W}rPr"), "b") is True


def test_required_styles_preserved_and_terms_added(
    tmp_path: Path,
    undip_format: Format,
) -> None:
    source, output = make_reference(tmp_path, undip_format)
    base = style_ids(read_xml(source, "word/styles.xml"))
    derived = style_ids(read_xml(output, "word/styles.xml"))

    assert len(derived) == len(set(derived))
    assert set(base) <= set(derived)
    assert "IstilahAsing" in derived
    assert "IstilahReview" in derived

    styles = read_xml(output, "word/styles.xml")
    foreign = get_style(styles, "IstilahAsing")
    assert foreign.get(f"{W}type") == "character"
    assert child(foreign.find(f"{W}rPr"), "i") is not None
    assert child(foreign.find(f"{W}rPr"), "lang").get(f"{W}val") == "en-US"


def test_reference_deterministic(tmp_path: Path, undip_format: Format) -> None:
    source = Path(undip_format.assets.reference_docx)
    first = tmp_path / "first.docx"
    second = tmp_path / "second.docx"

    build_reference_docx(source, first, undip_format)
    build_reference_docx(source, second, undip_format)

    assert first.read_bytes() == second.read_bytes()


def test_build_reference_rejects_overwriting_source(
    tmp_path: Path,
    undip_format: Format,
) -> None:
    source = tmp_path / "reference.docx"
    source.write_bytes(Path(undip_format.assets.reference_docx).read_bytes())
    before = source.read_bytes()

    with pytest.raises(StyleError):
        build_reference_docx(source, source, undip_format)

    assert source.read_bytes() == before


def test_stage_style_reference_writes_to_workspace(
    tmp_path: Path,
    undip_format: Format,
) -> None:
    source = Path(undip_format.assets.reference_docx)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    workspace = Workspace(root=tmp_path / ".laporan-build", keep=True)
    ctx = SimpleNamespace(
        format=undip_format,
        workspace=workspace,
        artifacts=ArtifactStore(),
        reference_docx=None,
    )

    result = StyleReferenceStage().run(ctx)

    assert result.status == "ok"
    assert result.changed is True
    assert ctx.reference_docx == workspace.path("reference.docx")
    assert ctx.reference_docx.is_file()
    assert result.artifacts == (ctx.reference_docx,)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before

    second = StyleReferenceStage().run(ctx)
    assert second.changed is False


def test_main_dev_cli_does_not_overwrite_source(tmp_path: Path) -> None:
    from docgen.stages.style_reference import main

    source = Path(load_format("undip-msi").assets.reference_docx)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "reference.docx"

    assert main(["--format", "undip-msi", "--out", str(output)]) == 0

    assert output.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_build_style_patch_split_and_can_be_unpacked() -> None:
    ppr, rpr, ppr_drops, rpr_drops = build_style_patch(
        {
            "space_before": 0,
            "space_after": 0,
            "line_spacing": 360,
            "first_line_indent": 709,
            "alignment": "both",
            "keep_next": True,
            "outline_level": 0,
            "font_family": "Times New Roman",
            "font_size": 24,
            "bold": True,
            "color": "000000",
            "shading": "none",
        }
    )

    tags_ppr = {tag for tag, _ in ppr}
    tags_rpr = {tag for tag, _ in rpr}
    assert {"spacing", "ind", "jc", "keepNext", "outlineLvl"} <= tags_ppr
    assert {"rFonts", "b", "bCs", "sz", "szCs", "color"} <= tags_rpr
    assert ppr_drops == ("shd",)
    assert rpr_drops == ("shd",)


def test_docx_styles_patch_and_verify(
    tmp_path: Path,
    undip_format: Format,
) -> None:
    _, output = make_reference(tmp_path, undip_format)
    package = DocumentPackage.load(output)
    original = package.part("word/styles.xml")

    expected = style_specs_for_format(undip_format)
    verify_style_contract(package, expected)

    patch_style(
        package,
        "Normal",
        rpr=[("color", {"val": "112233"})],
    )
    assert package.part("word/styles.xml") != original

    added = ensure_character_style(
        package,
        "IstilahBaru",
        "Istilah Baru",
        rpr_xml="<w:i/>",
    )
    assert added is True
    assert (
        ensure_character_style(
            package,
            "IstilahBaru",
            "Istilah Baru",
            rpr_xml="<w:i/>",
        )
        is False
    )
