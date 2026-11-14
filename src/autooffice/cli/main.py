"""Titik masuk CLI ``autooffice``."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from autooffice import __version__
from autooffice.docx.errors import DocgenError
from autooffice.errors import AutoOfficeError

from . import CliError
from .build import BuildOutcome, build_deck, build_markdown, require_google_extra
from .check import CheckResult, check_deck, check_markdown
from .doctor import doctor_report, render_doctor
from .outputs import resolve_output_directory
from .targets import (
    InputKind,
    default_check_targets,
    detect_input_kind,
    parse_doctor_targets,
    parse_targets,
)

DESCRIPTION = "Pipeline dokumen dan deck AutoOffice dari Markdown atau YAML."

_THEMES = ("indigo", "hitam")
_SYNC_MODES = ("push", "pull", "diff", "apply")


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser dengan satu permukaan perintah AutoOffice v1."""
    parser = argparse.ArgumentParser(prog="autooffice", description=DESCRIPTION)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="PERINTAH")

    build_parser_ = subparsers.add_parser(
        "build",
        help="Bangun DOCX/PDF dari Markdown atau PPTX/PDF/Slides dari YAML.",
    )
    build_parser_.add_argument("input", type=Path, help="Berkas .md atau .yaml.")
    build_parser_.add_argument(
        "--target",
        help="Target dipisah koma: docx,pdf (md) atau pptx,pdf,slides (yaml), atau all.",
    )
    build_parser_.add_argument("--out", type=Path, help="Direktori output final.")
    build_parser_.add_argument(
        "--theme",
        help="Theme deck: indigo atau hitam (hanya .yaml).",
    )
    build_parser_.add_argument(
        "--terms",
        action="store_true",
        help="Aktifkan gate istilah (hanya .md).",
    )
    build_parser_.add_argument(
        "--dry-run",
        action="store_true",
        help="Validasi dan cetak rencana tanpa menulis output atau memanggil COM/Google.",
    )
    build_parser_.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="Pertahankan intermediate DOCX/PPTX/staging di lokasi terdokumentasi.",
    )
    build_parser_.add_argument(
        "--sync",
        help="Mode Google Slides: push (default), pull, diff, atau apply (hanya target slides).",
    )

    check_parser = subparsers.add_parser(
        "check",
        help="Validasi Markdown/DOCX atau deck tanpa menulis output.",
    )
    check_parser.add_argument("input", type=Path, help="Berkas .md atau .yaml.")
    check_parser.add_argument(
        "--target",
        help="Target opsional; bawaannya semua target valid untuk input.",
    )
    check_parser.add_argument(
        "--theme",
        help="Theme deck: indigo atau hitam (hanya .yaml).",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Periksa Python, Pandoc, mmdc, COM Office, dan font tanpa jaringan.",
    )
    doctor_parser.add_argument(
        "--target",
        help="Target opsional: docx,pptx,pdf,slides,all.",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Cetak hasil sebagai JSON deterministik.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Jalankan CLI dan kembalikan kode keluar kontrak (0/1/2)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        if args.command == "build":
            return _run_build(args)
        if args.command == "check":
            return _run_check(args)
        if args.command == "doctor":
            return _run_doctor(args)
        raise CliError(
            f"perintah tidak dikenal: {args.command}",
            code="CLI-COMMAND",
            exit_code=2,
        )
    except CliError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return exc.exit_code
    except DocgenError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return exc.exit_code
    except AutoOfficeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("[ERROR] Dibatalkan oleh pengguna.", file=sys.stderr)
        return 130


def _run_build(args: argparse.Namespace) -> int:
    source = _require_input(cast("Path", args.input))
    kind = detect_input_kind(source)
    theme = cast("str | None", args.theme)
    sync = cast("str | None", args.sync)
    terms = bool(args.terms)
    dry_run = bool(args.dry_run)
    keep_intermediate = bool(args.keep_intermediate)
    out = cast("Path | None", args.out)

    _validate_theme(theme, kind)
    _validate_sync(sync, kind)
    if terms and kind is not InputKind.MARKDOWN:
        raise CliError(
            "--terms hanya valid untuk input .md",
            code="CLI-TERMS-TARGET",
            exit_code=2,
        )
    if out is not None:
        resolve_output_directory(source, out)
    targets = parse_targets(cast("str | None", args.target), kind, required=True)
    if sync is not None and "slides" not in targets:
        raise CliError(
            "--sync hanya valid bila target berisi slides",
            code="CLI-SYNC-TARGET",
            exit_code=2,
        )
    if "slides" in targets:
        require_google_extra()

    outcome = (
        build_markdown(
            source,
            targets,
            out,
            terms,
            keep_intermediate,
            dry_run,
        )
        if kind is InputKind.MARKDOWN
        else build_deck(
            source,
            targets,
            out,
            theme,
            dry_run,
            keep_intermediate,
            sync,
        )
    )
    _print_outcome(outcome)
    return 0


def _run_check(args: argparse.Namespace) -> int:
    source = _require_input(cast("Path", args.input))
    kind = detect_input_kind(source)
    theme = cast("str | None", args.theme)
    _validate_theme(theme, kind)
    raw_target = cast("str | None", args.target)
    targets = (
        default_check_targets(kind)
        if raw_target is None
        else parse_targets(raw_target, kind, required=False)
    )
    result = (
        check_markdown(source, targets)
        if kind is InputKind.MARKDOWN
        else check_deck(source, targets, theme)
    )
    return _print_check(result)


def _run_doctor(args: argparse.Namespace) -> int:
    targets = parse_doctor_targets(cast("str | None", args.target))
    report = doctor_report(targets)
    return render_doctor(report, json_output=bool(args.json_output))


def _print_outcome(outcome: BuildOutcome) -> None:
    for warning in outcome.warnings:
        print(f"[PERINGATAN] {warning}", file=sys.stderr)
    if outcome.dry_run:
        print(f"[RENCANA] input: {outcome.source}")
        print(f"[RENCANA] target: {', '.join(outcome.targets)}")
        for path in outcome.files:
            print(f"[RENCANA] tulis: {path}")
        for note in outcome.notes:
            print(f"[RENCANA] {note}")
        return
    for path in outcome.files:
        print(f"[OK] Keluaran: {path}")
    for note in outcome.notes:
        print(f"[INFO] {note}")


def _print_check(result: CheckResult) -> int:
    for note in result.notes:
        print(f"[INFO] {note}", file=sys.stderr)
    for finding in result.findings:
        marker = "[ERROR]" if finding.severity == "error" else "[PERINGATAN]"
        print(f"{marker} {finding.format()}", file=sys.stderr)
    if result.ok:
        print(f"[OK] check {result.source}: bersih")
        return 0
    print(
        f"[ERROR] {len(result.findings)} temuan ({result.error_count} error) pada {result.source}",
        file=sys.stderr,
    )
    return 1


def _require_input(path: Path) -> Path:
    source = path.expanduser()
    if not source.exists():
        raise CliError(
            f"input tidak ditemukan: {source}",
            code="CLI-INPUT-MISSING",
            exit_code=2,
            path=str(source),
        )
    if not source.is_file():
        raise CliError(
            f"input harus berupa berkas, bukan direktori: {source}",
            code="CLI-INPUT-TYPE",
            exit_code=2,
            path=str(source),
        )
    return source


def _validate_theme(theme: str | None, kind: InputKind) -> None:
    if theme is None:
        return
    if kind is not InputKind.DECK:
        raise CliError(
            "--theme hanya valid untuk input .yaml",
            code="CLI-THEME-TARGET",
            exit_code=2,
        )
    if theme not in _THEMES:
        raise CliError(
            f"theme tidak valid: {theme}; pilihan: {', '.join(_THEMES)}",
            code="CLI-THEME",
            exit_code=2,
        )


def _validate_sync(sync: str | None, kind: InputKind) -> None:
    if sync is None:
        return
    if kind is not InputKind.DECK:
        raise CliError(
            "--sync hanya valid untuk input .yaml dengan target slides",
            code="CLI-SYNC-TARGET",
            exit_code=2,
        )
    if sync not in _SYNC_MODES:
        raise CliError(
            f"mode sync tidak valid: {sync}; pilihan: {', '.join(_SYNC_MODES)}",
            code="CLI-SYNC-MODE",
            exit_code=2,
        )


if __name__ == "__main__":
    raise SystemExit(main())
