"""Pembacaan manifest, struktur, format, dan pembuatan proyek konten.

Lapis ini sengaja tidak mengetahui cara membangun DOCX/PDF. Semua detail
pipeline lama tetap berada di ``build-docx.sh`` dan ``build.sh``.

Struktur direktori yang dibaca:

- ``structures/<nama>.yml``   -> urutan bagian dan penomoran;
- ``formats/<nama>/format.yml`` -> preset, CSL, dan nama tampilan;
- ``<konten>/manifest.yml``   -> penunjuk struktur, format, dan metadata.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # ruamel.yaml adalah dependensi runtime, tetapi tidak selalu di venv lama.
    from ruamel.yaml import YAML  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - jalur fallback diuji lewat venv tanpa ruamel.yaml
    YAML = None  # type: ignore[assignment]


MANIFEST_VERSION = 1
DEFAULT_STRUCTURE = "assignment"
DEFAULT_FORMAT = "undip-msi"


class ManifestError(Exception):
    """Kesalahan manifest, struktur, atau format yang dapat ditampilkan ke pengguna."""


# ---------------------------------------------------------------------------
# Lokasi repositori
# ---------------------------------------------------------------------------


def project_root() -> Path:
    """Kembalikan akar repositori yang memuat ``structures/`` dan ``formats/``.

    Urutan pencarian: ``LAPORAN_ROOT``, lokasi paket (``src/laporan``), lalu
    direktori kerja. Direktori kerja dipakai agar paket tetap dapat diuji dari
    instalasi lain tanpa bergantung pada susunan folder sumber.
    """

    override = os.environ.get("LAPORAN_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    package_root = Path(__file__).resolve().parents[2]
    if (package_root / "structures").is_dir():
        return package_root

    cwd = Path.cwd()
    if (cwd / "structures").is_dir():
        return cwd

    return package_root


# ---------------------------------------------------------------------------
# YAML subset reader (fallback tanpa ruamel.yaml)
# ---------------------------------------------------------------------------


def _strip_comment(line: str) -> str:
    """Buang komentar ``#`` di luar tanda kutip."""

    out: list[str] = []
    quote: str | None = None
    escaped = False
    for char in line:
        if escaped:
            out.append(char)
            escaped = False
            continue
        if quote == '"' and char == "\\":
            out.append(char)
            escaped = True
            continue
        if quote is not None:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            out.append(char)
        elif char == "#":
            break
        else:
            out.append(char)
    return "".join(out).rstrip()


def _split_inline(value: str) -> list[str]:
    """Pisahkan isi ``[a, b]`` / ``{a: b}`` dengan menghormati kutip dan kurung."""

    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if quote == '"' and char == "\\":
            current.append(char)
            escaped = True
            continue
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            current.append(char)
        elif char in "[{":
            depth += 1
            current.append(char)
        elif char in "]}":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _looks_like_mapping(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_.-]+\s*:(\s|$)", value))


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1].replace("''", "'")
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item) for item in _split_inline(inner)]
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        result: dict[str, Any] = {}
        if not inner:
            return result
        for item in _split_inline(inner):
            key, separator, rest = item.partition(":")
            if not separator:
                raise ManifestError(f"Format inline map tidak valid: {item!r}")
            result[key.strip()] = _parse_scalar(rest.strip())
        return result

    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "~"}:
        return None
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+)", value):
        return float(value)
    return value


def _prepare_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        stripped = raw.lstrip(" ")
        if stripped in {"---", "..."}:
            continue
        indent = len(raw) - len(stripped)
        content = _strip_comment(stripped)
        if content:
            lines.append((indent, content))
    return lines


def _parse_map(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ManifestError(f"Indentasi YAML tidak valid: {content!r}")
        if content.startswith("-"):
            break

        key_part, separator, rest = content.partition(":")
        if not separator:
            raise ManifestError(f"Baris YAML bukan pasangan kunci-nilai: {content!r}")
        key = key_part.strip().strip("\"'")
        rest = rest.strip()
        index += 1

        if rest == "":
            if index < len(lines) and lines[index][0] > indent:
                value, index = _parse_block(lines, index, lines[index][0])
            else:
                value = {}
        else:
            value = _parse_scalar(rest)
        result[key] = value
    return result, index


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines) and lines[index][0] == indent:
        content = lines[index][1]
        if not content.startswith("-"):
            break
        rest = content[1:].strip()
        index += 1

        if rest == "":
            if index < len(lines) and lines[index][0] > indent:
                value, index = _parse_block(lines, index, lines[index][0])
            else:
                value = None
            result.append(value)
            continue

        if _looks_like_mapping(rest):
            key, _, raw_value = rest.partition(":")
            item: dict[str, Any] = {}
            raw_value = raw_value.strip()
            item[key.strip()] = _parse_scalar(raw_value) if raw_value else {}
            while index < len(lines) and lines[index][0] > indent:
                nested_indent = lines[index][0]
                nested, index = _parse_map(lines, index, nested_indent)
                item.update(nested)
            result.append(item)
        else:
            result.append(_parse_scalar(rest))
    return result, index


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines) or lines[index][0] < indent:
        return {}, index
    actual_indent = lines[index][0]
    if lines[index][1].startswith("-"):
        return _parse_list(lines, index, actual_indent)
    return _parse_map(lines, index, actual_indent)


def _parse_yaml_subset(text: str) -> Any:
    lines = _prepare_lines(text)
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ManifestError(f"Baris YAML tidak terpakai mulai: {lines[index][1]!r}")
    return value


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Baca satu berkas YAML menjadi ``dict``.

    ruamel.yaml dipakai bila tersedia. Bila tidak (mis. venv proyek hanya
    memasang python-docx/lxml/pytest), pembaca subset bawaan menangani bentuk
    yang dipakai repositori ini: skalar, daftar inline/blok, dan peta bersarang.
    """

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ManifestError(f"Tidak dapat membaca {source}: {exc}") from exc

    try:
        if YAML is not None:
            data = YAML(typ="safe").load(text)
        else:
            data = _parse_yaml_subset(text)
    except ManifestError:
        raise
    except Exception as exc:  # pesan ruamel.yaml tetap ramah pengguna
        raise ManifestError(f"YAML tidak valid di {source}: {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ManifestError(f"{source} harus berisi pemetaan YAML (kunci-nilai).")
    return data


# ---------------------------------------------------------------------------
# Model struktur dan format
# ---------------------------------------------------------------------------


def _string_list(value: Any, field_name: str, source: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise ManifestError(f"{source}: kunci '{field_name}' harus berupa daftar teks.")


def _safe_name(value: str, field_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ManifestError(f"{field_name} tidak valid: {value!r}")
    return value


@dataclass(frozen=True)
class Structure:
    name: str
    format: str
    front_matter: tuple[str, ...]
    body_numbering: str
    chapters: tuple[str, ...]
    back_matter: tuple[str, ...]
    toc: bool
    blank_line: str
    source: Path


@dataclass(frozen=True)
class Format:
    name: str
    display_name: str
    description: str
    csl: str
    bibliography: str
    presets: dict[str, str] = field(default_factory=dict)
    source: Path | None = None

    def preset_for(self, structure: str) -> str:
        preset = self.presets.get(structure) or self.presets.get("default")
        if not preset:
            raise ManifestError(
                f"Format '{self.name}' tidak memetakan preset untuk struktur "
                f"'{structure}'. Tambahkan kunci presets di {self.source or 'format.yml'}."
            )
        return preset


def load_structure(name: str) -> Structure:
    name = _safe_name(name, "Nama struktur")
    root = project_root()
    path = root / "structures" / f"{name}.yml"
    if not path.is_file():
        available = ", ".join(item.stem for item in sorted((root / "structures").glob("*.yml")))
        raise ManifestError(f"Struktur '{name}' tidak ditemukan. Tersedia: {available or '-'}.")
    data = load_yaml(path)
    structure_name = str(data.get("structure") or name)
    format_name = str(data.get("format") or DEFAULT_FORMAT)
    chapters = _string_list(data.get("chapters"), "chapters", path)
    if not chapters:
        raise ManifestError(f"{path}: kunci 'chapters' wajib berisi minimal satu berkas.")
    return Structure(
        name=structure_name,
        format=format_name,
        front_matter=_string_list(data.get("front_matter"), "front_matter", path),
        body_numbering=str(data.get("body_numbering") or "ARABIC_DOTTED"),
        chapters=chapters,
        back_matter=_string_list(data.get("back_matter"), "back_matter", path),
        toc=bool(data.get("toc", False)),
        blank_line=str(data.get("blank_line") or "before_heading_only"),
        source=path,
    )


def load_format(name: str) -> Format:
    name = _safe_name(name, "Nama format")
    root = project_root()
    path = root / "formats" / name / "format.yml"
    if not path.is_file():
        available = ", ".join(
            item.parent.name for item in sorted((root / "formats").glob("*/format.yml"))
        )
        raise ManifestError(f"Format '{name}' tidak ditemukan. Tersedia: {available or '-'}.")
    data = load_yaml(path)
    presets_raw = data.get("presets")
    presets: dict[str, str] = {}
    if isinstance(presets_raw, dict):
        presets = {str(key): str(value) for key, value in presets_raw.items()}
    elif presets_raw is not None:
        raise ManifestError(f"{path}: kunci 'presets' harus berupa pemetaan struktur->preset.")

    return Format(
        name=str(data.get("format") or name),
        display_name=str(data.get("name") or name),
        description=str(data.get("description") or ""),
        csl=str(data.get("csl") or "refs/undip-msi.csl"),
        bibliography=str(data.get("bibliography") or "references.bib"),
        presets=presets,
        source=path,
    )


def list_structures() -> list[Structure]:
    root = project_root()
    return [
        load_structure(path.stem)
        for path in sorted((root / "structures").glob("*.yml"))
        if path.is_file()
    ]


def list_formats() -> list[Format]:
    root = project_root()
    return [
        load_format(path.parent.name)
        for path in sorted((root / "formats").glob("*/format.yml"))
        if path.is_file()
    ]


# ---------------------------------------------------------------------------
# Proyek konten
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Project:
    content_dir: Path
    manifest_path: Path
    manifest: dict[str, Any]
    structure: Structure
    format: Format
    metadata_path: Path
    chapters_dir: Path
    chapter_paths: tuple[Path, ...]
    report_name: str


@dataclass
class CheckResult:
    project: Project | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def find_manifest(content_dir: Path) -> Path:
    for name in ("manifest.yml", "manifest.yaml"):
        candidate = content_dir / name
        if candidate.is_file():
            return candidate
    raise ManifestError(
        f"manifest.yml tidak ditemukan di {content_dir}. "
        "Buat proyek dengan: python -m laporan new <struktur> --format <format> --out <dir>"
    )


def _resolve_inside(base: Path, relative: str) -> Path:
    path = (base / relative).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as exc:
        raise ManifestError(f"Path keluar dari direktori konten: {relative}") from exc
    return path


def load_project(content_dir: str | Path) -> Project:
    base = Path(content_dir).expanduser().resolve()
    manifest_path = find_manifest(base)
    manifest = load_yaml(manifest_path)

    structure_name = manifest.get("structure")
    if not structure_name:
        raise ManifestError(f"{manifest_path}: kunci 'structure' wajib diisi.")
    structure = load_structure(str(structure_name))

    format_name = manifest.get("format") or structure.format
    format_ = load_format(str(format_name))

    metadata_name = str(manifest.get("metadata") or "metadata.yml")
    metadata_path = _resolve_inside(base, metadata_name)
    chapters_dir = (base / "chapters").resolve()

    if "chapters" in manifest:
        chapter_relatives = _string_list(manifest.get("chapters"), "chapters", manifest_path)
        if not chapter_relatives:
            raise ManifestError(f"{manifest_path}: kunci 'chapters' tidak boleh kosong.")
    else:
        chapter_relatives = structure.chapters
    chapter_paths = tuple(_resolve_inside(base, chapter) for chapter in chapter_relatives)

    report_name = str(manifest.get("report_name") or structure.name).strip()
    if not report_name:
        raise ManifestError(f"{manifest_path}: 'report_name' tidak boleh kosong.")
    if re.search(r"[\\/:*?\"<>|]", report_name):
        raise ManifestError(
            f"{manifest_path}: 'report_name' tidak boleh memuat karakter path: {report_name!r}"
        )

    return Project(
        content_dir=base,
        manifest_path=manifest_path,
        manifest=manifest,
        structure=structure,
        format=format_,
        metadata_path=metadata_path,
        chapters_dir=chapters_dir,
        chapter_paths=chapter_paths,
        report_name=report_name,
    )


def validate_project(content_dir: str | Path) -> CheckResult:
    """Validasi manifest, struktur, format, metadata, dan seluruh berkas bab."""

    result = CheckResult(project=None)
    base = Path(content_dir).expanduser().resolve()
    if not base.is_dir():
        result.errors.append(f"Direktori konten tidak ditemukan: {base}")
        return result

    try:
        project = load_project(base)
    except ManifestError as exc:
        result.errors.append(str(exc))
        return result

    result.project = project
    result.passed.append(f"manifest {project.manifest_path.name}")

    if project.chapter_paths:
        result.passed.append(
            f"struktur {project.structure.name} ({len(project.chapter_paths)} bab)"
        )
    result.passed.append(f"format {project.format.name}")

    if project.structure.format and project.structure.format != project.format.name:
        result.warnings.append(
            f"Manifest memakai format '{project.format.name}', sedangkan struktur "
            f"'{project.structure.name}' menetapkan default '{project.structure.format}'."
        )

    if not project.metadata_path.is_file():
        result.errors.append(f"Metadata tidak ditemukan: {project.metadata_path}")
    else:
        result.passed.append(f"metadata {project.metadata_path.name}")

    if not project.chapters_dir.is_dir():
        result.errors.append(f"Direktori bab tidak ditemukan: {project.chapters_dir}")

    expected_chapters = {path.resolve() for path in project.chapter_paths}
    if project.chapters_dir.is_dir():
        for extra in sorted(project.chapters_dir.glob("*.md")):
            if extra.resolve() not in expected_chapters:
                result.warnings.append(
                    f"Bab tidak tercantum di struktur '{project.structure.name}': "
                    f"{extra.relative_to(project.content_dir).as_posix()} "
                    "(tetap akan ikut terbangun oleh pipeline lama)."
                )

    for chapter in project.chapter_paths:
        if not chapter.is_file():
            result.errors.append(f"Bab tidak ditemukan: {chapter}")
            continue
        if chapter.suffix.lower() != ".md":
            result.warnings.append(f"Bab bukan Markdown: {chapter}")
        else:
            result.passed.append(f"bab {chapter.relative_to(project.content_dir).as_posix()}")

    bibliography = (project.content_dir / project.format.bibliography).resolve()
    if not bibliography.is_file():
        result.warnings.append(
            f"Bibliografi '{project.format.bibliography}' tidak ditemukan; "
            "build akan memakai references.bib dari repositori."
        )

    images = project.content_dir / "gambar"
    if not images.is_dir():
        result.warnings.append("Direktori gambar/ tidak ditemukan.")

    if not (project.content_dir / "cover.md").is_file():
        result.warnings.append(
            "cover.md tidak ditemukan; build akan memakai cover.md dari repositori."
        )

    return result


# ---------------------------------------------------------------------------
# Pembuatan proyek baru
# ---------------------------------------------------------------------------


_DISPLAY_TITLES = {
    "assignment": "Tugas",
    "proposal": "Proposal Tesis",
    "thesis": "Tesis",
}


def _display_title(structure: str) -> str:
    return _DISPLAY_TITLES.get(structure, structure.replace("-", " ").title())


def _chapter_title(path: str) -> str:
    stem = Path(path).stem
    stem = re.sub(r"^bab\d*[-_]?", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"^\d+[-_]", "", stem)
    words = re.split(r"[-_]+", stem)
    return " ".join(word.capitalize() for word in words if word) or "Bab"


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _metadata_text(structure: Structure, format_: Format, title: str) -> str:
    preset = format_.preset_for(structure.name)
    toc = "true" if structure.toc else "false"
    return f"""# Metadata proyek. Ubah nilai, pertahankan kunci `preset`.
title: {_yaml_quote(title)}
subtitle: ""
author:
  - name: "Nama Mahasiswa"
    nim: "NIM"
lecturer: "Nama Dosen Pengampu"
lecturer_label: "Dosen Pengampu:"
course: "Nama Mata Kuliah"
institution: "Universitas Diponegoro"
faculty: "Program Studi Magister Sistem Informasi"
year: "2026"
date: "Agustus 2026"
lang: "id-ID"
preset: {_yaml_quote(preset)}
toc: {toc}
daftar_gambar: false
daftar_tabel: false
"""


def _manifest_text(structure: Structure, format_: Format, report_name: str) -> str:
    chapter_lines = "\n".join(f"  - {chapter}" for chapter in structure.chapters)
    return f"""# Manifest proyek laporan. Jangan mengubah kunci di luar struktur/format.
manifest: {MANIFEST_VERSION}
structure: {structure.name}
format: {format_.name}
metadata: metadata.yml
report_name: {_yaml_quote(report_name)}
chapters:
{chapter_lines}
"""


def _chapter_text(path: str) -> str:
    title = _chapter_title(path)
    return f"""# {title}

Tulis isi bab ini di sini. Sitasi memakai kunci BibTeX, misalnya [@pandoc2024].

## Subbagian Pertama

Ganti paragraf contoh ini dengan materi Anda.

## Subbagian Kedua

Tambahkan pembahasan, tabel, atau gambar sesuai kebutuhan.
"""


def _cover_text(structure: Structure) -> str:
    has_preface = "preface" in structure.front_matter or "kata_pengantar" in structure.front_matter
    parts: list[str] = []

    if has_preface:
        parts.append(
            "# KATA PENGANTAR {-}\n\n"
            "Tulis kata pengantar di sini. Ganti paragraf contoh ini dengan materi Anda.\n"
        )

    if structure.toc:
        parts.append(
            """```{=typst}
#if toc-enabled {
  pagebreak()
  daftar-isi()
  pagebreak()
}
#set page(numbering: "1")
#counter(page).update(1)
```

```{=openxml}
<!-- Daftar isi DOCX disisipkan otomatis oleh docx.lua bila metadata toc: true. -->
```
"""
        )
    elif not has_preface:
        parts.append(
            """```{=openxml}
<!-- Halaman sampul ditangani oleh metadata; tidak ada daftar isi. -->
```
"""
        )

    return "\n".join(parts)


_REFERENCES_TEXT = """@manual{pandoc2024,
  author = {MacFarlane, John},
  title  = {Pandoc: A Universal Document Converter},
  year   = {2024},
  url    = {https://pandoc.org/MANUAL.html}
}
"""


def create_project(
    structure_name: str,
    format_name: str,
    out_dir: str | Path,
    *,
    title: str | None = None,
    report_name: str | None = None,
    force: bool = False,
) -> tuple[Path, list[Path]]:
    """Buat kerangka proyek konten baru dan kembalikan daftar berkas."""

    structure = load_structure(structure_name)
    format_ = load_format(format_name)
    out = Path(out_dir).expanduser().resolve()

    if out.exists() and not out.is_dir():
        raise ManifestError(f"Tujuan bukan direktori: {out}")
    if out.is_dir() and any(out.iterdir()) and not force:
        raise ManifestError(
            f"Direktori tujuan sudah berisi berkas: {out}. Gunakan --force untuk menimpa."
        )

    display = title or f"Judul {_display_title(structure.name)}"
    name = report_name or _display_title(structure.name)

    out.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    def write(relative: str, content: str) -> None:
        path = _resolve_inside(out, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        created.append(path)

    write("manifest.yml", _manifest_text(structure, format_, name))
    write("metadata.yml", _metadata_text(structure, format_, display))
    write("cover.md", _cover_text(structure))
    for chapter in structure.chapters:
        write(chapter, _chapter_text(chapter))
    write("references.bib", _REFERENCES_TEXT)

    images = out / "gambar"
    images.mkdir(parents=True, exist_ok=True)
    gitkeep = images / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("", encoding="utf-8")
        created.append(gitkeep)

    return out, created
