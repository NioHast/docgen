"""Antarmuka baris perintah AutoOffice.

Modul ini menyimpan error CLI bersama. Perintah memuat modul domain langsung
di dalam fungsi yang membutuhkannya agar ``autooffice --help`` dan
``autooffice --version`` tetap ringan.
"""

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


__all__ = ["CliError"]
