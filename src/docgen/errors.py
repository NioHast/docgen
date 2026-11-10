"""Hierarki error tunggal untuk ``docgen``.

Semua error yang dapat ditampilkan ke pengguna wajib berupa subclass
``DocgenError``. Setiap error membawa ``code``, ``path``, dan ``key`` opsional;
``format()`` menyusun pesan CLI yang deterministik dan ``exit_code`` menentukan
status proses. ``StageError`` menambahkan nama stage dan ``cause`` asli.

Stage membungkus exception tak dikenal menjadi ``StageError`` agar CLI tetap
menghasilkan exit code yang stabil. Modul ini tidak melakukan I/O dan tidak
menangkap error.
"""

from pathlib import Path


class DocgenError(Exception):
    """Error dasar dengan kode, path, dan exit code yang stabil."""

    exit_code: int = 1
    default_code: str = "DOCGEN"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        path: str | Path | None = None,
        key: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = str(message)
        self.code = code or self.default_code
        self.path = Path(path) if path is not None else None
        self.key = key

    def format(self) -> str:
        """Format pesan yang siap dicetak CLI."""

        parts: list[str] = []
        if self.path is not None:
            parts.append(str(self.path))
        if self.key:
            parts.append(f"kunci '{self.key}'")
        prefix = ": ".join(parts)
        text = self.message
        if self.code:
            text = f"{text} ({self.code})"
        return f"{prefix}: {text}" if prefix else text

    def __str__(self) -> str:  # pragma: no cover - ditutup oleh test CLI
        return self.format()


class ConfigError(DocgenError):
    """Kesalahan konfigurasi, format, struktur, atau aset."""

    default_code = "CFG"


class DocumentError(DocgenError):
    """Kesalahan dokumen Markdown dan validasi silangnya."""

    default_code = "DOC"


class MetadataError(DocumentError):
    """Kesalahan metadata front matter."""

    default_code = "META"


class ValidationError(DocgenError):
    """Kesalahan validasi input pengguna."""

    default_code = "VAL"


class StageError(DocgenError):
    """Kegagalan satu stage; menyimpan nama stage dan cause asli."""

    default_code = "STAGE"

    def __init__(
        self,
        stage: str,
        message: str,
        *,
        cause: BaseException | None = None,
        code: str | None = None,
        path: str | Path | None = None,
        key: str | None = None,
    ) -> None:
        super().__init__(message, code=code, path=path, key=key)
        self.stage = stage
        self.cause = cause

    def format(self) -> str:
        return f"[{self.stage}] {super().format()}"


class StageOrderError(DocgenError):
    """Deklarasi stage melanggar urutan atau guard kanonik."""

    default_code = "STAGE-ORDER"


class ToolMissingError(DocgenError):
    """Perkakas eksternal wajib tidak tersedia."""

    default_code = "TOOL-MISSING"

    def __init__(
        self,
        tool: str,
        message: str | None = None,
        *,
        code: str | None = None,
        path: str | Path | None = None,
        key: str | None = None,
    ) -> None:
        super().__init__(
            message or f"perkakas '{tool}' tidak ditemukan",
            code=code,
            path=path,
            key=key,
        )
        self.tool = tool


class ExternalToolError(DocgenError):
    """Kegagalan perkakas eksternal."""

    default_code = "TOOL"


class WordError(ExternalToolError):
    """Kegagalan Microsoft Word."""

    default_code = "WORD"


class PdfError(ExternalToolError):
    """Kegagalan pembuatan PDF."""

    default_code = "PDF"


class IdempotencyError(DocgenError):
    """Stage mengubah output saat dijalankan ulang."""

    default_code = "IDEMPOTENCY"


class OutputError(DocgenError):
    """Kegagalan workspace atau penulisan output."""

    default_code = "OUTPUT"


class ManifestError(DocgenError):
    """Kesalahan manifest Adeu."""

    default_code = "MANIFEST"


class ReconcileError(DocgenError):
    """Kesalahan rekonsiliasi paragraf."""

    default_code = "RECONCILE"


class AssetError(ConfigError):
    """Aset paket hilang atau tidak valid."""

    default_code = "CFG-ASSET"
