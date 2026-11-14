"""Stage ``style_reference``: derived ``reference.docx`` dari ``format.yml``.

Sumber kebenaran nilai visual adalah :class:`docgen.config.Format`. Stage ini
tidak pernah menulis ke ``assets.reference_docx``; derived reference selalu
ditulis ke workspace/cache. Semua mutasi XML memakai ``docgen.docx``.
"""

import hashlib
import time
from collections.abc import Mapping
from pathlib import Path

from ..config import Format
from ..package import DocumentPackage
from ..package.styles import (
    StyleError,
    StyleSpec,
    apply_page_layout,
    apply_style_specs,
    build_style_patch,
    verify_style_contract,
)
from ..pipeline import BaseStage, StageName, StageResult, canonical_prefix

STYLE_REFERENCE_PART = "word/styles.xml"
DEFAULT_REFERENCE_NAME = "reference.docx"

# Style karakter yang wajib ada agar stage terms dapat langsung bekerja.
ISTILAH_STYLES: tuple[StyleSpec, ...] = (
    StyleSpec(
        style_id="IstilahAsing",
        style_type="character",
        based_on="DefaultParagraphFont",
        rpr={"i": True, "lang": {"val": "en-US"}},
        name="Istilah Asing",
        custom=True,
    ),
    StyleSpec(
        style_id="IstilahReview",
        style_type="character",
        based_on="DefaultParagraphFont",
        rpr={"highlight": {"val": "yellow"}},
        name="Istilah Review",
        custom=True,
    ),
)

_CODE_STYLE_TYPES: Mapping[str, str] = {
    "SourceCode": "paragraph",
    "VerbatimChar": "character",
    "HTMLCode": "character",
    "HTMLPreformatted": "paragraph",
}

_COVER_STYLES: tuple[str, ...] = (
    "CoverTitle",
    "CoverSubtitle",
    "CoverCourse",
    "CoverLecturer",
    "CoverName",
    "CoverLine",
    "CoverInstitution",
    "CoverImage",
)


def _alignment(value: str) -> str:
    return "both" if value == "justify" else value


def _line_twips(multiplier: float) -> int:
    return round(multiplier * 240)


def _spacing(
    *,
    before: int,
    after: int,
    line_spacing: float,
) -> dict[str, object]:
    return {
        "before": int(before),
        "after": int(after),
        "line": _line_twips(line_spacing),
        "lineRule": "auto",
    }


def _font_attrs(family: str) -> dict[str, object]:
    return {"ascii": family, "hAnsi": family, "cs": family}


def _size_attrs(size_half_points: int) -> dict[str, object]:
    return {"val": int(size_half_points)}


def _body_spec(style_id: str, format_spec: Format) -> StyleSpec:
    body = format_spec.font.body
    return StyleSpec(
        style_id=style_id,
        style_type="paragraph",
        based_on="Normal" if style_id != "Normal" else None,
        ppr={
            "spacing": _spacing(
                before=body.space_before,
                after=body.space_after,
                line_spacing=body.line_spacing,
            ),
            "ind": {"firstLine": body.first_line_indent},
            "jc": {"val": _alignment(body.alignment)},
        },
        rpr={
            "rFonts": _font_attrs(body.family),
            "color": {"val": body.color},
            "sz": _size_attrs(body.size_half_points),
            "szCs": _size_attrs(body.size_half_points),
        },
        name={"Normal": "Normal"}.get(style_id),
    )


def _heading_spec(level: int, format_spec: Format) -> StyleSpec:
    heading = format_spec.headings[f"heading{level}"]
    if level == 1:
        indent: dict[str, object] = {"firstLine": heading.first_line_indent}
    else:
        indent = {
            "left": heading.indent_left,
            "hanging": heading.indent_hanging,
        }
    return StyleSpec(
        style_id=f"Heading{level}",
        style_type="paragraph",
        based_on="Normal",
        ppr={
            "keepNext": heading.keep_next,
            "keepLines": heading.keep_lines,
            "spacing": _spacing(
                before=heading.space_before,
                after=heading.space_after,
                line_spacing=heading.line_spacing,
            ),
            "ind": indent,
            "jc": {"val": _alignment(heading.alignment)},
            "outlineLvl": {"val": heading.outline_level},
        },
        rpr={
            "rFonts": _font_attrs(heading.font_family),
            "color": {"val": heading.color},
            "sz": _size_attrs(heading.font_size_half_points),
            "szCs": _size_attrs(heading.font_size_half_points),
            "b": heading.bold,
            "bCs": heading.bold,
        },
        name=f"heading {level}",
    )


def _toc_heading_spec(format_spec: Format) -> StyleSpec:
    toc = format_spec.toc_heading
    return StyleSpec(
        style_id=toc.heading_style,
        style_type="paragraph",
        based_on="Normal",
        ppr={
            "spacing": _spacing(
                before=toc.space_before,
                after=toc.space_after,
                line_spacing=toc.line_spacing,
            ),
            "ind": {"firstLine": toc.first_line_indent},
            "jc": {"val": _alignment(toc.alignment)},
        },
        rpr={
            "rFonts": _font_attrs(toc.font_family),
            "color": {"val": toc.color},
            "sz": _size_attrs(toc.font_size_half_points),
            "szCs": _size_attrs(toc.font_size_half_points),
            "b": toc.bold,
            "bCs": toc.bold,
        },
        name="TOC Heading",
    )


def _caption_spec(
    style_id: str,
    *,
    format_spec: Format,
    kind: str,
) -> StyleSpec:
    if kind == "figure":
        caption = format_spec.captions.figure
        alignment = format_spec.figures.caption_alignment
    else:
        caption = format_spec.captions.table
        alignment = caption.font.alignment
    font = caption.font
    return StyleSpec(
        style_id=style_id,
        style_type="paragraph",
        based_on="Normal",
        ppr={
            **({"keepNext": True} if caption.keep_next else {}),
            "spacing": _spacing(
                before=font.space_before,
                after=font.space_after,
                line_spacing=font.line_spacing,
            ),
            "ind": {"left": 0, "right": 0, "firstLine": 0},
            "jc": {"val": _alignment(alignment)},
        },
        rpr={
            "rFonts": _font_attrs(font.family),
            "color": {"val": font.color},
            "sz": _size_attrs(font.size_half_points),
            "szCs": _size_attrs(font.size_half_points),
            "b": font.bold,
            "bCs": font.bold,
            "i": font.italic,
            "iCs": font.italic,
        },
        name={"ImageCaption": "Image Caption", "TableCaption": "Table Caption"}[style_id],
    )


def _code_spec(style_id: str, format_spec: Format) -> StyleSpec:
    """Bangun ``StyleSpec`` code/character dari ``format_spec.code``."""

    code = format_spec.code
    style_type = _CODE_STYLE_TYPES.get(style_id, "paragraph")
    ppr: dict[str, object] = {}
    if style_type == "paragraph":
        ppr = {
            "spacing": _spacing(
                before=code.space_before,
                after=code.space_after,
                line_spacing=code.line_spacing,
            ),
            "ind": {"left": 0, "right": 0, "firstLine": 0},
            "jc": {"val": _alignment(code.alignment)},
        }
    return StyleSpec(
        style_id=style_id,
        style_type=style_type,  # type: ignore[arg-type]
        ppr=ppr,
        rpr={
            "rFonts": {
                "ascii": code.font.family,
                "hAnsi": code.font.family,
                "cs": code.font.family,
                "asciiTheme": None,
                "hAnsiTheme": None,
                "cstheme": None,
                "eastAsiaTheme": None,
            },
            "color": {
                "val": code.font.color,
                "themeColor": None,
                "themeShade": None,
                "themeTint": None,
            },
            "sz": _size_attrs(code.font.size_half_points),
            "szCs": _size_attrs(code.font.size_half_points),
        },
        ppr_drops=("shd",) if style_type == "paragraph" else (),
        rpr_drops=("shd",),
        custom=style_type == "character",
    )


def _hyperlink_spec() -> StyleSpec:
    return StyleSpec(
        style_id="Hyperlink",
        style_type="character",
        rpr={
            "color": {
                "val": "000000",
                "themeColor": None,
                "themeShade": None,
                "themeTint": None,
            },
            "u": {"val": "none"},
        },
        name="Hyperlink",
    )


def _bibliography_spec(format_spec: Format) -> StyleSpec:
    bibliography = format_spec.bibliography_style
    return StyleSpec(
        style_id="Bibliography",
        style_type="paragraph",
        based_on="Normal",
        ppr={
            "spacing": _spacing(
                before=bibliography.space_before,
                after=bibliography.space_after,
                line_spacing=bibliography.line_spacing,
            ),
            "ind": {
                "left": bibliography.indent_left,
                "hanging": bibliography.indent_hanging,
            },
            "jc": {"val": "both"},
        },
        rpr={
            "rFonts": _font_attrs(bibliography.font_family),
            "sz": _size_attrs(bibliography.font_size_half_points),
            "szCs": _size_attrs(bibliography.font_size_half_points),
        },
        name="Bibliography",
    )


def _figure_spec(format_spec: Format) -> StyleSpec:
    figures = format_spec.figures
    return StyleSpec(
        style_id="Figure",
        style_type="paragraph",
        based_on="Normal",
        ppr={
            "spacing": _spacing(
                before=figures.space_before,
                after=figures.space_after,
                line_spacing=format_spec.font.body.line_spacing,
            ),
            "ind": {"firstLine": figures.first_line_indent},
            "jc": {"val": _alignment(figures.image_alignment)},
        },
        name="Figure",
    )


def _abstract_spec(style_id: str, format_spec: Format) -> StyleSpec:
    abstract = format_spec.abstract
    first_line_indent = format_spec.font.body.first_line_indent if style_id == "AbstractBody" else 0
    return StyleSpec(
        style_id=style_id,
        style_type="paragraph",
        based_on="Normal",
        ppr={
            "spacing": _spacing(
                before=abstract.space_before,
                after=abstract.space_after,
                line_spacing=abstract.line_spacing,
            ),
            "ind": {
                "left": 0,
                "right": 0,
                "firstLine": first_line_indent,
            },
            "jc": {"val": _alignment(abstract.alignment)},
        },
        rpr={
            "rFonts": _font_attrs(abstract.font_family),
            "color": {"val": format_spec.font.body.color},
            "sz": _size_attrs(abstract.font_size_half_points),
            "szCs": _size_attrs(abstract.font_size_half_points),
        },
        name=style_id,
        ppr_drops=("ind",),
    )


def _cover_spec(style_id: str) -> StyleSpec:
    bold = style_id == "CoverTitle"
    return StyleSpec(
        style_id=style_id,
        style_type="paragraph",
        based_on="Normal",
        ppr={
            "spacing": {
                "before": 0,
                "after": 0,
            },
            "ind": {"left": 0, "right": 0, "firstLine": 0},
            "jc": {"val": "center"},
        },
        rpr=({"b": True, "bCs": True} if bold else {"b": False, "bCs": False}),
        name=style_id,
        ppr_drops=("ind",),
    )


def _resolve_format_arg(
    format_spec: Format | None,
    alternate: Format | None,
) -> Format:
    if format_spec is not None and alternate is not None:
        raise TypeError("format diberikan dua kali")
    selected = format_spec if format_spec is not None else alternate
    if selected is None:
        raise TypeError("format wajib diberikan")
    return selected


def style_specs_for_format(
    format_spec: Format | None = None,
    *,
    format: Format | None = None,
) -> dict[str, StyleSpec]:
    """Bangun seluruh :class:`StyleSpec` dari ``format.yml``."""

    format_spec = _resolve_format_arg(format_spec, format)
    specs: dict[str, StyleSpec] = {}
    for style_id in ("Normal", "BodyText", "FirstParagraph"):
        specs[style_id] = _body_spec(style_id, format_spec)
    for level in (1, 2, 3):
        specs[f"Heading{level}"] = _heading_spec(level, format_spec)
    specs[format_spec.toc_heading.heading_style] = _toc_heading_spec(format_spec)
    specs["ImageCaption"] = _caption_spec(
        "ImageCaption",
        format_spec=format_spec,
        kind="figure",
    )
    specs["TableCaption"] = _caption_spec(
        "TableCaption",
        format_spec=format_spec,
        kind="table",
    )
    for style_id in _CODE_STYLE_TYPES:
        specs[style_id] = _code_spec(style_id, format_spec)
    specs["Hyperlink"] = _hyperlink_spec()
    specs["Bibliography"] = _bibliography_spec(format_spec)
    specs["Figure"] = _figure_spec(format_spec)
    for style_id in ("AbstractBody", "AbstractKeywords"):
        specs[style_id] = _abstract_spec(style_id, format_spec)
    for style_id in _COVER_STYLES:
        specs[style_id] = _cover_spec(style_id)
    for spec in ISTILAH_STYLES:
        specs[spec.style_id] = spec
    return specs


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_reference_docx(
    source: str | Path,
    output: str | Path,
    format_spec: Format | None = None,
    *,
    format: Format | None = None,
) -> Path:
    """Hasilkan derived reference dari ``source`` tanpa menimpa source.

    Output boleh berada di workspace/cache. Fungsi ini deterministik: input
    dan format yang sama menghasilkan payload ZIP yang sama.
    """

    format_spec = _resolve_format_arg(format_spec, format)
    source_path = Path(source)
    output_path = Path(output)
    if not source_path.is_file():
        raise StyleError(
            f"reference.docx sumber tidak ditemukan: {source_path}",
            code="STYLE-SOURCE-MISSING",
            path=source_path,
        )
    try:
        if source_path.resolve() == output_path.resolve():
            raise StyleError(
                "reference.docx sumber tidak boleh ditimpa; tulis derived reference ke cache/temp",
                code="STYLE-SOURCE-OVERWRITE",
                path=source_path,
            )
    except OSError:
        pass

    before = _digest(source_path)
    package = DocumentPackage.load(source_path)
    specs = style_specs_for_format(format_spec)
    apply_style_specs(package, specs)
    page = format_spec.page
    apply_page_layout(
        package,
        size=page.size,
        orientation=page.orientation,
        margins={
            "top": page.margins.top,
            "right": page.margins.right,
            "bottom": page.margins.bottom,
            "left": page.margins.left,
        },
        header=page.header_distance,
        footer=page.footer_distance,
        gutter=page.gutter,
    )
    verify_style_contract(package, specs)
    package.save(output_path)
    after = _digest(source_path)
    if before != after:
        raise StyleError(
            "reference.docx sumber berubah selama pembuatan derived",
            code="STYLE-SOURCE-MUTATED",
            path=source_path,
        )
    return output_path


def verify_reference_docx(
    path: str | Path,
    format_spec: Format | None = None,
    *,
    format: Format | None = None,
) -> None:
    """Verifikasi derived reference terhadap spec format."""

    format_spec = _resolve_format_arg(format_spec, format)
    package = DocumentPackage.load(Path(path))
    verify_style_contract(package, style_specs_for_format(format_spec))


class StyleReferenceStage(BaseStage):
    """Hasilkan derived reference sebelum Pandoc."""

    name = StageName.STYLE_REFERENCE
    order = 30
    requires = canonical_prefix(StageName.STYLE_REFERENCE)
    mutates = frozenset({"workspace", "cache"})

    def run(self, ctx: object) -> StageResult:
        started = time.monotonic()
        format_spec = ctx.format  # type: ignore[attr-defined]
        source = Path(format_spec.assets.reference_docx)
        workspace = ctx.workspace  # type: ignore[attr-defined]
        ensure = getattr(workspace, "ensure", None)
        if callable(ensure):
            ensure()
        output = workspace.path(DEFAULT_REFERENCE_NAME)
        output.parent.mkdir(parents=True, exist_ok=True)
        before = _digest(output) if output.is_file() else None
        build_reference_docx(source, output, format_spec)
        after = _digest(output)
        ctx.reference_docx = output  # type: ignore[attr-defined]
        artifacts = getattr(ctx, "artifacts", None)
        if artifacts is not None:
            keys = artifacts.keys() if hasattr(artifacts, "keys") else ()
            if "reference_docx" not in keys:
                artifacts.put("reference_docx", output)
        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=before != after,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={
                "reference_bytes": output.stat().st_size,
                "source": str(source),
            },
            artifacts=(output,),
        )


def main(argv: list[str] | None = None) -> int:
    """CLI dev tipis: hasilkan derived reference dari format id.

    Orkestrasi produksi tetap milik ``docgen.pipeline``; fungsi ini hanya
    memudahkan pembuatan fixture dan pemeriksaan manual.
    """

    import argparse

    from ..config import load_format

    parser = argparse.ArgumentParser(description="Hasilkan derived reference.docx dari format.yml.")
    parser.add_argument("--format", required=True, help="ID format")
    parser.add_argument("--out", required=True, help="path derived reference")
    parser.add_argument(
        "--source",
        default=None,
        help="opsional; default assets.reference_docx milik format",
    )
    args = parser.parse_args(argv)
    format_spec = load_format(args.format)
    source = (
        Path(args.source) if args.source is not None else Path(format_spec.assets.reference_docx)
    )
    build_reference_docx(source, Path(args.out), format_spec)
    return 0


__all__ = [
    "DEFAULT_REFERENCE_NAME",
    "ISTILAH_STYLES",
    "StyleReferenceStage",
    "build_reference_docx",
    "build_style_patch",
    "main",
    "style_specs_for_format",
    "verify_reference_docx",
]
