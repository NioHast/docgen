"""Tes cabang build deck: renderer palsu, error Google, dan validasi target."""

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import autooffice.pdf
from autooffice.cli import CliError
from autooffice.cli.build import _render_pptx, build_deck, require_google_extra
from autooffice.deck.layout.spec import LayoutError
from autooffice.deck.model import CoveragePlan
from autooffice.design import DesignTokenError
from autooffice.google import GoogleAuthError, GoogleError

_MISSING = object()
_OK = object()


class _FakeRenderer:
    """Renderer palsu yang menulis artefak di workspace atau path yang diminta."""

    def __init__(
        self,
        *,
        artifact: object = _MISSING,
        destination: Path | None = None,
        coverage: object = _OK,
        warnings: tuple[str, ...] = (),
        error: Exception | None = None,
    ) -> None:
        self._artifact = artifact
        self._destination = destination
        self._coverage = coverage
        self._warnings = warnings
        self._error = error
        self.requests: list[object] = []

    def render(self, request: object) -> object:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        artifact: object = self._artifact
        if artifact is _MISSING:
            target = self._destination or request.workspace / "render.pptx"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"PK fake pptx")
            artifact = target
        coverage = SimpleNamespace(ok=True) if self._coverage is _OK else self._coverage
        return SimpleNamespace(
            artifact_path=artifact,
            coverage=coverage,
            warnings=self._warnings,
        )


def _use_factory(
    monkeypatch: pytest.MonkeyPatch,
    renderer: _FakeRenderer,
    *,
    name: str = "create_renderer",
    disable_create: bool = False,
) -> None:
    if disable_create:
        monkeypatch.setattr("autooffice.deck.render.pptx.create_renderer", None, raising=False)
    monkeypatch.setattr(f"autooffice.deck.render.pptx.{name}", lambda: renderer, raising=False)


def _fake_render_module(function: object) -> ModuleType:
    module = ModuleType("autooffice.deck.render.pptx")
    module.render_deck = function  # type: ignore[attr-defined]
    return module


def _fake_empty_render_module() -> ModuleType:
    return ModuleType("autooffice.deck.render.pptx")


def test_build_pptx_uses_create_renderer_and_filters_font_warning(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = _FakeRenderer(warnings=("font-embedding: belum", "caption terlalu panjang"))
    _use_factory(monkeypatch, renderer)
    out = tmp_path / "out"

    outcome = build_deck(deck_path, ("pptx",), out)

    assert (out / "deck.pptx").is_file()
    assert outcome.files == (out / "deck.pptx", out / "deck.transcript.md")
    assert outcome.warnings == ("caption terlalu panjang",)
    assert str(renderer.requests[0].target) == "pptx"  # type: ignore[attr-defined]
    assert renderer.requests[0].workspace == deck_path.parent / ".autooffice-build" / deck_path.stem  # type: ignore[attr-defined]


def test_build_pptx_falls_back_to_renderer_factory(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = _FakeRenderer()
    _use_factory(monkeypatch, renderer, name="renderer_factory", disable_create=True)
    out = tmp_path / "out"

    build_deck(deck_path, ("pptx",), out)

    assert (out / "deck.pptx").is_file()
    assert len(renderer.requests) == 1


def test_build_pptx_uses_render_deck_function(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def render_deck(request: object) -> object:
        calls.append(request)
        artifact = request.workspace / "function.pptx"  # type: ignore[attr-defined]
        artifact.write_bytes(b"PK function")
        return SimpleNamespace(
            artifact_path=artifact,
            coverage=SimpleNamespace(ok=True),
            warnings=(),
        )

    monkeypatch.setitem(
        sys.modules,
        "autooffice.deck.render.pptx",
        _fake_render_module(render_deck),
    )
    out = tmp_path / "out"

    outcome = build_deck(deck_path, ("pptx",), out)

    assert (out / "deck.pptx").read_bytes() == b"PK function"
    assert outcome.files == (out / "deck.pptx", out / "deck.transcript.md")
    assert len(calls) == 1


def test_build_pptx_without_renderer_api_stops_before_output(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "autooffice.deck.render.pptx", _fake_empty_render_module())
    out = tmp_path / "out"

    with pytest.raises(CliError, match="F1-PPTX") as error:
        build_deck(deck_path, ("pptx",), out)

    assert error.value.code == "CLI-LANE-F1-PPTX"
    assert not out.exists()


def test_render_pptx_reports_missing_renderer_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "autooffice.deck.render.pptx", _fake_empty_render_module())

    with pytest.raises(CliError, match="renderer PPTX") as error:
        _render_pptx(
            deck=None,
            layout=None,
            theme=None,
            target="pptx",
            workspace=tmp_path / "workspace",
            destination=tmp_path / "deck.pptx",
        )

    assert error.value.code == "CLI-LANE-F1-PPTX"


def test_build_pptx_renderer_type_error_is_lane_error(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = _FakeRenderer(error=TypeError("kontrak render salah"))
    _use_factory(monkeypatch, renderer)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="kontrak render salah") as error:
        build_deck(deck_path, ("pptx",), out)

    assert error.value.code == "CLI-LANE-F1-PPTX"
    assert not list(out.glob("*.pptx"))


@pytest.mark.parametrize(
    ("coverage", "match"),
    [
        (
            SimpleNamespace(
                ok=False,
                missing_keys=("s01.title",),
                duplicate_keys=(),
                unkeyed_visible=("s02.body",),
                missing_alt=(),
            ),
            "missing_keys: s01.title.*unkeyed_visible: s02.body",
        ),
        (SimpleNamespace(ok=False), "coverage tidak lengkap"),
    ],
)
def test_build_pptx_renderer_coverage_failure_stops_build(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    coverage: object,
    match: str,
) -> None:
    _use_factory(monkeypatch, _FakeRenderer(coverage=coverage))
    out = tmp_path / "out"

    with pytest.raises(CliError, match=match) as error:
        build_deck(deck_path, ("pptx",), out)

    assert error.value.code == "CLI-COVERAGE"
    assert not (out / "deck.pptx").exists()


def test_build_pptx_rejects_renderer_without_artifact_path(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_factory(monkeypatch, _FakeRenderer(artifact=None))

    with pytest.raises(CliError, match="tidak mengembalikan path") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out")

    assert error.value.code == "CLI-LANE-F1-PPTX"


def test_build_pptx_rejects_missing_rendered_artifact(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_factory(monkeypatch, _FakeRenderer(artifact=tmp_path / "hilang.pptx"))

    with pytest.raises(CliError, match="tidak menghasilkan artefak") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out")

    assert error.value.code == "CLI-LANE-F1-PPTX"


def test_build_pptx_publishes_renderer_artifact_written_to_destination(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out"
    _use_factory(monkeypatch, _FakeRenderer(destination=out / "deck.pptx"))

    outcome = build_deck(deck_path, ("pptx",), out)

    assert (out / "deck.pptx").read_bytes() == b"PK fake pptx"
    assert outcome.files == (out / "deck.pptx", out / "deck.transcript.md")


def test_build_pptx_font_embedding_adapter_missing_reports_lane(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(autooffice.pdf, "embed_pptx_fonts", None)

    with pytest.raises(CliError, match="F2-PDF") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out")

    assert error.value.code == "CLI-LANE-F2-PDF"


def test_build_pptx_font_embedding_cli_error_is_propagated(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_embed(_path: Path) -> Path:
        raise CliError("embed ditolak", code="CLI-CUSTOM", exit_code=1)

    monkeypatch.setattr(autooffice.pdf, "embed_pptx_fonts", fail_embed)

    with pytest.raises(CliError, match="embed ditolak") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out")

    assert error.value.code == "CLI-CUSTOM"


def test_build_pptx_ambiguous_font_cleanup_preserves_build_dir(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_factory(monkeypatch, _FakeRenderer())

    def fail_embed(_path: Path) -> Path:
        raise autooffice.pdf.WordCleanupError("worker PowerPoint masih hidup")

    monkeypatch.setattr(autooffice.pdf, "embed_pptx_fonts", fail_embed)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="CLI-FONT-CLEANUP") as error:
        build_deck(deck_path, ("pptx",), out)

    workspace = deck_path.parent / ".autooffice-build" / deck_path.stem
    assert error.value.code == "CLI-FONT-CLEANUP"
    assert error.value.cleanup_ambiguous is True
    assert workspace.is_dir()
    assert (workspace / "render.pptx").is_file()


def test_build_pptx_font_embedding_os_error_reports_font_lane(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_embed(_path: Path) -> Path:
        raise OSError("PowerPoint tidak dapat dibuka")

    monkeypatch.setattr(autooffice.pdf, "embed_pptx_fonts", fail_embed)

    with pytest.raises(CliError, match="PowerPoint tidak dapat dibuka") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out")

    assert error.value.code == "CLI-FONT-EMBED"
    assert error.value.exit_code == 1


def test_build_pptx_font_embedding_may_return_none(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(autooffice.pdf, "embed_pptx_fonts", lambda _path: None)

    outcome = build_deck(deck_path, ("pptx",), tmp_path / "out")

    assert (tmp_path / "out" / "deck.pptx").is_file()
    assert outcome.files == (
        tmp_path / "out" / "deck.pptx",
        tmp_path / "out" / "deck.transcript.md",
    )


def test_build_deck_requires_at_least_one_target(deck_path: Path) -> None:
    with pytest.raises(CliError, match="minimal satu target") as error:
        build_deck(deck_path, ())

    assert error.value.code == "CLI-TARGET-MISSING"


def test_build_deck_rejects_unknown_theme_name(deck_path: Path, tmp_path: Path) -> None:
    with pytest.raises(CliError, match="theme tidak valid") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out", theme="ungu")

    assert error.value.code == "CLI-THEME"
    assert error.value.exit_code == 2
    assert not (tmp_path / "out").exists()


def test_build_deck_wraps_theme_resolution_value_error(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_theme(_name: str) -> object:
        raise ValueError("token rusak")

    monkeypatch.setattr("autooffice.design.resolve_theme", fail_theme)

    with pytest.raises(CliError, match="theme 'indigo' tidak valid: token rusak") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out")

    assert error.value.code == "CLI-THEME"


def test_build_deck_propagates_theme_autooffice_error(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_theme(_name: str) -> object:
        raise DesignTokenError("token wajib hilang")

    monkeypatch.setattr("autooffice.design.resolve_theme", fail_theme)

    with pytest.raises(DesignTokenError, match="token wajib hilang"):
        build_deck(deck_path, ("pptx",), tmp_path / "out")


def test_build_deck_layout_failure_reports_layout_lane(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_plan(_deck: object, _theme: object, *, fail_on_overflow: bool = False) -> object:
        raise LayoutError("grid tidak muat")

    monkeypatch.setattr("autooffice.deck.layout.overflow.plan_deck", fail_plan)

    with pytest.raises(CliError, match="layout deck gagal") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out")

    assert error.value.code == "CLI-LAYOUT"
    assert error.value.exit_code == 1
    assert error.value.path == str(deck_path)


def test_build_deck_layout_overflow_reports_keys(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "autooffice.deck.layout.overflow.plan_deck",
        lambda _deck, _theme, *, fail_on_overflow=False: object(),
    )
    monkeypatch.setattr(
        "autooffice.deck.layout.overflow.plan_overflow_keys",
        lambda _plan: ("s01.points", "s02.table1"),
    )

    with pytest.raises(CliError, match=r"s01\.points, s02\.table1") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out")

    assert error.value.code == "CLI-LAYOUT-OVERFLOW"


def test_build_deck_coverage_plan_failure_reports_fields(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coverage = CoveragePlan(
        deck_id="deck",
        declared_keys=(),
        visible_keys=(),
        sync_keys=(),
        data_keys=(),
        unkeyed_visible=("s01.points",),
        missing_alt=(),
        duplicate_keys=("s01.title",),
        charts=(),
    )
    monkeypatch.setattr("autooffice.deck.model.build_coverage_plan", lambda _deck: coverage)
    out = tmp_path / "out"

    with pytest.raises(CliError, match=r"unkeyed_visible: s01\.points") as error:
        build_deck(deck_path, ("pptx",), out, dry_run=True)

    assert error.value.code == "CLI-COVERAGE"
    assert "duplicate_keys: s01.title" in str(error.value)
    assert "missing_alt" not in str(error.value)
    assert not out.exists()


def test_build_deck_warning_without_format_uses_str(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _PlainDiagnostic:
        severity = "warning"

        def __str__(self) -> str:
            return "sentence_length: kalimat panjang"

    monkeypatch.setattr(
        "autooffice.deck.copy.check_copy",
        lambda *_args, **_kwargs: (_PlainDiagnostic(),),
    )
    monkeypatch.setattr("autooffice.deck.copy.has_errors", lambda _diagnostics: False)
    out = tmp_path / "out"

    outcome = build_deck(deck_path, ("pptx",), out, dry_run=True)

    assert outcome.warnings == ("sentence_length: kalimat panjang",)
    assert not out.exists()


def test_build_deck_rejects_unknown_sync_mode(deck_path: Path, tmp_path: Path) -> None:
    with pytest.raises(CliError, match="mode sync tidak valid") as error:
        build_deck(deck_path, ("slides",), tmp_path / "out", sync="nope")

    assert error.value.code == "CLI-SYNC-MODE"
    assert error.value.exit_code == 2


def test_build_deck_rejects_sync_without_slides_target(deck_path: Path, tmp_path: Path) -> None:
    with pytest.raises(CliError, match="--sync hanya valid") as error:
        build_deck(deck_path, ("pptx",), tmp_path / "out", sync="diff")

    assert error.value.code == "CLI-SYNC-TARGET"


def test_build_deck_dry_run_pptx_only_does_not_mention_pdf_or_workspace_keep(
    deck_path: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"

    outcome = build_deck(deck_path, ("pptx",), out, dry_run=True)

    assert outcome.files == (out / "deck.pptx", out / "deck.transcript.md")
    assert not any("PDF deck" in note for note in outcome.notes)
    workspace_note = (
        f"workspace build sementara: {deck_path.parent / '.autooffice-build' / deck_path.stem}"
    )
    assert workspace_note in outcome.notes
    assert not out.exists()


def test_build_deck_dry_run_keep_intermediate_note(
    deck_path: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"

    outcome = build_deck(deck_path, ("pptx",), out, dry_run=True, keep_intermediate=True)

    assert (
        f"intermediate dipertahankan: {deck_path.parent / '.autooffice-build' / deck_path.stem}"
        in outcome.notes
    )
    assert not out.exists()


def test_build_deck_pptx_and_pdf_share_rendered_pptx(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out"
    exported: list[Path] = []

    def fake_export(pptx: Path, pdf: Path) -> Path:
        exported.append(pptx)
        pdf.write_bytes(b"%PDF-1.7 fake\n")
        return pdf

    monkeypatch.setattr(autooffice.pdf, "export_pptx_pdf", fake_export)

    outcome = build_deck(deck_path, ("pptx", "pdf"), out)

    assert outcome.files == (out / "deck.pptx", out / "deck.pdf", out / "deck.transcript.md")
    assert exported == [out / "deck.pptx"]
    assert (out / "deck.pdf").read_bytes() == b"%PDF-1.7 fake\n"


def test_build_deck_without_transcript_does_not_copy_one(
    deck_path: Path,
    tmp_path: Path,
) -> None:
    (deck_path.parent / "transcripts.md").unlink()
    out = tmp_path / "out"

    outcome = build_deck(deck_path, ("pptx",), out)

    assert outcome.files == (out / "deck.pptx",)
    assert not (out / "deck.transcript.md").exists()


def test_build_deck_pdf_without_exporter_reports_lane(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(autooffice.pdf, "export_pptx_pdf", None)

    with pytest.raises(CliError, match="F2-PDF") as error:
        build_deck(deck_path, ("pdf",), tmp_path / "out")

    assert error.value.code == "CLI-LANE-F2-PDF"


def test_build_deck_pdf_exporter_cli_error_is_wrapped_with_pptx_path(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_export(_pptx: Path, _pdf: Path) -> Path:
        raise CliError("PowerPoint sibuk", code="CLI-CUSTOM", exit_code=1)

    monkeypatch.setattr(autooffice.pdf, "export_pptx_pdf", fail_export)

    with pytest.raises(CliError, match="PPTX selesai di") as error:
        build_deck(deck_path, ("pdf",), tmp_path / "out")

    assert error.value.code == "CLI-CUSTOM"
    assert error.value.path is not None
    assert error.value.path.endswith(".pptx")


def test_build_deck_pdf_exporter_os_error_reports_pdf_lane(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_export(_pptx: Path, _pdf: Path) -> Path:
        raise OSError("COM putus")

    monkeypatch.setattr(autooffice.pdf, "export_pptx_pdf", fail_export)

    with pytest.raises(CliError, match="COM putus") as error:
        build_deck(deck_path, ("pdf",), tmp_path / "out")

    assert error.value.code == "CLI-PDF"
    assert error.value.exit_code == 1


def test_build_deck_dry_run_slides_accepts_ready_credentials(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        @classmethod
        def from_environment(cls) -> _Settings:
            return cls()

    class _Tokens:
        @classmethod
        def from_environment(cls) -> _Tokens:
            return cls()

        def require(self) -> dict[str, object]:
            return {"access_token": "token"}

    monkeypatch.setattr("autooffice.cli.build.require_google_extra", lambda: None)
    monkeypatch.setattr("autooffice.google.OAuthSettings", _Settings)
    monkeypatch.setattr("autooffice.google.TokenStore", _Tokens)
    out = tmp_path / "out"

    outcome = build_deck(deck_path, ("slides",), out, dry_run=True)

    assert outcome.dry_run is True
    assert any("Google Slides: push staging" in note for note in outcome.notes)
    assert not out.exists()


def test_build_deck_dry_run_slides_reports_token_failure(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        @classmethod
        def from_environment(cls) -> _Settings:
            return cls()

    class _Tokens:
        @classmethod
        def from_environment(cls) -> _Tokens:
            return cls()

        def require(self) -> dict[str, object]:
            raise GoogleAuthError("token belum ada")

    monkeypatch.setattr("autooffice.cli.build.require_google_extra", lambda: None)
    monkeypatch.setattr("autooffice.google.OAuthSettings", _Settings)
    monkeypatch.setattr("autooffice.google.TokenStore", _Tokens)

    with pytest.raises(CliError, match="kredensial Google") as error:
        build_deck(deck_path, ("slides",), tmp_path / "out", dry_run=True)

    assert error.value.code == "CLI-GOOGLE-CREDENTIALS"


def test_build_deck_slides_without_services_checks_extra_and_pushes(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extra_calls: list[int] = []
    pushes: list[dict[str, object]] = []

    def fake_push(**kwargs: object) -> None:
        pushes.append(kwargs)
        staging = Path(str(kwargs["staging"]))
        pushes[-1]["staging_exists"] = staging.is_file()

    monkeypatch.setattr("autooffice.cli.build.require_google_extra", lambda: extra_calls.append(1))
    monkeypatch.setattr("autooffice.google.push_deck", fake_push)
    out = tmp_path / "out"

    outcome = build_deck(deck_path, ("slides",), out)

    assert len(extra_calls) == 2
    assert pushes[0]["staging_exists"] is True
    assert pushes[0]["mode"] == "push"
    assert "services" not in pushes[0]
    assert outcome.files == (out / "deck.transcript.md",)
    assert not (out / "deck.slides-upload.pptx").exists()


def test_build_deck_slides_result_path_is_added_to_files(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out"
    extra = out / "push-result.txt"

    def fake_push(**_kwargs: object) -> Path:
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("hasil", encoding="utf-8")
        return extra

    monkeypatch.setattr("autooffice.cli.build.require_google_extra", lambda: None)
    monkeypatch.setattr("autooffice.google.push_deck", fake_push)

    outcome = build_deck(deck_path, ("slides",), out)

    assert extra in outcome.files
    assert extra.is_file()


def test_build_deck_slides_missing_push_api_reports_lane(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("autooffice.google.push_deck", None)

    with pytest.raises(CliError, match="F2-GOOGLE") as error:
        build_deck(deck_path, ("slides",), tmp_path / "out", google_services=object())

    assert error.value.code == "CLI-LANE-F2-GOOGLE"
    assert error.value.exit_code == 1


def test_build_deck_slides_push_google_error_removes_staging(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_push(**_kwargs: object) -> None:
        raise GoogleError("remote menolak")

    monkeypatch.setattr("autooffice.google.push_deck", fail_push)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="remote menolak") as error:
        build_deck(deck_path, ("slides",), out, google_services=object())

    assert error.value.code == "CLI-GOOGLE"
    assert error.value.path == str(deck_path)
    assert not (out / "deck.slides-upload.pptx").exists()


def test_build_deck_slides_push_google_error_keeps_staging_when_requested(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_push(**_kwargs: object) -> None:
        raise GoogleError("remote menolak")

    monkeypatch.setattr("autooffice.google.push_deck", fail_push)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="remote menolak"):
        build_deck(
            deck_path,
            ("slides",),
            out,
            keep_intermediate=True,
            google_services=object(),
        )

    assert (out / "deck.slides-upload.pptx").is_file()


def test_build_deck_slides_push_cli_error_is_propagated(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_push(**_kwargs: object) -> None:
        raise CliError("ditimpa", code="CLI-CUSTOM", exit_code=1)

    monkeypatch.setattr("autooffice.google.push_deck", fail_push)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="ditimpa") as error:
        build_deck(deck_path, ("slides",), out, google_services=object())

    assert error.value.code == "CLI-CUSTOM"
    assert not (out / "deck.slides-upload.pptx").exists()


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ("{bukan json", "tidak dapat dibaca"),
        ("[]", "objek JSON"),
        ('{"presentation_id": ""}', "presentation_id"),
    ],
)
def test_build_deck_sync_reports_unusable_state(
    deck_path: Path,
    tmp_path: Path,
    content: str,
    match: str,
) -> None:
    state = deck_path.parent / ".autooffice" / "state" / f"{deck_path.stem}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(content, encoding="utf-8")

    with pytest.raises(CliError, match=match) as error:
        build_deck(
            deck_path,
            ("slides",),
            tmp_path / "out",
            sync="diff",
            google_services=object(),
        )

    assert error.value.code == "CLI-GOOGLE-STATE"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("file_name", ["...yaml", "..yaml", ".. .yaml"])
def test_build_deck_rejects_dot_stem_before_any_write(
    tmp_path: Path,
    file_name: str,
) -> None:
    source = tmp_path / file_name
    source.write_text("schema: autooffice.deck/v1\n", encoding="utf-8")
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("tetap ada", encoding="utf-8")

    with pytest.raises(CliError, match="stem") as error:
        build_deck(source, ("pptx",), tmp_path / "out")

    assert error.value.code == "CLI-INPUT-NAME"
    assert source.is_file()
    assert sentinel.read_text(encoding="utf-8") == "tetap ada"
    assert not (tmp_path / "out").exists()


def test_require_google_extra_reports_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("autooffice.cli.build.importlib.util.find_spec", lambda _name: None)

    with pytest.raises(CliError, match="extra 'google'") as error:
        require_google_extra()

    assert error.value.code == "CLI-GOOGLE-EXTRA"
    assert error.value.exit_code == 1


def test_dry_run_pptx_requires_pptx_renderer_class(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("autooffice.deck.render.pptx")
    module.create_renderer = lambda: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "autooffice.deck.render.pptx", module)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="PptxRenderer") as error:
        build_deck(deck_path, ("pptx",), out, dry_run=True)

    assert error.value.code == "CLI-LANE-F1-PPTX"
    assert not out.exists()


def test_dry_run_pdf_requires_pptx_renderer(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "autooffice.deck.render.pptx", _fake_empty_render_module())
    out = tmp_path / "out"

    with pytest.raises(CliError, match="PptxRenderer") as error:
        build_deck(deck_path, ("pdf",), out, dry_run=True)

    assert error.value.code == "CLI-LANE-F1-PPTX"
    assert not out.exists()


def test_dry_run_pdf_requires_pptx_converter(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(autooffice.pdf, "export_pptx_pdf", None)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="F2-PDF") as error:
        build_deck(deck_path, ("pdf",), out, dry_run=True)

    assert error.value.code == "CLI-LANE-F2-PDF"
    assert not out.exists()


def test_dry_run_slides_requires_google_operation(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("autooffice.google.push_deck", None)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="F2-GOOGLE") as error:
        build_deck(deck_path, ("slides",), out, dry_run=True, google_services=object())

    assert error.value.code == "CLI-LANE-F2-GOOGLE"
    assert not out.exists()


def test_dry_run_sync_requires_sync_deck_operation(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = deck_path.parent / ".autooffice" / "state" / f"{deck_path.stem}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text('{"presentation_id": "p1"}', encoding="utf-8")
    monkeypatch.setattr("autooffice.google.sync_deck", None)
    out = tmp_path / "out"

    with pytest.raises(CliError, match="F2-GOOGLE") as error:
        build_deck(
            deck_path,
            ("slides",),
            out,
            sync="diff",
            dry_run=True,
            google_services=object(),
        )

    assert error.value.code == "CLI-LANE-F2-GOOGLE"
    assert not out.exists()


def test_build_persists_mermaid_cache_across_cleanup(
    deck_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out"
    cache = deck_path.parent / ".autooffice" / "cache" / "mermaid"
    cache.mkdir(parents=True)
    seeded = cache / "seeded.png"
    seeded.write_bytes(b"seed")

    class _CacheRenderer(_FakeRenderer):
        def render(self, request: object) -> object:
            cache_dir = request.workspace / "cache" / "mermaid"  # type: ignore[attr-defined]
            assert (cache_dir / "seeded.png").read_bytes() == b"seed"
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / "diagram.png").write_bytes(b"diagram")
            return super().render(request)

    _use_factory(monkeypatch, _CacheRenderer())
    build_deck(deck_path, ("pptx",), out)

    assert (cache / "diagram.png").read_bytes() == b"diagram"
    assert (cache / "seeded.png").read_bytes() == b"seed"
    assert not (deck_path.parent / ".autooffice-build" / deck_path.stem).exists()
