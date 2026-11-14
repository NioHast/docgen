#!/usr/bin/env python3
"""Gate lokal AutoOffice tanpa COM, Google live, atau jaringan.

Gate menjalankan langkah secara berurutan dan berhenti pada kegagalan pertama
yang memblokir. Semua perintah bersifat lokal: Ruff, mypy, pytest dengan
coverage, coverage policy berbasis risiko, import contracts, lock check, docs
checker, test-quality checker, pemeriksa path/package, checker style Python,
checker identifier, dan checker komentar. Tidak ada
langkah yang memanggil Word/PowerPoint COM, Google API, atau layanan eksternal.

Pemakaian:
    python tools/quality/gate.py
    python tools/quality/gate.py --list
    python tools/quality/gate.py --dry-run docs test-quality
    python tools/quality/gate.py lint types tests

Kode keluar mengikuti kode langkah pertama yang memblokir gagal, atau 0 bila
semua langkah yang memblokir lulus. Dengan ``--keep-going`` semua langkah tetap
dijalankan, tetapi kode kegagalan pertama tetap dikembalikan.
"""

import argparse
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Step:
    """Satu langkah gate yang dapat dijalankan atau ditampilkan."""

    name: str
    description: str
    command: tuple[str, ...]
    blocking: bool = True


def build_steps() -> tuple[Step, ...]:
    """Daftar langkah gate deterministik, semuanya offline."""
    return (
        Step(
            "format",
            "Ruff format check tanpa menulis berkas",
            ("uv", "run", "ruff", "format", "--check", "."),
        ),
        Step("lint", "Ruff lint untuk seluruh repo", ("uv", "run", "ruff", "check", ".")),
        Step("types", "Mypy untuk paket AutoOffice", ("uv", "run", "mypy", "src/autooffice")),
        Step("imports", "Import contracts via lint-imports", ("uv", "run", "lint-imports")),
        Step(
            "tests",
            "Pytest dengan coverage line dan branch",
            (
                "uv",
                "run",
                "pytest",
                "-q",
                "--cov=autooffice",
                "--cov-branch",
                "--cov-fail-under=90",
            ),
        ),
        Step(
            "coverage-policy",
            "Kebijakan coverage berbasis risiko: global 90, kritis 100, adapter 85",
            ("uv", "run", "python", "tools/quality/check_coverage.py"),
        ),
        Step("lock", "Pastikan uv.lock mutakhir tanpa menulis", ("uv", "lock", "--check")),
        Step(
            "docs",
            "Docs checker read-only",
            ("uv", "run", "python", "tools/quality/check_docs.py"),
        ),
        Step(
            "test-quality",
            "Test-quality checker statis",
            ("uv", "run", "python", "tools/quality/check_tests.py"),
        ),
        Step(
            "no-legacy",
            "Pemeriksa path, package, dan teknologi legacy",
            ("uv", "run", "python", "tools/quality/check_no_legacy.py"),
        ),
        Step(
            "python-style",
            "Checker gaya Python 3.15 untuk future import dan API deprecated",
            ("uv", "run", "python", "tools/quality/check_python.py"),
            blocking=True,
        ),
        Step(
            "identifiers",
            "Checker identifier Inggris untuk definisi dan referensi",
            ("uv", "run", "python", "tools/quality/check_identifiers.py"),
            blocking=True,
        ),
        Step(
            "source-style",
            "Checker komentar dan docstring bebas bahasa rencana atau riwayat",
            ("uv", "run", "python", "tools/quality/check_source_style.py"),
            blocking=True,
        ),
    )


def step_names(steps: Sequence[Step] | None = None) -> tuple[str, ...]:
    """Nama langkah dalam urutan eksekusi."""
    return tuple(step.name for step in (steps or build_steps()))


def select_steps(names: Sequence[str], steps: Sequence[Step] | None = None) -> tuple[Step, ...]:
    """Pilih langkah sesuai nama, mempertahankan urutan gate."""
    available = steps or build_steps()
    selected = set(names)
    if not selected:
        return tuple(available)
    result = tuple(step for step in available if step.name in selected)
    unknown = sorted(selected - set(step_names(available)))
    if unknown:
        raise ValueError(f"langkah tidak dikenal: {', '.join(unknown)}")
    return result


def format_command(step: Step) -> str:
    """Render perintah sebagai satu baris shell yang stabil."""
    return shlex.join(step.command)


def run_steps(
    steps: Sequence[Step],
    root: Path = REPO_ROOT,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    keep_going: bool = False,
) -> int:
    """Jalankan langkah dan kembalikan kode keluar pertama yang memblokir gagal."""
    first_failure: int | None = None
    for step in steps:
        print(f"[gate] {step.name}: {format_command(step)}", flush=True)
        completed = runner(step.command, cwd=root)
        code = int(completed.returncode)
        if code != 0:
            status = "GAGAL" if step.blocking else "PERINGATAN"
            print(f"[gate] {status}: {step.name} (exit {code})", flush=True)
            if step.blocking:
                if not keep_going:
                    return code
                if first_failure is None:
                    first_failure = code
            continue
    return 0 if first_failure is None else first_failure


def build_parser(steps: Sequence[Step] | None = None) -> argparse.ArgumentParser:
    """Bangun parser gate; tidak menjalankan apa pun saat dibuat."""
    available = steps or build_steps()
    parser = argparse.ArgumentParser(
        prog="gate.py",
        description="Gate lokal AutoOffice tanpa COM, Google live, atau jaringan.",
    )
    parser.add_argument(
        "steps",
        nargs="*",
        choices=step_names(available),
        metavar="STEP",
        help="langkah yang dijalankan; default semua",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_steps",
        help="cetak nama dan deskripsi langkah",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="cetak perintah tanpa menjalankannya",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="lanjutkan langkah berikutnya walau ada yang gagal",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="akar repo tempat perintah dijalankan",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Jalankan gate dan kembalikan kode keluar tanpa sys.exit."""
    parser = build_parser()
    args = parser.parse_args(argv)
    steps = select_steps(args.steps)
    if args.list_steps:
        for step in steps:
            print(f"{step.name:14} {step.description}")
        return 0
    if args.dry_run:
        for step in steps:
            print(format_command(step))
        return 0
    return run_steps(steps, args.root, keep_going=args.keep_going)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
