#!/usr/bin/env python3
"""Ekspor DOCX final menjadi PDF.

Alur per platform:

- **Windows**: memanggil ``tools/export_pdf.ps1`` yang membuat snapshot DOCX,
  membukanya lewat Microsoft Word COM, memperbarui field dan daftar isi,
  mengekspor PDF dengan ``ExportAsFixedFormat``, lalu menutup Word tanpa
  menyimpan DOCX.
- **Debian/Linux**: memanggil LibreOffice headless
  (``soffice --headless --convert-to pdf``).

PDF selalu diturunkan dari DOCX, bukan dari pipeline Markdown/Typst. Karena
itu glosarium, caption, penomoran, dan nomor halaman mengikuti hasil
``build-docx.sh``.

Usage:
  python tools/export_pdf.py Laporan.docx
  python tools/export_pdf.py Laporan.docx --output Laporan.pdf
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Batas waktu ekspor. 0 berarti tanpa batas.
DEFAULT_TIMEOUT = 300


def detect_platform() -> str:
    """Kembalikan ``windows`` atau ``linux`` (platform non-Windows)."""

    return "windows" if platform.system().lower() == "windows" else "linux"


def find_powershell() -> str | None:
    for name in ("powershell", "pwsh"):
        executable = shutil.which(name)
        if executable:
            return executable
    return None


def find_soffice() -> str | None:
    override = os.environ.get("LAPORAN_SOFFICE")
    if override:
        return override
    for name in ("soffice", "libreoffice"):
        executable = shutil.which(name)
        if executable:
            return executable
    return None


def build_word_command(
    powershell: str, script: Path, docx: Path, pdf: Path
) -> list[str]:
    return [
        powershell,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-DocxPath",
        str(docx),
        "-PdfPath",
        str(pdf),
    ]


def build_libreoffice_command(soffice: str, docx: Path, outdir: Path) -> list[str]:
    return [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(outdir),
        str(docx),
    ]


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """Hentikan proses ekspor beserta anaknya (Word/soffice)."""

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _run(command: list[str], timeout: int, label: str) -> int:
    try:
        process = subprocess.Popen(command)
    except OSError as exc:
        print(
            f"[export_pdf] ERROR: gagal menjalankan {label}: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        return process.wait(timeout=timeout if timeout > 0 else None)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        print(
            f"[export_pdf] ERROR: {label} tidak selesai dalam {timeout} detik.",
            file=sys.stderr,
        )
        return 1


def export_with_word(docx: Path, pdf: Path, timeout: int) -> int:
    powershell = find_powershell()
    if powershell is None:
        print(
            "[export_pdf] ERROR: PowerShell tidak ditemukan. Ekspor PDF di "
            "Windows membutuhkan PowerShell dan Microsoft Word desktop.",
            file=sys.stderr,
        )
        return 1

    script = Path(__file__).resolve().with_name("export_pdf.ps1")
    if not script.is_file():
        print(
            f"[export_pdf] ERROR: {script.name} tidak ditemukan di {script.parent}.",
            file=sys.stderr,
        )
        return 1

    command = build_word_command(powershell, script, docx, pdf)
    return _run(command, timeout, "Microsoft Word")


def export_with_libreoffice(docx: Path, pdf: Path, timeout: int) -> int:
    soffice = find_soffice()
    if soffice is None:
        print(
            "[export_pdf] ERROR: LibreOffice (soffice) tidak ditemukan. "
            "Instal dengan: sudo apt install libreoffice-writer",
            file=sys.stderr,
        )
        return 1

    outdir = pdf.parent
    outdir.mkdir(parents=True, exist_ok=True)
    expected = outdir / f"{docx.stem}.pdf"

    # Hindari keluaran basi dan konversi yang gagal menimpa nama lain.
    for stale in {pdf, expected}:
        try:
            stale.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(
                f"[export_pdf] ERROR: gagal menghapus PDF lama {stale}: {exc}",
                file=sys.stderr,
            )
            return 1

    command = build_libreoffice_command(soffice, docx, outdir)
    returncode = _run(command, timeout, "LibreOffice")
    if returncode != 0:
        return returncode

    if not expected.is_file():
        print(
            f"[export_pdf] ERROR: LibreOffice selesai tanpa error tetapi PDF "
            f"tidak terbentuk: {expected}",
            file=sys.stderr,
        )
        return 1

    if expected != pdf:
        try:
            expected.replace(pdf)
        except OSError as exc:
            print(
                f"[export_pdf] ERROR: gagal memindahkan {expected} ke {pdf}: {exc}",
                file=sys.stderr,
            )
            return 1

    if not pdf.is_file():
        print(
            f"[export_pdf] ERROR: PDF tidak terbentuk: {pdf}",
            file=sys.stderr,
        )
        return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ekspor DOCX final menjadi PDF memakai Word COM (Windows) atau "
            "LibreOffice headless (Debian/Linux)."
        )
    )
    parser.add_argument("docx", help="Path ke DOCX sumber.")
    parser.add_argument(
        "-o",
        "--output",
        help="Path PDF tujuan. Default: nama DOCX dengan ekstensi .pdf.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Batas waktu ekspor dalam detik (0 = tanpa batas).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    docx = Path(args.docx).resolve()
    if not docx.is_file():
        print(
            f"[export_pdf] ERROR: DOCX tidak ditemukan: {docx}",
            file=sys.stderr,
        )
        return 1

    pdf = Path(args.output).resolve() if args.output else docx.with_suffix(".pdf")
    if pdf.suffix.lower() != ".pdf":
        print(
            f"[export_pdf] ERROR: path tujuan harus berekstensi .pdf: {pdf}",
            file=sys.stderr,
        )
        return 1
    if pdf == docx:
        print(
            "[export_pdf] ERROR: path DOCX dan PDF tidak boleh sama.",
            file=sys.stderr,
        )
        return 1

    os_name = detect_platform()
    print(f"[export_pdf] Platform: {os_name}")
    print(f"[export_pdf] DOCX: {docx}")
    print(f"[export_pdf] PDF : {pdf}")

    if os_name == "windows":
        returncode = export_with_word(docx, pdf, args.timeout)
    else:
        returncode = export_with_libreoffice(docx, pdf, args.timeout)

    if returncode != 0:
        print(
            f"[export_pdf] ERROR: ekspor PDF gagal (kode {returncode}).",
            file=sys.stderr,
        )
        return returncode if returncode > 0 else 1

    if not pdf.is_file():
        print(
            f"[export_pdf] ERROR: ekspor selesai tetapi PDF tidak ditemukan: {pdf}",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] PDF diekspor: {pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
