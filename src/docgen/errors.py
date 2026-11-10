"""Hierarki error tunggal untuk ``docgen``.

Semua error yang dapat ditampilkan ke pengguna wajib berupa subclass
``DocgenError``. Stage membungkus exception tak dikenal menjadi
``StageError`` agar CLI tetap menghasilkan exit code yang stabil.
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
    default_code = "CFG"


class DocumentError(DocgenError):
    default_code = "DOC"


class MetadataError(DocumentError):
    default_code = "META"


class ValidationError(DocgenError):
    default_code = "VAL"


class StageError(DocgenError):
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
    default_code = "STAGE-ORDER"


class ToolMissingError(DocgenError):
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
    default_code = "TOOL"


class WordError(ExternalToolError):
    default_code = "WORD"


class PdfError(ExternalToolError):
    default_code = "PDF"


class IdempotencyError(DocgenError):
    default_code = "IDEMPOTENCY"


class OutputError(DocgenError):
    default_code = "OUTPUT"


class ManifestError(DocgenError):
    default_code = "MANIFEST"


class ReconcileError(DocgenError):
    default_code = "RECONCILE"


class AssetError(ConfigError):
    default_code = "CFG-ASSET"
