"""Orkestrasi build CLI untuk Markdown/DOCX dan deck YAML.

Modul domain diimpor di dalam fungsi yang membutuhkannya sehingga
``--help``/``--version`` tidak menyentuh COM, Google, atau renderer.
"""

import contextlib
import importlib.util
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from autooffice.errors import AutoOfficeError

from . import CliError
from .check import load_markdown_project
from .outputs import (
    DeckOutputs,
    atomic_copy,
    deck_outputs,
    deck_sync_path,
    docx_outputs,
    ensure_directory,
    format_missing_assets,
    missing_deck_assets,
    planned_deck_files,
    planned_docx_files,
    require_safe_build_directory,
    resolve_output_directory,
    stage_deck_assets,
)
from .targets import DECK_TARGETS, MD_TARGETS, InputKind


@dataclass(frozen=True, slots=True)
class BuildOutcome:
    """Hasil satu build atau rencana dry-run yang siap dicetak CLI."""

    source: Path
    kind: InputKind
    targets: tuple[str, ...]
    files: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    dry_run: bool = False


_AMBIGUOUS_CLEANUP_CODES = frozenset({"WORD-CLEANUP", "PDF-CLEANUP", "CLI-FONT-CLEANUP"})


def _is_cleanup_ambiguous(exc: BaseException) -> bool:
    """True bila error menyatakan worker Office mungkin masih menulis."""

    return bool(getattr(exc, "cleanup_ambiguous", False)) or (
        getattr(exc, "code", None) in _AMBIGUOUS_CLEANUP_CODES
    )


@dataclass(frozen=True, slots=True)
class _RenderedPptx:
    """Artefak PPTX hasil render beserta warning renderer."""

    artifact: Path
    warnings: tuple[str, ...]


def build_markdown(
    input: Path,
    targets: Sequence[str],
    out: Path | None = None,
    terms: bool = False,
    keep_intermediate: bool = False,
    dry_run: bool = False,
) -> BuildOutcome:
    """Bangun DOCX/PDF dari ``document.md`` memakai API ``build_docx``."""
    requested = _validated_targets(targets, MD_TARGETS, "markdown")
    if out is not None:
        out = resolve_output_directory(input, out)
    pdf_only = "pdf" in requested and "docx" not in requested

    if dry_run:
        project = load_markdown_project(input)
        report_name = str(project.document.metadata.report_name)
        outputs = docx_outputs(input, report_name, out)
        _preflight_markdown_apis(requested)
        dry_notes = [f"direktori output: {outputs.output_dir}"]
        if "pdf" in requested:
            dry_notes.append(f"PDF DOCX melalui Word COM: {outputs.pdf}")
        if keep_intermediate:
            dry_notes.append(f"intermediate dipertahankan: {outputs.build_dir}")
        return BuildOutcome(
            source=input,
            kind=InputKind.MARKDOWN,
            targets=requested,
            files=planned_docx_files(
                outputs,
                requested,
                terms=terms,
                keep_intermediate=keep_intermediate,
            ),
            warnings=tuple(str(warning) for warning in project.warnings),
            notes=tuple(dry_notes),
            dry_run=True,
        )

    from autooffice.docx.command import build_docx

    intermediate_dir = docx_outputs(input, "build", out).build_dir
    cleanup_safe = True
    try:
        result = build_docx(
            input=input,
            out=intermediate_dir if pdf_only else out,
            terms=terms,
            keep_intermediate=pdf_only or keep_intermediate,
        )
    except Exception as exc:
        if _is_cleanup_ambiguous(exc):
            cleanup_safe = False
        if cleanup_safe and pdf_only and not keep_intermediate:
            _cleanup_build_directory(
                input,
                intermediate_dir,
                ".laporan-build",
                per_stem=False,
            )
        raise
    report_name = result.docx.stem
    outputs = docx_outputs(input, report_name, out)
    if pdf_only and not _is_within(result.docx, outputs.build_dir):
        raise CliError(
            f"build DOCX intermediate keluar dari workspace build: {result.docx}",
            code="CLI-BUILD-PATH",
            exit_code=1,
            path=str(result.docx),
        )
    files: list[Path] = []
    notes: list[str] = []

    if "docx" in requested:
        files.append(result.docx)
    if result.manifest is not None:
        files.append(result.manifest)
    if result.terms is not None:
        files.append(result.terms)
    if result.workspace is not None and not pdf_only:
        notes.append(f"workspace dipertahankan: {result.workspace}")

    if "pdf" in requested:
        try:
            pdf_path = _convert_docx_to_pdf(result.docx, outputs.pdf)
        except CliError as exc:
            raise CliError(
                f"DOCX selesai di {result.docx}, tetapi {exc.message}",
                code=exc.code,
                exit_code=exc.exit_code,
                path=str(result.docx),
                cleanup_ambiguous=_is_cleanup_ambiguous(exc),
            ) from exc
        files.append(pdf_path)
        if pdf_only:
            if keep_intermediate:
                files.append(result.docx)
                notes.append(f"intermediate dipertahankan: {outputs.build_dir}")
                if result.workspace is not None:
                    notes.append(f"workspace dipertahankan: {result.workspace}")
            else:
                _cleanup_build_directory(
                    input,
                    outputs.build_dir,
                    ".laporan-build",
                    per_stem=False,
                )
                notes.append(
                    "DOCX intermediate dihapus dari workspace karena "
                    "--keep-intermediate tidak aktif"
                )

    return BuildOutcome(
        source=input,
        kind=InputKind.MARKDOWN,
        targets=requested,
        files=tuple(files),
        warnings=tuple(str(warning) for warning in result.warnings),
        notes=tuple(notes),
    )


def build_deck(
    input: Path,
    targets: Sequence[str],
    out: Path | None = None,
    theme: str | None = None,
    dry_run: bool = False,
    keep_intermediate: bool = False,
    sync: str | None = None,
    *,
    google_services: Any | None = None,
) -> BuildOutcome:
    """Bangun deck YAML menjadi PPTX/PDF/Slides.

    ``model``, ``layout``, ``copy``, dan ``render.pptx`` diimpor di dalam
    fungsi ini. ``google_services`` adalah seam dependency injection untuk
    test dan pemanggil yang sudah memiliki service Google; CLI normal tidak
    mengisinya.
    """
    requested = _validated_targets(targets, DECK_TARGETS, "deck")
    if out is not None:
        out = resolve_output_directory(input, out)
    outputs = deck_outputs(input, out)
    from autooffice.deck.model import build_coverage_plan, compile_deck_file

    deck = compile_deck_file(input)
    theme_value = _resolve_theme(_deck_theme_name(theme, deck))
    sync_mode = _sync_mode(sync, requested)
    sync_only = sync_mode in {"diff", "pull", "apply"}
    if "slides" in requested:
        _preflight_google(google_services, check_credentials=dry_run)
        if sync_mode != "push":
            _require_state(outputs.state)
    missing_assets = missing_deck_assets(deck, input.parent)
    if missing_assets:
        raise CliError(
            format_missing_assets(missing_assets),
            code="CLI-ASSET",
            exit_code=1,
            path=str(input),
        )
    if dry_run:
        _preflight_deck_apis(requested, sync_mode)
    else:
        _preflight_renderer(requested, sync_mode)

    transcript_source = input.parent / "transcripts.md"
    transcript = _load_transcript(deck, transcript_source)
    copy_warnings = _run_copy_checker(input, deck, transcript, transcript_source)
    coverage = build_coverage_plan(deck)
    _require_coverage_plan(coverage)
    layout_plan = _build_layout_plan(deck, theme_value, input)

    planned = list(
        planned_deck_files(
            outputs,
            requested,
            keep_intermediate=keep_intermediate,
            sync_mode=sync_mode,
        )
    )
    notes = _summary_notes(deck, coverage, outputs)
    if "slides" in requested:
        notes.extend(_google_notes(outputs, sync_mode, keep_intermediate=keep_intermediate))

    if dry_run:
        if "pdf" in requested:
            notes.append(f"PDF deck melalui PowerPoint COM: {outputs.pdf}")
        if not sync_only:
            if keep_intermediate:
                notes.append(f"intermediate dipertahankan: {outputs.build_dir}")
            else:
                notes.append(f"workspace build sementara: {outputs.build_dir}")
        return BuildOutcome(
            source=input,
            kind=InputKind.DECK,
            targets=requested,
            files=tuple(planned),
            warnings=copy_warnings,
            notes=tuple(notes),
            dry_run=True,
        )

    if not sync_only:
        ensure_directory(outputs.output_dir)
    warnings = list(copy_warnings)
    written: list[Path] = []
    cleanup_safe = True
    try:
        if _needs_render(requested, sync_mode):
            stage_deck_assets(input, deck, outputs.build_dir)
        pptx_source: Path | None = None
        if "pptx" in requested:
            rendered = _render_pptx(
                deck=deck,
                layout=layout_plan,
                theme=theme_value,
                target="pptx",
                workspace=outputs.build_dir,
                destination=outputs.pptx,
                cache=outputs.cache,
            )
            warnings.extend(rendered.warnings)
            pptx_source = rendered.artifact
            written.append(rendered.artifact)

        if "pdf" in requested:
            pdf_source = outputs.intermediate_pptx if pptx_source is None else pptx_source
            if pptx_source is None:
                rendered = _render_pptx(
                    deck=deck,
                    layout=layout_plan,
                    theme=theme_value,
                    target="pptx",
                    workspace=outputs.build_dir,
                    destination=outputs.intermediate_pptx,
                    cache=outputs.cache,
                )
                warnings.extend(rendered.warnings)
            try:
                pdf_path = _convert_pptx_to_pdf(pdf_source, outputs.pdf)
            except CliError as exc:
                raise CliError(
                    f"PPTX selesai di {pdf_source}, tetapi {exc.message}",
                    code=exc.code,
                    exit_code=exc.exit_code,
                    path=str(pdf_source),
                    cleanup_ambiguous=_is_cleanup_ambiguous(exc),
                ) from exc
            written.append(pdf_path)
            if keep_intermediate and pptx_source is None:
                written.append(outputs.intermediate_pptx)

        if "slides" in requested:
            if sync_mode == "push":
                staging_render = _render_pptx(
                    deck=deck,
                    layout=layout_plan,
                    theme=theme_value,
                    target="slides",
                    workspace=outputs.build_dir,
                    destination=outputs.staging,
                    embed_fonts=False,
                    cache=outputs.cache,
                )
                warnings.extend(staging_render.warnings)
                staging = staging_render.artifact
                try:
                    written.extend(
                        _google_sync(outputs, sync_mode, staging, google_services, theme_value)
                    )
                except CliError, AutoOfficeError, OSError:
                    if not keep_intermediate:
                        with contextlib.suppress(OSError):
                            staging.unlink(missing_ok=True)
                    raise
                if keep_intermediate:
                    written.append(staging)
                else:
                    with contextlib.suppress(OSError):
                        staging.unlink(missing_ok=True)
            else:
                written.extend(
                    _google_sync(outputs, sync_mode, outputs.staging, google_services, theme_value)
                )

        if transcript_source.is_file() and not sync_only:
            written.append(atomic_copy(transcript_source, outputs.transcript))
    except BaseException as exc:
        if _is_cleanup_ambiguous(exc):
            cleanup_safe = False
        raise
    finally:
        # Sync-only tidak me-render dan tidak membuat workspace; jangan hapus
        # direktori build yang mungkin ditinggalkan --keep-intermediate.
        # Cleanup ambigu berarti worker COM masih dapat menulis ke workspace.
        if cleanup_safe and not keep_intermediate and not sync_only:
            _cleanup_build_directory(input, outputs.build_dir, ".autooffice-build")

    if keep_intermediate and not sync_only:
        notes.append(f"intermediate dipertahankan: {outputs.build_dir}")

    if sync_only:
        written_set = set(written)
        files = tuple(path for path in planned if path in written_set)
    else:
        files = _ordered_files(planned, written)
    return BuildOutcome(
        source=input,
        kind=InputKind.DECK,
        targets=requested,
        files=files,
        warnings=tuple(dict.fromkeys(warnings)),
        notes=tuple(notes),
    )


def _validated_targets(
    targets: Sequence[str],
    allowed: tuple[str, ...],
    label: str,
) -> tuple[str, ...]:
    requested = tuple(targets)
    if not requested:
        raise CliError(
            "minimal satu target diperlukan",
            code="CLI-TARGET-MISSING",
            exit_code=2,
        )
    invalid = sorted(set(requested) - set(allowed))
    if invalid:
        raise CliError(
            f"target tidak valid untuk input {label}: {', '.join(invalid)}; "
            f"pilihan: {', '.join(allowed)}",
            code="CLI-TARGET-INVALID",
            exit_code=2,
        )
    return requested


def _deck_theme_name(theme: str | None, deck: Any) -> str:
    """Kembalikan theme eksplisit atau ``theme_name`` wajib dari deck."""
    if theme is not None:
        return theme
    name = getattr(deck, "theme_name", None)
    if not isinstance(name, str) or not name.strip():
        raise CliError(
            "deck tidak memiliki theme_name; tentukan --theme secara eksplisit",
            code="CLI-THEME",
            exit_code=1,
        )
    return name


def _resolve_theme(name: str) -> Any:
    if name not in {"indigo", "hitam"}:
        raise CliError(
            f"theme tidak valid: {name}; pilihan: indigo, hitam",
            code="CLI-THEME",
            exit_code=2,
        )
    from autooffice.design import resolve_theme

    try:
        return resolve_theme(name)
    except AutoOfficeError:
        raise
    except (TypeError, ValueError) as exc:
        raise CliError(
            f"theme '{name}' tidak valid: {exc}",
            code="CLI-THEME",
            exit_code=2,
        ) from exc


def _build_layout_plan(deck: Any, theme: Any, source: Path) -> Any:
    from autooffice.deck.layout.overflow import plan_deck, plan_overflow_keys

    try:
        plan = plan_deck(deck, theme, fail_on_overflow=False)
    except AutoOfficeError as exc:
        raise CliError(
            f"layout deck gagal: {exc}",
            code="CLI-LAYOUT",
            exit_code=1,
            path=str(source),
        ) from exc
    overflow = tuple(plan_overflow_keys(plan))
    if overflow:
        raise CliError(
            "layout overflow; build dihentikan tanpa shrink: " + ", ".join(overflow),
            code="CLI-LAYOUT-OVERFLOW",
            exit_code=1,
        )
    return plan


def _require_coverage_plan(coverage: Any) -> None:
    if bool(getattr(coverage, "ok", False)):
        return
    findings: list[str] = []
    for field in ("unkeyed_visible", "missing_alt", "duplicate_keys"):
        values = getattr(coverage, field, ())
        if values:
            findings.append(f"{field}: {', '.join(str(value) for value in values)}")
    raise CliError(
        "coverage plan gagal: " + "; ".join(findings),
        code="CLI-COVERAGE",
        exit_code=1,
    )


def _summary_notes(deck: Any, coverage: Any, outputs: DeckOutputs) -> list[str]:
    meta = getattr(deck, "meta", None)
    if not isinstance(meta, Mapping):
        raise CliError(
            "deck tidak memiliki metadata meta",
            code="CLI-META",
            exit_code=1,
            path=str(outputs.source),
        )
    raw_title = meta.get("title")
    if not isinstance(raw_title, str) or not raw_title.strip():
        raise CliError(
            "deck meta.title wajib berupa teks non-kosong",
            code="CLI-META",
            exit_code=1,
            path=str(outputs.source),
        )
    title = raw_title.strip()
    declared = len(getattr(coverage, "declared_keys", ()))
    charts = len(getattr(coverage, "charts", ()))
    return [
        f"deck: {title}",
        f"slide: {len(getattr(deck, 'slides', ()))}",
        f"coverage: {declared} key, {charts} chart, 0 temuan",
        f"direktori output: {outputs.output_dir}",
    ]


def _load_transcript(deck: Any, transcript_path: Path) -> Any | None:
    if not transcript_path.is_file():
        return None
    from autooffice.deck.transcript import parse_transcript_file

    return parse_transcript_file(
        transcript_path,
        [slide.slide_id for slide in deck.slides],
    )


def _run_copy_checker(
    source: Path,
    deck: Any,
    transcript: Any | None,
    transcript_path: Path,
) -> tuple[str, ...]:
    from autooffice.deck.copy import check_copy, has_errors

    copy_path = source.parent / "copy.yaml"
    diagnostics = check_copy(
        deck,
        transcript,
        copy_path=copy_path if copy_path.is_file() else None,
        deck_file=source,
        transcript_file=transcript_path if transcript_path.is_file() else None,
    )
    errors = tuple(diagnostic for diagnostic in diagnostics if _severity(diagnostic) == "error")
    if has_errors(diagnostics):
        raise CliError(
            "copy checker menemukan error: "
            + "; ".join(_format_diagnostic(diagnostic) for diagnostic in errors),
            code="CLI-COPY",
            exit_code=1,
            path=str(source),
        )
    return tuple(
        _format_diagnostic(diagnostic)
        for diagnostic in diagnostics
        if _severity(diagnostic) == "warning"
    )


def _severity(diagnostic: Any) -> str:
    value = getattr(diagnostic, "severity", "error")
    return str(value)


def _format_diagnostic(diagnostic: Any) -> str:
    formatter = getattr(diagnostic, "format", None)
    if callable(formatter):
        return str(formatter())
    return str(diagnostic)


def _preflight_markdown_apis(requested: tuple[str, ...]) -> None:
    """Validasi API Markdown pada dry-run tanpa memanggil COM."""

    from autooffice.docx.command import build_docx

    if not callable(build_docx):
        raise CliError(
            "API build DOCX tidak tersedia",
            code="CLI-DOCX",
            exit_code=1,
        )
    if "pdf" in requested:
        from autooffice.pdf import export_pdf

        if not callable(export_pdf):
            raise CliError(
                "API ekspor PDF tidak tersedia",
                code="CLI-PDF",
                exit_code=1,
            )


def _convert_docx_to_pdf(source: Path, destination: Path) -> Path:
    ensure_directory(destination.parent)
    from autooffice.pdf import export_pdf

    try:
        converted = export_pdf(source, destination)
    except CliError:
        raise
    except AutoOfficeError as exc:
        ambiguous = _is_cleanup_ambiguous(exc)
        raise CliError(
            f"ekspor PDF DOCX dengan Word gagal untuk '{source}' "
            f"dengan target '{destination}': {exc}",
            code="PDF-CLEANUP" if ambiguous else "CLI-PDF-COM",
            exit_code=1,
            path=str(source),
            cleanup_ambiguous=ambiguous,
        ) from exc
    except (OSError, ValueError) as exc:
        raise CliError(
            f"ekspor PDF DOCX gagal untuk '{source}' dengan target '{destination}': {exc}",
            code="CLI-PDF",
            exit_code=1,
            path=str(source),
        ) from exc
    return _require_artifact(_as_path(converted, "konversi PDF DOCX"), "konversi PDF DOCX")


def _convert_pptx_to_pdf(source: Path, destination: Path) -> Path:
    ensure_directory(destination.parent)
    from autooffice.pdf import export_pptx_pdf

    try:
        converted = export_pptx_pdf(source, destination)
    except CliError:
        raise
    except AutoOfficeError as exc:
        ambiguous = _is_cleanup_ambiguous(exc)
        raise CliError(
            f"ekspor PDF PPTX dengan PowerPoint gagal untuk '{source}' "
            f"dengan target '{destination}': {exc}",
            code="PDF-CLEANUP" if ambiguous else "CLI-PDF-COM",
            exit_code=1,
            path=str(source),
            cleanup_ambiguous=ambiguous,
        ) from exc
    except (OSError, ValueError) as exc:
        raise CliError(
            f"ekspor PDF PPTX gagal untuk '{source}' dengan target '{destination}': {exc}",
            code="CLI-PDF",
            exit_code=1,
            path=str(source),
        ) from exc
    return _require_artifact(_as_path(converted, "konversi PDF PPTX"), "konversi PDF PPTX")


class _Renderer(Protocol):
    def render(self, request: object) -> object:
        """Render satu request dan kembalikan hasil."""
        ...


@dataclass(frozen=True, slots=True)
class _FunctionRenderer:
    function: Callable[[object], object]

    def render(self, request: object) -> object:
        return self.function(request)


def _render_pptx(
    *,
    deck: Any,
    layout: Any,
    theme: Any,
    target: str,
    workspace: Path,
    destination: Path,
    embed_fonts: bool = True,
    cache: Path | None = None,
) -> _RenderedPptx:
    from autooffice.deck.render.protocol import OutputTarget, RenderRequest

    renderer = _renderer_from(importlib.import_module("autooffice.deck.render.pptx"))
    ensure_directory(workspace)
    if cache is not None:
        _restore_render_cache(cache, workspace)
    request = RenderRequest(
        deck=deck,
        layout=layout,
        theme=theme,
        target=OutputTarget(target),
        workspace=workspace,
    )
    try:
        result = renderer.render(request)
    except TypeError as exc:
        raise CliError(
            f"renderer PPTX tidak cocok dengan kontrak render: {exc}",
            code="CLI-RENDERER",
            exit_code=1,
        ) from exc
    if cache is not None:
        _persist_render_cache(workspace, cache)
    coverage = getattr(result, "coverage", None)
    if coverage is None:
        raise CliError(
            "renderer PPTX tidak mengembalikan coverage; artefak tidak dapat diverifikasi",
            code="CLI-RENDERER",
            exit_code=1,
        )
    if not bool(getattr(coverage, "ok", False)):
        raise CliError(
            "coverage renderer PPTX gagal: " + _coverage_message(coverage),
            code="CLI-COVERAGE",
            exit_code=1,
        )
    artifact = getattr(result, "artifact_path", None)
    artifact_path = _as_path(artifact, "renderer PPTX")
    _require_artifact(artifact_path, "renderer PPTX")
    warnings = tuple(str(warning) for warning in getattr(result, "warnings", ()))
    if embed_fonts:
        _embed_pptx_fonts(artifact_path)
        warnings = _without_font_embedding_warnings(warnings)
    return _RenderedPptx(artifact=_publish(artifact_path, destination), warnings=warnings)


def _restore_render_cache(cache: Path, workspace: Path) -> None:
    """Salin cache Mermaid persisten ke workspace render.

    Renderer menyimpan diagram di ``<workspace>/cache/mermaid`` lalu workspace
    dibersihkan setelah build. Menyalin kedua arah membuat diagram bertahan di
    ``.autooffice/cache/mermaid`` tanpa mengubah kontrak renderer.
    """

    source = cache / "mermaid"
    if not source.is_dir():
        return
    destination = workspace / "cache" / "mermaid"
    ensure_directory(destination)
    try:
        for item in source.iterdir():
            if item.is_file():
                shutil.copy2(item, destination / item.name)
    except OSError as exc:
        raise CliError(
            f"cache Mermaid tidak dapat dipulihkan dari {source}: {exc}",
            code="CLI-CACHE",
            exit_code=1,
            path=str(source),
        ) from exc


def _persist_render_cache(workspace: Path, cache: Path) -> None:
    """Simpan diagram Mermaid dari workspace ke cache persisten."""

    source = workspace / "cache" / "mermaid"
    if not source.is_dir():
        return
    destination = ensure_directory(cache / "mermaid")
    try:
        for item in source.iterdir():
            if item.is_file():
                shutil.copy2(item, destination / item.name)
    except OSError as exc:
        raise CliError(
            f"cache Mermaid tidak dapat disimpan ke {destination}: {exc}",
            code="CLI-CACHE",
            exit_code=1,
            path=str(destination),
        ) from exc


def _embed_pptx_fonts(source: Path) -> Path:
    """Tanam Plus Jakarta Sans ke PPTX final lewat PowerPoint COM.

    Embedding dilakukan sebelum artefak dipublikasikan ke path final agar
    build yang gagal tidak meninggalkan PPTX tanpa font. ``RenderResult``
    ``content_hash`` dihitung renderer sebelum embedding; hash byte final
    berubah setelah langkah ini.
    """

    from autooffice.pdf import embed_pptx_fonts

    try:
        embedded = embed_pptx_fonts(source)
    except CliError:
        raise
    except AutoOfficeError as exc:
        ambiguous = _is_cleanup_ambiguous(exc)
        raise CliError(
            f"font Plus Jakarta Sans gagal ditanam ke '{source}' dengan PowerPoint COM: {exc}. "
            "Final PPTX/PDF membutuhkan Microsoft PowerPoint desktop di Windows dan "
            "font Plus Jakarta Sans terpasang.",
            code="CLI-FONT-CLEANUP" if ambiguous else "CLI-FONT-EMBED",
            exit_code=1,
            path=str(source),
            cleanup_ambiguous=ambiguous,
        ) from exc
    except (OSError, ValueError) as exc:
        raise CliError(
            f"font Plus Jakarta Sans gagal ditanam ke '{source}': {exc}",
            code="CLI-FONT-EMBED",
            exit_code=1,
            path=str(source),
        ) from exc
    return _require_artifact(_as_path(embedded, "font embedding PPTX"), "font embedding PPTX")


def _without_font_embedding_warnings(warnings: tuple[str, ...]) -> tuple[str, ...]:
    """Hapus warning renderer setelah CLI berhasil menanam font."""

    return tuple(warning for warning in warnings if not warning.startswith("font-embedding:"))


def _renderer_from(module: Any) -> _Renderer:
    for name in ("create_renderer", "renderer_factory"):
        factory = getattr(module, name, None)
        if callable(factory):
            return cast(_Renderer, factory())
    renderer_class = getattr(module, "PptxRenderer", None)
    if isinstance(renderer_class, type):
        return cast(_Renderer, renderer_class())
    render_function = getattr(module, "render_deck", None)
    if callable(render_function):
        return _FunctionRenderer(cast("Callable[[object], object]", render_function))
    raise CliError(
        "renderer PPTX tidak menyediakan API render; build deck dihentikan tanpa output",
        code="CLI-RENDERER",
        exit_code=1,
    )


def _needs_render(targets: tuple[str, ...], sync_mode: str) -> bool:
    if bool({"pptx", "pdf"} & set(targets)):
        return True
    return "slides" in targets and sync_mode == "push"


def _preflight_deck_apis(targets: tuple[str, ...], sync_mode: str) -> None:
    """Validasi API deck pada dry-run tanpa COM, renderer, atau jaringan."""

    if {"pptx", "pdf"} & set(targets) or ("slides" in targets and sync_mode == "push"):
        _require_pptx_renderer_class()
    if "pdf" in targets:
        _require_pptx_pdf_adapter()
    if "slides" in targets:
        _require_google_operation(sync_mode)


def _require_pptx_renderer_class() -> None:
    pptx_module = importlib.import_module("autooffice.deck.render.pptx")
    if not isinstance(getattr(pptx_module, "PptxRenderer", None), type):
        raise CliError(
            "renderer PPTX (PptxRenderer) tidak tersedia; build deck dihentikan tanpa output",
            code="CLI-RENDERER",
            exit_code=1,
        )


def _require_pptx_pdf_adapter() -> None:
    from autooffice.pdf import export_pptx_pdf

    if not callable(export_pptx_pdf):
        raise CliError(
            "API ekspor PDF PPTX tidak tersedia",
            code="CLI-PDF",
            exit_code=1,
        )


def _require_google_operation(sync_mode: str) -> None:
    from autooffice.google import push_deck, sync_deck

    operation = push_deck if sync_mode == "push" else sync_deck
    if not callable(operation):
        raise CliError(
            f"operasi Google Slides '{sync_mode}' tidak tersedia",
            code="CLI-GOOGLE",
            exit_code=1,
        )


def _preflight_renderer(targets: tuple[str, ...], sync_mode: str) -> None:
    if not _needs_render(targets, sync_mode):
        return
    pptx_module = importlib.import_module("autooffice.deck.render.pptx")
    if not _has_renderer_api(pptx_module):
        raise CliError(
            "renderer PPTX tidak menyediakan API render; build deck dihentikan tanpa output",
            code="CLI-RENDERER",
            exit_code=1,
        )


def _has_renderer_api(module: Any) -> bool:
    for name in ("create_renderer", "renderer_factory", "render_deck"):
        if callable(getattr(module, name, None)):
            return True
    return isinstance(getattr(module, "PptxRenderer", None), type)


def _coverage_message(coverage: Any) -> str:
    parts: list[str] = []
    for field in ("missing_keys", "duplicate_keys", "unkeyed_visible", "missing_alt"):
        values = getattr(coverage, field, ())
        if values:
            parts.append(f"{field}: {', '.join(str(value) for value in values)}")
    return "; ".join(parts) or "coverage tidak lengkap"


def _publish(source: Path, destination: Path) -> Path:
    if source.resolve() == destination.resolve():
        return destination
    ensure_directory(destination.parent)
    return atomic_copy(source, destination)


def _ordered_files(planned: Sequence[Path], written: Sequence[Path]) -> tuple[Path, ...]:
    present = set(written)
    ordered = [path for path in planned if path in present]
    ordered.extend(path for path in written if path not in planned)
    return tuple(dict.fromkeys(ordered))


def _is_within(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
    except OSError, RuntimeError:
        return False
    return resolved == resolved_root or resolved.is_relative_to(resolved_root)


def _cleanup_build_directory(
    source: Path,
    build_dir: Path,
    root_name: str,
    *,
    per_stem: bool = True,
) -> None:
    """Validasi ulang lalu hapus workspace build, tidak pernah path lain."""

    safe_build_dir = require_safe_build_directory(
        source,
        build_dir,
        root_name,
        per_stem=per_stem,
    )
    if safe_build_dir == source.resolve() or safe_build_dir == source.parent.resolve():
        raise CliError(
            f"direktori build tidak aman untuk dihapus: {safe_build_dir}",
            code="CLI-BUILD-PATH",
            exit_code=1,
            path=str(source),
        )
    shutil.rmtree(safe_build_dir, ignore_errors=True)


def _as_path(value: object, component: str) -> Path:
    if isinstance(value, (str, Path)):
        return Path(value)
    raise CliError(
        f"{component} tidak mengembalikan path artefak yang valid",
        code="CLI-ARTIFACT",
        exit_code=1,
    )


def _require_artifact(path: Path, component: str) -> Path:
    if not path.is_file():
        raise CliError(
            f"{component} tidak menghasilkan artefak yang diminta: {path}",
            code="CLI-ARTIFACT",
            exit_code=1,
            path=str(path),
        )
    return path


def _sync_mode(sync: str | None, targets: tuple[str, ...]) -> str:
    if sync is not None and sync not in {"push", "pull", "diff", "apply"}:
        raise CliError(
            f"mode sync tidak valid: {sync}; pilihan: push, pull, diff, apply",
            code="CLI-SYNC-MODE",
            exit_code=2,
        )
    if "slides" not in targets:
        if sync is not None:
            raise CliError(
                "--sync hanya valid bila target berisi slides",
                code="CLI-SYNC-TARGET",
                exit_code=2,
            )
        return ""
    return "push" if sync is None else sync


def _google_notes(
    outputs: DeckOutputs,
    sync_mode: str,
    *,
    keep_intermediate: bool,
) -> list[str]:
    if sync_mode == "push":
        staging_state = "disimpan" if keep_intermediate else "dihapus setelah push"
        return [
            f"Google Slides: push staging {outputs.staging} ({staging_state})",
            f"Google Sheets: siapkan spreadsheet dan linked chart, state {outputs.state}",
        ]
    destination = deck_sync_path(outputs, sync_mode)
    return [f"Google Slides: {sync_mode}, tulis {destination}"]


def _google_sync(
    outputs: DeckOutputs,
    sync_mode: str,
    staging: Path,
    services: Any | None,
    theme: Any | None = None,
) -> list[Path]:
    if services is None:
        require_google_extra()
    if sync_mode != "push":
        _require_state(outputs.state)
    from autooffice.google import push_deck, sync_deck

    operation = push_deck if sync_mode == "push" else sync_deck
    if not callable(operation):
        raise CliError(
            f"operasi Google Slides '{sync_mode}' tidak tersedia",
            code="CLI-GOOGLE",
            exit_code=1,
            path=str(outputs.source),
        )
    arguments: dict[str, Any] = {
        "deck": outputs.source,
        "staging": staging,
        "state": outputs.state,
        "mode": sync_mode,
        "review_dir": outputs.review_dir,
    }
    if services is not None:
        arguments["services"] = services
    if sync_mode == "push":
        arguments["theme"] = theme
    try:
        result = operation(**arguments)
    except CliError:
        raise
    except AutoOfficeError as exc:
        raise CliError(
            f"Google Slides '{sync_mode}' gagal untuk {outputs.source}: {exc}",
            code="CLI-GOOGLE",
            exit_code=1,
            path=str(outputs.source),
        ) from exc
    if result is None:
        raise CliError(
            f"Google Slides '{sync_mode}' untuk {outputs.source} tidak mengembalikan output; "
            "state/review tidak boleh dianggap sukses",
            code="CLI-GOOGLE-RESULT",
            exit_code=1,
            path=str(outputs.source),
        )
    items: Sequence[object] = result if isinstance(result, (list, tuple)) else (result,)
    if not items:
        raise CliError(
            f"Google Slides '{sync_mode}' untuk {outputs.source} tidak menghasilkan output",
            code="CLI-GOOGLE-RESULT",
            exit_code=1,
            path=str(outputs.source),
        )
    paths: list[Path] = []
    for item in items:
        paths.append(_require_artifact(_as_path(item, "Google Slides"), "Google Slides"))
    return paths


def _preflight_google(services: Any | None, *, check_credentials: bool) -> None:
    """Pastikan extra dan (pada dry-run) kredensial Google tersedia.

    Dry-run tidak boleh menyentuh jaringan, jadi kredensial diperiksa dari
    environment dan token lokal. Build nyata menyerahkan pemuatan kredensial
    ke API publik ``autooffice.google`` agar CLI tidak menduplikasi OAuth.
    """
    if services is not None:
        return
    require_google_extra()
    if not check_credentials:
        return
    from autooffice.google import OAuthSettings, TokenStore

    try:
        OAuthSettings.from_environment()
        TokenStore.from_environment().require()
    except AutoOfficeError as exc:
        raise CliError(
            f"kredensial Google belum siap untuk target slides: {exc}",
            code="CLI-GOOGLE-CREDENTIALS",
            exit_code=1,
        ) from exc


def require_google_extra() -> None:
    """Gagalkan build Slides bila extra ``google`` tidak terpasang."""
    if importlib.util.find_spec("googleapiclient") is None:
        raise CliError(
            "extra 'google' belum terpasang; jalankan uv sync --extra google",
            code="CLI-GOOGLE-EXTRA",
            exit_code=1,
        )


def _require_state(path: Path) -> None:
    if not path.is_file():
        raise CliError(
            f"state belum ada di {path}; jalankan push lebih dulu",
            code="CLI-GOOGLE-STATE",
            exit_code=1,
            path=str(path),
        )
    from autooffice.google import GoogleStateError, load_state

    try:
        state = load_state(path)
    except GoogleStateError as exc:
        raise CliError(
            f"state Google tidak valid: {exc}",
            code="CLI-GOOGLE-STATE",
            exit_code=1,
            path=str(path),
        ) from exc
    if state.presentation_id is None:
        raise CliError(
            f"state {path} belum memiliki presentation_id; jalankan push lebih dulu",
            code="CLI-GOOGLE-STATE",
            exit_code=1,
            path=str(path),
        )


__all__ = ["BuildOutcome", "build_deck", "build_markdown", "require_google_extra"]
