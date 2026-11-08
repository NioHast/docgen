#!/usr/bin/env python3
"""Finalisasi tahap field Word untuk Laporan.docx.

Urutan kerja:

  1. Hanya di Windows: bila PowerShell dan Microsoft Word tersedia, jalankan
     ``tools/update_fields.ps1`` supaya seluruh field (TOC/PAGEREF/PAGE)
     memakai hasil perhitungan Word.
  2. Selalu jalankan ``scripts/finalize-docx.py --in-place`` untuk
     menghapus ``w:updateFields`` (agar Word tidak menampilkan prompt
     "Do you want to update the fields?"), memaksa
     ``compatibilityMode`` 15, dan merapikan hyperlink/font kode serta
     struktur section yang dinormalkan Word.

Di Linux (termasuk WSL) Word tidak tersedia: langkah 1 dilewati dengan
warning, dan hanya settings DOCX yang dibersihkan. TOC tetap memakai cache
terakhir. Finalisasi field Word dilakukan belakangan di Windows.

Hook di ``build-docx.sh`` dijalankan setelah ``docx-pagenum.py`` dan
sebelum ``add_paragraph_ids.py`` agar manifest mencerminkan DOCX final:

    "$PYTHON_BIN" "$TMPDIR/tools/word_finalize.py" "$REPORT"

Usage:
  python tools/word_finalize.py Laporan.docx
  python tools/word_finalize.py --skip-word Laporan.docx
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def warn(message: str) -> None:
    print(f"[word_finalize] WARNING: {message}", file=sys.stderr)


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def find_powershell() -> str | None:
    for name in ("powershell", "pwsh"):
        executable = shutil.which(name)
        if executable:
            return executable
    return None


def find_finalize_script() -> Path | None:
    candidate = Path(__file__).resolve().parent.parent / "scripts" / "finalize-docx.py"
    if candidate.is_file():
        return candidate
    fallback = Path(__file__).resolve().parent / "finalize-docx.py"
    if fallback.is_file():
        return fallback
    return None


def update_fields_with_word(docx: Path, timeout: int) -> bool:
    """Jalankan update_fields.ps1; False bila Word/PowerShell tidak siap."""
    if not is_windows():
        warn(
            "Microsoft Word hanya tersedia di Windows; field DOCX tidak "
            "diperbarui. TOC memakai cache terakhir."
        )
        return False

    powershell = find_powershell()
    if powershell is None:
        warn(
            "powershell tidak ditemukan; field DOCX tidak diperbarui. "
            "TOC memakai cache terakhir."
        )
        return False

    script = Path(__file__).resolve().with_name("update_fields.ps1")
    if not script.is_file():
        warn(
            f"{script.name} tidak ditemukan; field DOCX tidak diperbarui. "
            "TOC memakai cache terakhir."
        )
        return False

    command = [
        powershell,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-DocxPath",
        str(docx),
    ]
    try:
        result = subprocess.run(
            command,
            timeout=timeout if timeout > 0 else None,
            check=False,
        )
    except subprocess.TimeoutExpired:
        warn(
            f"Word tidak selesai dalam {timeout} detik; field DOCX tidak "
            "diperbarui. TOC memakai cache terakhir."
        )
        return False
    except OSError as exc:
        warn(
            f"gagal menjalankan PowerShell/Word ({exc}); field DOCX tidak "
            "diperbarui. TOC memakai cache terakhir."
        )
        return False

    if result.returncode != 0:
        warn(
            "Microsoft Word tidak tersedia atau gagal membuka dokumen. "
            "Field DOCX tidak diperbarui; TOC memakai cache terakhir."
        )
        return False
    return True


def clear_update_fields(docx: Path) -> bool:
    """Finalisasi penuh in-place: settings, style, dan struktur section."""
    finalize_script = find_finalize_script()
    if finalize_script is None:
        raise FileNotFoundError(
            "scripts/finalize-docx.py tidak ditemukan; tidak dapat "
            "menghapus w:updateFields."
        )
    result = subprocess.run(
        [
            sys.executable,
            str(finalize_script),
            "--in-place",
            str(docx),
        ],
        check=False,
    )
    return result.returncode == 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Di Windows, perbarui field DOCX lewat Word (opsional); di Linux "
            "lewati Word. Selalu bersihkan updateFields dan compatibility mode."
        )
    )
    parser.add_argument("docx", help="Path ke Laporan.docx")
    parser.add_argument(
        "--skip-word",
        action="store_true",
        help="Jangan buka Word; langsung bersihkan settings.xml.",
    )
    parser.add_argument(
        "--word-timeout",
        type=int,
        default=300,
        help="Batas waktu Word COM dalam detik (0 = tanpa batas).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    docx = Path(args.docx)
    if not docx.is_file():
        print(
            f"[word_finalize] ERROR: DOCX tidak ditemukan: {docx}",
            file=sys.stderr,
        )
        return 1

    if not is_windows():
        warn(
            "Word tidak tersedia di platform ini; field DOCX tidak diperbarui. "
            "TOC memakai cache terakhir. Finalisasi field Word dilakukan di Windows."
        )
    elif args.skip_word:
        warn(
            "Word dilewati (--skip-word); field DOCX tidak diperbarui. "
            "TOC memakai cache terakhir."
        )
    else:
        update_fields_with_word(docx, args.word_timeout)

    try:
        if not clear_update_fields(docx):
            print(
                "[word_finalize] ERROR: gagal membersihkan settings.xml "
                "(updateFields/compatibilityMode).",
                file=sys.stderr,
            )
            return 1
    except (OSError, FileNotFoundError) as exc:
        print(f"[word_finalize] ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"[OK] word_finalize: settings bersih (tanpa updateFields) -> {docx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
