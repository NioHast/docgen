"""Test edge case parser inline Markdown: escape, link, code, dan tabel."""

import pytest

from autooffice.deck.model import (
    MarkdownError,
    normalize_preserve_newlines,
    parse_inline,
    validate_plain_text,
)


def test_parse_inline_rejects_non_string_value() -> None:
    with pytest.raises(MarkdownError, match="harus string"):
        parse_inline(1)  # type: ignore[arg-type]


def test_validate_plain_text_rejects_non_string_value() -> None:
    with pytest.raises(MarkdownError, match="harus string"):
        validate_plain_text(1)  # type: ignore[arg-type]


def test_validate_plain_text_rejects_newline_when_single_line() -> None:
    with pytest.raises(MarkdownError, match="satu baris"):
        validate_plain_text("baris satu\nbaris dua", multiline=False)


def test_preserve_newlines_rejects_non_string_value() -> None:
    with pytest.raises(MarkdownError, match="harus string"):
        normalize_preserve_newlines(1)  # type: ignore[arg-type]


def test_preserve_newlines_rejects_newline_when_single_line() -> None:
    with pytest.raises(MarkdownError, match="satu baris"):
        normalize_preserve_newlines("baris satu\nbaris dua", multiline=False)


def test_table_separator_without_edge_pipes_is_rejected() -> None:
    with pytest.raises(MarkdownError, match="table"):
        parse_inline("--- | ---")


def test_pipe_wrapped_text_is_rejected_as_table() -> None:
    with pytest.raises(MarkdownError, match="table"):
        parse_inline("| kolom | nilai |")


def test_plain_text_rejects_italic_markup() -> None:
    with pytest.raises(MarkdownError, match="italic"):
        validate_plain_text("*miring*")


def test_empty_bold_marker_is_rejected() -> None:
    with pytest.raises(MarkdownError, match="bold Markdown kosong"):
        parse_inline("****")


def test_lone_asterisk_is_literal_text() -> None:
    parsed = parse_inline("a * b")

    assert parsed.plain_text == "a * b"


def test_asterisk_scanner_skips_double_star_pairs() -> None:
    parsed = parse_inline("a * **b**")

    assert parsed.plain_text == "a * b"
    assert any(segment.bold for segment in parsed.segments)


def test_empty_inline_code_is_rejected() -> None:
    with pytest.raises(MarkdownError, match="inline code kosong"):
        parse_inline("``")


def test_multiline_inline_code_is_rejected() -> None:
    with pytest.raises(MarkdownError, match="inline code harus satu baris"):
        parse_inline("`satu\ndua`")


def test_trailing_escape_is_rejected() -> None:
    with pytest.raises(MarkdownError, match="tanpa karakter tujuan"):
        parse_inline("\\")


def test_link_label_without_closing_bracket_is_rejected() -> None:
    with pytest.raises(MarkdownError, match="link yang tidak ditutup"):
        parse_inline("[label")


def test_link_without_closing_parenthesis_is_rejected() -> None:
    with pytest.raises(MarkdownError, match="URL link yang tidak ditutup"):
        parse_inline("[label](https://example.com")


def test_empty_link_label_is_rejected() -> None:
    with pytest.raises(MarkdownError, match="label link kosong"):
        parse_inline("[](https://example.com)")


def test_link_label_must_be_single_line() -> None:
    with pytest.raises(MarkdownError, match="label link harus satu baris"):
        parse_inline("[satu\ndua](https://example.com)")


def test_link_label_rejects_nested_markup() -> None:
    with pytest.raises(MarkdownError, match="label link hanya boleh plain text"):
        parse_inline("[a*b](https://example.com)")


@pytest.mark.parametrize("url", [" ", "https://example.com/a b"])
def test_link_url_rejects_empty_or_space(url: str) -> None:
    with pytest.raises(MarkdownError, match="kosong atau memuat spasi"):
        parse_inline(f"[label]({url})")


def test_link_url_requires_destination_after_scheme() -> None:
    with pytest.raises(MarkdownError, match="tanpa tujuan"):
        parse_inline("[label](mailto:)")


def test_http_link_requires_double_slash() -> None:
    with pytest.raises(MarkdownError, match="format https"):
        parse_inline("[label](http:example.com)")
