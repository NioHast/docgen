"""Tes unit konstanta dan helper ukuran halaman DOCX."""

import pytest

from docgen.docx.page import PAGE_SIZES, page_size

# Nilai pembanding diambil dari kontrak format lama (twip). Semua ukuran
# kanonis disimpan dalam orientasi portrait di ``PAGE_SIZES``.
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


# Nama ukuran bersifat case-sensitive di ``page.py``; normalisasi alias lama
# (``LETTER`` uppercase) adalah tanggung jawab masing-masing caller.
@pytest.mark.parametrize("name", ["F4", "A5", "a4", "LETTER", ""])
def test_nama_tidak_dikenal_menimbulkan_key_error(name: str) -> None:
    with pytest.raises(KeyError) as excinfo:
        page_size(name)
    assert excinfo.value.args == (name,)
