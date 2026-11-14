"""Upload staging PPTX ke Google Drive sebagai presentasi Slides."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from . import DriveError

PPTX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
SLIDES_MIME_TYPE = "application/vnd.google-apps.presentation"
PRESENTATION_URL_TEMPLATE = "https://docs.google.com/presentation/d/{presentation_id}/edit"


@dataclass(frozen=True, slots=True)
class UploadedPresentation:
    """Presentasi hasil konversi Drive: ID, URL, dan nama remote."""

    presentation_id: str
    url: str
    name: str

    def __post_init__(self) -> None:
        if not self.presentation_id.strip():
            raise DriveError("Upload Drive tidak mengembalikan presentation ID.")
        if not self.url.startswith("https://docs.google.com/presentation/d/"):
            raise DriveError(f"URL presentasi Google tidak valid: {self.url!r}.")
        if not self.name.strip():
            raise DriveError("Nama presentasi Google tidak boleh kosong.")


@runtime_checkable
class DriveApi(Protocol):
    """Kontrak Drive Google; fake mengimplementasikan kontrak yang sama."""

    def upload_presentation(self, pptx: Path, *, name: str) -> UploadedPresentation:
        """Upload PPTX dan kembalikan presentasi Google Slides."""


class GoogleDriveApi:
    """Adapter tipis Google Drive v3 dengan media upload."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def upload_presentation(self, pptx: Path, *, name: str) -> UploadedPresentation:
        """Upload satu file PPTX sebagai ``application/vnd.google-apps.presentation``."""
        source = _validated_pptx(pptx)
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as error:  # pragma: no cover - extra google belum terpasang
            raise DriveError(
                "Extra 'google' belum terpasang; jalankan uv sync --extra google."
            ) from error
        media = MediaFileUpload(str(source), mimetype=PPTX_MIME_TYPE, resumable=True)
        try:
            request = self._service.files().create(
                body={"name": name, "mimeType": SLIDES_MIME_TYPE},
                media_body=media,
                fields="id,name",
            )
            payload = request.execute()
        except Exception as error:
            raise DriveError(f"Upload presentasi ke Drive gagal: {error}") from error
        if not isinstance(payload, dict):
            raise DriveError("Drive mengembalikan respons upload yang bukan objek JSON.")
        presentation_id = payload.get("id")
        if not isinstance(presentation_id, str) or not presentation_id.strip():
            raise DriveError("Google Drive upload tidak mengembalikan file ID.")
        remote_name = payload.get("name")
        return UploadedPresentation(
            presentation_id=presentation_id,
            url=PRESENTATION_URL_TEMPLATE.format(presentation_id=presentation_id),
            name=remote_name if isinstance(remote_name, str) and remote_name else name,
        )


def upload_presentation(
    drive: DriveApi,
    pptx: str | Path,
    *,
    name: str,
) -> UploadedPresentation:
    """Upload lewat adapter Drive mana pun, termasuk fake in-memory."""
    if not name.strip():
        raise DriveError("Nama presentasi upload tidak boleh kosong.")
    return drive.upload_presentation(Path(pptx), name=name)


def _validated_pptx(pptx: str | Path) -> Path:
    source = Path(pptx)
    if source.suffix.lower() != ".pptx":
        raise DriveError(f"Upload Slides memerlukan file .pptx, bukan {source.name!r}.")
    if not source.is_file():
        raise DriveError(f"File staging PPTX tidak ditemukan: {source}.")
    if source.stat().st_size <= 0:
        raise DriveError(f"File staging PPTX kosong: {source}.")
    return source


__all__ = [
    "PPTX_MIME_TYPE",
    "SLIDES_MIME_TYPE",
    "DriveApi",
    "GoogleDriveApi",
    "UploadedPresentation",
    "upload_presentation",
]
