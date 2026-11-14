"""Antarmuka baris perintah AutoOffice.

Modul ini menyimpan error CLI bersama dan helper import lazy. Modul domain
hanya diimpor saat perintah yang membutuhkannya benar-benar dijalankan agar
``autooffice --help`` dan ``autooffice --version`` tetap ringan.
"""

import importlib
from typing import Any

from autooffice.errors import AutoOfficeError


class CliError(AutoOfficeError):
    """Kesalahan CLI yang dapat ditampilkan tanpa traceback.

    ``exit_code`` mengikuti kontrak CLI: 1 untuk kegagalan validasi, build,
    dependency, atau temuan; 2 untuk argumen, target, dan kombinasi flag yang
    salah.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "CLI",
        exit_code: int = 2,
        path: str | None = None,
        cleanup_ambiguous: bool = False,
    ) -> None:
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.path = path
        self.cleanup_ambiguous = cleanup_ambiguous
        super().__init__(self.format())

    def format(self) -> str:
        """Format pesan CLI yang deterministik."""
        prefix = f"{self.path}: " if self.path else ""
        return f"{prefix}{self.message} ({self.code})"

    def __str__(self) -> str:
        return self.format()


def require_module(name: str, lane: str) -> Any:
    """Impor modul domain secara lazy atau lempar :class:`CliError`.

    ``lane`` adalah nama lane plan, misalnya ``F1-PPTX``. Pesan error harus
    menyebut lane tersebut agar pengguna tahu bagian mana yang belum selesai,
    bukan menerima output palsu.
    """
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise CliError(
            f"modul '{name}' untuk lane {lane} belum tersedia: {exc}",
            code=f"CLI-LANE-{lane}",
            exit_code=1,
        ) from exc


def require_callable(module: object, name: str, lane: str) -> Any:
    """Ambil atribut callable dari modul lazy atau lempar :class:`CliError`."""
    value = getattr(module, name, None)
    if not callable(value):
        raise CliError(
            f"API '{name}' untuk lane {lane} belum tersedia",
            code=f"CLI-LANE-{lane}",
            exit_code=1,
        )
    return value


__all__ = ["CliError", "require_callable", "require_module"]
