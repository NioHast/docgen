"""Stage ``normalize``: spacing 1,5 baris, justify, dan hapus bold body.

Stage ini hanya mengubah ``word/document.xml``. Teks, run field, heading,
``CoverTitle``, caption, blok kode, daftar isi, dan section tidak diubah.
Urutan pipeline wajib menjaga stage ini sebelum ``equations`` dan
``blank_lines``.
"""

from __future__ import annotations

import time

from ..docx.layout import (
    LayoutError,
    LayoutReport,
    LayoutSpec,
    document_root,
    has_bold_field,
    is_exempt,
    normalize_layout,
    normalize_paragraph,
    preserve_tabs,
)
from ..docx.xml import sha256_c14n
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

# Nama error kontrak stage-api.
NormalizeError = LayoutError


class NormalizeStage(BaseStage):
    """Stage normalisasi layout paragraf."""

    name = StageName.NORMALIZE
    order = 80
    requires = canonical_prefix(StageName.NORMALIZE)
    mutates = frozenset({"word/document.xml"})
    idempotent = True

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        package = getattr(ctx, "package", None)
        if package is None:
            raise NormalizeError(
                "stage normalize membutuhkan DocumentPackage dari stage pandoc"
            )

        try:
            before = sha256_c14n(document_root(package))
            report = normalize_layout(package, spec=_spec_from_context(ctx))
            changed = sha256_c14n(document_root(package)) != before
        except NormalizeError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            raise NormalizeError(
                f"stage normalize gagal: {exc}",
                code="LAYOUT-STAGE",
            ) from exc

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "checked": report.checked,
                "normalized": report.normalized,
                "skipped": report.skipped,
                "fields_preserved": report.fields_preserved,
                "bold_runs_removed": report.bold_runs_removed,
            },
        )


def _spec_from_context(ctx: object) -> LayoutSpec:
    format_obj = getattr(ctx, "format", None)
    if format_obj is None:
        return LayoutSpec()
    try:
        return LayoutSpec.from_format(format_obj)
    except (TypeError, ValueError) as exc:
        raise NormalizeError(
            f"format layout tidak valid: {exc}",
            code="LAYOUT-SPEC",
        ) from exc


__all__ = [
    "LayoutError",
    "LayoutReport",
    "LayoutSpec",
    "NormalizeError",
    "NormalizeStage",
    "has_bold_field",
    "is_exempt",
    "normalize_layout",
    "normalize_paragraph",
    "preserve_tabs",
]
