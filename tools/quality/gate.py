#!/usr/bin/env python3
"""Gate lokal AutoOffice tanpa COM, Google live, atau jaringan.

Gate menjalankan langkah secara berurutan dan berhenti pada kegagalan pertama
yang memblokir. Semua perintah bersifat lokal: Ruff, mypy, pytest dengan
coverage, coverage policy berbasis risiko, import contracts, lock check, docs
checker, test-quality checker, daftar no-legacy, dan style checker. Tidak ada
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

AKAR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Step:
    """Satu langkah gate yang dapat dijalankan atau ditampilkan."""

    nama: str
    deskripsi: str
    perintah: tuple[str, ...]
    memblokir: bool = True


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
            "Daftar target legacy yang dilarang",
            ("uv", "run", "python", "tools/quality/check_no_legacy.py", "--list"),
        ),
        Step(
            "python-style",
            "Checker gaya Python 3.15 untuk future import dan API deprecated",
            ("uv", "run", "python", "tools/quality/check_python.py"),
            memblokir=True,
        ),
    )


def step_names(steps: Sequence[Step] | None = None) -> tuple[str, ...]:
    """Nama langkah dalam urutan eksekusi."""
    return tuple(step.nama for step in (steps or build_steps()))


def select_steps(names: Sequence[str], steps: Sequence[Step] | None = None) -> tuple[Step, ...]:
    """Pilih langkah sesuai nama, mempertahankan urutan gate."""
    tersedia = steps or build_steps()
    dipilih = set(names)
    if not dipilih:
        return tuple(tersedia)
    hasil = tuple(step for step in tersedia if step.nama in dipilih)
    tidak_dikenal = sorted(dipilih - set(step_names(tersedia)))
    if tidak_dikenal:
        raise ValueError(f"langkah tidak dikenal: {', '.join(tidak_dikenal)}")
    return hasil


def format_command(step: Step) -> str:
    """Render perintah sebagai satu baris shell yang stabil."""
    return shlex.join(step.perintah)


def run_steps(
    steps: Sequence[Step],
    root: Path = AKAR,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    keep_going: bool = False,
) -> int:
    """Jalankan langkah dan kembalikan kode keluar pertama yang memblokir gagal."""
    kegagalan_pertama: int | None = None
    for step in steps:
        print(f"[gate] {step.nama}: {format_command(step)}", flush=True)
        completed = runner(step.perintah, cwd=root)
        kode = int(completed.returncode)
        if kode != 0:
            status = "GAGAL" if step.memblokir else "PERINGATAN"
            print(f"[gate] {status}: {step.nama} (exit {kode})", flush=True)
            if step.memblokir:
                if not keep_going:
                    return kode
                if kegagalan_pertama is None:
                    kegagalan_pertama = kode
            continue
    return 0 if kegagalan_pertama is None else kegagalan_pertama


def build_parser(steps: Sequence[Step] | None = None) -> argparse.ArgumentParser:
    """Bangun parser gate; tidak menjalankan apa pun saat dibuat."""
    tersedia = steps or build_steps()
    parser = argparse.ArgumentParser(
        prog="gate.py",
        description="Gate lokal AutoOffice tanpa COM, Google live, atau jaringan.",
    )
    parser.add_argument(
        "steps",
        nargs="*",
        choices=step_names(tersedia),
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
        default=AKAR,
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
            print(f"{step.nama:14} {step.deskripsi}")
        return 0
    if args.dry_run:
        for step in steps:
            print(format_command(step))
        return 0
    return run_steps(steps, args.root, keep_going=args.keep_going)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
