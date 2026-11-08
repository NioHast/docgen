"""Tes validator caption Markdown sebelum build DOCX."""

from __future__ import annotations

from pathlib import Path

import check_captions as checker


def write_markdown(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_tabel_tanpa_caption_ditolak(tmp_path):
    path = write_markdown(
        tmp_path,
        "tanpa_caption.md",
        "# BAB I\n\n| Nama | Nilai |\n| --- | --- |\n| Ahmad | 90 |\n",
    )

    issues = checker.check_markdown(path)

    assert len(issues) == 1
    assert issues[0].kind == "tabel"
    assert issues[0].line == 3
    assert ": Judul tabel" in issues[0].message


def test_tabel_dengan_caption_di_atas_dan_bawah_diterima(tmp_path):
    atas = write_markdown(
        tmp_path,
        "atas.md",
        "# BAB I\n\n: Data responden\n\n| Nama | Nilai |\n| --- | --- |\n| Ahmad | 90 |\n",
    )
    bawah = write_markdown(
        tmp_path,
        "bawah.md",
        "# BAB I\n\n| Nama | Nilai |\n| --- | --- |\n| Ahmad | 90 |\n\n: Data responden\n",
    )

    assert checker.check_markdown(atas) == []
    assert checker.check_markdown(bawah) == []


def test_gambar_tanpa_alt_ditolak(tmp_path):
    path = write_markdown(
        tmp_path,
        "gambar_tanpa_alt.md",
        "# BAB I\n\n![](gambar/diagram.png)\n",
    )

    issues = checker.check_markdown(path)

    assert len(issues) == 1
    assert issues[0].kind == "gambar"
    assert issues[0].line == 3
    assert "alt text" in issues[0].message


def test_gambar_dengan_alt_diterima(tmp_path):
    path = write_markdown(
        tmp_path,
        "gambar_beralt.md",
        "# BAB I\n\n![Diagram alur](gambar/diagram.png)\n",
    )

    assert checker.check_markdown(path) == []


def test_contoh_di_dalam_code_span_dan_code_fence_diabaikan(tmp_path):
    path = write_markdown(
        tmp_path,
        "code.md",
        "# BAB I\n\n"
        "Contoh: `![tanpa alt](x.png)` dan `| a | b |`.\n\n"
        "```markdown\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n\n"
        "![](x.png)\n"
        "```\n",
    )

    assert checker.check_markdown(path) == []


def test_beberapa_temuan_dilaporkan_sekaligus(tmp_path):
    path = write_markdown(
        tmp_path,
        "banyak.md",
        "# BAB I\n\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n\n"
        "![](x.png)\n",
    )

    issues = checker.check_markdown(path)

    assert [issue.kind for issue in issues] == ["tabel", "gambar"]


def test_cli_sukses_dan_gagal(tmp_path, capsys):
    baik = write_markdown(
        tmp_path,
        "baik.md",
        "# BAB I\n\n: Data\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n![Diagram](x.png)\n",
    )
    buruk = write_markdown(
        tmp_path,
        "buruk.md",
        "# BAB I\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n",
    )

    assert checker.main([str(baik)]) == 0
    assert "[OK]" in capsys.readouterr().out

    assert checker.main([str(buruk)]) == 1
    captured = capsys.readouterr()
    assert "[ERROR]" in captured.err
    assert "Build DOCX dihentikan" in captured.err


def test_direktori_diperiksa_rekursif(tmp_path):
    subdir = tmp_path / "chapters"
    subdir.mkdir()
    (subdir / "bab1.md").write_text(
        "# BAB I\n\n![](gambar.png)\n", encoding="utf-8"
    )

    issues = checker.check_markdown(subdir / "bab1.md")
    assert len(issues) == 1

    files = checker.expand_paths([tmp_path])
    assert files == [subdir / "bab1.md"]
