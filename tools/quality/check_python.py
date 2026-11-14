#!/usr/bin/env python3
"""Pemeriksa gaya Python 3.15 untuk AutoOffice.

Checker statis ini menolak `from __future__ import annotations`, alias typing
warisan, dan API standard library yang sudah deprecated. Pemeriksaan memakai
AST dan tokenize, tidak menjalankan kode, tidak mengakses jaringan, dan tidak
menulis berkas.

Pemakaian:
    python tools/quality/check_python.py
    python tools/quality/check_python.py --list
    python tools/quality/check_python.py --format json src/autooffice tests

Kode keluar 0 bila bersih, 1 bila ada temuan, dan 2 bila path tidak ditemukan.
"""

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATHS: tuple[str, ...] = ("src/autooffice", "tests")

LEGACY_TYPING: dict[str, str] = {
    "AnyStr": "type parameter dengan constraint PEP 695",
    "ByteString": "bytes | bytearray | memoryview atau collections.abc.Buffer",
    "Callable": "collections.abc.Callable",
    "Dict": "dict",
    "FrozenSet": "frozenset",
    "Hashable": "collections.abc.Hashable",
    "Iterable": "collections.abc.Iterable",
    "Iterator": "collections.abc.Iterator",
    "List": "list",
    "Mapping": "collections.abc.Mapping",
    "MutableMapping": "collections.abc.MutableMapping",
    "NoReturn": "typing.Never",
    "Optional": "X | None",
    "Sequence": "collections.abc.Sequence",
    "Set": "set",
    "Sized": "collections.abc.Sized",
    "Text": "str",
    "Tuple": "tuple",
    "Type": "type",
    "TypeAlias": "type statement PEP 695",
    "TypeGuard": "typing.TypeIs bila narrowing dua arah dibutuhkan",
    "Union": "X | Y",
}

DEPRECATED_CALLS: dict[str, tuple[str, str]] = {
    "datetime.datetime.utcnow": (
        "datetime-utcnow",
        "datetime.utcnow() deprecated; gunakan datetime.now(UTC)",
    ),
    "datetime.utcnow": (
        "datetime-utcnow",
        "datetime.utcnow() deprecated; gunakan datetime.now(UTC)",
    ),
    "datetime.datetime.utcfromtimestamp": (
        "datetime-utcnow",
        "datetime.utcfromtimestamp() deprecated; gunakan datetime.fromtimestamp(ts, UTC)",
    ),
    "datetime.utcfromtimestamp": (
        "datetime-utcnow",
        "datetime.utcfromtimestamp() deprecated; gunakan datetime.fromtimestamp(ts, UTC)",
    ),
    "asyncio.get_event_loop": (
        "asyncio-loop",
        "asyncio.get_event_loop() deprecated; gunakan asyncio.run atau asyncio.Runner",
    ),
    "asyncio.events.get_event_loop": (
        "asyncio-loop",
        "asyncio.get_event_loop() deprecated; gunakan asyncio.run atau asyncio.Runner",
    ),
    "asyncio.get_event_loop_policy": (
        "asyncio-loop",
        "asyncio.get_event_loop_policy() deprecated; gunakan asyncio.run atau asyncio.Runner",
    ),
    "asyncio.events.get_event_loop_policy": (
        "asyncio-loop",
        "asyncio.get_event_loop_policy() deprecated; gunakan asyncio.run atau asyncio.Runner",
    ),
    "codecs.open": (
        "codecs-open",
        "codecs.open() deprecated; gunakan open() bawaan",
    ),
}


@dataclass(frozen=True)
class Aturan:
    """Satu aturan checker dengan nama stabil untuk komentar allow."""

    nama: str
    deskripsi: str


ATURAN: tuple[Aturan, ...] = (
    Aturan(
        "future-annotations",
        "Tolak from __future__ import annotations; anotasi lazy PEP 649/749 sudah default.",
    ),
    Aturan(
        "legacy-typing",
        "Tolak alias typing warisan; gunakan builtin generik dan X | None.",
    ),
    Aturan(
        "datetime-utcnow",
        "Tolak datetime.utcnow/utcfromtimestamp; gunakan datetime.now(UTC).",
    ),
    Aturan(
        "asyncio-loop",
        "Tolak get_event_loop/get_event_loop_policy; gunakan asyncio.run atau Runner.",
    ),
    Aturan(
        "pkg-resources",
        "Tolak pkg_resources; gunakan importlib.resources.",
    ),
    Aturan(
        "codecs-open",
        "Tolak codecs.open; gunakan open() bawaan.",
    ),
    Aturan(
        "unreadable",
        "Berkas tidak dapat diparse; perbaiki sintaks atau encoding.",
    ),
)

POLA_ALLOW = re.compile(
    r"#\s*python-style:\s*allow\s+"
    r"(?P<aturan>[A-Za-z0-9_-]+(?:\s*,\s*[A-Za-z0-9_-]+)*)"
)


@dataclass(frozen=True)
class Temuan:
    """Satu temuan checker dengan lokasi dan nama aturan."""

    aturan: str
    berkas: str
    baris: int
    pesan: str

    def __str__(self) -> str:
        return f"{self.berkas}:{self.baris}: [{self.aturan}] {self.pesan}"


@dataclass(frozen=True)
class Hasil:
    """Ringkasan hasil pemeriksaan."""

    berkas: int = 0
    temuan: tuple[Temuan, ...] = ()


def _nama_tampil(jalur: Path, cwd: Path) -> str:
    """Path relatif terhadap cwd bila memungkinkan, selain itu path absolut."""
    try:
        return jalur.resolve().relative_to(cwd.resolve()).as_posix()
    except ValueError:
        return jalur.resolve().as_posix()


def _iter_files(paths: list[str], cwd: Path) -> list[Path]:
    """Kumpulkan berkas Python secara deterministik tanpa duplikasi."""
    terpilih: dict[Path, None] = {}
    for mentah in paths:
        jalur = Path(mentah)
        if not jalur.is_absolute():
            jalur = cwd / jalur
        jalur = jalur.resolve()
        if not jalur.exists():
            raise FileNotFoundError(mentah)
        kandidat = [jalur] if jalur.is_file() else sorted(jalur.rglob("*.py"))
        for item in kandidat:
            if item.suffix == ".py" and item.is_file():
                terpilih[item] = None
    return sorted(terpilih, key=lambda item: _nama_tampil(item, cwd))


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Petakan nama lokal import ke nama lengkapnya."""
    hasil: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    hasil[alias.asname] = alias.name
                else:
                    akar = alias.name.split(".", 1)[0]
                    hasil[akar] = akar
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            if node.level:
                prefix = "." * node.level + prefix
            for alias in node.names:
                if alias.name == "*":
                    continue
                lengkap = f"{prefix}.{alias.name}" if prefix else alias.name
                hasil[alias.asname or alias.name] = lengkap
    return hasil


def _full_name(node: ast.AST, aliases: dict[str, str]) -> str:
    """Nama lengkap ekspresi Name/Attribute dengan alias import diterapkan."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        dasar = _full_name(node.value, aliases)
        return f"{dasar}.{node.attr}" if dasar else node.attr
    return ""


def _allow_map(teks: str) -> dict[int, set[str]]:
    """Baca komentar `# python-style: allow <rule>` per baris."""
    hasil: dict[int, set[str]] = {}
    try:
        token_stream = tokenize.generate_tokens(io.StringIO(teks).readline)
        for token in token_stream:
            if token.type != tokenize.COMMENT:
                continue
            cocok = POLA_ALLOW.search(token.string)
            if cocok is None:
                continue
            aturan = {bagian.strip() for bagian in cocok.group("aturan").split(",")}
            hasil.setdefault(token.start[0], set()).update(aturan)
    except IndentationError:
        return hasil
    except tokenize.TokenError:
        return hasil
    return hasil


def _tambah(
    hasil: list[Temuan],
    allow: dict[int, set[str]],
    aturan: str,
    tampil: str,
    baris: int,
    pesan: str,
) -> None:
    """Tambahkan temuan kecuali baris yang sama mengizinkannya atau duplikat."""
    if aturan in allow.get(baris, set()):
        return
    if any(item.aturan == aturan and item.baris == baris and item.pesan == pesan for item in hasil):
        return
    hasil.append(Temuan(aturan, tampil, baris, pesan))


def _modul_pkg_resources(nama: str) -> bool:
    """True bila nama modul adalah pkg_resources atau submodulnya."""
    return nama == "pkg_resources" or nama.startswith("pkg_resources.")


def _periksa_tree(tree: ast.Module, teks: str, tampil: str) -> list[Temuan]:
    """Periksa satu AST dan kembalikan temuan mentah."""
    aliases = _aliases(tree)
    allow = _allow_map(teks)
    hasil: list[Temuan] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            _periksa_import_from(node, allow, tampil, hasil)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _modul_pkg_resources(alias.name):
                    _tambah(
                        hasil,
                        allow,
                        "pkg-resources",
                        tampil,
                        node.lineno,
                        "pkg_resources deprecated; gunakan importlib.resources",
                    )
        elif isinstance(node, ast.Call):
            nama = _full_name(node.func, aliases)
            if nama in DEPRECATED_CALLS:
                aturan, pesan = DEPRECATED_CALLS[nama]
                _tambah(hasil, allow, aturan, tampil, node.lineno, pesan)
        elif isinstance(node, (ast.Attribute, ast.Name)):
            nama = _full_name(node, aliases)
            if nama in DEPRECATED_CALLS:
                aturan, pesan = DEPRECATED_CALLS[nama]
                _tambah(hasil, allow, aturan, tampil, node.lineno, pesan)
            elif isinstance(node, ast.Attribute) and nama.startswith("typing."):
                atribut = nama.rsplit(".", 1)[-1]
                pengganti = LEGACY_TYPING.get(atribut)
                if pengganti is not None:
                    _tambah(
                        hasil,
                        allow,
                        "legacy-typing",
                        tampil,
                        node.lineno,
                        f"typing.{atribut} warisan; gunakan {pengganti}",
                    )
    return hasil


def _periksa_import_from(
    node: ast.ImportFrom,
    allow: dict[int, set[str]],
    tampil: str,
    hasil: list[Temuan],
) -> None:
    """Periksa import from untuk future annotations, typing, dan pkg_resources."""
    if node.level == 0 and node.module == "__future__":
        for alias in node.names:
            if alias.name == "annotations":
                _tambah(
                    hasil,
                    allow,
                    "future-annotations",
                    tampil,
                    node.lineno,
                    "hapus from __future__ import annotations; target Python 3.15 lazy",
                )
    if node.level == 0 and node.module == "typing":
        for alias in node.names:
            pengganti = LEGACY_TYPING.get(alias.name)
            if pengganti is None:
                continue
            _tambah(
                hasil,
                allow,
                "legacy-typing",
                tampil,
                getattr(alias, "lineno", node.lineno),
                f"typing.{alias.name} warisan; gunakan {pengganti}",
            )
    if node.level == 0 and _modul_pkg_resources(node.module or ""):
        _tambah(
            hasil,
            allow,
            "pkg-resources",
            tampil,
            node.lineno,
            "pkg_resources deprecated; gunakan importlib.resources",
        )


def _periksa_berkas(jalur: Path, tampil: str) -> list[Temuan]:
    """Baca dan periksa satu berkas Python."""
    teks = jalur.read_text(encoding="utf-8")
    tree = ast.parse(teks, filename=tampil)
    return _periksa_tree(tree, teks, tampil)


def periksa(paths: list[str] | None = None, cwd: Path | None = None) -> Hasil:
    """Pindai path dan kembalikan temuan secara deterministik."""
    akar = (cwd or Path.cwd()).resolve()
    diminta = list(paths) if paths else list(DEFAULT_PATHS)
    berkas = _iter_files(diminta, akar)
    temuan: list[Temuan] = []
    for jalur in berkas:
        tampil = _nama_tampil(jalur, akar)
        try:
            temuan.extend(_periksa_berkas(jalur, tampil))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            temuan.append(
                Temuan(
                    "unreadable",
                    tampil,
                    0,
                    f"tidak dapat diperiksa: {exc.__class__.__name__}",
                )
            )
    temuan.sort(key=lambda item: (item.berkas, item.baris, item.aturan, item.pesan))
    return Hasil(berkas=len(berkas), temuan=tuple(temuan))


def _cetak_teks(hasil: Hasil) -> None:
    """Cetak ringkasan dan temuan dalam format teks."""
    print(f"Berkas diperiksa: {hasil.berkas}")
    print(f"Temuan: {len(hasil.temuan)}")
    for item in hasil.temuan:
        print(f"- {item}")


def _cetak_json(hasil: Hasil) -> None:
    """Cetak hasil dalam JSON yang stabil dan mudah dibaca mesin."""
    per_aturan: dict[str, int] = {}
    for item in hasil.temuan:
        per_aturan[item.aturan] = per_aturan.get(item.aturan, 0) + 1
    data = {
        "files": hasil.berkas,
        "findings": len(hasil.temuan),
        "by_rule": per_aturan,
        "violations": [
            {
                "rule": item.aturan,
                "file": item.berkas,
                "line": item.baris,
                "message": item.pesan,
            }
            for item in hasil.temuan
        ],
    }
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _cetak_daftar() -> None:
    """Cetak nama dan deskripsi aturan untuk dokumentasi dan allow comment."""
    for aturan in ATURAN:
        print(f"{aturan.nama:22} {aturan.deskripsi}")


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser CLI tanpa menjalankan pemeriksaan."""
    parser = argparse.ArgumentParser(
        prog="check_python.py",
        description="Periksa gaya Python 3.15 tanpa menjalankan kode.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="berkas atau direktori Python; default src/autooffice dan tests",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="daftar",
        help="cetak nama dan deskripsi aturan",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="format keluaran; default text",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Jalankan checker dan kembalikan kode keluar 0, 1, atau 2."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.daftar:
        _cetak_daftar()
        return 0
    try:
        hasil = periksa(args.paths or None)
    except FileNotFoundError as exc:
        print(f"path tidak ditemukan: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        _cetak_json(hasil)
    else:
        _cetak_teks(hasil)
    return 1 if hasil.temuan else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))
