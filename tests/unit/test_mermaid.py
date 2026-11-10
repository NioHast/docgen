"""Tes unit stage Mermaid: ekstraksi, hash cache, render, dan penggantian."""

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from docgen.errors import DocgenError, ToolMissingError
from docgen.pipeline import ArtifactStore, Workspace
from docgen.stages.mermaid import (
    MermaidError,
    MermaidStage,
    RenderOptions,
    extract_blocks,
    find_mmdc,
    render_blocks,
    render_hash,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

FAKE_MMDC = """\

import base64
import json
import os
import pathlib
import sys

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

arguments = sys.argv[1:]
log = os.environ.get("FAKE_MMDC_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(arguments) + "\\n")


def option(flag: str) -> str | None:
    try:
        return arguments[arguments.index(flag) + 1]
    except (ValueError, IndexError):
        return None


source = option("-i")
target = option("-o")
if source is None or target is None:
    print("fake mmdc: butuh -i dan -o", file=sys.stderr)
    raise SystemExit(2)

# Baca sumber agar fake juga gagal bila berkas input tidak dibuat.
pathlib.Path(source).read_text(encoding="utf-8")

output = pathlib.Path(target)
if output.parent.name != "gambar" or not output.name.startswith("mermaid-"):
    print(f"fake mmdc: path output tidak sesuai: {output}", file=sys.stderr)
    raise SystemExit(4)

if os.environ.get("FAKE_MMDC_FAIL"):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"partial")
    print("fake mmdc gagal disengaja", file=sys.stderr)
    raise SystemExit(3)

output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(PNG)
"""


def mermaid_fence(caption: str, code: str, *, newline: str = "\n") -> str:
    text = f'```{{.mermaid caption="{caption}"}}\n{code.rstrip()}\n```\n'
    return text.replace("\n", newline)


def make_fake_mmdc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Buat skrip mmdc palsu yang mencatat setiap pemanggilan."""

    log = tmp_path / "mmdc-invocations.log"
    monkeypatch.setenv("FAKE_MMDC_LOG", str(log))
    script = tmp_path / "fake_mmdc.py"
    script.write_text(FAKE_MMDC, encoding="utf-8", newline="\n")
    return script, log


def read_calls(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def assert_option(arguments: list[str], flag: str, value: str) -> None:
    assert flag in arguments
    assert arguments[arguments.index(flag) + 1] == value


def test_extract_blok_mermaid() -> None:
    source = (
        "# BAB I\n"
        "\n" + mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B") + "\nSetelah diagram.\n"
    )

    blocks = extract_blocks(source, path="bab1.md")

    assert len(blocks) == 1
    block = blocks[0]
    assert block.caption == "Diagram pipeline"
    assert block.code == "flowchart TD\n  A --> B"
    assert block.content == block.code
    assert block.line == 3
    assert block.start == 2
    assert block.end == 6
    assert block.indent == ""


def test_extract_mengabaikan_fence_biasa() -> None:
    source = "```python\nprint('```{.mermaid caption=\"palsu\"}')\n```\n\n" + mermaid_fence(
        "Diagram asli", "graph TD\n  A --> B"
    )

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].caption == "Diagram asli"


@pytest.mark.parametrize(
    "opener",
    [
        '```{.mermaid caption="Diagram"}',
        '```.mermaid caption="Diagram"',
        '```mermaid caption="Diagram"',
        '```{mermaid caption="Diagram"}',
        '~~~mermaid caption="Diagram"',
    ],
)
def test_extract_varian_info_string(opener: str) -> None:
    fence = "~~~" if opener.startswith("~~~") else "```"
    source = f"{opener}\nflowchart TD\n  A --> B\n{fence}\n"

    blocks = extract_blocks(source)

    assert len(blocks) == 1
    assert blocks[0].caption == "Diagram"


def test_extract_caption_tidak_ada_ditolak() -> None:
    source = "```{.mermaid}\nflowchart TD\n  A --> B\n```\n"

    with pytest.raises(MermaidError) as error:
        extract_blocks(source, path="bab1.md")

    message = str(error.value)
    assert isinstance(error.value, DocgenError)
    assert "bab1.md:1" in message
    assert "caption" in message


def test_extract_caption_kosong_ditolak() -> None:
    source = '```{.mermaid caption=""}\nflowchart TD\n  A --> B\n```\n'

    with pytest.raises(MermaidError, match="caption"):
        extract_blocks(source)


def test_extract_isi_kosong_ditolak() -> None:
    source = '```{.mermaid caption="Diagram"}\n\n```\n'

    with pytest.raises(MermaidError, match="kosong"):
        extract_blocks(source)


def test_extract_fence_mermaid_tidak_ditutup_ditolak() -> None:
    source = '```{.mermaid caption="Diagram"}\nflowchart TD\n  A --> B\n'

    with pytest.raises(MermaidError, match="tidak ditutup"):
        extract_blocks(source)


def test_extract_fence_biasa_tidak_ditutup_diabaikan() -> None:
    source = "```python\nprint('x')\n"

    assert extract_blocks(source) == []


def test_hash_idempoten_dan_bergantung_isi_dan_opsi() -> None:
    code = "flowchart TD\n  A --> B"

    assert render_hash(code) == render_hash(code)
    assert render_hash(code) == render_hash("flowchart TD\r\n  A --> B\r\n")
    assert len(render_hash(code)) == 12
    assert render_hash(code) != render_hash(code + "\n  B --> C")
    assert render_hash(code) != render_hash(code, RenderOptions(theme="dark"))
    assert render_hash(code, {"theme": "dark"}) == render_hash(code, RenderOptions(theme="dark"))
    assert render_hash(code, {"scale": 1}) == render_hash(code, RenderOptions(scale=1.0))


def test_render_blocks_mengganti_blok_dan_menulis_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = (
        "# BAB I\n"
        "\n"
        + mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B")
        + "\n"
        + mermaid_fence("Diagram kedua", "sequenceDiagram\n  A->>B: Halo")
        + "\nSelesai.\n"
    )

    result = render_blocks(source, base, mmdc=fake_mmdc)

    images = sorted((base / "gambar").glob("mermaid-*.png"))
    assert len(images) == 2
    assert all(image.read_bytes() == PNG_1X1 for image in images)
    assert len(read_calls(log)) == 2
    assert "```{.mermaid" not in result
    assert result.count("![") == 2
    assert "Gambar 1.1" not in result
    for image in images:
        assert f"](gambar/{image.name})" in result
    assert result.startswith("# BAB I\n\n")
    assert result.endswith("Selesai.\n")


def test_render_blocks_cache_tidak_memanggil_mmdc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B")

    first = render_blocks(source, base, mmdc=fake_mmdc)
    calls = read_calls(log)
    assert len(calls) == 1

    # Cache harus dipakai tanpa mencari mmdc sama sekali.
    second = render_blocks(source, base, mmdc=tmp_path / "tidak-ada-mmdc.exe")

    assert second == first
    assert read_calls(log) == calls
    assert len(list((base / "gambar").glob("mermaid-*.png"))) == 1


def test_render_blocks_diagram_sama_dirender_sekali(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)
    block = mermaid_fence("Diagram sama", "flowchart LR\n  A --> B")
    source = block + "\n" + block

    result = render_blocks(source, base, mmdc=fake_mmdc)

    assert len(read_calls(log)) == 1
    assert len(list((base / "gambar").glob("mermaid-*.png"))) == 1
    assert result.count("](gambar/mermaid-") == 2


def test_render_blocks_tanpa_blok_tidak_membuat_folder(
    tmp_path: Path,
) -> None:
    base = tmp_path / "tugas"
    source = "# BAB I\n\nTidak ada diagram.\n"

    result = render_blocks(source, base, mmdc=tmp_path / "tidak-ada-mmdc.exe")

    assert result == source
    assert not base.exists()


def _mermaid_context(tmp_path: Path, body: str) -> SimpleNamespace:
    return SimpleNamespace(
        document=SimpleNamespace(body=body, path=Path("document.md")),
        workspace=Workspace(root=tmp_path / ".laporan-build", keep=True),
        artifacts=ArtifactStore(),
    )


def test_stage_tanpa_blok_tetap_menulis_mermaid_md_dan_artifact(tmp_path: Path) -> None:
    body = "# BAB I\n\nTidak ada diagram.\n"
    ctx = _mermaid_context(tmp_path, body)

    first = MermaidStage().run(ctx)

    output = ctx.workspace.path("mermaid.md")
    assert first.status == "ok"
    assert first.changed is True
    assert first.metrics["blocks"] == 0
    assert first.artifacts == (output,)
    assert output.read_text(encoding="utf-8") == body
    assert ctx.artifacts.get("mermaid.markdown") == output

    second = MermaidStage().run(ctx)

    assert second.status == "ok"
    assert second.changed is False
    assert second.metrics["blocks"] == 0
    assert ctx.artifacts.get("mermaid.markdown") == output


def test_render_blocks_mmdc_hilang_melempar_tool_missing(
    tmp_path: Path,
) -> None:
    base = tmp_path / "tugas"
    source = mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B")

    with pytest.raises(ToolMissingError) as error:
        render_blocks(source, base, mmdc=tmp_path / "tidak-ada-mmdc.exe")

    message = str(error.value)
    assert isinstance(error.value, DocgenError)
    assert error.value.tool == "mmdc"
    assert error.value.exit_code == 1
    assert "mmdc tidak ditemukan" in message
    assert "npm install -g @mermaid-js/mermaid-cli" in message
    assert not (base / "gambar").exists()


def test_caption_hilang_tidak_merender_apa_pun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = "```{.mermaid}\nflowchart TD\n  A --> B\n```\n"

    with pytest.raises(MermaidError, match="caption"):
        render_blocks(source, base, mmdc=fake_mmdc)

    assert not log.exists()
    assert not (base / "gambar").exists()


def test_render_blocks_meneruskan_opsi_dan_mengubah_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)
    source = mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B")
    options = RenderOptions(theme="dark", background="white", size=800, scale=2.0)

    result = render_blocks(source, base, mmdc=fake_mmdc, options=options)

    calls = read_calls(log)
    assert len(calls) == 1
    assert_option(calls[0], "--theme", "dark")
    assert_option(calls[0], "--backgroundColor", "white")
    assert_option(calls[0], "--size", "800")
    assert_option(calls[0], "--scale", "2.0")
    first_images = list((base / "gambar").glob("mermaid-*.png"))
    assert len(first_images) == 1
    assert first_images[0].name in result

    # Opsi berbeda harus menghasilkan hash dan PNG berbeda.
    other = render_blocks(source, base, mmdc=fake_mmdc)
    other_images = list((base / "gambar").glob("mermaid-*.png"))
    assert len(other_images) == 2
    assert len(read_calls(log)) == 2
    assert other != result


def test_render_gagal_membersihkan_png_parsial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, log = make_fake_mmdc(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_MMDC_FAIL", "1")
    source = mermaid_fence("Diagram pipeline", "flowchart TD\n  A --> B")

    with pytest.raises(MermaidError, match="mmdc gagal"):
        render_blocks(source, base, mmdc=fake_mmdc)

    assert len(read_calls(log)) == 1
    assert list((base / "gambar").glob("mermaid-*.png")) == []


def test_render_blocks_meneruskan_path_ke_pesan_error(tmp_path: Path) -> None:
    source = "```{.mermaid}\nflowchart TD\n  A --> B\n```\n"

    with pytest.raises(MermaidError) as error:
        render_blocks(source, tmp_path / "tugas", path="bab1.md")

    assert "bab1.md:1" in str(error.value)


def test_line_ending_crlf_dipertahankan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, _log = make_fake_mmdc(tmp_path, monkeypatch)
    source = (
        "# BAB I\r\n"
        "\r\n"
        + mermaid_fence(
            "Diagram pipeline",
            "flowchart TD\n  A --> B",
            newline="\r\n",
        )
        + "\r\nSesudah.\r\n"
    )

    result = render_blocks(source, base, mmdc=fake_mmdc)

    assert "](gambar/mermaid-" in result
    assert "\n" not in result.replace("\r\n", "")


def test_tanpa_newline_akhir_tetap_tanpa_newline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, _log = make_fake_mmdc(tmp_path, monkeypatch)
    source = '```{.mermaid caption="Diagram pipeline"}\nflowchart TD\n  A --> B\n```'

    result = render_blocks(source, base, mmdc=fake_mmdc)

    assert result.startswith("![Diagram pipeline](gambar/mermaid-")
    assert not result.endswith("\n")


def test_indentasi_fence_dipertahankan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, _log = make_fake_mmdc(tmp_path, monkeypatch)
    source = '  ```{.mermaid caption="Diagram"}\n  flowchart TD\n    A --> B\n  ```\n'

    result = render_blocks(source, base, mmdc=fake_mmdc)

    assert result.startswith("  ![Diagram](gambar/mermaid-")


def test_caption_dengan_kurung_siku_di_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "tugas"
    fake_mmdc, _log = make_fake_mmdc(tmp_path, monkeypatch)
    source = mermaid_fence("Diagram [utama]", "flowchart TD\n  A --> B")

    result = render_blocks(source, base, mmdc=fake_mmdc)

    assert result.startswith("![Diagram [utama\\]](gambar/mermaid-")


def test_find_mmdc_eksplisit_dan_tidak_ada(tmp_path: Path) -> None:
    script = tmp_path / "mmdc.py"
    script.write_text("", encoding="utf-8")

    assert find_mmdc(script) == str(script)
    assert find_mmdc(tmp_path / "tidak-ada-mmdc") is None
