"""Stage ``pandoc``: Markdown materialized menjadi DOCX sementara.

Stage ini adalah satu-satunya jembatan Markdown -> DOCX. TOC, daftar
gambar/tabel, penomoran heading, dan sampul ditangani stage post-Pandoc.
Karena itu perintah di sini **tidak** memakai ``--lua-filter`` dan **tidak**
meminta Pandoc menulis TOC. Field TOC native ditulis ``stages/toc.py``;
daftar gambar/tabel ditulis ``stages/lists.py``.

Input Markdown diambil dari artifact ``markdown`` milik stage ``front_matter``
(yang sudah memuat hasil render Mermaid). ``reference.docx`` wajib berasal dari
artifact derived ``style_reference``, bukan langsung dari aset format. Hasil
Pandoc ditulis ke workspace agar pipeline dapat memuatnya sebagai satu
``DocumentPackage`` tanpa intermediate DOCX di direktori output.

Referensi: https://pandoc.org/MANUAL.html
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..errors import DocgenError, ExternalToolError, StageError, ToolMissingError
from ..package import DocumentPackage
from ..pipeline import BaseStage, StageContext, StageName, StageResult, canonical_prefix

__all__ = [
    "DEFAULT_TIMEOUT",
    "PANDOC_INSTALL_HINT",
    "PandocError",
    "PandocInvocation",
    "PandocStage",
    "build_pandoc_command",
    "build_pandoc_metadata",
    "find_pandoc",
    "resolve_bibliography",
    "run_pandoc",
    "write_metadata_file",
]

DEFAULT_TIMEOUT = 300
PANDOC_INSTALL_HINT = (
    "Pasang Pandoc dari https://pandoc.org/installing.html, lalu pastikan "
    "`pandoc` ada di PATH atau berikan path pandoc secara eksplisit."
)
METADATA_FILENAME = "pandoc-metadata.yml"
DEFAULT_BIBLIOGRAPHY_HEADING = "DAFTAR PUSTAKA"


class PandocError(ExternalToolError):
    """Pandoc tidak dapat dijalankan atau tidak menghasilkan DOCX valid."""

    default_code = "PANDOC"


@dataclass(frozen=True)
class PandocInvocation:
    """Parameter satu pemanggilan Pandoc.

    ``metadata_file`` sengaja opsional: stage selalu membuatnya, tetapi
    command builder tetap dapat dipakai untuk kebutuhan diagnosa tanpa file.
    """

    markdown: Path
    output: Path
    reference_docx: Path
    bibliography: Path | None = None
    csl: Path | None = None
    metadata_file: Path | None = None
    resource_paths: tuple[Path, ...] = ()
    timeout: int = DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# Pencarian executable dan metadata
# ---------------------------------------------------------------------------


def find_pandoc(explicit: str | Path | None = None) -> str | None:
    """Cari Pandoc dari path eksplisit, environment, PATH, lalu lokasi Windows."""

    if explicit is not None:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(str(explicit))
        if found is not None:
            return found
        return None

    for variable in ("DOCGEN_PANDOC", "PANDOC", "LAPORAN_PANDOC"):
        value = os.environ.get(variable)
        if not value:
            continue
        candidate = Path(value).expanduser()
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(value)
        if found is not None:
            return found

    found = shutil.which("pandoc")
    if found is not None:
        return found

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "Pandoc" / "pandoc.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _executable_command(executable: str | Path) -> list[str]:
    """Prefix executable; skrip Python dipakai untuk fake Pandoc di tes."""

    path = Path(executable)
    if path.suffix.lower() in {".py", ".pyw"}:
        return [sys.executable, str(path)]
    return [str(path)]


def _document_language(document: object) -> str:
    metadata = getattr(document, "metadata", None)
    value = getattr(metadata, "lang", None)
    return str(value) if value else "id-ID"


def _bibliography_heading(format_spec: object) -> str:
    bibliography_style = getattr(format_spec, "bibliography_style", None)
    value = getattr(bibliography_style, "heading", None)
    return str(value) if value else DEFAULT_BIBLIOGRAPHY_HEADING


def build_pandoc_metadata(
    document: object,
    format_spec: object,
    *,
    bibliography: Path | None = None,
) -> dict[str, object]:
    """Metadata front matter yang boleh dilihat Pandoc.

    ``front_matter`` sudah menulis sampul, kata pengantar, abstrak, dan
    identitas penulis sebagai blok Markdown. Mengirim ``title``/``author``/
    ``date`` ke Pandoc akan membuat title block bawaan sehingga sampul dan
    isi terduplikasi. Karena itu metadata di sini dibatasi pada nilai yang
    memang dipakai Pandoc/citeproc:

    - ``lang`` untuk locale citeproc;
    - ``reference-section-title`` dari ``format.bibliography_style.heading``
      bila dokumen memiliki bibliografi.
    """

    metadata: dict[str, object] = {"lang": _document_language(document)}
    if bibliography is not None:
        metadata["reference-section-title"] = _bibliography_heading(format_spec)
    return metadata


def write_metadata_file(path: str | Path, metadata: Mapping[str, object]) -> Path:
    """Tulis metadata Pandoc secara deterministik dan idempoten.

    JSON adalah subset YAML sehingga langsung diterima ``--metadata-file``.
    Tidak ada timestamp atau urutan dictionary yang berubah-ubah.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(
            dict(metadata),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    previous = target.read_text(encoding="utf-8") if target.is_file() else None
    if previous != text:
        target.write_text(text, encoding="utf-8", newline="\n")
    return target


# ---------------------------------------------------------------------------
# Resolusi input dari StageContext
# ---------------------------------------------------------------------------


def _artifact_path(ctx: object, key: str) -> Path | None:
    artifacts = getattr(ctx, "artifacts", None)
    if artifacts is None:
        return None
    try:
        keys = tuple(artifacts.keys())
    except AttributeError, TypeError:
        return None
    if key not in keys:
        return None
    value = artifacts.get(key)
    return Path(value)


def _markdown_path(ctx: object) -> Path:
    """Markdown hasil ``front_matter`` + ``mermaid`` dari satu sumber.

    Satu-satunya input adalah artifact ``markdown`` yang dideklarasikan stage
    ``front_matter``. Tidak ada fallback ke file workspace: artifact yang
    hilang atau bukan file selalu menjadi ``PANDOC-INPUT`` agar penyebabnya
    terlihat, bukan tertutup oleh file cadangan lama.
    """

    artifact = _artifact_path(ctx, "markdown")
    if artifact is None or not artifact.is_file():
        raise PandocError(
            "Markdown materialized untuk Pandoc tidak tersedia sebagai file "
            "artifact 'markdown'; jalankan stage front_matter/mermaid lebih dulu.",
            code="PANDOC-INPUT",
            path=artifact,
            key="markdown",
        )
    return artifact


def _reference_path(ctx: object) -> Path:
    reference = getattr(ctx, "reference_docx", None)
    if reference is None:
        reference = _artifact_path(ctx, "reference_docx")
    if reference is None:
        raise PandocError(
            "reference.docx derived belum tersedia; jalankan stage style_reference sebelum pandoc.",
            code="PANDOC-REFERENCE",
            key="reference_docx",
        )
    path = Path(reference)
    if not path.is_file():
        raise PandocError(
            "reference.docx derived tidak ditemukan di disk; jalankan ulang stage style_reference.",
            code="PANDOC-REFERENCE",
            path=path,
            key="reference_docx",
        )
    return path


def _resolve_existing(
    raw: str | Path,
    *,
    bases: Sequence[Path],
) -> Path | None:
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    for base in bases:
        resolved = (base / candidate).resolve()
        if resolved.is_file():
            return resolved
    return None


def resolve_bibliography(document: object, format_spec: object) -> Path | None:
    """Resolve ``document.bibliography`` atau default ``format.citation``.

    Path relatif dicari relatif terhadap direktori ``document.md`` lebih dulu,
    lalu direktori ``format.yml`` (asset package). Nilai yang dinyatakan tetapi
    tidak ditemukan adalah error, bukan warning: tanpa itu sitasi akan menjadi
    teks mentah di DOCX.
    """

    raw = getattr(document, "bibliography", None)
    explicit = raw is not None
    citation = getattr(format_spec, "citation", None)
    if raw is None:
        raw = getattr(citation, "bibliography", None)
    if raw is None:
        return None

    document_path = Path(getattr(document, "path", Path.cwd()))
    format_path = Path(getattr(format_spec, "path", document_path))
    bases = (document_path.parent, format_path.parent)
    resolved = _resolve_existing(str(raw), bases=bases)
    if resolved is None:
        if not explicit:
            # ``Document`` sudah membawa default format hanya bila struktur
            # memang memiliki back matter bibliografi. Dokument tanpa
            # bibliografi tidak boleh gagal karena aset format tidak ada.
            return None
        raise PandocError(
            f"bibliography tidak ditemukan: {raw!r}; periksa kunci "
            "'bibliography' atau sediakan references.bib di samping document.md.",
            code="PANDOC-BIBLIOGRAPHY",
            path=document_path,
            key="bibliography",
        )
    return resolved


def _resolve_csl(format_spec: object) -> Path:
    citation = getattr(format_spec, "citation", None)
    raw = getattr(citation, "csl", None)
    if raw is None:
        raise PandocError(
            "CSL format tidak tersedia; periksa citation.csl pada format.yml.",
            code="PANDOC-CSL",
            key="citation.csl",
        )
    path = Path(raw)
    if not path.is_absolute():
        format_path = Path(getattr(format_spec, "path", Path.cwd()))
        path = format_path.parent / path
    if not path.is_file():
        raise PandocError(
            f"CSL tidak ditemukan: {path}; periksa citation.csl pada format.yml.",
            code="PANDOC-CSL",
            path=path,
            key="citation.csl",
        )
    return path.resolve()


def _resource_paths(ctx: object, markdown: Path) -> tuple[Path, ...]:
    """Direktori pencarian gambar untuk Pandoc.

    Gambar Markdown relatif terhadap ``document.md``; Mermaid dapat menulis ke
    ``gambar/`` di direktori dokumen atau workspace. Logo front matter memakai
    path absolut sehingga tidak butuh entri tambahan.
    """

    document_path = Path(getattr(getattr(ctx, "document", None), "path", Path.cwd()))
    format_path = Path(getattr(getattr(ctx, "format", None), "path", document_path))
    workspace = getattr(ctx, "workspace", None)
    workspace_root = (
        Path(workspace.root)
        if workspace is not None and getattr(workspace, "root", None) is not None
        else None
    )

    candidates: list[Path] = [
        document_path.parent,
        markdown.parent,
        format_path.parent,
        document_path.parent / "gambar",
    ]
    if workspace_root is not None:
        candidates.extend([workspace_root, workspace_root / "gambar"])

    seen: set[str] = set()
    result: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if not resolved.is_dir():
            continue
        key = str(resolved).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(resolved)
    return tuple(result)


def _pandoc_executable(ctx: object) -> str:
    injected = getattr(ctx, "pandoc", None)
    if injected is not None:
        if isinstance(injected, (str, Path)):
            executable = find_pandoc(injected)
        else:
            # Adapter pipeline boleh menyediakan path executable lewat atribut
            # ``executable``/``path``.
            raw = getattr(injected, "executable", None) or getattr(injected, "path", None)
            executable = find_pandoc(raw) if raw is not None else None
        if executable is None:
            raise ToolMissingError(
                "pandoc",
                f"Pandoc yang diberikan tidak dapat dijalankan. {PANDOC_INSTALL_HINT}",
            )
        return executable

    executable = find_pandoc()
    if executable is None:
        raise ToolMissingError(
            "pandoc",
            f"Pandoc tidak ditemukan di PATH. {PANDOC_INSTALL_HINT}",
        )
    return executable


# ---------------------------------------------------------------------------
# Command builder dan eksekusi
# ---------------------------------------------------------------------------


def build_pandoc_command(
    executable: str | Path,
    *,
    markdown: str | Path,
    output: str | Path,
    reference_docx: str | Path | None = None,
    bibliography: str | Path | None = None,
    csl: str | Path | None = None,
    metadata_file: str | Path | None = None,
    resource_paths: Sequence[str | Path] = (),
    citeproc: bool = True,
    top_level_division: str = "chapter",
    toc: bool = False,
    extra_args: Sequence[str] = (),
) -> list[str]:
    """Bangun argv Pandoc tanpa menyentuh filesystem.

    ``toc`` default false dan direfleksikan sebagai ``--metadata=toc=false``.
    Stage post-Pandoc yang menulis field TOC; menambahkan ``--toc`` di sini
    akan membuat daftar isi ganda. ``--lua-filter`` tidak pernah ditambahkan.
    """

    command = [
        *_executable_command(executable),
        str(markdown),
        f"--top-level-division={top_level_division}",
        f"--metadata=toc={'true' if toc else 'false'}",
    ]

    if metadata_file is not None:
        command.append(f"--metadata-file={metadata_file}")
    if reference_docx is not None:
        command.append(f"--reference-doc={reference_docx}")
    if citeproc:
        command.append("--citeproc")
    if bibliography is not None:
        command.append(f"--bibliography={bibliography}")
    if csl is not None:
        command.append(f"--csl={csl}")

    if resource_paths:
        search_path = os.pathsep.join(str(path) for path in resource_paths)
        command.append(f"--resource-path={search_path}")

    command.extend(extra_args)
    command.extend(["-o", str(output)])
    return command


def run_pandoc(
    command: Sequence[str],
    *,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Jalankan Pandoc dan angkat ``PandocError`` yang dapat ditindaklanjuti."""

    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PandocError(
            f"Pandoc melebihi batas waktu {timeout} detik; dokumen terlalu "
            "besar atau render gambar macet.",
            code="PANDOC-TIMEOUT",
        ) from exc
    except OSError as exc:
        raise PandocError(
            f"Gagal menjalankan Pandoc: {exc}. {PANDOC_INSTALL_HINT}",
            code="PANDOC-EXEC",
        ) from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        suffix = f": {detail[-2000:]}" if detail else ""
        raise PandocError(
            f"Pandoc gagal (kode {completed.returncode}){suffix}. "
            "Periksa input Markdown, bibliography/CSL, dan reference.docx.",
            code="PANDOC-FAILED",
        )


def _digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _temporary_output(output: Path) -> Path:
    return output.with_name(f"{output.stem}.tmp{output.suffix}")


def _load_output(path: Path, *, markdown: Path) -> DocumentPackage:
    """Validasi output Pandoc dan kembalikan package yang sama untuk stage."""

    if not path.is_file() or path.stat().st_size == 0:
        raise PandocError(
            "Pandoc tidak menghasilkan DOCX; periksa pesan Pandoc di atas.",
            code="PANDOC-OUTPUT",
            path=path,
        )
    try:
        return DocumentPackage.load(path)
    except DocgenError as exc:
        raise PandocError(
            f"output Pandoc bukan DOCX yang valid: {exc}",
            code="PANDOC-OUTPUT",
            path=path,
            key=markdown.name,
        ) from exc
    except Exception as exc:  # pragma: no cover - pengaman kontrak
        raise PandocError(
            f"output Pandoc tidak dapat dibuka sebagai DOCX: {exc}",
            code="PANDOC-OUTPUT",
            path=path,
            key=markdown.name,
        ) from exc


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


class PandocStage(BaseStage):
    """Konversi Markdown materialized menjadi DOCX sementara di workspace."""

    name = StageName.PANDOC
    order = 40
    requires = canonical_prefix(StageName.PANDOC)
    mutates = frozenset({"package"})
    idempotent = True

    def run(self, ctx: StageContext) -> StageResult:
        """Konversi Markdown materialized menjadi DOCX di workspace.

        Menulis metadata sementara, menjalankan Pandoc, memuat hasilnya sekali,
        lalu menyimpan package ke ``ctx.package`` untuk stage berikutnya.
        Mengembalikan ``StageResult`` berisi path DOCX dan metadata. Melempar
        ``PandocError`` untuk prasyarat yang hilang dan ``StageError`` untuk
        kegagalan proses yang tidak dikenal.
        """

        started = time.monotonic()
        try:
            markdown = _markdown_path(ctx)
            reference = _reference_path(ctx)
            workspace = getattr(ctx, "workspace", None)
            if workspace is None or not callable(getattr(workspace, "ensure", None)):
                raise PandocError(
                    "stage pandoc membutuhkan workspace untuk output sementara.",
                    code="PANDOC-WORKSPACE",
                )
            workspace.ensure()

            document = getattr(ctx, "document", None)
            format_spec = getattr(ctx, "format", None)
            metadata = getattr(document, "metadata", None)
            if metadata is None:
                raise PandocError(
                    "metadata dokumen tidak tersedia; stage pandoc membutuhkan report_name.",
                    code="PANDOC-METADATA",
                )
            report_name = metadata.report_name
            output = Path(workspace.path(f"{report_name}.docx"))
            temporary = _temporary_output(output)
            bibliography = resolve_bibliography(document, format_spec)
            metadata_file = write_metadata_file(
                Path(workspace.path(METADATA_FILENAME)),
                build_pandoc_metadata(
                    document,
                    format_spec,
                    bibliography=bibliography,
                ),
            )
            csl = _resolve_csl(format_spec)
            resources = _resource_paths(ctx, markdown)
            executable = _pandoc_executable(ctx)

            invocation = PandocInvocation(
                markdown=markdown,
                output=temporary,
                reference_docx=reference,
                bibliography=bibliography,
                csl=csl,
                metadata_file=metadata_file,
                resource_paths=resources,
            )
            command = build_pandoc_command(
                executable,
                markdown=invocation.markdown,
                output=invocation.output,
                reference_docx=invocation.reference_docx,
                bibliography=invocation.bibliography,
                csl=invocation.csl,
                metadata_file=invocation.metadata_file,
                resource_paths=invocation.resource_paths,
                citeproc=True,
                top_level_division="chapter",
                toc=False,
            )

            before = _digest(output)
            temporary.unlink(missing_ok=True)
            try:
                run_pandoc(command, timeout=invocation.timeout)
                package = _load_output(temporary, markdown=markdown)
                os.replace(temporary, output)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise

            # Satu load package target dilakukan di sini agar stage postprocess
            # menerima objek yang sama. Pipeline wajib memakai ctx.package ini,
            # bukan memanggil load ulang.
            ctx.package = package

            artifacts = getattr(ctx, "artifacts", None)
            if artifacts is not None and hasattr(artifacts, "put"):
                keys = set(artifacts.keys())
                if "pandoc_docx" not in keys:
                    artifacts.put("pandoc_docx", output)

            after = _digest(output)
            metrics = {
                "markdown_bytes": markdown.stat().st_size,
                "output_bytes": output.stat().st_size,
                "resource_paths": len(resources),
                "bibliography": "yes" if bibliography is not None else "no",
            }
            logger = getattr(ctx, "logger", None)
            if logger is not None and callable(getattr(logger, "info", None)):
                logger.info(
                    "pandoc: %s -> %s (%d byte)",
                    markdown.name,
                    output.name,
                    output.stat().st_size,
                )
            return StageResult(
                stage=self.name.value,
                status="ok",
                changed=before != after,
                duration_ms=int((time.monotonic() - started) * 1000),
                metrics=metrics,
                artifacts=(output, metadata_file),
            )
        except DocgenError:
            raise
        except Exception as exc:  # pragma: no cover - pengaman kontrak
            document_path = getattr(getattr(ctx, "document", None), "path", None)
            raise StageError(
                self.name.value,
                f"konversi Pandoc gagal: {exc}",
                cause=exc,
                path=document_path,
                code="PANDOC-STAGE",
            ) from exc
