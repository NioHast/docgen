"""Validasi aset font PPTX dan penanda embedding final oleh CLI.

PowerPoint menyimpan font tertanam sebagai part ``.fntdata`` yang bukan TTF
mentah: format tersebut merupakan wrapper EOT/MicroType Express. Menulis byte
TTF langsung sebagai ``fntdata`` membuat PowerPoint meminta repair, jadi
renderer tidak menulis part font sendiri. Renderer hanya memvalidasi aset TTF
bundled; embedding final dilakukan setelah render oleh CLI melalui PowerPoint
COM (``SaveCopyAs`` format 24 dengan ``EmbedTrueTypeFonts=msoTrue``). Target
Slides tidak memakai embedding PPTX karena Google Slides memakai Google Fonts.
"""

import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from pptx.oxml.ns import qn

from autooffice.design.fonts import (
    FONT_FAMILY,
    FONT_FILES,
    FONT_HASHES,
    font_path,
    sha256,
)
from autooffice.design.theme import Theme

from .shapes import PptxRenderError, primary_typeface

EMBEDDED = "embedded"
DEFERRED = "deferred"
FONT_EMBEDDING_WARNING = (
    "font-embedding: renderer PPTX tidak menanam font; final PPTX/PDF ditanam "
    "oleh CLI memakai PowerPoint COM setelah render."
)


@dataclass(frozen=True, slots=True)
class FontEmbeddingResult:
    """Hasil post-processing font setelah PPTX disimpan."""

    status: str
    warnings: tuple[str, ...]
    font_files: tuple[str, ...]
    blocker: str | None


def font_files_for_theme(theme: Theme) -> tuple[Path, ...]:
    """Kembalikan empat TTF Plus Jakarta Sans yang dibundel package.

    Family token boleh berupa stack; yang diperiksa adalah typeface utamanya.
    Setiap berkas harus cocok dengan hash SHA-256 aset yang tercatat, bukan
    hanya memiliki header TrueType yang benar.
    """
    primary = primary_typeface(theme.typography.family)
    if primary != FONT_FAMILY:
        raise PptxRenderError(
            f"Theme memakai font '{theme.typography.family}'; aset tertanam hanya "
            f"tersedia untuk '{FONT_FAMILY}'."
        )
    paths: list[Path] = []
    for file_name in FONT_FILES:
        path = font_path(file_name)
        if not path.is_file():
            raise PptxRenderError(f"Aset font tidak ditemukan: {file_name}.")
        header = path.read_bytes()[:4]
        if header not in {b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"}:
            raise PptxRenderError(f"Aset font bukan TrueType/OpenType valid: {file_name}.")
        if sha256(path) != FONT_HASHES[file_name]:
            raise PptxRenderError(f"Aset font tidak cocok hash SHA-256: {file_name}.")
        paths.append(path)
    return tuple(paths)


def embedded_fonts(pptx_path: Path) -> tuple[str, ...]:
    """Baca nama family dari ``p:embeddedFontLst`` di presentation.xml."""
    with zipfile.ZipFile(pptx_path) as archive:
        try:
            data = archive.read("ppt/presentation.xml")
        except KeyError as error:
            raise PptxRenderError("PPTX tidak memiliki ppt/presentation.xml.") from error
    root = etree.fromstring(data)
    typefaces = [
        element.get("typeface", "")
        for element in root.iter(qn("p:font"))
        if element.get("typeface")
    ]
    return tuple(dict.fromkeys(typefaces))


def embed_fonts(pptx_path: Path, theme: Theme) -> FontEmbeddingResult:
    """Validasi aset font dan tandai embedding final sebagai tugas CLI."""
    if not pptx_path.is_file():
        raise PptxRenderError(f"PPTX untuk font embedding tidak ditemukan: {pptx_path}.")
    files = font_files_for_theme(theme)
    return FontEmbeddingResult(
        status=DEFERRED,
        warnings=(FONT_EMBEDDING_WARNING,),
        font_files=tuple(path.name for path in files),
        blocker=None,
    )
