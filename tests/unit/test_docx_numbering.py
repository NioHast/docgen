"""Tes unit helper kanonis nomor bab dan angka Romawi DOCX."""

import pytest

from docgen.docx.numbering import (
    chapter_number,
    format_roman,
    roman_to_int,
    to_roman,
)
from docgen.markdown.headings import (
    NumberingSpec,
    format_chapter_number,
    roman,
)

ROMAN_CASES: tuple[tuple[str, int | None], ...] = (
    ("I", 1),
    ("IV", 4),
    ("IX", 9),
    ("XIV", 14),
    ("MCMXCIV", 1994),
    ("xiv", 14),
    ("", None),
    ("ABC", None),
    # Non-kanonis, tetapi simbolnya tetap dijumlahkan menjadi 4.
    ("IIII", 4),
)

CHAPTER_CASES: tuple[tuple[str, int | None], ...] = (
    ("BAB IV", 4),
    ("BAB 4", 4),
    ("4. Metode", 4),
    ("BAB IX TINJAUAN", 9),
    ("BAB IV.1 Metode", 4),
    ("4.1 Metode", None),
    ("DAFTAR PUSTAKA", None),
    ("", None),
)


@pytest.mark.parametrize(("token", "expected"), ROMAN_CASES)
def test_roman_to_int(token: str, expected: int | None) -> None:
    assert roman_to_int(token) == expected


@pytest.mark.parametrize(("text", "expected"), CHAPTER_CASES)
def test_chapter_number(text: str, expected: int | None) -> None:
    assert chapter_number(text) == expected


def test_chapter_number_none_menghasilkan_none() -> None:
    assert chapter_number(None) is None


def test_legacy_numbering_tidak_diekspor_lagi() -> None:
    """Hanya ``docx.numbering`` yang boleh mendefinisikan helper nomor bab."""

    from docgen.docx import captions, layout

    assert not hasattr(layout, "roman_to_int")
    assert not hasattr(layout, "chapter_number")
    assert not hasattr(captions, "chapter_number")
    assert not hasattr(captions, "_roman_to_int")
    assert not hasattr(captions, "_chapter_number")


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (1, "I"),
        (4, "IV"),
        (9, "IX"),
        (14, "XIV"),
        (40, "XL"),
        (1994, "MCMXCIV"),
        (0, ""),
        (-1, ""),
    ),
)
def test_format_roman(value: int, expected: str) -> None:
    assert format_roman(value) == expected
    assert to_roman(value) == expected


def test_roman_roundtrip() -> None:
    for value in range(1, 101):
        assert roman_to_int(to_roman(value)) == value


@pytest.mark.parametrize("value", (1, 4, 9, 14, 40, 1994))
def test_format_roman_sama_dengan_markdown_headings(value: int) -> None:
    assert format_roman(value) == roman(value)
    assert format_chapter_number(value, NumberingSpec("BAB_ROMAN")) == f"BAB {format_roman(value)}"
