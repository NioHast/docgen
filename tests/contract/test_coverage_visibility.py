"""Contract test: every coverage key must be backed by visible PPTX content."""

import posixpath
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import pytest

from autooffice.deck.layout.spec import LayoutPlan, PlacedBlock, SlideLayout
from autooffice.deck.model.deck_ir import (
    BlockIR,
    DeckIR,
    KeyBinding,
    KeyKind,
    KeyManifest,
    SlideIR,
)
from autooffice.deck.model.schema import ChartSeries
from autooffice.deck.render.pptx import PptxRenderer
from autooffice.deck.render.protocol import OutputTarget, RenderRequest
from autooffice.design.theme import resolve_theme

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_KEY_EXTENSION_TAG = "{urn:autooffice:key}key"
_KEY_EXTENSION_URI = "{6F8D3C8E-6A5D-4C2B-9D70-1E6E4F5A8B21}"
_KEY_MARKER = "autooffice:key:"
_CHART_MARKER = "autooffice:chart:"
_MEDIA_MARKERS = (
    "autooffice:table:",
    "autooffice:chart:",
    "autooffice:image:",
    "autooffice:diagram:",
    "chrome:",
)
_SLIDE_PART = re.compile(r"^ppt/slides/slide\d+\.xml$")
_NOTES_PART = re.compile(r"^ppt/notesSlides/notesSlide\d+\.xml$")


def _q(prefix: str, local: str) -> str:
    return f"{{{_NS[prefix]}}}{local}"


_SHAPE_TAGS = frozenset(
    {
        _q("p", "sp"),
        _q("p", "graphicFrame"),
        _q("p", "pic"),
        _q("p", "grpSp"),
        _q("p", "cxnSp"),
    }
)


@dataclass(frozen=True, slots=True)
class _VisibilityScan:
    visible: frozenset[str]
    metadata: frozenset[str]

    @property
    def metadata_only(self) -> frozenset[str]:
        return self.metadata - self.visible


def _binding(
    key: str,
    *,
    slide_id: str,
    block_id: str | None,
    leaf: str,
    kind: KeyKind = "text",
) -> KeyBinding:
    return KeyBinding(
        key=key,
        slide_id=slide_id,
        block_id=block_id,
        leaf=leaf,
        kind=kind,
        sync=True,
        yaml_path=("slides", 0),
        value="nilai",
        plain_text="nilai",
    )


def _visibility_deck() -> DeckIR:
    text = BlockIR("title", "text", None, "title", {"text": "Judul laporan"})
    table = BlockIR(
        "table1",
        "table",
        None,
        None,
        {
            "columns": ("A", "B"),
            "rows": (("1", "2"),),
            "caption": "Tabel data",
        },
    )
    chart = BlockIR(
        "chart1",
        "chart",
        None,
        None,
        {
            "kind": "line",
            "title": "Adopsi per kuartal",
            "alt": "Grafik garis adopsi naik",
            "categories": ("Q1", "Q2"),
            "series": (ChartSeries("2025", (1, 2)), ChartSeries("2026", (3, 4))),
            "caption": "Target internal",
        },
    )
    bindings = [
        _binding("s01.title.text", slide_id="s01", block_id="title", leaf="text"),
        *(
            _binding(
                f"s01.table1.{leaf}",
                slide_id="s01",
                block_id="table1",
                leaf=leaf,
            )
            for leaf in ("h1", "h2", "r1.c1", "r1.c2", "caption")
        ),
        _binding("s01.notes", slide_id="s01", block_id=None, leaf="notes", kind="notes"),
        _binding(
            "s01.source.text",
            slide_id="s01",
            block_id=None,
            leaf="source.text",
            kind="source",
        ),
        *(
            _binding(
                f"s02.chart1.{leaf}",
                slide_id="s02",
                block_id="chart1",
                leaf=leaf,
                kind="data" if ".value" in leaf else "text",
            )
            for leaf in (
                "title",
                "cat1",
                "cat2",
                "series1.name",
                "series1.value1",
                "series1.value2",
                "series2.name",
                "series2.value1",
                "series2.value2",
                "caption",
            )
        ),
    ]
    return DeckIR(
        schema="autooffice.deck/v1",
        meta={"title": "Coverage Visibility Deck", "author": "AutoOffice"},
        theme_name="indigo",
        slides=(
            SlideIR(
                "s01",
                "content",
                0,
                (text, table),
                "Catatan pembicara.",
                {"text": "Sumber: data internal", "url": "https://example.com/data"},
            ),
            SlideIR("s02", "line", 1, (chart,), None, None),
        ),
        keys=KeyManifest(tuple(bindings)),
    )


def _visibility_layout() -> LayoutPlan:
    return LayoutPlan(
        (
            SlideLayout(
                "s01",
                (
                    PlacedBlock("title", 914400, 609600, 10363200, 700000),
                    PlacedBlock("table1", 914400, 1600000, 10363200, 2200000),
                ),
                (),
            ),
            SlideLayout(
                "s02",
                (PlacedBlock("chart1", 914400, 609600, 10363200, 4200000),),
                (),
            ),
        )
    )


@pytest.fixture
def rendered_visibility_deck(tmp_path: Path) -> tuple[DeckIR, Path]:
    deck = _visibility_deck()
    result = PptxRenderer().render(
        RenderRequest(
            deck=deck,
            layout=_visibility_layout(),
            theme=resolve_theme("indigo"),
            target=OutputTarget.PPTX,
            workspace=tmp_path / "workspace",
        )
    )
    assert result.coverage.ok is True
    return deck, result.artifact_path


def _matching_parts(names: Iterable[str], pattern: re.Pattern[str]) -> tuple[str, ...]:
    return tuple(sorted(name for name in names if pattern.match(name)))


def _read_xml(package: zipfile.ZipFile, part: str) -> ElementTree.Element:
    return ElementTree.fromstring(package.read(part))


def _shapes(root: ElementTree.Element) -> tuple[ElementTree.Element, ...]:
    tree = root.find(".//" + _q("p", "spTree"))
    if tree is None:
        return ()
    return tuple(child for child in tree if child.tag in _SHAPE_TAGS)


def _has_descendant(element: ElementTree.Element, tag: str) -> bool:
    return element.find(".//" + tag) is not None


def _has_visible_text(element: ElementTree.Element) -> bool:
    return any((node.text or "").strip() for node in element.iter(_q("a", "t")))


def _shape_key(c_nv_pr: ElementTree.Element | None) -> str | None:
    if c_nv_pr is None:
        return None
    name = c_nv_pr.get("name", "")
    if name.startswith(_KEY_MARKER):
        return name.removeprefix(_KEY_MARKER) or None
    if name.startswith(_MEDIA_MARKERS):
        return None
    title = c_nv_pr.get("title", "")
    if title and not title.startswith(("autooffice:", "chrome:")):
        return title
    return None


def _metadata_keys(c_nv_pr: ElementTree.Element) -> set[str]:
    keys: set[str] = set()
    name = c_nv_pr.get("name", "")
    if name.startswith(_KEY_MARKER):
        key = name.removeprefix(_KEY_MARKER)
        if key:
            keys.add(key)
    elif not name.startswith(_MEDIA_MARKERS):
        title = c_nv_pr.get("title", "")
        if title and not title.startswith(("autooffice:", "chrome:")):
            keys.add(title)
    keys.update(node.text for node in c_nv_pr.iter(_KEY_EXTENSION_TAG) if node.text)
    return keys


def _scan_table(
    shape: ElementTree.Element,
    visible: set[str],
    metadata: set[str],
) -> None:
    for cell in shape.iter(_q("a", "tc")):
        tc_pr = cell.find(_q("a", "tcPr"))
        if tc_pr is None:
            continue
        keys = {node.text for node in tc_pr.iter(_KEY_EXTENSION_TAG) if node.text}
        if not keys:
            continue
        metadata.update(keys)
        if _has_visible_text(cell):
            visible.update(keys)


def _chart_id(shape: ElementTree.Element) -> str | None:
    c_nv_pr = shape.find(".//" + _q("p", "cNvPr"))
    if c_nv_pr is None:
        return None
    name = c_nv_pr.get("name", "")
    if not name.startswith(_CHART_MARKER):
        return None
    return name.removeprefix(_CHART_MARKER) or None


def _relationships_part(part: str) -> str:
    directory, filename = posixpath.split(part)
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def _related_chart_part(
    package: zipfile.ZipFile,
    slide_part: str,
    relationship_id: str,
) -> str | None:
    rels_part = _relationships_part(slide_part)
    if rels_part not in package.namelist():
        return None
    for relationship in _read_xml(package, rels_part):
        if relationship.get("Id") != relationship_id:
            continue
        if not relationship.get("Type", "").endswith("/chart"):
            continue
        target = relationship.get("Target")
        if not target:
            return None
        return posixpath.normpath(posixpath.join(posixpath.dirname(slide_part), target))
    return None


def _chart_points(container: ElementTree.Element) -> tuple[tuple[int, str], ...]:
    points: list[tuple[int, str]] = []
    for fallback, point in enumerate(container.iter(_q("c", "pt"))):
        raw_index = point.get("idx")
        try:
            index = int(raw_index) if raw_index is not None else fallback
        except ValueError:
            index = fallback
        value = point.find(_q("c", "v"))
        text = "" if value is None or value.text is None else value.text.strip()
        points.append((index, text))
    points.sort()
    return tuple(points)


def _first_text(container: ElementTree.Element, tag: str) -> str:
    for node in container.iter(tag):
        text = (node.text or "").strip()
        if text:
            return text
    return ""


def _scan_chart_xml(
    root: ElementTree.Element,
    chart_id: str,
    visible: set[str],
) -> None:
    """Map chart data keys to visible chart title, categories, and series.

    Chart keys live in the slide shape's ``cNvPr`` extension list, so the chart
    part is parsed independently to prove the data itself was rendered.
    """
    chart = root.find(_q("c", "chart"))
    if chart is None:
        return
    title = chart.find(_q("c", "title"))
    if title is not None and _has_visible_text(title):
        visible.add(f"{chart_id}.title")

    categories = root.find(".//" + _q("c", "cat"))
    if categories is not None:
        for index, text in _chart_points(categories):
            if text:
                visible.add(f"{chart_id}.cat{index + 1}")

    for series_index, series in enumerate(root.iter(_q("c", "ser")), start=1):
        name = series.find(_q("c", "tx"))
        if name is not None and _first_text(name, _q("c", "v")):
            visible.add(f"{chart_id}.series{series_index}.name")
        values = series.find(_q("c", "val"))
        if values is None:
            continue
        for index, text in _chart_points(values):
            if text:
                visible.add(f"{chart_id}.series{series_index}.value{index + 1}")


def _scan_chart(
    package: zipfile.ZipFile,
    slide_part: str,
    shape: ElementTree.Element,
    visible: set[str],
) -> None:
    chart_id = _chart_id(shape)
    chart_reference = shape.find(".//" + _q("c", "chart"))
    if chart_id is None or chart_reference is None:
        return
    relationship_id = chart_reference.get(_q("r", "id"))
    if relationship_id is None:
        return
    chart_part = _related_chart_part(package, slide_part, relationship_id)
    if chart_part is None:
        return
    _scan_chart_xml(_read_xml(package, chart_part), chart_id, visible)


def _scan_part(
    package: zipfile.ZipFile,
    part: str,
    root: ElementTree.Element,
    visible: set[str],
    metadata: set[str],
) -> None:
    for shape in _shapes(root):
        c_nv_pr = shape.find(".//" + _q("p", "cNvPr"))
        if c_nv_pr is not None:
            metadata.update(_metadata_keys(c_nv_pr))
        if _has_descendant(shape, _q("a", "tbl")):
            _scan_table(shape, visible, metadata)
            continue
        if _has_descendant(shape, _q("c", "chart")):
            _scan_chart(package, part, shape, visible)
            continue
        key = _shape_key(c_nv_pr)
        if key is not None and _has_visible_text(shape):
            visible.add(key)


def _scan_visibility(path: Path) -> _VisibilityScan:
    visible: set[str] = set()
    metadata: set[str] = set()
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        for part in _matching_parts(names, _SLIDE_PART):
            _scan_part(package, part, _read_xml(package, part), visible, metadata)
        for part in _matching_parts(names, _NOTES_PART):
            _scan_part(package, part, _read_xml(package, part), visible, metadata)
    return _VisibilityScan(frozenset(visible), frozenset(metadata))


def _assert_visible_coverage(path: Path, expected_keys: Iterable[str]) -> _VisibilityScan:
    """Reject manifest or metadata-only keys that lack visible backing."""
    scan = _scan_visibility(path)
    expected = frozenset(expected_keys)
    missing = expected - scan.visible
    unexpected = scan.visible - expected
    if scan.metadata_only or missing or unexpected:
        details: list[str] = []
        if scan.metadata_only:
            details.append(f"metadata-only={sorted(scan.metadata_only)}")
        if missing:
            details.append(f"missing-visible={sorted(missing)}")
        if unexpected:
            details.append(f"unexpected-visible={sorted(unexpected)}")
        raise AssertionError("coverage keys without visible elements: " + "; ".join(details))
    return scan


def _add_metadata_only_key(source: Path, destination: Path, key: str) -> str:
    with zipfile.ZipFile(source) as package:
        entries = [(info, package.read(info.filename)) for info in package.infolist()]
    contents = {info.filename: data for info, data in entries}

    target_part: str | None = None
    for name in sorted(contents):
        if not _SLIDE_PART.match(name):
            continue
        root = ElementTree.fromstring(contents[name])
        if any(_chart_id(shape) is not None for shape in _shapes(root)):
            target_part = name
            break
    assert target_part is not None

    root = ElementTree.fromstring(contents[target_part])
    chart_shape = next(shape for shape in _shapes(root) if _chart_id(shape) is not None)
    c_nv_pr = chart_shape.find(".//" + _q("p", "cNvPr"))
    assert c_nv_pr is not None
    ext_lst = c_nv_pr.find(_q("a", "extLst"))
    if ext_lst is None:
        ext_lst = ElementTree.SubElement(c_nv_pr, _q("a", "extLst"))
    extension = ext_lst.find(_q("a", "ext"))
    if extension is None:
        extension = ElementTree.SubElement(
            ext_lst,
            _q("a", "ext"),
            {"uri": _KEY_EXTENSION_URI},
        )
    ElementTree.SubElement(extension, _KEY_EXTENSION_TAG).text = key
    contents[target_part] = ElementTree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
    )

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as package:
        for info, _ in entries:
            package.writestr(info, contents[info.filename])
    return target_part


def test_every_manifest_key_is_backed_by_visible_pptx_element(
    rendered_visibility_deck: tuple[DeckIR, Path],
) -> None:
    deck, artifact_path = rendered_visibility_deck

    scan = _assert_visible_coverage(artifact_path, deck.keys.keys())

    assert scan.visible == frozenset(deck.keys.keys())
    assert scan.metadata_only == frozenset()
    assert {
        "s01.title.text",
        "s01.table1.h1",
        "s01.notes",
        "s01.source.text",
        "s02.chart1.caption",
    } <= scan.visible


def test_metadata_only_key_is_rejected(
    rendered_visibility_deck: tuple[DeckIR, Path],
    tmp_path: Path,
) -> None:
    deck, artifact_path = rendered_visibility_deck
    tampered = tmp_path / "metadata-only.pptx"
    part = _add_metadata_only_key(artifact_path, tampered, "s01.ghost.text")

    with zipfile.ZipFile(tampered) as package:
        assert b"s01.ghost.text" in package.read(part)

    with pytest.raises(AssertionError, match=r"s01\.ghost\.text"):
        _assert_visible_coverage(tampered, deck.keys.keys())
