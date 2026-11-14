"""Tes acceptance demo deck: build PPTX/PDF nyata dengan font tertanam."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from pptx import Presentation
from pypdf import PdfReader

from autooffice.cli.doctor import doctor_report

pytestmark = [pytest.mark.integration, pytest.mark.slow]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DECK_DIR = REPO_ROOT / "examples" / "demo-deck"
EXPECTED_SLIDES = 24
BUILD_TIMEOUT_S = 900
_ANIMATION_TAGS = frozenset({"timing", "transition"})
_PRESENTATIONML_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _skip_reason() -> str | None:
    """Alasan skip bila prasyarat COM/font demo deck tidak tersedia."""
    if sys.platform != "win32":
        return (
            "demo deck acceptance membutuhkan Windows, Microsoft PowerPoint, "
            f"dan font Plus Jakarta Sans; platform saat ini {sys.platform!r}"
        )
    checks = {check.name: check for check in doctor_report(("pptx", "pdf")).checks}
    missing = [
        f"{name}: {checks[name].detail}"
        for name in ("powerpoint", "pywin32", "font-assets", "fonts")
        if not checks[name].ok
    ]
    if missing:
        return "prasyarat build demo deck tidak tersedia: " + "; ".join(missing)
    return None


def _copy_demo_deck(destination: Path) -> Path:
    """Salin input demo deck ke direktori sementara tanpa cache build lama."""
    shutil.copytree(
        DEMO_DECK_DIR,
        destination,
        ignore=shutil.ignore_patterns(".autooffice*", "out"),
    )
    return destination / "deck.yaml"


def _run_build(deck_path: Path, out: Path) -> None:
    """Jalankan CLI build nyata untuk target pptx,pdf di direktori sementara."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "autooffice",
            "build",
            str(deck_path),
            "--target",
            "pptx,pdf",
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=BUILD_TIMEOUT_S,
        env=environment,
    )
    assert completed.returncode == 0, (
        "build demo deck gagal "
        f"(exit {completed.returncode})\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )


def _assert_pptx(pptx: Path) -> None:
    """PPTX dapat dibuka, 24 slide, font tertanam, dan tanpa animasi/transisi."""
    assert len(Presentation(str(pptx)).slides) == EXPECTED_SLIDES

    with ZipFile(pptx) as package:
        names = package.namelist()
        font_parts = [
            name
            for name in names
            if name.startswith("ppt/fonts/") and name.lower().endswith(".fntdata")
        ]
        assert font_parts, "PPTX tidak memuat part ppt/fonts/*.fntdata"
        empty_parts = [name for name in font_parts if package.getinfo(name).file_size == 0]
        assert not empty_parts, "part fntdata kosong: " + ", ".join(empty_parts)

        presentation = ElementTree.fromstring(package.read("ppt/presentation.xml"))
        embedded = presentation.find(f".//{{{_PRESENTATIONML_NS}}}embeddedFontLst")
        assert embedded is not None, "presentation.xml tidak memuat p:embeddedFontLst"
        typefaces = {
            font.get("typeface") for font in embedded.iter(f"{{{_PRESENTATIONML_NS}}}font")
        }
        assert "Plus Jakarta Sans" in typefaces, (
            "font tertanam tidak memuat Plus Jakarta Sans: " + ", ".join(sorted(typefaces))
        )

        offenders: list[str] = []
        for name in names:
            if not name.lower().endswith(".xml"):
                continue
            root = ElementTree.fromstring(package.read(name))
            for element in root.iter():
                local_name = element.tag.rsplit("}", 1)[-1]
                if local_name in _ANIMATION_TAGS:
                    offenders.append(f"{name}: {local_name}")
        assert not offenders, "PPTX memuat timing/transition: " + ", ".join(offenders)


def _assert_pdf(pdf: Path) -> None:
    """PDF diawali magic %PDF- dan berisi 24 halaman."""
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert len(PdfReader(str(pdf)).pages) == EXPECTED_SLIDES


def test_demo_deck_builds_pptx_pdf_with_embedded_fonts_and_transcript(
    tmp_path: Path,
) -> None:
    """Build demo deck nyata lalu verifikasi PPTX, PDF, dan transkrip."""
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)

    deck_path = _copy_demo_deck(tmp_path / "examples" / "demo-deck")
    out = tmp_path / "out"
    _run_build(deck_path, out)

    pptx = out / f"{deck_path.stem}.pptx"
    pdf = out / f"{deck_path.stem}.pdf"
    transcript = out / f"{deck_path.stem}.transcript.md"
    assert pptx.is_file(), f"PPTX tidak ditemukan: {pptx}"
    assert pdf.is_file(), f"PDF tidak ditemukan: {pdf}"
    assert transcript.is_file(), f"transcript tidak ditemukan: {transcript}"

    _assert_pptx(pptx)
    _assert_pdf(pdf)
    assert transcript.read_bytes() == (deck_path.parent / "transcripts.md").read_bytes()
