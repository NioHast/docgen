"""Tes unit konstanta dan helper ukuran halaman DOCX."""

import pytest
from lxml import etree

from docgen.docx.page import PAGE_SIZES, PageError, content_width, page_size
from docgen.docx.xml import qn

# Nilai pembanding memakai satuan twip. Semua ukuran kanonis disimpan dalam
# orientasi portrait di ``PAGE_SIZES``.
PORTRAIT_SIZES = (
    ("A4", 11906, 16838),
    ("Letter", 12240, 15840),
)
ORIENTED_SIZES = (
    ("A4", "portrait", 11906, 16838),
    ("A4", "landscape", 16838, 11906),
    ("Letter", "portrait", 12240, 15840),
    ("Letter", "landscape", 15840, 12240),
)


def test_page_sizes_hanya_memuat_dua_ukuran_kanonis() -> None:
    assert tuple(PAGE_SIZES) == ("A4", "Letter")


@pytest.mark.parametrize(("name", "width", "height"), PORTRAIT_SIZES)
def test_setiap_ukuran_positif_dan_sesuai_kontrak(
    name: str,
    width: int,
    height: int,
) -> None:
    assert PAGE_SIZES[name] == (width, height)
    assert page_size(name) == (width, height)


@pytest.mark.parametrize(("name", "orientation", "width", "height"), ORIENTED_SIZES)
def test_semua_orientasi_kanonis(
    name: str,
    orientation: str,
    width: int,
    height: int,
) -> None:
    assert page_size(name, orientation) == (width, height)


def test_a4_adalah_11906_kali_16838_twip() -> None:
    assert PAGE_SIZES["A4"] == (11906, 16838)
    assert page_size("A4") == (11906, 16838)
    assert page_size("A4", "portrait") == (11906, 16838)


def test_letter_adalah_12240_kali_15840_twip() -> None:
    assert PAGE_SIZES["Letter"] == (12240, 15840)
    assert page_size("Letter") == (12240, 15840)


def test_landscape_menukar_lebar_dan_tinggi() -> None:
    assert page_size("A4", "landscape") == (16838, 11906)
    assert page_size("Letter", "landscape") == (15840, 12240)


def test_orientasi_selain_landscape_diperlakukan_sebagai_portrait() -> None:
    assert page_size("A4", "portrait") == (11906, 16838)
    assert page_size("A4", "Portrait") == (11906, 16838)
    assert page_size("A4", "sideways") == (11906, 16838)


# Nama ukuran bersifat case-sensitive di ``page.py``; normalisasi nama
# (``LETTER`` uppercase) adalah tanggung jawab masing-masing caller.
@pytest.mark.parametrize("name", ["F4", "A5", "a4", "LETTER", ""])
def test_nama_tidak_dikenal_menimbulkan_key_error(name: str) -> None:
    with pytest.raises(KeyError) as excinfo:
        page_size(name)
    assert excinfo.value.args == (name,)


# ---------------------------------------------------------------------------
# content_width
# ---------------------------------------------------------------------------


def _section(
    *,
    width: str | None = "11906",
    left: str | None = "2268",
    right: str | None = "1701",
    gutter: str | None = "0",
    page_size_element: bool = True,
    page_margin_element: bool = True,
) -> etree._Element:
    section = etree.Element(qn("w:sectPr"))
    if page_size_element:
        size = etree.SubElement(section, qn("w:pgSz"))
        if width is not None:
            size.set(qn("w:w"), width)
    if page_margin_element:
        margin = etree.SubElement(section, qn("w:pgMar"))
        for tag, value in (("w:left", left), ("w:right", right), ("w:gutter", gutter)):
            if value is not None:
                margin.set(qn(tag), value)
    return section


def _body_with(*sections: etree._Element) -> etree._Element:
    body = etree.Element(qn("w:body"))
    for section in sections:
        body.append(section)
    return body


def _assert_page_width_error(body: etree._Element) -> None:
    with pytest.raises(PageError) as excinfo:
        content_width(body)
    assert excinfo.value.code == "PAGE-WIDTH"


def test_content_width_a4_margin_normal() -> None:
    body = _body_with(_section())
    # A4 11906 dikurangi margin kiri 2268 dan kanan 1701.
    assert content_width(body) == 7937


def test_content_width_mengurangi_gutter() -> None:
    body = _body_with(_section(gutter="720"))
    assert content_width(body) == 11906 - 2268 - 1701 - 720


def test_content_width_gutter_hilang_dihitung_nol() -> None:
    body = _body_with(_section(gutter=None))
    assert content_width(body) == 11906 - 2268 - 1701


def test_content_width_landscape() -> None:
    body = _body_with(_section(width="16838"))
    # Landscape menukar lebar A4; margin tidak berubah.
    assert content_width(body) == 16838 - 2268 - 1701


def test_content_width_memakai_sectpr_child_langsung() -> None:
    body = etree.Element(qn("w:body"))
    paragraph = etree.SubElement(body, qn("w:p"))
    properties = etree.SubElement(paragraph, qn("w:pPr"))
    properties.append(_section(width="16838"))
    body.append(_section(width="11906"))
    assert content_width(body) == 7937


def test_content_width_memakai_sectpr_nested_terakhir() -> None:
    body = etree.Element(qn("w:body"))
    for width in ("12240", "11906"):
        paragraph = etree.SubElement(body, qn("w:p"))
        properties = etree.SubElement(paragraph, qn("w:pPr"))
        properties.append(_section(width=width))
    assert content_width(body) == 7937


def test_content_width_tanpa_sectpr_menimbulkan_page_error() -> None:
    _assert_page_width_error(etree.Element(qn("w:body")))


@pytest.mark.parametrize(
    ("page_size_element", "page_margin_element"),
    [(False, True), (True, False)],
)
def test_content_width_pgsz_atau_pgmar_hilang_menimbulkan_page_error(
    page_size_element: bool,
    page_margin_element: bool,
) -> None:
    body = _body_with(
        _section(
            page_size_element=page_size_element,
            page_margin_element=page_margin_element,
        )
    )
    _assert_page_width_error(body)


def _attribute_element(section: etree._Element, attribute: str) -> tuple[etree._Element, str]:
    if attribute == "width":
        element = section.find(qn("w:pgSz"))
        name = qn("w:w")
    else:
        element = section.find(qn("w:pgMar"))
        name = qn(f"w:{attribute}")
    assert element is not None
    return element, name


@pytest.mark.parametrize("attribute", ["width", "left", "right"])
def test_content_width_atribut_hilang_menimbulkan_page_error(attribute: str) -> None:
    section = _section()
    element, name = _attribute_element(section, attribute)
    element.attrib.pop(name, None)
    _assert_page_width_error(_body_with(section))


@pytest.mark.parametrize("attribute", ["width", "left", "right"])
def test_content_width_atribut_bukan_bilangan_bulat_menimbulkan_page_error(
    attribute: str,
) -> None:
    section = _section()
    element, name = _attribute_element(section, attribute)
    element.set(name, "lebar")
    _assert_page_width_error(_body_with(section))


def test_content_width_tidak_positif_menimbulkan_page_error() -> None:
    _assert_page_width_error(_body_with(_section(width="3000", left="2000", right="2000")))


def test_content_width_nol_menimbulkan_page_error() -> None:
    _assert_page_width_error(_body_with(_section(width="4000", left="2000", right="2000")))
