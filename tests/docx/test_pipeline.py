"""Tes unit orkestrasi pipeline: nama stage, urutan, opsi, dan workspace."""

from pathlib import Path

import pytest

from autooffice.docx.errors import OutputError, StageOrderError
from autooffice.docx.paths import output_directory
from autooffice.docx.pipeline import (
    CANONICAL_ORDER,
    CANONICAL_STAGES,
    ArtifactStore,
    BuildOptions,
    Pipeline,
    StageName,
    StageSpec,
    Workspace,
    _adeu_options,
    validate_stage_order,
)
from autooffice.docx.stages.pandoc import build_pandoc_command


def test_stage_name_contains_all_canonical_stages() -> None:
    assert set(CANONICAL_ORDER) == set(StageName)
    assert len(CANONICAL_ORDER) == len(StageName)
    assert StageName.FRONT_MATTER in CANONICAL_ORDER
    assert CANONICAL_ORDER[:5] == (
        StageName.VALIDATE,
        StageName.MERMAID,
        StageName.STYLE_REFERENCE,
        StageName.FRONT_MATTER,
        StageName.PANDOC,
    )
    assert StageName.LISTS in CANONICAL_ORDER
    assert StageName.CAPTIONS.value == "captions"


def test_canonical_specs_requires_is_prefix() -> None:
    for index, spec in enumerate(CANONICAL_STAGES):
        assert spec.name is CANONICAL_ORDER[index]
        assert spec.requires == CANONICAL_ORDER[:index]
        assert spec.mutates <= {
            "workspace",
            "cache",
            "package",
            "word/document.xml",
            "word/numbering.xml",
            "word/styles.xml",
            "word/header*.xml",
            "word/footer*.xml",
            "word/_rels/document.xml.rels",
            "[Content_Types].xml",
        }
        if spec.name in {StageName.OFFICE, StageName.PDF}:
            assert spec.idempotent is False
        else:
            assert spec.idempotent is True


def test_canonical_orders_unique_and_increasing() -> None:
    orders = [spec.order for spec in CANONICAL_STAGES]
    assert orders == sorted(orders)
    assert len(orders) == len(set(orders))
    by_name = {spec.name: spec.order for spec in CANONICAL_STAGES}
    assert by_name[StageName.FRONT_MATTER] == 35
    assert by_name[StageName.PANDOC] == 40
    assert by_name[StageName.PDF] == 170


def test_validate_stage_order_rejects_swapped_order() -> None:
    specs = list(CANONICAL_STAGES)
    specs[4], specs[5] = specs[5], specs[4]
    with pytest.raises(StageOrderError):
        validate_stage_order(specs)


def test_validate_stage_order_rejects_missing_stage() -> None:
    with pytest.raises(StageOrderError):
        validate_stage_order(CANONICAL_STAGES[:-1])


def test_validate_stage_order_rejects_requires_not_prefix() -> None:
    specs = list(CANONICAL_STAGES)
    broken = StageSpec(
        name=specs[5].name,
        order=specs[5].order,
        module=specs[5].module,
        mutates=specs[5].mutates,
        idempotent=specs[5].idempotent,
        requires=(StageName.PANDOC,),
    )
    specs[5] = broken
    with pytest.raises(StageOrderError):
        validate_stage_order(specs)


def test_pipeline_registers_each_stage_exactly_once() -> None:
    pipeline = Pipeline()
    names = [stage.name for stage in pipeline.stages]
    assert names == list(CANONICAL_ORDER)
    assert len(set(names)) == len(names)
    assert [spec.name for spec in pipeline.specs] == list(CANONICAL_ORDER)


def test_pipeline_only_uses_stage_modules_in_package() -> None:
    for spec in CANONICAL_STAGES:
        assert spec.module.startswith("stages/")
        assert "tools/" not in spec.module
        assert "scripts/" not in spec.module
        assert not spec.module.endswith("docx.lua")


def test_pipeline_does_not_add_lua_filter_to_pandoc(tmp_path: Path) -> None:
    command = build_pandoc_command(
        "pandoc",
        markdown=tmp_path / "document.md",
        output=tmp_path / "out.docx",
        reference_docx=tmp_path / "reference.docx",
    )
    lowered = [part.lower() for part in command]
    assert not any(part.startswith("--lua-filter") for part in lowered)
    assert not any(part.endswith("docx.lua") for part in lowered)
    assert not any(part.endswith(".sh") for part in lowered)


def test_adeu_options_maps_flags() -> None:
    default = _adeu_options(BuildOptions())
    assert (default.bookmarks, default.manifest, default.source_scan) == (True, True, True)

    no_manifest = _adeu_options(BuildOptions(manifest=False))
    assert (no_manifest.bookmarks, no_manifest.manifest, no_manifest.source_scan) == (
        True,
        False,
        False,
    )

    no_adeu = _adeu_options(BuildOptions(adeu=False, manifest=True))
    assert (no_adeu.bookmarks, no_adeu.manifest, no_adeu.source_scan) == (
        False,
        False,
        False,
    )


def test_build_options_rejects_unknown_target() -> None:
    with pytest.raises(ValueError, match="target tidak dikenal: 'rtf'"):
        BuildOptions(target="rtf")  # type: ignore[arg-type]


def test_output_directory_example_and_user(tmp_path: Path) -> None:
    example = tmp_path / "examples" / "assignment-single" / "document.md"
    assert output_directory(example) == example.parent / "out"

    user = tmp_path / "proyek" / "document.md"
    assert output_directory(user) == user.parent


def test_workspace_cleanup_and_keep(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / ".laporan-build", keep=False)
    workspace.ensure()
    (workspace.root / "intermediate.docx").write_bytes(b"x")
    workspace.cleanup()
    assert not workspace.root.exists()

    kept = Workspace(root=tmp_path / ".laporan-build", keep=True)
    kept.ensure()
    (kept.root / "intermediate.docx").write_bytes(b"x")
    kept.cleanup()
    assert (kept.root / "intermediate.docx").is_file()


def test_artifact_store_rejects_key_without_stage_prefix() -> None:
    artifacts = ArtifactStore()
    artifacts.put("mermaid.markdown", Path("mermaid.md"))
    assert artifacts.require("mermaid.markdown") == Path("mermaid.md")
    with pytest.raises(OutputError):
        artifacts.put("sembarang", Path("x"))


def test_pipeline_rejects_incomplete_stage_class() -> None:
    pipeline = Pipeline()
    with pytest.raises(StageOrderError):
        Pipeline(stages=[type(stage) for stage in pipeline.stages[:-1]])
