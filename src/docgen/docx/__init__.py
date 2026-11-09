"""Fondasi DOCX: satu package, satu load, satu save.

Semua operasi ZIP/OPC dan XML untuk pipeline melewati modul ini. Stage tidak
boleh memakai ``zipfile``, ``python-docx``, atau traversal ``lxml`` sendiri.
"""

from __future__ import annotations

from ..errors import DocgenError


class DocxError(DocgenError):
    """Kesalahan umum pada operasi DOCX."""

    default_code = "DOCX"


class PackageError(DocxError):
    """ZIP atau struktur OPC tidak dapat dibaca."""

    default_code = "PKG"


class PartNotFoundError(PackageError):
    """Part yang diminta tidak ada di dalam package."""

    default_code = "PART-MISSING"


class PartExistsError(PackageError):
    """Part atau relationship baru bentrok dengan yang sudah ada."""

    default_code = "PART-EXISTS"


class InvalidPackageError(PackageError):
    """Package tidak valid saat ``validate()`` dijalankan."""

    default_code = "PKG-INVALID"


class SaveError(PackageError):
    """Package gagal ditulis ke disk."""

    default_code = "SAVE"


class XmlError(DocxError):
    """XML tidak well-formed, memakai entity, atau tidak didukung."""

    default_code = "XML"


# Impor setelah kelas error didefinisikan agar submodule dapat mengimpor balik
# dari package ini tanpa siklus inisialisasi.
from .names import *  # noqa: E402,F401,F403
from .names import __all__ as _names_all  # noqa: E402
from .package import (  # noqa: E402
    CONTENT_TYPES_PART,
    DOCUMENT_PART,
    MAIN_DOCUMENT_CONTENT_TYPE,
    PACKAGE_RELS_PART,
    RELATIONSHIPS_CONTENT_TYPE,
    DocumentPackage,
    DocxPackage,
    PartInfo,
    Relationship,
    REL_TYPE_FOOTER,
    REL_TYPE_HEADER,
    REL_TYPE_HYPERLINK,
    REL_TYPE_IMAGE,
    REL_TYPE_OFFICE_DOCUMENT,
    REL_TYPE_STYLES,
)
from .xml import (  # noqa: E402
    PPR_ORDER,
    RPR_ORDER,
    SECTPR_ORDER,
    TBLPR_ORDER,
    TCPR_ORDER,
    canonicalize_xml,
    ensure_ppr,
    ensure_rpr,
    ensure_tblpr,
    ensure_tcpr,
    get_or_add,
    insert_ordered,
    is_on,
    iter_paragraphs,
    iter_runs,
    paragraph_text,
    parse_xml,
    qn,
    run_text,
    serialize_xml,
    sha256_c14n,
)

__all__ = [
    "CONTENT_TYPES_PART",
    "DOCUMENT_PART",
    "DocxError",
    "DocumentPackage",
    "DocxPackage",
    "InvalidPackageError",
    "MAIN_DOCUMENT_CONTENT_TYPE",
    "PACKAGE_RELS_PART",
    "PPR_ORDER",
    "PackageError",
    "PartExistsError",
    "PartInfo",
    "PartNotFoundError",
    "RELATIONSHIPS_CONTENT_TYPE",
    "REL_TYPE_FOOTER",
    "REL_TYPE_HEADER",
    "REL_TYPE_HYPERLINK",
    "REL_TYPE_IMAGE",
    "REL_TYPE_OFFICE_DOCUMENT",
    "REL_TYPE_STYLES",
    "RPR_ORDER",
    "Relationship",
    "SECTPR_ORDER",
    "SaveError",
    "TBLPR_ORDER",
    "TCPR_ORDER",
    "XmlError",
    "canonicalize_xml",
    "ensure_ppr",
    "ensure_rpr",
    "ensure_tblpr",
    "ensure_tcpr",
    "get_or_add",
    "insert_ordered",
    "is_on",
    "iter_paragraphs",
    "iter_runs",
    "paragraph_text",
    "parse_xml",
    "qn",
    "run_text",
    "serialize_xml",
    "sha256_c14n",
] + list(_names_all)
