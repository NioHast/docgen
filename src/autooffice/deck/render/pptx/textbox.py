"""Text box native dan renderer block berbasis teks untuk PPTX."""

from collections.abc import Mapping
from dataclasses import dataclass

from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.shapes.base import BaseShape
from pptx.slide import Slide
from pptx.text.text import TextFrame, _Paragraph
from pptx.util import Emu

from autooffice.deck.layout.measure import measure_code_text, measure_text
from autooffice.deck.model.deck_ir import BlockIR
from autooffice.design.theme import Theme

from .shapes import (
    Box,
    PptxRenderError,
    apply_paragraph_style,
    apply_run_style,
    field_optional_text,
    field_sequence,
    field_text,
    set_chrome_shape,
    set_keyed_shape,
)

_TITLE_ROLES = frozenset({"display", "title"})
_ROLE_COLORS = {
    "display": "ink",
    "title": "ink",
    "lead": "ink_secondary",
    "body": "ink",
    "caption": "muted",
    "label": "ink_secondary",
    "kicker": "accent",
}
_ROLE_WEIGHTS = {
    "display": 800,
    "title": 700,
    "lead": 600,
    "body": 400,
    "caption": 400,
    "label": 600,
    "kicker": 700,
}


@dataclass(frozen=True, slots=True)
class TextStyle:
    """Gaya teks yang seluruhnya diturunkan dari token theme."""

    size_pt: float
    weight: int
    color: str
    family: str
    line_height: float


def role_style(theme: Theme, role: str | None) -> TextStyle:
    """Petakan role authoring ke ukuran, bobot, dan warna token."""
    active_role = role if role in _ROLE_COLORS else "body"
    typography = theme.typography
    size_pt = typography.title_pt if active_role in _TITLE_ROLES else typography.body_pt
    if active_role in {"caption", "label", "kicker"}:
        size_pt = typography.minimum_pt
    return TextStyle(
        size_pt=max(size_pt, typography.minimum_pt),
        weight=_ROLE_WEIGHTS[active_role],
        color=_color_for_role(theme, active_role),
        family=typography.family,
        line_height=typography.line_height,
    )


def body_style(theme: Theme, *, weight: int = 400, color: str | None = None) -> TextStyle:
    """Gaya body standar yang dapat dipakai caption tabel dan media."""
    return TextStyle(
        size_pt=max(theme.typography.body_pt, theme.typography.minimum_pt),
        weight=weight,
        color=theme.colors.ink if color is None else color,
        family=theme.typography.family,
        line_height=theme.typography.line_height,
    )


def code_style(theme: Theme) -> TextStyle:
    """Gaya teks code dari token code."""
    return TextStyle(
        size_pt=max(theme.code.size_pt, theme.typography.minimum_pt),
        weight=400,
        color=theme.colors.ink,
        family=theme.code.family,
        line_height=theme.code.line_height,
    )


def add_keyed_text(
    slide: Slide,
    box: Box,
    *,
    key: str,
    text: str,
    style: TextStyle,
    theme: Theme,
    description: str | None = None,
    bullet: bool = False,
    ordered: bool = False,
    bullet_start: int = 1,
    hyperlink: str | None = None,
) -> BaseShape:
    """Buat text box native berkey dan terapkan token tipografi."""
    return _add_text_shape(
        slide,
        box,
        key=key,
        chrome_name=None,
        text=text,
        style=style,
        theme=theme,
        description=text if description is None else description,
        bullet=bullet,
        ordered=ordered,
        bullet_start=bullet_start,
        hyperlink=hyperlink,
        alignment=PP_ALIGN.LEFT,
    )


def add_chrome_text(
    slide: Slide,
    box: Box,
    *,
    name: str,
    text: str,
    style: TextStyle,
    theme: Theme,
    description: str = "",
    alignment: PP_ALIGN = PP_ALIGN.LEFT,
) -> BaseShape:
    """Buat text box chrome tanpa key agar tidak dihitung coverage."""
    return _add_text_shape(
        slide,
        box,
        key=None,
        chrome_name=name,
        text=text,
        style=style,
        theme=theme,
        description=description,
        bullet=False,
        ordered=False,
        bullet_start=1,
        hyperlink=None,
        alignment=alignment,
    )


def _add_text_shape(
    slide: Slide,
    box: Box,
    *,
    key: str | None,
    chrome_name: str | None,
    text: str,
    style: TextStyle,
    theme: Theme,
    description: str,
    bullet: bool,
    ordered: bool,
    bullet_start: int,
    hyperlink: str | None,
    alignment: PP_ALIGN,
) -> BaseShape:
    """Bangun satu text box lalu tandai sebagai key atau chrome."""
    shape = slide.shapes.add_textbox(
        Emu(box.left),
        Emu(box.top),
        Emu(box.width),
        Emu(box.height),
    )
    if not shape.has_text_frame:
        label = f"key '{key}'" if key is not None else f"chrome '{chrome_name}'"
        raise PptxRenderError(f"Text box untuk {label} tidak memiliki text frame.")
    text_frame = shape.text_frame
    text_frame.word_wrap = True
    text_frame.auto_size = MSO_AUTO_SIZE.NONE
    text_frame.margin_left = Emu(0)
    text_frame.margin_right = Emu(0)
    text_frame.margin_top = Emu(0)
    text_frame.margin_bottom = Emu(0)
    _write_paragraphs(
        text_frame,
        text,
        style=style,
        theme=theme,
        bullet=bullet,
        ordered=ordered,
        bullet_start=bullet_start,
        hyperlink=hyperlink,
        alignment=alignment,
    )
    if key is not None:
        set_keyed_shape(shape, key, description=description)
    else:
        set_chrome_shape(shape, chrome_name or "", description=description)
    return shape


def add_caption(
    slide: Slide,
    box: Box,
    *,
    key: str,
    text: str,
    theme: Theme,
) -> BaseShape:
    """Buat caption media berkey dengan gaya caption."""
    style = body_style(theme, weight=400, color=theme.colors.muted)
    return add_keyed_text(slide, box, key=key, text=text, style=style, theme=theme)


def render_text_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
) -> tuple[BaseShape, ...]:
    """Render block ``text`` menjadi satu atau dua text box berkey."""
    inner = box.inset(theme.spacing.card_padding_emu)
    heading = field_optional_text(block.fields, "heading")
    body = field_text(block.fields, "text", block_id=block.block_id)
    body_text_style = role_style(theme, block.role)
    namespace = f"{slide_id}.{block.block_id}"
    if not heading:
        return (
            add_keyed_text(
                slide,
                inner,
                key=f"{namespace}.text",
                text=body,
                style=body_text_style,
                theme=theme,
            ),
        )

    heading_style = body_style(theme, weight=600, color=theme.colors.ink_secondary)
    heading_height = measure_text(
        heading,
        available_width_emu=inner.width,
        theme=theme,
        font_size_pt=heading_style.size_pt,
        weight=heading_style.weight,
    ).height_emu
    heading_height = min(max(1, heading_height), inner.height)
    body_height = inner.height - heading_height
    if body_height <= 0:
        raise PptxRenderError(
            f"Block '{block.block_id}' tidak menyisakan ruang untuk teks setelah heading."
        )
    heading_box = Box(left=inner.left, top=inner.top, width=inner.width, height=heading_height)
    body_box = Box(
        left=inner.left,
        top=inner.top + heading_height,
        width=inner.width,
        height=body_height,
    )
    return (
        add_keyed_text(
            slide,
            heading_box,
            key=f"{namespace}.heading",
            text=heading,
            style=heading_style,
            theme=theme,
        ),
        add_keyed_text(
            slide,
            body_box,
            key=f"{namespace}.text",
            text=body,
            style=body_text_style,
            theme=theme,
        ),
    )


def render_bullets_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
) -> tuple[BaseShape, ...]:
    """Render setiap item bullets sebagai paragraph native berkey sendiri."""
    inner = box.inset(theme.spacing.card_padding_emu)
    items = field_sequence(block.fields, "items", block_id=block.block_id)
    ordered = bool(block.fields.get("ordered", False))
    indent = theme.spacing.md_emu
    available_width = inner.width - indent
    if available_width <= 0:
        raise PptxRenderError(f"Block '{block.block_id}' tidak memiliki lebar untuk bullets.")
    style = body_style(theme)
    namespace = f"{slide_id}.{block.block_id}"
    heights = [
        max(
            1,
            measure_text(
                item,
                available_width_emu=available_width,
                theme=theme,
                font_size_pt=style.size_pt,
                weight=style.weight,
            ).height_emu,
        )
        for item in items
    ]
    if not heights:
        raise PptxRenderError(f"Block bullets '{block.block_id}' tidak memiliki item.")
    total = sum(heights)
    if total > inner.height:
        raise PptxRenderError(
            f"Block bullets '{block.block_id}' memerlukan tinggi {total} EMU, "
            f"melebihi kotak {inner.height} EMU."
        )
    top = inner.top
    shapes: list[BaseShape] = []
    for index, (item, height) in enumerate(zip(items, heights, strict=True), start=1):
        item_box = Box(left=inner.left, top=top, width=inner.width, height=height)
        shapes.append(
            add_keyed_text(
                slide,
                item_box,
                key=f"{namespace}.item{index}.text",
                text=item,
                style=style,
                theme=theme,
                bullet=True,
                ordered=ordered,
                bullet_start=index,
            )
        )
        top += height
    return tuple(shapes)


def render_quote_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
) -> tuple[BaseShape, ...]:
    """Render quote dan attribution sebagai text box berkey terpisah."""
    inner = box.inset(theme.spacing.card_padding_emu)
    text = field_text(block.fields, "text", block_id=block.block_id)
    attribution = field_optional_text(block.fields, "attribution")
    text_style = role_style(theme, "body")
    namespace = f"{slide_id}.{block.block_id}"
    text_height = measure_text(
        text,
        available_width_emu=inner.width,
        theme=theme,
        font_size_pt=text_style.size_pt,
        weight=text_style.weight,
    ).height_emu
    text_height = min(max(1, text_height), inner.height)
    shapes: list[BaseShape] = [
        add_keyed_text(
            slide,
            Box(left=inner.left, top=inner.top, width=inner.width, height=text_height),
            key=f"{namespace}.text",
            text=text,
            style=text_style,
            theme=theme,
        )
    ]
    if attribution:
        attribution_style = body_style(
            theme,
            weight=600,
            color=theme.colors.ink_secondary,
        )
        remaining = inner.height - text_height
        if remaining <= 0:
            raise PptxRenderError(
                f"Block quote '{block.block_id}' tidak menyisakan ruang untuk attribution."
            )
        attribution_height = measure_text(
            attribution,
            available_width_emu=inner.width,
            theme=theme,
            font_size_pt=attribution_style.size_pt,
            weight=attribution_style.weight,
        ).height_emu
        attribution_height = min(max(1, attribution_height), remaining)
        shapes.append(
            add_keyed_text(
                slide,
                Box(
                    left=inner.left,
                    top=inner.top + text_height,
                    width=inner.width,
                    height=attribution_height,
                ),
                key=f"{namespace}.attribution",
                text=attribution,
                style=attribution_style,
                theme=theme,
            )
        )
    return tuple(shapes)


def render_metric_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
) -> tuple[BaseShape, ...]:
    """Render metric label, value, dan caption dengan key masing-masing."""
    inner = box.inset(theme.spacing.card_padding_emu)
    label = field_text(block.fields, "label", block_id=block.block_id)
    value = field_text(block.fields, "value", block_id=block.block_id)
    caption = field_optional_text(block.fields, "caption")
    namespace = f"{slide_id}.{block.block_id}"
    status = block.fields.get("status")
    status_name = status if isinstance(status, str) else "neutral"
    value_style = TextStyle(
        size_pt=max(theme.typography.title_pt, theme.typography.minimum_pt),
        weight=800,
        color=theme.colors.status.get(status_name, theme.colors.ink),
        family=theme.typography.family,
        line_height=theme.typography.line_height,
    )
    label_style = body_style(theme, weight=600, color=theme.colors.ink_secondary)
    caption_style = body_style(theme, weight=400, color=theme.colors.muted)
    parts: list[tuple[str, str, TextStyle]] = [
        ("value", value, value_style),
        ("label", label, label_style),
    ]
    if caption:
        parts.append(("caption", caption, caption_style))
    heights = [
        max(
            1,
            measure_text(
                text,
                available_width_emu=inner.width,
                theme=theme,
                font_size_pt=style.size_pt,
                weight=style.weight,
            ).height_emu,
        )
        for _, text, style in parts
    ]
    total = sum(heights)
    if total > inner.height:
        raise PptxRenderError(
            f"Block metric '{block.block_id}' memerlukan tinggi {total} EMU, "
            f"melebihi kotak {inner.height} EMU."
        )
    top = inner.top
    shapes: list[BaseShape] = []
    for (leaf, text, style), height in zip(parts, heights, strict=True):
        shapes.append(
            add_keyed_text(
                slide,
                Box(left=inner.left, top=top, width=inner.width, height=height),
                key=f"{namespace}.{leaf}",
                text=text,
                style=style,
                theme=theme,
            )
        )
        top += height
    return tuple(shapes)


def render_code_block(
    slide: Slide,
    block: BlockIR,
    box: Box,
    theme: Theme,
    *,
    slide_id: str,
) -> tuple[BaseShape, ...]:
    """Render code literal dan filename opsional sebagai native text box."""
    inner = box.inset(theme.spacing.card_padding_emu)
    code = field_text(block.fields, "code", block_id=block.block_id)
    filename = field_optional_text(block.fields, "filename")
    namespace = f"{slide_id}.{block.block_id}"
    code_text_style = code_style(theme)
    shapes: list[BaseShape] = []
    top = inner.top
    if filename:
        filename_style = body_style(theme, weight=600, color=theme.colors.ink_secondary)
        filename_height = measure_text(
            filename,
            available_width_emu=inner.width,
            theme=theme,
            font_size_pt=filename_style.size_pt,
            weight=filename_style.weight,
        ).height_emu
        filename_height = min(max(1, filename_height), inner.height)
        shapes.append(
            add_keyed_text(
                slide,
                Box(left=inner.left, top=top, width=inner.width, height=filename_height),
                key=f"{namespace}.filename",
                text=filename,
                style=filename_style,
                theme=theme,
            )
        )
        top += filename_height
    remaining = inner.bottom - top
    if remaining <= 0:
        raise PptxRenderError(f"Block code '{block.block_id}' tidak memiliki ruang teks.")
    code_box = Box(left=inner.left, top=top, width=inner.width, height=remaining)
    if bool(block.fields.get("line_numbers", True)):
        line_count = _code_line_count(code)
        gutter_width = _line_number_gutter_width(
            line_count,
            theme=theme,
            available_width_emu=inner.width,
        )
        gutter_gap = theme.spacing.sm_emu
        if gutter_width + gutter_gap >= inner.width:
            raise PptxRenderError(
                f"Block code '{block.block_id}' tidak memiliki lebar untuk gutter nomor baris."
            )
        numbers_box = Box(
            left=inner.left,
            top=top,
            width=gutter_width,
            height=remaining,
        )
        line_number_style = TextStyle(
            size_pt=code_text_style.size_pt,
            weight=400,
            color=theme.colors.muted,
            family=theme.code.family,
            line_height=theme.code.line_height,
        )
        shapes.append(
            add_chrome_text(
                slide,
                numbers_box,
                name=f"code-lines:{namespace}",
                text="\n".join(str(number) for number in range(1, line_count + 1)),
                style=line_number_style,
                theme=theme,
                description=f"Nomor baris {block.block_id}",
                alignment=PP_ALIGN.RIGHT,
            )
        )
        code_box = Box(
            left=inner.left + gutter_width + gutter_gap,
            top=top,
            width=inner.width - gutter_width - gutter_gap,
            height=remaining,
        )
    shapes.append(
        add_keyed_text(
            slide,
            code_box,
            key=f"{namespace}.code",
            text=code,
            style=code_text_style,
            theme=theme,
        )
    )
    return tuple(shapes)


def _code_line_count(code: str) -> int:
    """Hitung baris logis code; baris kosong tetap mendapat nomor."""
    normalized = code.replace("\r\n", "\n").replace("\r", "\n")
    return max(1, len(normalized.split("\n")))


def _line_number_gutter_width(
    line_count: int,
    *,
    theme: Theme,
    available_width_emu: int,
) -> int:
    """Lebar minimum gutter nomor baris dari advance monospace konservatif."""
    widest = str(max(1, line_count))
    measurement = measure_code_text(
        widest,
        available_width_emu=max(1, available_width_emu),
        theme=theme,
    )
    return max(1, measurement.width_emu)


def render_source_text(
    slide: Slide,
    slide_id: str,
    source: Mapping[str, str],
    theme: Theme,
) -> BaseShape:
    """Render ``source.text`` di dalam margin bawah yang disediakan token."""
    text = source.get("text", "")
    if not text:
        raise PptxRenderError(f"Slide '{slide_id}' memiliki source tanpa teks.")
    margin = max(theme.grid.margin_bottom_emu, theme.spacing.md_emu)
    box = Box(
        left=theme.grid.margin_left_emu,
        top=theme.grid.slide_height_emu - margin,
        width=theme.grid.slide_width_emu - theme.grid.margin_left_emu - theme.grid.margin_right_emu,
        height=margin,
    )
    style = role_style(theme, "caption")
    return add_keyed_text(
        slide,
        box,
        key=f"{slide_id}.source.text",
        text=text,
        style=style,
        theme=theme,
        hyperlink=source.get("url"),
    )


def _color_for_role(theme: Theme, role: str) -> str:
    name = _ROLE_COLORS[role]
    if name == "ink":
        return theme.colors.ink
    if name == "ink_secondary":
        return theme.colors.ink_secondary
    if name == "muted":
        return theme.colors.muted
    return theme.colors.accent


def _write_paragraphs(
    text_frame: TextFrame,
    text: str,
    *,
    style: TextStyle,
    theme: Theme,
    bullet: bool,
    ordered: bool,
    bullet_start: int,
    hyperlink: str | None,
    alignment: PP_ALIGN = PP_ALIGN.LEFT,
) -> None:
    text_frame.clear()  # type: ignore[no-untyped-call]
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    for index, line in enumerate(lines):
        paragraph = (
            text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()  # type: ignore[no-untyped-call]
        )
        paragraph.text = line
        apply_paragraph_style(
            paragraph,
            line_height=style.line_height,
            font_size_pt=style.size_pt,
            alignment=alignment,
        )
        if bullet:
            _set_bullet(
                paragraph,
                indent_emu=theme.spacing.md_emu,
                ordered=ordered,
                start_at=bullet_start + index,
            )
        for run in paragraph.runs:
            apply_run_style(
                run,
                family=style.family,
                size_pt=style.size_pt,
                weight=style.weight,
                color=style.color,
                tracking_em=theme.typography.tracking_em,
            )
            if hyperlink:
                run.hyperlink.address = hyperlink


def _set_bullet(
    paragraph: _Paragraph,
    *,
    indent_emu: int,
    ordered: bool,
    start_at: int,
) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_pr.set("marL", str(indent_emu))
    p_pr.set("indent", str(-indent_emu))
    font = OxmlElement("a:buFont")
    font.set("typeface", "Arial")
    p_pr.insert_element_before(font, "a:tabLst", "a:defRPr", "a:extLst")
    if ordered:
        command = OxmlElement("a:buAutoNum")
        command.set("type", "arabicPeriod")
        command.set("startAt", str(max(1, start_at)))
    else:
        command = OxmlElement("a:buChar")
        command.set("char", "\u2022")
    p_pr.insert_element_before(command, "a:tabLst", "a:defRPr", "a:extLst")
