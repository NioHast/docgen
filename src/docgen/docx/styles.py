"""Helper style DOCX yang dipakai bersama stage dan tes.

Modul ini adalah satu-satunya tempat yang memutasi ``word/styles.xml``.
Semua fungsi menerima :class:`DocumentPackage`; pemanggil tidak perlu
menyentuh ZIP atau pohon XML secara langsung.

API publik mengikuti ``docs/dev/contracts/docx-api.md``:

``StyleSpec``
    Spesifikasi deklaratif satu style.
``read_style_ids`` / ``style_exists``
    Membaca style tanpa memutasi package.
``patch_style`` / ``apply_style_specs``
    Memutasi ``word/styles.xml``.
``ensure_character_style``
    Menambah atau memperbaiki character style.
``verify_style_contract``
    Memeriksa nilai style yang diharapkan.
"""

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

from lxml import etree

from . import DocxError
from .names import W_SECTPR, W
from .page import PAGE_SIZES
from .page import page_size as resolve_page_size
from .xml import PPR_ORDER, RPR_ORDER, SECTPR_ORDER, get_or_add

# ``names.py`` sengaja tidak mengekspor setiap tag yang hanya dipakai styles.
# Konstanta lokal di bawah memakai namespace yang sama tanpa menambah nama
# baru ke modul fondasi.
W_NS = W[1:-1]
W_STYLES = W + "styles"
W_STYLE = W + "style"
W_STYLE_ID = W + "styleId"
W_BASEDON = W + "basedOn"
W_NAME = W + "name"
W_QFORMAT = W + "qFormat"
W_TYPE = W + "type"
W_CUSTOM_STYLE = W + "customStyle"
W_PPR_TAG = W + "pPr"
W_RPR_TAG = W + "rPr"
W_NEXT = W + "next"
W_LINK = W + "link"
W_UI_PRIORITY = W + "uiPriority"
W_SEMI_HIDDEN = W + "semiHidden"
W_UNHIDE = W + "unhideWhenUsed"
W_ALIASES = W + "aliases"
W_AUTO_REDEFINE = W + "autoRedefine"
W_HIDDEN = W + "hidden"
W_LOCKED = W + "locked"
W_PERSONAL = W + "personal"
W_RSID = W + "rsid"

STYLE_ORDER: tuple[str, ...] = (
    "name",
    "aliases",
    "basedOn",
    "next",
    "link",
    "autoRedefine",
    "hidden",
    "uiPriority",
    "semiHidden",
    "unhideWhenUsed",
    "qFormat",
    "locked",
    "personal",
    "personalCompose",
    "personalReply",
    "rsid",
    "pPr",
    "rPr",
    "tblPr",
    "trPr",
    "tcPr",
    "tblStylePr",
)

StyleType = Literal["paragraph", "character", "table", "numbering"]


class StyleError(DocxError):
    """Style tidak ditemukan, duplikat, atau nilainya tidak valid."""

    default_code = "STYLE"


class StyleContractError(DocxError):
    """Nilai style tidak sesuai kontrak yang diharapkan."""

    default_code = "STYLE-CONTRACT"


@dataclass(frozen=True)
class StyleSpec:
    """Spesifikasi deklaratif satu style OOXML."""

    style_id: str
    style_type: StyleType
    based_on: str | None = None
    ppr: Mapping[str, object] = field(default_factory=dict)
    rpr: Mapping[str, object] = field(default_factory=dict)
    name: str | None = None
    ppr_drops: tuple[str, ...] = ()
    rpr_drops: tuple[str, ...] = ()
    custom: bool = False


class StylePatch(NamedTuple):
    """Hasil :func:`build_style_patch`; kompatibel dengan unpack 4-nilai."""

    ppr: list[tuple[str, dict[str, object]]]
    rpr: list[tuple[str, dict[str, object]]]
    ppr_drops: tuple[str, ...]
    rpr_drops: tuple[str, ...]


# ---------------------------------------------------------------------------
# Akses style
# ---------------------------------------------------------------------------


def _styles_root(package: object) -> etree._Element:
    try:
        root = package.xml("word/styles.xml")  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - package selalu valid
        if isinstance(exc, DocxError):
            raise
        raise StyleError(
            "word/styles.xml tidak dapat dibaca",
            code="STYLE-PART",
        ) from exc
    if root.tag != W_STYLES:
        raise StyleError(
            "root word/styles.xml bukan w:styles",
            code="STYLE-ROOT",
        )
    return root


def _style_elements(root: etree._Element) -> list[etree._Element]:
    return [child for child in root if isinstance(child.tag, str) and child.tag == W_STYLE]


def read_style_ids(package: object) -> frozenset[str]:
    """Kembalikan seluruh ``w:styleId`` tanpa memutasi package."""

    return frozenset(
        style.get(W_STYLE_ID)
        for style in _style_elements(_styles_root(package))
        if style.get(W_STYLE_ID)
    )


def style_exists(package: object, style_id: str) -> bool:
    """True bila ``style_id`` ada di ``word/styles.xml``."""

    return _find_style(_styles_root(package), style_id) is not None


def get_style_element(package: object, style_id: str) -> etree._Element:
    """Kembalikan elemen style; lempar :class:`StyleError` bila tidak ada."""

    style = _find_style(_styles_root(package), style_id)
    if style is None:
        raise StyleError(
            f"style '{style_id}' tidak ditemukan di word/styles.xml",
            code="STYLE-MISSING",
            key=style_id,
        )
    return style


def _find_style(root: etree._Element, style_id: str) -> etree._Element | None:
    for style in _style_elements(root):
        if style.get(W_STYLE_ID) == style_id:
            return style
    return None


def _qname(tag: str) -> str:
    if tag.startswith("{"):
        return tag
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        if prefix != "w":
            raise StyleError(
                f"prefix namespace style tidak didukung: {tag!r}",
                code="STYLE-XML",
            )
        return f"{{{W_NS}}}{local}"
    return f"{{{W_NS}}}{tag}"


def _local(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag.split(":", 1)[-1]


def _insert_style_child(style: etree._Element, child: etree._Element) -> None:
    """Sisipkan anak style pada urutan skema yang benar."""

    index = _order_index(STYLE_ORDER).get(_local(child.tag), len(STYLE_ORDER))
    for existing in style:
        if not isinstance(existing.tag, str):
            continue
        existing_index = _order_index(STYLE_ORDER).get(_local(existing.tag))
        if existing_index is not None and existing_index > index:
            style.insert(style.index(existing), child)
            return
    style.append(child)


def _order_index(order: Sequence[str]) -> dict[str, int]:
    return {name: index for index, name in enumerate(order)}


def _ensure_container(
    style: etree._Element,
    tag: str,
    order: Sequence[str],
) -> etree._Element:
    qualified = _qname(tag)
    existing = style.find(qualified)
    if existing is not None:
        return existing
    container = etree.Element(qualified)
    _insert_style_child(style, container)
    return container


def _reorder_children(parent: etree._Element, order: Sequence[str]) -> None:
    order_map = _order_index(order)
    children = list(parent)
    if len(children) < 2:
        return
    decorated = [
        (order_map.get(_local(child.tag), len(order)), index, child)
        for index, child in enumerate(children)
    ]
    decorated.sort(key=lambda item: (item[0], item[1]))
    for child in children:
        parent.remove(child)
    for _, _, child in decorated:
        parent.append(child)


def _set_attributes(element: etree._Element, attrs: Mapping[str, object]) -> None:
    for raw_name, value in attrs.items():
        name = raw_name if raw_name.startswith("{") else _qname(raw_name)
        if value is None:
            element.attrib.pop(name, None)
            continue
        text = ("1" if value else "0") if isinstance(value, bool) else str(value)
        element.set(name, text)


def _apply_updates(
    container: etree._Element,
    updates: Sequence[tuple[str, Mapping[str, object]]],
    drops: Sequence[str],
    order: Sequence[str],
) -> None:
    for raw_tag in drops:
        for existing in list(container):
            if isinstance(existing.tag, str) and existing.tag == _qname(raw_tag):
                container.remove(existing)
    for tag, attrs in updates:
        qualified = _qname(tag)
        existing = container.find(qualified)
        if existing is None:
            existing = etree.SubElement(container, qualified)
        _set_attributes(existing, attrs)
    _reorder_children(container, order)


def _patch_style_element(
    style: etree._Element,
    *,
    ppr: Sequence[tuple[str, Mapping[str, object]]] = (),
    rpr: Sequence[tuple[str, Mapping[str, object]]] = (),
    drops: Sequence[str] = (),
    ppr_drops: Sequence[str] | None = None,
    rpr_drops: Sequence[str] | None = None,
) -> None:
    global_drops = tuple(drops)
    ppr_removals = tuple(ppr_drops or ()) + global_drops
    rpr_removals = tuple(rpr_drops or ()) + global_drops
    if ppr or ppr_removals:
        container = _ensure_container(style, "pPr", PPR_ORDER)
        _apply_updates(container, ppr, ppr_removals, PPR_ORDER)
    if rpr or rpr_removals:
        container = _ensure_container(style, "rPr", RPR_ORDER)
        _apply_updates(container, rpr, rpr_removals, RPR_ORDER)


def patch_style(
    package: object,
    style_id: str,
    *,
    ppr: Sequence[tuple[str, Mapping[str, object]]] = (),
    rpr: Sequence[tuple[str, Mapping[str, object]]] = (),
    drops: Sequence[str] = (),
    ppr_drops: Sequence[str] | None = None,
    rpr_drops: Sequence[str] | None = None,
) -> None:
    """Ubah child ``w:pPr``/``w:rPr`` milik satu style.

    ``drops`` menghapus tag dari kedua container; ``ppr_drops`` dan
    ``rpr_drops`` membatasi penghapusan ke satu container.
    """

    root = _styles_root(package)
    style = _find_style(root, style_id)
    if style is None:
        raise StyleError(
            f"style '{style_id}' tidak ditemukan di word/styles.xml",
            code="STYLE-MISSING",
            key=style_id,
        )
    _patch_style_element(
        style,
        ppr=ppr,
        rpr=rpr,
        drops=drops,
        ppr_drops=ppr_drops,
        rpr_drops=rpr_drops,
    )
    package.set_xml("word/styles.xml", root)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Spesifikasi -> update OOXML
# ---------------------------------------------------------------------------


def _mapping_updates(
    mapping: Mapping[str, object],
) -> tuple[list[tuple[str, dict[str, object]]], tuple[str, ...]]:
    updates: list[tuple[str, dict[str, object]]] = []
    drops: list[str] = []
    for raw_tag, value in mapping.items():
        tag = _local(raw_tag)
        if value is None:
            drops.append(tag)
            continue
        if isinstance(value, Mapping):
            attrs = {str(key): item for key, item in value.items()}
        elif isinstance(value, bool):
            attrs = {"val": None} if value else {"val": "0"}
        elif isinstance(value, (tuple, list)):
            attrs = {"val": " ".join(str(item) for item in value)}
        else:
            attrs = {"val": value}
        updates.append((tag, attrs))
    return updates, tuple(drops)


def _ensure_spec_style(package: object, spec: StyleSpec) -> bool:
    root = _styles_root(package)
    style = _find_style(root, spec.style_id)
    if spec.based_on is not None and _find_style(root, spec.based_on) is None:
        raise StyleError(
            f"style '{spec.style_id}' memakai basedOn '{spec.based_on}' yang tidak ada",
            code="STYLE-BASEDON",
            key=spec.style_id,
        )
    added = False
    if style is None:
        style = etree.Element(W_STYLE)
        style.set(W_TYPE, spec.style_type)
        style.set(W_STYLE_ID, spec.style_id)
        if spec.custom:
            style.set(W_CUSTOM_STYLE, "1")
        _insert_style_child(style, etree.Element(W_NAME))
        style.find(W_NAME).set(_qname("val"), spec.name or spec.style_id)
        if spec.based_on:
            based = etree.Element(W_BASEDON)
            based.set(_qname("val"), spec.based_on)
            _insert_style_child(style, based)
        if spec.style_type == "paragraph":
            _insert_style_child(style, etree.Element(W_QFORMAT))
        root.append(style)
        added = True
    else:
        declared_type = style.get(W_TYPE)
        if declared_type and declared_type != spec.style_type:
            raise StyleError(
                f"style '{spec.style_id}' bertipe {declared_type!r}, bukan {spec.style_type!r}",
                code="STYLE-TYPE",
                key=spec.style_id,
            )
        if spec.name is not None:
            name = style.find(W_NAME)
            if name is None:
                name = etree.Element(W_NAME)
                _insert_style_child(style, name)
            name.set(_qname("val"), spec.name)
        if spec.based_on is not None:
            based = style.find(W_BASEDON)
            if based is None:
                based = etree.Element(W_BASEDON)
                _insert_style_child(style, based)
            based.set(_qname("val"), spec.based_on)
    return added


def apply_style_specs(
    package: object,
    specs: Mapping[str, StyleSpec],
) -> None:
    """Terapkan seluruh :class:`StyleSpec`; style baru hanya jika dideklarasikan."""

    root = _styles_root(package)
    for spec in specs.values():
        _ensure_spec_style(package, spec)
        style = _find_style(root, spec.style_id)
        if style is None:  # pragma: no cover - baru saja dipastikan ada
            raise StyleError(
                f"style '{spec.style_id}' gagal dibuat",
                code="STYLE-MISSING",
                key=spec.style_id,
            )
        ppr, ppr_drops = _mapping_updates(spec.ppr)
        rpr, rpr_drops = _mapping_updates(spec.rpr)
        _patch_style_element(
            style,
            ppr=tuple((tag, attrs) for tag, attrs in ppr),
            rpr=tuple((tag, attrs) for tag, attrs in rpr),
            ppr_drops=tuple(spec.ppr_drops) + ppr_drops,
            rpr_drops=tuple(spec.rpr_drops) + rpr_drops,
        )
    package.set_xml("word/styles.xml", root)  # type: ignore[attr-defined]


def _parse_rpr_fragment(rpr_xml: str) -> etree._Element:
    """Parse potongan XML rPr dengan parser aman milik package."""

    from .xml import parse_xml

    source = f'<w:rPr xmlns:w="{W_NS}">{rpr_xml}</w:rPr>'
    try:
        root = parse_xml(source)
    except DocxError as exc:
        raise StyleError(
            f"rpr_xml tidak valid: {exc}",
            code="STYLE-XML",
        ) from exc
    if root.tag != W_RPR_TAG:
        raise StyleError("rpr_xml harus menghasilkan w:rPr", code="STYLE-XML")
    return root


def ensure_character_style(
    package: object,
    style_id: str,
    name: str,
    *,
    rpr_xml: str,
) -> bool:
    """Pastikan character style ada dan memuat properti ``rpr_xml``.

    Mengembalikan ``True`` hanya bila style baru ditambahkan. Style yang sudah
    ada diperbaiki tanpa mengganti properti lain.
    """

    root = _styles_root(package)
    desired = list(_parse_rpr_fragment(rpr_xml))
    style = _find_style(root, style_id)
    if style is None:
        style = etree.Element(W_STYLE)
        style.set(W_TYPE, "character")
        style.set(W_CUSTOM_STYLE, "1")
        style.set(W_STYLE_ID, style_id)
        name_node = etree.Element(W_NAME)
        name_node.set(_qname("val"), name)
        style.append(name_node)
        based = etree.Element(W_BASEDON)
        based.set(_qname("val"), "DefaultParagraphFont")
        style.append(based)
        root.append(style)
        added = True
    else:
        if style.get(W_TYPE) != "character":
            raise StyleError(
                f"style '{style_id}' sudah ada tetapi bukan character style",
                code="STYLE-TYPE",
                key=style_id,
            )
        added = False
        name_node = style.find(W_NAME)
        if name_node is None:
            name_node = etree.Element(W_NAME)
            _insert_style_child(style, name_node)
        name_node.set(_qname("val"), name)
        based = style.find(W_BASEDON)
        if based is None:
            based = etree.Element(W_BASEDON)
            _insert_style_child(style, based)
        based.set(_qname("val"), "DefaultParagraphFont")

    desired_tags = {child.tag for child in desired if isinstance(child.tag, str)}
    container = _ensure_container(style, "rPr", RPR_ORDER)
    for child in list(container):
        if isinstance(child.tag, str) and child.tag in desired_tags:
            container.remove(child)
    for child in desired:
        container.append(copy.deepcopy(child))
    _reorder_children(container, RPR_ORDER)
    package.set_xml("word/styles.xml", root)  # type: ignore[attr-defined]
    return added


# ---------------------------------------------------------------------------
# Verifikasi
# ---------------------------------------------------------------------------


def _expected_text(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _verify_updates(
    container: etree._Element,
    mapping: Mapping[str, object],
    *,
    style_id: str,
    label: str,
) -> None:
    for raw_tag, expected in mapping.items():
        tag = _local(raw_tag)
        element = container.find(_qname(tag))
        if element is None:
            raise StyleContractError(
                f"style '{style_id}': {label}.{tag} tidak ditemukan",
                code="STYLE-CONTRACT",
                key=style_id,
            )
        if expected is None:
            continue
        if isinstance(expected, Mapping):
            for raw_attr, attr_value in expected.items():
                attr = _qname(str(raw_attr))
                actual = element.get(attr)
                if attr_value is None:
                    if actual is not None:
                        raise StyleContractError(
                            f"style '{style_id}': {label}.{tag}@{raw_attr} "
                            f"harus tidak ada, bukan {actual!r}",
                            code="STYLE-CONTRACT",
                            key=style_id,
                        )
                    continue
                wanted = _expected_text(attr_value)
                if actual != wanted:
                    raise StyleContractError(
                        f"style '{style_id}': {label}.{tag}@{raw_attr} "
                        f"bernilai {actual!r}, seharusnya {wanted!r}",
                        code="STYLE-CONTRACT",
                        key=style_id,
                    )
        elif isinstance(expected, bool):
            val = element.get(_qname("val"))
            actual_on = val is None or val.casefold() not in {"0", "false", "off"}
            if actual_on != expected:
                raise StyleContractError(
                    f"style '{style_id}': {label}.{tag} bernilai {actual_on}, "
                    f"seharusnya {expected}",
                    code="STYLE-CONTRACT",
                    key=style_id,
                )
        else:
            val = element.get(_qname("val"))
            wanted = _expected_text(expected)
            if val != wanted:
                raise StyleContractError(
                    f"style '{style_id}': {label}.{tag} bernilai {val!r}, seharusnya {wanted!r}",
                    code="STYLE-CONTRACT",
                    key=style_id,
                )


def verify_style_contract(
    package: object,
    expected: Mapping[str, StyleSpec],
) -> None:
    """Lempar :class:`StyleContractError` bila style tidak sesuai harapan."""

    root = _styles_root(package)
    for style_id, spec in expected.items():
        style = _find_style(root, style_id)
        if style is None:
            raise StyleContractError(
                f"style '{style_id}' wajib ada di word/styles.xml",
                code="STYLE-CONTRACT",
                key=style_id,
            )
        declared_type = style.get(W_TYPE)
        if declared_type is not None and declared_type != spec.style_type:
            raise StyleContractError(
                f"style '{style_id}' bertipe {declared_type!r}, seharusnya {spec.style_type!r}",
                code="STYLE-CONTRACT",
                key=style_id,
            )
        if spec.name is not None:
            name = style.find(W_NAME)
            actual = name.get(_qname("val")) if name is not None else None
            if actual != spec.name:
                raise StyleContractError(
                    f"style '{style_id}' bernama {actual!r}, seharusnya {spec.name!r}",
                    code="STYLE-CONTRACT",
                    key=style_id,
                )
        if spec.based_on is not None:
            based = style.find(W_BASEDON)
            actual = based.get(_qname("val")) if based is not None else None
            if actual != spec.based_on:
                raise StyleContractError(
                    f"style '{style_id}' basedOn {actual!r}, seharusnya {spec.based_on!r}",
                    code="STYLE-CONTRACT",
                    key=style_id,
                )
        ppr = style.find(W_PPR_TAG)
        if spec.ppr:
            if ppr is None:
                raise StyleContractError(
                    f"style '{style_id}' tidak memiliki w:pPr",
                    code="STYLE-CONTRACT",
                    key=style_id,
                )
            _verify_updates(
                ppr,
                spec.ppr,
                style_id=style_id,
                label="pPr",
            )
        rpr = style.find(W_RPR_TAG)
        if spec.rpr:
            if rpr is None:
                raise StyleContractError(
                    f"style '{style_id}' tidak memiliki w:rPr",
                    code="STYLE-CONTRACT",
                    key=style_id,
                )
            _verify_updates(
                rpr,
                spec.rpr,
                style_id=style_id,
                label="rPr",
            )


def apply_page_layout(
    package: object,
    *,
    size: str,
    orientation: str,
    margins: Mapping[str, int],
    header: int,
    footer: int,
    gutter: int,
) -> None:
    """Terapkan ukuran halaman dan margin ke seluruh ``w:sectPr``.

    Margin memakai twip. Ukuran halaman memakai twip A4/Letter; orientasi
    ``landscape`` menukar lebar dan tinggi.
    """

    if size not in PAGE_SIZES:
        raise StyleError(
            f"ukuran halaman tidak didukung: {size!r}",
            code="STYLE-PAGE",
            key="page.size",
        )
    if orientation not in {"portrait", "landscape"}:
        raise StyleError(
            f"orientasi halaman tidak didukung: {orientation!r}",
            code="STYLE-PAGE",
            key="page.orientation",
        )
    width, height = resolve_page_size(size, orientation)

    root = package.xml("word/document.xml")  # type: ignore[attr-defined]
    sections = [
        element
        for element in root.iter()
        if isinstance(element.tag, str) and element.tag == W_SECTPR
    ]
    if not sections:
        raise StyleError(
            "w:sectPr tidak ditemukan di word/document.xml",
            code="STYLE-PAGE",
        )

    for section in sections:
        page_size = get_or_add(section, "w:pgSz", SECTPR_ORDER)
        _set_attributes(
            page_size,
            {
                "w": width,
                "h": height,
                "orient": orientation,
            },
        )
        page_margin = get_or_add(section, "w:pgMar", SECTPR_ORDER)
        _set_attributes(
            page_margin,
            {
                "top": margins["top"],
                "right": margins["right"],
                "bottom": margins["bottom"],
                "left": margins["left"],
                "header": header,
                "footer": footer,
                "gutter": gutter,
            },
        )
    package.set_xml("word/document.xml", root)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Port API generator style lama
# ---------------------------------------------------------------------------


def _spacing_patch(spec: Mapping[str, object]) -> dict[str, object]:
    attrs: dict[str, object] = {}
    if "space_before" in spec:
        attrs["before"] = spec["space_before"]
    if "space_after" in spec:
        attrs["after"] = spec["space_after"]
    if "line_spacing" in spec:
        attrs["line"] = spec["line_spacing"]
        attrs["lineRule"] = "auto"
    return attrs


def _indent_patch(spec: Mapping[str, object]) -> dict[str, object]:
    attrs: dict[str, object] = {}
    if "first_line_indent" in spec:
        attrs["firstLine"] = spec["first_line_indent"]
    if "indent_left" in spec:
        attrs["left"] = spec["indent_left"]
    if "indent_hanging" in spec:
        attrs["hanging"] = spec["indent_hanging"]
        if "first_line_indent" not in spec:
            # Hanging tidak boleh bertabrakan dengan firstLine warisan.
            attrs["firstLine"] = None
    return attrs


def _toggle_patch(
    spec: Mapping[str, object],
) -> list[tuple[str, dict[str, object]]]:
    updates: list[tuple[str, dict[str, object]]] = []
    for field_name, tag in (("keep_next", "keepNext"), ("keep_lines", "keepLines")):
        if field_name in spec:
            updates.append((tag, {"val": None} if spec[field_name] else {"val": "0"}))
    for field_name, tag in (("bold", "b"), ("italic", "i")):
        if field_name in spec:
            toggle = {"val": None} if spec[field_name] else {"val": "0"}
            updates.append((tag, dict(toggle)))
            updates.append((f"{tag}Cs", dict(toggle)))
    return updates


def _shading_patch(
    spec: Mapping[str, object],
) -> tuple[list[tuple[str, dict[str, object]]], list[str], list[str]]:
    if "shading" not in spec:
        return [], [], []
    if spec["shading"] == "none":
        return [], ["shd"], ["shd"]
    attrs = {
        "val": "clear",
        "color": "auto",
        "fill": spec["shading"],
    }
    return [("shd", attrs)], [], []


def build_style_patch(spec: Mapping[str, object]) -> StylePatch:
    """Terjemahkan spec datar hasil format menjadi update pPr/rPr.

    Fungsi ini adalah pengganti ``tools/build_style.py:build_style_patch``
    yang dipecah menjadi helper kecil. Nilai yang tidak ada di ``spec`` tidak
    menulis properti apa pun.
    """

    ppr: list[tuple[str, dict[str, object]]] = []
    rpr: list[tuple[str, dict[str, object]]] = []
    ppr_drops: list[str] = []
    rpr_drops: list[str] = []

    spacing = _spacing_patch(spec)
    if spacing:
        ppr.append(("spacing", spacing))

    indent = _indent_patch(spec)
    if indent:
        ppr.append(("ind", indent))

    if "alignment" in spec:
        ppr.append(("jc", {"val": spec["alignment"]}))

    for tag, attrs in _toggle_patch(spec):
        if tag in {"keepNext", "keepLines"}:
            ppr.append((tag, attrs))
        else:
            rpr.append((tag, attrs))

    if "outline_level" in spec:
        ppr.append(("outlineLvl", {"val": spec["outline_level"]}))

    if "font_family" in spec:
        family = spec["font_family"]
        rpr.append(("rFonts", {"ascii": family, "hAnsi": family, "cs": family}))

    if "color" in spec:
        rpr.append(("color", {"val": spec["color"]}))

    if "font_size" in spec:
        size = spec["font_size"]
        rpr.append(("sz", {"val": size}))
        rpr.append(("szCs", {"val": size}))

    shading_updates, parsed_ppr_drops, parsed_rpr_drops = _shading_patch(spec)
    rpr.extend(shading_updates)
    ppr_drops.extend(parsed_ppr_drops)
    rpr_drops.extend(parsed_rpr_drops)

    return StylePatch(
        ppr=ppr,
        rpr=rpr,
        ppr_drops=tuple(ppr_drops),
        rpr_drops=tuple(rpr_drops),
    )


__all__ = [
    "STYLE_ORDER",
    "StyleContractError",
    "StyleError",
    "StylePatch",
    "StyleSpec",
    "StyleType",
    "apply_page_layout",
    "apply_style_specs",
    "build_style_patch",
    "ensure_character_style",
    "get_style_element",
    "patch_style",
    "read_style_ids",
    "style_exists",
    "verify_style_contract",
]
