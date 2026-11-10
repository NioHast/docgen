r"""Audit italic istilah asing pada dokumen DOCX.

Alat ini membaca DOCX hasil build, mengelompokkan kata/frasa Latin, lalu
menulis laporan Markdown untuk ditinjau agent. Alat tidak mengubah DOCX,
glosarium, atau naskah; keputusan tetap di tangan peninjau.

Pemakaian:
    python tools/dev/audit_terms.py --docx Laporan.docx \\
        --glossary src/docgen/data/glossary/istilah.tsv \\
        --out .laporan/istilah-audit.md

Kode keluar:
    0  tidak ada temuan yang perlu diperbaiki/diputuskan
    2  ada ``PERLU DIPERBAIKI`` atau ``PERLU KEPUTUSAN``
    1  kesalahan input (DOCX/glosarium tidak valid)

Modul ini adalah CLI tipis sekaligus pintu re-export API publik. Implementasi
dipecah ke ``audit_terms_model`` (model), ``audit_terms_rules`` (aturan),
``audit_terms_parser`` (ekstraksi DOCX), dan ``audit_terms_report`` (laporan).
"""

import argparse
import sys
from pathlib import Path

from audit_terms_model import (
    CATEGORY_ABBREVIATION,
    CATEGORY_GLOSSARY_ITALIC,
    CATEGORY_GLOSSARY_PLAIN,
    CATEGORY_ITALIC_MISSING,
    CATEGORY_LABEL,
    CATEGORY_MIXED_CASE_NAME,
    CATEGORY_ORDER,
    CATEGORY_PLAIN_BUT_ITALIC,
    CATEGORY_UNKNOWN,
    DECISION_CATEGORIES,
    FIX_CATEGORIES,
    OK_CATEGORIES,
    AuditResult,
    Group,
    Occurrence,
)
from audit_terms_parser import (
    DOCUMENT_PART,
    HEADER_FOOTER_RE,
    audit_docx,
    collect_occurrences,
    iter_audit_paragraphs,
    make_context,
)
from audit_terms_report import render_report
from audit_terms_rules import (
    CONTEXT_WORD_RE,
    ENGLISH_STOPWORDS,
    INDONESIAN_NOISE,
    INDONESIAN_PREFIXES,
    NON_PROSE_RE,
    TOKEN_RE,
    is_abbreviation,
    is_english_stopword,
    is_mixed_case_name,
    looks_indonesian,
    normalize_key,
)

from docgen.docx import DocxError
from docgen.docx.terms import load_glossary

__all__ = [
    "CATEGORY_ABBREVIATION",
    "CATEGORY_GLOSSARY_ITALIC",
    "CATEGORY_GLOSSARY_PLAIN",
    "CATEGORY_ITALIC_MISSING",
    "CATEGORY_LABEL",
    "CATEGORY_MIXED_CASE_NAME",
    "CATEGORY_ORDER",
    "CATEGORY_PLAIN_BUT_ITALIC",
    "CATEGORY_UNKNOWN",
    "CONTEXT_WORD_RE",
    "DECISION_CATEGORIES",
    "DOCUMENT_PART",
    "ENGLISH_STOPWORDS",
    "FIX_CATEGORIES",
    "HEADER_FOOTER_RE",
    "INDONESIAN_NOISE",
    "INDONESIAN_PREFIXES",
    "NON_PROSE_RE",
    "OK_CATEGORIES",
    "TOKEN_RE",
    "AuditResult",
    "Group",
    "Occurrence",
    "audit_docx",
    "collect_occurrences",
    "is_abbreviation",
    "is_english_stopword",
    "is_mixed_case_name",
    "iter_audit_paragraphs",
    "looks_indonesian",
    "main",
    "make_context",
    "normalize_key",
    "render_report",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Audit italic istilah asing pada DOCX dan tulis laporan Markdown.")
    )
    parser.add_argument(
        "--docx",
        type=Path,
        required=True,
        help="file DOCX yang diaudit (mis. Laporan.docx)",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        default=Path("src/docgen/data/glossary/istilah.tsv"),
        help="glosarium TSV (default: src/docgen/data/glossary/istilah.tsv)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".laporan/istilah-audit.md"),
        help="laporan Markdown (default: .laporan/istilah-audit.md)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        glossary = load_glossary(args.glossary)
        result = audit_docx(args.docx, glossary)
        report = render_report(result, args.docx, args.glossary)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(report)

        fix_terms = len(result.needs_fix)
        decision_terms = len(result.needs_decision)
        print(f"Laporan audit: {args.out.as_posix()}")
        print(
            f"Paragraf diperiksa: {result.paragraph_count}; "
            f"perlu diperbaiki: {fix_terms} istilah; "
            f"perlu keputusan: {decision_terms} istilah."
        )
        return 2 if (fix_terms or decision_terms) else 0
    except (DocxError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except AttributeError, OSError:
        pass
    raise SystemExit(main())
