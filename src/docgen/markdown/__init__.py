"""Parser dan penomoran Markdown bersama untuk fitur non-Pandoc.

Modul ini sengaja kecil dan bebas dari ``python-docx``/``lxml`` agar bisa
dipakai oleh Adeu, validasi, stage front matter, dan alat dev tanpa duplikasi
parser.
"""

from .blocks import (
    MarkdownBlock,
    MarkdownError,
    clean_text,
    iter_candidate_texts,
    load_markdown_blocks,
    load_markdown_directory,
    normalize_for_match,
    normalize_heading,
    normalize_inline,
    normalize_path,
    parse_markdown_blocks,
)
from .headings import (
    Heading,
    HeadingNumberer,
    MarkdownHeading,
    MarkdownHeadingError,
    NumberingSpec,
    balance_title,
    format_chapter_number,
    heading_level,
    is_unnumbered,
    number_markdown,
    number_markdown_headings,
    parse_heading,
    render_heading,
    roman,
    uppercase_markdown,
)

__all__ = [
    "Heading",
    "HeadingNumberer",
    "MarkdownBlock",
    "MarkdownError",
    "MarkdownHeading",
    "MarkdownHeadingError",
    "NumberingSpec",
    "balance_title",
    "clean_text",
    "format_chapter_number",
    "heading_level",
    "is_unnumbered",
    "iter_candidate_texts",
    "load_markdown_blocks",
    "load_markdown_directory",
    "normalize_for_match",
    "normalize_heading",
    "normalize_inline",
    "normalize_path",
    "number_markdown",
    "number_markdown_headings",
    "parse_heading",
    "parse_markdown_blocks",
    "render_heading",
    "roman",
    "uppercase_markdown",
]
