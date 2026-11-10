"""Resolusi path paket dan path relatif yang aman.

API masuk mencakup :func:`data_root`, :func:`format_dir`,
:func:`structure_dir`, :func:`glossary_file`, dan :func:`safe_relative_path`.
Semua data bawaan dibaca dari ``src/docgen/data`` di dalam paket. Tidak ada
fallback ke akar repositori atau direktori kerja: bila data paket hilang,
``docgen`` gagal dengan ``ConfigError``/``AssetError`` yang jelas.

Modul ini tidak menulis berkas dan tidak membuat direktori.
"""

import re
from pathlib import Path, PurePosixPath

from .errors import AssetError, ConfigError

PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_DIRNAME = "data"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def package_root() -> Path:
    """Direktori paket ``docgen``."""

    return PACKAGE_ROOT


def output_directory(document_path: Path) -> Path:
    """Direktori keluaran build untuk sebuah dokumen.

    Dokumen contoh di ``examples/<nama>/document.md`` ditulis ke
    ``examples/<nama>/out`` agar berkas sumber tetap bersih. Dokumen pengguna
    lain ditulis di folder yang sama dengan dokumen. Aturan ini dipakai
    bersama oleh pipeline build dan reconcile; tidak ada fallback ke direktori
    kerja saat ini atau lokasi tebakan lain.
    """

    parent = document_path.parent
    if parent.parent.name == "examples":
        return parent / "out"
    return parent


def data_root() -> Path:
    """Direktori data paket, tanpa fallback ke cwd/root repo."""

    root = PACKAGE_ROOT / DATA_DIRNAME
    if not root.is_dir():
        raise ConfigError(
            f"direktori data paket tidak ditemukan: {root}",
            code="CFG-DATA-MISSING",
            path=root,
        )
    return root


def formats_root(*, root: Path | None = None) -> Path:
    """Direktori ``formats``; melempar ``ConfigError`` bila tidak ada."""

    base = (root or data_root()) / "formats"
    if not base.is_dir():
        raise ConfigError(
            f"direktori format tidak ditemukan: {base}",
            code="CFG-DATA-MISSING",
            path=base,
        )
    return base


def structures_root(*, root: Path | None = None) -> Path:
    """Direktori ``structures``; melempar ``ConfigError`` bila tidak ada."""

    base = (root or data_root()) / "structures"
    if not base.is_dir():
        raise ConfigError(
            f"direktori struktur tidak ditemukan: {base}",
            code="CFG-DATA-MISSING",
            path=base,
        )
    return base


def format_dir(format_id: str, *, root: Path | None = None) -> Path:
    """Direktori satu format; validasi ID dan keberadaannya."""

    validate_id(format_id, kind="format")
    path = formats_root(root=root) / format_id
    if not path.is_dir():
        raise ConfigError(
            f"format '{format_id}' tidak ditemukan",
            code="CFG-FORMAT-MISSING",
            path=path,
        )
    return path


def structure_dir(structure_id: str, *, root: Path | None = None) -> Path:
    """Direktori satu struktur; validasi ID dan keberadaannya."""

    validate_id(structure_id, kind="struktur")
    path = structures_root(root=root) / structure_id
    if not path.is_dir():
        raise ConfigError(
            f"struktur '{structure_id}' tidak ditemukan",
            code="CFG-STRUCTURE-MISSING",
            path=path,
        )
    return path


def templates_dir(structure_id: str, *, root: Path | None = None) -> Path:
    """Direktori template milik satu struktur."""

    return structure_dir(structure_id, root=root) / "templates"


def glossary_file(*, root: Path | None = None) -> Path:
    """Path glosarium paket; melempar ``AssetError`` bila berkas tidak ada."""

    path = (root or data_root()) / "glossary" / "istilah.tsv"
    if not path.is_file():
        raise AssetError(
            f"glosarium paket tidak ditemukan: {path}",
            code="CFG-ASSET-MISSING",
            path=path,
        )
    return path


def validate_id(value: str, *, kind: str) -> str:
    """Trim dan validasi ID format/struktur dengan pola ``[a-z0-9][a-z0-9-]*``."""

    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"ID {kind} wajib diisi",
            code="CFG-REQUIRED",
            key=kind,
        )
    text = value.strip()
    if not _ID_RE.fullmatch(text):
        raise ConfigError(
            f"ID {kind} '{text}' tidak valid; gunakan pola [a-z0-9][a-z0-9-]*",
            code="CFG-TYPE",
            key=kind,
        )
    return text


def safe_relative_path(
    raw: object,
    *,
    base: Path,
    label: str,
    code: str = "CFG-PATH",
    must_exist: bool = False,
    expect_file: bool = False,
    expect_dir: bool = False,
) -> Path:
    """Resolve ``raw`` relatif terhadap ``base`` dan tolak escape.

    Kontrak mewajibkan path relatif dengan pemisah ``/``. Path absolut,
    backslash, segmen ``..``, dan skema URL ditolak sebelum disentuh.
    ``must_exist``, ``expect_file``, dan ``expect_dir`` menambahkan pemeriksaan
    keberadaan. Semua pelanggaran melempar ``ConfigError`` dengan ``key``
    berisi ``label``; tidak ada berkas yang dibuat.
    """

    if not isinstance(raw, str):
        raise ConfigError(
            f"{label} harus berupa teks path relatif",
            code="CFG-TYPE",
            key=label,
        )
    text = raw.strip()
    if not text:
        raise ConfigError(
            f"{label} tidak boleh kosong",
            code="CFG-REQUIRED",
            key=label,
        )
    if "\\" in text:
        raise ConfigError(
            f"{label} harus memakai pemisah '/', bukan '\\\\': {raw!r}",
            code="CFG-PATH-ESCAPE",
            key=label,
        )
    if text.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", text):
        raise ConfigError(
            f"{label} harus berupa path relatif: {raw!r}",
            code="CFG-PATH-ESCAPE",
            key=label,
        )
    if _SCHEME_RE.match(text):
        raise ConfigError(
            f"{label} harus berupa path lokal relatif: {raw!r}",
            code="CFG-PATH-ESCAPE",
            key=label,
        )

    posix = PurePosixPath(text)
    if any(part in {"", ".", ".."} for part in posix.parts):
        raise ConfigError(
            f"{label} tidak boleh memuat segmen '.', '..', atau kosong: {raw!r}",
            code="CFG-PATH-ESCAPE",
            key=label,
        )

    try:
        resolved_base = base.resolve()
        candidate = (resolved_base / Path(*posix.parts)).resolve()
    except OSError as exc:
        raise ConfigError(
            f"{label} tidak dapat diresolusi: {raw!r}: {exc}",
            code="CFG-PATH",
            key=label,
        ) from exc
    try:
        candidate.relative_to(resolved_base)
    except ValueError as exc:
        raise ConfigError(
            f"{label} keluar dari direktori basis {resolved_base}: {raw!r}",
            code="CFG-PATH-ESCAPE",
            key=label,
        ) from exc

    if expect_file and candidate.exists() and not candidate.is_file():
        raise ConfigError(
            f"{label} bukan berkas: {candidate}",
            code="CFG-ASSET-MISSING",
            path=candidate,
            key=label,
        )
    if expect_dir and candidate.exists() and not candidate.is_dir():
        raise ConfigError(
            f"{label} bukan direktori: {candidate}",
            code="CFG-ASSET-MISSING",
            path=candidate,
            key=label,
        )
    if must_exist and not candidate.exists():
        raise ConfigError(
            f"{label} tidak ditemukan: {candidate}",
            code=code,
            path=candidate,
            key=label,
        )
    return candidate


def check_case_collisions(directory: Path, *, label: str) -> None:
    """Tolak nama berkas yang hanya berbeda kapitalisasi.

    Perbandingan dilakukan casefold agar Windows dan Linux memberi hasil yang
    sama secara logis. Direktori yang tidak ada dilewati; pemanggil sudah
    memvalidasi keberadaannya.
    """

    if not directory.is_dir():
        return
    seen: dict[str, str] = {}
    for child in directory.iterdir():
        folded = child.name.casefold()
        previous = seen.get(folded)
        if previous is not None and previous != child.name:
            raise ConfigError(
                f"nama berkas hanya berbeda kapitalisasi di {directory}: "
                f"{previous!r} dan {child.name!r}",
                code="CFG-DUPLICATE",
                path=directory,
                key=label,
            )
        seen[folded] = child.name
