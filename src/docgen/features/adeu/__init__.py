"""Integrasi Adeu: bookmark ``pNNNN``, manifest, dan rekonsiliasi.

Modul ini hanya menyediakan API fitur. Hook ke pipeline (setelah ``lists``,
sebelum ``save``) dimiliki oleh pemilik ``pipeline.py``.
"""

from .manifest import (
    DEFAULT_MANIFEST_DIR,
    DEFAULT_MANIFEST_NAME,
    KIND_VALUES,
    MANIFEST_VERSION,
    PARAGRAPH_ID_RE,
    Manifest,
    ManifestParagraph,
    default_manifest_path,
    dump_manifest,
    load_manifest,
    manifest_from_dict,
    manifest_to_dict,
    sha256_text,
    validate_manifest,
)
from .paragraph_ids import (
    AdeuOptions,
    add_paragraph_ids,
    analyze_manifest,
    prepare_manifest,
    resolve_options,
    run_docx,
    write_prepared_manifest,
)
from .reconcile import (
    DocxSnapshot,
    MarkdownBlock,
    ReconcileResult,
    SourceMatch,
    build_report,
    extract_bookmarks,
    find_source,
    run,
)

__all__ = [
    "DEFAULT_MANIFEST_DIR",
    "DEFAULT_MANIFEST_NAME",
    "KIND_VALUES",
    "MANIFEST_VERSION",
    "PARAGRAPH_ID_RE",
    "AdeuOptions",
    "DocxSnapshot",
    "Manifest",
    "ManifestParagraph",
    "MarkdownBlock",
    "ReconcileResult",
    "SourceMatch",
    "add_paragraph_ids",
    "analyze_manifest",
    "build_report",
    "default_manifest_path",
    "dump_manifest",
    "extract_bookmarks",
    "find_source",
    "load_manifest",
    "manifest_from_dict",
    "manifest_to_dict",
    "prepare_manifest",
    "resolve_options",
    "run",
    "run_docx",
    "sha256_text",
    "validate_manifest",
    "write_prepared_manifest",
]
