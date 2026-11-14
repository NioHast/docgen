"""Test parser inline Markdown dan normalisasi teks."""

import pytest

from autooffice.deck.model import (
    MarkdownError,
    normalize_inline,
    normalize_preserve_newlines,
    parse_inline,
    validate_plain_text,
)


def test_bold_is_stripped_from_plain_text() -> None:
    parsed = parse_inline("Kontrak **lebih murah** daripada perbaikan.")

    assert parsed.plain_text == "Kontrak lebih murah daripada perbaikan."
    assert any(segment.bold for segment in parsed.segments)


def test_inline_code_is_preserved_as_plain_text() -> None:
    parsed = parse_inline("Pakai `item1.text` sebagai leaf.")

    assert parsed.plain_text == "Pakai item1.text sebagai leaf."
    assert any(segment.code for segment in parsed.segments)


def test_link_keeps_label_not_url() -> None:
    parsed = parse_inline("Baca [kontrak](https://example.com/kontrak).")

    assert parsed.plain_text == "Baca kontrak."
    assert parsed.segments[1].link == "https://example.com/kontrak"


def test_mailto_link_is_allowed() -> None:
    parsed = parse_inline("Hubungi [tim](mailto:tim@example.com).")

    assert parsed.plain_text == "Hubungi tim."


def test_escaped_bracket_inside_link_label() -> None:
    parsed = parse_inline(r"[a\]b](https://example.com)")

    assert parsed.plain_text == "a]b"


def test_link_target_keeps_balanced_parentheses() -> None:
    url = "https://en.wikipedia.org/wiki/Function_(mathematics)"
    parsed = parse_inline(f"[F]({url})")

    assert parsed.plain_text == "F"
    assert parsed.segments[0].link == url


def test_link_target_supports_escaped_closing_parenthesis() -> None:
    parsed = parse_inline(r"[F](https://example.com/a\)b)")

    assert parsed.segments[0].link == "https://example.com/a)b"


def test_unbalanced_link_parentheses_are_rejected() -> None:
    with pytest.raises(MarkdownError, match="tidak ditutup"):
        parse_inline("[F](https://en.wikipedia.org/wiki/Function_(mathematics)")


@pytest.mark.parametrize(
    "url",
    ["http://[::1", "http://example.com\uff0fx"],
)
def test_malformed_link_url_rejected(url: str) -> None:
    with pytest.raises(MarkdownError, match="URL link"):
        parse_inline(f"[label]({url})")


@pytest.mark.parametrize("url", ["http://:80", "http://user@"])
def test_link_url_without_host_rejected(url: str) -> None:
    with pytest.raises(MarkdownError, match="host"):
        parse_inline(f"[label]({url})")


@pytest.mark.parametrize(
    ("value", "match"),
    [
        ("\x00", "karakter kontrol"),
        ("\x01", "karakter kontrol"),
        ("\u200b", "tak terlihat"),
    ],
)
def test_invisible_or_control_character_rejected(value: str, match: str) -> None:
    with pytest.raises(MarkdownError, match=match):
        parse_inline(value)


@pytest.mark.parametrize("value", ["a\tb", "a\nb"])
def test_preserve_newlines_allows_tabs_and_newlines(value: str) -> None:
    assert normalize_preserve_newlines(value) == value


def test_escaped_characters_are_literal() -> None:
    parsed = parse_inline(r"Bintang \* dan underscore \_ dan kurung \[x\].")

    assert parsed.plain_text == "Bintang * dan underscore _ dan kurung [x]."


def test_whitespace_is_normalized_per_line() -> None:
    parsed = parse_inline("  Halo    dunia  \n\n  Baris   kedua  ")

    assert parsed.plain_text == "Halo dunia\n\nBaris kedua"


def test_em_and_en_dash_are_rejected() -> None:
    with pytest.raises(MarkdownError, match="dash"):
        parse_inline("A \u2014 B")

    with pytest.raises(MarkdownError, match="dash"):
        parse_inline("A \u2013 B")


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("*miring*", "italic"),
        ("# Heading", "heading"),
        ("- satu", "list"),
        ("1. satu", "list"),
        ("> kutipan", "blockquote"),
        ("![alt](https://example.com/a.png)", "gambar"),
        ("[label](relative/path)", "link"),
        ("[label](file:///tmp/x)", "link"),
        ("[label](ftp://example.com)", "link"),
        ("[label](https://)", "URL"),
        ("<b>teks</b>", "HTML"),
        ("[^1]", "link"),
        ("**tidak ditutup", "bold"),
        ("`tidak ditutup", "inline code"),
        (r"escape \q", "escape"),
    ],
)
def test_invalid_inline_markdown_rejected(text: str, match: str) -> None:
    with pytest.raises(MarkdownError, match=match):
        parse_inline(text)


def test_one_line_field_rejects_newline() -> None:
    with pytest.raises(MarkdownError, match="satu baris"):
        parse_inline("baris satu\nbaris dua", multiline=False)


def test_empty_inline_text_rejected() -> None:
    with pytest.raises(MarkdownError, match="kosong"):
        parse_inline("   ")


def test_normalize_inline_returns_plain_text() -> None:
    assert normalize_inline("**Halo** `dunia`.") == "Halo dunia."


def test_validate_plain_text_rejects_markdown() -> None:
    with pytest.raises(MarkdownError, match="plain text"):
        validate_plain_text("**bold**")

    with pytest.raises(MarkdownError, match="plain text"):
        validate_plain_text("`code`")

    with pytest.raises(MarkdownError, match="plain text"):
        validate_plain_text("[label](https://example.com)")

    with pytest.raises(MarkdownError, match="footnote"):
        validate_plain_text("[^1]")


def test_validate_plain_text_accepts_raw_url_and_symbols() -> None:
    assert validate_plain_text("Sumber: https://example.com/data, 100%") == (
        "Sumber: https://example.com/data, 100%"
    )


def test_preserve_newlines_keeps_internal_spacing() -> None:
    normalized = normalize_preserve_newlines("\n\n  a  \n\n  b  \n\n")

    assert normalized == "  a  \n\n  b  "


def test_preserve_newlines_converts_crlf() -> None:
    normalized = normalize_preserve_newlines("baris satu\r\nbaris dua\r\n")

    assert normalized == "baris satu\nbaris dua"


def test_preserve_newlines_rejects_empty_text() -> None:
    with pytest.raises(MarkdownError, match="kosong"):
        normalize_preserve_newlines("\n\n   \n")
