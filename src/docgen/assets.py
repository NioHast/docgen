"""Resolusi aset yang dirujuk dokumen.

Aturan path mengikuti kontrak: relatif terhadap direktori ``document.md``,
memakai ``/``, tidak boleh absolut atau keluar direktori. Glosarium pengguna
di ``<dir dokumen>/istilah.tsv`` mengalahkan glosarium paket.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import paths as path_mod
from .config import Format, Structure
from .errors import AssetError

_FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)*?\1")
_IMAGE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\(\s*"
    r"(?P<dest><[^>]*>|[^)\s]+)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)


@dataclass(frozen=True)
class ImageReference:
    line: int
    alt: str
    destination: str
    path: Path


@dataclass(frozen=True)
class Assets:
    document_dir: Path
    images_dir: Path
    images_dir_exists: bool
    bibliography: Path | None
    glossary: Path
    glossary_is_override: bool
    templates_dir: Path
    images: tuple[ImageReference, ...] = ()


def masked_lines(text: str) -> list[str]:
    """Samarkan fenced code dan inline code sebelum memindai Markdown."""

    masked: list[str] = []
    fence_character = ""
    fence_length = 0
    in_fence = False
    for line in text.splitlines():
        if in_fence:
            stripped = line.lstrip()
            if (
                stripped
                and stripped[0] == fence_character
                and len(stripped) - len(stripped.lstrip(fence_character)) >= fence_length
                and not stripped.lstrip(fence_character).strip()
            ):
                in_fence = False
                fence_character = ""
                fence_length = 0
            masked.append("")
            continue
        match = _FENCE_RE.match(line)
        if match is not None:
            fence = match.group("fence")
            in_fence = True
            fence_character = fence[0]
            fence_length = len(fence)
            masked.append("")
            continue
        masked.append(_INLINE_CODE_RE.sub(lambda found: " " * len(found.group(0)), line))
    return masked


def iter_image_references(body: str, *, base: Path) -> tuple[ImageReference, ...]:
    """Kembalikan gambar lokal yang dirujuk dan valid."""

    references: list[ImageReference] = []
    for line_number, line in enumerate(masked_lines(body), start=1):
        for match in _IMAGE_RE.finditer(line):
            raw = match.group("dest").strip()
            if raw.startswith("<") and raw.endswith(">"):
                raw = raw[1:-1].strip()
            if not raw:
                continue
            if raw.lower().startswith("data:"):
                raise AssetError(
                    f"gambar baris {line_number} memakai data URI; gunakan berkas lokal",
                    code="CFG-PATH-ESCAPE",
                    path=base,
                    key=f"gambar[{line_number}]",
                )
            if "://" in raw:
                raise AssetError(
                    f"gambar baris {line_number} harus berupa path lokal relatif: {raw!r}",
                    code="CFG-PATH-ESCAPE",
                    path=base,
                    key=f"gambar[{line_number}]",
                )
            resolved = path_mod.safe_relative_path(
                raw,
                base=base,
                label=f"gambar[{line_number}]",
                code="CFG-ASSET-MISSING",
                must_exist=True,
                expect_file=True,
            )
            references.append(
                ImageReference(
                    line=line_number,
                    alt=match.group("alt"),
                    destination=raw,
                    path=resolved,
                )
            )
    return tuple(references)


def _resolve_bibliography(
    raw: str | None,
    *,
    document_dir: Path,
) -> Path | None:
    if raw is None:
        return None
    path = path_mod.safe_relative_path(
        raw,
        base=document_dir,
        label="bibliography",
        code="CFG-ASSET-MISSING",
        must_exist=True,
        expect_file=True,
    )
    if path.suffix.lower() != ".bib":
        raise AssetError(
            f"bibliography harus berekstensi .bib: {raw!r}",
            code="CFG-TYPE",
            path=document_dir,
            key="bibliography",
        )
    return path


def _resolve_glossary(
    document_dir: Path,
) -> tuple[Path, bool]:
    override = document_dir / "istilah.tsv"
    if override.exists():
        if not override.is_file():
            raise AssetError(
                "istilah.tsv harus berupa berkas",
                code="CFG-ASSET-MISSING",
                path=override,
                key="istilah.tsv",
            )
        return override.resolve(), True
    return path_mod.glossary_file(), False


def _resolve_images_dir(document_dir: Path) -> tuple[Path, bool]:
    directory = document_dir / "gambar"
    if not directory.exists():
        return (document_dir / "gambar").resolve(), False
    if not directory.is_dir():
        raise AssetError(
            "'gambar' harus berupa direktori",
            code="CFG-ASSET-MISSING",
            path=directory,
            key="gambar",
        )
    resolved = directory.resolve()
    try:
        resolved.relative_to(document_dir)
    except ValueError as exc:
        raise AssetError(
            "direktori gambar keluar dari direktori dokumen",
            code="CFG-PATH-ESCAPE",
            path=resolved,
            key="gambar",
        ) from exc
    return resolved, True


def resolve_assets(
    document_path: Path,
    *,
    structure: Structure,
    format: Format,
    bibliography: str | None,
    body: str,
) -> Assets:
    """Resolve gambar, bibliografi, glosarium, dan template."""

    document_dir = document_path.parent.resolve()
    has_bibliography = any(item.id == "bibliography" for item in structure.back_matter)
    raw_bibliography = bibliography
    if raw_bibliography is None and has_bibliography:
        raw_bibliography = format.citation.bibliography
    resolved_bibliography = _resolve_bibliography(
        raw_bibliography,
        document_dir=document_dir,
    )
    images_dir, images_dir_exists = _resolve_images_dir(document_dir)
    glossary, glossary_is_override = _resolve_glossary(document_dir)
    images = iter_image_references(body, base=document_dir)
    templates = structure.template_dir.resolve()
    if not templates.is_dir() and any(item.source == "template" for item in structure.front_matter):
        raise AssetError(
            "direktori template struktur tidak ditemukan",
            code="CFG-TEMPLATE-MISSING",
            path=templates,
        )
    return Assets(
        document_dir=document_dir,
        images_dir=images_dir,
        images_dir_exists=images_dir_exists,
        bibliography=resolved_bibliography,
        glossary=glossary,
        glossary_is_override=glossary_is_override,
        templates_dir=templates,
        images=images,
    )
