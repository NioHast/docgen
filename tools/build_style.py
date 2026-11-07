#!/usr/bin/env python3
"""Generate reference.docx untuk pandoc dari sebuah preset YAML.

Script ini TIDAK membangun DOCX dari nol. reference.docx yang sudah ada
(berisi seluruh definisi style) dipakai sebagai basis: zip-nya dibuka,
``word/styles.xml`` dan ``word/document.xml`` diubah seperlunya, dan semua
berkas lain disalin apa adanya. Dengan cara ini style seperti ImageCaption,
TableCaption, TOCHeading, Heading1, dan style kustom lainnya tetap utuh.

Nilai preset yang diterapkan:
  - margin_*          -> w:pgMar pada setiap w:sectPr (cm/mm/in/pt -> twip)
  - font_size         -> w:sz dan w:szCs (setengah poin)
  - first_line_indent -> w:ind/@w:firstLine pada BodyText dan FirstParagraph
  - line_spacing      -> spasi 1,5 baris (w:line="360" w:lineRule="auto")

Selain itu, generator menerapkan spesifikasi format acuan ke style berikut.
Semua nilai punya default sesuai acuan dan dapat dioverride lewat kunci
preset ``<prefix>_<field>`` (mis. ``heading1_font_size: 11pt``):

  - Normal       : TNR 12 pt, line 360, before/after 0, jc both, firstLine 709
  - Heading1     : TNR 12 pt bold hitam, center, 0/0, line 360, keepNext,
                   keepLines, outlineLvl 0
  - Heading2/3   : TNR 12 pt bold hitam, both, 0/0, line 360, keepNext,
                   hanging 709/709, outlineLvl 1/2
  - TOCHeading   : TNR 12 pt bold, center, 0/0, line 360
  - ImageCaption : TNR 10 pt tegak, center, 0/0, line 240
  - TableCaption : TNR 10 pt tegak, both, 0/0, line 240, keepNext
  - SourceCode   : Courier New 10 pt, line 240, 0/0, tanpa shading, kiri
  - Bibliography : TNR 12 pt, line 360, 0/0, hanging 720 twip
  - Figure       : center, 0/0

Catatan pemetaan yang disengaja:
  - ``line_spacing: 0.75em`` adalah satuan Typst dan tidak punya padanan
    langsung di Word. Supaya konsisten dengan tampilan PDF laporan, DOCX
    selalu memakai spasi 1,5 baris. Nilai em dari preset tidak dikonversi
    secara matematis.
  - ``font_family`` preset umumnya font Typst (mis. "Libertinus Serif") yang
    tidak terpasang di Windows. Word akan menggantinya secara diam-diam
    dengan font lain, sehingga DOCX default memakai "Times New Roman".
    Gunakan ``--font`` bila ingin memilih font DOCX lain secara eksplisit.
    Bila ``--font`` diberikan, kunci ``*_font_family`` per style diabaikan
    (kecuali SourceCode, yang tetap memakai font monospace).

Contoh:
  python tools/build_style.py --preset presets/skripsi-4433.yml \\
      --out /tmp/reference-generated.docx
  python tools/build_style.py --preset presets/skripsi-4433.yml \\
      --out /tmp/reference-generated.docx --font "Cambria"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

CM_TO_TWIP = 566.929  # 1 cm = 566.929 twip
DEFAULT_DOCX_FONT = "Times New Roman"
DOCX_LINE_SPACING = 360  # 1,5 baris; lihat catatan pemetaan di docstring.
SOURCE_CODE_FONT = "Courier New"

STYLE_RE = re.compile(
    r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>.*?</w:style>', re.S
)
RFONTS_RE = re.compile(r"<w:rFonts\b[^>]*/>")
SIZE_RE = re.compile(r"<w:(sz|szCs)\b[^>]*/>")
PGMAR_RE = re.compile(r"<w:pgMar\b[^>]*/>")
W_TAG_RE = re.compile(r"<(/?)(w:[A-Za-z0-9]+)\b([^>]*)>")

# Font monospace tidak ikut diubah oleh --font supaya blok kode tetap
# terbaca sebagai kode.
MONOSPACE_FONTS = {
    "consolas",
    "courier",
    "courier new",
    "dejavu sans mono",
    "lucida console",
    "menlo",
    "monaco",
    "source code pro",
}

DIMENSION_RE = re.compile(
    r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(cm|mm|in|pt)\s*$", re.I
)
FONT_SIZE_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(?:pt)?\s*$", re.I)

# Urutan anak elemen sesuai skema OOXML. Dipakai saat menambah elemen baru
# agar styles.xml tetap valid dan dapat dibaca Word.
CONTAINER_ORDER: dict[str, tuple[str, ...]] = {
    "pPr": (
        "pStyle",
        "keepNext",
        "keepLines",
        "pageBreakBefore",
        "framePr",
        "widowControl",
        "numPr",
        "suppressLineNumbers",
        "pBdr",
        "shd",
        "tabs",
        "suppressAutoHyphens",
        "kinsoku",
        "wordWrap",
        "overflowPunct",
        "topLinePunct",
        "autoSpaceDE",
        "autoSpaceDN",
        "bidi",
        "adjustRightInd",
        "snapToGrid",
        "spacing",
        "ind",
        "contextualSpacing",
        "mirrorIndents",
        "suppressOverlap",
        "jc",
        "textDirection",
        "textAlignment",
        "textboxTightWrap",
        "outlineLvl",
        "divId",
        "cnfStyle",
        "rPr",
        "sectPr",
        "pPrChange",
    ),
    "rPr": (
        "rStyle",
        "rFonts",
        "b",
        "bCs",
        "i",
        "iCs",
        "caps",
        "smallCaps",
        "strike",
        "dstrike",
        "outline",
        "shadow",
        "emboss",
        "imprint",
        "noProof",
        "snapToGrid",
        "vanish",
        "webHidden",
        "color",
        "spacing",
        "w",
        "kern",
        "position",
        "sz",
        "szCs",
        "highlight",
        "u",
        "effect",
        "bdr",
        "shd",
        "fitText",
        "vertAlign",
        "rtl",
        "cs",
        "em",
        "lang",
        "eastAsianLayout",
        "specVanish",
        "oMath",
    ),
}

# Default spesifikasi format acuan. Setiap field dapat dioverride lewat
# preset memakai kunci ``<prefix>_<field>``.
STYLE_SPEC_DEFAULTS: dict[str, dict[str, object]] = {
    "Normal": {
        "prefix": "normal",
        "font_family": DEFAULT_DOCX_FONT,
        "font_size": "12pt",
        "line_spacing": 360,
        "space_before": "0pt",
        "space_after": "0pt",
        "alignment": "both",
        "first_line_indent": "1.25cm",
    },
    "Heading1": {
        "prefix": "heading1",
        "font_family": DEFAULT_DOCX_FONT,
        "font_size": "12pt",
        "bold": True,
        "color": "000000",
        "alignment": "center",
        "space_before": "0pt",
        "space_after": "0pt",
        "line_spacing": 360,
        "keep_next": True,
        "keep_lines": True,
        "outline_level": 0,
        "first_line_indent": "0cm",
    },
    "Heading2": {
        "prefix": "heading2",
        "font_family": DEFAULT_DOCX_FONT,
        "font_size": "12pt",
        "bold": True,
        "color": "000000",
        "alignment": "both",
        "space_before": "0pt",
        "space_after": "0pt",
        "line_spacing": 360,
        "keep_next": True,
        "keep_lines": True,
        "outline_level": 1,
        "indent_left": "1.25cm",
        "indent_hanging": "1.25cm",
    },
    "Heading3": {
        "prefix": "heading3",
        "font_family": DEFAULT_DOCX_FONT,
        "font_size": "12pt",
        "bold": True,
        "color": "000000",
        "alignment": "both",
        "space_before": "0pt",
        "space_after": "0pt",
        "line_spacing": 360,
        "keep_next": True,
        "keep_lines": True,
        "outline_level": 2,
        "indent_left": "1.25cm",
        "indent_hanging": "1.25cm",
    },
    "TOCHeading": {
        "prefix": "toc_heading",
        "font_family": DEFAULT_DOCX_FONT,
        "font_size": "12pt",
        "bold": True,
        "color": "000000",
        "alignment": "center",
        "space_before": "0pt",
        "space_after": "0pt",
        "line_spacing": 360,
        "first_line_indent": "0cm",
    },
    "ImageCaption": {
        "prefix": "image_caption",
        "font_family": DEFAULT_DOCX_FONT,
        "font_size": "10pt",
        "bold": False,
        "italic": False,
        "alignment": "center",
        "space_before": "0pt",
        "space_after": "0pt",
        "line_spacing": 240,
    },
    "TableCaption": {
        "prefix": "table_caption",
        "font_family": DEFAULT_DOCX_FONT,
        "font_size": "10pt",
        "bold": False,
        "italic": False,
        "alignment": "both",
        "space_before": "0pt",
        "space_after": "0pt",
        "line_spacing": 240,
        "keep_next": True,
    },
    "SourceCode": {
        "prefix": "source_code",
        "font_family": SOURCE_CODE_FONT,
        "font_size": "10pt",
        "line_spacing": 240,
        "space_before": "0pt",
        "space_after": "0pt",
        "shading": "none",
        "alignment": "left",
    },
    "Bibliography": {
        "prefix": "bibliography",
        "font_family": DEFAULT_DOCX_FONT,
        "font_size": "12pt",
        "line_spacing": 360,
        "space_before": "0pt",
        "space_after": "0pt",
        "indent_left": "1.27cm",
        "indent_hanging": "1.27cm",
    },
    "Figure": {
        "prefix": "figure",
        "alignment": "center",
        "space_before": "0pt",
        "space_after": "0pt",
        "first_line_indent": "0cm",
    },
}


def load_preset(path: Path) -> dict[str, str]:
    """Baca preset YAML. PyYAML dipakai bila tersedia; jika tidak, fallback
    ke parser skalar datar tanpa dependensi tambahan."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return parse_flat_yaml(path)

    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:  # type: ignore[attr-defined]
        raise ValueError(f"YAML preset tidak valid: {path}\n{exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Preset harus berupa mapping YAML: {path}")
    return {str(key): "" if value is None else str(value) for key, value in data.items()}


def parse_flat_yaml(path: Path) -> dict[str, str]:
    """Parser minimal untuk ``key: value`` datar (fallback tanpa PyYAML)."""
    data: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("- "):
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if value[:1] in ("'", '"'):
                quote = value[0]
                end = value.find(quote, 1)
                if end == -1:
                    raise ValueError(
                        f"Kutip tidak ditutup pada {path}:{line_number}"
                    )
                value = value[1:end]
            else:
                value = value.split("#", 1)[0].strip()
            data[key] = value
    return data


def xml_attr(value: object) -> str:
    """Escape nilai untuk atribut XML."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def set_tag_attrs(tag: str, attrs: dict[str, object]) -> str:
    """Ganti/tambah/hapus atribut ``w:*`` pada satu elemen XML.

    Nilai ``None`` berarti atribut dihapus bila ada.
    """
    for name, value in attrs.items():
        pattern = re.compile(rf'(\s+w:{re.escape(name)}=")[^"]*(")')
        if value is None:
            tag = pattern.sub("", tag, count=1)
            continue
        if pattern.search(tag):
            tag = pattern.sub(
                lambda match: f"{match.group(1)}{xml_attr(value)}{match.group(2)}",
                tag,
                count=1,
            )
            continue
        stripped = tag.rstrip()
        if stripped.endswith("/>"):
            tag = stripped[:-2].rstrip() + f' w:{name}="{xml_attr(value)}"/>'
        elif stripped.endswith(">"):
            tag = stripped[:-1].rstrip() + f' w:{name}="{xml_attr(value)}">'
        else:
            raise ValueError(f"Elemen bukan tag XML yang valid: {tag[:80]}")
    return tag


def dimension_to_twips(value: str, field: str) -> int:
    text = str(value).strip()
    if re.fullmatch(r"0(?:\.0+)?", text):
        return 0
    match = DIMENSION_RE.match(text)
    if not match:
        raise ValueError(
            f"Nilai {field} '{value}' tidak valid. Gunakan satuan cm, mm, in, atau pt."
        )
    number = float(match.group(1))
    unit = match.group(2).lower()
    factor = {
        "cm": CM_TO_TWIP,
        "mm": CM_TO_TWIP / 10.0,
        "in": 1440.0,
        "pt": 20.0,
    }[unit]
    return int(round(number * factor))


def font_size_to_half_points(value: str, field: str = "font_size") -> int:
    match = FONT_SIZE_RE.match(str(value))
    if not match:
        raise ValueError(
            f"Nilai {field} '{value}' tidak valid. Contoh yang benar: 12pt."
        )
    half_points = int(round(float(match.group(1)) * 2))
    if half_points <= 0:
        raise ValueError(f"{field} harus lebih besar dari nol: '{value}'")
    return half_points


def parse_bool(value: object, field: str) -> bool:
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Nilai {field} '{value}' bukan boolean yang valid")


def parse_line_spacing(value: object, field: str) -> int:
    text = str(value).strip()
    if re.fullmatch(r"[0-9]+", text):
        return int(text)
    try:
        multiple = float(text)
    except ValueError as exc:
        raise ValueError(
            f"Nilai {field} '{value}' tidak valid. Gunakan twip (mis. 360) "
            "atau kelipatan baris (mis. 1.5)."
        ) from exc
    if multiple <= 0:
        raise ValueError(f"Nilai {field} harus lebih besar dari nol: '{value}'")
    return int(round(multiple * 240))


def parse_alignment(value: object, field: str) -> str:
    text = str(value).strip().lower()
    text = {"justify": "both", "justified": "both"}.get(text, text)
    if text not in {"both", "center", "left", "right", "distribute"}:
        raise ValueError(f"Nilai {field} '{value}' bukan alignment yang valid")
    return text


def parse_color(value: object, field: str) -> str:
    text = str(value).strip().lstrip("#").upper()
    if text == "AUTO":
        return "auto"
    if not re.fullmatch(r"[0-9A-F]{6}", text):
        raise ValueError(
            f"Nilai {field} '{value}' bukan warna heksadesimal 6 digit"
        )
    return text


def parse_outline_level(value: object, field: str) -> int:
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+", text):
        raise ValueError(f"Nilai {field} '{value}' bukan level outline yang valid")
    level = int(text)
    if level > 9:
        raise ValueError(f"Nilai {field} harus antara 0 dan 9: '{value}'")
    return level


def parse_shading(value: object, field: str) -> str:
    text = str(value).strip().lower()
    if text in {"", "none", "off", "false"}:
        return "none"
    return parse_color(text, field)


def normalize_spec_field(style_id: str, field: str, value: object) -> object:
    """Normalisasi satu nilai style dari preset/default ke tipe internal."""
    label = f"{style_id}.{field}"
    if field == "font_family":
        text = str(value).strip()
        if not text:
            raise ValueError(f"Nilai {label} tidak boleh kosong")
        return text
    if field == "font_size":
        return font_size_to_half_points(str(value), label)
    if field in {"bold", "italic", "keep_next", "keep_lines"}:
        return parse_bool(value, label)
    if field == "color":
        return parse_color(value, label)
    if field == "alignment":
        return parse_alignment(value, label)
    if field in {
        "space_before",
        "space_after",
        "first_line_indent",
        "indent_left",
        "indent_hanging",
    }:
        return dimension_to_twips(str(value), label)
    if field == "line_spacing":
        return parse_line_spacing(value, label)
    if field == "outline_level":
        return parse_outline_level(value, label)
    if field == "shading":
        return parse_shading(value, label)
    raise ValueError(f"Field style tidak dikenal: {field}")


def resolve_style_specs(preset: dict[str, str]) -> dict[str, dict[str, object]]:
    """Gabungkan default acuan dengan override ``<prefix>_<field>`` preset."""
    resolved: dict[str, dict[str, object]] = {}
    for style_id, defaults in STYLE_SPEC_DEFAULTS.items():
        prefix = str(defaults["prefix"])
        spec: dict[str, object] = {}
        for field, default in defaults.items():
            if field == "prefix":
                continue
            raw = preset.get(f"{prefix}_{field}", default)
            spec[field] = normalize_spec_field(style_id, field, raw)
        resolved[style_id] = spec
    return resolved


def find_style(styles_xml: str, style_id: str) -> re.Match[str]:
    match = STYLE_RE.search(styles_xml)
    while match:
        if match.group(1) == style_id:
            return match
        match = STYLE_RE.search(styles_xml, match.end())
    raise ValueError(f"Style '{style_id}' tidak ditemukan di reference.docx")


def iter_top_level_spans(inner: str):
    """Hasilkan (start, end, tag) untuk elemen top-level di dalam container."""
    depth = 0
    start: int | None = None
    tag: str | None = None

    for match in W_TAG_RE.finditer(inner):
        closing = match.group(1) == "/"
        tag_name = match.group(2).split(":", 1)[1]
        self_closing = (not closing) and match.group(3).rstrip().endswith("/")

        if closing:
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start is not None and tag is not None:
                yield start, match.end(), tag
                start = None
                tag = None
            continue

        if depth == 0:
            start = match.start()
            tag = tag_name
            if self_closing:
                yield start, match.end(), tag
                start = None
                tag = None
            else:
                depth = 1
        elif not self_closing:
            depth += 1


def find_top_level_span(inner: str, tag: str) -> tuple[int, int] | None:
    for start, end, name in iter_top_level_spans(inner):
        if name == tag:
            return start, end
    return None


def remove_top_level_child(inner: str, tag: str) -> str:
    spans = [
        (start, end)
        for start, end, name in iter_top_level_spans(inner)
        if name == tag
    ]
    for start, end in reversed(spans):
        inner = inner[:start] + inner[end:]
    return inner


def reorder_container_children(inner: str, container: str) -> str:
    """Urutkan anak container sesuai skema agar Word menerimanya."""
    order = CONTAINER_ORDER.get(container)
    if not order:
        return inner
    spans = list(iter_top_level_spans(inner))
    if len(spans) < 2:
        return inner

    chunks: list[dict[str, object]] = []
    last = 0
    for position, (start, end, tag) in enumerate(spans):
        chunks.append(
            {
                "tag": tag,
                "leading": inner[last:start],
                "xml": inner[start:end],
                "position": position,
            }
        )
        last = end
    tail = inner[last:]

    order_index = {tag: index for index, tag in enumerate(order)}
    chunks.sort(
        key=lambda chunk: (
            order_index.get(str(chunk["tag"]), len(order)),
            int(chunk["position"]),
        )
    )
    return (
        "".join(f"{chunk['leading']}{chunk['xml']}" for chunk in chunks) + tail
    )


def find_container_span(
    style_block: str, container: str
) -> tuple[int, int, int] | None:
    pattern = re.compile(rf"<w:{re.escape(container)}(?:\s[^>]*)?>")
    match = pattern.search(style_block)
    if not match:
        return None
    if match.group(0).rstrip().endswith("/>"):
        return match.start(), match.end(), match.end()
    close = style_block.find(f"</w:{container}>", match.end())
    if close == -1:
        raise ValueError(f"</w:{container}> tidak ditemukan pada style")
    return match.start(), match.end(), close


def ensure_container(
    style_block: str, container: str
) -> tuple[str, tuple[int, int, int]]:
    span = find_container_span(style_block, container)
    if span is not None:
        return style_block, span

    if container == "pPr":
        rpr_span = find_container_span(style_block, "rPr")
        insert_at = (
            rpr_span[0]
            if rpr_span is not None
            else style_block.rfind("</w:style>")
        )
    else:
        insert_at = style_block.rfind("</w:style>")
    if insert_at == -1:
        raise ValueError("</w:style> tidak ditemukan")

    new_container = f"<w:{container}>\n  </w:{container}>\n"
    style_block = style_block[:insert_at] + new_container + style_block[insert_at:]
    span = find_container_span(style_block, container)
    if span is None:  # pragma: no cover - tidak mungkin bila insert berhasil
        raise ValueError(f"Gagal membuat <w:{container}>")
    return style_block, span


def patch_container(
    style_block: str,
    container: str,
    updates: list[tuple[str, dict[str, object]]],
    drops: tuple[str, ...] = (),
) -> str:
    """Ubah elemen anak di dalam ``<w:pPr>`` atau ``<w:rPr>``."""
    style_block, (_, inner_start, inner_end) = ensure_container(
        style_block, container
    )
    inner = style_block[inner_start:inner_end]

    for tag in drops:
        inner = remove_top_level_child(inner, tag)

    for child_tag, attrs in updates:
        span = find_top_level_span(inner, child_tag)
        if span is None:
            new_tag = set_tag_attrs(f"<w:{child_tag}/>", attrs)
            inner = inner.rstrip() + "\n    " + new_tag
            continue
        start, end = span
        replacement = set_tag_attrs(inner[start:end], attrs)
        inner = inner[:start] + replacement + inner[end:]

    inner = reorder_container_children(inner, container)
    return style_block[:inner_start] + inner + style_block[inner_end:]


def patch_style(
    styles_xml: str,
    style_id: str,
    *,
    ppr: list[tuple[str, dict[str, object]]] | None = None,
    rpr: list[tuple[str, dict[str, object]]] | None = None,
    ppr_drops: tuple[str, ...] = (),
    rpr_drops: tuple[str, ...] = (),
) -> str:
    match = find_style(styles_xml, style_id)
    block = match.group(0)
    if ppr or ppr_drops:
        block = patch_container(block, "pPr", ppr or [], ppr_drops)
    if rpr or rpr_drops:
        block = patch_container(block, "rPr", rpr or [], rpr_drops)
    return styles_xml[: match.start()] + block + styles_xml[match.end() :]


def build_style_patch(
    spec: dict[str, object],
) -> tuple[
    list[tuple[str, dict[str, object]]],
    list[tuple[str, dict[str, object]]],
    tuple[str, ...],
    tuple[str, ...],
]:
    """Terjemahkan satu spec hasil resolve menjadi update pPr/rPr."""
    ppr: list[tuple[str, dict[str, object]]] = []
    rpr: list[tuple[str, dict[str, object]]] = []
    ppr_drops: list[str] = []
    rpr_drops: list[str] = []

    spacing_attrs: dict[str, object] = {}
    if "space_before" in spec:
        spacing_attrs["before"] = spec["space_before"]
    if "space_after" in spec:
        spacing_attrs["after"] = spec["space_after"]
    if "line_spacing" in spec:
        spacing_attrs["line"] = spec["line_spacing"]
        spacing_attrs["lineRule"] = "auto"
    if spacing_attrs:
        ppr.append(("spacing", spacing_attrs))

    ind_attrs: dict[str, object] = {}
    if "first_line_indent" in spec:
        ind_attrs["firstLine"] = spec["first_line_indent"]
    if "indent_left" in spec:
        ind_attrs["left"] = spec["indent_left"]
    if "indent_hanging" in spec:
        ind_attrs["hanging"] = spec["indent_hanging"]
        if "first_line_indent" not in spec:
            # Hanging indent tidak boleh bertabrakan dengan firstLine warisan.
            ind_attrs["firstLine"] = None
    if ind_attrs:
        ppr.append(("ind", ind_attrs))

    if "alignment" in spec:
        ppr.append(("jc", {"val": spec["alignment"]}))

    for field, tag in (("keep_next", "keepNext"), ("keep_lines", "keepLines")):
        if field in spec:
            ppr.append(
                (tag, {"val": None} if spec[field] else {"val": "0"})
            )

    if "outline_level" in spec:
        ppr.append(("outlineLvl", {"val": spec["outline_level"]}))

    if "font_family" in spec:
        family = spec["font_family"]
        rpr.append(
            ("rFonts", {"ascii": family, "hAnsi": family, "cs": family})
        )

    for field, tag in (("bold", "b"), ("italic", "i")):
        if field in spec:
            toggle = {"val": None} if spec[field] else {"val": "0"}
            rpr.append((tag, dict(toggle)))
            rpr.append((f"{tag}Cs", dict(toggle)))

    if "color" in spec:
        rpr.append(("color", {"val": spec["color"]}))

    if "font_size" in spec:
        size = spec["font_size"]
        rpr.append(("sz", {"val": size}))
        rpr.append(("szCs", {"val": size}))

    if "shading" in spec:
        if spec["shading"] == "none":
            ppr_drops.append("shd")
            rpr_drops.append("shd")
        else:
            rpr.append(
                (
                    "shd",
                    {
                        "val": "clear",
                        "color": "auto",
                        "fill": spec["shading"],
                    },
                )
            )

    return ppr, rpr, tuple(ppr_drops), tuple(rpr_drops)


def apply_style_specs(
    styles_xml: str,
    specs: dict[str, dict[str, object]],
    *,
    apply_font_family: bool,
) -> str:
    """Terapkan seluruh spec style; font per style opsional agar --font menang."""
    for style_id, spec in specs.items():
        active = spec
        if not apply_font_family and style_id != "SourceCode":
            active = {
                key: value
                for key, value in spec.items()
                if key != "font_family"
            }
        ppr, rpr, ppr_drops, rpr_drops = build_style_patch(active)
        styles_xml = patch_style(
            styles_xml,
            style_id,
            ppr=ppr,
            rpr=rpr,
            ppr_drops=ppr_drops,
            rpr_drops=rpr_drops,
        )
    return styles_xml


def current_normal_size(styles_xml: str) -> int | None:
    match = find_style(styles_xml, "Normal")
    size_match = re.search(
        r'<w:sz\b[^>]*w:val="([0-9]+)"', match.group(0)
    )
    return int(size_match.group(1)) if size_match else None


def apply_font(styles_xml: str, font: str) -> str:
    """Terapkan font ke semua rFonts eksplisit, kecuali font monospace."""

    def replace_rfonts(match: re.Match[str]) -> str:
        tag = match.group(0)
        ascii_match = re.search(r'w:ascii="([^"]*)"', tag)
        if ascii_match and ascii_match.group(1).lower() in MONOSPACE_FONTS:
            return tag
        if not ascii_match:
            # Jangan sentuh rFonts berbasis theme (mis. rFonts majorHAnsi)
            # yang tidak punya font eksplisit.
            return tag
        return set_tag_attrs(tag, {"ascii": font, "hAnsi": font, "cs": font})

    return RFONTS_RE.sub(replace_rfonts, styles_xml)


def apply_body_font_size(
    styles_xml: str, old_half_points: int, new_half_points: int
) -> str:
    """Ganti ukuran font yang semula sama dengan ukuran Normal.

    Beberapa style di reference.docx (BodyText, FirstParagraph, Compact,
    caption, TOC, dst.) menduplikasi ukuran Normal secara eksplisit. Tanpa
    propagasi ini, perubahan font_size preset tidak akan terlihat pada teks
    isi karena style tersebut menimpa Normal. Heading yang memang lebih
    besar (mis. Heading1 14pt) tidak ikut berubah.
    """

    def replace_size(match: re.Match[str]) -> str:
        tag = match.group(0)
        value_match = re.search(r'w:val="([0-9]+)"', tag)
        if value_match and int(value_match.group(1)) == old_half_points:
            return set_tag_attrs(tag, {"val": str(new_half_points)})
        return tag

    return SIZE_RE.sub(replace_size, styles_xml)


def apply_margins(document_xml: str, margins: dict[str, int]) -> str:
    if not PGMAR_RE.search(document_xml):
        raise ValueError("w:pgMar tidak ditemukan di word/document.xml")

    attrs = {
        "top": margins["margin_top"],
        "right": margins["margin_right"],
        "bottom": margins["margin_bottom"],
        "left": margins["margin_left"],
    }
    return PGMAR_RE.sub(lambda match: set_tag_attrs(match.group(0), attrs), document_xml)


def ensure_character_style(
    styles_xml: str, style_id: str, name: str, rpr_inner: str
) -> tuple[str, bool]:
    if re.search(
        rf'<w:style\b[^>]*w:styleId="{re.escape(style_id)}"', styles_xml
    ):
        return styles_xml, False

    style = (
        f'<w:style w:type="character" w:customStyle="1" w:styleId="{style_id}">\n'
        f'  <w:name w:val="{name}"/>\n'
        f'  <w:basedOn w:val="DefaultParagraphFont"/>\n'
        f"  <w:rPr>\n"
        f"    {rpr_inner}\n"
        f"  </w:rPr>\n"
        f"</w:style>\n"
    )
    closing = styles_xml.rfind("</w:styles>")
    if closing == -1:
        raise ValueError("</w:styles> tidak ditemukan")
    return styles_xml[:closing] + style + styles_xml[closing:], True


def rewrite_docx(
    base_docx: Path,
    out_docx: Path,
    styles_xml: str,
    document_xml: str,
) -> None:
    out_docx.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=out_docx.name + ".", suffix=".tmp", dir=str(out_docx.parent)
    )
    os.close(fd)
    try:
        with zipfile.ZipFile(base_docx, "r") as source:
            names = set(source.namelist())
            for required in ("word/styles.xml", "word/document.xml"):
                if required not in names:
                    raise ValueError(
                        f"Basis '{base_docx}' tidak memiliki {required}; "
                        "bukan reference.docx yang valid."
                    )
            with zipfile.ZipFile(temp_name, "w") as target:
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename == "word/styles.xml":
                        data = styles_xml.encode("utf-8")
                    elif item.filename == "word/document.xml":
                        data = document_xml.encode("utf-8")
                    target.writestr(item, data)
        os.replace(temp_name, out_docx)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate reference.docx untuk pandoc dari preset YAML."
    )
    parser.add_argument("--preset", required=True, help="Path ke preset .yml")
    parser.add_argument("--out", required=True, help="Path reference.docx hasil generate")
    parser.add_argument(
        "--font",
        default=None,
        help="Font DOCX eksplisit (default: Times New Roman; font_family preset diabaikan)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    preset_path = Path(args.preset)
    out_path = Path(args.out)
    base_docx = Path(__file__).resolve().parent.parent / "reference.docx"

    if not preset_path.is_file():
        print(f"ERROR: preset tidak ditemukan: {preset_path}", file=sys.stderr)
        return 1
    if not base_docx.is_file():
        print(
            f"ERROR: basis reference.docx tidak ditemukan: {base_docx}",
            file=sys.stderr,
        )
        return 1

    try:
        preset = load_preset(preset_path)

        for field in ("margin_top", "margin_bottom", "margin_left", "margin_right"):
            if not preset.get(field):
                raise ValueError(f"Preset '{preset_path}' tidak memiliki '{field}'")
        margins = {
            field: dimension_to_twips(preset[field], field)
            for field in ("margin_top", "margin_bottom", "margin_left", "margin_right")
        }

        font = (args.font or "").strip() or DEFAULT_DOCX_FONT
        preset_font = preset.get("font_family", "").strip()
        explicit_font = bool((args.font or "").strip())

        with zipfile.ZipFile(base_docx, "r") as archive:
            styles_xml = archive.read("word/styles.xml").decode("utf-8")
            document_xml = archive.read("word/document.xml").decode("utf-8")

        style_count_before = len(STYLE_RE.findall(styles_xml))
        styles_xml = apply_font(styles_xml, font)

        font_size = preset.get("font_size")
        new_half_points = None
        if font_size:
            old_half_points = current_normal_size(styles_xml)
            new_half_points = font_size_to_half_points(font_size)
            if old_half_points is None:
                raise ValueError("Ukuran font Normal tidak ditemukan di styles.xml")
            styles_xml = apply_body_font_size(
                styles_xml, old_half_points, new_half_points
            )

        if preset.get("line_spacing"):
            # Disengaja: 0.75em (Typst) tidak dikonversi langsung; DOCX
            # memakai spasi 1,5 baris agar konsisten dengan PDF.
            spacing = {"line": DOCX_LINE_SPACING, "lineRule": "auto"}
            for style_id in ("Normal", "BodyText", "FirstParagraph"):
                styles_xml = patch_style(
                    styles_xml, style_id, ppr=[("spacing", spacing)]
                )

        indent_twips = None
        if preset.get("first_line_indent"):
            indent_twips = dimension_to_twips(
                preset["first_line_indent"], "first_line_indent"
            )
            for style_id in ("BodyText", "FirstParagraph"):
                styles_xml = patch_style(
                    styles_xml,
                    style_id,
                    ppr=[("ind", {"firstLine": indent_twips})],
                )

        style_specs = resolve_style_specs(preset)
        styles_xml = apply_style_specs(
            styles_xml,
            style_specs,
            apply_font_family=not explicit_font,
        )

        document_xml = apply_margins(document_xml, margins)

        styles_xml, added_isng = ensure_character_style(
            styles_xml,
            "IstilahAsing",
            "Istilah Asing",
            '<w:i/><w:lang w:val="en-US"/>',
        )
        styles_xml, added_review = ensure_character_style(
            styles_xml,
            "IstilahReview",
            "Istilah Review",
            '<w:highlight w:val="yellow"/>',
        )

        style_count_after = len(STYLE_RE.findall(styles_xml))
        expected_added = int(added_isng) + int(added_review)
        if style_count_after != style_count_before + expected_added:
            raise ValueError(
                "Jumlah style berubah tidak wajar: "
                f"{style_count_before} -> {style_count_after}"
            )

        # Pastikan XML yang ditulis tetap well-formed.
        ElementTree.fromstring(styles_xml.encode("utf-8"))
        ElementTree.fromstring(document_xml.encode("utf-8"))

        rewrite_docx(base_docx, out_path, styles_xml, document_xml)
    except (ValueError, OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        print(f"ERROR: gagal membuat reference.docx: {exc}", file=sys.stderr)
        return 1

    if preset_font and not explicit_font:
        print(
            f"[INFO] font_family preset '{preset_font}' diabaikan untuk DOCX; "
            f"memakai '{font}'. Gunakan --font untuk override."
        )
    print(f"[OK] reference.docx digenerate: {out_path}")
    print(
        "     margin (twip): "
        f"top={margins['margin_top']} right={margins['margin_right']} "
        f"bottom={margins['margin_bottom']} left={margins['margin_left']}"
    )
    print(
        "     margin (cm): "
        f"top={margins['margin_top'] / CM_TO_TWIP:.2f} "
        f"right={margins['margin_right'] / CM_TO_TWIP:.2f} "
        f"bottom={margins['margin_bottom'] / CM_TO_TWIP:.2f} "
        f"left={margins['margin_left'] / CM_TO_TWIP:.2f}"
    )
    print(f"     font: {font}")
    if new_half_points is not None:
        print(
            f"     font_size: {new_half_points} half-points "
            f"({new_half_points / 2:g} pt)"
        )
    if indent_twips is not None:
        print(f"     first_line_indent: {indent_twips} twip")
    print(
        "     style acuan: "
        + ", ".join(style_specs)
        + " (dapat dioverride lewat preset)"
    )
    print(
        "     style: "
        f"{style_count_before} -> {style_count_after} "
        "(IstilahAsing/IstilahReview ditambahkan bila belum ada)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
