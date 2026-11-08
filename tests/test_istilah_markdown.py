"""Tes preprocessing glosarium Markdown untuk build PDF."""

from __future__ import annotations

from pathlib import Path

from istilah_markdown import main

HEADER = "term\titalic\tgloss_first\tstatus\n"


def write_glossary(tmp_path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    path = tmp_path / "istilah.tsv"
    lines = [HEADER.rstrip("\n")]
    lines.extend("\t".join(row) for row in rows)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path


def run_preprocess(
    tmp_path: Path,
    source: str,
    rows: list[tuple[str, str, str, str]],
    *,
    filename: str = "bab1-pendahuluan.md",
    out_name: str = "chapters-pre",
) -> tuple[str, Path, Path]:
    src = tmp_path / "chapters"
    src.mkdir()
    (src / filename).write_text(source, encoding="utf-8", newline="\n")
    glossary = write_glossary(tmp_path, rows)
    out = tmp_path / out_name

    assert main(
        [
            "--src",
            str(src),
            "--glossary",
            str(glossary),
            "--out",
            str(out),
        ]
    ) == 0

    return (out / filename).read_text(encoding="utf-8"), src, glossary


GUI_ROW = ("graphical user interface", "yes", "yes", "confirmed")


def test_graphical_user_interface_is_wrapped(tmp_path):
    source = (
        "Metode ini memakai Graphical User Interface (GUI).\n"
        "Lalu ditulis ulang sebagai graphical user interface.\n"
    )
    expected = (
        "Metode ini memakai *Graphical User Interface* (GUI).\n"
        "Lalu ditulis ulang sebagai *graphical user interface*.\n"
    )

    output, _, _ = run_preprocess(tmp_path, source, [GUI_ROW])

    assert output == expected


def test_longest_phrase_wins_over_short_word(tmp_path):
    output, _, _ = run_preprocess(
        tmp_path,
        "training data dan data pelatihan.\n",
        [
            ("training data", "yes", "no", "confirmed"),
            ("data", "yes", "no", "confirmed"),
        ],
    )

    assert output == "*training data* dan *data* pelatihan.\n"
    assert "*training*" not in output


def test_longer_nonitalic_term_blocks_shorter_italic_term(tmp_path):
    output, _, _ = run_preprocess(
        tmp_path,
        "big data dan data pelatihan.\n",
        [
            ("big data", "no", "no", "confirmed"),
            ("data", "yes", "no", "confirmed"),
        ],
    )

    assert output == "big data dan *data* pelatihan.\n"


def test_code_fence_and_inline_code_are_untouched(tmp_path):
    source = (
        "```python\n"
        "Graphical User Interface\n"
        "```\n"
        "\n"
        "`Graphical User Interface` dan ``Graphical User Interface``.\n"
        "\n"
        "Graphical User Interface di luar kode.\n"
    )
    expected = (
        "```python\n"
        "Graphical User Interface\n"
        "```\n"
        "\n"
        "`Graphical User Interface` dan ``Graphical User Interface``.\n"
        "\n"
        "*Graphical User Interface* di luar kode.\n"
    )

    output, _, _ = run_preprocess(tmp_path, source, [GUI_ROW])

    assert output == expected


def test_already_italic_text_is_not_wrapped_twice(tmp_path):
    source = (
        "*Graphical User Interface* dan _Graphical User Interface_ tetap.\n"
    )

    output, _, _ = run_preprocess(tmp_path, source, [GUI_ROW])

    assert output == source


def test_links_are_untouched(tmp_path):
    source = (
        "Buka [Graphical User Interface](https://example.com/graphical-user-interface).\n"
        "Gambar: ![Graphical User Interface](gambar/graphical-user-interface.png)\n"
        "Graphical User Interface juga muncul di sini.\n"
    )
    expected = (
        "Buka [Graphical User Interface](https://example.com/graphical-user-interface).\n"
        "Gambar: ![Graphical User Interface](gambar/graphical-user-interface.png)\n"
        "*Graphical User Interface* juga muncul di sini.\n"
    )

    output, _, _ = run_preprocess(tmp_path, source, [GUI_ROW])

    assert output == expected


def test_idempotent(tmp_path):
    source = "Graphical User Interface dan training data.\n"
    rows = [
        GUI_ROW,
        ("training data", "yes", "no", "confirmed"),
    ]

    first, _, glossary = run_preprocess(tmp_path, source, rows)
    assert first == "*Graphical User Interface* dan *training data*.\n"

    second_out = tmp_path / "chapters-pre-2"
    assert main(
        [
            "--src",
            str(tmp_path / "chapters-pre"),
            "--glossary",
            str(glossary),
            "--out",
            str(second_out),
        ]
    ) == 0
    second = (second_out / "bab1-pendahuluan.md").read_text(encoding="utf-8")

    assert second == first


def test_yaml_frontmatter_is_not_modified(tmp_path):
    source = (
        "---\n"
        "title: Graphical User Interface\n"
        "tags:\n"
        "  - training data\n"
        "---\n"
        "Graphical User Interface di badan dokumen.\n"
    )
    expected = (
        "---\n"
        "title: Graphical User Interface\n"
        "tags:\n"
        "  - training data\n"
        "---\n"
        "*Graphical User Interface* di badan dokumen.\n"
    )

    output, _, _ = run_preprocess(
        tmp_path,
        source,
        [GUI_ROW, ("training data", "yes", "no", "confirmed")],
    )

    assert output == expected


def test_out_must_not_equal_src(tmp_path, capsys):
    src = tmp_path / "chapters"
    src.mkdir()
    (src / "bab1.md").write_text(
        "Graphical User Interface.\n", encoding="utf-8", newline="\n"
    )
    glossary = write_glossary(tmp_path, [GUI_ROW])

    assert main(
        [
            "--src",
            str(src),
            "--glossary",
            str(glossary),
            "--out",
            str(src),
        ]
    ) == 1
    assert "tidak boleh sama" in capsys.readouterr().err
    assert (src / "bab1.md").read_text(encoding="utf-8") == (
        "Graphical User Interface.\n"
    )


def test_missing_glossary_is_reported(tmp_path, capsys):
    src = tmp_path / "chapters"
    src.mkdir()
    (src / "bab1.md").write_text(
        "Graphical User Interface.\n", encoding="utf-8", newline="\n"
    )

    assert main(
        [
            "--src",
            str(src),
            "--glossary",
            str(tmp_path / "tidak-ada.tsv"),
            "--out",
            str(tmp_path / "out"),
        ]
    ) == 1
    assert "Glosarium tidak ditemukan" in capsys.readouterr().err
