"""Tes renderer Mermaid inline: ekstraksi, hash, penggantian, dan integrasi."""

from __future__ import annotations

import base64
import os
import shutil
import sys
from pathlib import Path

import pytest

from laporan.mermaid import (
    MermaidError,
    RenderOptions,
    extract_blocks,
    main,
    render_hash,
    replace_markdown_blocks,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

FAKE_MMDC = """\
from __future__ import annotations

import base64
import os
import pathlib
import sys

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def option(arguments: list[str], flag: str) -> str | None:
    try:
        return arguments[arguments.index(flag) + 1]
    except (ValueError, IndexError):
        return None


source = option(sys.argv[1:], "-i")
target = option(sys.argv[1:], "-o")
if source is None or target is None:
    print("fake mmdc: butuh -i dan -o", file=sys.stderr)
    raise SystemExit(2)

# Baca sumber agar fake juga gagal bila berkas input tidak dibuat.
pathlib.Path(source).read_text(encoding="utf-8")
log = os.environ.get("FAKE_MMDC_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("render\\n")

output = pathlib.Path(target)
if output.parent.name != "gambar" or not output.name.startswith("mermaid-"):
    print(f"fake mmdc: path output tidak sesuai: {output}", file=sys.stderr)
    raise SystemExit(3)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(PNG)
"""


def mermaid_fence(caption: str, code: str) -> str:
    return (
        f'```{{.mermaid caption="{caption}"}}\n'
        f"{code.rstrip()}\n"
        "```\n"
    )


def make_fake_mmdc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Buat executable mmdc palsu yang mencatat setiap pemanggilan."""

    log = tmp_path / "mmdc-invocations.log"
    monkeypatch.setenv("FAKE_MMDC_LOG", str(log))

    if os.name == "nt":
        script = tmp_path / "fake_mmdc.py"
        script.write_text(FAKE_MMDC, encoding="utf-8", newline="\n")
        wrapper = tmp_path / "mmdc.cmd"
        wrapper.write_bytes(
            (
                "@echo off\r\n"
                f'"{sys.executable}" "{script}" %*\r\n'
            ).encode("utf-8")
        )
        return wrapper, log

    wrapper = tmp_path / "mmdc"
    wrapper.write_text(
        f"#!{sys.executable}\n{FAKE_MMDC}", encoding="utf-8", newline="\n"
    )
    wrapper.chmod(0o755)
    return wrapper, log


def test_extract_blok_mermaid():
    source = (
        "# BAB I\n"
        "\n"
        + mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B")
        + "\nSetelah diagram.\n"
    )

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].caption == "Diagram pipeline"
    assert blocks[0].code == "flowchart TD\n  A --> B"
    assert blocks[0].content == blocks[0].code
    assert blocks[0].line == 3


def test_extract_mengabaikan_fence_biasa():
    source = (
        "```python\n"
        'print(\'```{.mermaid caption="palsu"}\')\n'
        "```\n"
        "\n"
        + mermaid_fence("Diagram asli", "graph TD\n  A --> B")
    )

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].caption == "Diagram asli"


def test_caption_wajib():
    source = "```{.mermaid}\nflowchart TD\n  A --> B\n```\n"

    with pytest.raises(MermaidError) as error:
        extract_blocks(source, path="bab1.md")

    message = str(error.value)
    assert "bab1.md:1" in message
    assert "caption" in message


def test_caption_kosong_ditolak():
    source = '```{.mermaid caption=""}\nflowchart TD\n  A --> B\n```\n'

    with pytest.raises(MermaidError, match="caption"):
        extract_blocks(source)


def test_blok_mermaid_tidak_ditutup_ditolak():
    source = "```{.mermaid caption=\"Diagram\"}\nflowchart TD\n  A --> B\n"

    with pytest.raises(MermaidError, match="tidak ditutup"):
        extract_blocks(source)


def test_hash_idempoten_dan_bergantung_isi_dan_opsi():
    code = "flowchart TD\n  A --> B"

    assert render_hash(code) == render_hash(code)
    assert render_hash(code) == render_hash("flowchart TD\r\n  A --> B\r\n")
    assert len(render_hash(code)) == 12
    assert render_hash(code) != render_hash(code + "\n  B --> C")
    assert render_hash(code) != render_hash(code, RenderOptions(theme="dark"))
    assert render_hash(code, {"theme": "dark"}) == render_hash(
        code, RenderOptions(theme="dark")
    )
    assert render_hash(code, {"scale": 1}) == render_hash(
        code, RenderOptions(scale=1.0)
    )


def test_penggantian_markdown_tanpa_nomor_manual(tmp_path):
    source = (
        "Sebelum.\n"
        "\n"
        + mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B")
        + "\nSesudah.\n"
    )
    digest = render_hash("flowchart TD\n  A --> B")

    result = replace_markdown_blocks(source, tmp_path)

    expected = (
        "Sebelum.\n"
        "\n"
        f"![Diagram pipeline](gambar/mermaid-{digest}.png)\n"
        "\nSesudah.\n"
    )
    assert result == expected
    assert "Gambar 1.1" not in result
    assert not (tmp_path / "gambar").exists()


def test_tanpa_newline_akhir_tetap_tanpa_newline(tmp_path):
    source = (
        '```{.mermaid caption="Diagram pipeline"}\n'
        "flowchart TD\n"
        "  A --> B\n"
        "```"
    )

    result = replace_markdown_blocks(source, tmp_path)

    assert result.startswith("![Diagram pipeline](gambar/mermaid-")
    assert not result.endswith("\n")


def test_integrasi_dua_diagram(tmp_path, monkeypatch):
    task = tmp_path / "tugas"
    chapters = task / "chapters"
    chapters.mkdir(parents=True)
    source = chapters / "bab1.md"
    source.write_text(
        "# BAB I\n"
        "\n"
        + mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B")
        + "\n"
        + mermaid_fence("Diagram kedua", "sequenceDiagram\n  A->>B: Halo")
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    bibliography = task / "references.bib"
    bibliography.write_text("@book{kunci, title={Tetap}}\n", encoding="utf-8")
    other_image = task / "gambar" / "lain.png"
    other_image.parent.mkdir(parents=True)
    other_image.write_bytes(b"gambar lain")

    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)

    assert (
        main(
            [
                "--src",
                str(chapters),
                "--out-dir",
                str(task),
                "--mmdc",
                str(fake_mmdc),
            ]
        )
        == 0
    )

    images = sorted((task / "gambar").glob("mermaid-*.png"))
    assert len(images) == 2
    assert log.read_text(encoding="utf-8").splitlines() == ["render", "render"]

    text = source.read_text(encoding="utf-8")
    assert "```{.mermaid" not in text
    assert text.count("![") == 2
    for image in images:
        relative = image.relative_to(task).as_posix()
        assert f"]({relative})" in text
        assert image.read_bytes() == PNG_1X1

    assert bibliography.read_text(encoding="utf-8") == (
        "@book{kunci, title={Tetap}}\n"
    )
    assert other_image.read_bytes() == b"gambar lain"

    # Jalankan ulang: tidak ada render baru dan Markdown tidak berubah.
    first_text = source.read_text(encoding="utf-8")
    assert (
        main(
            [
                "--src",
                str(chapters),
                "--out-dir",
                str(task),
                "--mmdc",
                str(fake_mmdc),
            ]
        )
        == 0
    )
    assert source.read_text(encoding="utf-8") == first_text
    assert log.read_text(encoding="utf-8").splitlines() == ["render", "render"]


def test_png_cache_tetap_mengganti_blok(tmp_path, monkeypatch):
    task = tmp_path / "tugas"
    task.mkdir()
    code = "flowchart TD\n  A --> B"
    source = tmp_path / "bab1.md"
    source.write_text(
        mermaid_fence("Diagram pipeline", code), encoding="utf-8", newline="\n"
    )
    digest = render_hash(code)
    cached = task / "gambar" / f"mermaid-{digest}.png"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(PNG_1X1)

    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)

    assert (
        main(
            [
                "--src",
                str(source),
                "--out-dir",
                str(task),
                "--mmdc",
                str(fake_mmdc),
            ]
        )
        == 0
    )

    assert not log.exists()
    assert cached.read_bytes() == PNG_1X1
    assert f"![Diagram pipeline](gambar/mermaid-{digest}.png)" in (
        source.read_text(encoding="utf-8")
    )


def test_diagram_sama_dirender_sekali(tmp_path, monkeypatch):
    task = tmp_path / "tugas"
    task.mkdir()
    source = tmp_path / "bab1.md"
    block = mermaid_fence("Diagram sama", "flowchart LR\n  A --> B")
    source.write_text(block + "\n" + block, encoding="utf-8", newline="\n")

    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)

    assert (
        main(
            [
                "--src",
                str(source),
                "--out-dir",
                str(task),
                "--mmdc",
                str(fake_mmdc),
            ]
        )
        == 0
    )

    assert len(list((task / "gambar").glob("mermaid-*.png"))) == 1
    assert log.read_text(encoding="utf-8").splitlines() == ["render"]
    text = source.read_text(encoding="utf-8")
    assert text.count("](gambar/mermaid-") == 2


def test_mmdc_tidak_ada_exit_1(tmp_path, capsys):
    task = tmp_path / "tugas"
    task.mkdir()
    source = tmp_path / "bab1.md"
    original = mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B")
    source.write_text(original, encoding="utf-8", newline="\n")

    code = main(
        [
            "--src",
            str(source),
            "--out-dir",
            str(task),
            "--mmdc",
            str(tmp_path / "tidak-ada-mmdc.exe"),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "mmdc tidak ditemukan" in captured.err
    assert "npm install -g @mermaid-js/mermaid-cli" in captured.err
    assert source.read_text(encoding="utf-8") == original
    assert not (task / "gambar").exists()


def test_caption_hilang_lewat_cli_tidak_menulis(tmp_path, monkeypatch, capsys):
    task = tmp_path / "tugas"
    task.mkdir()
    source = tmp_path / "bab1.md"
    original = "```{.mermaid}\nflowchart TD\n  A --> B\n```\n"
    source.write_text(original, encoding="utf-8", newline="\n")
    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)

    code = main(
        [
            "--src",
            str(source),
            "--out-dir",
            str(task),
            "--mmdc",
            str(fake_mmdc),
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "caption" in captured.err
    assert source.read_text(encoding="utf-8") == original
    assert not log.exists()
    assert not (task / "gambar").exists()


def test_hanya_berkas_md_yang_disentuh(tmp_path, monkeypatch):
    source_dir = tmp_path / "sumber"
    source_dir.mkdir()
    markdown = source_dir / "bab1.md"
    markdown.write_text(
        mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B"),
        encoding="utf-8",
        newline="\n",
    )
    bibliography = source_dir / "references.bib"
    bibliography.write_text("@book{kunci}\n", encoding="utf-8")
    notes = source_dir / "catatan.txt"
    notes.write_text(
        '```{.mermaid caption="Bukan Markdown"}\nflowchart TD\n```\n',
        encoding="utf-8",
    )
    task = tmp_path / "tugas"
    task.mkdir()
    fake_mmdc, _log = make_fake_mmdc(tmp_path, monkeypatch)

    assert (
        main(
            [
                "--src",
                str(source_dir),
                "--out-dir",
                str(task),
                "--mmdc",
                str(fake_mmdc),
            ]
        )
        == 0
    )

    assert "@book{kunci}" in bibliography.read_text(encoding="utf-8")
    assert "```{.mermaid" in notes.read_text(encoding="utf-8")
    assert "](gambar/mermaid-" in markdown.read_text(encoding="utf-8")


def test_crlf_dan_bom_dipertahankan(tmp_path, monkeypatch):
    task = tmp_path / "tugas"
    task.mkdir()
    source = tmp_path / "bab1.md"
    text = (
        "# BAB I\r\n"
        "\r\n"
        + mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B").replace(
            "\n", "\r\n"
        )
    )
    source.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    fake_mmdc, _log = make_fake_mmdc(tmp_path, monkeypatch)

    assert (
        main(
            [
                "--src",
                str(source),
                "--out-dir",
                str(task),
                "--mmdc",
                str(fake_mmdc),
            ]
        )
        == 0
    )

    data = source.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert b"![Diagram pipeline](gambar/mermaid-" in data
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")


@pytest.mark.integration
def test_mmdc_asli_merender_png(tmp_path):
    mmdc = shutil.which("mmdc")
    if mmdc is None:
        pytest.skip("mmdc tidak tersedia")

    task = tmp_path / "tugas"
    task.mkdir()
    source = tmp_path / "diagram.md"
    source.write_text(
        mermaid_fence("Diagram mmdc", "flowchart LR\n  A --> B"),
        encoding="utf-8",
        newline="\n",
    )

    assert (
        main(
            [
                "--src",
                str(source),
                "--out-dir",
                str(task),
                "--mmdc",
                mmdc,
            ]
        )
        == 0
    )

    images = list((task / "gambar").glob("mermaid-*.png"))
    assert len(images) == 1
    assert images[0].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    text = source.read_text(encoding="utf-8")
    assert f"![Diagram mmdc](gambar/{images[0].name})" in text
