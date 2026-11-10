"""Tes unit helper kanonis nomor bab dan angka Romawi DOCX."""

import pytest

from docgen.docx.captions import (
    _chapter_number as captions_chapter_number,
)
from docgen.docx.captions import (
    _roman_to_int as captions_roman_to_int,
)
from docgen.docx.layout import (
    chapter_number as layout_chapter_number,
)
from docgen.docx.layout import (
    roman_to_int as layout_roman_to_int,
)
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
    # Non-kanonis, tetapi sumber lama tetap menjumlahkannya menjadi 4.
    ("IIII", 4),
)

CHAPTER_CASES: tuple[tuple[str, int | None], ...] = (
    ("BAB IV", 4),
    ("BAB 4", 4),
    ("4. Metode", 4),
    ("BAB IX TINJAUAN", 9),
    ("DAFTAR PUSTAKA", None),
    ("", None),
)

# Domain ``layout.chapter_number`` belum mengenal heading arab bertitik.
LAYOUT_CHAPTER_CASES: tuple[str, ...] = (
    "BAB IV",
    "BAB 4",
    "BAB IX TINJAUAN",
    "DAFTAR PUSTAKA",
    "",
)


@pytest.mark.parametrize(("token", "expected"), ROMAN_CASES)
def test_roman_to_int(token: str, expected: int | None) -> None:
    assert roman_to_int(token) == expected


@pytest.mark.parametrize(("token", "expected"), ROMAN_CASES)
def test_roman_to_int_sama_dengan_sumber_lama(token: str, expected: int | None) -> None:
    assert layout_roman_to_int(token) == expected
    assert captions_roman_to_int(token) == expected
    assert roman_to_int(token) == expected


@pytest.mark.parametrize(("text", "expected"), CHAPTER_CASES)
def test_chapter_number(text: str, expected: int | None) -> None:
    assert chapter_number(text) == expected


def test_chapter_number_none_menghasilkan_none() -> None:
    assert chapter_number(None) is None


@pytest.mark.parametrize(("text", "expected"), CHAPTER_CASES)
def test_chapter_number_sama_dengan_captions(text: str, expected: int | None) -> None:
    assert captions_chapter_number(text) == expected
    assert chapter_number(text) == expected


@pytest.mark.parametrize("text", LAYOUT_CHAPTER_CASES)
def test_chapter_number_sama_dengan_layout(text: str) -> None:
    assert chapter_number(text) == layout_chapter_number(text)


def test_chapter_number_arabic_dotted_mengikuti_captions() -> None:
    """Ekstensi ``4.`` berasal dari captions, bukan layout."""

    assert layout_chapter_number("4. Metode") is None
    assert captions_chapter_number("4. Metode") == 4
    assert chapter_number("4. Metode") == 4


def test_chapter_number_menolak_subbab_arab() -> None:
    assert chapter_number("4.1 Metode") is None


def test_chapter_number_bab_dengan_titik_mengikuti_regex_lama() -> None:
    # Lookahead ``BAB_RE`` menerima titik sebagai pemisah, jadi bentuk ini
    # memang menghasilkan 4 pada sumber lama.
    assert chapter_number("BAB IV.1 Metode") == 4
    assert layout_chapter_number("BAB IV.1 Metode") == 4
    assert captions_chapter_number("BAB IV.1 Metode") == 4


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


@pytest.mark.parametrize("value", (1, 4, 9, 14, 40, 1994))
def test_format_roman_sama_dengan_markdown_headings(value: int) -> None:
    assert format_roman(value) == roman(value)
    assert format_chapter_number(value, NumberingSpec("BAB_ROMAN")) == f"BAB {format_roman(value)}"
