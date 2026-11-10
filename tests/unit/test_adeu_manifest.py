"""Tes schema, model, dan determinisme manifest Adeu."""

import json
from pathlib import Path

import pytest

from docgen.adeu.manifest import (
    DEFAULT_MANIFEST_DIR,
    DEFAULT_MANIFEST_NAME,
    MANIFEST_VERSION,
    Manifest,
    ManifestParagraph,
    default_manifest_path,
    dump_manifest,
    load_manifest,
    make_paragraph,
    manifest_from_dict,
    manifest_to_dict,
    sha256_text,
    validate_manifest,
)
from docgen.errors import ManifestError


def _paragraph(
    paragraph_id: str = "p0001",
    *,
    index: int = 0,
    text: str = "Paragraf contoh.",
    kind: str = "body",
    heading_path: tuple[str, ...] = ("BAB I PENDAHULUAN",),
    protected: bool = False,
    protected_reason: str | None = None,
    source_file: str | None = None,
    source_line: int | None = None,
) -> ManifestParagraph:
    return make_paragraph(
        id=paragraph_id,
        index=index,
        kind=kind,
        heading_path=heading_path,
        text=text,
        protected=protected,
        protected_reason=protected_reason,
        source_file=source_file,
        source_line=source_line,
    )


def _manifest(*paragraphs: ManifestParagraph, docx: str = "Tugas.docx") -> Manifest:
    items = paragraphs or (_paragraph(),)
    include_source = any(
        paragraph.source_file is not None or paragraph.source_line is not None
        for paragraph in items
    )
    return Manifest(
        version=MANIFEST_VERSION,
        docx=docx,
        paragraphs=items,
        include_source=include_source,
    )


def _raw(manifest: Manifest) -> dict[str, object]:
    return json.loads(json.dumps(manifest_to_dict(manifest)))


def test_default_manifest_path_is_next_to_document() -> None:
    assert default_manifest_path("proyek/document.md") == (
        Path("proyek") / DEFAULT_MANIFEST_DIR / DEFAULT_MANIFEST_NAME
    )
    assert (
        default_manifest_path(Path("proyek") / "document.md")
        .as_posix()
        .endswith(".laporan/manifest.json")
    )


def test_dump_and_load_are_deterministic(tmp_path: Path) -> None:
    manifest = _manifest(
        _paragraph(
            "p0001",
            index=0,
            kind="heading",
            heading_path=("BAB I PENDAHULUAN",),
            text="BAB I PENDAHULUAN",
        ),
        _paragraph(
            "p0002",
            index=1,
            text="Paragraf contoh.",
            source_file="document.md",
            source_line=7,
        ),
        _paragraph(
            "p0003",
            index=2,
            kind="caption",
            text="Tabel 1. Contoh.",
            protected=True,
            protected_reason="caption_style",
        ),
    )

    first = tmp_path / "satu" / "manifest.json"
    second = tmp_path / "dua" / "manifest.json"
    dump_manifest(manifest, first)
    dump_manifest(manifest, second)

    assert first.read_bytes() == second.read_bytes()
    assert load_manifest(first) == manifest
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert "built_at" not in payload
    assert payload["version"] == MANIFEST_VERSION
    assert set(payload["paragraphs"][0]) == {
        "id",
        "index",
        "kind",
        "heading_path",
        "text",
        "text_sha256",
        "protected",
        "protected_reason",
        "source_file",
        "source_line",
    }


def test_legacy_built_at_is_accepted_but_not_written(tmp_path: Path) -> None:
    raw = _raw(_manifest())
    raw["built_at"] = "2026-11-06T00:00:00+00:00"
    manifest = manifest_from_dict(raw)

    destination = tmp_path / "manifest.json"
    dump_manifest(manifest, destination)
    assert "built_at" not in destination.read_text(encoding="utf-8")


def test_unknown_keys_are_rejected() -> None:
    raw = _raw(_manifest())
    raw["tambahan"] = True
    with pytest.raises(ManifestError) as excinfo:
        manifest_from_dict(raw)
    assert excinfo.value.code == "MANIFEST-SCHEMA"

    raw = _raw(_manifest())
    raw["paragraphs"][0]["rahasia"] = "x"
    with pytest.raises(ManifestError):
        manifest_from_dict(raw)


def test_duplicate_id_and_index_are_rejected() -> None:
    raw = _raw(
        _manifest(
            _paragraph("p0001", index=0),
            _paragraph("p0001", index=1),
        )
    )
    with pytest.raises(ManifestError) as excinfo:
        manifest_from_dict(raw)
    assert excinfo.value.code == "MANIFEST-DUPLICATE"

    raw = _raw(
        _manifest(
            _paragraph("p0001", index=0),
            _paragraph("p0002", index=0),
        )
    )
    with pytest.raises(ManifestError) as excinfo:
        manifest_from_dict(raw)
    assert excinfo.value.code == "MANIFEST-DUPLICATE"


def test_text_sha256_is_verified() -> None:
    raw = _raw(_manifest())
    raw["paragraphs"][0]["text"] = "Teks sudah diubah di luar alat."
    with pytest.raises(ManifestError) as excinfo:
        manifest_from_dict(raw)
    assert excinfo.value.code == "MANIFEST-HASH"

    raw = _raw(_manifest())
    raw["paragraphs"][0]["text_sha256"] = "0" * 64
    with pytest.raises(ManifestError):
        manifest_from_dict(raw)


def test_missing_text_sha256_is_rejected() -> None:
    raw = _raw(_manifest())
    del raw["paragraphs"][0]["text_sha256"]
    with pytest.raises(ManifestError):
        manifest_from_dict(raw)


def test_protected_fields_must_be_consistent() -> None:
    raw = _raw(_manifest())
    raw["paragraphs"][0]["protected"] = True
    raw["paragraphs"][0]["protected_reason"] = None
    with pytest.raises(ManifestError) as excinfo:
        manifest_from_dict(raw)
    assert excinfo.value.code == "MANIFEST-PROTECTED"

    raw = _raw(_manifest())
    raw["paragraphs"][0]["protected"] = False
    raw["paragraphs"][0]["protected_reason"] = "caption_style"
    with pytest.raises(ManifestError) as excinfo:
        manifest_from_dict(raw)
    assert excinfo.value.code == "MANIFEST-PROTECTED"


def test_source_file_and_line_must_be_paired() -> None:
    raw = _raw(_manifest())
    raw["paragraphs"][0]["source_file"] = "document.md"
    raw["paragraphs"][0]["source_line"] = None
    with pytest.raises(ManifestError) as excinfo:
        manifest_from_dict(raw)
    assert excinfo.value.code == "MANIFEST-SOURCE"


def test_docx_name_must_be_a_basename() -> None:
    raw = _raw(_manifest(docx="folder/Tugas.docx"))
    with pytest.raises(ManifestError) as excinfo:
        manifest_from_dict(raw)
    assert excinfo.value.code == "MANIFEST-DOCX"


def test_unsupported_version_is_rejected() -> None:
    raw = _raw(_manifest())
    raw["version"] = 2
    with pytest.raises(ManifestError) as excinfo:
        manifest_from_dict(raw)
    assert excinfo.value.code == "MANIFEST-VERSION"


def test_manifest_roundtrip_preserves_hash_and_order() -> None:
    manifest = _manifest(
        _paragraph("p0002", index=1, text="Kedua"),
        _paragraph("p0001", index=0, text="Pertama"),
    )
    loaded = manifest_from_dict(_raw(manifest))
    assert [paragraph.id for paragraph in loaded.paragraphs] == ["p0001", "p0002"]
    assert loaded.paragraphs[0].text_sha256 == sha256_text("Pertama")
    validate_manifest(loaded)


def test_load_missing_manifest_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestError) as excinfo:
        load_manifest(tmp_path / "tidak-ada.json")
    assert excinfo.value.code == "MANIFEST-MISSING"
