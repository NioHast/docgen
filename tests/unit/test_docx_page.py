"""Tes unit konstanta dan helper ukuran halaman DOCX."""

from collections.abc import Mapping

import pytest

from docgen.docx.page import PAGE_SIZES, page_size

# Nilai pembanding diambil apa adanya dari sumber lama:
# ``stages/sections.py`` (``PAGE_SIZES_TWIP``) dan
# ``stages/front_matter.py`` (``_PAGE_SIZES``). Keduanya memakai twip.
SECTIONS_PAGE_SIZES: Mapping[str, tuple[int, int]] = {
    "A4": (11906, 16838),
    "Letter": (12240, 15840),
}
FRONT_MATTER_PAGE_SIZES: Mapping[tuple[str, str], tuple[int, int]] = {
    ("A4", "portrait"): (11906, 16838),
    ("A4", "landscape"): (16838, 11906),
    ("LETTER", "portrait"): (12240, 15840),
    ("LETTER", "landscape"): (15840, 12240),
}


def test_page_sizes_sama_dengan_map_stage_sections() -> None:
    assert dict(PAGE_SIZES) == dict(SECTIONS_PAGE_SIZES)


@pytest.mark.parametrize(("name", "expected"), SECTIONS_PAGE_SIZES.items())
def test_setiap_ukuran_positif_dan_sama_dengan_sumber(name: str, expected: tuple[int, int]) -> None:
    width, height = PAGE_SIZES[name]
    assert width > 0
    assert height > 0
    assert (width, height) == expected
    assert page_size(name) == expected


@pytest.mark.parametrize(("key", "expected"), FRONT_MATTER_PAGE_SIZES.items())
def test_semua_orientasi_sama_dengan_map_front_matter(
    key: tuple[str, str], expected: tuple[int, int]
) -> None:
    size, orientation = key
    canonical_name = "Letter" if size == "LETTER" else size
    assert page_size(canonical_name, orientation) == expected


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


# ``LETTER`` sengaja diuji: map front_matter memakai huruf besar, sedangkan
# konfigurasi dan map stage sections memakai ``Letter`` yang case-sensitive.
@pytest.mark.parametrize("name", ["F4", "A5", "a4", "LETTER", ""])
def test_nama_tidak_dikenal_menimbulkan_key_error(name: str) -> None:
    with pytest.raises(KeyError) as excinfo:
        page_size(name)
    assert excinfo.value.args == (name,)
