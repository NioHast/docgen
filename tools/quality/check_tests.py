#!/usr/bin/env python3
"""Pemeriksa kualitas test statis untuk AutoOffice.

Checker memindai fungsi `test_*` dan menolak pelanggaran keras: test tanpa
assertion perilaku, `assert True` atau tautologi, `time.sleep`, akses network
langsung, penulisan yang jelas di luar `tmp_path`, dan skip tanpa alasan.
Pemeriksaan memakai AST, tidak menjalankan test, tidak mengakses jaringan, dan
tidak menulis berkas. Direktori `tests/fixtures/**` diabaikan.

Pemakaian:
    python tools/quality/check_tests.py [PATH ...]

Kode keluar 0 bila bersih, 1 bila ada pelanggaran, dan 2 bila path tidak ada.
"""

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATHS = ("tests",)
SLEEP_CALLS = frozenset({"time.sleep", "asyncio.sleep"})
NETWORK_PREFIXES = (
    "aiohttp.",
    "http.client.",
    "httpx.",
    "requests.",
    "socket.",
)
NETWORK_CALLS = frozenset(
    {
        "urllib.request.urlopen",
        "urllib.request.urlretrieve",
        "urllib.urlopen",
    }
)
WRITE_METHODS = frozenset(
    {
        "mkdir",
        "touch",
        "unlink",
        "write_bytes",
        "write_text",
    }
)
WRITE_FUNCTIONS = frozenset(
    {
        "os.makedirs",
        "os.mkdir",
        "os.remove",
        "os.rename",
        "os.replace",
        "os.unlink",
        "shutil.copy",
        "shutil.copy2",
        "shutil.copyfile",
        "shutil.copytree",
        "shutil.move",
        "shutil.rmtree",
    }
)
TEMP_DIRECTORY_CALLS = frozenset(
    {
        "tempfile.NamedTemporaryFile",
        "tempfile.TemporaryDirectory",
        "tempfile.TemporaryFile",
        "tempfile.mkdtemp",
    }
)
SAFE_PATH_NAMES = frozenset({"tmp_path", "tmp_path_factory", "tmpdir"})
UNSAFE_CALLS = frozenset(
    {
        "os.getcwd",
        "os.path.expanduser",
        "pathlib.Path.cwd",
        "pathlib.Path.home",
        "Path.cwd",
        "Path.home",
    }
)


@dataclass(frozen=True)
class Pelanggaran:
    """Satu pelanggaran test dengan lokasi dan jenisnya."""

    jenis: str
    berkas: str
    baris: int
    pesan: str

    def __str__(self) -> str:
        return f"{self.berkas}:{self.baris}: [{self.jenis}] {self.pesan}"


@dataclass(frozen=True)
class Hasil:
    """Ringkasan hasil pemeriksaan test."""

    berkas: int = 0
    test: int = 0
    masalah: tuple[Pelanggaran, ...] = ()


def _is_test_file(jalur: Path) -> bool:
    return jalur.suffix == ".py" and jalur.name.startswith("test_")


def _di_fixtures(jalur: Path) -> bool:
    bagian = [bagian.lower() for bagian in jalur.resolve().parts]
    return any(
        bagian[posisi] == "tests" and bagian[posisi + 1] == "fixtures"
        for posisi in range(len(bagian) - 1)
    )


def _iter_files(paths: list[str], cwd: Path) -> list[Path]:
    """Kumpulkan berkas test secara deterministik."""
    terpilih: list[Path] = []
    terlihat: set[Path] = set()
    for mentah in paths:
        jalur = Path(mentah)
        if not jalur.is_absolute():
            jalur = cwd / jalur
        jalur = jalur.resolve()
        if not jalur.exists():
            raise FileNotFoundError(mentah)
        kandidat = [jalur] if jalur.is_file() else sorted(jalur.rglob("test_*.py"))
        for item in kandidat:
            if not _is_test_file(item) or _di_fixtures(item):
                continue
            if item not in terlihat:
                terlihat.add(item)
                terpilih.append(item)
    terpilih.sort(key=lambda item: _nama_tampil(item, cwd))
    return terpilih


def _nama_tampil(jalur: Path, cwd: Path) -> str:
    try:
        return jalur.resolve().relative_to(cwd).as_posix()
    except ValueError:
        return jalur.resolve().as_posix()


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


class _DirectVisitor(ast.NodeVisitor):
    """Telusuri body tanpa masuk ke definisi fungsi atau class bersarang."""

    def __init__(self, aliases: dict[str, str], helpers: set[str] | None = None) -> None:
        self.aliases = aliases
        self.helpers = helpers or set()
        self.found = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Assert(self, node: ast.Assert) -> None:
        self.found = True

    def visit_Call(self, node: ast.Call) -> None:
        if _is_assertion_call(node, self.aliases) or _is_helper_call(node, self.helpers):
            self.found = True
        self.generic_visit(node)


def _is_assertion_call(call: ast.Call, aliases: dict[str, str]) -> bool:
    """True bila call adalah assertion pytest/unittest yang dikenal."""
    nama = _full_name(call.func, aliases)
    if nama in {"pytest.raises", "pytest.warns", "pytest.fail"}:
        return True
    akhir = nama.rsplit(".", 1)[-1]
    if akhir.startswith("assert"):
        return True
    return akhir == "fail" and nama in {"pytest.fail", "self.fail", "cls.fail"}


def _is_helper_call(call: ast.Call, helpers: set[str]) -> bool:
    """True bila call memanggil helper assertion lokal."""
    fungsi = call.func
    if isinstance(fungsi, ast.Name):
        return fungsi.id in helpers
    if (
        isinstance(fungsi, ast.Attribute)
        and isinstance(fungsi.value, ast.Name)
        and fungsi.value.id in {"self", "cls"}
    ):
        return fungsi.attr in helpers
    return False


def _has_direct_assertion(body: list[ast.stmt], aliases: dict[str, str]) -> bool:
    visitor = _DirectVisitor(aliases)
    for statement in body:
        visitor.visit(statement)
    return visitor.found


def _assertion_helpers(tree: ast.Module, aliases: dict[str, str]) -> set[str]:
    """Kumpulkan fungsi non-test yang memuat assertion langsung."""
    helpers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("test_"):
            continue
        if _has_direct_assertion(node.body, aliases):
            helpers.add(node.name)
    return helpers


def _has_assertion(
    node: ast.FunctionDef | ast.AsyncFunctionDef, aliases: dict[str, str], helpers: set[str]
) -> bool:
    visitor = _DirectVisitor(aliases, helpers)
    for statement in node.body:
        visitor.visit(statement)
    return visitor.found


def _is_true_constant(node: ast.AST) -> bool:
    if not isinstance(node, ast.Constant):
        return False
    if isinstance(node.value, bool):
        return node.value is True
    return isinstance(node.value, int) and node.value == 1


def _is_not_false(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Constant)
        and node.operand.value is False
    )


def _same_expr(left: ast.AST, right: ast.AST) -> bool:
    return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)


def _is_tautology(expr: ast.AST) -> bool:
    """True bila ekspresi assertion selalu benar karena bentuknya."""
    if _is_true_constant(expr) or _is_not_false(expr):
        return True
    if isinstance(expr, ast.Compare):
        sebelumnya = expr.left
        for operator, pembanding in zip(expr.ops, expr.comparators, strict=True):
            if (
                isinstance(operator, ast.Eq)
                and _same_expr(sebelumnya, pembanding)
                and _simple_expr(sebelumnya)
            ):
                return True
            sebelumnya = pembanding
    if isinstance(expr, ast.BoolOp):
        return any(_is_tautology(value) for value in expr.values)
    return False


def _simple_expr(expr: ast.AST) -> bool:
    """True untuk ekspresi tanpa call, sehingga perbandingan identik tautologis."""
    return isinstance(expr, (ast.Attribute, ast.Constant, ast.Name, ast.Subscript))


def _iter_calls(node: ast.AST):
    """Hasilkan call di body test tanpa masuk ke definisi bersarang."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Call):
            yield child
        yield from _iter_calls(child)


def _iter_asserts(node: ast.AST):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Assert):
            yield child
        yield from _iter_asserts(child)


def _combine(risiko: list[str]) -> str:
    if "safe" in risiko:
        return "safe"
    if "unsafe" in risiko:
        return "unsafe"
    return "unknown"


def _binop_risk(kiri: str, kanan: str) -> str:
    if "safe" in {kiri, kanan}:
        return "safe"
    if kiri == "unsafe" and kanan == "unsafe":
        return "unsafe"
    return "unknown"


def _path_risk(expr: ast.AST, safe: set[str], unsafe: set[str]) -> str:
    """Perkirakan apakah ekspresi path pasti aman, pasti keluar tmp_path, atau unknown."""
    if isinstance(expr, ast.Name):
        if expr.id in safe or expr.id in SAFE_PATH_NAMES:
            return "safe"
        if expr.id in unsafe or expr.id == "__file__":
            return "unsafe"
        return "unknown"
    if isinstance(expr, ast.Constant):
        if isinstance(expr.value, str):
            return "unsafe"
        return "unknown"
    if isinstance(expr, ast.Attribute):
        if expr.attr in {"cwd", "home"} and _full_name(expr.value, {}) in {"Path", "pathlib.Path"}:
            return "unsafe"
        dasar = _path_risk(expr.value, safe, unsafe)
        if dasar == "safe":
            return "safe"
        return dasar
    if isinstance(expr, ast.Subscript):
        return _path_risk(expr.value, safe, unsafe)
    if isinstance(expr, ast.BinOp):
        return _binop_risk(
            _path_risk(expr.left, safe, unsafe),
            _path_risk(expr.right, safe, unsafe),
        )

    if isinstance(expr, (ast.List, ast.Set, ast.Tuple)):
        return _combine([_path_risk(item, safe, unsafe) for item in expr.elts])
    if isinstance(expr, ast.JoinedStr):
        return _combine([_path_risk(item, safe, unsafe) for item in expr.values])
    if isinstance(expr, ast.Call):
        nama = _full_name(expr.func, {})
        if nama in TEMP_DIRECTORY_CALLS:
            return "safe"
        if nama in UNSAFE_CALLS:
            return "unsafe"
        risiko = [_path_risk(argument, safe, unsafe) for argument in expr.args]
        risiko.extend(_path_risk(keyword.value, safe, unsafe) for keyword in expr.keywords)
        risiko.append(_path_risk(expr.func, safe, unsafe))
        return _combine(risiko)
    return "unknown"


def _bindings(
    node: ast.FunctionDef | ast.AsyncFunctionDef, unsafe: set[str]
) -> tuple[set[str], set[str]]:
    """Kumpulkan nama lokal yang pasti aman dan yang pasti keluar tmp_path."""
    aman: set[str] = {
        argumen.arg
        for argumen in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        if argumen.arg in SAFE_PATH_NAMES
    }
    tidak_aman = set(unsafe)
    berubah = True
    while berubah:
        berubah = False
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                targets = child.targets
                value = child.value
            elif isinstance(child, ast.AnnAssign) and child.value is not None:
                targets = [child.target]
                value = child.value
            else:
                targets = []
                value = None
            if value is not None:
                risiko = _path_risk(value, aman, tidak_aman)
                tujuan = "aman" if risiko == "safe" else "tidak_aman" if risiko == "unsafe" else ""
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if tujuan == "aman" and target.id not in aman:
                        aman.add(target.id)
                        berubah = True
                    elif tujuan == "tidak_aman" and target.id not in tidak_aman:
                        tidak_aman.add(target.id)
                        berubah = True
            if isinstance(child, (ast.With, ast.AsyncWith)):
                for item in child.items:
                    if not isinstance(item.optional_vars, ast.Name):
                        continue
                    if _path_risk(item.context_expr, aman, tidak_aman) != "safe":
                        continue
                    if item.optional_vars.id not in aman:
                        aman.add(item.optional_vars.id)
                        berubah = True
    return aman, tidak_aman


def _module_unsafe_roots(tree: ast.Module) -> set[str]:
    """Nama modul yang jelas menunjuk path repo, filesystem, atau working directory."""
    hasil: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        if _path_risk(value, set(), set()) != "unsafe":
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                hasil.add(target.id)
    return hasil


def _write_targets(call: ast.Call) -> list[ast.AST]:
    """Kembalikan ekspresi path yang ditulis oleh satu call."""
    fungsi = call.func
    if isinstance(fungsi, ast.Attribute):
        if fungsi.attr in WRITE_METHODS:
            return [fungsi.value]
        return []
    if not isinstance(fungsi, ast.Name):
        return []
    if fungsi.id == "open":
        if len(call.args) < 2:
            return []
        mode = call.args[1]
        if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str):
            return []
        if not any(token in mode.value for token in ("a", "w", "x", "+")):
            return []
        return [call.args[0]]
    nama = _full_name(fungsi, {})
    if nama not in WRITE_FUNCTIONS:
        return []
    if nama in {
        "os.rename",
        "os.replace",
        "shutil.copy",
        "shutil.copy2",
        "shutil.copyfile",
        "shutil.copytree",
        "shutil.move",
    }:
        return list(call.args[-1:])
    return list(call.args[:1])


def _violations_for(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    aliases: dict[str, str],
    helpers: set[str],
    unsafe: set[str],
) -> list[Pelanggaran]:
    hasil: list[Pelanggaran] = []
    if not _has_assertion(node, aliases, helpers):
        hasil.append(
            Pelanggaran("no_assert", "", node.lineno, "test tidak memiliki assertion perilaku")
        )
    for assertion in _iter_asserts(node):
        if _is_tautology(assertion.test):
            hasil.append(
                Pelanggaran(
                    "assert_true",
                    "",
                    assertion.lineno,
                    "assert selalu benar; ganti dengan expected independen",
                )
            )
    aman, tidak_aman = _bindings(node, unsafe)
    for call in _iter_calls(node):
        nama = _full_name(call.func, aliases)
        if nama in SLEEP_CALLS:
            hasil.append(
                Pelanggaran("sleep", "", call.lineno, "test memakai sleep; gunakan fake clock")
            )
        if nama.startswith(NETWORK_PREFIXES) or nama in NETWORK_CALLS:
            hasil.append(
                Pelanggaran("network", "", call.lineno, f"test mengakses network langsung: {nama}")
            )
        for target in _write_targets(call):
            if _path_risk(target, aman, tidak_aman) == "unsafe":
                hasil.append(
                    Pelanggaran(
                        "write",
                        "",
                        call.lineno,
                        "test menulis path yang jelas di luar tmp_path",
                    )
                )
    return hasil


def _skip_reason_missing(dec: ast.AST, aliases: dict[str, str]) -> bool:
    """True bila dekorator skip/skipif tidak menyertakan reason."""
    if isinstance(dec, ast.Call):
        if _full_name(dec.func, aliases) not in {"pytest.mark.skip", "pytest.mark.skipif"}:
            return False
        return not any(keyword.arg == "reason" for keyword in dec.keywords)
    return _full_name(dec, aliases) in {"pytest.mark.skip", "pytest.mark.skipif"}


def _collect_tests(
    body: list[ast.stmt],
    path: Path,
    tampil: str,
    aliases: dict[str, str],
    helpers: set[str],
    unsafe: set[str],
    hasil: list[Pelanggaran],
    kelas: list[str] | None = None,
) -> int:
    """Kumpulkan test dari module/class dan tambahkan pelanggarannya."""
    jumlah = 0
    kelas = kelas or []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_"):
                continue
            jumlah += 1
            for violation in _violations_for(node, aliases, helpers, unsafe):
                hasil.append(
                    Pelanggaran(
                        violation.jenis,
                        tampil,
                        violation.baris,
                        violation.pesan,
                    )
                )
            for dec in node.decorator_list:
                if _skip_reason_missing(dec, aliases):
                    hasil.append(
                        Pelanggaran(
                            "skip_without_reason",
                            tampil,
                            dec.lineno,
                            "skip/skipif wajib memiliki alasan tertulis",
                        )
                    )
        elif isinstance(node, ast.ClassDef):
            jumlah += _collect_tests(
                node.body,
                path,
                tampil,
                aliases,
                helpers,
                unsafe,
                hasil,
                [*kelas, node.name],
            )
    return jumlah


def _parse_file(path: Path, tampil: str) -> tuple[int, list[Pelanggaran]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=tampil)
    aliases = _aliases(tree)
    helpers = _assertion_helpers(tree, aliases)
    unsafe = _module_unsafe_roots(tree)
    hasil: list[Pelanggaran] = []
    jumlah = _collect_tests(tree.body, path, tampil, aliases, helpers, unsafe, hasil)
    return jumlah, hasil


def periksa(paths: list[str] | None = None) -> Hasil:
    """Pindai path dan kembalikan pelanggaran test secara deterministik."""
    cwd = Path.cwd().resolve()
    diminta = list(paths) if paths else list(DEFAULT_PATHS)
    berkas = _iter_files(diminta, cwd)
    jumlah_test = 0
    masalah: list[Pelanggaran] = []
    for jalur in berkas:
        tampil = _nama_tampil(jalur, cwd)
        try:
            jumlah, temuan = _parse_file(jalur, tampil)
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            masalah.append(
                Pelanggaran(
                    "unreadable",
                    tampil,
                    0,
                    f"tidak dapat diperiksa: {exc.__class__.__name__}",
                )
            )
            continue
        jumlah_test += jumlah
        masalah.extend(temuan)
    masalah.sort(key=lambda item: (item.berkas, item.baris, item.jenis, item.pesan))
    return Hasil(berkas=len(berkas), test=jumlah_test, masalah=tuple(masalah))


def main(argv: list[str] | None = None) -> int:
    """Jalankan checker dan kembalikan kode keluar 0, 1, atau 2."""
    parser = argparse.ArgumentParser(
        prog="check_tests.py",
        description="Periksa kualitas test statis tanpa menjalankan test.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="berkas atau direktori test; default tests/",
    )
    args = parser.parse_args(argv)
    try:
        hasil = periksa(args.paths or None)
    except FileNotFoundError as exc:
        print(f"path tidak ditemukan: {exc}", file=sys.stderr)
        return 2
    print(f"Berkas test diperiksa: {hasil.berkas}")
    print(f"Fungsi test diperiksa: {hasil.test}")
    print(f"Pelanggaran: {len(hasil.masalah)}")
    for masalah in hasil.masalah:
        print(f"- {masalah}")
    return 1 if hasil.masalah else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))
