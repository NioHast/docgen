"""Titik masuk CLI ``autooffice``."""

import argparse
from collections.abc import Sequence

from autooffice import __version__

DESCRIPTION = "Pipeline dokumen dan deck AutoOffice dari YAML."


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser CLI minimal untuk scaffold F0."""
    parser = argparse.ArgumentParser(prog="autooffice", description=DESCRIPTION)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Jalankan CLI scaffold dan kembalikan kode keluar."""
    parser = build_parser()
    parser.parse_args(argv)
    return 0
