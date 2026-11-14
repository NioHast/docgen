"""Tes edge case pipeline: validasi stage, target, workspace, dan run bercabang."""

import logging
import shutil
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import autooffice.docx.pipeline as pipeline_module
from autooffice.docx.adeu.paragraph_ids import AdeuOptions
from autooffice.docx.errors import (
    DocgenError,
    OutputError,
    StageError,
    StageOrderError,
    ToolMissingError,
    WordError,
)
from autooffice.docx.package import DocumentPackage
from autooffice.docx.package.bookmarks import PARAGRAPH_ID_RE
from autooffice.docx.pipeline import (
    CANONICAL_ORDER,
    CANONICAL_STAGES,
    ArtifactStore,
    BaseStage,
    BuildOptions,
    BuildReport,
    Pipeline,
    StageContext,
    StageName,
    StageResult,
    StageSpec,
    Workspace,
    _bookmark_names,
    _find_word,
    _platform_name,
    _resolve_target,
    _specs_for_classes,
    _verify_bookmarks,
    validate_stage_order,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "docx" / "minimal"
GOLDEN = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "golden" / "laporan-baseline.docx"
)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _result(
    name: StageName,
    *,
    changed: bool = False,
    warnings: tuple[str, ...] = (),
) -> StageResult:
    return StageResult(
        stage=name.value,
        status="ok",
        changed=changed,
        duration_ms=0,
        warnings=warnings,
    )


def _make_stage(
    spec: StageSpec,
    *,
    name: StageName | str | None = None,
    order: int | None = None,
    requires: tuple[StageName, ...] | None = None,
    mutates: frozenset[str] | None = None,
    idempotent: bool | None = None,
    runner: object = None,
    enabled: object = None,
) -> type[BaseStage]:
    stage_name = spec.name if name is None else name
    stage_order = spec.order if order is None else order
    stage_requires = spec.requires if requires is None else requires
    stage_mutates = spec.mutates if mutates is None else mutates
    stage_idempotent = spec.idempotent if idempotent is None else idempotent

    def run(self: BaseStage, ctx: StageContext) -> StageResult:
        if runner is not None:
            return runner(ctx)  # type: ignore[operator, no-any-return]
        return _result(stage_name)  # type: ignore[arg-type]

    def is_enabled(self: BaseStage, ctx: StageContext) -> bool:
        if enabled is not None:
            return enabled(ctx)  # type: ignore[operator, no-any-return]
        return True

    class_name = f"Fake{str(getattr(stage_name, 'value', stage_name)).title()}"
    return type(
        class_name,
        (BaseStage,),
        {
            "name": stage_name,
            "order": stage_order,
            "requires": stage_requires,
            "mutates": stage_mutates,
            "idempotent": stage_idempotent,
            "run": run,
            "enabled": is_enabled,
        },
    )


def _stage_classes() -> list[type[BaseStage]]:
    return [_make_stage(spec) for spec in CANONICAL_STAGES]


def _pipeline(
    *,
    runners: dict[StageName, object] | None = None,
    disabled: set[StageName] | None = None,
) -> Pipeline:
    known_runners = runners or {}
    disabled_names = disabled or set()
    classes: list[type[BaseStage]] = []
    for spec in CANONICAL_STAGES:
        classes.append(
            _make_stage(
                spec,
                runner=known_runners.get(spec.name),
                enabled=(lambda ctx: False) if spec.name in disabled_names else None,
            )
        )
    return Pipeline(stages=classes)


def _project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    shutil.copytree(FIXTURE, target)
    return target / "document.md"


def _pandoc_loads_golden(ctx: StageContext) -> StageResult:
    ctx.package = DocumentPackage.load(GOLDEN)
    return _result(StageName.PANDOC, changed=True)


def _mark_workspace(ctx: StageContext) -> StageResult:
    workspace = ctx.workspace.ensure()
    (workspace / "mermaid.marker").write_text("ok", encoding="utf-8")
    return _result(StageName.MERMAID, changed=True)


def _write_pdf(ctx: StageContext) -> StageResult:
    path = ctx.output_dir / f"{ctx.document.metadata.report_name}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n")
    return _result(StageName.PDF, changed=True)


def _raise_cleanup_error(ctx: StageContext) -> StageResult:
    workspace = ctx.workspace.ensure()
    (workspace / "partial.docx").write_bytes(b"PK\x03\x04partial")
    raise WordError(
        "worker Word masih hidup",
        code="WORD-CLEANUP",
        cleanup_ambiguous=True,
    )


def _raise_runtime(ctx: StageContext) -> StageResult:
    raise RuntimeError("boom")


def _raise_stage_error(ctx: StageContext) -> StageResult:
    raise StageError("custom", "gagal", code="CUSTOM-ERROR")


def _raise_office_error(ctx: StageContext) -> StageResult:
    raise StageError(StageName.OFFICE.value, "office gagal", code="OFFICE-TEST")


def _zip_docx(path: Path, document_xml: str) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)
    return path


def _bookmark_document(names: tuple[str, ...], *, close: bool = True) -> str:
    starts = "".join(
        f'<w:bookmarkStart w:id="{index}" w:name="{name}"/>' for index, name in enumerate(names)
    )
    ends = (
        "".join(f'<w:bookmarkEnd w:id="{index}"/>' for index in range(len(names))) if close else ""
    )
    return f'<w:document xmlns:w="{W_NS}"><w:body><w:p>{starts}{ends}</w:p></w:body></w:document>'


# ---------------------------------------------------------------------------
# validate_stage_order
# ---------------------------------------------------------------------------


def test_validate_stage_order_rejects_duplicate_names() -> None:
    specs = [*CANONICAL_STAGES, CANONICAL_STAGES[0]]

    with pytest.raises(StageOrderError, match="nama stage duplikat"):
        validate_stage_order(specs)


def test_validate_stage_order_reports_missing_and_extra_names() -> None:
    with pytest.raises(StageOrderError, match="hilang: pdf"):
        validate_stage_order(CANONICAL_STAGES[:-1])

    extra = StageSpec(
        name="extra",  # type: ignore[arg-type]
        order=999,
        module="stages/extra.py",
        mutates=frozenset(),
        idempotent=True,
    )
    with pytest.raises(StageOrderError, match="tambahan: extra"):
        validate_stage_order([*CANONICAL_STAGES, extra])


def test_validate_stage_order_reports_swapped_order() -> None:
    specs = list(CANONICAL_STAGES)
    specs[4], specs[5] = specs[5], specs[4]

    with pytest.raises(StageOrderError, match="urutan tidak sama dengan kontrak"):
        validate_stage_order(specs)


def test_validate_stage_order_rejects_non_increasing_orders() -> None:
    specs = list(CANONICAL_STAGES)
    specs[-1] = StageSpec(
        name=specs[-1].name,
        order=specs[-2].order,
        module=specs[-1].module,
        mutates=specs[-1].mutates,
        idempotent=specs[-1].idempotent,
        requires=specs[-1].requires,
    )

    with pytest.raises(StageOrderError, match="nilai order stage harus unik dan naik"):
        validate_stage_order(specs)


def test_validate_stage_order_rejects_unknown_part_and_bad_idempotent() -> None:
    unknown = list(CANONICAL_STAGES)
    unknown[0] = StageSpec(
        name=unknown[0].name,
        order=unknown[0].order,
        module=unknown[0].module,
        mutates=frozenset({"bogus"}),
        idempotent=True,
        requires=(),
    )
    with pytest.raises(StageOrderError, match="memutasi part tidak dikenal: bogus"):
        validate_stage_order(unknown)

    non_idempotent = list(CANONICAL_STAGES)
    non_idempotent[0] = StageSpec(
        name=non_idempotent[0].name,
        order=non_idempotent[0].order,
        module=non_idempotent[0].module,
        mutates=frozenset(),
        idempotent=False,
        requires=(),
    )
    with pytest.raises(StageOrderError, match="tidak boleh mendeklarasikan idempotent=False"):
        validate_stage_order(non_idempotent)


def test_validate_stage_order_rejects_inverted_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_order = list(CANONICAL_ORDER)
    new_order[16], new_order[17] = new_order[17], new_order[16]
    by_name = {spec.name: spec for spec in CANONICAL_STAGES}
    specs: list[StageSpec] = []
    for index, name in enumerate(new_order):
        original = by_name[name]
        specs.append(
            StageSpec(
                name=name,
                order=(index + 1) * 10,
                module=original.module,
                mutates=original.mutates,
                idempotent=original.idempotent,
                requires=tuple(new_order[:index]),
            )
        )
    monkeypatch.setattr(pipeline_module, "CANONICAL_ORDER", tuple(new_order))

    with pytest.raises(StageOrderError, match="urutan guard gagal"):
        validate_stage_order(specs)


# ---------------------------------------------------------------------------
# _specs_for_classes
# ---------------------------------------------------------------------------


def test_specs_for_classes_rejects_empty_pipeline() -> None:
    with pytest.raises(StageOrderError, match="tidak memiliki stage"):
        _specs_for_classes([])


def test_specs_for_classes_rejects_unknown_and_duplicate_names() -> None:
    classes = _stage_classes()
    unknown = _make_stage(CANONICAL_STAGES[0], name="bogus")

    with pytest.raises(StageOrderError, match="nama stage tidak dikenal"):
        _specs_for_classes([unknown, *classes[1:]])
    with pytest.raises(StageOrderError, match="terdaftar lebih dari sekali"):
        _specs_for_classes([*classes, classes[0]])


def test_specs_for_classes_rejects_missing_stage() -> None:
    classes = _stage_classes()
    classes.pop(4)

    with pytest.raises(StageOrderError, match="stage 'pandoc' tidak terdaftar"):
        _specs_for_classes(classes)


def test_specs_for_classes_rejects_wrong_order_requires_mutates_and_idempotent() -> None:
    wrong_order = _stage_classes()
    wrong_order[0] = _make_stage(CANONICAL_STAGES[0], order=11)
    with pytest.raises(StageOrderError, match="memakai order 11, harus 10"):
        _specs_for_classes(wrong_order)

    wrong_requires = _stage_classes()
    wrong_requires[5] = _make_stage(CANONICAL_STAGES[5], requires=())
    with pytest.raises(StageOrderError, match="requires stage 'sections' bukan prefix"):
        _specs_for_classes(wrong_requires)

    wrong_mutates = _stage_classes()
    wrong_mutates[0] = _make_stage(CANONICAL_STAGES[0], mutates=frozenset({"bogus"}))
    with pytest.raises(StageOrderError, match="memutasi part tidak dikenal: bogus"):
        _specs_for_classes(wrong_mutates)

    wrong_idempotent = _stage_classes()
    wrong_idempotent[0] = _make_stage(CANONICAL_STAGES[0], idempotent=False)
    with pytest.raises(StageOrderError, match="salah mendeklarasikan idempotent"):
        _specs_for_classes(wrong_idempotent)


def test_specs_for_classes_rejects_extra_registered_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "CANONICAL_STAGES", CANONICAL_STAGES[:-1])

    with pytest.raises(StageOrderError, match="stage tidak dikenal: pdf"):
        _specs_for_classes(_stage_classes())


def test_base_stage_run_is_abstract_contract() -> None:
    with pytest.raises(NotImplementedError):
        BaseStage.run(object(), object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Workspace, artifact, report
# ---------------------------------------------------------------------------


def test_workspace_ensure_rejects_file(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.write_text("bukan direktori", encoding="utf-8")
    workspace = Workspace(root=root, keep=False)

    with pytest.raises(OutputError, match="workspace bukan direktori") as excinfo:
        workspace.ensure()

    assert excinfo.value.code == "OUTPUT-WORKSPACE"


def test_workspace_path_and_intermediate_guard_escape(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / "workspace", keep=False)
    workspace.ensure()

    assert workspace.exists is True
    assert workspace.intermediate("sub/file.txt") == workspace.root / "sub" / "file.txt"

    with pytest.raises(OutputError, match="workspace") as excinfo:
        workspace.path("../keluar.txt")

    assert excinfo.value.code == "OUTPUT-WORKSPACE"


def test_workspace_cleanup_handles_file_and_missing_root(tmp_path: Path) -> None:
    file_root = tmp_path / "workspace-file"
    file_root.write_text("x", encoding="utf-8")
    Workspace(root=file_root, keep=False).cleanup()
    assert not file_root.exists()

    missing = Workspace(root=tmp_path / "tidak-ada", keep=False)
    missing.cleanup()
    assert missing.exists is False


def test_workspace_ensure_wraps_mkdir_oserror(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("berkas", encoding="utf-8")
    workspace = Workspace(root=blocker / "workspace", keep=False)

    with pytest.raises(OutputError, match="workspace tidak dapat dibuat") as excinfo:
        workspace.ensure()

    assert excinfo.value.code == "OUTPUT-WORKSPACE"


def test_workspace_cleanup_wraps_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    workspace = Workspace(root=root, keep=False)

    def fail_rmtree(path: Path) -> None:
        raise OSError("akses ditolak")

    monkeypatch.setattr(pipeline_module.shutil, "rmtree", fail_rmtree)

    with pytest.raises(OutputError, match="gagal membersihkan workspace") as excinfo:
        workspace.cleanup()

    assert excinfo.value.code == "OUTPUT-WORKSPACE"


def _junction_or_skip(link: Path, target: Path) -> None:
    """Buat junction Windows atau lewati tes bila tidak tersedia."""

    if sys.platform != "win32":
        pytest.skip("junction hanya tersedia di Windows")
    try:
        import _winapi

        _winapi.CreateJunction(str(target.resolve()), str(link))
    except (AttributeError, ImportError, OSError) as exc:  # pragma: no cover - platform
        pytest.skip(f"junction tidak tersedia: {exc}")


def _dir_link_or_skip(link: Path, target: Path) -> None:
    """Buat junction di Windows, symlink direktori di platform lain."""

    if sys.platform == "win32":
        _junction_or_skip(link, target)
        return
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - izin symlink
        pytest.skip(f"symlink tidak tersedia: {exc}")


def _remove_dir_link(link: Path) -> None:
    if not link.exists() and not link.is_symlink():
        return
    try:
        link.unlink()
    except OSError:  # pragma: no cover - junction Windows lama
        link.rmdir()


@pytest.mark.parametrize("target_name", [".git", "assets", "."])
def test_workspace_ensure_rejects_laporan_build_link_to_other_target(
    tmp_path: Path,
    target_name: str,
) -> None:
    document = tmp_path / "document"
    document.mkdir()
    source = document / "document.md"
    source.write_text("sumber", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("sentinel luar", encoding="utf-8")
    if target_name == ".":
        target = document
    else:
        target = document / target_name
        target.mkdir()
    sentinel = target / "sentinel.txt"
    sentinel.write_text("jangan hilang", encoding="utf-8")
    link = document / ".laporan-build"
    _dir_link_or_skip(link, target)
    workspace = Workspace(root=link, keep=False)
    try:
        with pytest.raises(OutputError, match="workspace symlink/junction") as excinfo:
            workspace.ensure()

        assert excinfo.value.code == "OUTPUT-WORKSPACE"
        assert source.read_text(encoding="utf-8") == "sumber"
        assert outside.read_text(encoding="utf-8") == "sentinel luar"
        assert sentinel.read_text(encoding="utf-8") == "jangan hilang"
        workspace.cleanup()
        assert sentinel.read_text(encoding="utf-8") == "jangan hilang"
    finally:
        _remove_dir_link(link)


def test_workspace_cleanup_unlinks_junction_without_deleting_target(tmp_path: Path) -> None:
    document = tmp_path / "document"
    document.mkdir()
    target = document / ".git"
    target.mkdir()
    sentinel = target / "config"
    sentinel.write_text("jangan hilang", encoding="utf-8")
    link = document / ".laporan-build"
    _dir_link_or_skip(link, target)

    Workspace(root=link, keep=False).cleanup()

    assert sentinel.read_text(encoding="utf-8") == "jangan hilang"
    assert target.is_dir()
    assert not link.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="junction hanya tersedia di Windows")
def test_workspace_ensure_rejects_windows_junction_laporan_build(tmp_path: Path) -> None:
    document = tmp_path / "document"
    document.mkdir()
    target = document / ".git"
    target.mkdir()
    sentinel = target / "config"
    sentinel.write_text("jangan hilang", encoding="utf-8")
    link = document / ".laporan-build"
    _junction_or_skip(link, target)
    workspace = Workspace(root=link, keep=False)
    try:
        assert link.is_junction()
        with pytest.raises(OutputError, match="workspace symlink/junction") as excinfo:
            workspace.ensure()

        assert excinfo.value.code == "OUTPUT-WORKSPACE"
        assert sentinel.read_text(encoding="utf-8") == "jangan hilang"
    finally:
        _remove_dir_link(link)


def test_artifact_store_rejects_duplicate_and_missing_key() -> None:
    artifacts = ArtifactStore()
    artifacts.put("docx", Path("a.docx"))

    with pytest.raises(OutputError, match="sudah ada") as duplicate:
        artifacts.put("docx", Path("b.docx"))
    with pytest.raises(OutputError, match="tidak ditemukan") as missing:
        artifacts.get("pdf")

    assert duplicate.value.code == "OUTPUT-ARTIFACT"
    assert missing.value.code == "OUTPUT-ARTIFACT"
    assert artifacts.keys() == ("docx",)


def test_build_report_records_warnings_and_changed_count() -> None:
    report = BuildReport()
    report.record(_result(StageName.VALIDATE, changed=True, warnings=("satu",)))
    report.record(_result(StageName.MERMAID))
    report.add_warning("dua")

    assert report.changed == 1
    assert report.warnings == ["satu", "dua"]


# ---------------------------------------------------------------------------
# Platform, Word, dan target
# ---------------------------------------------------------------------------


def test_platform_name_maps_windows_and_other(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert _platform_name() == "windows"
    monkeypatch.setattr(sys, "platform", "linux")
    assert _platform_name() == "linux"


def test_find_word_uses_office_finder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "windows")
    monkeypatch.setattr(
        "autooffice.docx.stages.office.find_word_executable",
        lambda: "C:/Office/WINWORD.EXE",
    )

    assert _find_word() == "C:/Office/WINWORD.EXE"


class _FakeWinreg(SimpleNamespace):
    HKEY_LOCAL_MACHINE = 1
    HKEY_CURRENT_USER = 2

    @staticmethod
    def OpenKey(hive: int, key_path: str) -> object:
        raise OSError("tidak ada")


def test_find_word_falls_back_to_program_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    office = tmp_path / "Microsoft Office" / "root" / "Office16"
    office.mkdir(parents=True)
    executable = office / "WINWORD.EXE"
    executable.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "windows")
    monkeypatch.setattr("autooffice.docx.stages.office.find_word_executable", lambda: None)
    monkeypatch.setitem(sys.modules, "winreg", _FakeWinreg())
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)

    assert _find_word() == str(executable)


def test_find_word_returns_none_when_all_locations_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "windows")
    monkeypatch.setattr("autooffice.docx.stages.office.find_word_executable", lambda: None)
    monkeypatch.setitem(sys.modules, "winreg", _FakeWinreg())
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))

    assert _find_word() is None


def test_resolve_target_docx_short_circuits() -> None:
    assert _resolve_target(BuildOptions(target="docx")) == ("docx", [])


def test_resolve_target_non_windows_rejects_pdf_and_both_without_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "linux")

    with pytest.raises(ToolMissingError, match="PDF hanya didukung di Windows"):
        _resolve_target(BuildOptions(target="pdf"))
    with pytest.raises(ToolMissingError, match="target both tidak didukung"):
        _resolve_target(BuildOptions(target="both"))


def test_resolve_target_non_windows_degrades_both_with_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "linux")

    target, warnings = _resolve_target(BuildOptions(target="both", allow_missing_word=True))

    assert target == "docx"
    assert len(warnings) == 1
    assert "diturunkan menjadi docx" in warnings[0]


def test_resolve_target_windows_requires_word(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "windows")
    monkeypatch.setattr(pipeline_module, "_find_word", lambda: None)

    with pytest.raises(ToolMissingError, match="target pdf membutuhkan"):
        _resolve_target(BuildOptions(target="pdf"))
    with pytest.raises(ToolMissingError, match="target both membutuhkan"):
        _resolve_target(BuildOptions(target="both"))


def test_resolve_target_windows_degrades_both_without_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "windows")
    monkeypatch.setattr(pipeline_module, "_find_word", lambda: None)

    target, warnings = _resolve_target(BuildOptions(target="both", allow_missing_word=True))

    assert target == "docx"
    assert "PDF dilewati" in warnings[0]


def test_resolve_target_windows_with_word_keeps_requested_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "windows")
    monkeypatch.setattr(pipeline_module, "_find_word", lambda: "C:/WINWORD.EXE")

    assert _resolve_target(BuildOptions(target="pdf")) == ("pdf", [])
    assert _resolve_target(BuildOptions(target="both")) == ("both", [])


# ---------------------------------------------------------------------------
# Bookmark verification
# ---------------------------------------------------------------------------


def test_bookmark_names_reads_only_paragraph_ids(tmp_path: Path) -> None:
    path = _zip_docx(
        tmp_path / "out.docx",
        _bookmark_document(("p0002", "lain", "p0001")),
    )

    assert _bookmark_names(path) == ("p0002", "p0001")


def test_bookmark_names_reports_bad_zip_and_bad_xml(tmp_path: Path) -> None:
    bad_zip = tmp_path / "bad.docx"
    bad_zip.write_bytes(b"bukan zip")
    with pytest.raises(StageError, match="tidak dapat dibaca") as excinfo:
        _bookmark_names(bad_zip)
    assert excinfo.value.code == "OFFICE-BOOKMARK"

    bad_xml = _zip_docx(tmp_path / "bad-xml.docx", "<w:document")
    with pytest.raises(StageError, match="bukan XML valid") as excinfo:
        _bookmark_names(bad_xml)
    assert excinfo.value.code == "OFFICE-BOOKMARK"


def test_verify_bookmarks_accepts_exact_sequence(tmp_path: Path) -> None:
    path = _zip_docx(tmp_path / "ok.docx", _bookmark_document(("p0001", "p0002")))
    before = path.read_bytes()

    assert _verify_bookmarks(path, ("p0001", "p0002")) is None

    assert _bookmark_names(path) == ("p0001", "p0002")
    assert path.read_bytes() == before


def test_verify_bookmarks_rejects_start_without_end(tmp_path: Path) -> None:
    path = _zip_docx(
        tmp_path / "unclosed.docx",
        _bookmark_document(("p0001",), close=False),
    )

    with pytest.raises(DocgenError, match="tidak memiliki bookmarkEnd") as excinfo:
        _verify_bookmarks(path, ("p0001",))

    assert excinfo.value.code == "OFFICE-BOOKMARK"


def test_verify_bookmarks_reports_missing_extra_and_reordered(tmp_path: Path) -> None:
    missing = _zip_docx(tmp_path / "missing.docx", _bookmark_document(("p0001",)))
    with pytest.raises(DocgenError, match="hilang: p0002") as missing_error:
        _verify_bookmarks(missing, ("p0001", "p0002"))
    assert missing_error.value.code == "OFFICE-BOOKMARK"

    extra = _zip_docx(tmp_path / "extra.docx", _bookmark_document(("p0001", "p0002")))
    with pytest.raises(DocgenError, match="tambahan: p0002"):
        _verify_bookmarks(extra, ("p0001",))

    reordered = _zip_docx(
        tmp_path / "reordered.docx",
        _bookmark_document(("p0002", "p0001")),
    )
    with pytest.raises(DocgenError, match="urutan bookmark berubah"):
        _verify_bookmarks(reordered, ("p0001", "p0002"))


# ---------------------------------------------------------------------------
# _run_batch
# ---------------------------------------------------------------------------


def _batch_context() -> SimpleNamespace:
    return SimpleNamespace(
        report=BuildReport(),
        logger=logging.getLogger("tests.pipeline"),
        document=SimpleNamespace(path=Path("document.md")),
    )


def test_run_batch_records_skipped_stage_without_running_it() -> None:
    stage_class = _make_stage(
        CANONICAL_STAGES[0],
        runner=_raise_runtime,
        enabled=lambda ctx: False,
    )
    pipeline = Pipeline(stages=_stage_classes())
    ctx = _batch_context()

    pipeline._run_batch([stage_class()], ctx)

    assert len(ctx.report.stages) == 1
    result = ctx.report.stages[0]
    assert result.status == "skipped"
    assert result.changed is False
    assert result.warnings == ("stage 'validate' dinonaktifkan oleh opsi build.",)


def test_run_batch_passes_docgen_errors_and_wraps_unknown_errors() -> None:
    pipeline = Pipeline(stages=_stage_classes())

    with pytest.raises(StageError) as custom:
        pipeline._run_batch(
            [_make_stage(CANONICAL_STAGES[0], runner=_raise_stage_error)()],
            _batch_context(),
        )
    assert custom.value.code == "CUSTOM-ERROR"

    with pytest.raises(StageError, match="stage 'validate' gagal: boom") as wrapped:
        pipeline._run_batch(
            [_make_stage(CANONICAL_STAGES[0], runner=_raise_runtime)()],
            _batch_context(),
        )
    assert wrapped.value.code == "STAGE-UNHANDLED"
    assert isinstance(wrapped.value.cause, RuntimeError)


def test_run_batch_preserves_cleanup_ambiguity_on_unknown_error() -> None:
    class CleanupError(RuntimeError):
        cleanup_ambiguous = True

    def raise_cleanup(ctx: StageContext) -> StageResult:
        raise CleanupError("worker COM masih hidup")

    pipeline = Pipeline(stages=_stage_classes())

    with pytest.raises(StageError, match="worker COM masih hidup") as wrapped:
        pipeline._run_batch(
            [_make_stage(CANONICAL_STAGES[0], runner=raise_cleanup)()],
            _batch_context(),
        )

    assert wrapped.value.code == "STAGE-UNHANDLED"
    assert wrapped.value.cleanup_ambiguous is True


# ---------------------------------------------------------------------------
# Pipeline.run
# ---------------------------------------------------------------------------


def test_pipeline_run_writes_docx_and_manifest_then_cleans_workspace(
    tmp_path: Path,
) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(runners={StageName.PANDOC: _pandoc_loads_golden})

    result = pipeline.run(document, BuildOptions(target="docx"))

    expected_docx = document.parent / "Paritas.docx"
    expected_manifest = document.parent / ".laporan" / "manifest.json"
    assert result.docx == expected_docx
    assert expected_docx.is_file()
    assert result.pdf is None
    assert result.manifest == expected_manifest
    assert expected_manifest.is_file()
    assert result.kept_workspace is None
    assert not (document.parent / ".laporan-build").exists()
    assert [stage.stage for stage in result.stages] == [name.value for name in CANONICAL_ORDER]


def test_pipeline_run_preserves_workspace_on_ambiguous_cleanup(
    tmp_path: Path,
) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(
        runners={
            StageName.MERMAID: _mark_workspace,
            StageName.PANDOC: _raise_cleanup_error,
        }
    )

    with pytest.raises(WordError, match="WORD-CLEANUP") as excinfo:
        pipeline.run(document, BuildOptions(target="docx", adeu=False))

    workspace = document.parent / ".laporan-build"
    assert excinfo.value.code == "WORD-CLEANUP"
    assert excinfo.value.cleanup_ambiguous is True
    assert workspace.is_dir()
    assert (workspace / "partial.docx").is_file()
    assert (workspace / "mermaid.marker").is_file()
    assert any("cleanup Office ambigu" in note for note in excinfo.value.__notes__)


def test_pipeline_run_keeps_workspace_and_records_disabled_stage(tmp_path: Path) -> None:
    document = _project(tmp_path)
    output_dir = tmp_path / "out"
    pipeline = _pipeline(
        runners={
            StageName.MERMAID: _mark_workspace,
            StageName.PANDOC: _pandoc_loads_golden,
        },
        disabled={StageName.TERMS},
    )

    result = pipeline.run(
        document,
        BuildOptions(target="docx", keep=True, adeu=False),
        output_dir=output_dir,
    )

    workspace = document.parent / ".laporan-build"
    assert result.docx == output_dir / "Paritas.docx"
    assert result.docx is not None
    assert result.docx.is_file()
    assert result.manifest is None
    assert result.kept_workspace == workspace
    assert (workspace / "mermaid.marker").read_text(encoding="utf-8") == "ok"
    assert any("dinonaktifkan" in warning for warning in result.warnings)


def test_pipeline_run_both_allow_returns_docx_when_word_com_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from autooffice.docx.stages.office import OfficeStage
    from autooffice.docx.stages.pdf import PdfStage

    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "windows")
    monkeypatch.setattr(pipeline_module, "_find_word", lambda: "C:/WINWORD.EXE")
    monkeypatch.setattr("autooffice.docx.stages.office.word_available", lambda: False)
    document = _project(tmp_path)
    classes: list[type[BaseStage]] = []
    for spec in CANONICAL_STAGES:
        if spec.name is StageName.PANDOC:
            classes.append(_make_stage(spec, runner=_pandoc_loads_golden))
        elif spec.name is StageName.OFFICE:
            classes.append(OfficeStage)
        elif spec.name is StageName.PDF:
            classes.append(PdfStage)
        else:
            classes.append(_make_stage(spec))
    pipeline = Pipeline(stages=classes)

    result = pipeline.run(
        document,
        BuildOptions(target="both", allow_missing_word=True, adeu=False),
    )

    assert result.docx == document.parent / "Paritas.docx"
    assert result.docx is not None
    assert result.docx.is_file()
    assert result.pdf is None
    assert any("PDF dilewati" in warning for warning in result.warnings)


def test_pipeline_run_degrades_both_to_docx_on_non_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "linux")
    document = _project(tmp_path)
    pipeline = _pipeline(runners={StageName.PANDOC: _pandoc_loads_golden})

    result = pipeline.run(
        document,
        BuildOptions(target="both", allow_missing_word=True, adeu=False),
    )

    assert result.docx == document.parent / "Paritas.docx"
    assert result.pdf is None
    assert any("diturunkan menjadi docx" in warning for warning in result.warnings)


def test_pipeline_run_pdf_target_uses_and_removes_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "windows")
    monkeypatch.setattr(pipeline_module, "_find_word", lambda: "C:/WINWORD.EXE")
    document = _project(tmp_path)
    pipeline = _pipeline(
        runners={
            StageName.PANDOC: _pandoc_loads_golden,
            StageName.PDF: _write_pdf,
        }
    )

    result = pipeline.run(document, BuildOptions(target="pdf", adeu=False))

    assert result.docx is None
    assert result.pdf == document.parent / "Paritas.pdf"
    assert result.pdf is not None
    assert result.pdf.is_file()
    assert not (document.parent / ".laporan-build").exists()


def test_pipeline_run_both_target_writes_docx_and_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline_module, "_platform_name", lambda: "windows")
    monkeypatch.setattr(pipeline_module, "_find_word", lambda: "C:/WINWORD.EXE")
    document = _project(tmp_path)
    pipeline = _pipeline(
        runners={
            StageName.PANDOC: _pandoc_loads_golden,
            StageName.PDF: _write_pdf,
        }
    )

    result = pipeline.run(document, BuildOptions(target="both", adeu=False))

    assert result.docx == document.parent / "Paritas.docx"
    assert result.pdf == document.parent / "Paritas.pdf"
    assert result.docx is not None
    assert result.pdf is not None
    assert result.docx.is_file()
    assert result.pdf.is_file()


def test_pipeline_run_rejects_output_dir_inside_workspace(tmp_path: Path) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(runners={StageName.PANDOC: _pandoc_loads_golden})
    workspace = document.parent / ".laporan-build"

    with pytest.raises(OutputError, match="tidak boleh berada di dalam workspace") as excinfo:
        pipeline.run(
            document,
            BuildOptions(target="docx", keep=False, adeu=False),
            output_dir=workspace,
        )

    assert excinfo.value.code == "OUTPUT-WORKSPACE"
    assert not workspace.exists()


def test_pipeline_run_allows_output_dir_inside_kept_workspace(tmp_path: Path) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(runners={StageName.PANDOC: _pandoc_loads_golden})
    workspace = document.parent / ".laporan-build"

    result = pipeline.run(
        document,
        BuildOptions(target="docx", keep=True, adeu=False),
        output_dir=workspace,
    )

    expected_docx = workspace / "Paritas.docx"
    assert result.docx == expected_docx
    assert result.docx is not None
    assert result.docx.is_file()
    assert result.kept_workspace == workspace
    assert workspace.is_dir()


def test_pipeline_run_rejects_missing_docx_after_save(tmp_path: Path) -> None:
    document = _project(tmp_path)

    def remove_saved_docx(ctx: StageContext) -> StageResult:
        ctx.artifacts.require("docx").unlink()
        return _result(StageName.OFFICE)

    pipeline = _pipeline(
        runners={
            StageName.PANDOC: _pandoc_loads_golden,
            StageName.OFFICE: remove_saved_docx,
        }
    )

    with pytest.raises(OutputError, match="DOCX tidak terbentuk") as excinfo:
        pipeline.run(document, BuildOptions(target="docx", adeu=False))

    assert excinfo.value.code == "OUTPUT-DOCX"
    assert not (document.parent / ".laporan-build").exists()


def test_pipeline_run_wraps_output_directory_mkdir_failure(tmp_path: Path) -> None:
    document = _project(tmp_path)
    blocker = tmp_path / "blocked"
    blocker.write_text("berkas", encoding="utf-8")
    pipeline = _pipeline(runners={StageName.PANDOC: _pandoc_loads_golden})

    with pytest.raises(OutputError, match="direktori output tidak dapat dibuat") as excinfo:
        pipeline.run(
            document,
            BuildOptions(target="docx", adeu=False),
            output_dir=blocker,
        )

    assert excinfo.value.code == "OUTPUT-DIRECTORY"
    assert not (document.parent / ".laporan-build").exists()


def test_pipeline_cleanup_failure_does_not_mask_original_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(runners={StageName.PANDOC: _raise_runtime})

    def fail_cleanup(self: Workspace) -> None:
        raise OutputError("gagal membersihkan workspace uji", code="OUTPUT-WORKSPACE")

    monkeypatch.setattr(Workspace, "cleanup", fail_cleanup)

    with pytest.raises(StageError, match="stage 'pandoc' gagal: boom") as excinfo:
        pipeline.run(document, BuildOptions(target="docx", adeu=False))

    assert excinfo.value.code == "STAGE-UNHANDLED"
    assert any("gagal membersihkan" in note for note in excinfo.value.__notes__)


def test_pipeline_cleanup_failure_raises_without_original_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(runners={StageName.PANDOC: _pandoc_loads_golden})

    def fail_cleanup(self: Workspace) -> None:
        raise OutputError("gagal membersihkan workspace uji", code="OUTPUT-WORKSPACE")

    monkeypatch.setattr(Workspace, "cleanup", fail_cleanup)

    with pytest.raises(OutputError, match="gagal membersihkan workspace uji") as excinfo:
        pipeline.run(document, BuildOptions(target="docx", adeu=False))

    assert excinfo.value.code == "OUTPUT-WORKSPACE"


def test_pipeline_run_requires_package_after_presave_stages(tmp_path: Path) -> None:
    document = _project(tmp_path)

    with pytest.raises(StageError, match="package DOCX tidak terbentuk") as excinfo:
        _pipeline().run(document, BuildOptions(target="docx", adeu=False))

    assert excinfo.value.code == "STAGE-PACKAGE"
    assert not (document.parent / ".laporan-build").exists()


@pytest.mark.parametrize("keep", [False, True])
def test_pipeline_run_wraps_stage_failure_and_respects_keep(
    tmp_path: Path,
    keep: bool,
) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(
        runners={
            StageName.MERMAID: _mark_workspace,
            StageName.PANDOC: _raise_runtime,
        }
    )

    with pytest.raises(StageError, match="stage 'pandoc' gagal: boom") as excinfo:
        pipeline.run(document, BuildOptions(target="docx", keep=keep, adeu=False))

    workspace = document.parent / ".laporan-build"
    assert excinfo.value.code == "STAGE-UNHANDLED"
    assert workspace.exists() is keep


def test_pipeline_run_does_not_swallow_docgen_stage_error(tmp_path: Path) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(
        runners={
            StageName.MERMAID: _mark_workspace,
            StageName.PANDOC: _raise_stage_error,
        }
    )

    with pytest.raises(StageError, match="gagal") as excinfo:
        pipeline.run(document, BuildOptions(target="docx", adeu=False))

    assert excinfo.value.code == "CUSTOM-ERROR"
    assert not (document.parent / ".laporan-build").exists()


def test_pipeline_run_post_save_failure_happens_after_docx_write(tmp_path: Path) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(
        runners={
            StageName.PANDOC: _pandoc_loads_golden,
            StageName.OFFICE: _raise_office_error,
        }
    )

    with pytest.raises(StageError, match="office gagal") as excinfo:
        pipeline.run(document, BuildOptions(target="docx", adeu=False))

    assert excinfo.value.code == "OFFICE-TEST"
    assert (document.parent / "Paritas.docx").is_file()
    assert not (document.parent / ".laporan-build").exists()


def test_pipeline_run_bookmark_verification_failure_is_reported(tmp_path: Path) -> None:
    document = _project(tmp_path)

    def corrupt_bookmarks(ctx: StageContext) -> StageResult:
        docx = ctx.artifacts.require("docx")
        _zip_docx(docx, _bookmark_document(()))
        return _result(StageName.OFFICE)

    pipeline = _pipeline(
        runners={
            StageName.PANDOC: _pandoc_loads_golden,
            StageName.OFFICE: corrupt_bookmarks,
        }
    )

    with pytest.raises(DocgenError, match="bookmark pNNNN tidak dipertahankan") as excinfo:
        pipeline.run(document, BuildOptions(target="docx"))

    assert excinfo.value.code == "OFFICE-BOOKMARK"


def test_pipeline_run_without_adeu_removes_bookmarks(tmp_path: Path) -> None:
    document = _project(tmp_path)
    pipeline = _pipeline(runners={StageName.PANDOC: _pandoc_loads_golden})

    result = pipeline.run(
        document,
        BuildOptions(target="docx", adeu=False),
        output_dir=tmp_path / "out",
    )

    assert result.manifest is None
    assert result.docx is not None
    package = DocumentPackage.load(result.docx)
    bookmark_names = [
        element.get(f"{{{W_NS}}}name") or ""
        for element in package.xml("word/document.xml").iter(f"{{{W_NS}}}bookmarkStart")
    ]
    assert [name for name in bookmark_names if PARAGRAPH_ID_RE.fullmatch(name)] == []


def test_adeu_options_are_not_constructed_for_missing_manifest_support() -> None:
    options = AdeuOptions(bookmarks=False, manifest=False, source_scan=False)

    assert options.bookmarks is False
    assert options.manifest is False
    assert options.source_scan is False
