"""Tes unit penomoran heading Markdown dan ``balance_title``."""

import pytest

from docgen.errors import DocgenError
from docgen.markdown.headings import (
    LINE_BREAK,
    TAB,
    Heading,
    HeadingNumberer,
    MarkdownHeadingError,
    NumberingSpec,
    balance_title,
    format_chapter_number,
    number_markdown,
    number_markdown_headings,
    parse_heading,
    roman,
    uppercase_markdown,
)


def test_roman_and_chapter_number() -> None:
    assert roman(1) == "I"
    assert roman(4) == "IV"
    assert roman(9) == "IX"
    assert roman(14) == "XIV"
    assert roman(0) == ""
    assert format_chapter_number(2, NumberingSpec("BAB_ROMAN")) == "BAB II"
    assert format_chapter_number(2, NumberingSpec("ARABIC_DOTTED")) == "2."


def test_invalid_numbering_spec_rejected() -> None:
    assert issubclass(MarkdownHeadingError, DocgenError)
    with pytest.raises(MarkdownHeadingError):
        NumberingSpec(body="ROMAN")  # type: ignore[arg-type]


def test_numbering_romawi_h1_h2_h3_dan_reset() -> None:
    numberer = HeadingNumberer(NumberingSpec("BAB_ROMAN"))

    assert numberer.number(1, "Pendahuluan").number == "BAB I"
    assert numberer.number(2, "Latar Belakang").number == "1.1."
    assert numberer.number(3, "Rumusan").number == "1.1.1."
    assert numberer.number(2, "Tujuan").number == "1.2."
    assert numberer.number(1, "Pembahasan").number == "BAB II"
    assert numberer.number(2, "Analisis").number == "2.1."


def test_numbering_arabic_dotted() -> None:
    numberer = HeadingNumberer(NumberingSpec("ARABIC_DOTTED"))

    assert numberer.number(1, "Pendahuluan").number == "1."
    assert numberer.number(2, "Latar Belakang").number == "1.1."
    assert numberer.number(3, "Rumusan").number == "1.1.1."


def test_sub_dot_disabled() -> None:
    numberer = HeadingNumberer(NumberingSpec("BAB_ROMAN", sub_dot=False, subsub_dot=False))

    numberer.number(1, "Bab")
    assert numberer.number(2, "Sub").number == "1.1"
    assert numberer.number(3, "Subsub").number == "1.1.1"


def test_h2_before_h1_uses_implicit_chapter() -> None:
    numberer = HeadingNumberer(NumberingSpec("BAB_ROMAN"))

    assert numberer.number(2, "Sub Awal").number == "1.1."
    assert numberer.number(1, "Bab Satu").number == "BAB I"
    assert numberer.number(2, "Sub").number == "1.1."


def test_unnumbered_h1_does_not_reset_counters() -> None:
    numberer = HeadingNumberer(NumberingSpec("BAB_ROMAN"))

    assert numberer.number(1, "Pendahuluan").number == "BAB I"
    assert numberer.number(2, "Latar Belakang").number == "1.1."
    assert numberer.number(1, "Abstrak", unnumbered=True).number is None
    assert numberer.number(2, "Metode").number == "1.2."
    assert numberer.number(1, "Pembahasan").number == "BAB II"


def test_h4_h6_tidak_dinomori_dan_tidak_mengubah_counter() -> None:
    numberer = HeadingNumberer(NumberingSpec("BAB_ROMAN"))
    numberer.number(1, "Bab")
    assert numberer.number(2, "Sub").number == "1.1."

    for level in (4, 5, 6):
        heading = numberer.number(level, f"Level {level}")
        assert heading.number is None
        assert not heading.unnumbered

    assert numberer.number(2, "Sub Berikut").number == "1.2."


def test_parse_heading_attributes_and_unnumbered() -> None:
    parsed = parse_heading("## Judul Sub {#sub .unnumbered} ##")
    assert parsed is not None
    assert parsed.level == 2
    assert parsed.text == "Judul Sub"
    assert parsed.attributes == "{#sub .unnumbered}"
    assert parsed.unnumbered is True

    shorthand = parse_heading("# Abstrak {-}")
    assert shorthand is not None
    assert shorthand.unnumbered is True

    assert parse_heading("    # kode") is None
    assert parse_heading("Teks # bukan heading") is None


def test_uppercase_heading_menjaga_inline_dan_url() -> None:
    text = "Sub *miring* [tautan](HTTP://EXAMPLE.COM) `kode`"
    assert uppercase_markdown(text) == "SUB *MIRING* [TAUTAN](HTTP://EXAMPLE.COM) `kode`"


def test_render_heading_romawi_memakai_line_break() -> None:
    numberer = HeadingNumberer(NumberingSpec("BAB_ROMAN"))
    heading = numberer.number(1, "Pendahuluan")

    assert heading == Heading(
        level=1,
        text="Pendahuluan",
        number="BAB I",
        unnumbered=False,
    )
    # Render H1 bukan tanggung jawab HeadingNumberer; dicek via Markdown.
    output = number_markdown("# Pendahuluan\n", NumberingSpec("BAB_ROMAN"))
    assert output == f"# BAB I{LINE_BREAK}PENDAHULUAN\n"


def test_number_markdown_h2_h3_dan_arabic() -> None:
    markdown = "# Pendahuluan\n\n## Latar Belakang\n\n### Detail\n\n# Pembahasan\n\n## Analisis\n"

    roman_output = number_markdown(markdown, NumberingSpec("BAB_ROMAN"))
    assert f"# BAB I{LINE_BREAK}PENDAHULUAN\n" in roman_output
    assert f"## 1.1.{TAB}Latar Belakang\n" in roman_output
    assert f"### 1.1.1.{TAB}Detail\n" in roman_output
    assert f"# BAB II{LINE_BREAK}PEMBAHASAN\n" in roman_output
    assert f"## 2.1.{TAB}Analisis\n" in roman_output

    arabic_output = number_markdown(markdown, NumberingSpec("ARABIC_DOTTED"))
    assert arabic_output.startswith("# 1. PENDAHULUAN\n")
    assert "## 1.1." in arabic_output


def test_number_markdown_unnumbered_dan_atribut() -> None:
    markdown = "# Ringkasan {-}\n\n## Sub {#sub}\n\n# Bab Satu\n\n## Anak\n"
    output = number_markdown(markdown, NumberingSpec("BAB_ROMAN"))

    assert "# Ringkasan {-}" in output
    assert f"## 1.1.{TAB}Sub {{#sub}}\n" in output
    assert f"# BAB I{LINE_BREAK}BAB SATU\n" in output
    assert f"## 1.1.{TAB}Anak\n" in output


def test_number_markdown_melewati_fenced_code() -> None:
    markdown = "```markdown\n# bukan heading\n## juga bukan\n```\n\n# Pendahuluan\n"
    output = number_markdown(markdown, NumberingSpec("BAB_ROMAN"))

    assert "# bukan heading" in output
    assert "## juga bukan" in output
    assert f"# BAB I{LINE_BREAK}PENDAHULUAN\n" in output


def test_balance_title_judul_pendek_satu_baris() -> None:
    assert balance_title("Laporan Tugas") == ("Laporan Tugas",)
    assert balance_title("") == ("",)
    assert balance_title("x" * 80) == ("x" * 80,)


def test_balance_title_dua_kata_panjang_tidak_crash() -> None:
    text = ("A" * 30) + " " + ("B" * 30)
    assert len(text) > 55

    lines = balance_title(text)

    assert lines == ("A" * 30, "B" * 30)
    assert " ".join(lines) == text


def test_balance_title_memecah_judul_panjang() -> None:
    text = "Optimasi Pipeline Pemrosesan Dokumen Markdown untuk Laporan Tugas Akhir"

    lines = balance_title(text)

    assert 2 <= len(lines) <= 3
    assert " ".join(lines) == text
    assert max(len(line) for line in lines) < len(text)


def test_number_markdown_dan_alias_sama() -> None:
    markdown = "# Pendahuluan\n"
    assert number_markdown(markdown, NumberingSpec()) == number_markdown_headings(
        markdown, NumberingSpec()
    )
