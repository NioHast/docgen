"""Helper kanonis nomor bab dan angka Romawi untuk pipeline DOCX.

Modul ini menyatukan logika yang sebelumnya terduplikasi di
``docgen.docx.layout`` dan ``docgen.docx.captions``:

* konversi token angka Romawi menjadi bilangan bulat;
* pembacaan nomor bab dari teks ``BAB IV``, ``BAB 4``, atau ``4.``;
* pemformatan bilangan bulat menjadi angka Romawi kapital.

Modul ini murni dan tidak bergantung pada lapisan Markdown, XML, maupun
package DOCX.
"""

import re

__all__ = [
    "ARABIC_CHAPTER_RE",
    "BAB_RE",
    "chapter_number",
    "format_roman",
    "roman_to_int",
    "to_roman",
]

BAB_RE = re.compile(
    r"^\s*BAB\s+(?P<number>[IVXLCDM]+|\d+)(?=\s|[.:;,\-\u2013\u2014]|$)",
    re.IGNORECASE,
)
ARABIC_CHAPTER_RE = re.compile(r"^\s*(?P<number>\d+)(?!\.\d)[\.\s]+")

_ROMAN_VALUES: dict[str, int] = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}

_ROMAN_MAP: tuple[tuple[int, str], ...] = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def roman_to_int(token: str) -> int | None:
    """Konversi token angka Romawi menjadi bilangan bulat.

    Huruf besar dan kecil diterima. ``None`` dikembalikan bila token kosong
    atau memuat karakter di luar ``I V X L C D M``. Token non-kanonis seperti
    ``"IIII"`` tetap dijumlahkan sesuai perilaku sumber lama.
    """

    total = 0
    previous = 0
    for character in reversed(token.upper()):
        value = _ROMAN_VALUES.get(character)
        if value is None:
            return None
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total or None


def chapter_number(text: str | None) -> int | None:
    """Nomor bab dari teks ``BAB <romawi/arab>`` atau ``<arab>.``.

    Format yang didukung sama dengan helper lama di ``layout`` dan
    ``captions``: ``BAB IV``, ``BAB 4``, dan ``4. Metode``. Teks ``None``
    atau kosong menghasilkan ``None``.
    """

    if text is None:
        return None
    match = BAB_RE.match(text)
    if match is not None:
        token = match.group("number")
        if token.isdigit():
            return int(token)
        return roman_to_int(token)

    # Heading1 proposal dapat bernomor arab, mis. "4. Metode". Lookahead
    # menolak subbab seperti "4.1 Metode".
    match = ARABIC_CHAPTER_RE.match(text)
    if match is not None:
        return int(match.group("number"))
    return None


def to_roman(value: int) -> str:
    """Konversi bilangan bulat menjadi angka Romawi kapital.

    Nilai nol atau negatif menghasilkan string kosong, sama seperti helper
    ``roman`` pada lapisan Markdown.
    """

    if value <= 0:
        return ""
    remaining = value
    out: list[str] = []
    for number, symbol in _ROMAN_MAP:
        while remaining >= number:
            out.append(symbol)
            remaining -= number
    return "".join(out)


def format_roman(value: int) -> str:
    """Format nomor bab sebagai angka Romawi kapital.

    Fungsi ini setara dengan helper ``roman`` yang dipakai
    ``format_chapter_number`` tanpa ketergantungan pada ``NumberingSpec``.
    """

    return to_roman(value)
