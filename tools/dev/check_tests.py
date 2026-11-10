#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 nothinx
"""Pemeriksa kualitas test statis untuk suite repo ini.

Skrip memindai fungsi `test_*` di module-level atau class, lalu memberi verdict
berdasarkan sinyal kelemahan yang bisa dibaca dari AST. Hasilnya adalah bahan
review, bukan vonis otomatis: setiap temuan menyertakan sinyal, keyakinan,
bukti singkat, dan saran tindakan.

Pemakaian:
    python tools/dev/check_tests.py [paths...] [--format json|markdown]
        [--output PATH] [--fail-on high|medium|low]

Default path adalah `tests/`, default format JSON, dan default kode keluar 0.
Opsi `--fail-on` memilih level keyakinan minimum yang memicu kode keluar 1.
Direktori `tests/fixtures/**` dan berkas selain `test_*.py` diabaikan.

Skrip hanya memakai pustaka standar dan tidak menjalankan test atau Word.
Deteksi `duplicate_body` bersifat exact AST; duplikasi semantik tidak dideteksi.
"""

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

GENERATED_BY = "tools/dev/check_tests.py"
SCHEMA_VERSION = 1
DEFAULT_PATHS = ("tests",)

VERDICT_ORDER = ("KEEP", "KEEP-WEAK", "MERGE", "TRIM", "REMOVE")
SEVERITY_ORDER = ("REMOVE", "MERGE", "TRIM", "KEEP-WEAK", "KEEP")
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}

SIGNAL_VERDICT = {
    "no_assert": "REMOVE",
    "tautology": "REMOVE",
    "expected_from_sut": "REMOVE",
    "existence_only": "REMOVE",
    "duplicate_body": "MERGE",
    "private_access": "TRIM",
    "broad_raises": "KEEP-WEAK",
    "exit_code_only": "KEEP-WEAK",
    "exact_snapshot": "TRIM",
    "env_dependent": "KEEP-WEAK",
    "platform_skip_only": "KEEP-WEAK",
    "integration_in_unit": "MERGE",
}
SIGNAL_CONFIDENCE = {
    "no_assert": "high",
    "tautology": "high",
    "expected_from_sut": "medium",
    "existence_only": "high",
    "duplicate_body": "high",
    "private_access": "medium",
    "broad_raises": "medium",
    "exit_code_only": "high",
    "exact_snapshot": "medium",
    "env_dependent": "low",
    "platform_skip_only": "medium",
    "integration_in_unit": "medium",
}
SIGNAL_ACTION = {
    "no_assert": "Hapus test atau tambahkan assertion yang memeriksa perilaku",
    "tautology": "Ganti assertion dengan nilai expected independen",
    "expected_from_sut": "Hitung expected dari sumber independen, bukan dari SUT",
    "existence_only": "Tambahkan assertion nilai atau isi hasil",
    "duplicate_body": "Gabungkan dengan test duplikat atau hapus salinannya",
    "private_access": "Uji lewat API publik atau sediakan seam yang stabil",
    "broad_raises": "Persempit exception dan tambahkan match atau assertion kode error",
    "exit_code_only": "Tambahkan assertion pesan atau kode error domain",
    "exact_snapshot": "Pindahkan snapshot ke fixture dan assert invariant yang relevan",
    "env_dependent": "Ganti waktu, random, jaringan, path absolut, atau os.environ dengan fake",
    "platform_skip_only": "Pisahkan test platform ke marker yang sesuai atau uji lintas platform",
    "integration_in_unit": "Pindahkan test ke tests/integration atau ganti boundary dengan fake",
}

BROAD_EXCEPTIONS = frozenset(
    {"Exception", "BaseException", "ValueError", "TypeError", "RuntimeError", "KeyError"}
)
ERROR_CODE_NAMES = frozenset({"code", "errno", "returncode", "exit_code"})
COMPARISON_OPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
ENV_WRITE_CALLS = frozenset(
    {
        "os.putenv",
        "os.unsetenv",
        "os.environ.update",
        "os.environ.setdefault",
        "os.environ.pop",
        "os.environ.clear",
    }
)
SUBPROCESS_EXEC_NAMES = frozenset(
    {
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.popen",
        "subprocess.run",
    }
)
OS_EXEC_NAMES = frozenset({"os.popen", "os.system"})
READ_CALL_NAMES = frozenset(
    {
        "copy",
        "copytree",
        "exists",
        "glob",
        "is_dir",
        "is_file",
        "iterdir",
        "load",
        "loads",
        "open",
        "read_bytes",
        "read_text",
        "rglob",
        "walk",
    }
)
COM_CALL_NAMES = frozenset({"dispatch", "ensuredispatch", "getactiveobject", "createobject"})


class _Test:
    """Satu fungsi test yang ditemukan beserta AST dan metadata berkas."""

    __slots__ = (
        "aliases",
        "assert_helpers",
        "body",
        "body_hash",
        "decorators",
        "end_line",
        "file",
        "id",
        "line",
        "local_private",
        "node",
        "path",
    )

    def __init__(
        self,
        *,
        id: str,
        file: str,
        line: int,
        end_line: int,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        aliases: dict[str, str],
        assert_helpers: set[str],
        local_private: set[str],
        path: Path,
    ) -> None:
        self.id = id
        self.file = file
        self.line = line
        self.end_line = end_line
        self.node = node
        self.body = node.body
        self.decorators = node.decorator_list
        self.aliases = aliases
        self.assert_helpers = assert_helpers
        self.body_hash = _body_hash(node.body)
        self.local_private = local_private
        self.path = path


def _display_path(path: Path, cwd: Path) -> str:
    """Kembalikan path relatif ke cwd bila memungkinkan, selalu dengan slash."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(cwd).as_posix()
    except ValueError:
        return resolved.as_posix()


def _is_test_file(path: Path) -> bool:
    """True bila nama berkas memakai pola test_*.py."""
    return path.suffix == ".py" and path.name.startswith("test_")


def _in_fixtures(path: Path) -> bool:
    """True bila path berada di bawah tests/fixtures."""
    parts = [part.lower() for part in path.resolve().parts]
    return any(
        parts[index] == "tests" and parts[index + 1] == "fixtures"
        for index in range(len(parts) - 1)
    )


def _iter_files(paths: list[str], cwd: Path) -> list[Path]:
    """Kumpulkan berkas test dari path yang diberikan secara deterministik."""
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
        for candidate in candidates:
            if not _is_test_file(candidate) or _in_fixtures(candidate):
                continue
            if candidate not in seen:
                seen.add(candidate)
                selected.append(candidate)
    selected.sort(key=lambda item: _display_path(item, cwd))
    return selected


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    """Petakan nama lokal import ke nama lengkapnya."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                else:
                    root = alias.name.split(".", 1)[0]
                    aliases[root] = root
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                full = f"{prefix}.{alias.name}" if prefix else alias.name
                aliases[alias.asname or alias.name] = full
    return aliases


def _private_name(name: str) -> bool:
    """True untuk nama privat satu garis bawah, bukan dunder atau nama buang."""
    if name == "_":
        return False
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _local_private_names(tree: ast.Module) -> set[str]:
    """Nama privat yang didefinisikan di berkas test itu sendiri."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if _private_name(node.name):
                names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and _private_name(target.id):
                    names.add(target.id)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and _private_name(node.target.id)
        ):
            names.add(node.target.id)
    return names


def _body_without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """Buang docstring pertama dari body fungsi."""
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return body[1:]
    return body


def _body_hash(body: list[ast.stmt]) -> str:
    """Hash AST body setelah docstring dibuang.

    Sinyal duplikasi bersifat exact AST. Dua test yang berbeda secara sintaks
    tetapi setara secara semantik tidak terdeteksi oleh hash ini.
    """
    normalized = ast.Module(body=_body_without_docstring(body), type_ignores=[])
    dump = ast.dump(normalized, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dump.encode("utf-8")).hexdigest()


def _collect_body(
    body: list[ast.stmt],
    display: str,
    classes: list[str],
    aliases: dict[str, str],
    assert_helpers: set[str],
    local_private: set[str],
    path: Path,
    hasil: list[_Test],
) -> None:
    """Telusuri body module atau class untuk mengumpulkan fungsi test."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("test_"):
                continue
            qualified = "::".join([display, *classes, node.name])
            hasil.append(
                _Test(
                    id=qualified,
                    file=display,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    node=node,
                    aliases=aliases,
                    assert_helpers=assert_helpers,
                    local_private=local_private,
                    path=path,
                )
            )
        elif isinstance(node, ast.ClassDef):
            _collect_body(
                node.body,
                display,
                [*classes, node.name],
                aliases,
                assert_helpers,
                local_private,
                path,
                hasil,
            )


def _collect_file(path: Path, display: str) -> list[_Test]:
    """Parse satu berkas lalu kembalikan semua fungsi test di dalamnya."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=display)
    aliases = _import_aliases(tree)
    assert_helpers = _assertion_helpers(tree, aliases)
    local_private = _local_private_names(tree)
    hasil: list[_Test] = []
    _collect_body(tree.body, display, [], aliases, assert_helpers, local_private, path, hasil)
    return hasil


def scan(paths: list[str] | None = None) -> list[_Test]:
    """Pindai path dan kembalikan test terurut berdasarkan file lalu baris."""
    cwd = Path.cwd().resolve()
    requested = list(paths) if paths else list(DEFAULT_PATHS)
    hasil: list[_Test] = []
    for path in _iter_files(requested, cwd):
        display = _display_path(path, cwd)
        try:
            hasil.extend(_collect_file(path, display))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            print(f"lewati {display}: {exc.__class__.__name__}", file=sys.stderr)
    hasil.sort(key=lambda item: (item.file, item.line, item.id))
    return hasil


def _duplicate_map(tests: list[_Test]) -> dict[str, str]:
    """Petakan id test duplikat ke id test kanonis pertama."""
    groups: dict[str, list[_Test]] = {}
    for test in tests:
        groups.setdefault(test.body_hash, []).append(test)
    duplicates: dict[str, str] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        canonical = group[0]
        for duplicate in group[1:]:
            duplicates[duplicate.id] = canonical.id
    return duplicates


def _walk_body(test: _Test):
    """Hasilkan semua node AST di body test."""
    for statement in test.body:
        yield from ast.walk(statement)


def _full_name(node: ast.AST, aliases: dict[str, str]) -> str:
    """Nama lengkap ekspresi Name/Attribute dengan alias import diterapkan."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _full_name(node.value, aliases)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _is_assertion_call(call: ast.Call, aliases: dict[str, str]) -> bool:
    """True bila call adalah assertion pytest/unittest yang dikenal."""
    name = _full_name(call.func, aliases)
    if name in {"pytest.raises", "pytest.warns", "pytest.fail"}:
        return True
    last = name.rsplit(".", 1)[-1]
    if last.startswith("assert"):
        return True
    return last == "fail" and name in {"pytest.fail", "self.fail", "cls.fail"}


def _walk_direct(node: ast.AST):
    """Telusuri node tanpa masuk ke definisi fungsi/class bersarang."""
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield from _walk_direct(child)


def _body_has_direct_assertion(body: list[ast.stmt], aliases: dict[str, str]) -> bool:
    """True bila body memuat assertion langsung, bukan lewat helper lain."""
    for statement in body:
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        for node in _walk_direct(statement):
            if isinstance(node, ast.Assert):
                return True
            if isinstance(node, ast.Call) and _is_assertion_call(node, aliases):
                return True
    return False


def _assertion_helpers(tree: ast.Module, aliases: dict[str, str]) -> set[str]:
    """Kumpulkan fungsi/class method lokal yang memuat assertion langsung."""
    helpers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("test_"):
            continue
        if _body_has_direct_assertion(node.body, aliases):
            helpers.add(node.name)
    return helpers


def _is_helper_call(call: ast.Call, test: _Test) -> bool:
    """True bila call memanggil helper assertion lokal secara langsung."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in test.assert_helpers
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in {"self", "cls"}
    ):
        return func.attr in test.assert_helpers
    return False


def _has_no_assert(test: _Test) -> bool:
    """True bila test tidak punya assertion langsung maupun lewat helper lokal.

    ``with pytest.raises(...)`` ikut terdeteksi karena context manager-nya
    berupa Call yang dikunjungi bersama body test.
    """
    for node in _walk_body(test):
        if isinstance(node, ast.Assert):
            return False
        if isinstance(node, ast.Call) and (
            _is_assertion_call(node, test.aliases) or _is_helper_call(node, test)
        ):
            return False
    return True


def _is_true_literal(node: ast.AST) -> bool:
    """True untuk `True` dan integer `1`."""
    if not isinstance(node, ast.Constant):
        return False
    if isinstance(node.value, bool):
        return node.value is True
    return isinstance(node.value, int) and node.value == 1


def _is_not_false(node: ast.AST) -> bool:
    """True untuk ekspresi `not False`."""
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Constant)
        and node.operand.value is False
    )


def _same_expr(left: ast.AST, right: ast.AST) -> bool:
    """Bandingkan dua ekspresi berdasarkan dump AST tanpa atribut lokasi."""
    return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)


def _contains_tautology(expr: ast.AST) -> bool:
    """True bila ekspresi assertion selalu benar karena bentuknya."""
    if _is_true_literal(expr) or _is_not_false(expr):
        return True
    if isinstance(expr, ast.Compare):
        previous = expr.left
        for operator, comparator in zip(expr.ops, expr.comparators, strict=True):
            if isinstance(operator, ast.Eq) and _same_expr(previous, comparator):
                return True
            previous = comparator
    if isinstance(expr, ast.BoolOp):
        return any(_contains_tautology(value) for value in expr.values)
    return False


def _has_tautology(test: _Test) -> bool:
    """True bila ada assertion tautologis di test."""
    return any(
        _contains_tautology(node.test) for node in _walk_body(test) if isinstance(node, ast.Assert)
    )


def _expected_name(name: str) -> bool:
    """True untuk variabel expected atau expected_*."""
    lower = name.lower()
    return lower == "expected" or lower.startswith("expected_")


def _expected_pair(
    left: ast.AST,
    right: ast.AST,
    assigned: dict[str, set[str]],
    aliases: dict[str, str],
) -> bool:
    """True bila pasangan Compare membandingkan call SUT dengan expected-nya."""
    if isinstance(left, ast.Name) and isinstance(right, ast.Call):
        return _full_name(right.func, aliases) in assigned.get(left.id, set())
    if isinstance(left, ast.Call) and isinstance(right, ast.Name):
        return _full_name(left.func, aliases) in assigned.get(right.id, set())
    if isinstance(left, ast.Call) and isinstance(right, ast.Call):
        left_name = _full_name(left.func, aliases)
        return bool(left_name) and left_name == _full_name(right.func, aliases)
    return False


def _has_expected_from_sut(test: _Test) -> bool:
    """True bila expected diisi dari call SUT yang sama dengan yang diuji."""
    assigned: dict[str, set[str]] = {}
    for node in _walk_body(test):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        if not isinstance(value, ast.Call):
            continue
        call_name = _full_name(value.func, test.aliases)
        if not call_name:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and _expected_name(target.id):
                assigned.setdefault(target.id, set()).add(call_name)
    if not assigned:
        return False
    for node in _walk_body(test):
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
            continue
        previous = node.test.left
        for operator, comparator in zip(node.test.ops, node.test.comparators, strict=True):
            if isinstance(operator, ast.Eq) and _expected_pair(
                previous, comparator, assigned, test.aliases
            ):
                return True
            previous = comparator
    return False


def _is_none_constant(node: ast.AST) -> bool:
    """True untuk literal None."""
    return isinstance(node, ast.Constant) and node.value is None


def _is_existence_expr(expr: ast.AST, aliases: dict[str, str]) -> bool:
    """True untuk assertion yang hanya memeriksa keberadaan atau tipe."""
    if isinstance(expr, ast.Compare) and len(expr.ops) == 1 and isinstance(expr.ops[0], ast.IsNot):
        return _is_none_constant(expr.left) or _is_none_constant(expr.comparators[0])
    if isinstance(expr, ast.Call):
        last = _full_name(expr.func, aliases).rsplit(".", 1)[-1]
        return last in {"hasattr", "callable", "is_file", "exists"}
    if isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.And):
        return all(_is_existence_expr(value, aliases) for value in expr.values)
    return False


def _has_existence_only(test: _Test) -> bool:
    """True bila seluruh assertion test hanya memeriksa keberadaan."""
    assertions = [node for node in _walk_body(test) if isinstance(node, ast.Assert)]
    return bool(assertions) and all(
        _is_existence_expr(node.test, test.aliases) for node in assertions
    )


def _bound_names(test: _Test) -> set[str]:
    """Nama lokal yang diikat di dalam test atau menjadi argumennya."""
    names: set[str] = set()
    for argument in [
        *test.node.args.posonlyargs,
        *test.node.args.args,
        *test.node.args.kwonlyargs,
        test.node.args.vararg,
        test.node.args.kwarg,
    ]:
        if argument is not None:
            names.add(argument.arg)
    for node in _walk_body(test):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.ExceptHandler),
        ):
            name = node.name
            if name is not None:
                names.add(name)
    return names


def _is_production_name(name: str) -> bool:
    """True bila nama modul berasal dari paket produksi ``docgen`` atau ``src``."""
    return (
        name == "docgen" or name.startswith("docgen.") or name == "src" or name.startswith("src.")
    )


def _production_private_alias(name: str, aliases: dict[str, str]) -> bool:
    """True bila nama lokal adalah import privat dari modul produksi."""
    full = aliases.get(name)
    if full is None or not _is_production_name(full):
        return False
    return _private_name(name) or any(_private_name(part) for part in full.split("."))


def _annotation_node_ids(node: ast.AST) -> set[int]:
    """Kumpulkan id node di dalam anotasi agar tidak dianggap akses runtime."""
    ids: set[int] = set()
    for child in ast.walk(node):
        annotation: ast.AST | None = None
        if isinstance(child, (ast.arg, ast.AnnAssign)):
            annotation = child.annotation
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotation = child.returns
        if annotation is not None:
            ids.update(id(item) for item in ast.walk(annotation))
    return ids


def _origin_level(expr: ast.AST, aliases: dict[str, str], origins: dict[str, str]) -> str:
    """Perkiraan asal nilai: ``production``, ``local``, atau ``unknown``."""
    if isinstance(expr, ast.Name):
        if expr.id in {"self", "cls"}:
            return "local"
        if expr.id in origins:
            return origins[expr.id]
        full = aliases.get(expr.id)
        if full is not None:
            return "production" if _is_production_name(full) else "local"
        return "unknown"
    if isinstance(expr, ast.Attribute):
        full = _full_name(expr, aliases)
        if _is_production_name(full):
            return "production"
        return _origin_level(expr.value, aliases, origins)
    if isinstance(expr, ast.Call):
        full = _full_name(expr.func, aliases)
        return "production" if _is_production_name(full) else "local"
    if isinstance(expr, ast.Subscript):
        return _origin_level(expr.value, aliases, origins)
    if isinstance(expr, ast.IfExp):
        left = _origin_level(expr.body, aliases, origins)
        right = _origin_level(expr.orelse, aliases, origins)
        return left if left == right else "unknown"
    if isinstance(
        expr,
        (
            ast.Constant,
            ast.Dict,
            ast.DictComp,
            ast.GeneratorExp,
            ast.List,
            ast.ListComp,
            ast.Set,
            ast.SetComp,
            ast.Tuple,
        ),
    ):
        return "local"
    return "unknown"


def _set_target_origins(target: ast.AST, origin: str, origins: dict[str, str]) -> None:
    """Catat asal nilai untuk target assignment sederhana."""
    if isinstance(target, ast.Name):
        origins[target.id] = origin
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            _set_target_origins(element, origin, origins)
    elif isinstance(target, ast.Starred):
        _set_target_origins(target.value, origin, origins)


def _binding_origins(test: _Test) -> dict[str, str]:
    """Petakan nama lokal test ke perkiraan asal nilainya."""
    origins: dict[str, str] = {"self": "local", "cls": "local"}
    for node in ast.walk(test.node):
        if not isinstance(node, ast.arg):
            continue
        annotation = node.annotation
        if annotation is None:
            origins.setdefault(node.arg, "unknown")
            continue
        name = _full_name(annotation, test.aliases)
        origins[node.arg] = "production" if _is_production_name(name) else "local"

    body_nodes = list(_walk_body(test))
    statements = sorted(
        (
            node
            for node in body_nodes
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.For, ast.AsyncFor))
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )
    for node in statements:
        if isinstance(node, ast.Assign):
            origin = _origin_level(node.value, test.aliases, origins)
            for target in node.targets:
                _set_target_origins(target, origin, origins)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            origin = _origin_level(node.value, test.aliases, origins)
            _set_target_origins(node.target, origin, origins)
        elif isinstance(node, ast.NamedExpr):
            _set_target_origins(
                node.target, _origin_level(node.value, test.aliases, origins), origins
            )
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            origin = _origin_level(node.iter, test.aliases, origins)
            _set_target_origins(node.target, origin, origins)
    for node in body_nodes:
        if not isinstance(node, ast.comprehension):
            continue
        origin = _origin_level(node.iter, test.aliases, origins)
        _set_target_origins(node.target, origin, origins)
    return origins


def _private_access_level(test: _Test) -> str | None:
    """Tingkat keyakinan akses privat ke kode produksi, atau None bila tidak ada."""
    aliases = test.aliases
    bound = _bound_names(test)
    origins = _binding_origins(test)
    annotations = _annotation_node_ids(test.node)
    level: str | None = None
    for node in _walk_body(test):
        if id(node) in annotations:
            continue
        if isinstance(node, ast.Attribute) and _private_name(node.attr):
            full = _full_name(node, aliases)
            if _is_production_name(full):
                level = _stronger_level(level, "medium")
            else:
                origin = _origin_level(node.value, aliases, origins)
                if origin == "production":
                    level = _stronger_level(level, "medium")
                elif origin == "unknown":
                    level = _stronger_level(level, "low")
        elif isinstance(node, ast.Name) and _private_name(node.id):
            if node.id in bound or node.id in test.local_private:
                continue
            if _production_private_alias(node.id, aliases) or origins.get(node.id) == "production":
                level = _stronger_level(level, "medium")
    return level


def _stronger_level(current: str | None, candidate: str) -> str:
    """Pilih level keyakinan yang lebih tinggi."""
    if current is None or CONFIDENCE_RANK[candidate] > CONFIDENCE_RANK[current]:
        return candidate
    return current


def _mentions_error_code(expr: ast.AST) -> bool:
    """True bila ekspresi assertion menyebut kode error atau return code."""
    for node in ast.walk(expr):
        if isinstance(node, ast.Attribute) and node.attr in ERROR_CODE_NAMES:
            return True
        if isinstance(node, ast.Name) and node.id in ERROR_CODE_NAMES:
            return True
        if isinstance(node, ast.Subscript):
            key = node.slice
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value in ERROR_CODE_NAMES
            ):
                return True
    return False


def _is_broad_exception(expr: ast.AST) -> bool:
    """True bila argumen pytest.raises memakai exception yang terlalu luas."""
    if isinstance(expr, ast.Name):
        return expr.id in BROAD_EXCEPTIONS
    if isinstance(expr, ast.Attribute):
        return expr.attr in BROAD_EXCEPTIONS
    return False


def _has_broad_raises(test: _Test) -> bool:
    """True bila pytest.raises luas tanpa match dan tanpa assertion kode error."""
    broad = False
    for node in _walk_body(test):
        if not isinstance(node, ast.Call):
            continue
        if _full_name(node.func, test.aliases) != "pytest.raises":
            continue
        if any(keyword.arg == "match" for keyword in node.keywords):
            continue
        if node.args and _is_broad_exception(node.args[0]):
            broad = True
    if not broad:
        return False
    return not any(
        _mentions_error_code(node.test) for node in _walk_body(test) if isinstance(node, ast.Assert)
    )


def _is_code_expr(expr: ast.AST) -> bool:
    """True bila ekspresi membaca code, returncode, atau exit_code."""
    if isinstance(expr, ast.Name):
        return expr.id in ERROR_CODE_NAMES
    if isinstance(expr, ast.Attribute):
        return expr.attr in ERROR_CODE_NAMES
    if isinstance(expr, ast.Subscript):
        key = expr.slice
        return (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and key.value in ERROR_CODE_NAMES
        )
    return False


def _is_number(expr: ast.AST) -> bool:
    """True untuk literal angka, termasuk angka negatif."""
    if isinstance(expr, ast.Constant):
        return isinstance(expr.value, (int, float)) and not isinstance(expr.value, bool)
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, (ast.USub, ast.UAdd)):
        return _is_number(expr.operand)
    return False


def _is_code_comparison(expr: ast.AST) -> bool:
    """True bila Compare hanya membandingkan kode dengan angka."""
    if not isinstance(expr, ast.Compare):
        return False
    previous = expr.left
    for operator, comparator in zip(expr.ops, expr.comparators, strict=True):
        if not isinstance(operator, COMPARISON_OPS):
            return False
        code_left = _is_code_expr(previous)
        code_right = _is_code_expr(comparator)
        number_left = _is_number(previous)
        number_right = _is_number(comparator)
        if not ((code_left and number_right) or (number_left and code_right)):
            return False
        previous = comparator
    return True


def _is_code_only_expr(expr: ast.AST) -> bool:
    """True bila assertion hanya berisi perbandingan kode dengan angka."""
    if _is_code_comparison(expr):
        return True
    if isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.And):
        return all(_is_code_only_expr(value) for value in expr.values)
    return False


def _has_exit_code_only(test: _Test) -> bool:
    """True bila semua assertion hanya membandingkan exit code dengan angka."""
    assertions = [node for node in _walk_body(test) if isinstance(node, ast.Assert)]
    return bool(assertions) and all(_is_code_only_expr(node.test) for node in assertions)


class _StringCollector(ast.NodeVisitor):
    """Kumpulkan literal string di body tanpa mengambil docstring atau string lepas."""

    def __init__(self) -> None:
        self.values: list[str] = []

    def visit_Expr(self, node: ast.Expr) -> None:
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.values.append(node.value)


def _string_constants(test: _Test) -> list[str]:
    """Kembalikan literal string yang dipakai di body test."""
    collector = _StringCollector()
    for statement in test.body:
        collector.visit(statement)
    return collector.values


def _constants_in(node: ast.AST) -> list[str]:
    """Kembalikan literal string di dalam satu node AST."""
    collector = _StringCollector()
    collector.visit(node)
    return collector.values


def _is_snapshot_value(value: str) -> bool:
    """True bila string tampak seperti snapshot panjang, XML, atau JSON."""
    if len(value) > 200 or "<w:" in value or "<?xml" in value:
        return True
    stripped = value.lstrip()
    return stripped.startswith(("{", "[")) and len(value) > 100


def _snapshot_variable(name: str) -> bool:
    """True untuk variabel expected/snapshot yang lazim menampung snapshot."""
    lower = name.lower()
    return lower in {"expected", "snapshot"} or lower.startswith(("expected_", "snapshot_"))


def _value_string_nodes(expr: ast.AST, test: _Test) -> list[ast.Constant]:
    """Kembalikan literal yang menjadi nilai assertion, bukan argumen input."""
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return [expr]
    if isinstance(expr, ast.BoolOp):
        result: list[ast.Constant] = []
        for value in expr.values:
            result.extend(_value_string_nodes(value, test))
        return result
    if isinstance(expr, ast.UnaryOp):
        return _value_string_nodes(expr.operand, test)
    if isinstance(expr, ast.Compare):
        result = _value_string_nodes(expr.left, test)
        for comparator in expr.comparators:
            result.extend(_value_string_nodes(comparator, test))
        return result
    if isinstance(expr, ast.IfExp):
        return [
            *_value_string_nodes(expr.body, test),
            *_value_string_nodes(expr.orelse, test),
        ]
    if isinstance(expr, ast.BinOp):
        return [
            *_value_string_nodes(expr.left, test),
            *_value_string_nodes(expr.right, test),
        ]
    if isinstance(expr, (ast.List, ast.Set, ast.Tuple)):
        result = []
        for element in expr.elts:
            result.extend(_value_string_nodes(element, test))
        return result
    if isinstance(expr, ast.Call) and _is_assertion_call(expr, test.aliases):
        result = []
        for argument in [*expr.args, *(keyword.value for keyword in expr.keywords)]:
            result.extend(_value_string_nodes(argument, test))
        return result
    return []


def _assertion_text_nodes(test: _Test) -> tuple[list[ast.Constant], set[str]]:
    """Kumpulkan literal nilai dan nama yang dipakai dalam assertion."""
    literals: list[ast.Constant] = []
    names: set[str] = set()
    for node in _walk_body(test):
        if isinstance(node, ast.Assert):
            literals.extend(_value_string_nodes(node.test, test))
            names.update(child.id for child in ast.walk(node.test) if isinstance(child, ast.Name))
            continue
        if not isinstance(node, ast.Call):
            continue
        assertion = _is_assertion_call(node, test.aliases)
        if not assertion and not _is_helper_call(node, test):
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            if assertion:
                literals.extend(_value_string_nodes(argument, test))
            names.update(child.id for child in ast.walk(argument) if isinstance(child, ast.Name))
    return literals, names


def _snapshot_assignments(test: _Test) -> dict[str, list[ast.Constant]]:
    """Petakan variabel expected/snapshot ke literal nilai assignment-nya."""
    assigned: dict[str, list[ast.Constant]] = {}
    for node in _walk_body(test):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and _snapshot_variable(target.id):
                assigned.setdefault(target.id, []).extend(_value_string_nodes(value, test))
    return assigned


def _has_exact_snapshot(test: _Test) -> bool:
    """True bila snapshot literal benar-benar dipakai dalam assertion.

    Literal XML/JSON yang hanya menjadi input ke fungsi, package, atau fixture
    tidak dihitung sebagai snapshot output.
    """
    literals, asserted_names = _assertion_text_nodes(test)
    for name, values in _snapshot_assignments(test).items():
        if name in asserted_names:
            literals.extend(values)
    return any(_is_snapshot_value(node.value) for node in literals)


def _is_absolute_path(value: str) -> bool:
    """True bila string tampak seperti path absolut Windows atau Unix tertentu."""
    stripped = value.strip()
    if len(stripped) >= 3 and stripped[0].isalpha() and stripped[1] == ":" and stripped[2] in "\\/":
        return True
    return stripped in {"/home", "/tmp"} or stripped.startswith(("/home/", "/tmp/"))


def _is_environ_store(target: ast.AST, aliases: dict[str, str]) -> bool:
    """True bila target assignment menulis ke os.environ."""
    if isinstance(target, ast.Name):
        return _full_name(target, aliases) == "os.environ"
    if isinstance(target, ast.Subscript):
        return _full_name(target.value, aliases) in {"os.environ", "os.environb"}
    return False


def _has_env_write(test: _Test) -> bool:
    """True bila test menulis atau mengubah os.environ secara langsung."""
    for node in _walk_body(test):
        if isinstance(node, ast.Assign):
            if any(_is_environ_store(target, test.aliases) for target in node.targets):
                return True
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if _is_environ_store(node.target, test.aliases):
                return True
        elif isinstance(node, ast.Delete):
            if any(_is_environ_store(target, test.aliases) for target in node.targets):
                return True
        elif isinstance(node, ast.Call) and _full_name(node.func, test.aliases) in ENV_WRITE_CALLS:
            return True
    return False


def _uses_monkeypatch(test: _Test) -> bool:
    """True bila test memakai fixture atau objek monkeypatch."""
    arguments = [
        *test.node.args.posonlyargs,
        *test.node.args.args,
        *test.node.args.kwonlyargs,
    ]
    if any("monkeypatch" in argument.arg.lower() for argument in arguments):
        return True
    for node in _walk_body(test):
        if isinstance(node, ast.Name) and "monkeypatch" in node.id.lower():
            return True
        if isinstance(node, ast.Call):
            name = _full_name(node.func, test.aliases).lower()
            if "monkeypatch" in name:
                return True
    return False


def _has_env_dependency(test: _Test) -> bool:
    """True bila test bergantung pada waktu, random, jaringan, path, atau env."""
    for node in _walk_body(test):
        if isinstance(node, ast.Call):
            name = _full_name(node.func, test.aliases)
            if name in {"time.sleep", "time.time"}:
                return True
            if name.startswith(("random.", "socket.", "requests.", "urllib.")):
                return True
            if name.endswith(".now") and "datetime" in name.split("."):
                return True
    for value in _string_constants(test):
        if _is_absolute_path(value):
            return True
    return _has_env_write(test) and not _uses_monkeypatch(test)


def _skipif_condition(decorator: ast.AST, aliases: dict[str, str]) -> ast.AST | None:
    """Ambil ekspresi kondisi dari dekorator pytest.mark.skipif."""
    if not isinstance(decorator, ast.Call):
        return None
    if _full_name(decorator.func, aliases) != "pytest.mark.skipif":
        return None
    if decorator.args:
        return decorator.args[0]
    for keyword in decorator.keywords:
        if keyword.arg == "condition":
            return keyword.value
    return None


def _platform_condition_only(expr: ast.AST, aliases: dict[str, str]) -> bool:
    """True bila kondisi skip hanya memakai sys.platform atau os.name."""
    found = False
    other = False
    for node in ast.walk(expr):
        if isinstance(node, ast.Attribute):
            name = _full_name(node, aliases)
            if name in {"sys.platform", "os.name"} or name.startswith("sys.platform."):
                found = True
            elif name:
                other = True
        elif isinstance(node, ast.Name):
            name = _full_name(node, aliases)
            if name in {"sys", "os"}:
                continue
            if name in {"sys.platform", "os.name"}:
                found = True
            else:
                other = True
    return found and not other


def _has_platform_skip_only(test: _Test) -> bool:
    """True bila test hanya di-skip berdasarkan platform atau os.name."""
    for decorator in test.decorators:
        condition = _skipif_condition(decorator, test.aliases)
        if condition is not None and _platform_condition_only(condition, test.aliases):
            return True
    return False


def _in_unit(path: Path) -> bool:
    """True bila path berada di bawah tests/unit."""
    parts = [part.lower() for part in path.resolve().parts]
    return any(
        parts[index] == "tests" and parts[index + 1] == "unit" for index in range(len(parts) - 1)
    )


def _looks_like_program(value: str, program: str) -> bool:
    """True bila string tampak memanggil program atau path executable-nya."""
    text = value.strip().strip("\"'")
    if not text:
        return False
    name = text.rsplit("/", 1)[-1]
    if name in {program, f"{program}.exe"}:
        return True
    first = text.split(None, 1)[0]
    first_name = first.rsplit("/", 1)[-1]
    return first_name in {program, f"{program}.exe"}


def _is_examples_value(value: str) -> bool:
    """True bila string menunjuk ke direktori examples repo."""
    normalized = value.strip().replace("\\", "/").lower()
    return (
        normalized == "examples"
        or normalized.startswith("examples/")
        or normalized.endswith("/examples")
        or "/examples/" in normalized
    )


def _is_process_exec(name: str) -> bool:
    """True hanya untuk API eksekusi proses nyata, bukan exception atau import."""
    lower = name.lower()
    return lower in SUBPROCESS_EXEC_NAMES or lower in OS_EXEC_NAMES


def _process_api_patched(test: _Test) -> bool:
    """True bila test mengganti API subprocess/os dengan fake."""
    process_apis = SUBPROCESS_EXEC_NAMES | OS_EXEC_NAMES
    for node in _walk_body(test):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and _full_name(target, test.aliases).lower() in process_apis
                ):
                    return True
        elif isinstance(node, ast.Call):
            name = _full_name(node.func, test.aliases)
            if name in {"mock.patch", "mocker.patch"} and node.args:
                target = node.args[0]
                if (
                    isinstance(target, ast.Constant)
                    and isinstance(target.value, str)
                    and target.value.lower() in process_apis
                ):
                    return True
            if name != "monkeypatch.setattr" or len(node.args) < 2:
                continue
            target = _full_name(node.args[0], test.aliases).lower()
            attribute = node.args[1]
            if (
                isinstance(attribute, ast.Constant)
                and isinstance(attribute.value, str)
                and f"{target}.{attribute.value.lower()}" in process_apis
            ):
                return True
    return False


def _real_program_names(test: _Test) -> dict[str, str]:
    """Petakan variabel hasil ``shutil.which`` ke program nyata."""
    programs: dict[str, str] = {}
    for node in _walk_body(test):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue
        if (
            not isinstance(value, ast.Call)
            or _full_name(value.func, test.aliases).lower() != "shutil.which"
        ):
            continue
        if not value.args or not isinstance(value.args[0], ast.Constant):
            continue
        program = value.args[0].value
        if not isinstance(program, str):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                for candidate in ("mmdc", "pandoc"):
                    if _looks_like_program(program, candidate):
                        programs[target.id] = candidate
    return programs


def _integration_reasons(test: _Test) -> list[str]:
    """Kembalikan alasan test unit menyentuh boundary integration nyata."""
    if not _in_unit(test.path):
        return []
    process_patched = _process_api_patched(test)
    real_programs = _real_program_names(test)
    reasons: set[str] = set()
    for node in _walk_body(test):
        if not isinstance(node, ast.Call):
            continue
        name = _full_name(node.func, test.aliases)
        lower = name.lower()
        last = lower.rsplit(".", 1)[-1]
        strings = _constants_in(node)
        process_exec = _is_process_exec(lower)
        if process_exec and not process_patched:
            reasons.add("subprocess")
            if any(_looks_like_program(value, "mmdc") for value in strings):
                reasons.add("mmdc")
            if any(_looks_like_program(value, "pandoc") for value in strings):
                reasons.add("pandoc")
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id in real_programs:
                    reasons.add(real_programs[child.id])
        if not process_patched:
            for keyword in node.keywords:
                if (
                    keyword.arg in {"mmdc", "pandoc"}
                    and isinstance(keyword.value, ast.Name)
                    and keyword.value.id in real_programs
                ):
                    reasons.add(real_programs[keyword.value.id])
        if any(token in lower for token in ("win32com", "pythoncom", "comtypes")) and (
            last in COM_CALL_NAMES or any("word.application" in value.lower() for value in strings)
        ):
            reasons.add("Word COM")
        reader = (
            last in READ_CALL_NAMES
            or last.startswith(("read_", "load_", "open_"))
            or last in {"load_fixture", "baca"}
        )
        if reader and any(_is_examples_value(value) for value in strings):
            reasons.add("examples/")
    return sorted(reasons)


def _detect_signals(test: _Test, duplicate_of: str | None) -> tuple[dict[str, str], dict[str, str]]:
    """Kembalikan sinyal, bukti singkat, dan override keyakinan per sinyal."""
    signals: dict[str, str] = {}
    confidences: dict[str, str] = {}
    if _has_no_assert(test):
        signals["no_assert"] = (
            "test tidak memiliki assert, pytest.raises/warns/fail, atau assert unittest"
        )
    if _has_tautology(test):
        signals["tautology"] = (
            "assert membandingkan ekspresi dengan dirinya sendiri atau konstanta selalu benar"
        )
    if _has_expected_from_sut(test):
        signals["expected_from_sut"] = (
            "expected diisi dari pemanggilan SUT yang sama dengan yang diuji"
        )
    if _has_existence_only(test):
        signals["existence_only"] = (
            "seluruh assertion hanya memeriksa keberadaan atau tipe, bukan nilai"
        )
    if duplicate_of is not None:
        signals["duplicate_body"] = (
            f"body test identik dengan {duplicate_of} setelah docstring dibuang"
        )
    private_level = _private_access_level(test)
    if private_level is not None:
        signals["private_access"] = (
            "test mengakses atribut, nama, atau import privat dari kode produksi"
        )
        confidences["private_access"] = private_level
    if _has_broad_raises(test):
        signals["broad_raises"] = (
            "pytest.raises memakai exception luas tanpa match atau assertion kode error"
        )
    if _has_exit_code_only(test):
        signals["exit_code_only"] = "seluruh assertion hanya membandingkan exit code dengan angka"
    if _has_exact_snapshot(test):
        signals["exact_snapshot"] = "test menyimpan snapshot literal panjang, XML, atau JSON"
    if _has_env_dependency(test):
        signals["env_dependent"] = (
            "test bergantung pada waktu, random, jaringan, path absolut, atau os.environ"
        )
    if _has_platform_skip_only(test):
        signals["platform_skip_only"] = "skip hanya berdasarkan sys.platform atau os.name"
    reasons = _integration_reasons(test)
    if reasons:
        signals["integration_in_unit"] = (
            f"test unit memakai {', '.join(reasons)} yang seharusnya diuji di integration"
        )
    return signals, confidences


def _make_finding(
    test: _Test,
    signals: dict[str, str],
    confidences: dict[str, str],
    duplicate_of: str | None,
) -> dict[str, Any]:
    """Susun satu finding output dari sinyal yang ditemukan."""
    if not signals:
        return {
            "id": test.id,
            "file": test.file,
            "line": test.line,
            "verdict": "KEEP",
            "confidence": "high",
            "signals": [],
            "evidence": "tidak ada sinyal kelemahan",
            "suggested_action": "Tidak ada tindakan; pertahankan test.",
            "duplicate_of": None,
        }
    verdict = next(
        order
        for order in SEVERITY_ORDER
        if any(SIGNAL_VERDICT[signal] == order for signal in signals)
    )
    effective = {signal: confidences.get(signal, SIGNAL_CONFIDENCE[signal]) for signal in signals}
    matching = [signal for signal in signals if SIGNAL_VERDICT[signal] == verdict]
    confidence_signal = max(matching, key=lambda signal: CONFIDENCE_RANK[effective[signal]])
    actions: list[str] = []
    for signal in signals:
        action = SIGNAL_ACTION[signal]
        if action not in actions:
            actions.append(action)
    return {
        "id": test.id,
        "file": test.file,
        "line": test.line,
        "verdict": verdict,
        "confidence": effective[confidence_signal],
        "signals": list(signals),
        "evidence": "; ".join(signals.values()) + ".",
        "suggested_action": "; ".join(actions) + ".",
        "duplicate_of": duplicate_of if "duplicate_body" in signals else None,
    }


def periksa(paths: list[str] | None = None) -> dict[str, Any]:
    """Pindai path dan kembalikan payload hasil pemeriksaan."""
    tests = scan(paths)
    duplicates = _duplicate_map(tests)
    findings: list[dict[str, Any]] = []
    for test in tests:
        duplicate_of = duplicates.get(test.id)
        signals, confidences = _detect_signals(test, duplicate_of)
        findings.append(_make_finding(test, signals, confidences, duplicate_of))
    summary: dict[str, int] = {"total": len(findings)}
    for verdict in VERDICT_ORDER:
        summary[verdict] = sum(1 for finding in findings if finding["verdict"] == verdict)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "summary": summary,
        "tests": findings,
    }


def render_json(payload: dict[str, Any]) -> str:
    """Render payload sebagai JSON deterministik."""
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _markdown_cell(value: object) -> str:
    """Escape isi sel tabel Markdown."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(payload: dict[str, Any]) -> str:
    """Render payload sebagai ringkasan dan tabel Markdown."""
    summary = payload["summary"]
    tests = payload["tests"]
    lines = [
        "# Ringkasan Kualitas Test",
        "",
        f"Total test: {summary['total']}",
        "",
        "| Verdict | Jumlah |",
        "| --- | ---: |",
    ]
    for verdict in VERDICT_ORDER:
        lines.append(f"| {verdict} | {summary[verdict]} |")
    lines.extend(
        [
            "",
            "## Tabel Temuan",
            "",
            "| file:line | test | verdict | confidence | signals | action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for test in tests:
        test_id = str(test["id"])
        label = test_id.split("::", 1)[1] if "::" in test_id else test_id
        signals = ", ".join(test["signals"]) if test["signals"] else "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(f"{test['file']}:{test['line']}"),
                    _markdown_cell(label),
                    _markdown_cell(test["verdict"]),
                    _markdown_cell(test["confidence"]),
                    _markdown_cell(signals),
                    _markdown_cell(test["suggested_action"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _threshold_hit(payload: dict[str, Any], threshold: str) -> bool:
    """True bila ada finding non-KEEP pada atau di atas level keyakinan."""
    limit = CONFIDENCE_RANK[threshold]
    for test in payload["tests"]:
        if test["verdict"] == "KEEP":
            continue
        if CONFIDENCE_RANK[test["confidence"]] >= limit:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    """Jalankan checker dan kembalikan kode keluar."""
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
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="format keluaran; default json",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="tulis hasil ke berkas, bukan stdout",
    )
    parser.add_argument(
        "--fail-on",
        choices=("high", "medium", "low"),
        help="level keyakinan minimum yang memicu kode keluar 1",
    )
    args = parser.parse_args(argv)
    try:
        payload = periksa(args.paths or None)
    except FileNotFoundError as exc:
        print(f"path tidak ditemukan: {exc}", file=sys.stderr)
        return 2
    text = render_markdown(payload) if args.format == "markdown" else render_json(payload)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.fail_on and _threshold_hit(payload, args.fail_on):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
