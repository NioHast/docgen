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

Catatan pemetaan yang disengaja:
  - ``line_spacing: 0.75em`` adalah satuan Typst dan tidak punya padanan
    langsung di Word. Supaya konsisten dengan tampilan PDF laporan, DOCX
    selalu memakai spasi 1,5 baris. Nilai em dari preset tidak dikonversi
    secara matematis.
  - ``font_family`` preset umumnya font Typst (mis. "Libertinus Serif") yang
    tidak terpasang di Windows. Word akan menggantinya secara diam-diam
    dengan font lain, sehingga DOCX default memakai "Times New Roman".
    Gunakan ``--font`` bila ingin memilih font DOCX lain secara eksplisit.

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

STYLE_RE = re.compile(
    r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>.*?</w:style>', re.S
)
RFONTS_RE = re.compile(r"<w:rFonts\b[^>]*/>")
SIZE_RE = re.compile(r"<w:(sz|szCs)\b[^>]*/>")
PGMAR_RE = re.compile(r"<w:pgMar\b[^>]*/>")

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
    """Ganti/tambah atribut ``w:*`` pada satu elemen XML self-closing."""
    for name, value in attrs.items():
        pattern = re.compile(rf'(\bw:{re.escape(name)}=")[^"]*(")')
        if pattern.search(tag):
            tag = pattern.sub(
                lambda match: f"{match.group(1)}{xml_attr(value)}{match.group(2)}",
                tag,
                count=1,
            )
        else:
            tag = tag.rstrip()
            if not tag.endswith("/>"):
                raise ValueError(f"Elemen bukan self-closing: {tag[:80]}")
            tag = tag[:-2].rstrip() + f' w:{name}="{xml_attr(value)}"/>'
    return tag


def dimension_to_twips(value: str, field: str) -> int:
    match = DIMENSION_RE.match(value)
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


def font_size_to_half_points(value: str) -> int:
    match = FONT_SIZE_RE.match(value)
    if not match:
        raise ValueError(
            f"Nilai font_size '{value}' tidak valid. Contoh yang benar: 12pt."
        )
    half_points = int(round(float(match.group(1)) * 2))
    if half_points <= 0:
        raise ValueError(f"font_size harus lebih besar dari nol: '{value}'")
    return half_points


def find_style(styles_xml: str, style_id: str) -> re.Match[str]:
    match = STYLE_RE.search(styles_xml)
    while match:
        if match.group(1) == style_id:
            return match
        match = STYLE_RE.search(styles_xml, match.end())
    raise ValueError(f"Style '{style_id}' tidak ditemukan di reference.docx")


def patch_container(
    style_block: str,
    container: str,
    updates: list[tuple[str, dict[str, object]]],
) -> str:
    """Ubah elemen anak di dalam ``<w:pPr>`` atau ``<w:rPr>``."""
    open_tag = f"<w:{container}>"
    close_tag = f"</w:{container}>"
    start = style_block.find(open_tag)
    if start == -1:
        raise ValueError(f"<w:{container}> tidak ditemukan pada style")
    start += len(open_tag)
    end = style_block.find(close_tag, start)
    if end == -1:
        raise ValueError(f"</w:{container}> tidak ditemukan pada style")

    inner = style_block[start:end]
    for child_tag, attrs in updates:
        child_re = re.compile(rf"<w:{re.escape(child_tag)}\b[^>]*/>")
        match = child_re.search(inner)
        if match:
            replacement = set_tag_attrs(match.group(0), attrs)
            inner = inner[: match.start()] + replacement + inner[match.end() :]
        else:
            new_tag = set_tag_attrs(f"<w:{child_tag}/>", attrs)
            inner = inner.rstrip() + "\n    " + new_tag

    return style_block[:start] + inner + style_block[end:]


def patch_style(
    styles_xml: str,
    style_id: str,
    *,
    ppr: list[tuple[str, dict[str, object]]] | None = None,
    rpr: list[tuple[str, dict[str, object]]] | None = None,
) -> str:
    match = find_style(styles_xml, style_id)
    block = match.group(0)
    if ppr:
        block = patch_container(block, "pPr", ppr)
    if rpr:
        block = patch_container(block, "rPr", rpr)
    return styles_xml[: match.start()] + block + styles_xml[match.end() :]


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

    if preset_font and not args.font:
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
        "     style: "
        f"{style_count_before} -> {style_count_after} "
        "(IstilahAsing/IstilahReview ditambahkan bila belum ada)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
