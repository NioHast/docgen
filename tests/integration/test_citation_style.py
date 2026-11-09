"""Tes gaya sitasi author-date UNDIP MSI (turunan APA 7).

Menjalankan ``pandoc --citeproc`` pada tiga entri (1, 2, dan 3 penulis) dan
memastikan keluaran memakai ``(Nama, 2020)``/``Nama dan Nama, 2020``,
``dkk.`` untuk tiga penulis, serta daftar pustaka alfabetis tanpa nomor.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
CSL = ROOT / "src" / "docgen" / "data" / "formats" / "undip-msi" / "citation.csl"
PANDOC_DIR = Path(r"C:\Users\nioha\AppData\Local\Pandoc")

BIB = """\
@book{satu2020,
  author = {Solo, Samuel},
  title = {Satu Penulis},
  year = {2020},
  publisher = {Penerbit Satu}
}

@book{dua2020,
  author = {Alpha, Anna and Beta, Budi},
  title = {Dua Penulis},
  year = {2020},
  publisher = {Penerbit Dua}
}

@book{tiga2020,
  author = {Citra, Cahaya and Darma, Dedi and Eka, Erna},
  title = {Tiga Penulis},
  year = {2020},
  publisher = {Penerbit Tiga}
}
"""

MARKDOWN = """\
Satu penulis: [@satu2020].

Dua penulis: [@dua2020].

Tiga penulis: [@tiga2020].

Naratif dua: @dua2020.
"""


def _pandoc() -> tuple[str, dict[str, str]]:
    """Cari Pandoc di PATH, env, atau instalasi Windows pengguna."""
    env = os.environ.copy()
    search_path = env.get("PATH", "")
    if PANDOC_DIR.is_dir():
        search_path = str(PANDOC_DIR) + os.pathsep + search_path
    env["PATH"] = search_path

    candidates = [
        env.get("LAPORAN_PANDOC"),
        env.get("PANDOC"),
        shutil.which("pandoc", path=search_path),
    ]
    local_appdata = env.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(str(Path(local_appdata) / "Pandoc" / "pandoc.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate, env
    pytest.skip("pandoc tidak tersedia")


def test_citation_style_author_date_alfabetis(tmp_path: Path) -> None:
    pandoc, env = _pandoc()
    bibliography = tmp_path / "references.bib"
    bibliography.write_text(BIB, encoding="utf-8")
    markdown = tmp_path / "uji.md"
    markdown.write_text(MARKDOWN, encoding="utf-8")

    result = subprocess.run(
        [
            pandoc,
            str(markdown),
            "--citeproc",
            f"--bibliography={bibliography}",
            f"--csl={CSL}",
            "--metadata=lang=id-ID",
            "--metadata=reference-section-title=DAFTAR PUSTAKA",
            "-t",
            "plain",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout

    # Bukan gaya numerik IEEE.
    assert not re.search(r"\[\d+\]", output), output

    # Satu penulis, dua penulis ("dan"), tiga penulis ("dkk.").
    assert "(Solo, 2020)" in output, output
    assert "(Alpha dan Beta, 2020)" in output, output
    assert re.search(r"\(Citra,\s+dkk\.,\s+2020\)", output), output
    assert "Alpha dan Beta (2020)" in output, output

    # Daftar pustaka alfabetis dan tanpa label nomor.
    assert "DAFTAR PUSTAKA" in output, output
    bibliography_text = output.split("DAFTAR PUSTAKA", 1)[1]
    positions = [
        bibliography_text.index(name) for name in ("Alpha", "Citra", "Solo")
    ]
    assert positions == sorted(positions), bibliography_text
    assert not re.search(r"(?m)^\s*\[\d+\]", bibliography_text), bibliography_text

    # Ampersand dipertahankan di daftar pustaka (sesuai contoh-dp.txt).
    assert "Alpha, A., & Beta, B." in bibliography_text, bibliography_text
