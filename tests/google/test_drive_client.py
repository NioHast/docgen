"""Test adapter GoogleDriveApi dengan service palsu tanpa panggilan jaringan."""

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from autooffice.google import DriveError
from autooffice.google.drive import (
    PPTX_MIME_TYPE,
    SLIDES_MIME_TYPE,
    DriveApi,
    GoogleDriveApi,
    UploadedPresentation,
    upload_presentation,
)


class FakeMediaFileUpload:
    """Media upload palsu yang mencatat berkas dan MIME yang dikirim adapter."""

    def __init__(self, filename: str, *, mimetype: str, resumable: bool) -> None:
        self.filename = filename
        self._mimetype = mimetype
        self.resumable = resumable
        self.size = Path(filename).stat().st_size

    def mimetype(self) -> str:
        return self._mimetype


class FakeRequest:
    """Request Drive palsu yang mengembalikan payload atau error yang disiapkan."""

    def __init__(self, result: object) -> None:
        self.result = result

    def execute(self) -> object:
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class FakeDriveService:
    """Service Drive minimal: ``files().create(...).execute()``."""

    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def files(self) -> FakeDriveService:
        return self

    def create(self, **kwargs: object) -> FakeRequest:
        self.calls.append(kwargs)
        return FakeRequest(self.result)


class ServiceError(Exception):
    """Error HTTP gaya googleapiclient dengan status pada ``resp``."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.resp = SimpleNamespace(status=status)


@pytest.fixture(autouse=True)
def fake_googleapiclient(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ganti modul googleapiclient dengan media upload palsu."""
    parent = ModuleType("googleapiclient")
    parent.__path__ = []
    http_module = ModuleType("googleapiclient.http")
    http_module.MediaFileUpload = FakeMediaFileUpload
    monkeypatch.setitem(sys.modules, "googleapiclient", parent)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http_module)


def _pptx(tmp_path: Path, payload: bytes = b"PK\x03\x04fake-pptx") -> Path:
    target = tmp_path / "deck.pptx"
    target.write_bytes(payload)
    return target


def test_upload_creates_slides_file_with_media_and_returns_url(tmp_path: Path) -> None:
    staging = _pptx(tmp_path)
    service = FakeDriveService({"id": "presentation-1", "name": "Remote deck"})
    adapter = GoogleDriveApi(service)

    uploaded = upload_presentation(adapter, str(staging), name="Local deck")

    assert uploaded == UploadedPresentation(
        presentation_id="presentation-1",
        url="https://docs.google.com/presentation/d/presentation-1/edit",
        name="Remote deck",
    )
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["body"] == {"name": "Local deck", "mimeType": SLIDES_MIME_TYPE}
    assert call["fields"] == "id,name"
    media = call["media_body"]
    assert isinstance(media, FakeMediaFileUpload)
    assert media.filename == str(staging)
    assert media.mimetype() == PPTX_MIME_TYPE
    assert media.resumable is True


def test_upload_falls_back_to_local_name_when_drive_omits_name(tmp_path: Path) -> None:
    staging = _pptx(tmp_path)
    service = FakeDriveService({"id": "presentation-1", "name": ""})

    uploaded = GoogleDriveApi(service).upload_presentation(staging, name="Local deck")

    assert uploaded.name == "Local deck"


def test_upload_falls_back_to_local_name_when_drive_name_is_not_text(tmp_path: Path) -> None:
    staging = _pptx(tmp_path)
    service = FakeDriveService({"id": "presentation-1", "name": 42})

    uploaded = GoogleDriveApi(service).upload_presentation(staging, name="Local deck")

    assert uploaded.name == "Local deck"


def test_upload_rejects_non_object_payload(tmp_path: Path) -> None:
    staging = _pptx(tmp_path)
    service = FakeDriveService(["not", "an", "object"])

    with pytest.raises(DriveError, match="bukan objek JSON"):
        GoogleDriveApi(service).upload_presentation(staging, name="Deck")


@pytest.mark.parametrize(
    "payload",
    [{}, {"id": ""}, {"id": "   "}, {"id": 42}, {"id": None}],
    ids=["missing", "empty", "blank", "integer", "null"],
)
def test_upload_rejects_payload_without_file_id(tmp_path: Path, payload: dict[str, object]) -> None:
    staging = _pptx(tmp_path)
    service = FakeDriveService(payload)

    with pytest.raises(DriveError, match="tidak mengembalikan file ID"):
        GoogleDriveApi(service).upload_presentation(staging, name="Deck")


def test_upload_wraps_service_error(tmp_path: Path) -> None:
    staging = _pptx(tmp_path)
    service = FakeDriveService(RuntimeError("upload terputus"))

    with pytest.raises(DriveError, match="Upload presentasi ke Drive gagal: upload terputus"):
        GoogleDriveApi(service).upload_presentation(staging, name="Deck")


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_upload_maps_http_errors_without_retry(tmp_path: Path, status: int) -> None:
    staging = _pptx(tmp_path)
    service = FakeDriveService(ServiceError(status))

    with pytest.raises(DriveError, match=f"HTTP {status}"):
        GoogleDriveApi(service).upload_presentation(staging, name="Deck")

    assert len(service.calls) == 1


def test_upload_rejects_blank_name_before_calling_drive(tmp_path: Path) -> None:
    staging = _pptx(tmp_path)
    service = FakeDriveService({"id": "presentation-1"})

    with pytest.raises(DriveError, match="Nama presentasi upload"):
        upload_presentation(GoogleDriveApi(service), staging, name="  ")

    assert service.calls == []


def test_upload_rejects_non_pptx_before_calling_drive(tmp_path: Path) -> None:
    staging = tmp_path / "deck.txt"
    staging.write_text("bukan pptx", encoding="utf-8")
    service = FakeDriveService({"id": "presentation-1"})

    with pytest.raises(DriveError, match=r"\.pptx"):
        GoogleDriveApi(service).upload_presentation(staging, name="Deck")

    assert service.calls == []


def test_upload_rejects_missing_file_before_calling_drive(tmp_path: Path) -> None:
    service = FakeDriveService({"id": "presentation-1"})

    with pytest.raises(DriveError, match="tidak ditemukan"):
        GoogleDriveApi(service).upload_presentation(tmp_path / "missing.pptx", name="Deck")

    assert service.calls == []


def test_upload_rejects_empty_file_before_calling_drive(tmp_path: Path) -> None:
    staging = _pptx(tmp_path, b"")
    service = FakeDriveService({"id": "presentation-1"})

    with pytest.raises(DriveError, match="kosong"):
        GoogleDriveApi(service).upload_presentation(staging, name="Deck")

    assert service.calls == []


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (
            {
                "presentation_id": " ",
                "url": "https://docs.google.com/presentation/d/x/edit",
                "name": "Deck",
            },
            "ID",
        ),
        (
            {"presentation_id": "x", "url": "https://example.com/x", "name": "Deck"},
            "URL",
        ),
        (
            {
                "presentation_id": "x",
                "url": "https://docs.google.com/presentation/d/x/edit",
                "name": " ",
            },
            "Nama",
        ),
    ],
    ids=["id", "url", "name"],
)
def test_uploaded_presentation_rejects_invalid_fields(
    kwargs: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(DriveError, match=match):
        UploadedPresentation(**kwargs)


def test_google_drive_adapter_satisfies_protocol() -> None:
    assert isinstance(GoogleDriveApi(FakeDriveService({})), DriveApi)
