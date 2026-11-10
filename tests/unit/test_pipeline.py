"""Tes unit orkestrasi pipeline: nama stage, urutan, opsi, dan workspace."""

from pathlib import Path

import pytest

from docgen.errors import OutputError, StageOrderError
from docgen.paths import output_directory
from docgen.pipeline import (
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
from docgen.stages.pandoc import build_pandoc_command


def test_stage_name_memuat_semua_stage_kanonik() -> None:
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


def test_canonical_specs_requires_adalah_prefix() -> None:
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


def test_canonical_orders_unik_dan_naik() -> None:
    orders = [spec.order for spec in CANONICAL_STAGES]
    assert orders == sorted(orders)
    assert len(orders) == len(set(orders))
    by_name = {spec.name: spec.order for spec in CANONICAL_STAGES}
    assert by_name[StageName.FRONT_MATTER] == 35
    assert by_name[StageName.PANDOC] == 40
    assert by_name[StageName.PDF] == 170


def test_validate_stage_order_menolak_urutan_tertukar() -> None:
    specs = list(CANONICAL_STAGES)
    specs[4], specs[5] = specs[5], specs[4]
    with pytest.raises(StageOrderError):
        validate_stage_order(specs)


def test_validate_stage_order_menolak_stage_hilang() -> None:
    with pytest.raises(StageOrderError):
        validate_stage_order(CANONICAL_STAGES[:-1])


def test_validate_stage_order_menolak_requires_bukan_prefix() -> None:
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


def test_pipeline_mendaftarkan_setiap_stage_tepat_sekali() -> None:
    pipeline = Pipeline()
    names = [stage.name for stage in pipeline.stages]
    assert names == list(CANONICAL_ORDER)
    assert len(set(names)) == len(names)
    assert [spec.name for spec in pipeline.specs] == list(CANONICAL_ORDER)


def test_pipeline_hanya_memakai_modul_stage_dalam_paket() -> None:
    for spec in CANONICAL_STAGES:
        assert spec.module.startswith("stages/")
        assert "tools/" not in spec.module
        assert "scripts/" not in spec.module
        assert not spec.module.endswith("docx.lua")


def test_pipeline_tidak_menambahkan_lua_filter_ke_pandoc(tmp_path: Path) -> None:
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


def test_adeu_options_memeta_kan_flag() -> None:
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


def test_build_options_menolak_target_tidak_dikenal() -> None:
    with pytest.raises(ValueError):
        BuildOptions(target="rtf")  # type: ignore[arg-type]


def test_direktori_output_contoh_dan_pengguna(tmp_path: Path) -> None:
    example = tmp_path / "examples" / "assignment-single" / "document.md"
    assert output_directory(example) == example.parent / "out"

    user = tmp_path / "proyek" / "document.md"
    assert output_directory(user) == user.parent


def test_workspace_cleanup_dan_keep(tmp_path: Path) -> None:
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


def test_artifact_store_menolak_key_tanpa_prefix_stage() -> None:
    artifacts = ArtifactStore()
    artifacts.put("mermaid.markdown", Path("mermaid.md"))
    assert artifacts.require("mermaid.markdown") == Path("mermaid.md")
    with pytest.raises(OutputError):
        artifacts.put("sembarang", Path("x"))


def test_pipeline_menolak_kelas_stage_tidak_lengkap() -> None:
    pipeline = Pipeline()
    with pytest.raises(StageOrderError):
        Pipeline(stages=[type(stage) for stage in pipeline.stages[:-1]])
