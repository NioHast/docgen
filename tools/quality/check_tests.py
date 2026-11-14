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
class Violation:
    """Satu pelanggaran test dengan lokasi dan jenisnya."""

    kind: str
    file: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: [{self.kind}] {self.message}"


@dataclass(frozen=True)
class Result:
    """Ringkasan hasil pemeriksaan test."""

    file_count: int = 0
    test: int = 0
    violations: tuple[Violation, ...] = ()


def _is_test_file(path: Path) -> bool:
    return path.suffix == ".py" and path.name.startswith("test_")


def _in_fixtures(path: Path) -> bool:
    parts = [part.lower() for part in path.resolve().parts]
    return any(
        parts[position] == "tests" and parts[position + 1] == "fixtures"
        for position in range(len(parts) - 1)
    )


def _iter_files(paths: list[str], cwd: Path) -> list[Path]:
    """Kumpulkan berkas test secara deterministik."""
    selected: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(raw)
        candidates = [path] if path.is_file() else sorted(path.rglob("test_*.py"))
        for item in candidates:
            if not _is_test_file(item) or _in_fixtures(item):
                continue
            if item not in seen:
                seen.add(item)
                selected.append(item)
    selected.sort(key=lambda item: _display_name(item, cwd))
    return selected


def _display_name(path: Path, cwd: Path) -> str:
    try:
        return path.resolve().relative_to(cwd).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Petakan nama lokal import ke nama lengkapnya."""
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    result[alias.asname] = alias.name
                else:
                    root = alias.name.split(".", 1)[0]
                    result[root] = root
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                full_name = f"{prefix}.{alias.name}" if prefix else alias.name
                result[alias.asname or alias.name] = full_name
    return result


def _full_name(node: ast.AST, aliases: dict[str, str]) -> str:
    """Nama lengkap ekspresi Name/Attribute dengan alias import diterapkan."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _full_name(node.value, aliases)
        return f"{base}.{node.attr}" if base else node.attr
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
    name = _full_name(call.func, aliases)
    if name in {"pytest.raises", "pytest.warns", "pytest.fail"}:
        return True
    ending = name.rsplit(".", 1)[-1]
    if ending.startswith("assert"):
        return True
    return ending == "fail" and name in {"pytest.fail", "self.fail", "cls.fail"}


def _is_helper_call(call: ast.Call, helpers: set[str]) -> bool:
    """True bila call memanggil helper assertion lokal."""
    function = call.func
    if isinstance(function, ast.Name):
        return function.id in helpers
    if (
        isinstance(function, ast.Attribute)
        and isinstance(function.value, ast.Name)
        and function.value.id in {"self", "cls"}
    ):
        return function.attr in helpers
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
        previous = expr.left
        for operator, comparator in zip(expr.ops, expr.comparators, strict=True):
            if (
                isinstance(operator, ast.Eq)
                and _same_expr(previous, comparator)
                and _simple_expr(previous)
            ):
                return True
            previous = comparator
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


def _combine(risk: list[str]) -> str:
    if "safe" in risk:
        return "safe"
    if "unsafe" in risk:
        return "unsafe"
    return "unknown"


def _binop_risk(left: str, right: str) -> str:
    if "safe" in {left, right}:
        return "safe"
    if left == "unsafe" and right == "unsafe":
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
        base = _path_risk(expr.value, safe, unsafe)
        if base == "safe":
            return "safe"
        return base
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
        name = _full_name(expr.func, {})
        if name in TEMP_DIRECTORY_CALLS:
            return "safe"
        if name in UNSAFE_CALLS:
            return "unsafe"
        risk = [_path_risk(argument, safe, unsafe) for argument in expr.args]
        risk.extend(_path_risk(keyword.value, safe, unsafe) for keyword in expr.keywords)
        risk.append(_path_risk(expr.func, safe, unsafe))
        return _combine(risk)
    return "unknown"


def _bindings(
    node: ast.FunctionDef | ast.AsyncFunctionDef, unsafe: set[str]
) -> tuple[set[str], set[str]]:
    """Kumpulkan nama lokal yang pasti aman dan yang pasti keluar tmp_path."""
    safe: set[str] = {
        argument.arg
        for argument in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
        if argument.arg in SAFE_PATH_NAMES
    }
    unsafe_names = set(unsafe)
    changed = True
    while changed:
        changed = False
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
                risk = _path_risk(value, safe, unsafe_names)
                verdict = "aman" if risk == "safe" else "tidak_aman" if risk == "unsafe" else ""
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if verdict == "aman" and target.id not in safe:
                        safe.add(target.id)
                        changed = True
                    elif verdict == "tidak_aman" and target.id not in unsafe_names:
                        unsafe_names.add(target.id)
                        changed = True
            if isinstance(child, (ast.With, ast.AsyncWith)):
                for item in child.items:
                    if not isinstance(item.optional_vars, ast.Name):
                        continue
                    if _path_risk(item.context_expr, safe, unsafe_names) != "safe":
                        continue
                    if item.optional_vars.id not in safe:
                        safe.add(item.optional_vars.id)
                        changed = True
    return safe, unsafe_names


def _module_unsafe_roots(tree: ast.Module) -> set[str]:
    """Nama modul yang jelas menunjuk path repo, filesystem, atau working directory."""
    result: set[str] = set()
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
                result.add(target.id)
    return result


def _write_targets(call: ast.Call) -> list[ast.AST]:
    """Kembalikan ekspresi path yang ditulis oleh satu call."""
    function = call.func
    if isinstance(function, ast.Attribute):
        if function.attr in WRITE_METHODS:
            return [function.value]
        return []
    if not isinstance(function, ast.Name):
        return []
    if function.id == "open":
        if len(call.args) < 2:
            return []
        mode = call.args[1]
        if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str):
            return []
        if not any(token in mode.value for token in ("a", "w", "x", "+")):
            return []
        return [call.args[0]]
    name = _full_name(function, {})
    if name not in WRITE_FUNCTIONS:
        return []
    if name in {
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
) -> list[Violation]:
    result: list[Violation] = []
    if not _has_assertion(node, aliases, helpers):
        result.append(
            Violation("no_assert", "", node.lineno, "test tidak memiliki assertion perilaku")
        )
    for assertion in _iter_asserts(node):
        if _is_tautology(assertion.test):
            result.append(
                Violation(
                    "assert_true",
                    "",
                    assertion.lineno,
                    "assert selalu benar; ganti dengan expected independen",
                )
            )
    safe, unsafe_names = _bindings(node, unsafe)
    for call in _iter_calls(node):
        name = _full_name(call.func, aliases)
        if name in SLEEP_CALLS:
            result.append(
                Violation("sleep", "", call.lineno, "test memakai sleep; gunakan fake clock")
            )
        if name.startswith(NETWORK_PREFIXES) or name in NETWORK_CALLS:
            result.append(
                Violation("network", "", call.lineno, f"test mengakses network langsung: {name}")
            )
        for target in _write_targets(call):
            if _path_risk(target, safe, unsafe_names) == "unsafe":
                result.append(
                    Violation(
                        "write",
                        "",
                        call.lineno,
                        "test menulis path yang jelas di luar tmp_path",
                    )
                )
    return result


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
    display: str,
    aliases: dict[str, str],
    helpers: set[str],
    unsafe: set[str],
    result: list[Violation],
    class_names: list[str] | None = None,
) -> int:
    """Kumpulkan test dari module/class dan tambahkan pelanggarannya."""
    count = 0
    class_names = class_names or []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_"):
                continue
            count += 1
            for violation in _violations_for(node, aliases, helpers, unsafe):
                result.append(
                    Violation(
                        violation.kind,
                        display,
                        violation.line,
                        violation.message,
                    )
                )
            for dec in node.decorator_list:
                if _skip_reason_missing(dec, aliases):
                    result.append(
                        Violation(
                            "skip_without_reason",
                            display,
                            dec.lineno,
                            "skip/skipif wajib memiliki alasan tertulis",
                        )
                    )
        elif isinstance(node, ast.ClassDef):
            count += _collect_tests(
                node.body,
                path,
                display,
                aliases,
                helpers,
                unsafe,
                result,
                [*class_names, node.name],
            )
    return count


def _parse_file(path: Path, display: str) -> tuple[int, list[Violation]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=display)
    aliases = _aliases(tree)
    helpers = _assertion_helpers(tree, aliases)
    unsafe = _module_unsafe_roots(tree)
    result: list[Violation] = []
    count = _collect_tests(tree.body, path, display, aliases, helpers, unsafe, result)
    return count, result


def check(paths: list[str] | None = None) -> Result:
    """Pindai path dan kembalikan pelanggaran test secara deterministik."""
    cwd = Path.cwd().resolve()
    requested = list(paths) if paths else list(DEFAULT_PATHS)
    files = _iter_files(requested, cwd)
    test_count = 0
    violations: list[Violation] = []
    for path in files:
        display = _display_name(path, cwd)
        try:
            count, findings = _parse_file(path, display)
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            violations.append(
                Violation(
                    "unreadable",
                    display,
                    0,
                    f"tidak dapat diperiksa: {exc.__class__.__name__}",
                )
            )
            continue
        test_count += count
        violations.extend(findings)
    violations.sort(key=lambda item: (item.file, item.line, item.kind, item.message))
    return Result(file_count=len(files), test=test_count, violations=tuple(violations))


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
        result = check(args.paths or None)
    except FileNotFoundError as exc:
        print(f"path tidak ditemukan: {exc}", file=sys.stderr)
        return 2
    print(f"Berkas test diperiksa: {result.file_count}")
    print(f"Fungsi test diperiksa: {result.test}")
    print(f"Pelanggaran: {len(result.violations)}")
    for violation in result.violations:
        print(f"- {violation}")
    return 1 if result.violations else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))
