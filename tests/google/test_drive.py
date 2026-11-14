"""Test upload Drive fake dan kontrak MIME presentasi."""

from pathlib import Path

import pytest

from autooffice.google import DriveError
from autooffice.google.drive import (
    PPTX_MIME_TYPE,
    SLIDES_MIME_TYPE,
    DriveApi,
    upload_presentation,
)
from autooffice.google.fake import FakeGoogleServices


def test_upload_returns_presentation_id_and_url(
    fake_google: FakeGoogleServices,
    tmp_path: Path,
) -> None:
    staging = tmp_path / "deck.slides-upload.pptx"
    staging.write_bytes(b"PK\x03\x04fake-pptx")

    uploaded = upload_presentation(fake_google.drive, staging, name="F2 Google")

    assert uploaded.presentation_id == "presentation-1"
    assert uploaded.url.endswith("/presentation-1/edit")
    assert uploaded.name == "F2 Google"
    request = fake_google.drive.uploads[-1]
    assert request.media_mime_type == PPTX_MIME_TYPE
    assert request.target_mime_type == SLIDES_MIME_TYPE
    assert request.size_bytes == len(b"PK\x03\x04fake-pptx")


def test_fake_drive_satisfies_protocol(fake_google: FakeGoogleServices) -> None:
    assert isinstance(fake_google.drive, DriveApi)


def test_upload_rejects_missing_or_non_pptx(
    fake_google: FakeGoogleServices,
    tmp_path: Path,
) -> None:
    with pytest.raises(DriveError, match="tidak ditemukan"):
        upload_presentation(fake_google.drive, tmp_path / "missing.pptx", name="Deck")

    text_file = tmp_path / "deck.txt"
    text_file.write_text("bukan pptx", encoding="utf-8")
    with pytest.raises(DriveError, match=r"\.pptx"):
        upload_presentation(fake_google.drive, text_file, name="Deck")
