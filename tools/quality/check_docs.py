#!/usr/bin/env python3
"""Pemeriksa dokumentasi AutoOffice yang read-only dan deterministik.

Checker memindai `README.md` akar, `docs/**/*.md`, README paket
`src/autooffice/**`, serta README `tests` dan `tools`. Pemeriksaan mencakup
tautan relatif, TOC dokumen panjang, judul level 1, bahasa code fence,
keterjangkauan halaman dari indeks dokumentasi, dan registry referensi.
`docs/dev/archive/**` dikecualikan karena arsip dibekukan.

Pemakaian:
    python tools/quality/check_docs.py [akar-repo]

Kode keluar 0 bila bersih dan 1 bila ada temuan. Skrip tidak mengakses
jaringan dan tidak menulis berkas.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_FILE = Path("docs/dev/references.md")
ROOT_DOCUMENT = Path("README.md")
DOCS_DIR = Path("docs")
SRC_DIR = Path("src/autooffice")
ARCHIVE_DIR = Path("docs/dev/archive")
MODULE_READMES = (
    Path("tests/README.md"),
    Path("tools/README.md"),
)
TOC_THRESHOLD = 150
TOC_SLUGS = frozenset({"daftar-isi", "table-of-contents"})
MAIN_INDEX = Path("docs/README.md")

LINK_PATTERN = re.compile(
    r"(?<!!)\[(?P<teks>[^\]\n]*)\]\(\s*"
    r"(?:<(?P<bersudut>[^>\n]*)>|(?P<polos>[^\s)\n]+))"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)\n]*\)))?\s*\)"
)
FENCE_PATTERN = re.compile(r"^[ \t]*(?P<pagar>`{3,}|~{3,})(?P<info>.*)$")
INLINE_CODE_PATTERN = re.compile(r"(`+)(?P<isi>[^\n]+?)\1")
COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
HEADING_PATTERN = re.compile(r"^(?P<pagar>#{1,6})[ \t]+(?P<teks>.+?)[ \t]*#*[ \t]*$")
TOC_LINK_PATTERN = re.compile(r"^[ \t]*[-*+][ \t]+\[[^\]\n]*\]\(#(?P<anchor>[^)\n]+)\)")


@dataclass(frozen=True)
class Problem:
    """Satu temuan checker dengan lokasi berkas dan baris."""

    file: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.message}"


@dataclass(frozen=True)
class Result:
    """Ringkasan hasil pemeriksaan."""

    file_count: int = 0
    link_count: int = 0
    toc: int = 0
    entry_count: int = 0
    problems: tuple[Problem, ...] = ()


@dataclass(frozen=True)
class Entry:
    """Satu baris registry referensi."""

    label: str
    url: str
    line: int


@dataclass(frozen=True)
class Fence:
    """Satu code fence dengan nomor baris pembuka dan penutup."""

    opening_line: int
    closing_line: int
    info: str
    closed: bool


def _mask(pattern: re.Pattern[str], text: str) -> str:
    """Ganti bagian yang cocok dengan spasi tanpa mengubah nomor baris."""

    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return pattern.sub(blank, text)


def _fences(text: str) -> list[Fence]:
    """Kembalikan code fence dengan aturan panjang penutup CommonMark."""
    result: list[Fence] = []
    active: tuple[str, int, int, str] | None = None
    line = text.splitlines()
    for number, content in enumerate(line, 1):
        match = FENCE_PATTERN.match(content)
        if active is None:
            if match is not None:
                token = match.group("pagar")
                active = (token[0], len(token), number, match.group("info").strip())
            continue
        if (
            match is not None
            and match.group("pagar")[0] == active[0]
            and len(match.group("pagar")) >= active[1]
            and not match.group("info").strip()
        ):
            result.append(Fence(active[2], number, active[3], True))
            active = None
    if active is not None:
        result.append(Fence(active[2], len(line), active[3], False))
    return result


def _strip_fences(text: str) -> str:
    """Kosongkan seluruh code fence tanpa mengubah jumlah baris."""
    line = text.splitlines(keepends=True)
    for fence in _fences(text):
        for position in range(fence.opening_line - 1, fence.closing_line):
            if position < len(line):
                ending = "\n" if line[position].endswith("\n") else ""
                line[position] = ending
    return "".join(line)


def _strip_code(text: str) -> str:
    """Kosongkan code fence, komentar HTML, dan inline code."""
    text = _strip_fences(text)
    text = _mask(COMMENT_PATTERN, text)
    return _mask(INLINE_CODE_PATTERN, text)


def _link_target(match: re.Match[str]) -> str:
    angled = match.group("bersudut")
    if angled is not None:
        return angled
    return match.group("polos") or ""


def _relative_target(target: str) -> str | None:
    """Kembalikan path relatif yang harus diperiksa, atau None bila dilewati."""
    target = target.strip()
    if not target or target.startswith("#") or target.startswith("//"):
        return None
    if SCHEME_PATTERN.match(target):
        return None
    path = target.split("#", 1)[0].split("?", 1)[0]
    if not path or path.startswith("/"):
        return None
    return unquote(path)


def _document_files(root: Path) -> list[Path]:
    """Daftar README dan dokumen Markdown aktif di luar arsip."""
    root = root.resolve()
    archive = (root / ARCHIVE_DIR).resolve()
    candidates = [root / ROOT_DOCUMENT]
    directory = root / DOCS_DIR
    if directory.is_dir():
        candidates.extend(sorted(directory.rglob("*.md")))
    src_dir = root / SRC_DIR
    if src_dir.is_dir():
        candidates.extend(sorted(src_dir.rglob("README.md")))
    candidates.extend(root / path for path in MODULE_READMES)
    files: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if not path.is_file() or path in seen or path.is_relative_to(archive):
            continue
        seen.add(path)
        files.append(path)
    return files


def _heading_text(text: str) -> str:
    """Ambil teks yang terlihat dari heading Markdown."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("`", "")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)__(.+?)__(?!\w)", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    return text.strip()


def _heading_slug(text: str) -> str:
    """Ubah teks heading menjadi slug anchor gaya GitHub."""
    text = _heading_text(text).lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _document_headings(text: str) -> list[tuple[int, int, str]]:
    """Kembalikan pasangan (baris, level, slug) untuk setiap heading."""
    text = _mask(COMMENT_PATTERN, _strip_fences(text))
    heading: list[tuple[int, int, str]] = []
    seen: dict[str, int] = {}
    for number, line in enumerate(text.splitlines(), 1):
        match = HEADING_PATTERN.match(line)
        if match is None:
            continue
        level = len(match.group("pagar"))
        slug = _heading_slug(match.group("teks"))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        if count:
            slug = f"{slug}-{count}"
        heading.append((number, level, slug))
    return heading


def _check_headings(text: str, name: str) -> list[Problem]:
    """Pastikan dokumen punya tepat satu judul level 1 di luar code fence."""
    count = sum(1 for _, level, _ in _document_headings(text) if level == 1)
    if count == 1:
        return []
    return [Problem(name, 0, f"judul level 1 harus tepat satu, ditemukan {count}")]


def _check_fences(text: str, name: str) -> list[Problem]:
    """Pastikan setiap code fence ditutup dan punya bahasa."""
    problems: list[Problem] = []
    for fence in _fences(text):
        if not fence.closed:
            problems.append(Problem(name, fence.opening_line, "code fence tidak ditutup"))
        elif not fence.info:
            problems.append(Problem(name, fence.opening_line, "code fence tanpa bahasa"))
    return problems


def check_file_toc(text: str, name: str) -> tuple[int, list[Problem]]:
    """Periksa keberadaan TOC dan validitas anchor untuk satu dokumen."""
    line = text.splitlines()
    heading = _document_headings(text)
    index = next(
        (position for position, (_, _, slug) in enumerate(heading) if slug in TOC_SLUGS),
        None,
    )
    if index is None:
        if len(line) > TOC_THRESHOLD:
            return 0, [Problem(name, 0, f"dokumen {len(line)} baris tanpa daftar isi")]
        return 0, []
    toc_line, level_toc, _ = heading[index]
    anchor_heading = {slug for _, _, slug in heading}
    limit = len(line) + 1
    for number, level, _ in heading[index + 1 :]:
        if level <= level_toc:
            limit = number
            break
    count = 0
    problems: list[Problem] = []
    for number in range(toc_line + 1, limit):
        match = TOC_LINK_PATTERN.match(line[number - 1])
        if match is None:
            continue
        anchor = match.group("anchor")
        if anchor not in anchor_heading:
            problems.append(Problem(name, number, f"anchor daftar isi tidak valid: #{anchor}"))
        count += 1
    if not count:
        problems.append(Problem(name, toc_line, "daftar isi tidak berisi tautan anchor"))
    return 1, problems


def check_file_links(text: str, path: Path, name: str) -> tuple[int, list[Problem]]:
    """Periksa tautan relatif dalam satu teks Markdown."""
    cleaned = _strip_code(text)
    count = 0
    problems: list[Problem] = []
    for match in LINK_PATTERN.finditer(cleaned):
        relative = _relative_target(_link_target(match))
        if relative is None:
            continue
        count += 1
        target = path.parent / relative
        if not target.exists():
            line = cleaned.count("\n", 0, match.start()) + 1
            problems.append(Problem(name, line, f"tautan rusak: {relative}"))
    return count, problems


def _page_target(path: Path) -> Path | None:
    """Resolve tautan ke berkas Markdown, termasuk tautan direktori."""
    if path.is_dir():
        path = path / "README.md"
    if path.suffix == ".md" and path.is_file():
        return path
    return None


def _page_links(text: str, path: Path) -> set[Path]:
    """Kumpulkan target Markdown yang resolve dari satu dokumen."""
    result: set[Path] = set()
    for match in LINK_PATTERN.finditer(_strip_code(text)):
        relative = _relative_target(_link_target(match))
        if relative is None:
            continue
        target = _page_target(path.parent / relative)
        if target is not None:
            result.add(target)
    return result


def _check_index(root: Path) -> list[Problem]:
    """Pastikan semua halaman docs terjangkau dari `docs/README.md`."""
    directory = root / DOCS_DIR
    if not directory.is_dir():
        return []
    index = root / MAIN_INDEX
    if not index.is_file():
        return [Problem(MAIN_INDEX.as_posix(), 0, "indeks dokumentasi tidak ditemukan")]
    page = {
        path.resolve()
        for path in directory.rglob("*.md")
        if not path.resolve().is_relative_to((root / ARCHIVE_DIR).resolve())
    }
    seen: set[Path] = set()
    queue = [index.resolve()]
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        for target in _page_links(path.read_text(encoding="utf-8"), path):
            if target.resolve() in page and target.resolve() not in seen:
                queue.append(target.resolve())
    problems: list[Problem] = []
    for path in sorted(page - seen):
        problems.append(
            Problem(
                path.relative_to(root.resolve()).as_posix(),
                0,
                "halaman tidak terjangkau dari docs/README.md",
            )
        )
    return problems


def check_documents(root: Path = REPO_ROOT) -> Result:
    """Periksa tautan, TOC, judul, code fence, dan indeks dokumentasi."""
    root = root.resolve()
    file_count = 0
    total_links = 0
    toc_count = 0
    problems: list[Problem] = []
    for path in _document_files(root):
        name = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        link_count, findings = check_file_links(text, path, name)
        toc, toc_findings = check_file_toc(text, name)
        file_count += 1
        total_links += link_count
        toc_count += toc
        problems.extend(findings)
        problems.extend(toc_findings)
        problems.extend(_check_headings(text, name))
        problems.extend(_check_fences(text, name))
    problems.extend(_check_index(root))
    return Result(
        file_count=file_count,
        link_count=total_links,
        toc=toc_count,
        problems=tuple(problems),
    )


def _table_columns(row: str) -> list[str] | None:
    content = row.strip()
    if "|" not in content:
        return None
    if content.startswith("|"):
        content = content[1:]
    if content.endswith("|"):
        content = content[:-1]
    return [column.strip() for column in content.split("|")]


def _is_separator_row(columns: list[str]) -> bool:
    return bool(columns) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in columns)


def read_registry(text: str) -> list[Entry]:
    """Ambil entri dari tabel tiga kolom `Label | URL | Dipakai untuk`."""
    entries: list[Entry] = []
    for number, line in enumerate(text.splitlines(), 1):
        columns = _table_columns(line)
        if columns is None or len(columns) != 3 or _is_separator_row(columns):
            continue
        if [content.casefold() for content in columns[:2]] == ["label", "url"]:
            continue
        entries.append(Entry(label=columns[0], url=columns[1], line=number))
    return entries


def _url_valid(url: str) -> bool:
    if not url or any(character.isspace() for character in url):
        return False
    try:
        result = urlsplit(url)
        _ = result.port
    except ValueError:
        return False
    return result.scheme in {"http", "https"} and bool(result.hostname)


def check_registry(path: Path = REPO_ROOT / REGISTRY_FILE) -> Result:
    """Periksa sintaks URL, label unik, dan URL unik di registry."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Result(problems=(Problem(REGISTRY_FILE.as_posix(), 0, "registry tidak ditemukan"),))
    entries = read_registry(text)
    name = REGISTRY_FILE.as_posix()
    problems: list[Problem] = []
    if not entries:
        problems.append(Problem(name, 0, "registry tidak berisi entri tabel"))
    seen_labels: dict[str, Entry] = {}
    seen_urls: dict[str, Entry] = {}
    for item in entries:
        url = item.url.removeprefix("<").removesuffix(">")
        if not item.label:
            problems.append(Problem(name, item.line, "label registry kosong"))
        label_key = item.label.casefold()
        if label_key in seen_labels:
            problems.append(Problem(name, item.line, f"label duplikat: {item.label}"))
        else:
            seen_labels[label_key] = item
        if not _url_valid(url):
            problems.append(
                Problem(name, item.line, f"URL tidak valid (harus http/https): {item.url}")
            )
            continue
        if url in seen_urls:
            problems.append(Problem(name, item.line, f"URL duplikat: {url}"))
        else:
            seen_urls[url] = item
    return Result(file_count=1, entry_count=len(entries), problems=tuple(problems))


def check(root: Path = REPO_ROOT) -> Result:
    """Periksa dokumentasi dan registry di bawah akar repo."""
    root = root.resolve()
    document = check_documents(root)
    registry = check_registry(root / REGISTRY_FILE)
    return Result(
        file_count=document.file_count,
        link_count=document.link_count,
        toc=document.toc,
        entry_count=registry.entry_count,
        problems=document.problems + registry.problems,
    )


def main(argv: list[str] | None = None) -> int:
    """Jalankan checker dan kembalikan kode keluar 0 atau 1."""
    parser = argparse.ArgumentParser(
        prog="check_docs.py",
        description="Periksa tautan, TOC, judul, code fence, indeks, dan registry dokumentasi.",
    )
    parser.add_argument("root", nargs="?", type=Path, default=REPO_ROOT, help="akar repo")
    args = parser.parse_args(argv)
    result = check(args.root)
    print(f"Dokumen diperiksa: {result.file_count}")
    print(f"Tautan relatif diperiksa: {result.link_count}")
    print(f"TOC diperiksa: {result.toc}")
    print(f"Entri registry: {result.entry_count}")
    if result.problems:
        print(f"Broken: {len(result.problems)}")
        for problem in sorted(
            result.problems, key=lambda item: (item.file, item.line, item.message)
        ):
            print(f"- {problem}")
        return 1
    print("Broken: 0")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))
