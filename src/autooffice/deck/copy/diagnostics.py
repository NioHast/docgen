"""Model diagnostic dan temuan rule copy checker.

Diagnostic adalah keluaran publik checker. Setiap diagnostic wajib memuat
rule, severity, key, file bila tersedia, line bila tersedia, message, dan hint.
Rule internal memakai ``RuleViolation`` yang lebih kecil; checker menaikkannya
menjadi ``Diagnostic`` dengan severity dan lokasi dari konfigurasi.
"""

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Satu temuan copy checker yang siap ditampilkan CLI atau build gate."""

    rule: str
    severity: Severity
    key: str
    message: str
    hint: str
    file: str | None = None
    line: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Bentuk mapping deterministik sesuai urutan kontrak copy."""
        return {
            "rule": self.rule,
            "severity": self.severity,
            "key": self.key,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "hint": self.hint,
        }

    def format(self) -> str:
        """Format satu baris untuk keluaran manusia."""
        location = self.file or "<deck>"
        if self.line is not None:
            location = f"{location}:{self.line}"
        return (
            f"{location}: {self.severity}: {self.key} [{self.rule}] "
            f"{self.message} Hint: {self.hint}"
        )


@dataclass(frozen=True, slots=True)
class RuleViolation:
    """Temuan satu rule sebelum diberi severity dan lokasi."""

    message: str
    hint: str
    offset: int = 0
