"""Workflow satu berkas Markdown: front matter, materialisasi, build DOCX/PDF.

Berkas sumber berisi YAML front matter di awal dan body Markdown setelahnya.
Modul ini tidak menulis ulang pipeline: ia membuat proyek sementara
``.laporan-build/`` di folder berkas, lalu memanggil ``build-docx.sh`` dan/atau
``build.sh`` dengan kontrak environment yang sudah dipakai CLI mode folder.

Yang dijaga di sini:

- tidak ada tulisan ke akar repositori;
- metadata sementara tidak memuat path absolut;
- referensi dan gambar harus relatif terhadap folder berkas;
- workspace dibersihkan setelah build, kecuali ``keep=True``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from . import manifest as manifest_mod
from . import mermaid as mermaid_mod
from . import platform as platform_mod

try:  # ruamel.yaml adalah dependensi runtime; fallback menjaga venv pengembangan lama.
    from ruamel.yaml import YAML  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - jalur fallback diuji tanpa ruamel.yaml
    YAML = None  # type: ignore[assignment]


WORKSPACE_DIRNAME = ".laporan-build"
DEFAULT_REPORT_NAME = "Tugas"
TARGETS = ("docx", "pdf", "both")

_FRONT_MATTER_START = "---"
_FRONT_MATTER_END = {"---", "..."}
_FENCE_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)*?\1")
_IMAGE_RE = re.compile(
    r"(?<!\\)!\[(?P<alt>[^\]]*)\]\(\s*"
    r"(?P<dest><[^>]*>|[^)\s]+)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
_SAFE_PRESET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_ABSOLUTE_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

# Kunci yang mengatur materialisasi dan tidak boleh ikut ke metadata Pandoc.
_BUILD_ONLY_KEYS = frozenset(
    {
        "laporan",
        "structure",
        "format",
        "preset",
        "bibliography",
        "references",
        "report_name",
        "output",
        "glossary",
    }
)

# Kunci yang secara historis menunjuk path. Dibuang agar metadata sementara
# tidak pernah memuat path absolut dari front matter.
_PATH_KEYS = frozenset(
    {
        "csl",
        "reference-doc",
        "reference_doc",
        "resource-path",
        "resource_path",
        "template",
        "logo",
        "cover",
        "input-files",
        "bibliography-file",
        "bibliography_file",
    }
)

_COVER_TEXT = """```{=openxml}
<!-- Sampul dibangun dari metadata.yml; TOC ditangani docx.lua. -->
```
"""


class SingleFileError(Exception):
    """Kesalahan berkas tunggal yang dapat ditampilkan ke pengguna."""


@dataclass(frozen=True)
class SingleFileDocument:
    """Hasil pembacaan satu berkas Markdown."""

    path: Path
    front_matter: dict[str, Any]
    body: str


@dataclass(frozen=True)
class Materialized:
    """Proyek sementara yang siap dipakai pipeline build."""

    document: SingleFileDocument
    workspace: Path
    metadata: dict[str, Any]
    report_name: str
    toc: bool
    structure: manifest_mod.Structure
    format: manifest_mod.Format

    @property
    def metadata_path(self) -> Path:
        return self.workspace / "metadata.yml"

    @property
    def cover_path(self) -> Path:
        return self.workspace / "cover.md"

    @property
    def chapters_dir(self) -> Path:
        return self.workspace / "chapters"

    @property
    def chapter_path(self) -> Path:
        return self.chapters_dir / "01.md"

    @property
    def bibliography_path(self) -> Path:
        return self.workspace / "references.bib"

    @property
    def images_dir(self) -> Path:
        return self.workspace / "gambar"


@dataclass(frozen=True)
class BuildResult:
    """Hasil satu invokasi ``build-file``."""

    document: Path
    workspace: Path
    outputs: tuple[Path, ...]
    targets: tuple[str, ...]
    kept: bool


Runner = Callable[..., subprocess.CompletedProcess[Any]]


# ---------------------------------------------------------------------------
# Pembacaan dan validasi front matter
# ---------------------------------------------------------------------------


def _resolve_document_path(document: str | Path) -> Path:
    path = Path(document).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        path = path.resolve()
    except OSError as exc:
        raise SingleFileError(f"Tidak dapat membaca path {document}: {exc}") from exc
    if not path.exists():
        raise SingleFileError(f"Berkas tidak ditemukan: {path}")
    if not path.is_file():
        raise SingleFileError(f"Bukan berkas biasa: {path}")
    if path.suffix.lower() not in {".md", ".markdown"}:
        raise SingleFileError(f"Berkas sumber harus Markdown (.md): {path}")
    return path


def _split_front_matter(text: str, source: Path) -> tuple[str, str]:
    """Pisahkan YAML front matter dan body tanpa mengubah isi body."""

    text = text.lstrip("\ufeff")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONT_MATTER_START:
        raise SingleFileError(
            f"{source}: YAML front matter wajib di awal berkas, diawali baris '---'."
        )
    for index in range(1, len(lines)):
        if lines[index].strip() in _FRONT_MATTER_END:
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise SingleFileError(
        f"{source}: front matter belum ditutup dengan baris '---' atau '...'."
    )


def _parse_front_matter(text: str, source: Path) -> dict[str, Any]:
    if not text.strip():
        raise SingleFileError(f"{source}: YAML front matter kosong.")
    try:
        if YAML is not None:
            data = YAML(typ="safe").load(text)
        else:
            data = manifest_mod._parse_yaml_subset(text)
    except Exception as exc:  # pesan ruamel.yaml maupun parser fallback
        raise SingleFileError(f"{source}: YAML front matter tidak valid: {exc}") from exc

    if data is None:
        raise SingleFileError(f"{source}: YAML front matter kosong.")
    if not isinstance(data, dict):
        raise SingleFileError(f"{source}: front matter harus berupa pemetaan YAML.")
    return {str(key): value for key, value in data.items()}


def parse_document(document: str | Path) -> SingleFileDocument:
    """Baca satu berkas Markdown dan pisahkan front matter dari body."""

    path = _resolve_document_path(document)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SingleFileError(f"{path}: berkas sumber harus UTF-8: {exc}") from exc
    except OSError as exc:
        raise SingleFileError(f"Tidak dapat membaca {path}: {exc}") from exc

    front_matter_text, body = _split_front_matter(text, path)
    data = _parse_front_matter(front_matter_text, path)
    if not body.strip():
        raise SingleFileError(f"{path}: body Markdown kosong setelah front matter.")
    return SingleFileDocument(path=path, front_matter=data, body=body)


# ---------------------------------------------------------------------------
# Nilai front matter
# ---------------------------------------------------------------------------


def _string_value(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise SingleFileError(f"Front matter: kunci '{field}' wajib diisi.")
        return None
    if isinstance(value, (dict, list, tuple, bool)):
        raise SingleFileError(f"Front matter: kunci '{field}' harus berupa teks.")
    text = str(value).strip()
    if required and not text:
        raise SingleFileError(f"Front matter: kunci '{field}' tidak boleh kosong.")
    return text


def _bool_value(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0"}:
            return False
    raise SingleFileError(
        f"Front matter: kunci '{field}' harus bernilai true atau false."
    )


def _bool_or_default(data: dict[str, Any], field: str, default: bool) -> bool:
    value = data.get(field)
    if value is None:
        return default
    return _bool_value(value, field)


def _normalize_value(value: Any) -> Any:
    """Ubah nilai YAML menjadi tipe yang aman ditulis ulang ke metadata.yml."""

    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


def _normalize_author(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("author")
    if raw is None:
        raise SingleFileError("Front matter: kunci 'author' wajib diisi.")
    nim = _string_value(data.get("nim"), "nim")

    if isinstance(raw, str):
        entries: list[Any] = [raw]
    elif isinstance(raw, dict):
        entries = [raw]
    elif isinstance(raw, list):
        entries = raw
    else:
        raise SingleFileError(
            "Front matter: kunci 'author' harus berupa teks, pemetaan, atau daftar."
        )

    if not entries:
        raise SingleFileError("Front matter: daftar 'author' tidak boleh kosong.")

    result: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        if isinstance(entry, str):
            name = entry.strip()
            if not name:
                raise SingleFileError(
                    f"Front matter: author ke-{index} tidak memiliki nama."
                )
            item: dict[str, Any] = {"name": name}
        elif isinstance(entry, dict):
            normalized = _normalize_value(entry)
            name = _string_value(normalized.get("name"), f"author[{index}].name")
            if not name:
                raise SingleFileError(
                    f"Front matter: author ke-{index} tidak memiliki 'name'."
                )
            item = dict(normalized)
            item["name"] = name
        else:
            raise SingleFileError(
                f"Front matter: author ke-{index} harus berupa teks atau pemetaan."
            )

        if nim and len(entries) == 1 and not item.get("nim"):
            item["nim"] = nim
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Jalur aset
# ---------------------------------------------------------------------------


def _is_inside(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base.resolve())
    except ValueError:
        return False
    return True


def _resolve_local_path(base: Path, raw: str, field: str) -> Path:
    text = raw.strip()
    if not text:
        raise SingleFileError(f"{field} tidak boleh kosong.")

    if text.startswith(("/", "\\")) or _ABSOLUTE_WINDOWS_RE.match(text):
        raise SingleFileError(f"{field} harus berupa path relatif: {raw!r}.")
    if _SCHEME_RE.match(text):
        raise SingleFileError(f"{field} harus berupa path lokal relatif: {raw!r}.")

    posix = text.replace("\\", "/")
    parts = PurePosixPath(posix).parts
    if any(part == ".." for part in parts):
        raise SingleFileError(
            f"{field} tidak boleh keluar dari folder berkas: {raw!r}."
        )

    try:
        resolved = (base / posix).resolve()
    except OSError as exc:
        raise SingleFileError(f"{field} tidak dapat dibaca: {raw!r}: {exc}") from exc
    if not _is_inside(resolved, base):
        raise SingleFileError(
            f"{field} tidak boleh keluar dari folder berkas: {raw!r}."
        )
    return resolved


def _masked_lines(text: str) -> list[str]:
    """Samarkan fenced code dan inline code agar contoh gambar diabaikan."""

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


def _validate_images(document: SingleFileDocument) -> tuple[Path, ...]:
    images: list[Path] = []
    seen: set[Path] = set()
    base = document.path.parent

    for line_number, line in enumerate(_masked_lines(document.body), start=1):
        for match in _IMAGE_RE.finditer(line):
            raw = match.group("dest").strip()
            if raw.startswith("<") and raw.endswith(">"):
                raw = raw[1:-1].strip()
            if not raw:
                continue

            resolved = _resolve_local_path(base, raw, f"Gambar baris {line_number}")
            parts = PurePosixPath(raw.replace("\\", "/")).parts
            if len(parts) < 2 or parts[0] != "gambar":
                raise SingleFileError(
                    f"{document.path}:{line_number}: gambar harus berada di "
                    f"folder 'gambar/' (ditemukan {raw!r})."
                )
            if not resolved.is_file():
                raise SingleFileError(
                    f"{document.path}:{line_number}: gambar tidak ditemukan: {raw}."
                )
            if resolved not in seen:
                seen.add(resolved)
                images.append(resolved)
    return tuple(images)


def _source_images_dir(document: SingleFileDocument) -> Path | None:
    source = document.path.parent / "gambar"
    if not source.exists():
        return None
    if not source.is_dir():
        raise SingleFileError(f"'gambar' harus berupa direktori: {source}")
    try:
        resolved = source.resolve()
    except OSError as exc:
        raise SingleFileError(f"Tidak dapat membaca folder gambar {source}: {exc}") from exc
    if not _is_inside(resolved, document.path.parent):
        raise SingleFileError(f"Folder gambar keluar dari folder berkas: {source}")
    return resolved


# ---------------------------------------------------------------------------
# Diagram Mermaid
# ---------------------------------------------------------------------------


def _render_mermaid_blocks(
    document: SingleFileDocument,
) -> tuple[str, tuple[Path, ...]]:
    """Render blok Mermaid ke ``gambar/`` folder tugas lalu ganti dengan gambar.

    Bila tidak ada blok Mermaid, body dikembalikan tanpa perubahan dan tidak
    ada berkas yang ditulis maupun ``mmdc`` yang dicari.
    """

    try:
        plans = mermaid_mod.plan_blocks(
            document.body,
            document.path.parent,
            path=document.path,
        )
        if not plans:
            return document.body, ()

        executable = None
        if any(not plan.image_path.is_file() for plan in plans):
            executable = mermaid_mod.find_mmdc()
            if executable is None:
                raise SingleFileError(
                    "Blok Mermaid ditemukan, tetapi mmdc tidak ditemukan di PATH. "
                    "Pasang Mermaid CLI dengan "
                    "`npm install -g @mermaid-js/mermaid-cli` (butuh Node.js), "
                    "lalu pastikan `mmdc` ada di PATH."
                )

        rendered: list[Path] = []
        seen: set[Path] = set()
        for plan in plans:
            if plan.image_path in seen:
                continue
            seen.add(plan.image_path)
            rendered.append(
                mermaid_mod.render_mermaid(
                    plan.block.code,
                    plan.image_path,
                    executable,
                )
            )
        body = mermaid_mod.rewrite_markdown(document.body, plans)
    except (mermaid_mod.MermaidError, OSError) as exc:
        raise SingleFileError(f"Gagal memproses diagram Mermaid: {exc}") from exc

    return body, tuple(rendered)


# ---------------------------------------------------------------------------
# Metadata sementara
# ---------------------------------------------------------------------------


def _validate_preset(name: str) -> None:
    if not _SAFE_PRESET_RE.fullmatch(name):
        raise SingleFileError(f"Nama preset tidak valid: {name!r}.")
    path = manifest_mod.project_root() / "presets" / f"{name}.yml"
    if not path.is_file():
        raise SingleFileError(
            f"Preset '{name}' tidak ditemukan di {path}. "
            "Periksa kunci preset pada front matter."
        )


def _validate_report_name(name: str) -> str:
    if not name or name in {".", ".."}:
        raise SingleFileError("report_name tidak boleh kosong.")
    if re.search(r'[\\/:*?"<>|]', name):
        raise SingleFileError(
            f"report_name tidak boleh memuat karakter path: {name!r}."
        )
    return name


def _assert_no_absolute_paths(value: Any, key: str = "metadata") -> None:
    if isinstance(value, str):
        if value.startswith(("/", "\\")) or _ABSOLUTE_WINDOWS_RE.match(value):
            raise SingleFileError(
                f"Metadata '{key}' tidak boleh berisi path absolut: {value!r}."
            )
    elif isinstance(value, dict):
        for child_key, child in value.items():
            _assert_no_absolute_paths(child, f"{key}.{child_key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_no_absolute_paths(child, f"{key}[{index}]")


def _build_metadata(
    document: SingleFileDocument,
    *,
    title: str,
    authors: list[dict[str, Any]],
    preset: str,
    toc: bool,
) -> dict[str, Any]:
    data = document.front_matter
    metadata: dict[str, Any] = {"title": title}

    subtitle = _string_value(data.get("subtitle"), "subtitle")
    if subtitle is not None:
        metadata["subtitle"] = subtitle
    metadata["author"] = authors

    for key in (
        "lecturer",
        "lecturer_label",
        "course",
        "institution",
        "faculty",
        "year",
        "date",
        "lang",
        "abstract",
        "abstract_id",
        "abstract_en",
        "keywords",
        "keywords_id",
        "keywords_en",
        "approval",
        "preface",
        "statement",
        "heading_chapter_prefix",
        "heading_chapter_num_format",
        "heading_sub_dot",
        "heading_subsub_dot",
        "cover_show_lecturer",
        "cover_hide_lecturer",
        "cover_logo_width",
    ):
        if key in data and data[key] is not None:
            metadata[key] = _normalize_value(data[key])

    if "lang" not in metadata:
        metadata["lang"] = "id-ID"

    metadata["preset"] = preset
    metadata["toc"] = toc
    metadata["daftar_gambar"] = _bool_or_default(data, "daftar_gambar", False)
    metadata["daftar_tabel"] = _bool_or_default(data, "daftar_tabel", False)

    handled = {
        "title",
        "subtitle",
        "author",
        "nim",
        "toc",
        "daftar_gambar",
        "daftar_tabel",
        *(
            "lecturer",
            "lecturer_label",
            "course",
            "institution",
            "faculty",
            "year",
            "date",
            "lang",
            "abstract",
            "abstract_id",
            "abstract_en",
            "keywords",
            "keywords_id",
            "keywords_en",
            "approval",
            "preface",
            "statement",
            "heading_chapter_prefix",
            "heading_chapter_num_format",
            "heading_sub_dot",
            "heading_subsub_dot",
            "cover_show_lecturer",
            "cover_hide_lecturer",
            "cover_logo_width",
        ),
    }
    for key, value in data.items():
        if key in handled or key in _BUILD_ONLY_KEYS or key in _PATH_KEYS:
            continue
        metadata[key] = _normalize_value(value)

    _assert_no_absolute_paths(metadata)
    return metadata


# ---------------------------------------------------------------------------
# Penulisan YAML tanpa ketergantungan wajib pada ruamel.yaml
# ---------------------------------------------------------------------------


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_inline(value: Any) -> str:
    if isinstance(value, dict) and not value:
        return "{}"
    if isinstance(value, list) and not value:
        return "[]"
    return _yaml_scalar(value)


def _dump_yaml_block(value: Any, indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent

    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if isinstance(item, dict) and item:
                lines.append(f"{pad}{key_text}:")
                lines.extend(_dump_yaml_block(item, indent + 2))
            elif isinstance(item, list) and item:
                lines.append(f"{pad}{key_text}:")
                lines.extend(_dump_yaml_list(item, indent + 2))
            else:
                lines.append(f"{pad}{key_text}: {_yaml_inline(item)}")
        return lines

    if isinstance(value, list):
        return _dump_yaml_list(value, indent)

    return [f"{pad}{_yaml_inline(value)}"]


def _dump_yaml_list(items: list[Any], indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent

    for item in items:
        if isinstance(item, dict):
            if not item:
                lines.append(f"{pad}- {{}}")
                continue
            first = True
            for key, value in item.items():
                key_text = str(key)
                prefix = f"{pad}- " if first else f"{pad}  "
                first = False
                if isinstance(value, dict) and value:
                    lines.append(f"{prefix}{key_text}:")
                    lines.extend(_dump_yaml_block(value, indent + 4))
                elif isinstance(value, list) and value:
                    lines.append(f"{prefix}{key_text}:")
                    lines.extend(_dump_yaml_list(value, indent + 4))
                else:
                    lines.append(f"{prefix}{key_text}: {_yaml_inline(value)}")
        elif isinstance(item, list):
            lines.append(f"{pad}-")
            lines.extend(_dump_yaml_list(item, indent + 2))
        else:
            lines.append(f"{pad}- {_yaml_inline(item)}")
    return lines


def dump_metadata_yaml(metadata: dict[str, Any]) -> str:
    """Tulis metadata sebagai YAML yang kompatibel dengan build-docx.sh."""

    return "\n".join(_dump_yaml_block(metadata, 0)) + "\n"


# ---------------------------------------------------------------------------
# Materialisasi
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Plan:
    metadata: dict[str, Any]
    report_name: str
    toc: bool
    bibliography: Path
    glossary: Path
    source_images: Path | None
    structure: manifest_mod.Structure
    format: manifest_mod.Format


def _build_plan(document: SingleFileDocument) -> _Plan:
    data = document.front_matter
    title = _string_value(data.get("title"), "title", required=True)
    assert title is not None  # required=True

    structure_name = (
        _string_value(data.get("structure"), "structure")
        or manifest_mod.DEFAULT_STRUCTURE
    )
    try:
        structure = manifest_mod.load_structure(structure_name)
    except manifest_mod.ManifestError as exc:
        raise SingleFileError(str(exc)) from exc

    format_name = (
        _string_value(data.get("format"), "format")
        or structure.format
        or manifest_mod.DEFAULT_FORMAT
    )
    try:
        format_ = manifest_mod.load_format(format_name)
    except manifest_mod.ManifestError as exc:
        raise SingleFileError(str(exc)) from exc

    preset = (
        _string_value(data.get("preset"), "preset")
        or format_.preset_for(structure.name)
    )
    _validate_preset(preset)

    toc = _bool_or_default(data, "toc", structure.toc)
    report_name = _validate_report_name(
        _string_value(data.get("report_name"), "report_name") or DEFAULT_REPORT_NAME
    )

    if "references" in data:
        raise SingleFileError(
            "Front matter: bibliografi embedded ('references') belum didukung; "
            "gunakan kunci 'bibliography' yang menunjuk berkas .bib relatif."
        )

    bibliography_raw = (
        _string_value(data.get("bibliography"), "bibliography")
        or format_.bibliography
        or "references.bib"
    )
    bibliography = _resolve_local_path(
        document.path.parent, bibliography_raw, "bibliography"
    )
    if not bibliography.is_file():
        raise SingleFileError(
            f"Bibliografi tidak ditemukan: {bibliography_raw} "
            f"(relatif terhadap {document.path.parent})."
        )

    glossary_raw = _string_value(data.get("glossary"), "glossary")
    if glossary_raw:
        glossary = _resolve_local_path(
            document.path.parent, glossary_raw, "glossary"
        )
        if not glossary.is_file():
            raise SingleFileError(
                f"Glosarium tidak ditemukan: {glossary_raw} "
                f"(relatif terhadap {document.path.parent})."
            )
    else:
        glossary = manifest_mod.project_root() / "writing" / "istilah.tsv"
        if not glossary.is_file():
            raise SingleFileError(
                f"Glosarium repositori tidak ditemukan: {glossary}. "
                "Build-docx.sh memerlukannya sebelum Pandoc."
            )

    _validate_images(document)
    source_images = _source_images_dir(document)

    authors = _normalize_author(data)
    metadata = _build_metadata(
        document,
        title=title,
        authors=authors,
        preset=preset,
        toc=toc,
    )

    return _Plan(
        metadata=metadata,
        report_name=report_name,
        toc=toc,
        bibliography=bibliography,
        glossary=glossary,
        source_images=source_images,
        structure=structure,
        format=format_,
    )


def _workspace_path(document: Path, workspace: str | Path | None) -> Path:
    if workspace is None:
        return (document.parent / WORKSPACE_DIRNAME).resolve()

    candidate = Path(workspace).expanduser()
    if not candidate.is_absolute():
        candidate = document.parent / candidate
    candidate = candidate.resolve()

    if candidate == document.parent or not _is_inside(candidate, document.parent):
        raise SingleFileError(
            f"Workspace build harus berada di folder berkas: {document.parent}"
        )
    return candidate


def _prepare_workspace(workspace: Path) -> None:
    if workspace.is_symlink():
        raise SingleFileError(
            f"Workspace tidak boleh berupa symlink: {workspace}. Hapus manual lalu ulangi."
        )
    if workspace.exists():
        if not workspace.is_dir():
            raise SingleFileError(f"Workspace bukan direktori: {workspace}")
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=False)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _materialize(document: SingleFileDocument, workspace: Path) -> Materialized:
    plan = _build_plan(document)
    chapter_text, mermaid_images = _render_mermaid_blocks(document)
    rendered_document = SingleFileDocument(
        path=document.path,
        front_matter=document.front_matter,
        body=chapter_text,
    )
    if mermaid_images:
        _validate_images(rendered_document)

    try:
        _prepare_workspace(workspace)
    except OSError as exc:
        raise SingleFileError(f"Tidak dapat menyiapkan workspace {workspace}: {exc}") from exc

    try:
        (workspace / "chapters").mkdir()
        (workspace / "gambar").mkdir()
        (workspace / "writing").mkdir()

        _write_text(workspace / "metadata.yml", dump_metadata_yaml(plan.metadata))
        _write_text(workspace / "cover.md", _COVER_TEXT)

        body = chapter_text.replace("\r\n", "\n").replace("\r", "\n")
        if not body.endswith("\n"):
            body += "\n"
        _write_text(workspace / "chapters" / "01.md", body)

        shutil.copyfile(plan.bibliography, workspace / "references.bib")
        shutil.copyfile(plan.glossary, workspace / "writing" / "istilah.tsv")

        source_images = plan.source_images
        if source_images is None:
            source_images = _source_images_dir(rendered_document)
        if source_images is not None:
            shutil.copytree(source_images, workspace / "gambar", dirs_exist_ok=True)
    except SingleFileError:
        _cleanup_workspace(workspace)
        raise
    except OSError as exc:
        _cleanup_workspace(workspace)
        raise SingleFileError(f"Gagal menyiapkan workspace {workspace}: {exc}") from exc

    return Materialized(
        document=document,
        workspace=workspace,
        metadata=plan.metadata,
        report_name=plan.report_name,
        toc=plan.toc,
        structure=plan.structure,
        format=plan.format,
    )


def materialize(
    document: str | Path, *, workspace: str | Path | None = None
) -> Materialized:
    """Baca berkas dan tulis proyek sementara tanpa menjalankan build."""

    source = parse_document(document)
    target = _workspace_path(source.path, workspace)
    return _materialize(source, target)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _cleanup_workspace(workspace: Path) -> None:
    try:
        if workspace.is_symlink() or workspace.is_file():
            workspace.unlink()
        elif workspace.is_dir():
            shutil.rmtree(workspace)
    except OSError as exc:
        print(
            f"[PERINGATAN] Gagal menghapus workspace {workspace}: {exc}",
            file=sys.stderr,
        )


def _build_env(materialized: Materialized) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "LAPORAN_METADATA": materialized.metadata_path.as_posix(),
            "LAPORAN_CHAPTERS": materialized.chapters_dir.as_posix(),
            "LAPORAN_REPORT_NAME": materialized.report_name,
            "LAPORAN_TOC": "true" if materialized.toc else "false",
            "LAPORAN_PYTHON": Path(sys.executable).as_posix(),
            "LAPORAN_ROOT": manifest_mod.project_root().as_posix(),
            "OUTDIR": materialized.workspace.as_posix(),
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


def _copy_output(source: Path, destination: Path) -> None:
    if source.stat().st_size <= 0:
        raise SingleFileError(f"Keluaran build kosong: {source}")
    if destination.is_dir():
        raise SingleFileError(f"Tujuan keluaran adalah direktori: {destination}")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    except OSError as exc:
        raise SingleFileError(
            f"Gagal menyalin {source.name} ke {destination}: {exc}"
        ) from exc


def _run_targets(
    materialized: Materialized, target: str, runner: Runner | None
) -> tuple[Path, ...]:
    if target not in TARGETS:
        raise SingleFileError(
            f"Target tidak dikenal: {target!r}. Pilih docx, pdf, atau both."
        )
    targets = ("docx", "pdf") if target == "both" else (target,)

    root = manifest_mod.project_root()
    bash = platform_mod.find_bash()
    if not bash:
        raise SingleFileError(
            "bash tidak ditemukan. Di Windows gunakan Git Bash; "
            "di Debian pasang paket bash."
        )

    execute = subprocess.run if runner is None else runner
    env = _build_env(materialized)
    outputs: list[Path] = []

    for current in targets:
        script_name = "build-docx.sh" if current == "docx" else "build.sh"
        script = root / script_name
        if not script.is_file():
            raise SingleFileError(f"Pipeline build tidak ditemukan: {script}")

        command = [bash, script_name, materialized.workspace.as_posix()]
        print(f"[BUILD] {script_name} untuk {materialized.document.path.name}")
        try:
            completed = execute(command, cwd=os.fspath(root), env=env, check=False)
        except OSError as exc:
            raise SingleFileError(f"Gagal menjalankan {script_name}: {exc}") from exc

        if completed.returncode != 0:
            raise SingleFileError(
                f"{script_name} keluar dengan kode {completed.returncode}."
            )

        source = materialized.workspace / f"{materialized.report_name}.{current}"
        if not source.is_file():
            raise SingleFileError(
                f"{script_name} selesai, tetapi keluaran tidak ditemukan: {source}"
            )

        destination = materialized.document.path.parent / source.name
        _copy_output(source, destination)
        outputs.append(destination)
        print(f"[OK] {destination}")

    return tuple(outputs)


def build_file(
    document: str | Path,
    *,
    target: str = "docx",
    keep: bool = False,
    workspace: str | Path | None = None,
    runner: Runner | None = None,
) -> BuildResult:
    """Materialisasi satu berkas, jalankan pipeline, dan salin keluarannya.

    ``runner`` hanya dipakai tes untuk mengganti ``subprocess.run``. Build
    nyata selalu memanggil ``build-docx.sh``/``build.sh`` dari akar repositori.
    """

    source = parse_document(document)
    workspace_path = _workspace_path(source.path, workspace)
    materialized = _materialize(source, workspace_path)
    targets = ("docx", "pdf") if target == "both" else (target,)

    try:
        outputs = _run_targets(materialized, target, runner)
    finally:
        if not keep:
            _cleanup_workspace(workspace_path)

    return BuildResult(
        document=source.path,
        workspace=workspace_path,
        outputs=outputs,
        targets=targets,
        kept=keep,
    )
