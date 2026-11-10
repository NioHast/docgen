"""Stage ``pdf``: ekspor DOCX final ke PDF memakai Microsoft Word.

Stage ini hanya membaca DOCX dan menulis PDF. Tidak ada mutasi package.
Aturan ``--allow-missing-word`` diterapkan di sini: target ``both`` boleh
melewati PDF, sedangkan target ``pdf`` selalu gagal bila Word tidak ada.
"""

import time

from ..errors import PdfError, ToolMissingError, WordError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix
from .office import (
    _check_pdf,
    _docx_path,
    _pdf_path,
    _word_adapter,
)


class PdfStage(BaseStage):
    """Ekspor DOCX final ke PDF; Word-only."""

    name = StageName.PDF
    order = 170
    requires = canonical_prefix(StageName.PDF)
    mutates = frozenset()
    idempotent = False

    def enabled(self, ctx: object) -> bool:
        if getattr(ctx, "dry_run", False):
            return False
        target = getattr(getattr(ctx, "options", None), "target", "both")
        return target in {"pdf", "both"}

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        if not self.enabled(ctx):
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                warnings=("target tidak meminta PDF.",),
            )

        docx = None
        pdf = _pdf_path(ctx)
        adapter = _word_adapter(ctx, action="export_pdf")

        if not adapter.available():
            target = getattr(getattr(ctx, "options", None), "target", "both")
            allow = bool(getattr(getattr(ctx, "options", None), "allow_missing_word", False))
            if target == "both" and allow:
                return StageResult(
                    stage=self.name.value,
                    status="skipped",
                    changed=False,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    warnings=(
                        "Microsoft Word tidak tersedia; PDF dilewati dan DOCX "
                        "tetap dihasilkan (--allow-missing-word).",
                    ),
                )
            try:
                docx = _docx_path(ctx)
            except WordError:
                docx = None
            raise ToolMissingError(
                "Microsoft Word",
                "Microsoft Word tidak tersedia; PDF tidak dapat dihasilkan. "
                "Pasang Word desktop atau gunakan --target docx.",
                path=docx,
            )

        docx = _docx_path(ctx)
        try:
            result = adapter.export_pdf(docx, pdf)
        except PdfError, ToolMissingError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise PdfError(
                f"stage pdf gagal: {exc}",
                code="PDF-STAGE",
                path=pdf,
            ) from exc

        if not result.is_file():
            raise PdfError(
                "Word selesai tanpa error tetapi PDF tidak ditemukan.",
                code="PDF-OUTPUT",
                path=result,
            )
        _check_pdf(result)

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=False,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={"pdf_bytes": result.stat().st_size},
            artifacts=(result,),
        )
