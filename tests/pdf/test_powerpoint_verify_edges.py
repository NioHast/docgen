"""Tes cabang edge verifikasi font hasil PowerPoint COM memakai fake."""

import io
import zipfile
from pathlib import Path

import pytest
from test_powerpoint import (
    EMBEDDED_PPTX_BYTES,
    PPTX_BYTES,
    _minimal_pptx,
    _without_entry,
    install,
    make_environment,
)

from autooffice.pdf import powerpoint
from autooffice.pdf.com import WordComError


def _package(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _replace_entry(data: bytes, name: str, replacement: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, payload in entries:
            archive.writestr(info, replacement if info.filename == name else payload)
    return buffer.getvalue()


def _embed_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: bytes,
    match: str,
) -> None:
    pptx = tmp_path / "Deck.pptx"
    pptx.write_bytes(PPTX_BYTES)
    environment = make_environment(embedded_bytes=payload)
    install(monkeypatch, environment)

    with pytest.raises(WordComError, match=match):
        powerpoint.embed_fonts(pptx, timeout_s=5.0)

    assert pptx.read_bytes() == PPTX_BYTES


def test_embed_fonts_rejects_empty_font_part(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _replace_entry(
        EMBEDDED_PPTX_BYTES,
        "ppt/fonts/font1.fntdata",
        b"",
    )

    _embed_fails(monkeypatch, tmp_path, payload, "part font kosong")


def test_embed_fonts_rejects_package_without_presentation_xml(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _package({"ppt/fonts/font1.fntdata": b"fake-fntdata"})

    _embed_fails(monkeypatch, tmp_path, payload, "tidak memiliki\\s+ppt/presentation.xml")


def test_embed_fonts_rejects_non_zip_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _embed_fails(monkeypatch, tmp_path, b"bukan zip", "bukan arsip PPTX valid")


def test_embed_fonts_rejects_invalid_presentation_xml(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _package(
        {
            "ppt/presentation.xml": b"<bukan xml",
            "ppt/fonts/font1.fntdata": b"fake-fntdata",
        }
    )

    _embed_fails(monkeypatch, tmp_path, payload, "presentation.xml yang tidak valid")


def test_embed_fonts_rejects_wrong_font_family(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        font_family="Arial",
        with_markers=True,
    )

    _embed_fails(monkeypatch, tmp_path, payload, 'typeface="Plus Jakarta Sans"')


def test_embed_fonts_rejects_missing_bold_font(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        roles=("regular",),
        with_markers=True,
    )

    _embed_fails(monkeypatch, tmp_path, payload, "p:bold")


def test_embed_fonts_rejects_timing_injected_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        with_markers=True,
        with_timing=True,
    )

    _embed_fails(monkeypatch, tmp_path, payload, "p:timing")


def test_embed_fonts_rejects_transition_injected_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        with_markers=True,
        with_transition=True,
    )

    _embed_fails(monkeypatch, tmp_path, payload, "p:transition")


def test_embed_fonts_rejects_lost_key_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        with_markers=False,
    )

    _embed_fails(monkeypatch, tmp_path, payload, "metadata key")


def test_embed_fonts_rejects_missing_relationship_part(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _without_entry(
        _minimal_pptx(
            font_part=True,
            embedded_font_list=True,
            with_markers=True,
        ),
        "ppt/_rels/presentation.xml.rels",
    )

    _embed_fails(monkeypatch, tmp_path, payload, "presentation.xml.rels")


def test_embed_fonts_rejects_one_unresolved_font_relationship(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        with_markers=True,
        relationship_ids=("rId900", "rId999"),
    )

    _embed_fails(
        monkeypatch,
        tmp_path,
        payload,
        r"p:bold.*relationship tidak ada",
    )


def test_embed_fonts_rejects_both_unresolved_font_relationships(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        with_markers=True,
        relationship_ids=("rId998", "rId999"),
    )

    _embed_fails(
        monkeypatch,
        tmp_path,
        payload,
        r"p:regular.*relationship tidak ada",
    )


def test_embed_fonts_rejects_regular_and_bold_same_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        with_markers=True,
        font_targets=("fonts/font1.fntdata", "fonts/font1.fntdata"),
    )

    _embed_fails(monkeypatch, tmp_path, payload, "terpisah")


def test_embed_fonts_rejects_non_font_relationship_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        with_markers=True,
        relationship_type=(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
        ),
    )

    _embed_fails(monkeypatch, tmp_path, payload, "bukan font")


def test_embed_fonts_rejects_missing_fntdata_content_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    payload = _minimal_pptx(
        font_part=True,
        embedded_font_list=True,
        with_markers=True,
        write_font_content_type=False,
    )

    _embed_fails(monkeypatch, tmp_path, payload, "content type fntdata")
