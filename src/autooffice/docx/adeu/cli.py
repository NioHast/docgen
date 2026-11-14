"""Titik masuk CLI fitur Adeu.

``register_reconcile`` mendaftarkan subperintah ``reconcile`` pada parser
``autooffice`` yang diberikan. Pemanggil di ``autooffice.cli`` cukup:

```python
from .adeu.cli import register_reconcile

register_reconcile(subparsers)
```

dan memetakan ``args.command == "reconcile"`` ke ``command_reconcile``.
"""

import argparse
import sys
from collections.abc import Sequence

from ..errors import DocgenError
from . import reconcile


def register_reconcile(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    """Daftarkan subperintah ``reconcile`` ke parser ``autooffice``."""

    parser: argparse.ArgumentParser = subparsers.add_parser(
        "reconcile",
        help="Rekonsiliasi edit manual DOCX dengan manifest Adeu.",
        description=(
            "Bandingkan DOCX hasil edit dengan manifest Adeu dan document.md, "
            "lalu tulis laporan tinjauan. Tidak mengubah DOCX/manifest/Markdown."
        ),
    )
    reconcile.configure_parser(parser)
    return parser


def command_reconcile(args: argparse.Namespace) -> int:
    """Handler untuk subperintah ``autooffice reconcile``."""

    return reconcile.command(args)


def build_parser(prog: str = "autooffice") -> argparse.ArgumentParser:
    """Parser mandiri ``python -m autooffice.docx.adeu.cli``."""

    parser = argparse.ArgumentParser(
        prog=prog,
        description="Perintah fitur Adeu.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_reconcile(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"reconcile": command_reconcile}
    try:
        return handlers[args.command](args)
    except DocgenError as exc:
        print(f"[ERROR] {exc.format()}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("[ERROR] Dibatalkan oleh pengguna.", file=sys.stderr)
        return 130


__all__ = [
    "build_parser",
    "command_reconcile",
    "main",
    "register_reconcile",
]


if __name__ == "__main__":  # pragma: no cover - titik masuk manual
    raise SystemExit(main())
