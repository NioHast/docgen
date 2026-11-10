"""Stage ``front_matter``: materialisasi Markdown sebelum Pandoc.

Stage ini memindahkan bagian ``Pandoc`` dari ``docx.lua`` yang berjalan
sebelum Pandoc:

- sampul dari metadata dokumen + ``structure.cover`` + ``format.assets.logo``;
- template legal ``approval``/``statement`` dari ``structure.front_matter``;
- ``preface``, ``abstract_id``, ``abstract_en``, dan kata kunci;
- penomoran Heading 1/2/3 pada body;
- page break dan section break front matter dengan margin dari ``format.yml``.

Output berupa Markdown yang siap dikonsumsi Pandoc. Body hanya dibaca dari
artifact ``mermaid.markdown`` milik stage mermaid; tidak ada fallback ke
``document.body``. TOC dan daftar gambar/tabel **tidak** ditulis di sini;
keduanya milik stage post-Pandoc.
"""

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from ..config import Format, FrontMatterItem, Structure
from ..document import Document
from ..docx.page import PAGE_SIZES, page_size
from ..errors import DocgenError
from ..markdown.headings import (
    NumberingSpec,
    balance_title,
    number_markdown_headings,
    parse_heading,
)
from ..pipeline import BaseStage, StageName, StageResult

__all__ = [
    "PAGE_BREAK_XML",
    "FrontMatterError",
    "FrontMatterStage",
    "page_break",
    "render_front_matter",
    "render_template",
    "spacer",
]

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_WHITESPACE_RE = re.compile(r"\s+")

PAGE_BREAK_XML = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


class FrontMatterError(DocgenError):
    """Front matter tidak dapat dirender dari data yang diberikan."""

    default_code = "FRONT-MATTER"


@dataclass(frozen=True, slots=True)
class _FrontMatterValues:
    """Nilai yang boleh dipakai placeholder template."""

    mapping: Mapping[str, str]

    @classmethod
    def from_document(cls, document: Document) -> _FrontMatterValues:
        metadata = document.metadata
        authors = ", ".join(metadata.author_names)
        nims = ", ".join(author.nim for author in metadata.authors if author.nim is not None)
        return cls(
            mapping={
                "title": metadata.title,
                "subtitle": metadata.subtitle or "",
                "author": authors,
                "authors": authors,
                "nim": nims,
                "lecturer": metadata.lecturer or "",
                "lecturer_label": metadata.lecturer_label,
                "course": metadata.course or "",
                "institution": metadata.institution or "",
                "faculty": metadata.faculty or "",
                "year": metadata.year or "",
                "date": metadata.date or "",
                "lang": metadata.lang,
                "abstract_id": metadata.abstract_id or "",
                "abstract_en": metadata.abstract_en or "",
                "preface": metadata.preface or "",
                "keywords": ", ".join(metadata.keywords),
                "keywords_en": ", ".join(metadata.keywords_en),
                "report_name": metadata.report_name,
            }
        )


def _raw_openxml(xml: str) -> str:
    return f"```{{=openxml}}\n{xml}\n```"


def page_break() -> str:
    """Raw block page break yang setara dengan ``pagebreak()`` docx.lua."""

    return _raw_openxml(PAGE_BREAK_XML)


def spacer(twips: int) -> str:
    """Jarak vertikal eksplisit, bukan deretan ``<w:p/>`` kosong.

    ``docx.lua`` menerjemahkan 640 twip menjadi dua paragraf kosong (360 twip
    per baris). Stage ini menulis satu paragraf dengan ``w:spacing`` eksplisit
    agar jumlah jarak tidak bergantung pada ukuran font/style Normal.
    """

    if twips <= 0:
        return ""
    return _raw_openxml(
        f'<w:p><w:pPr><w:spacing w:before="{int(twips)}" w:after="0"/></w:pPr></w:p>'
    )


def _div(style: str, content: str) -> str:
    return f'::: {{custom-style="{style}"}}\n{content.strip()}\n:::'


def _one_line(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _twips_to_cm(twips: int) -> str:
    centimeters = twips / 566.9291338582677
    return f"{centimeters:.2f}".rstrip("0").rstrip(".")


def _logo_destination(path: str | Path) -> str:
    destination = Path(path).expanduser().resolve().as_posix()
    if any(character.isspace() for character in destination):
        return f"<{destination}>"
    return destination


def _lecturer_label(label: str) -> str:
    """Normalisasi label dosen seperti cabang ``lecturer_label`` docx.lua."""

    text = label.strip()
    if not text:
        return "Dosen Pengampu: "
    if not re.search(r":\s*$", text):
        return text + ": "
    if not text.endswith((" ", "\t")):
        return text + " "
    return text


def _template_values(document: Document) -> Mapping[str, str]:
    return _FrontMatterValues.from_document(document).mapping


def render_template(
    template: str,
    values: Mapping[str, str],
    *,
    path: str | Path | None = None,
) -> str:
    """Ganti placeholder ``{{ key }}`` pada template legal.

    Placeholder yang tidak dikenal adalah error, bukan dibiarkan lolos ke
    DOCX. Placeholder berbentuk ``{{?istilah?}}`` bukan milik template ini dan
    tidak cocok dengan pola, sehingga tetap dipertahankan untuk stage terms.
    """

    def replace(match: re.Match[str]) -> str:
        key = match.group("key")
        if key not in values:
            raise FrontMatterError(
                f"template memuat variabel tidak dikenal: '{{{{ {key} }}}}'",
                code="CFG-TEMPLATE-VAR",
                path=path,
                key=key,
            )
        return str(values[key])

    return _PLACEHOLDER_RE.sub(replace, template)


def _section_break(format: Format) -> str:
    """Section break penutup sampul dengan ukuran/margin dari format.yml."""

    page = format.page
    raw_size = str(page.size).upper()
    size = "Letter" if raw_size == "LETTER" else raw_size
    orientation = str(page.orientation).lower()
    if size not in PAGE_SIZES or orientation not in {"portrait", "landscape"}:
        raise FrontMatterError(
            f"ukuran halaman tidak didukung: {page.size}/{page.orientation}",
            code="FRONT-MATTER-PAGE",
            key="page.size",
        )
    width, height = page_size(size, orientation)
    orientation_attr = ' w:orient="landscape"' if orientation == "landscape" else ""
    margins = page.margins
    return _raw_openxml(
        "<w:p><w:pPr><w:sectPr>"
        '<w:footnotePr><w:numRestart w:val="eachSect"/></w:footnotePr>'
        f'<w:pgSz w:w="{width}" w:h="{height}"{orientation_attr}/>'
        f'<w:pgMar w:top="{margins.top}" w:right="{margins.right}" '
        f'w:bottom="{margins.bottom}" w:left="{margins.left}" '
        f'w:header="{page.header_distance}" w:footer="{page.footer_distance}" '
        f'w:gutter="{page.gutter}"/>'
        "</w:sectPr></w:pPr></w:p>"
    )


def _render_cover(
    document: Document,
    structure: Structure,
    format: Format,
    *,
    include_logo: bool,
    logo: str | Path | None,
) -> str:
    metadata = document.metadata
    blocks: list[str] = []

    title = _one_line(metadata.title)
    if title:
        upper_title = title.upper()
        title_lines = balance_title(upper_title) if structure.cover.title_split else (upper_title,)
        blocks.append(_div("CoverTitle", "  \n".join(title_lines)))

    if metadata.subtitle:
        blocks.append(_div("CoverSubtitle", _one_line(metadata.subtitle).upper()))
    if metadata.course:
        blocks.append(_div("CoverCourse", f"**{_one_line(metadata.course)}**"))
    if metadata.lecturer and structure.cover.show_lecturer:
        label = _lecturer_label(metadata.lecturer_label)
        blocks.append(
            _div(
                "CoverLecturer",
                f"{label}**{_one_line(metadata.lecturer)}**",
            )
        )

    if include_logo and logo is not None:
        blocks.append(spacer(640))
        width = _twips_to_cm(structure.cover.logo_width)
        blocks.append(
            _div(
                "CoverImage",
                f"![]({_logo_destination(logo)}){{width={width}cm}}",
            )
        )
        blocks.append(spacer(640))

    if metadata.authors:
        blocks.append(_div("CoverLine", "Disusun oleh:"))
        for author in metadata.authors:
            blocks.append(_div("CoverName", f"**{_one_line(author.name)}**"))
            if author.nim:
                blocks.append(_div("CoverLine", _one_line(author.nim)))

    if metadata.faculty or metadata.institution or metadata.year:
        blocks.append(spacer(640))
        for value in (metadata.faculty, metadata.institution, metadata.year):
            if value:
                blocks.append(_div("CoverInstitution", _one_line(value).upper()))

    blocks.append(_section_break(format))
    return "\n\n".join(block for block in blocks if block)


def _read_template(
    structure: Structure,
    template_name: str | None,
    *,
    document: Document,
) -> str:
    if not template_name:
        raise FrontMatterError(
            "front_matter source template tidak memiliki key 'template'",
            code="CFG-CONDITIONAL",
            key="template",
        )
    template_dir = structure.template_dir.resolve()
    path = (template_dir / template_name).resolve()
    try:
        path.relative_to(template_dir)
    except ValueError as exc:
        raise FrontMatterError(
            f"template keluar dari direktori template: {template_name}",
            code="CFG-PATH-ESCAPE",
            path=path,
            key="template",
        ) from exc
    if not path.is_file():
        raise FrontMatterError(
            f"template tidak ditemukan: {template_name}",
            code="CFG-TEMPLATE-MISSING",
            path=path,
            key="template",
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise FrontMatterError(
            f"template tidak dapat dibaca: {exc}",
            code="CFG-TEMPLATE-MISSING",
            path=path,
            key="template",
        ) from exc
    rendered = render_template(
        text,
        _template_values(document),
        path=path,
    ).strip()
    return rendered + "\n\n" + page_break()


def _render_preface(document: Document) -> str:
    text = document.metadata.preface
    if not text or not text.strip():
        raise FrontMatterError(
            "front matter 'preface' wajib diisi untuk struktur ini",
            code="CFG-REQUIRED",
            path=document.path,
            key="preface",
        )
    return "\n\n".join(
        [
            "# KATA PENGANTAR {-}",
            text.strip(),
            page_break(),
        ]
    )


def _emphasize_paragraphs(text: str) -> str:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n[ \t]*\n", text.strip())
        if paragraph.strip()
    ]
    return "\n\n".join(f"*{paragraph}*" for paragraph in paragraphs)


def _render_abstract(
    document: Document,
    *,
    english: bool,
) -> str:
    metadata = document.metadata
    text = metadata.abstract_en if english else metadata.abstract_id
    label = "ABSTRACT" if english else "ABSTRAK"
    keyword_label = "Keywords:" if english else "Kata Kunci:"
    keywords = metadata.keywords_en if english else metadata.keywords

    if not text or not text.strip():
        key = "abstract_en" if english else "abstract_id"
        raise FrontMatterError(
            f"front matter '{key}' wajib diisi untuk struktur ini",
            code="CFG-REQUIRED",
            path=document.path,
            key=key,
        )

    blocks: list[str] = [f"# {label} {{-}}"]
    if metadata.title:
        title = _one_line(metadata.title).upper()
        blocks.append(_div("CoverLine", f"*{title}*" if english else title))
    blocks.append(_emphasize_paragraphs(text) if english else text.strip())
    if keywords:
        joined = ", ".join(keywords)
        blocks.append(f"**{keyword_label}** *{joined}*")
    blocks.append(page_break())
    return "\n\n".join(blocks)


def _render_item(
    item: FrontMatterItem,
    document: Document,
    structure: Structure,
    format: Format,
    *,
    include_logo: bool,
    logo: str | Path | None,
) -> str | None:
    item_id = item.id
    source = item.source

    if item_id == "cover":
        return _render_cover(
            document,
            structure,
            format,
            include_logo=include_logo,
            logo=logo,
        )
    if item_id in {"approval", "statement"}:
        if source != "template":
            raise FrontMatterError(
                f"front matter '{item_id}' harus memakai source template",
                code="CFG-CONDITIONAL",
                key=item_id,
            )
        return _read_template(
            structure,
            item.template,
            document=document,
        )
    if item_id == "preface":
        return _render_preface(document)
    if item_id == "abstract_id":
        return _render_abstract(document, english=False)
    if item_id == "abstract_en":
        return _render_abstract(document, english=True)
    if item_id in {"toc", "list_of_tables", "list_of_figures"}:
        # Field TOC/daftar ditulis oleh stage post-Pandoc. Jangan membuat
        # placeholder di Markdown agar tidak ada field ganda.
        return None
    raise FrontMatterError(
        f"front matter id tidak dikenal: {item_id}",
        code="CFG-UNKNOWN-FRONT-MATTER",
        key=item_id,
    )


def _mark_appendix_unnumbered(markdown: str) -> str:
    """Tandai Heading 1 ``Lampiran`` dan turunannya sebagai unnumbered.

    ``# Lampiran`` adalah back matter yang mengikuti
    ``structure.back_matter.appendices``. Tanpa penanda ``{-}``, numberer
    Markdown akan memberinya nomor bab berikutnya (mis. ``BAB VI``) sebelum
    stage ``sections`` sempat mengenalinya sebagai back matter. Heading 2/3
    di bawah Lampiran juga tidak boleh mewarisi nomor subbab bab terakhir.
    """

    def with_marker(parsed: Any, line: str) -> str:
        content = line.rstrip("\r\n")
        attributes = parsed.attributes.strip()
        if attributes:
            inner = attributes[1:-1].strip()
            attributes = "{ " + " ".join(filter(None, (inner, ".unnumbered"))) + " }"
        else:
            attributes = "{-}"
        ending = line[len(content) :]
        return f"{parsed.indent}{'#' * parsed.level} {parsed.text} {attributes}{ending}"

    lines: list[str] = []
    in_appendix = False
    for line in markdown.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        parsed = parse_heading(content)
        if parsed is None or not parsed.text:
            lines.append(line)
            continue
        if parsed.level == 1:
            in_appendix = parsed.text.strip().casefold() == "lampiran"
            if in_appendix and not parsed.unnumbered:
                lines.append(with_marker(parsed, line))
                continue
        elif in_appendix and parsed.level in (2, 3) and not parsed.unnumbered:
            lines.append(with_marker(parsed, line))
            continue
        lines.append(line)
    return "".join(lines)


def render_front_matter(
    document: Document,
    structure: Structure,
    format: Format,
    *,
    body: str | None = None,
    include_logo: bool = True,
    logo: str | Path | None = None,
) -> str:
    """Bangun Markdown final sebelum Pandoc.

    ``body`` default adalah ``document.body``. Bila stage menerima Markdown
    hasil Mermaid, kirimkan lewat parameter ini. Logo default berasal dari
    ``format.assets.logo``; ``include_logo=False`` mematikan blok logo untuk
    pengujian atau format tanpa logo.
    """

    source_body = document.body if body is None else body
    spec = NumberingSpec(
        body=structure.numbering.body,  # type: ignore[arg-type]
        sub_dot=structure.numbering.sub_dot,
        subsub_dot=structure.numbering.subsub_dot,
    )
    numbered_body = number_markdown_headings(
        _mark_appendix_unnumbered(source_body),
        spec,
    )

    resolved_logo = format.assets.logo if logo is None else logo
    blocks: list[str] = []
    for item in structure.front_matter:
        block = _render_item(
            item,
            document,
            structure,
            format,
            include_logo=include_logo,
            logo=resolved_logo,
        )
        if block:
            blocks.append(block)

    blocks.append(numbered_body)
    return "\n\n".join(block.strip("\n") for block in blocks if block.strip()) + "\n"


def _markdown_source(ctx: Any) -> str:
    """Sumber body satu-satunya: artifact ``mermaid.markdown`` dari stage mermaid.

    Tidak ada fallback ke ``document.body`` maupun ke artifact ``markdown``
    milik stage ini sendiri. Artifact yang tidak dideklarasikan atau tidak
    dapat dibaca adalah error input, bukan alasan memakai sumber cadangan.
    """

    artifacts = getattr(ctx, "artifacts", None)
    try:
        keys = tuple(artifacts.keys()) if artifacts is not None else ()
    except AttributeError, TypeError:
        keys = ()
    if artifacts is None or "mermaid.markdown" not in keys:
        raise FrontMatterError(
            "artifact 'mermaid.markdown' dari stage mermaid tidak tersedia",
            code="FRONT-MATTER-INPUT",
            key="mermaid.markdown",
        )
    path = Path(artifacts.get("mermaid.markdown"))
    if not path.is_file():
        raise FrontMatterError(
            f"artifact mermaid.markdown tidak ditemukan atau bukan file: {path}",
            code="FRONT-MATTER-INPUT",
            path=path,
        )
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise FrontMatterError(
            f"artifact mermaid.markdown tidak dapat dibaca: {exc}",
            code="FRONT-MATTER-INPUT",
            path=path,
        ) from exc


class FrontMatterStage(BaseStage):
    """Stage materialisasi Markdown sebelum ``pandoc``.

    Body hanya dibaca dari artifact ``mermaid.markdown`` milik stage mermaid;
    tidak ada fallback ke ``document.body`` atau artifact lain.
    """

    name: ClassVar[StageName] = StageName.FRONT_MATTER
    order: ClassVar[int] = 35
    requires: ClassVar[tuple[StageName, ...]] = (
        StageName.VALIDATE,
        StageName.MERMAID,
        StageName.STYLE_REFERENCE,
    )
    mutates: ClassVar[frozenset[str]] = frozenset({"workspace"})
    idempotent: ClassVar[bool] = True

    def run(self, ctx: Any) -> StageResult:
        started = time.monotonic()
        ctx.workspace.ensure()
        path = ctx.workspace.path("front_matter.md")
        body = _markdown_source(ctx)
        text = render_front_matter(
            ctx.document,
            ctx.structure,
            ctx.format,
            body=body,
            logo=ctx.format.assets.logo,
        )
        previous = path.read_text(encoding="utf-8") if path.is_file() else None
        changed = previous != text
        if changed:
            path.write_text(text, encoding="utf-8", newline="\n")

        # Output final untuk Pandoc memakai key standar ``markdown``. Stage
        # mermaid menyimpan bahan mentahnya di ``mermaid.markdown`` agar tidak
        # dianggap output stage ini saat build dijalankan ulang.
        keys = set(ctx.artifacts.keys())
        if "markdown" not in keys:
            ctx.artifacts.put("markdown", path)

        return StageResult(
            stage=self.name.value,
            status="ok",
            changed=changed,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={"markdown_bytes": len(text.encode("utf-8"))},
            artifacts=(path,),
        )
