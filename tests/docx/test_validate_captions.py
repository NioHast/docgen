"""Tes unit stage ``validate``: caption tabel dan alt text gambar."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from autooffice.docx.errors import ValidationError
from autooffice.docx.stages.validate import (
    CaptionIssue,
    ValidateStage,
    check_markdown,
    check_text,
    expand_paths,
    main,
)


def write_markdown(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_table_without_caption_rejected(tmp_path):
    path = write_markdown(
        tmp_path,
        "tanpa_caption.md",
        "# BAB I\n\n| Nama | Nilai |\n| --- | --- |\n| Ahmad | 90 |\n",
    )

    issues = check_markdown(path)

    assert len(issues) == 1
    assert isinstance(issues[0], CaptionIssue)
    assert issues[0].kind == "tabel"
    assert issues[0].line == 3
    assert ": Judul tabel" in issues[0].message


def test_table_with_caption_above_and_below_accepted(tmp_path):
    above = write_markdown(
        tmp_path,
        "atas.md",
        "# BAB I\n\n: Data responden\n\n| Nama | Nilai |\n| --- | --- |\n| Ahmad | 90 |\n",
    )
    below = write_markdown(
        tmp_path,
        "bawah.md",
        "# BAB I\n\n| Nama | Nilai |\n| --- | --- |\n| Ahmad | 90 |\n\n: Data responden\n",
    )

    assert check_markdown(above) == []
    assert check_markdown(below) == []


def test_image_without_alt_rejected(tmp_path):
    path = write_markdown(
        tmp_path,
        "gambar_tanpa_alt.md",
        "# BAB I\n\n![](gambar/diagram.png)\n",
    )

    issues = check_markdown(path)

    assert len(issues) == 1
    assert issues[0].kind == "gambar"
    assert issues[0].line == 3
    assert "alt text" in issues[0].message


def test_image_with_alt_accepted(tmp_path):
    path = write_markdown(
        tmp_path,
        "gambar_beralt.md",
        "# BAB I\n\n![Diagram alur](gambar/diagram.png)\n",
    )

    assert check_markdown(path) == []


def test_reference_image_without_alt_rejected(tmp_path):
    path = write_markdown(
        tmp_path,
        "reference.md",
        "# BAB I\n\n![][gambar]\n\n[gambar]: x.png\n",
    )

    issues = check_markdown(path)

    assert [issue.kind for issue in issues] == ["gambar"]


def test_example_inside_code_span_and_code_fence_ignored(tmp_path):
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

    assert check_markdown(path) == []


def test_html_code_and_pre_ignored(tmp_path):
    inline = write_markdown(
        tmp_path,
        "html_inline.md",
        "# BAB I\n\n<code>![](x.png)</code> dan <code>| A | B |</code>\n",
    )
    block = write_markdown(
        tmp_path,
        "html_block.md",
        "# BAB I\n\n<pre>\n| A | B |\n| --- | --- |\n| 1 | 2 |\n![](x.png)\n</pre>\n",
    )

    assert check_markdown(inline) == []
    assert check_markdown(block) == []


def test_multiple_findings_reported_at_once(tmp_path):
    path = write_markdown(
        tmp_path,
        "banyak.md",
        "# BAB I\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n![](x.png)\n",
    )

    issues = check_markdown(path)

    assert [issue.kind for issue in issues] == ["tabel", "gambar"]


def test_cli_success_and_failure(tmp_path, capsys):
    good = write_markdown(
        tmp_path,
        "baik.md",
        "# BAB I\n\n: Data\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n![Diagram](x.png)\n",
    )
    bad = write_markdown(
        tmp_path,
        "buruk.md",
        "# BAB I\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n",
    )

    assert main([str(good)]) == 0
    assert "[OK]" in capsys.readouterr().out

    assert main([str(bad)]) == 1
    captured = capsys.readouterr()
    assert "[ERROR]" in captured.err
    assert "Build DOCX dihentikan" in captured.err


def test_directory_checked_recursively(tmp_path):
    subdir = tmp_path / "chapters"
    subdir.mkdir()
    (subdir / "bab1.md").write_text("# BAB I\n\n![](gambar.png)\n", encoding="utf-8")

    assert len(check_markdown(subdir / "bab1.md")) == 1
    assert expand_paths([tmp_path]) == [subdir / "bab1.md"]


def test_check_text_uses_line_offset():
    issues = check_text(
        "| A | B |\n| --- | --- |\n| 1 | 2 |\n",
        path=Path("document.md"),
        line_offset=6,
    )

    assert issues[0].line == 7


def test_validate_stage_reports_original_file_line_number(tmp_path):
    path = write_markdown(
        tmp_path,
        "document.md",
        "---\n"
        "title: Uji\n"
        "author: Penulis\n"
        "structure: thesis\n"
        "format: undip-msi\n"
        "---\n"
        "\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n",
    )
    body = "---\ntitle: Uji\n---\n"  # tidak dipakai; body asli diambil manual
    body = path.read_text(encoding="utf-8").split("---\n", 2)[-1]
    ctx = SimpleNamespace(
        document=SimpleNamespace(path=path, body=body),
    )

    with pytest.raises(ValidationError) as caught:
        ValidateStage().run(ctx)

    assert caught.value.code == "VAL-CAPTION"
    assert "document.md:8" in caught.value.message or ":8:" in caught.value.message


def test_validate_stage_metadata():
    stage = ValidateStage()

    assert stage.name.value == "validate"
    assert stage.order == 10
    assert stage.mutates == frozenset()
    assert stage.idempotent is True
