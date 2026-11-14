"""Perintah ``check``: validasi Markdown/DOCX dan deck tanpa menulis output."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from autooffice.errors import AutoOfficeError

from . import CliError, require_callable, require_module
from .outputs import missing_deck_assets
from .targets import InputKind


@dataclass(frozen=True, slots=True)
class Finding:
    """Satu temuan check yang siap dicetak CLI."""

    severity: Literal["error", "warning"]
    message: str
    rule: str = "check"
    key: str | None = None
    file: str | None = None
    line: int | None = None
    hint: str | None = None

    def format(self) -> str:
        """Format satu baris dengan lokasi, key, dan hint bila tersedia."""
        location = self.file or "<input>"
        if self.line is not None:
            location = f"{location}:{self.line}"
        key = f" [{self.key}]" if self.key is not None else ""
        hint = f" Hint: {self.hint}" if self.hint is not None else ""
        return f"{location}: {self.severity}: {self.message} [{self.rule}]{key}{hint}"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Hasil check satu input beserta target yang diminta."""

    source: Path
    kind: InputKind
    targets: tuple[str, ...]
    findings: tuple[Finding, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """True bila tidak ada temuan berperingkat error (warning tidak memblokir)."""
        return self.error_count == 0

    @property
    def error_count(self) -> int:
        """Jumlah temuan berperingkat error."""
        return sum(1 for finding in self.findings if finding.severity == "error")


def load_markdown_project(source: Path) -> Any:
    """Muat dan validasi project Markdown memakai API domain DOCX.

    Fungsi ini tidak menjalankan Pandoc atau Word. Front matter, format,
    struktur, aset, dan urutan heading divalidasi oleh ``load_project`` serta
    ``validate_body``.
    """
    document_module = require_module("autooffice.docx.document", "F1-DOCX")
    load_project = require_callable(document_module, "load_project", "F1-DOCX")
    validate_module = require_module("autooffice.docx.stages.validate", "F1-DOCX")
    validate_body = require_callable(validate_module, "validate_body", "F1-DOCX")
    project = load_project(source)
    validate_body(project.document)
    return project


def check_markdown(
    source: Path,
    targets: tuple[str, ...],
) -> CheckResult:
    """Validasi front matter, format, struktur, aset, heading, dan caption."""
    project = load_markdown_project(source)
    findings = [
        Finding(severity="warning", message=str(warning), rule="docx", file=str(source))
        for warning in getattr(project, "warnings", ())
    ]
    return CheckResult(
        source=source,
        kind=InputKind.MARKDOWN,
        targets=targets,
        findings=tuple(findings),
    )


def check_deck(
    source: Path,
    targets: tuple[str, ...],
    theme: str | None = None,
) -> CheckResult:
    """Validasi deck YAML: schema, coverage, layout, copy, dan transkrip."""
    model_module = require_module("autooffice.deck.model", "F1-MODEL")
    compile_deck_file = require_callable(model_module, "compile_deck_file", "F1-MODEL")
    build_coverage_plan = require_callable(model_module, "build_coverage_plan", "F1-MODEL")

    deck = compile_deck_file(source)
    theme_name = theme or str(getattr(deck, "theme_name", "indigo"))
    theme_value: Any | None = None
    findings: list[Finding] = []
    notes: list[str] = []

    findings.extend(_asset_findings(source, deck))

    try:
        design_module = require_module("autooffice.design", "F1-DESIGN")
        resolve_theme = require_callable(design_module, "resolve_theme", "F1-DESIGN")
        theme_value = resolve_theme(theme_name)
    except CliError as exc:
        findings.append(_cli_finding(exc, rule="theme", file=source))
    except AutoOfficeError as exc:
        findings.append(
            Finding(
                severity="error",
                message=f"theme '{theme_name}' gagal di-resolve: {exc}",
                rule="theme",
                file=str(source),
            )
        )

    coverage = build_coverage_plan(deck)
    findings.extend(_coverage_findings(coverage, source))
    notes.append(
        f"coverage: {len(getattr(coverage, 'declared_keys', ()))} key, "
        f"{len(getattr(coverage, 'charts', ()))} chart"
    )

    if theme_value is not None:
        layout_findings, layout_note = _layout_findings(deck, theme_value, source)
        findings.extend(layout_findings)
        if layout_note is not None:
            notes.append(layout_note)

    copy_findings, copy_notes = _copy_findings(source, deck)
    findings.extend(copy_findings)
    notes.extend(copy_notes)

    return CheckResult(
        source=source,
        kind=InputKind.DECK,
        targets=targets,
        findings=tuple(findings),
        notes=tuple(notes),
    )


def _asset_findings(source: Path, deck: Any) -> list[Finding]:
    missing = missing_deck_assets(deck, source.parent)
    return [
        Finding(
            severity="error",
            message=item.format(),
            rule="asset",
            key=item.reference.key,
            file=str(source),
        )
        for item in missing
    ]


def _coverage_findings(coverage: Any, source: Path) -> list[Finding]:
    findings: list[Finding] = []
    for key in getattr(coverage, "unkeyed_visible", ()):
        findings.append(
            Finding(
                severity="error",
                message=f"objek tampil tanpa key: {key}",
                rule="coverage",
                key=str(key),
                file=str(source),
            )
        )
    for key in getattr(coverage, "missing_alt", ()):
        findings.append(
            Finding(
                severity="error",
                message=f"objek tanpa alt text: {key}",
                rule="coverage",
                key=str(key),
                file=str(source),
            )
        )
    for key in getattr(coverage, "duplicate_keys", ()):
        findings.append(
            Finding(
                severity="error",
                message=f"key duplikat: {key}",
                rule="coverage",
                key=str(key),
                file=str(source),
            )
        )
    return findings


def _layout_findings(
    deck: Any,
    theme: Any,
    source: Path,
) -> tuple[list[Finding], str | None]:
    try:
        require_module("autooffice.deck.layout", "F1-LAYOUT")
        overflow_module = require_module("autooffice.deck.layout.overflow", "F1-LAYOUT")
        plan_deck = require_callable(overflow_module, "plan_deck", "F1-LAYOUT")
        plan_overflow_keys = require_callable(overflow_module, "plan_overflow_keys", "F1-LAYOUT")
    except CliError as exc:
        return [_cli_finding(exc, rule="layout", file=source)], str(exc)

    try:
        plan = plan_deck(deck, theme, fail_on_overflow=False)
    except AutoOfficeError as exc:
        return (
            [
                Finding(
                    severity="error",
                    message=f"layout gagal (lane F1-LAYOUT): {exc}",
                    rule="layout",
                    file=str(source),
                )
            ],
            None,
        )

    keys = plan_overflow_keys(plan)
    return (
        [
            Finding(
                severity="error",
                message=f"overflow pada key: {key}",
                rule="layout",
                key=str(key),
                file=str(source),
            )
            for key in keys
        ],
        None,
    )


def _copy_findings(source: Path, deck: Any) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    notes: list[str] = []
    transcript_path = source.parent / "transcripts.md"
    transcript: Any | None = None

    if transcript_path.is_file():
        try:
            transcript_module = require_module("autooffice.deck.transcript", "F1-COPY")
            parse_transcript_file = require_callable(
                transcript_module, "parse_transcript_file", "F1-COPY"
            )
            transcript = parse_transcript_file(
                transcript_path,
                [slide.slide_id for slide in deck.slides],
            )
        except CliError as exc:
            notes.append(f"transcript validation dilewati: {exc}")
        except AutoOfficeError as exc:
            findings.append(
                Finding(
                    severity="error",
                    message=str(exc),
                    rule="transcript",
                    file=str(transcript_path),
                )
            )

    try:
        copy_module = require_module("autooffice.deck.copy", "F1-COPY")
        check_copy = require_callable(copy_module, "check_copy", "F1-COPY")
    except CliError as exc:
        notes.append(f"copy checker dilewati: {exc}")
        return findings, notes

    copy_path = source.parent / "copy.yaml"
    try:
        diagnostics = check_copy(
            deck,
            transcript,
            copy_path=copy_path if copy_path.is_file() else None,
            deck_file=source,
            transcript_file=transcript_path if transcript_path.is_file() else None,
        )
    except (AutoOfficeError, OSError) as exc:
        findings.append(
            Finding(
                severity="error",
                message=str(exc),
                rule="copy",
                file=str(source),
            )
        )
        return findings, notes

    findings.extend(_diagnostic_findings(diagnostics))
    return findings, notes


def _diagnostic_findings(diagnostics: Any) -> list[Finding]:
    findings: list[Finding] = []
    for diagnostic in diagnostics:
        severity: Literal["error", "warning"] = (
            "error" if getattr(diagnostic, "severity", "error") == "error" else "warning"
        )
        line_value = getattr(diagnostic, "line", None)
        findings.append(
            Finding(
                severity=severity,
                message=str(getattr(diagnostic, "message", "")),
                rule=str(getattr(diagnostic, "rule", "copy")),
                key=_optional_text(getattr(diagnostic, "key", None)),
                file=_optional_text(getattr(diagnostic, "file", None)),
                line=line_value if isinstance(line_value, int) else None,
                hint=_optional_text(getattr(diagnostic, "hint", None)),
            )
        )
    return findings


def _cli_finding(exc: CliError, *, rule: str, file: Path) -> Finding:
    return Finding(
        severity="error",
        message=str(exc),
        rule=rule,
        file=str(file),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = [
    "CheckResult",
    "Finding",
    "check_deck",
    "check_markdown",
    "load_markdown_project",
]
