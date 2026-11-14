"""Tes unit ``docx/terms.py`` dan stage ``stages/terms.py``."""

import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from autooffice.docx import paths
from autooffice.docx.package import DocumentPackage
from autooffice.docx.package.paragraphs import paragraph_text
from autooffice.docx.package.xml import iter_paragraphs, iter_runs
from autooffice.docx.pipeline import BuildOptions
from autooffice.docx.stages import terms as terms_stage
from autooffice.docx.stages.terms import TermsStage, resolve_glossary, review_path_for
from autooffice.docx.terms import (
    GlossaryError,
    MarkerError,
    StyleResolution,
    TermsError,
    TermsVerifyReport,
    apply_terms,
    ensure_styles,
    iter_markers,
    load_glossary,
    match_terms,
    merge_glossaries,
    resolve_style,
    verify_terms,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def write_glossary(
    tmp_path: Path,
    rows: list[tuple[str, ...]],
    *,
    header: str = "term\titalic",
    filename: str = "istilah.tsv",
) -> Path:
    path = tmp_path / filename
    lines = ["# glosarium tes", header]
    for row in rows:
        lines.append("\t".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def make_docx(tmp_path: Path, paragraphs: list[str], name: str = "dokumen.docx") -> Path:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    path = tmp_path / name
    document.save(path)
    return path


def run_style(run) -> str | None:
    rpr = run.find(f"{W}rPr")
    if rpr is None:
        return None
    rstyle = rpr.find(f"{W}rStyle")
    if rstyle is None:
        return None
    return rstyle.get(f"{W}val")


def style_spans(package: DocumentPackage, style_id: str) -> list[str]:
    spans: list[str] = []
    current: list[str] = []
    root = package.xml("word/document.xml")
    for paragraph in iter_paragraphs(root):
        for run in iter_runs(paragraph):
            text = "".join(node.text or "" for node in run.findall(f"{W}t"))
            if run_style(run) == style_id:
                current.append(text)
            elif current:
                spans.append("".join(current))
                current = []
    if current:
        spans.append("".join(current))
    return spans


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


def add_complex_field(paragraph, result_text: str) -> None:
    begin_run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin_run._r.append(begin)

    instruction_run = paragraph.add_run()
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " MERGEFIELD X "
    instruction_run._r.append(instruction)

    separate_run = paragraph.add_run()
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    separate_run._r.append(separate)

    paragraph.add_run(result_text)

    end_run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    end_run._r.append(end)


def context(
    tmp_path: Path,
    package: DocumentPackage,
    *,
    terms: bool = True,
    body: str = "",
    glossary: Path | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        document=SimpleNamespace(path=tmp_path / "document.md", body=body),
        options=BuildOptions(terms=terms),
        package=package,
        glossary=glossary,
    )


# ---------------------------------------------------------------------------
# Glosarium dan pencocokan
# ---------------------------------------------------------------------------


def test_glossary_only_loads_live_fields(tmp_path: Path) -> None:
    path = write_glossary(tmp_path, [("training data", "yes")])

    glossary = load_glossary(path)
    entry = glossary.entries["training data"]

    fields = {field.name for field in dataclasses.fields(entry)}
    assert "line_no" not in fields
    assert "gloss_first" not in fields
    assert "status" not in fields
    assert entry.term == "training data"
    assert entry.italic is True


def test_glossary_old_header_rejected(tmp_path: Path) -> None:
    path = tmp_path / "istilah.tsv"
    path.write_text(
        "term\titalic\tgloss_first\tstatus\ndata\tno\tno\tconfirmed\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(GlossaryError) as error:
        load_glossary(path)

    assert error.value.code == "GLOSSARY-HEADER"


def test_package_glossary_loads_all_entries() -> None:
    path = paths.glossary_file()
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    glossary = load_glossary(path)

    assert lines[0] == "term\titalic"
    assert len(glossary) == len(lines) - 1
    assert "data" in glossary.entries


def test_glossary_duplicate_and_invalid_value(tmp_path: Path) -> None:
    path = write_glossary(
        tmp_path,
        [("data", "yes"), ("DATA", "no"), ("salah", "mungkin")],
    )

    with pytest.raises(GlossaryError) as error:
        load_glossary(path)

    message = str(error.value)
    assert "duplikat" in message
    assert "italic harus" in message


def test_match_terms_longest_phrase_and_word_boundary(tmp_path: Path) -> None:
    glossary = load_glossary(
        write_glossary(
            tmp_path,
            [("big data", "yes"), ("data", "no"), ("training data", "yes")],
        )
    )

    matches = match_terms("big data, training data, metadata, datang", glossary)
    values = [match.entry.term for match in matches]

    assert values == ["big data", "training data"]
    assert [match.start for match in matches] == [0, 10]


def test_merge_glossary_override_wins_per_phrase(tmp_path: Path) -> None:
    base = load_glossary(write_glossary(tmp_path, [("data", "no")], filename="base.tsv"))
    override = load_glossary(write_glossary(tmp_path, [("data", "yes")], filename="override.tsv"))

    merged = merge_glossaries(base, override)

    assert merged.entries["data"].italic is True
    assert merged.source == override.source


# ---------------------------------------------------------------------------
# Apply / verify
# ---------------------------------------------------------------------------


def test_apply_verify_and_idempotent(tmp_path: Path) -> None:
    glossary = load_glossary(
        write_glossary(
            tmp_path,
            [("training data", "yes"), ("data", "no")],
        )
    )
    source = make_docx(tmp_path, ["Awal training data dan data akhir."])
    package = DocumentPackage.load(source)

    report = apply_terms(package, glossary)

    assert report.applied == 1
    assert report.changed is True
    assert style_spans(package, "IstilahAsing") == ["training data"]
    assert verify_terms(package, glossary).violations == ()

    first = tmp_path / "first.docx"
    package.save(first)

    second_report = apply_terms(package, glossary)
    assert second_report.applied == 0
    assert second_report.changed is False

    second = tmp_path / "second.docx"
    package.save(second)
    assert first.read_bytes() == second.read_bytes()


def test_marker_becomes_review_and_text_intact(tmp_path: Path) -> None:
    glossary = load_glossary(write_glossary(tmp_path, []))
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("Bagian {{?validation ")
    paragraph.add_run("dataset?}} perlu dicek.")
    source = tmp_path / "marker.docx"
    document.save(source)
    package = DocumentPackage.load(source)
    review = tmp_path / ".laporan" / "istilah-baru.txt"

    report = apply_terms(package, glossary, review_path=review)

    text = "\n".join(
        paragraph_text(paragraph) for paragraph in iter_paragraphs(package.xml("word/document.xml"))
    )
    assert "{{?" not in text
    assert "?}}" not in text
    assert "Bagian validation dataset perlu dicek." in text
    assert style_spans(package, "IstilahReview") == ["validation dataset"]
    assert report.reviews == ("validation dataset",)
    assert review.read_text(encoding="utf-8") == "validation dataset\n"
    assert verify_terms(package, glossary).violations == ()


def test_verify_fails_for_plain_text(tmp_path: Path) -> None:
    glossary = load_glossary(write_glossary(tmp_path, [("training data", "yes")]))
    package = DocumentPackage.load(make_docx(tmp_path, ["training data"]))

    report = verify_terms(package, glossary)

    assert report.violations
    assert "tanpa style IstilahAsing" in report.violations[0]


def test_verify_fails_for_remaining_marker(tmp_path: Path) -> None:
    glossary = load_glossary(write_glossary(tmp_path, []))
    package = DocumentPackage.load(make_docx(tmp_path, ["Bagian {{?belum diputuskan?}}."]))

    report = verify_terms(package, glossary)

    assert report.violations
    assert "masih ada penanda" in report.violations[0]


def test_verify_fails_when_italic_no_text_is_slanted(tmp_path: Path) -> None:
    glossary = load_glossary(write_glossary(tmp_path, [("data", "no")]))
    document = Document()
    run = document.add_paragraph().add_run("data")
    run.italic = True
    path = tmp_path / "data-miring.docx"
    document.save(path)

    report = verify_terms(DocumentPackage.load(path), glossary)

    assert report.violations
    assert "seharusnya tegak" in report.violations[0]


def test_external_hyperlink_and_field_untouched(tmp_path: Path) -> None:
    glossary = load_glossary(write_glossary(tmp_path, [("training data", "yes")]))
    document = Document()

    hyperlink_paragraph = document.add_paragraph("Awal ")
    add_external_hyperlink(
        hyperlink_paragraph,
        "training data",
        "https://example.com",
    )
    hyperlink_paragraph.add_run(" akhir")

    field_paragraph = document.add_paragraph("Awal ")
    add_complex_field(field_paragraph, "training data")
    field_paragraph.add_run(" akhir")

    source = tmp_path / "aman.docx"
    document.save(source)
    package = DocumentPackage.load(source)

    report = apply_terms(package, glossary)

    assert report.applied == 0
    assert style_spans(package, "IstilahAsing") == []
    assert verify_terms(package, glossary).violations == ()
    texts = [
        paragraph_text(paragraph) for paragraph in iter_paragraphs(package.xml("word/document.xml"))
    ]
    assert texts == ["Awal training data akhir", "Awal training data akhir"]


def test_marker_validation() -> None:
    assert [marker.content for marker in iter_markers("{{?satu?}}")] == ["satu"]
    for value in ("{{??}}", "{{? ?}}", "{{?tanpa penutup", "{{?a\nb?}}"):
        with pytest.raises(MarkerError):
            list(iter_markers(value))


def test_resolver_unified_style(tmp_path: Path) -> None:
    package = DocumentPackage.load(make_docx(tmp_path, ["data"]))
    ensure_styles(package)

    resolution = resolve_style(package, "IstilahAsing")

    assert isinstance(resolution, StyleResolution)
    assert resolution.italic is True
    assert resolution.lang == "en-US"


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


def test_stage_terms_off_does_not_write_review(tmp_path: Path) -> None:
    package = DocumentPackage.load(make_docx(tmp_path, ["training data"]))
    before = package.part("word/document.xml")
    ctx = context(tmp_path, package, terms=False)

    stage = TermsStage()
    result = stage.run(ctx)

    assert stage.enabled(ctx) is False
    assert result.status == "skipped"
    assert result.changed is False
    assert package.part("word/document.xml") == before
    assert not (tmp_path / ".laporan").exists()


def test_stage_terms_on_override_user_wins(tmp_path: Path) -> None:
    glossary_path = write_glossary(tmp_path, [("data", "yes")])
    package = DocumentPackage.load(make_docx(tmp_path, ["data dan data lain"]))
    ctx = context(tmp_path, package, terms=True, glossary=glossary_path)

    result = TermsStage().run(ctx)

    assert result.status == "ok"
    assert result.changed is True
    assert result.metrics["applied"] == 2
    assert style_spans(package, "IstilahAsing") == ["data", "data"]
    review = review_path_for(tmp_path / "document.md")
    assert review == tmp_path / ".laporan" / "istilah-baru.txt"
    assert review.is_file()
    assert verify_terms(package, load_glossary(glossary_path)).violations == ()


def test_stage_terms_gate_verify_fails(tmp_path: Path, monkeypatch) -> None:
    glossary_path = write_glossary(tmp_path, [("training data", "yes")])
    package = DocumentPackage.load(make_docx(tmp_path, ["training data"]))
    ctx = context(tmp_path, package, terms=True, glossary=glossary_path)

    monkeypatch.setattr(
        terms_stage,
        "verify_terms",
        lambda package, glossary: TermsVerifyReport(
            violations=("pelanggaran uji",),
            warnings=(),
        ),
    )

    with pytest.raises(TermsError) as error:
        TermsStage().run(ctx)

    assert "verifikasi istilah gagal" in str(error.value)


def test_stage_terms_without_package(tmp_path: Path) -> None:
    ctx = context(tmp_path, package=None)  # type: ignore[arg-type]

    with pytest.raises(TermsError):
        TermsStage().run(ctx)


def test_resolve_glossary_package_and_user_override(tmp_path: Path) -> None:
    (tmp_path / "document.md").write_text("---\ntitle: x\n---\n", encoding="utf-8")
    write_glossary(tmp_path, [("data", "yes")])

    glossary = resolve_glossary(tmp_path / "document.md")

    assert glossary.entries["data"].italic is True
    assert glossary.source == tmp_path / "istilah.tsv"
