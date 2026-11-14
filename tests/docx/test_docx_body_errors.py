"""Tes pemetaan error domain saat ``word/document.xml`` tidak ada."""

import zipfile
from pathlib import Path

import pytest

from autooffice.docx.adeu.paragraph_ids import _body_paragraphs
from autooffice.docx.package.bookmarks import BookmarkError, iter_bookmarks
from autooffice.docx.package.captions import CaptionError, iter_captions
from autooffice.docx.package.fields import FieldError, insert_toc
from autooffice.docx.package.package import CONTENT_TYPES_PART, PACKAGE_RELS_PART, DocumentPackage
from autooffice.docx.package.sections import SectionError, iter_sections

CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _package_without_document(tmp_path: Path) -> DocumentPackage:
    """Package minimal tanpa part dokumen; validasi OPC dilewati."""

    path = tmp_path / "tanpa-dokumen.docx"
    content_types = (
        f'<Types xmlns="{CT_NS}">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "</Types>"
    ).encode()
    package_rels = f'<Relationships xmlns="{REL_NS}"/>'.encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(CONTENT_TYPES_PART, content_types)
        archive.writestr(PACKAGE_RELS_PART, package_rels)
    return DocumentPackage.load(path, validate=False)


def test_bookmarks_missing_document_maps_to_bookmark_error(tmp_path: Path) -> None:
    package = _package_without_document(tmp_path)

    with pytest.raises(BookmarkError):
        iter_bookmarks(package)


def test_captions_missing_document_maps_to_caption_no_body(tmp_path: Path) -> None:
    package = _package_without_document(tmp_path)

    with pytest.raises(CaptionError) as excinfo:
        iter_captions(package)

    assert excinfo.value.code == "CAPTION-NO-BODY"


def test_fields_missing_document_maps_to_field_error(tmp_path: Path) -> None:
    package = _package_without_document(tmp_path)

    with pytest.raises(FieldError):
        insert_toc(package, title="DAFTAR ISI")


def test_sections_missing_document_maps_to_section_error(tmp_path: Path) -> None:
    package = _package_without_document(tmp_path)

    with pytest.raises(SectionError):
        iter_sections(package)


def test_adeu_missing_document_maps_to_bookmark_error(tmp_path: Path) -> None:
    package = _package_without_document(tmp_path)

    with pytest.raises(BookmarkError):
        _body_paragraphs(package)
