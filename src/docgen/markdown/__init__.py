"""Parser Markdown bersama untuk fitur non-Pandoc.

Modul ini sengaja kecil dan bebas dari ``python-docx``/``lxml`` agar bisa
dipakai oleh Adeu, validasi, dan alat dev tanpa duplikasi parser.
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

__all__ = [
    "MarkdownBlock",
    "MarkdownError",
    "clean_text",
    "iter_candidate_texts",
    "load_markdown_blocks",
    "load_markdown_directory",
    "normalize_for_match",
    "normalize_heading",
    "normalize_inline",
    "normalize_path",
    "parse_markdown_blocks",
]
