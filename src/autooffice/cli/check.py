"""Perintah ``check``: validasi Markdown/DOCX dan deck tanpa menulis output."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from autooffice.errors import AutoOfficeError

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
    from autooffice.docx.document import load_project
    from autooffice.docx.stages.validate import validate_body

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
    from autooffice.deck.model import build_coverage_plan, compile_deck_file

    deck = compile_deck_file(source)
    theme_name = theme if theme is not None else getattr(deck, "theme_name", None)
    theme_value: Any | None = None
    findings: list[Finding] = []
    notes: list[str] = []

    findings.extend(_asset_findings(source, deck))

    meta = getattr(deck, "meta", None)
    title = meta.get("title") if isinstance(meta, Mapping) else None
    if not isinstance(title, str) or not title.strip():
        findings.append(
            Finding(
                severity="error",
                message="deck meta.title wajib berupa teks non-kosong",
                rule="meta",
                file=str(source),
            )
        )

    if not isinstance(theme_name, str) or not theme_name.strip():
        findings.append(
            Finding(
                severity="error",
                message="deck tidak memiliki theme_name",
                rule="theme",
                file=str(source),
            )
        )
    else:
        try:
            from autooffice.design import resolve_theme

            theme_value = resolve_theme(theme_name)
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
    from autooffice.deck.layout.overflow import plan_deck, plan_overflow_keys

    try:
        plan = plan_deck(deck, theme, fail_on_overflow=False)
    except AutoOfficeError as exc:
        return (
            [
                Finding(
                    severity="error",
                    message=f"layout gagal: {exc}",
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
        from autooffice.deck.transcript import parse_transcript_file

        try:
            transcript = parse_transcript_file(
                transcript_path,
                [slide.slide_id for slide in deck.slides],
            )
        except AutoOfficeError as exc:
            findings.append(
                Finding(
                    severity="error",
                    message=str(exc),
                    rule="transcript",
                    file=str(transcript_path),
                )
            )

    from autooffice.deck.copy import check_copy

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
