#!/usr/bin/env python3
"""Pemeriksa identifier Python AutoOffice.

Checker ini memindai definisi dan referensi identifier pada AST: nama fungsi,
kelas, parameter, target assignment/for/with/comprehension, nama exception,
alias import, nama atribut, dan nama test. Setiap identifier dipecah menjadi
kata snake_case atau CamelCase, lalu setiap kata dibandingkan dengan daftar
token Indonesia yang dikurasi.

Komentar, docstring, dan literal string tidak pernah diperiksa karena checker
hanya berjalan pada node identifier AST. Nama domain ``hitam`` (kontrak tema
deck) dan ``indigo`` dikecualikan agar identifier tema tetap dapat memakai nama
kontrak tersebut.

Daftar token diturunkan dari audit identifier repo, lalu kata Inggris dibuang.
Daftar itu disematkan di modul ini sehingga checker tidak bergantung pada berkas
audit saat dijalankan.

Pemakaian:
    python tools/quality/check_identifiers.py
    python tools/quality/check_identifiers.py --list
    python tools/quality/check_identifiers.py --format json src/autooffice tests

Baris yang memuat komentar ``# identifier-ok`` dikecualikan dari pemeriksaan.
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

DEFAULT_PATHS: tuple[str, ...] = ("src/autooffice", "tests", "tools/quality")

# Nama domain yang sengaja dipertahankan meskipun berasal dari bahasa Indonesia.
DOMAIN_IDENTIFIERS: frozenset[str] = frozenset({"hitam", "indigo"})

# Token Indonesia yang dikurasi dari audit identifier repo. Kata Inggris seperti
# ``black``, ``file``, ``line``, ``name``, dan ``test`` tidak masuk daftar.
INDONESIAN_IDENTIFIER_TOKENS: frozenset[str] = frozenset(
    {
        "akar",
        "akhir",
        "akronim",
        "aktif",
        "alamat",
        "aman",
        "ambil",
        "ambang",
        "antrean",
        "argumen",
        "arsip",
        "asing",
        "atribut",
        "aturan",
        "bab",
        "baca",
        "bagian",
        "baku",
        "baris",
        "batas",
        "berhasil",
        "berkas",
        "bersih",
        "bersudut",
        "berubah",
        "buat",
        "buka",
        "cari",
        "cetak",
        "cocok",
        "daftar",
        "dasar",
        "deskripsi",
        "destinasi",
        "dikenal",
        "diminta",
        "dipilih",
        "direktori",
        "dokumen",
        "entri",
        "fungsi",
        "gagal",
        "gambar",
        "garis",
        "halaman",
        "hapus",
        "hasil",
        "hitung",
        "huruf",
        "indeks",
        "isi",
        "istilah",
        "jalankan",
        "jalur",
        "jenis",
        "judul",
        "jumlah",
        "kalimat",
        "kanan",
        "kandidat",
        "karakter",
        "kata",
        "kegagalan",
        "kelas",
        "keluaran",
        "kembali",
        "kesalahan",
        "kiri",
        "kode",
        "kolom",
        "komentar",
        "konstanta",
        "kosong",
        "kunci",
        "kualitas",
        "lampiran",
        "lanjut",
        "laporan",
        "lebar",
        "lengkap",
        "masalah",
        "masukan",
        "memblokir",
        "mentah",
        "metode",
        "modul",
        "muat",
        "nama",
        "nilai",
        "nim",
        "nims",
        "nomor",
        "objek",
        "pagar",
        "panjang",
        "paragraf",
        "pelanggaran",
        "pembanding",
        "pemisah",
        "pengganti",
        "pengguna",
        "periksa",
        "perintah",
        "pertama",
        "pesan",
        "peta",
        "pindah",
        "pola",
        "posisi",
        "properti",
        "relatif",
        "risiko",
        "salin",
        "samarkan",
        "sampul",
        "sebaris",
        "sebelumnya",
        "sel",
        "simpan",
        "skema",
        "subjudul",
        "tabel",
        "tambah",
        "tampil",
        "tanggal",
        "tanpa",
        "tautan",
        "tebal",
        "teks",
        "temuan",
        "terlihat",
        "terpilih",
        "tersedia",
        "tertutup",
        "tidak",
        "tinggi",
        "tujuan",
        "tulis",
        "tutup",
        "ubah",
        "ukuran",
        "ulang",
        "utama",
        "variabel",
        "waktu",
        "warna",
    }
)

ALLOW_PATTERN = re.compile(r"#\s*identifier-ok\b")
WORD_PATTERN = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]?[a-z]+|[A-Z]+|\d+")


@dataclass(frozen=True)
class Rule:
    """Satu aturan checker dengan nama stabil untuk dokumentasi."""

    name: str
    description: str


RULES: tuple[Rule, ...] = (
    Rule(
        "identifier",
        "Nama identifier wajib bahasa Inggris; hitam dan indigo adalah nama domain.",
    ),
    Rule(
        "unreadable",
        "Berkas tidak dapat diparse; perbaiki sintaks atau encoding.",
    ),
)


@dataclass(frozen=True)
class Finding:
    """Satu temuan checker dengan lokasi dan nama identifier."""

    rule: str
    file: str
    line: int
    name: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: [{self.rule}] {self.name}"


@dataclass(frozen=True)
class Result:
    """Ringkasan hasil pemeriksaan."""

    file_count: int = 0
    findings: tuple[Finding, ...] = ()


def _display_name(path: Path, cwd: Path) -> str:
    """Path relatif terhadap cwd bila memungkinkan, selain itu path absolut."""
    try:
        return path.resolve().relative_to(cwd.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _iter_files(paths: list[str], cwd: Path) -> list[Path]:
    """Kumpulkan berkas Python secara deterministik tanpa duplikasi."""
    selected: dict[Path, None] = {}
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(raw)
        candidates = [path] if path.is_file() else sorted(path.rglob("*.py"))
        for item in candidates:
            if item.suffix == ".py" and item.is_file():
                selected[item] = None
    return sorted(selected, key=lambda item: _display_name(item, cwd))


def _identifier_words(identifier: str) -> tuple[str, ...]:
    """Pecah identifier snake_case atau CamelCase menjadi kata pembentuknya."""
    words: list[str] = []
    for part in identifier.split("_"):
        words.extend(match.group(0) for match in WORD_PATTERN.finditer(part))
    return tuple(words)


def _allow_lines(text: str) -> set[int]:
    """Baca komentar ``# identifier-ok`` per baris tanpa memindai string."""
    result: set[int] = set()
    try:
        token_stream = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in token_stream:
            if token.type == tokenize.COMMENT and ALLOW_PATTERN.search(token.string):
                result.add(token.start[0])
    except IndentationError, tokenize.TokenError:
        return result
    return result


class _IdentifierCollector(ast.NodeVisitor):
    """Kumpulkan nama identifier yang didefinisikan atau direferensikan."""

    def __init__(self) -> None:
        self.names: list[tuple[str, int]] = []
        self._seen: set[tuple[str, int]] = set()

    def add(self, name: str | None, line: int) -> None:
        """Catat satu nama identifier bila belum pernah muncul di baris itu."""
        if not name:
            return
        key = (name, line)
        if key in self._seen:
            return
        self._seen.add(key)
        self.names.append(key)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.add(node.name, node.lineno)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.add(node.name, node.lineno)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.add(node.name, node.lineno)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        self.add(node.arg, node.lineno)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.add(node.id, node.lineno)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.add(node.attr, node.lineno)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.add(node.name, node.lineno)
        self.generic_visit(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        self.add(node.arg, node.lineno)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            line = getattr(alias, "lineno", node.lineno)
            for part in alias.name.split("."):
                self.add(part, line)
            self.add(alias.asname, line)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            line = getattr(alias, "lineno", node.lineno)
            if alias.name != "*":
                self.add(alias.name, line)
            self.add(alias.asname, line)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        self.add(node.name, node.lineno)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        self.add(node.name, node.lineno)
        self.generic_visit(node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        self.add(node.rest, node.lineno)
        self.generic_visit(node)


def _indonesian_word(identifier: str) -> str | None:
    """Kembalikan kata Indonesia pertama pada identifier, bila ada."""
    if identifier.casefold() in DOMAIN_IDENTIFIERS:
        return None
    for word in _identifier_words(identifier):
        folded = word.casefold()
        if folded in DOMAIN_IDENTIFIERS:
            continue
        if folded in INDONESIAN_IDENTIFIER_TOKENS:
            return word
    return None


def _check_tree(tree: ast.Module, text: str, display: str) -> list[Finding]:
    """Periksa satu AST dan kembalikan temuan pada baris yang tidak diizinkan."""
    collector = _IdentifierCollector()
    collector.visit(tree)
    allowed = _allow_lines(text)
    findings: list[Finding] = []
    for name, line in collector.names:
        if line in allowed:
            continue
        if _indonesian_word(name) is not None:
            findings.append(Finding("identifier", display, line, name))
    return findings


def _check_file(path: Path, display: str) -> list[Finding]:
    """Baca dan periksa satu berkas Python."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=display)
    return _check_tree(tree, text, display)


def check(paths: list[str] | None = None, cwd: Path | None = None) -> Result:
    """Pindai path dan kembalikan temuan secara deterministik."""
    root = (cwd or Path.cwd()).resolve()
    requested = list(paths) if paths else list(DEFAULT_PATHS)
    files = _iter_files(requested, root)
    findings: list[Finding] = []
    for path in files:
        display = _display_name(path, root)
        try:
            findings.extend(_check_file(path, display))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            findings.append(
                Finding(
                    "unreadable",
                    display,
                    0,
                    f"tidak dapat diperiksa: {exc.__class__.__name__}",
                )
            )
    findings.sort(key=lambda item: (item.file, item.line, item.name, item.rule))
    return Result(file_count=len(files), findings=tuple(findings))


def _print_text(result: Result) -> None:
    """Cetak satu diagnostik per baris tanpa ringkasan tambahan."""
    for item in result.findings:
        print(item)


def _print_json(result: Result) -> None:
    """Cetak hasil dalam JSON yang stabil dan mudah dibaca mesin."""
    data = {
        "files": result.file_count,
        "findings": len(result.findings),
        "violations": [
            {
                "rule": item.rule,
                "file": item.file,
                "line": item.line,
                "name": item.name,
            }
            for item in result.findings
        ],
    }
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _print_rule_list() -> None:
    """Cetak nama dan deskripsi aturan."""
    for rule in RULES:
        print(f"{rule.name:14} {rule.description}")


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser CLI tanpa menjalankan pemeriksaan."""
    parser = argparse.ArgumentParser(
        prog="check_identifiers.py",
        description="Periksa identifier Indonesia tanpa menjalankan kode.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="berkas atau direktori Python; default src/autooffice, tests, dan tools/quality",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_rules",
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
    if args.list_rules:
        _print_rule_list()
        return 0
    try:
        result = check(args.paths or None)
    except FileNotFoundError as exc:
        print(f"path tidak ditemukan: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        _print_json(result)
    else:
        _print_text(result)
    return 1 if result.findings else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))
