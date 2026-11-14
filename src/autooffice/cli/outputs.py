"""Penamaan output final, intermediate, state, dan helper tulis atomik."""

import contextlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from . import CliError

_INVALID_REPORT_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_ASSET_FIELDS: dict[str, str] = {
    "image": "path",
    "diagram": "source",
}
_ASSET_ROOTS = ("assets", "diagrams")
_MAX_OUTPUT_STEM_LENGTH = 200
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CLOCK$",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


@dataclass(frozen=True, slots=True)
class DocxOutputs:
    """Path output satu build Markdown/DOCX."""

    source: Path
    output_dir: Path
    docx: Path
    pdf: Path
    manifest: Path
    terms: Path
    build_dir: Path

    @property
    def intermediate_docx(self) -> Path:
        """DOCX intermediate untuk target PDF tanpa DOCX final."""
        return self.build_dir / self.docx.name


@dataclass(frozen=True, slots=True)
class DeckOutputs:
    """Path output, state, cache, review, dan intermediate satu build deck."""

    source: Path
    output_dir: Path
    pptx: Path
    pdf: Path
    transcript: Path
    staging: Path
    state: Path
    cache: Path
    review_dir: Path
    build_dir: Path

    @property
    def intermediate_pptx(self) -> Path:
        """PPTX intermediate untuk target PDF tanpa target PPTX final."""
        return self.build_dir / f"{self.source.stem}.pptx"


@dataclass(frozen=True, slots=True)
class AssetReference:
    """Satu referensi aset relatif yang ditemukan pada block deck."""

    relative_path: str
    slide_id: str
    block_id: str
    block_type: str

    @property
    def key(self) -> str:
        """Namespace block pemilik aset."""
        return f"{self.slide_id}.{self.block_id}"


@dataclass(frozen=True, slots=True)
class MissingAsset:
    """Satu aset deck yang tidak ada atau keluar dari direktori deck."""

    reference: AssetReference
    absolute_path: Path
    reason: str

    def format(self) -> str:
        """Format temuan aset dengan slide, block, path relatif, dan absolut."""
        reference = self.reference
        return (
            f"slide '{reference.slide_id}', block '{reference.block_id}': "
            f"{self.reason}: {reference.relative_path} (resolved: {self.absolute_path})"
        )


def resolve_output_directory(source: Path, out: Path | None) -> Path:
    """Tentukan direktori output final sesuai perilaku docgen dan plan 10.4.

    ``--out`` menimpa direktori final. Tanpa ``--out``, input di
    ``examples/<nama>/`` memakai ``out/``; input lain memakai direktori input.
    Path yang sudah ada tetapi bukan direktori ditolak sebelum build.
    """
    if out is not None:
        expanded = out.expanduser()
        if expanded.exists() and not expanded.is_dir():
            raise CliError(
                f"--out harus direktori, bukan berkas: {expanded}",
                code="CLI-OUT-NOT-DIR",
                exit_code=2,
            )
        return expanded

    parent = source.parent
    if parent.parent.name == "examples":
        return parent / "out"
    return parent


def docx_outputs(
    source: Path,
    report_name: str,
    out: Path | None = None,
) -> DocxOutputs:
    """Bangun path DOCX/PDF, manifest, istilah, dan intermediate.

    Nama final berasal dari ``report_name`` front matter. Manifest, istilah,
    dan ``.laporan-build`` tetap berada di samping dokumen sumber walaupun
    ``--out`` diberikan, persis seperti perilaku docgen.
    """
    name = _safe_report_name(report_name, source)
    output_dir = resolve_output_directory(source, out)
    document_dir = source.parent
    build_dir = _safe_workspace_root(
        source,
        document_dir,
        ".laporan-build",
        protected=(output_dir,),
    )
    return DocxOutputs(
        source=source,
        output_dir=output_dir,
        docx=output_dir / f"{name}.docx",
        pdf=output_dir / f"{name}.pdf",
        manifest=document_dir / ".laporan" / "manifest.json",
        terms=document_dir / ".laporan" / "istilah-baru.txt",
        build_dir=build_dir,
    )


def deck_outputs(source: Path, out: Path | None = None) -> DeckOutputs:
    """Bangun path deck final, staging, state, cache, review, dan intermediate.

    State dan cache selalu berada di samping YAML agar ``--out`` tidak
    mengubah identitas state. Intermediate berada di samping YAML, atau di
    bawah ``--out`` bila diberikan.
    """
    stem = _input_stem(source)
    _validate_output_stem(stem, source, code="CLI-INPUT-NAME", label="nama berkas input")
    output_dir = resolve_output_directory(source, out)
    document_dir = source.parent
    state_root = _safe_state_root(document_dir, source)
    build_dir = _safe_build_directory(
        source,
        document_dir,
        ".autooffice-build",
        stem,
        protected=(output_dir,),
    )
    return DeckOutputs(
        source=source,
        output_dir=output_dir,
        pptx=output_dir / f"{stem}.pptx",
        pdf=output_dir / f"{stem}.pdf",
        transcript=output_dir / f"{stem}.transcript.md",
        staging=output_dir / f"{stem}.slides-upload.pptx",
        state=state_root / "state" / f"{stem}.json",
        cache=state_root / "cache",
        review_dir=state_root / "review",
        build_dir=build_dir,
    )


def planned_docx_files(
    outputs: DocxOutputs,
    targets: tuple[str, ...],
    *,
    terms: bool,
    keep_intermediate: bool = False,
) -> tuple[Path, ...]:
    """Daftar file final yang akan ditulis build Markdown.

    DOCX intermediate hanya dilaporkan untuk target PDF tanpa DOCX final dan
    hanya bila ``--keep-intermediate`` mempertahankannya.
    """
    paths: list[Path] = []
    if "docx" in targets:
        paths.append(outputs.docx)
    if "pdf" in targets:
        paths.append(outputs.pdf)
    paths.append(outputs.manifest)
    if terms:
        paths.append(outputs.terms)
    if "pdf" in targets and "docx" not in targets and keep_intermediate:
        paths.append(outputs.intermediate_docx)
    return _deduplicate(paths)


def planned_deck_files(
    outputs: DeckOutputs,
    targets: tuple[str, ...],
    *,
    keep_intermediate: bool = False,
    sync_mode: str = "",
) -> tuple[Path, ...]:
    """Daftar artefak yang akan ditulis build deck pada target yang diminta.

    Staging Slides dan PPTX intermediate PDF hanya masuk daftar bila
    ``--keep-intermediate`` aktif. File review sync masuk daftar untuk mode
    ``pull``, ``diff``, dan ``apply``.
    """
    paths: list[Path] = []
    if "pptx" in targets:
        paths.append(outputs.pptx)
    if "pdf" in targets:
        paths.append(outputs.pdf)
    sync_only = sync_mode in {"diff", "pull", "apply"}
    if not sync_only and (outputs.source.parent / "transcripts.md").is_file():
        paths.append(outputs.transcript)
    if "pdf" in targets and "pptx" not in targets and keep_intermediate:
        paths.append(outputs.intermediate_pptx)
    if "slides" in targets:
        sync_path = deck_sync_path(outputs, sync_mode)
        if sync_path is not None:
            paths.append(sync_path)
        paths.append(outputs.state)
        if sync_mode in {"", "push"} and keep_intermediate:
            paths.append(outputs.staging)
    return _deduplicate(paths)


def deck_sync_path(outputs: DeckOutputs, sync_mode: str) -> Path | None:
    """Path laporan review untuk mode sync non-push."""
    stem = outputs.source.stem
    if sync_mode == "pull":
        return outputs.review_dir / f"{stem}.pulled.yaml"
    if sync_mode == "diff":
        return outputs.review_dir / f"{stem}.diff.json"
    if sync_mode == "apply":
        return outputs.review_dir / f"{stem}.applied.yaml"
    return None


def deck_asset_references(deck: Any) -> tuple[AssetReference, ...]:
    """Kumpulkan referensi gambar dan diagram dalam urutan slide dan block."""
    references: list[AssetReference] = []
    for slide in getattr(deck, "slides", ()):
        for block in getattr(slide, "blocks", ()):
            field_name = _ASSET_FIELDS.get(str(getattr(block, "block_type", "")))
            if field_name is None:
                continue
            fields = getattr(block, "fields", {})
            value = fields.get(field_name) if hasattr(fields, "get") else None
            if not isinstance(value, str) or not value:
                continue
            references.append(
                AssetReference(
                    relative_path=value,
                    slide_id=str(getattr(slide, "slide_id", "")),
                    block_id=str(getattr(block, "block_id", "")),
                    block_type=str(getattr(block, "block_type", "")),
                )
            )
    return tuple(references)


def missing_deck_assets(deck: Any, deck_root: Path) -> tuple[MissingAsset, ...]:
    """Validasi keberadaan setiap aset relatif terhadap direktori deck."""
    root = deck_root.resolve()
    missing: list[MissingAsset] = []
    for reference in deck_asset_references(deck):
        pure = PurePosixPath(reference.relative_path)
        candidate = root / reference.relative_path
        try:
            resolved = candidate.resolve()
        except OSError, RuntimeError:
            missing.append(
                MissingAsset(
                    reference=reference,
                    absolute_path=candidate.absolute(),
                    reason="path aset tidak dapat di-resolve",
                )
            )
            continue
        if (
            pure.is_absolute()
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            missing.append(
                MissingAsset(
                    reference=reference,
                    absolute_path=resolved,
                    reason="path aset keluar dari direktori deck",
                )
            )
            continue
        if not resolved.is_relative_to(root):
            missing.append(
                MissingAsset(
                    reference=reference,
                    absolute_path=resolved,
                    reason="path aset keluar dari direktori deck",
                )
            )
            continue
        if not resolved.is_file():
            missing.append(
                MissingAsset(
                    reference=reference,
                    absolute_path=resolved,
                    reason="aset tidak ditemukan",
                )
            )
    return tuple(missing)


def format_missing_assets(missing: tuple[MissingAsset, ...] | list[MissingAsset]) -> str:
    """Gabungkan temuan aset menjadi satu pesan yang menyebut slide dan block."""
    return "; ".join(item.format() for item in missing)


def stage_deck_assets(source: Path, deck: Any, workspace: Path) -> tuple[Path, ...]:
    """Salin ``assets/`` dan ``diagrams/`` ke workspace render.

    Semua referensi divalidasi lebih dulu. File yang dirujuk di luar dua pohon
    standar tetap disalin ke path relatif yang sama agar renderer selalu
    workspace-relative. Symlink/junction tidak pernah diikuti: link pada pohon
    aset atau komponen path referensi ditolak sebelum penyalinan.
    """
    deck_root = source.parent
    missing = missing_deck_assets(deck, deck_root)
    if missing:
        raise CliError(
            format_missing_assets(missing),
            code="CLI-ASSET",
            exit_code=1,
            path=str(source),
        )
    asset_roots: list[Path] = []
    for name in _ASSET_ROOTS:
        asset_root = deck_root / name
        if not asset_root.exists():
            continue
        if not asset_root.is_dir():
            raise CliError(
                f"pohon aset bukan direktori: {asset_root}",
                code="CLI-ASSET-STAGE",
                exit_code=1,
                path=str(asset_root),
            )
        _reject_asset_links(asset_root, source)
        asset_roots.append(asset_root)
    references = deck_asset_references(deck)
    for reference in references:
        _reject_reference_links(deck_root, reference.relative_path, source)
    if _is_link(workspace):
        raise CliError(
            f"workspace build tidak boleh symlink/junction: {workspace}",
            code="CLI-ASSET-STAGE",
            exit_code=1,
            path=str(source),
        )

    root = ensure_directory(workspace).resolve()
    staged: list[Path] = []
    for asset_root in asset_roots:
        destination = root / asset_root.name
        _require_path_within(root, destination, source)
        _copy_asset_tree(asset_root, destination, root, source)
        staged.append(destination)
    for reference in references:
        relative_path = reference.relative_path.replace("\\", "/")
        destination = root / PurePosixPath(relative_path)
        if _is_link(destination):
            raise CliError(
                f"tujuan aset tidak boleh symlink/junction: {destination}",
                code="CLI-ASSET-LINK",
                exit_code=1,
                path=str(source),
            )
        if destination.is_file():
            continue
        asset_source = deck_root / relative_path
        resolved_source = asset_source.resolve()
        _require_path_within(root, destination, source)
        ensure_directory(destination.parent)
        _require_path_within(root, destination.parent, source)
        try:
            shutil.copy2(resolved_source, destination)
        except OSError as exc:
            raise CliError(
                f"aset tidak dapat disalin ke workspace build: {resolved_source} -> "
                f"{destination}: {exc}",
                code="CLI-ASSET-STAGE",
                exit_code=1,
                path=str(resolved_source),
            ) from exc
        staged.append(destination)
    return _deduplicate(staged)


def _copy_asset_tree(
    source: Path,
    destination: Path,
    workspace_root: Path,
    deck_source: Path,
) -> None:
    try:
        _require_path_within(workspace_root, destination, deck_source)
        if destination.exists() and not destination.is_dir():
            raise OSError(f"tujuan bukan direktori: {destination}")
        _require_path_within(workspace_root, destination, deck_source)
        shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True)
    except OSError as exc:
        raise CliError(
            f"pohon aset tidak dapat disalin ke workspace build: {source} -> {destination}: {exc}",
            code="CLI-ASSET-STAGE",
            exit_code=1,
            path=str(source),
        ) from exc


def _reject_asset_links(asset_root: Path, source: Path) -> None:
    """Tolak symlink/junction di seluruh pohon aset tanpa mengikutinya."""

    if _is_link(asset_root):
        raise CliError(
            f"pohon aset tidak boleh berupa symlink/junction: {asset_root}",
            code="CLI-ASSET-LINK",
            exit_code=1,
            path=str(source),
        )
    for current, directories, files in os.walk(asset_root, followlinks=False):
        current_path = Path(current)
        for name in (*directories, *files):
            candidate = current_path / name
            if _is_link(candidate):
                raise CliError(
                    f"pohon aset memuat symlink/junction yang tidak diizinkan: {candidate}",
                    code="CLI-ASSET-LINK",
                    exit_code=1,
                    path=str(source),
                )


def _reject_reference_links(deck_root: Path, relative_path: str, source: Path) -> None:
    """Tolak symlink/junction pada komponen path aset yang dirujuk."""

    current = deck_root
    for part in PurePosixPath(relative_path.replace("\\", "/")).parts:
        current = current / part
        if _is_link(current):
            raise CliError(
                f"aset merujuk symlink/junction yang tidak diizinkan: {current}",
                code="CLI-ASSET-LINK",
                exit_code=1,
                path=str(source),
            )


def _require_path_within(root: Path, path: Path, source: Path) -> None:
    """Pastikan path hasil resolve masih berada di bawah workspace build."""

    try:
        resolved_root = root.resolve()
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise CliError(
            f"path workspace build tidak dapat di-resolve: {path}: {exc}",
            code="CLI-ASSET-STAGE",
            exit_code=1,
            path=str(source),
        ) from exc
    if resolved != resolved_root and not resolved.is_relative_to(resolved_root):
        raise CliError(
            f"path workspace build keluar dari direktori build: {path} -> {resolved}",
            code="CLI-ASSET-STAGE",
            exit_code=1,
            path=str(source),
        )


def ensure_directory(path: Path) -> Path:
    """Buat direktori output bila belum ada dan kembalikan path-nya."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CliError(
            f"direktori output tidak dapat dibuat: {exc}",
            code="CLI-OUT-CREATE",
            exit_code=2,
            path=str(path),
        ) from exc
    if not path.is_dir():
        raise CliError(
            f"path output bukan direktori: {path}",
            code="CLI-OUT-NOT-DIR",
            exit_code=2,
            path=str(path),
        )
    return path


def atomic_write_text(path: Path, text: str) -> Path:
    """Tulis teks UTF-8 secara atomik ke ``path``."""
    return atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    """Tulis byte secara atomik memakai file sementara di direktori tujuan.

    File sementara di-flush dan di-``fsync`` sebelum ``os.replace``. Kegagalan
    serialisasi/penulisan apa pun membersihkan file sementara, bukan hanya
    ``OSError``.
    """
    ensure_directory(path.parent)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception as exc:
        _remove_temporary(temporary)
        raise CliError(
            f"file output tidak dapat ditulis: {path}: {exc}",
            code="CLI-OUT-WRITE",
            exit_code=1,
            path=str(path),
        ) from exc
    return path


def atomic_copy(source: Path, destination: Path) -> Path:
    """Salin file secara atomik dan pertahankan isi byte demi byte."""
    ensure_directory(destination.parent)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            with source.open("rb") as reader:
                shutil.copyfileobj(reader, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception as exc:
        _remove_temporary(temporary)
        raise CliError(
            f"file tidak dapat disalin ke {destination}: {exc}",
            code="CLI-OUT-COPY",
            exit_code=1,
            path=str(source),
        ) from exc
    return destination


def _remove_temporary(temporary: Path | None) -> None:
    if temporary is None:
        return
    with contextlib.suppress(OSError):
        temporary.unlink(missing_ok=True)


def _safe_report_name(report_name: str, source: Path) -> str:
    text = report_name.strip()
    if not text:
        raise CliError(
            "report_name kosong; isi front matter sebelum build",
            code="CLI-REPORT-NAME",
            exit_code=2,
            path=str(source),
        )
    if _INVALID_REPORT_NAME.search(text) or Path(text).name != text:
        raise CliError(
            f"report_name tidak aman sebagai nama berkas: {report_name!r}",
            code="CLI-REPORT-NAME",
            exit_code=2,
            path=str(source),
        )
    _validate_output_stem(text, source, code="CLI-REPORT-NAME", label="report_name")
    return text


def _input_stem(source: Path) -> str:
    """Ambil stem input dengan menghapus ekstensi yang didukung.

    ``Path.stem`` tidak menghapus suffix pada nama berawalan titik, sehingga
    ``..yaml`` menghasilkan ``..yaml``. Kontrak CLI memakai nama tanpa
    ekstensi secara literal agar ``..yaml``/``...yaml`` dapat ditolak.
    """

    name = source.name
    lowered = name.casefold()
    for suffix in (".yaml", ".md"):
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return source.stem


def _validate_output_stem(
    stem: str,
    source: Path,
    *,
    code: str,
    label: str,
) -> None:
    candidate = stem.rstrip(" .")
    if not candidate or candidate in {".", ".."}:
        raise CliError(
            f"{label} tidak memiliki stem yang aman: {stem!r}",
            code=code,
            exit_code=2,
            path=str(source),
        )
    if candidate != stem:
        raise CliError(
            f"{label} tidak boleh berakhir dengan spasi atau titik: {stem!r}",
            code=code,
            exit_code=2,
            path=str(source),
        )
    if _utf16_length(candidate) > _MAX_OUTPUT_STEM_LENGTH:
        raise CliError(
            f"{label} terlalu panjang (maksimum {_MAX_OUTPUT_STEM_LENGTH} karakter): {candidate!r}",
            code=code,
            exit_code=2,
            path=str(source),
        )
    base = candidate.split(".", 1)[0].rstrip(" .").upper()
    if base in _WINDOWS_RESERVED_NAMES:
        raise CliError(
            f"{label} memakai nama perangkat Windows yang dicadangkan: {stem!r}",
            code=code,
            exit_code=2,
            path=str(source),
        )


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction is not None and is_junction())


def _resolve_document_directory(
    document_dir: Path,
    *,
    code: str,
    source: Path,
) -> Path:
    """Resolve direktori dokumen sekali agar identitas child dapat dibandingkan."""

    try:
        return document_dir.resolve()
    except (OSError, RuntimeError) as exc:
        raise CliError(
            f"direktori dokumen tidak dapat di-resolve: {document_dir}: {exc}",
            code=code,
            exit_code=2,
            path=str(source),
        ) from exc


def _require_exact_internal_path(
    path: Path,
    expected: Path,
    *,
    document_dir: Path,
    code: str,
    source: Path,
) -> Path:
    """Resolve ``path`` dan wajibkan identitasnya tepat sama dengan ``expected``.

    Root internal (``.autooffice``, ``.autooffice-build``, ``.laporan-build``)
    boleh berupa symlink/junction hanya bila target hasil resolve memiliki
    parent dan nama yang persis sama dengan path yang diharapkan. Junction ke
    ``.git``, ``assets``, direktori dokumen, atau nama lain ditolak agar
    ``rmtree`` tidak pernah menghapus path di luar identitas workspace.
    """

    is_link = _is_link(path)
    try:
        resolved = path.resolve(strict=True) if is_link else path.resolve()
    except (OSError, RuntimeError) as exc:
        raise CliError(
            f"path internal tidak dapat di-resolve: {path}: {exc}",
            code=code,
            exit_code=2,
            path=str(source),
        ) from exc
    if resolved == expected:
        return resolved
    if resolved == document_dir or not resolved.is_relative_to(document_dir):
        raise CliError(
            f"symlink/junction keluar dari direktori deck: {path} -> {resolved}",
            code=code,
            exit_code=2,
            path=str(source),
        )
    raise CliError(
        f"symlink/junction tidak menunjuk ke path internal yang diharapkan: "
        f"{path} -> {resolved} (diharapkan {expected})",
        code=code,
        exit_code=2,
        path=str(source),
    )


def _safe_state_root(document_dir: Path, source: Path) -> Path:
    """Resolve ``.autooffice`` dan subdir state dengan identitas yang tetap."""

    resolved_document = _resolve_document_directory(
        document_dir,
        code="CLI-STATE-PATH",
        source=source,
    )
    state_root = resolved_document / ".autooffice"
    resolved_state = _require_exact_internal_path(
        state_root,
        state_root,
        document_dir=resolved_document,
        code="CLI-STATE-PATH",
        source=source,
    )
    for parts in (("state",), ("cache",), ("review",), ("cache", "mermaid")):
        expected = resolved_state.joinpath(*parts)
        _require_exact_internal_path(
            expected,
            expected,
            document_dir=resolved_document,
            code="CLI-STATE-PATH",
            source=source,
        )
    return resolved_state


def _safe_workspace_root(
    source: Path,
    document_dir: Path,
    root_name: str,
    *,
    protected: tuple[Path, ...] = (),
) -> Path:
    """Resolve root workspace tetap (mis. ``.laporan-build``) dengan aman.

    Root harus memiliki identitas ``<document_dir>/<root_name>`` setelah
    resolve. Link yang dialihkan ke ``.git``, ``assets``, direktori dokumen,
    atau nama lain ditolak walaupun targetnya masih di bawah dokumen.
    """

    resolved_document = _resolve_document_directory(
        document_dir,
        code="CLI-BUILD-PATH",
        source=source,
    )
    root = document_dir / root_name
    resolved_root = _require_exact_internal_path(
        root,
        resolved_document / root_name,
        document_dir=resolved_document,
        code="CLI-BUILD-PATH",
        source=source,
    )
    if root.exists() and not root.is_dir():
        raise CliError(
            f"root build bukan direktori: {root}",
            code="CLI-BUILD-PATH",
            exit_code=2,
            path=str(source),
        )
    try:
        resolved_source = source.resolve()
        protected_paths = tuple(path.resolve() for path in protected)
    except (OSError, RuntimeError) as exc:
        raise CliError(
            f"direktori build tidak dapat di-resolve: {root}: {exc}",
            code="CLI-BUILD-PATH",
            exit_code=2,
            path=str(source),
        ) from exc
    if resolved_root == resolved_document or not resolved_root.is_relative_to(resolved_document):
        raise CliError(
            f"root build keluar dari direktori dokumen: {resolved_root}",
            code="CLI-BUILD-PATH",
            exit_code=2,
            path=str(source),
        )
    if resolved_source == resolved_root or resolved_source.is_relative_to(resolved_root):
        raise CliError(
            f"root build memuat berkas sumber: {resolved_source}",
            code="CLI-BUILD-PATH",
            exit_code=2,
            path=str(source),
        )
    for protected_path in protected_paths:
        if protected_path == resolved_root or protected_path.is_relative_to(resolved_root):
            raise CliError(
                f"root build memuat output yang dilindungi: {protected_path}",
                code="CLI-BUILD-PATH",
                exit_code=2,
                path=str(source),
            )
    return resolved_root


def _safe_build_directory(
    source: Path,
    document_dir: Path,
    root_name: str,
    stem: str,
    *,
    protected: tuple[Path, ...] = (),
) -> Path:
    """Resolve direktori build dan pastikan selalu di bawah root build.

    Root build dan direktori hasil tidak boleh berupa symlink/junction yang
    keluar dari direktori dokumen. Path sumber, output, atau dokumen yang
    berada di dalam direktori build juga ditolak agar pembersihan tidak
    menghapus data pengguna.
    """

    _validate_output_stem(
        stem,
        source,
        code="CLI-BUILD-PATH",
        label="nama direktori build",
    )
    if Path(stem).name != stem:
        raise CliError(
            f"nama direktori build bukan satu komponen path: {stem!r}",
            code="CLI-BUILD-PATH",
            exit_code=2,
            path=str(source),
        )
    resolved_document = _resolve_document_directory(
        document_dir,
        code="CLI-BUILD-PATH",
        source=source,
    )
    build_root = document_dir / root_name
    resolved_root = _require_exact_internal_path(
        build_root,
        resolved_document / root_name,
        document_dir=resolved_document,
        code="CLI-BUILD-PATH",
        source=source,
    )
    if build_root.exists() and not build_root.is_dir():
        raise CliError(
            f"root build bukan direktori: {build_root}",
            code="CLI-BUILD-PATH",
            exit_code=2,
            path=str(source),
        )
    build_dir = resolved_root / stem
    resolved_build = _require_exact_internal_path(
        build_dir,
        resolved_root / stem,
        document_dir=resolved_document,
        code="CLI-BUILD-PATH",
        source=source,
    )
    try:
        resolved_source = source.resolve()
        protected_paths = tuple(path.resolve() for path in protected)
    except (OSError, RuntimeError) as exc:
        raise CliError(
            f"direktori build tidak dapat di-resolve: {build_dir}: {exc}",
            code="CLI-BUILD-PATH",
            exit_code=2,
            path=str(source),
        ) from exc
    if resolved_build == resolved_root or not resolved_build.is_relative_to(resolved_root):
        raise CliError(
            f"direktori build tidak berada di bawah root build: {resolved_build}",
            code="CLI-BUILD-PATH",
            exit_code=2,
            path=str(source),
        )
    if resolved_source == resolved_build or resolved_source.is_relative_to(resolved_build):
        raise CliError(
            f"direktori build memuat berkas sumber: {resolved_source}",
            code="CLI-BUILD-PATH",
            exit_code=2,
            path=str(source),
        )
    for protected_path in protected_paths:
        if protected_path == resolved_build or protected_path.is_relative_to(resolved_build):
            raise CliError(
                f"direktori build memuat output yang dilindungi: {protected_path}",
                code="CLI-BUILD-PATH",
                exit_code=2,
                path=str(source),
            )
    return resolved_build


def require_safe_build_directory(
    source: Path,
    build_dir: Path,
    root_name: str,
    *,
    per_stem: bool = True,
) -> Path:
    """Validasi ulang direktori build tepat sebelum pembersihan.

    Dipakai oleh ``build`` agar ``rmtree`` tidak pernah menyentuh sumber,
    output, atau path di luar ``<document_dir>/<root_name>``.
    """

    if not per_stem:
        if build_dir.name != root_name:
            raise CliError(
                f"workspace build bukan root yang diharapkan: {build_dir}",
                code="CLI-BUILD-PATH",
                exit_code=1,
                path=str(source),
            )
        safe_root = _safe_workspace_root(
            source,
            source.parent,
            root_name,
            protected=(source.parent,),
        )
        if _resolve_for_cleanup(build_dir, source) != safe_root:
            raise CliError(
                f"workspace build tidak cocok dengan root yang divalidasi: {build_dir}",
                code="CLI-BUILD-PATH",
                exit_code=1,
                path=str(source),
            )
        return safe_root
    stem = _input_stem(source)
    if build_dir.name != stem:
        raise CliError(
            f"direktori build tidak cocok dengan nama stem input: {build_dir}",
            code="CLI-BUILD-PATH",
            exit_code=1,
            path=str(source),
        )
    safe_build = _safe_build_directory(
        source,
        source.parent,
        root_name,
        stem,
        protected=(source.parent,),
    )
    if _resolve_for_cleanup(build_dir, source) != safe_build:
        raise CliError(
            f"direktori build tidak cocok dengan path yang divalidasi: {build_dir}",
            code="CLI-BUILD-PATH",
            exit_code=1,
            path=str(source),
        )
    return safe_build


def _resolve_for_cleanup(path: Path, source: Path) -> Path:
    """Resolve path cleanup dan bungkus kegagalan sebagai ``CliError``."""

    try:
        return path.resolve()
    except (OSError, RuntimeError) as exc:
        raise CliError(
            f"path build tidak dapat di-resolve sebelum dibersihkan: {path}: {exc}",
            code="CLI-BUILD-PATH",
            exit_code=1,
            path=str(source),
        ) from exc


def _deduplicate(paths: list[Path]) -> tuple[Path, ...]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return tuple(result)


__all__ = [
    "AssetReference",
    "DeckOutputs",
    "DocxOutputs",
    "MissingAsset",
    "atomic_copy",
    "atomic_write_bytes",
    "atomic_write_text",
    "deck_asset_references",
    "deck_outputs",
    "deck_sync_path",
    "docx_outputs",
    "ensure_directory",
    "format_missing_assets",
    "missing_deck_assets",
    "planned_deck_files",
    "planned_docx_files",
    "require_safe_build_directory",
    "resolve_output_directory",
    "stage_deck_assets",
]
