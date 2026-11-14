#!/usr/bin/env python3
"""Daftar target legacy yang tidak boleh dipakai AutoOffice.

Skrip ini belum dijalankan di gate. F0 hanya membekukan daftar target agar
lane berikutnya memiliki rujukan yang sama saat migrasi selesai.
"""

import argparse
from collections.abc import Sequence

NO_LEGACY_PATHS: tuple[str, ...] = (
    "src/docgen",
    "src/autooffice/legacy",
    "package.json",
    "node_modules",
    "PptxGenJS",
    "Reveal",
)


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser untuk daftar target no-legacy."""
    parser = argparse.ArgumentParser(
        prog="check_no_legacy",
        description="Daftar path dan teknologi legacy yang tidak boleh dipakai AutoOffice.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Cetak seluruh target no-legacy.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Jalankan skrip dan kembalikan kode keluar."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.list:
        parser.print_help()
        return 0
    for target in NO_LEGACY_PATHS:
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
