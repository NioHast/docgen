"""Antarmuka baris perintah ``docgen``."""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .adeu.cli import command_reconcile, register_reconcile
from .document import load_project
from .errors import DocgenError
from .pipeline import BuildOptions, Pipeline
from .stages.validate import validate_body


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docgen",
        description="Generator dokumen akademik dari satu berkas document.md.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="PERINTAH")

    check_parser = subparsers.add_parser(
        "check",
        help="Validasi front matter, format, struktur, template, aset, dan body.",
    )
    check_parser.add_argument("document", help="Berkas document.md.")

    build_parser_ = subparsers.add_parser(
        "build",
        help="Bangun DOCX/PDF lewat pipeline Python.",
    )
    build_parser_.add_argument("document", help="Berkas document.md.")
    build_parser_.add_argument(
        "--target",
        choices=("docx", "pdf", "both"),
        default="both",
        help="Keluaran yang dibangun (default: both).",
    )
    build_parser_.add_argument(
        "--keep",
        action="store_true",
        help="Pertahankan .laporan-build dan intermediate DOCX.",
    )
    build_parser_.add_argument(
        "--terms",
        action="store_true",
        help="Aktifkan check/apply/verify/gate istilah.",
    )
    build_parser_.add_argument(
        "--no-manifest",
        action="store_true",
        help="Matikan manifest dan source scan.",
    )
    build_parser_.add_argument(
        "--no-adeu",
        action="store_true",
        help="Matikan bookmark, manifest, dan source scan.",
    )
    build_parser_.add_argument(
        "--allow-missing-word",
        action="store_true",
        help="Izinkan PDF dilewati jika Microsoft Word tidak tersedia.",
    )

    subparsers.add_parser(
        "doctor",
        help="Periksa Python, Pandoc, Word, dan mmdc.",
    )
    register_reconcile(subparsers)
    return parser


# ---------------------------------------------------------------------------
# Perintah
# ---------------------------------------------------------------------------


def command_check(args: argparse.Namespace) -> int:
    project = load_project(args.document)
    for warning in project.warnings:
        print(f"[PERINGATAN] {warning}", file=sys.stderr)
    document = project.document
    validate_body(document)
    print(f"[OK] {document.metadata.title}")
    print(
        f"     format={project.format.id} struktur={project.structure.id} "
        f"author={len(document.metadata.authors)} bab={len(project.structure.body)}"
    )
    if project.assets.bibliography is not None:
        print(f"     bibliografi={project.assets.bibliography}")
    if project.assets.images:
        print(f"     gambar={len(project.assets.images)}")
    print(f"     glosarium={project.assets.glossary}")
    return 0


def command_build(args: argparse.Namespace) -> int:
    options = BuildOptions(
        target=args.target,
        keep=args.keep,
        terms=args.terms,
        manifest=not args.no_manifest and not args.no_adeu,
        adeu=not args.no_adeu,
        allow_missing_word=args.allow_missing_word,
    )
    pipeline = Pipeline()
    result = pipeline.run(args.document, options)
    for warning in result.warnings:
        print(f"[PERINGATAN] {warning}", file=sys.stderr)
    for path in (result.docx, result.pdf):
        if path is not None:
            print(f"[OK] Keluaran: {path}")
    if result.manifest is not None:
        print(f"[OK] Manifest: {result.manifest}")
    if result.kept_workspace is not None:
        print(f"[INFO] Workspace dipertahankan: {result.kept_workspace}")
    return 0


def _find_tool(name: str) -> str | None:
    if sys.platform == "win32":
        candidates: list[Path] = []
        local = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("PROGRAMFILES")
        if name == "pandoc":
            if local:
                candidates.append(Path(local) / "Pandoc" / "pandoc.exe")
            if program_files:
                candidates.append(Path(program_files) / "Pandoc" / "pandoc.exe")
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return shutil.which(f"{name}.exe") or shutil.which(name)
    return shutil.which(name)


def _find_word() -> str | None:
    from .pipeline import _find_word as find_word

    return find_word()


def _tool_version(command: str | None) -> str | None:
    if command is None:
        return None
    try:
        completed = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    output = (completed.stdout or completed.stderr or "").strip().splitlines()
    return output[0] if output else None


def _status(ok: bool, label: str, detail: str) -> str:
    marker = "[OK]" if ok else "[--]"
    return f"{marker} {label:<18} {detail}"


def command_doctor(_args: argparse.Namespace) -> int:
    python_ok = sys.version_info >= (3, 15)
    python_detail = platform.python_version()
    pandoc = _find_tool("pandoc")
    word = _find_word()
    mmdc = _find_tool("mmdc")

    print(f"OS                 : {sys.platform}")
    print(
        _status(
            python_ok,
            "Python",
            f"{python_detail} (butuh >=3.15)" if not python_ok else python_detail,
        )
    )
    pandoc_version = _tool_version(pandoc)
    print(
        _status(
            bool(pandoc),
            "Pandoc",
            f"{pandoc_version} - {pandoc}"
            if pandoc and pandoc_version
            else (pandoc or "tidak ditemukan (wajib untuk DOCX)"),
        )
    )
    if sys.platform == "win32":
        print(
            _status(
                bool(word),
                "Microsoft Word",
                word or "tidak ditemukan (PDF tidak tersedia)",
            )
        )
    else:
        print(_status(True, "Microsoft Word", "tidak berlaku (PDF hanya Windows)"))
    print(
        _status(
            bool(mmdc),
            "mmdc",
            mmdc or "tidak ditemukan (hanya diperlukan untuk blok Mermaid)",
        )
    )

    if not python_ok or not pandoc:
        print()
        print("Kesimpulan: dependensi wajib belum lengkap; build DOCX belum siap.")
        return 1
    print()
    print("Kesimpulan: siap untuk DOCX." + ("" if word else " PDF belum siap."))
    return 0


# ---------------------------------------------------------------------------
# Titik masuk
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "check": command_check,
        "build": command_build,
        "doctor": command_doctor,
        "reconcile": command_reconcile,
    }
    try:
        return handlers[args.command](args)
    except DocgenError as exc:
        print(f"[ERROR] {exc.format()}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("[ERROR] Dibatalkan oleh pengguna.", file=sys.stderr)
        return 130
