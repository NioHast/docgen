"""Tes modul istilah asing. Fixture DOCX dibuat dengan python-docx."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from lxml.etree import _Element

from terms import (
    ISTILAH_ASING,
    ISTILAH_REVIEW,
    MARKER_RE,
    MarkerError,
    direct_style_id,
    ensure_styles,
    iter_markers,
    main,
)

FIXTURES = Path(__file__).parent / "fixtures" / "istilah"


# ---------------------------------------------------------------------------
# Helper pembuat fixture


def write_glossary(tmp_path: Path, rows: list[tuple[str, ...]]) -> Path:
    """Tulis TSV UTF-8/LF dengan header yang benar."""

    path = tmp_path / "istilah.tsv"
    lines = ["# glosarium tes", "term\titalic\tgloss_first\tstatus"]
    for row in rows:
        lines.append("\t".join(row))
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path


def make_docx(tmp_path: Path, paragraphs: list[str]) -> Path:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    path = tmp_path / "dokumen.docx"
    doc.save(path)
    return path


def paragraph_style_spans(paragraph, style_id: str) -> list[str]:
    spans: list[str] = []
    current: list[str] = []
    for run in paragraph.runs:
        if direct_style_id(run._r) == style_id:
            current.append(run.text)
        elif current:
            spans.append("".join(current))
            current = []
    if current:
        spans.append("".join(current))
    return spans


def all_style_spans(path: Path, style_id: str) -> list[str]:
    doc = Document(path)
    spans: list[str] = []
    for paragraph in doc.paragraphs:
        spans.extend(paragraph_style_spans(paragraph, style_id))
    return spans


def find_style(doc: Document, style_id: str) -> _Element:
    for style in doc.styles.element.findall(qn("w:style")):
        if style.get(qn("w:styleId")) == style_id:
            return style
    raise AssertionError(f"Style {style_id} tidak ditemukan")


def add_direct_lang(run, value: str) -> None:
    rpr = run._r.get_or_add_rPr()
    for old in rpr.findall(qn("w:lang")):
        rpr.remove(old)
    lang = OxmlElement("w:lang")
    lang.set(qn("w:val"), value)
    rpr.append(lang)


def istilah_run(doc: Document, paragraph, text: str):
    ensure_styles(doc)
    run = paragraph.add_run(text)
    run.style = doc.styles["Istilah Asing"]
    return run


def xml_style_ids(path: Path, style_id: str) -> list[str]:
    doc = Document(path)
    result: list[str] = []
    for run in doc.element.body.iter(qn("w:r")):
        rpr = run.find(qn("w:rPr"))
        if rpr is None:
            continue
        rstyle = rpr.find(qn("w:rStyle"))
        if rstyle is not None and rstyle.get(qn("w:val")) == style_id:
            result.append("".join(node.text or "" for node in run.findall(qn("w:t"))))
    return result


def add_external_hyperlink(paragraph, text: str, url: str) -> None:
    rel_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel_id)
    run = OxmlElement("w:r")
    text_node = OxmlElement("w:t")
    text_node.text = text
    run.append(text_node)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_complex_field(paragraph, result_text: str, instruction: str = " MERGEFIELD X ") -> None:
    begin_run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin_run._r.append(begin)

    instruction_run = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    instruction_run._r.append(instr)

    separate_run = paragraph.add_run()
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    separate_run._r.append(separate)

    paragraph.add_run(result_text)

    end_run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    end_run._r.append(end)


# ---------------------------------------------------------------------------
# Tes wajib


def test_training_data_italic_data_pelatihan_upright(tmp_path, capsys):
    glossary = write_glossary(
        tmp_path,
        [
            ("training data", "yes", "no", "confirmed"),
            ("data", "no", "no", "confirmed"),
        ],
    )
    docx = make_docx(tmp_path, ["training data", "data pelatihan"])

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    assert doc.paragraphs[0].text == "training data"
    assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_ASING) == [
        "training data"
    ]
    assert paragraph_style_spans(doc.paragraphs[1], ISTILAH_ASING) == []

    style = find_style(doc, ISTILAH_ASING)
    assert style.get(qn("w:type")) == "character"
    assert style.find(qn("w:basedOn")).get(qn("w:val")) == "DefaultParagraphFont"
    rpr = style.find(qn("w:rPr"))
    assert rpr.find(qn("w:i")) is not None
    assert rpr.find(qn("w:lang")).get(qn("w:val")) == "en-US"
    assert capsys.readouterr().out


def test_big_data_longest_wins_and_standalone_data_upright(tmp_path):
    glossary = write_glossary(
        tmp_path,
        [
            ("big data", "yes", "no", "confirmed"),
            ("data", "no", "no", "confirmed"),
        ],
    )
    docx = make_docx(tmp_path, ["big data dan data"])

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    assert doc.paragraphs[0].text == "big data dan data"
    assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_ASING) == ["big data"]


def test_longer_nonitalic_term_blocks_shorter_italic_term(tmp_path):
    glossary = write_glossary(
        tmp_path,
        [
            ("big data", "no", "no", "confirmed"),
            ("data", "yes", "no", "confirmed"),
        ],
    )
    docx = make_docx(tmp_path, ["big data"])

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    assert doc.paragraphs[0].text == "big data"
    assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_ASING) == []


def test_range_exact_prefix_suffix_unchanged_in_one_run(tmp_path):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = make_docx(tmp_path, ["awal training data akhir"])

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    paragraph = doc.paragraphs[0]
    assert paragraph.text == "awal training data akhir"
    assert paragraph_style_spans(paragraph, ISTILAH_ASING) == ["training data"]
    assert paragraph.runs[0].text == "awal "
    assert paragraph.runs[-1].text == " akhir"
    assert direct_style_id(paragraph.runs[0]._r) is None
    assert direct_style_id(paragraph.runs[-1]._r) is None

    styled_run = next(
        run
        for run in paragraph.runs
        if direct_style_id(run._r) == ISTILAH_ASING
    )
    rpr = styled_run._r.find(qn("w:rPr"))
    assert rpr.find(qn("w:i")) is not None
    assert rpr.find(qn("w:lang")).get(qn("w:val")) == "en-US"


def test_term_split_across_three_runs_keeps_other_formatting(tmp_path):
    glossary = write_glossary(
        tmp_path,
        [
            ("training data", "yes", "no", "confirmed"),
            ("data", "no", "no", "confirmed"),
        ],
    )
    docx = tmp_path / "terpotong.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("trai")
    middle = paragraph.add_run("ning")
    middle.bold = True
    paragraph.add_run(" data")
    doc.save(docx)

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    paragraph = doc.paragraphs[0]
    assert paragraph.text == "training data"
    assert paragraph_style_spans(paragraph, ISTILAH_ASING) == ["training data"]
    middle_runs = [run for run in paragraph.runs if run.text == "ning"]
    assert len(middle_runs) == 1
    assert middle_runs[0].bold is True
    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 0


def test_product_names_are_not_styled(tmp_path):
    glossary = write_glossary(
        tmp_path,
        [
            ("Python", "no", "no", "confirmed"),
            ("Microsoft Word", "no", "no", "confirmed"),
        ],
    )
    docx = make_docx(tmp_path, ["Python dan Microsoft Word adalah nama produk."])

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    assert doc.paragraphs[0].text == "Python dan Microsoft Word adalah nama produk."
    assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_ASING) == []


def test_marker_becomes_review_text_and_is_recorded(tmp_path, capsys):
    glossary = write_glossary(
        tmp_path,
        [("validation dataset", "yes", "no", "review")],
    )
    docx = tmp_path / "review.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("Bagian {{?validation ")
    paragraph.add_run("dataset?}} perlu dicek.")
    doc.save(docx)

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    paragraph = doc.paragraphs[0]
    assert paragraph.text == "Bagian validation dataset perlu dicek."
    assert paragraph_style_spans(paragraph, ISTILAH_REVIEW) == [
        "validation dataset"
    ]
    assert "{{?" not in paragraph.text
    assert "?}}" not in paragraph.text

    style = find_style(doc, ISTILAH_REVIEW)
    assert style.get(qn("w:type")) == "character"
    assert style.find(qn("w:rPr")).find(qn("w:highlight")).get(qn("w:val")) == "yellow"

    review_file = tmp_path / "review" / "istilah-baru.txt"
    assert review_file.read_text(encoding="utf-8") == "validation dataset\n"

    assert main(["review", str(docx)]) == 0
    output = capsys.readouterr().out
    assert "validation dataset" in output


def test_ordinary_question_sentence_is_untouched(tmp_path):
    glossary = write_glossary(tmp_path, [])
    docx = make_docx(tmp_path, ["Apa itu data? Mengapa penting?"])

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    paragraph = doc.paragraphs[0]
    assert paragraph.text == "Apa itu data? Mengapa penting?"
    assert paragraph_style_spans(paragraph, ISTILAH_ASING) == []
    assert paragraph_style_spans(paragraph, ISTILAH_REVIEW) == []
    review_file = tmp_path / "review" / "istilah-baru.txt"
    assert review_file.read_text(encoding="utf-8") == ""


def test_marker_regex_only_accepts_new_syntax():
    assert MARKER_RE.search("?lama?") is None
    assert MARKER_RE.search("Apa itu data? Mengapa?") is None
    match = MARKER_RE.search("awal {{?validation dataset?}} akhir")
    assert match is not None
    assert match.group(1) == "validation dataset"
    assert MARKER_RE.fullmatch("{{?baris\nbaru?}}") is None
    assert MARKER_RE.fullmatch("{{?ada {{?nested?}}") is None


def test_empty_and_malformed_markers_raise():
    for value in (
        "??",
        "{{??}}",
        "{{? ?}}",
        "{{?tanpa penutup",
        "{{?a\nb?}}",
        "{{?a\rb?}}",
        "{{?a }} b?}}",
    ):
        with pytest.raises(MarkerError):
            list(iter_markers(value))


def test_check_reports_empty_marker_as_error(tmp_path, capsys):
    markdown = tmp_path / "bab.md"
    markdown.write_bytes(b"{{??}}\n")

    assert main(["check", str(markdown)]) == 1
    assert "kosong" in capsys.readouterr().err


def test_review_preserved_after_two_and_three_applies(tmp_path):
    glossary = write_glossary(
        tmp_path, [("validation dataset", "yes", "no", "review")]
    )
    docx = make_docx(tmp_path, ["Bagian {{?validation dataset?}} perlu dicek."])
    review_file = tmp_path / "review" / "istilah-baru.txt"

    for apply_number in (1, 2, 3):
        assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0
        assert review_file.read_text(encoding="utf-8") == "validation dataset\n"
        doc = Document(docx)
        assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_REVIEW) == [
            "validation dataset"
        ]
        assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_ASING) == []
        assert doc.paragraphs[0].text == (
            "Bagian validation dataset perlu dicek."
        ), f"apply ke-{apply_number} mengubah teks"


def test_verify_fails_for_plain_italic_term(tmp_path, capsys):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = make_docx(tmp_path, ["training data tanpa style"])

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    output = capsys.readouterr().out
    assert "tanpa style IstilahAsing" in output


def test_verify_fails_when_marker_remains(tmp_path, capsys):
    glossary = write_glossary(tmp_path, [])
    docx = tmp_path / "marker.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("Bagian {{?belum ")
    paragraph.add_run("diputuskan?}}.")
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    output = capsys.readouterr().out
    assert "masih ada penanda" in output
    assert "{{?belum diputuskan?}}" in output


def test_verify_fails_for_wrong_istilah_asing_run(tmp_path, capsys):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = tmp_path / "salah-style.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("Python")
    style = doc.styles.add_style("IstilahAsing", WD_STYLE_TYPE.CHARACTER)
    run.style = style
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    output = capsys.readouterr().out
    assert "bukan istilah di glosarium" in output


def test_verify_uses_effective_style_properties(tmp_path, capsys):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = tmp_path / "style-tanpa-lang.docx"
    doc = Document()
    style = doc.styles.add_style(ISTILAH_ASING, WD_STYLE_TYPE.CHARACTER)
    style_el = find_style(doc, ISTILAH_ASING)
    rpr = OxmlElement("w:rPr")
    rpr.append(OxmlElement("w:i"))
    style_el.append(rpr)
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("training data")
    run.style = style
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    output = capsys.readouterr().out
    assert "bukan en-US" in output


def test_verify_fails_istilah_asing_with_direct_italic_off(tmp_path, capsys):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = tmp_path / "direct-italic-off.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = istilah_run(doc, paragraph, "training data")
    run.italic = False
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    output = capsys.readouterr().out
    assert "tidak efektif italic" in output


def test_verify_fails_istilah_asing_with_non_en_us_lang(tmp_path, capsys):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = tmp_path / "direct-lang-id.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = istilah_run(doc, paragraph, "training data")
    add_direct_lang(run, "id-ID")
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    output = capsys.readouterr().out
    assert "bukan en-US" in output


def test_italic_no_term_with_manual_italic_fails(tmp_path, capsys):
    glossary = write_glossary(tmp_path, [("data", "no", "no", "confirmed")])
    docx = tmp_path / "data-italic.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("data")
    run.italic = True
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    output = capsys.readouterr().out
    assert "seharusnya tegak" in output


def test_italic_no_term_with_istilah_asing_fails(tmp_path, capsys):
    glossary = write_glossary(tmp_path, [("data", "no", "no", "confirmed")])
    docx = tmp_path / "data-asing.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    istilah_run(doc, paragraph, "data")
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    output = capsys.readouterr().out
    assert "seharusnya tegak" in output


def test_product_name_with_en_us_but_not_italic_passes(tmp_path):
    glossary = write_glossary(tmp_path, [("Python", "no", "no", "confirmed")])
    docx = tmp_path / "python-lang.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("Python")
    add_direct_lang(run, "en-US")
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 0


def test_data_does_not_match_inside_datang_or_metadata(tmp_path):
    glossary = write_glossary(
        tmp_path, [("data", "yes", "no", "confirmed")]
    )
    docx = make_docx(tmp_path, ["datang dan metadata"])

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    assert doc.paragraphs[0].text == "datang dan metadata"
    assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_ASING) == []


# ---------------------------------------------------------------------------
# Tes tambahan untuk aturan pencocokan dan keamanan


def test_case_preserved_and_double_space_not_matched(tmp_path):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = make_docx(tmp_path, ["Training Data", "training  data"])

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    assert doc.paragraphs[0].text == "Training Data"
    assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_ASING) == [
        "Training Data"
    ]
    assert doc.paragraphs[1].text == "training  data"
    assert paragraph_style_spans(doc.paragraphs[1], ISTILAH_ASING) == []


def test_hyphenated_term_and_case_insensitive_match(tmp_path):
    glossary = write_glossary(
        tmp_path,
        [
            ("fine-tuning", "yes", "no", "confirmed"),
            ("tuning", "no", "no", "confirmed"),
        ],
    )
    docx = make_docx(tmp_path, ["Fine-Tuning dan tuning"])

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    assert doc.paragraphs[0].text == "Fine-Tuning dan tuning"
    assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_ASING) == [
        "Fine-Tuning"
    ]


def test_explicit_italic_off_does_not_override_istilah_asing(tmp_path):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = tmp_path / "italic-off.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("training data")
    run.italic = False
    add_direct_lang(run, "id-ID")
    doc.save(docx)

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    styled_runs = [
        run
        for run in doc.paragraphs[0].runs
        if direct_style_id(run._r) == ISTILAH_ASING
    ]
    assert len(styled_runs) == 1
    rpr = styled_runs[0]._r.find(qn("w:rPr"))
    italic = rpr.find(qn("w:i"))
    assert italic is not None
    assert italic.get(qn("w:val")) in {None, "1", "true", "on"}
    lang = rpr.find(qn("w:lang"))
    assert lang is not None
    assert lang.get(qn("w:val")) == "en-US"


def test_ensure_styles_repairs_existing_istilah_asing_definition():
    doc = Document()
    doc.styles.add_style(ISTILAH_ASING, WD_STYLE_TYPE.CHARACTER)
    style = find_style(doc, ISTILAH_ASING)
    rpr = OxmlElement("w:rPr")
    wrong_italic = OxmlElement("w:i")
    wrong_italic.set(qn("w:val"), "0")
    wrong_lang = OxmlElement("w:lang")
    wrong_lang.set(qn("w:val"), "id-ID")
    rpr.append(wrong_italic)
    rpr.append(wrong_lang)
    style.append(rpr)

    ensure_styles(doc)

    rpr = find_style(doc, ISTILAH_ASING).find(qn("w:rPr"))
    italic = rpr.find(qn("w:i"))
    assert italic is not None
    assert italic.get(qn("w:val")) is None
    assert rpr.find(qn("w:lang")).get(qn("w:val")) == "en-US"
    assert (
        find_style(doc, ISTILAH_ASING).find(qn("w:basedOn")).get(qn("w:val"))
        == "DefaultParagraphFont"
    )


def test_pending_review_item_with_en_us_is_not_a_verify_failure(tmp_path):
    glossary = write_glossary(
        tmp_path,
        [("validation dataset", "yes", "no", "review")],
    )
    docx = tmp_path / "review-lang.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("Bagian {{?validation dataset?}} perlu dicek.")
    add_direct_lang(run, "en-US")
    doc.save(docx)

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0
    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 0


def test_manual_italic_is_skipped_but_reported_as_direct_formatting(
    tmp_path, capsys
):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = tmp_path / "manual.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("training data")
    run.italic = True
    doc.save(docx)

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0
    doc = Document(docx)
    assert paragraph_style_spans(doc.paragraphs[0], ISTILAH_ASING) == []

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 0
    output = capsys.readouterr().out
    assert "direct formatting" in output


def test_plain_english_text_with_en_us_passes(tmp_path):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = tmp_path / "english.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("This is ordinary English prose.")
    add_direct_lang(run, "en-US")
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 0


def test_italic_term_with_direct_en_us_without_style_fails(tmp_path, capsys):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = tmp_path / "term-lang.docx"
    doc = Document()
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("training data")
    run.italic = True  # lolos cek "plain"; satu-satunya kegagalan harus cek bahasa
    add_direct_lang(run, "en-US")
    doc.save(docx)

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    output = capsys.readouterr().out
    assert "direct w:lang en-US tanpa style IstilahAsing" in output


def test_external_hyperlink_and_field_are_not_touched(tmp_path):
    glossary = write_glossary(
        tmp_path, [("training data", "yes", "no", "confirmed")]
    )
    docx = tmp_path / "aman.docx"
    doc = Document()

    hyperlink_paragraph = doc.add_paragraph("Awal ")
    add_external_hyperlink(hyperlink_paragraph, "training data", "https://example.com")
    hyperlink_paragraph.add_run(" akhir")

    field_paragraph = doc.add_paragraph("Awal ")
    add_complex_field(field_paragraph, "training data")
    field_paragraph.add_run(" akhir")

    doc.save(docx)

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    assert all_style_spans(docx, ISTILAH_ASING) == []
    assert doc.paragraphs[0].text == "Awal training data akhir"
    assert doc.paragraphs[1].text == "Awal training data akhir"

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 0


def test_markers_inside_field_and_external_hyperlink_are_reported(
    tmp_path, capsys
):
    glossary = write_glossary(tmp_path, [])
    docx = tmp_path / "marker-terlindungi.docx"
    doc = Document()

    hyperlink_paragraph = doc.add_paragraph("Awal ")
    add_external_hyperlink(
        hyperlink_paragraph,
        "{{?external term?}}",
        "https://example.com",
    )
    hyperlink_paragraph.add_run(" akhir")

    field_paragraph = doc.add_paragraph("Awal ")
    add_complex_field(field_paragraph, "{{?field term?}}")
    field_paragraph.add_run(" akhir")

    doc.save(docx)
    before = [paragraph.text for paragraph in Document(docx).paragraphs]

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0
    apply_output = capsys.readouterr().out
    assert "field/hyperlink" in apply_output
    assert "{{?external term?}}" in apply_output
    assert "{{?field term?}}" in apply_output

    after = [paragraph.text for paragraph in Document(docx).paragraphs]
    assert after == before
    assert "{{?external term?}}" in after[0]
    assert "{{?field term?}}" in after[1]
    assert xml_style_ids(docx, ISTILAH_REVIEW) == []
    assert xml_style_ids(docx, ISTILAH_ASING) == []
    review_file = tmp_path / "review" / "istilah-baru.txt"
    assert review_file.read_text(encoding="utf-8") == "external term\nfield term\n"

    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 1
    verify_output = capsys.readouterr().out
    assert "field/hyperlink" in verify_output
    assert "external term" in verify_output
    assert "field term" in verify_output

    assert main(["review", str(docx)]) == 0
    review_output = capsys.readouterr().out
    assert "external term" in review_output
    assert "field term" in review_output


def test_check_writes_review_file_and_exits_two(tmp_path):
    markdown = tmp_path / "bab.md"
    markdown.write_text(
        "Satu {{?baru?}} dan {{?baru?}} serta {{?istilah lain?}}.\n",
        encoding="utf-8",
        newline="\n",
    )

    assert main(["check", str(markdown)]) == 2

    review_file = tmp_path / "review" / "istilah-baru.txt"
    assert review_file.read_text(encoding="utf-8") == "baru\nistilah lain\n"


def test_check_validates_glossary(tmp_path, capsys):
    markdown = tmp_path / "bab.md"
    markdown.write_text("{{?baru?}}\n", encoding="utf-8", newline="\n")
    bad_glossary = tmp_path / "rusak.tsv"
    bad_glossary.write_bytes(
        (
            "term\titalic\tgloss_first\tstatus\n"
            "data\tyes\tno\tconfirmed\n"
            "DATA\tno\tno\tconfirmed\n"
            "ambigu\tmungkin\tno\tconfirmed\n"
            "kurang\tkolom\n"
        ).encode("utf-8")
    )

    assert main(["check", str(markdown), "--glossary", str(bad_glossary)]) == 1
    error = capsys.readouterr().err
    assert "duplikat" in error
    assert "italic harus" in error
    assert "kolom kurang" in error


def test_static_fixture_apply_then_verify(tmp_path):
    source = FIXTURES / "contoh.docx"
    glossary = FIXTURES / "istilah.tsv"
    docx = tmp_path / "contoh.docx"
    shutil.copyfile(source, docx)

    assert main(["apply", str(docx), "--glossary", str(glossary)]) == 0
    assert main(["verify", str(docx), "--glossary", str(glossary)]) == 0

    doc = Document(docx)
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    assert "{{?" not in text
    assert "?}}" not in text
    assert "training data" in text
    assert (tmp_path / "review" / "istilah-baru.txt").exists()
