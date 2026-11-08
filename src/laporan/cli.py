"""Antarmuka baris perintah ``python -m laporan``."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys

from . import __version__
from . import manifest as manifest_mod
from . import platform as platform_mod


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="laporan",
        description="Fondasi struktur modular laporan akademik (format, struktur, konten, platform).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="PERINTAH")

    subparsers.add_parser("list", help="Tampilkan struktur dan format yang tersedia.")

    new_parser = subparsers.add_parser(
        "new", help="Buat kerangka proyek konten baru dari sebuah struktur."
    )
    new_parser.add_argument("structure", help="Nama struktur, mis. assignment.")
    new_parser.add_argument(
        "--format",
        dest="format_name",
        help="Nama format, mis. undip-msi. Default mengikuti struktur.",
    )
    new_parser.add_argument("--out", required=True, help="Direktori tujuan proyek konten.")
    new_parser.add_argument("--title", help="Judul laporan pada metadata.yml.")
    new_parser.add_argument("--report-name", help="Nama berkas keluaran, mis. Tugas.")
    new_parser.add_argument(
        "--force", action="store_true", help="Timpa direktori tujuan yang sudah berisi berkas."
    )

    check_parser = subparsers.add_parser(
        "check", help="Validasi manifest, struktur, format, metadata, dan berkas bab."
    )
    check_parser.add_argument("dir", help="Direktori proyek konten.")

    build_parser = subparsers.add_parser(
        "build", help="Bangun dokumen memakai pipeline lama (build-docx.sh/build.sh)."
    )
    build_parser.add_argument("dir", help="Direktori proyek konten.")
    build_parser.add_argument(
        "--target",
        choices=("docx", "pdf", "both"),
        default="docx",
        help="Keluaran yang dibangun (default: docx).",
    )
    build_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tampilkan perintah dan environment tanpa menjalankan build.",
    )

    subparsers.add_parser(
        "doctor", help="Periksa Python, Pandoc, Typst, dan Word/LibreOffice."
    )
    return parser


# ---------------------------------------------------------------------------
# Perintah
# ---------------------------------------------------------------------------


def command_list(_args: argparse.Namespace) -> int:
    structures = manifest_mod.list_structures()
    formats = manifest_mod.list_formats()

    print(f"Struktur ({len(structures)}):")
    if not structures:
        print("  (tidak ada berkas structures/*.yml)")
    for structure in structures:
        toc_label = "ya" if structure.toc else "tidak"
        print(
            f"  {structure.name:<12} format={structure.format:<12} "
            f"bab={len(structure.chapters):<2} toc={toc_label}"
        )

    print()
    print(f"Format ({len(formats)}):")
    if not formats:
        print("  (tidak ada berkas formats/*/format.yml)")
    for format_ in formats:
        print(f"  {format_.name:<12} {format_.display_name}")
    return 0


def command_new(args: argparse.Namespace) -> int:
    structure = manifest_mod.load_structure(args.structure)
    format_name = args.format_name or structure.format
    out, created = manifest_mod.create_project(
        args.structure,
        format_name,
        args.out,
        title=args.title,
        report_name=args.report_name,
        force=args.force,
    )
    print(f"[OK] Proyek konten dibuat di {out}")
    for path in created:
        print(f"     + {path.relative_to(out).as_posix()}")
    print("Langkah berikutnya: edit metadata.yml dan chapters/*.md, lalu jalankan check/build.")
    return 0


def command_check(args: argparse.Namespace) -> int:
    result = manifest_mod.validate_project(args.dir)
    for item in result.passed:
        print(f"[OK] {item}")
    for warning in result.warnings:
        print(f"[PERINGATAN] {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"[ERROR] {error}", file=sys.stderr)

    if result.ok and result.project is not None:
        project = result.project
        print(
            f"[OK] {project.structure.name} + {project.format.name}: "
            f"{len(project.chapter_paths)} bab siap."
        )
        return 0

    print(
        f"[GAGAL] {len(result.errors)} kesalahan, {len(result.warnings)} peringatan.",
        file=sys.stderr,
    )
    return 1


def _toc_enabled(project: manifest_mod.Project) -> bool:
    """Nilai `toc` proyek; metadata menang, struktur menjadi fallback.

    ``new`` menulis nilai struktur ke metadata. Proyek lama yang belum punya
    kunci tersebut tetap mengikuti struktur agar build tidak berubah diam-diam.
    """

    fallback = project.structure.toc
    try:
        metadata = manifest_mod.load_yaml(project.metadata_path)
    except manifest_mod.ManifestError:
        return fallback
    if "toc" not in metadata:
        return fallback
    value = metadata["toc"]
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "on", "1"}


def _build_env(project: manifest_mod.Project) -> dict[str, str]:
    env = dict(os.environ)
    env["LAPORAN_METADATA"] = os.fspath(project.metadata_path)
    env["LAPORAN_CHAPTERS"] = os.fspath(project.chapters_dir)
    env["LAPORAN_REPORT_NAME"] = project.report_name
    # Diteruskan sebagai metadata Pandoc eksplisit oleh build-docx.sh/build.sh
    # agar nilai `toc` sampai ke docx.lua/template.typ tanpa bergantung pada
    # urutan pembacaan metadata file.
    env["LAPORAN_TOC"] = "true" if _toc_enabled(project) else "false"
    env["PYTHONUTF8"] = "1"
    return env


def _ensure_docx_glossary(project: manifest_mod.Project) -> None:
    """Sediakan glosarium di OUTDIR konten.

    ``build-docx.sh`` mencari ``$OUTDIR/writing/istilah.tsv`` tanpa fallback.
    Saat OUTDIR adalah direktori konten, salin glosarium repo sekali bila
    proyek belum memilikinya. Ini penyediaan aset, bukan duplikasi logika
    build.
    """

    target = project.content_dir / "writing" / "istilah.tsv"
    if target.is_file():
        return
    source = manifest_mod.project_root() / "writing" / "istilah.tsv"
    if not source.is_file():
        print(
            f"[PERINGATAN] Glosarium repo tidak ditemukan: {source}; "
            "build-docx.sh akan gagal.",
            file=sys.stderr,
        )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    print(f"[INFO] Glosarium disalin ke {target}")


def _run_build(script_name: str, project: manifest_mod.Project, dry_run: bool) -> int:
    root = manifest_mod.project_root()
    script = root / script_name
    if not script.is_file():
        print(f"[ERROR] Pipeline lama tidak ditemukan: {script}", file=sys.stderr)
        return 1

    bash = platform_mod.find_bash()
    if not bash:
        print(
            "[ERROR] bash tidak ditemukan. Di Windows gunakan Git Bash; "
            "di Debian pasang paket bash.",
            file=sys.stderr,
        )
        return 1

    if script_name == "build-docx.sh" and not dry_run:
        _ensure_docx_glossary(project)

    env = _build_env(project)
    command = [bash, script_name, os.fspath(project.content_dir)]
    print(f"[BUILD] {script_name} untuk {project.content_dir}")
    print(
        "        LAPORAN_METADATA="
        f"{env['LAPORAN_METADATA']} LAPORAN_CHAPTERS={env['LAPORAN_CHAPTERS']} "
        f"LAPORAN_REPORT_NAME={env['LAPORAN_REPORT_NAME']} "
        f"LAPORAN_TOC={env['LAPORAN_TOC']}"
    )
    if dry_run:
        print("        (dry-run) " + " ".join(shlex.quote(part) for part in command))
        return 0

    try:
        completed = subprocess.run(command, cwd=root, env=env, check=False)
    except OSError as exc:
        print(f"[ERROR] Gagal menjalankan {script_name}: {exc}", file=sys.stderr)
        return 1
    if completed.returncode != 0:
        print(f"[ERROR] {script_name} keluar dengan kode {completed.returncode}.", file=sys.stderr)
    else:
        print(f"[OK] {script_name} selesai.")
    return completed.returncode


def command_build(args: argparse.Namespace) -> int:
    result = manifest_mod.validate_project(args.dir)
    if not result.ok or result.project is None:
        for error in result.errors:
            print(f"[ERROR] {error}", file=sys.stderr)
        print("[GAGAL] Perbaiki hasil check sebelum build.", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"[PERINGATAN] {warning}", file=sys.stderr)

    project = result.project
    targets = ("docx", "pdf") if args.target == "both" else (args.target,)
    for target in targets:
        script_name = "build-docx.sh" if target == "docx" else "build.sh"
        code = _run_build(script_name, project, args.dry_run)
        if code != 0:
            return code
    return 0


def _status(ok: bool, label: str, detail: str) -> str:
    marker = "[OK]" if ok else "[--]"
    return f"{marker} {label:<18} {detail}"


def command_doctor(_args: argparse.Namespace) -> int:
    os_name = platform_mod.detect_os()
    bash = platform_mod.find_bash()
    pandoc = platform_mod.find_tool("pandoc")
    typst = platform_mod.find_tool("typst")
    word = platform_mod.find_word()
    libreoffice = platform_mod.find_libreoffice()

    pandoc_version = platform_mod.tool_version(pandoc, "--version")
    typst_version = platform_mod.tool_version(typst, "--version")
    python_ok = sys.version_info >= (3, 9)
    python_detail = f"{platform_mod.python_version()} - {platform_mod.python_executable()}"
    if not python_ok:
        python_detail += " (butuh Python >= 3.9)"

    print(f"OS                 : {os_name}")
    print(_status(python_ok, "Python", python_detail))
    print(_status(bool(bash), "bash", bash or "tidak ditemukan (wajib untuk build)"))
    print(
        _status(
            bool(pandoc),
            "Pandoc",
            f"{pandoc_version} - {pandoc}" if pandoc else "tidak ditemukan (wajib untuk DOCX/PDF)",
        )
    )
    print(
        _status(
            bool(typst),
            "Typst",
            f"{typst_version} - {typst}" if typst else "tidak ditemukan (wajib untuk PDF)",
        )
    )
    if os_name == "windows":
        print(
            _status(
                bool(word),
                "Microsoft Word",
                word or "tidak ditemukan (opsional; finalisasi field TOC)",
            )
        )
    else:
        print(_status(True, "Microsoft Word", "tidak berlaku di luar Windows"))
    print(
        _status(
            bool(libreoffice),
            "LibreOffice",
            libreoffice or "tidak ditemukan (opsional; nomor halaman TOC DOCX)",
        )
    )

    required_ok = bool(python_ok and bash and pandoc)
    print()
    if not required_ok:
        print("Kesimpulan: dependensi wajib belum lengkap; build belum dapat dijalankan.")
        return 1
    print(
        "Kesimpulan: siap untuk DOCX."
        + (" PDF juga siap." if typst else " PDF belum siap (Typst tidak ditemukan).")
    )
    return 0


# ---------------------------------------------------------------------------
# Titik masuk
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "list": command_list,
        "new": command_new,
        "check": command_check,
        "build": command_build,
        "doctor": command_doctor,
    }
    try:
        return handlers[args.command](args)
    except manifest_mod.ManifestError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("[ERROR] Dibatalkan oleh pengguna.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
