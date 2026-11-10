"""Stage ``terms``: check, apply, verify, dan gate istilah.

Stage hanya aktif bila ``ctx.options.terms`` bernilai true. Tanpa flag tersebut
tidak ada auto-italic, tidak ada gate, dan tidak ada review file.
"""

import time
from pathlib import Path

from .. import paths
from ..docx.terms import (
    Glossary,
    GlossaryError,
    TermsError,
    apply_terms,
    collect_markdown_terms,
    load_glossary,
    merge_glossaries,
    unique_terms,
    verify_terms,
    write_review_file,
)
from ..errors import AssetError
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

REVIEW_RELATIVE = Path(".laporan") / "istilah-baru.txt"


def review_path_for(document_path: str | Path) -> Path:
    """Lokasi baku review istilah di samping ``document.md``."""

    return Path(document_path).resolve().parent / REVIEW_RELATIVE


def _same_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve() == second.resolve()
    except OSError:
        return first == second


def _package_glossary() -> Path | None:
    try:
        return paths.glossary_file()
    except AssetError:
        return None


def resolve_glossary(
    document_path: str | Path,
    override: str | Path | Glossary | None = None,
) -> Glossary:
    """Muat glosarium package lalu override user di samping dokumen.

    Presedensi user > package dan merge dilakukan per frasa (casefold).
    ``override`` eksplisit (mis. ``ctx.glossary``) boleh berupa path atau
    :class:`Glossary`; bila tidak ada, ``<document_dir>/istilah.tsv`` dipakai.
    """

    document_dir = Path(document_path).resolve().parent
    package_path = _package_glossary()
    explicit_glossary: Glossary | None = override if isinstance(override, Glossary) else None
    candidates: list[Path] = []
    if isinstance(override, str | Path):
        candidates.append(Path(override))
    user_path = document_dir / "istilah.tsv"
    if user_path.exists():
        candidates.append(user_path)

    unique_candidates: list[Path] = []
    for candidate in candidates:
        if package_path is not None and _same_path(Path(candidate), package_path):
            continue
        if any(_same_path(Path(candidate), known) for known in unique_candidates):
            continue
        unique_candidates.append(Path(candidate))

    if package_path is None and not unique_candidates and explicit_glossary is None:
        raise GlossaryError(
            "glosarium paket dan istilah.tsv pengguna tidak ditemukan; "
            "letakkan istilah.tsv di samping document.md",
            code="GLOSSARY-MISSING",
            path=document_dir / "istilah.tsv",
        )

    glossary: Glossary | None = None
    if package_path is not None:
        glossary = load_glossary(package_path)
    if explicit_glossary is not None:
        glossary = (
            explicit_glossary if glossary is None else merge_glossaries(glossary, explicit_glossary)
        )
    for candidate in unique_candidates:
        loaded = load_glossary(candidate)
        glossary = loaded if glossary is None else merge_glossaries(glossary, loaded)
    assert glossary is not None
    return glossary


class TermsStage(BaseStage):
    """Check Markdown, apply istilah, verify, dan tulis review file."""

    name = StageName.TERMS
    order = 120
    requires = canonical_prefix(StageName.TERMS)
    mutates = frozenset({"word/document.xml", "word/styles.xml"})

    def enabled(self, ctx: object) -> bool:
        options = getattr(ctx, "options", None)
        return bool(getattr(options, "terms", False))

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        if not self.enabled(ctx):
            return StageResult(
                stage=self.name.value,
                status="skipped",
                changed=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                metrics={"terms": 0},
            )

        package = getattr(ctx, "package", None)
        if package is None:
            raise TermsError(
                "stage terms membutuhkan DocumentPackage hasil Pandoc",
                code="TERMS-NO-PACKAGE",
                path=getattr(getattr(ctx, "document", None), "path", None),
            )

        document = ctx.document  # type: ignore[attr-defined]
        glossary = resolve_glossary(
            document.path,
            getattr(ctx, "glossary", None),
        )
        markdown_terms = collect_markdown_terms(document.body)

        report = apply_terms(package, glossary)
        verification = verify_terms(package, glossary)

        reviews = unique_terms((*report.reviews, *markdown_terms))
        review_path = review_path_for(document.path)
        write_review_file(review_path, reviews)

        if verification.violations:
            detail = "\n".join(verification.violations)
            raise TermsError(
                "verifikasi istilah gagal:\n" + detail,
                code="TERMS-VERIFY",
                path=review_path,
            )

        artifacts = getattr(ctx, "artifacts", None)
        if artifacts is not None:
            keys = artifacts.keys() if hasattr(artifacts, "keys") else ()
            if "terms_review" not in keys:
                artifacts.put("terms_review", review_path)

        warnings = tuple(report.warnings) + tuple(verification.warnings)
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=bool(report.changed),
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "applied": report.applied,
                "reviews": len(reviews),
                "violations": 0,
                "skipped_bibliography": report.skipped_bibliography,
                "glossary_entries": len(glossary),
            },
            warnings=warnings,
            artifacts=(review_path,),
        )


__all__ = [
    "REVIEW_RELATIVE",
    "TermsStage",
    "resolve_glossary",
    "review_path_for",
]
