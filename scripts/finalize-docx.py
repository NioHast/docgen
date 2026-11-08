#!/usr/bin/env python3
"""Finalisasi document.xml hasil pandoc agar penomoran halaman DOCX
mengikuti kaidah laporan akademik Indonesia:

  - Sampul + pernyataan   : tanpa nomor halaman
  - Front matter          : i, ii, iii ... (lowerRoman, mulai 1), bawah tengah,
                            12 pt, tanpa header
  - Body (BAB I s.d. akhir): 1, 2, 3 ... (decimal, mulai 1), header kanan 10 pt
  - Halaman pertama bab   : nomor lanjut di footer tengah 12 pt, header kosong
                            (setiap section body memakai `w:titlePg`)

Pandoc/docx.lua hanya menyisipkan section break di akhir sampul dan di
setiap awal bab (karena `--top-level-division=chapter`). Script ini:

  1. Menambahkan section break baru tepat sebelum Heading1 body pertama
     (BAB I) bila belum ada, sehingga dokumen memiliki tiga zona.
  2. Menulis ulang setiap `w:sectPr` agar memiliki `w:pgNumType` yang
     sesuai zona dan `w:titlePg` pada setiap section body.
  3. Membuat part header/footer baru yang tidak saling di-link antar
     seksi: footer front matter (PAGE, tengah, 12 pt), header body
     (PAGE, kanan, 10 pt), header first body kosong, footer first body
     (PAGE, tengah, 12 pt), serta footer default body yang kosong secara
     visual. Footer default body tetap memuat field PAGE tersembunyi
     sebagai probe agar `docx-pagenum.py` (yang membaca baris terakhir
     PDF) tetap dapat mengisi nomor halaman daftar isi.
  4. Membersihkan part header/footer lama yang tidak lagi dipakai.

Field PAGE ditulis sebagai field OpenXML asli (fldChar begin/separate/end),
bukan teks biasa, sehingga Word/LibreOffice tetap memperbaruinya.

Usage:
  python3 scripts/finalize-docx.py input.docx output.docx
"""

import os
import re
import sys
import tempfile
import zipfile

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

SECT_RE = re.compile(r"<w:sectPr\b[^>]*>.*?</w:sectPr>", re.S)
PARA_RE = re.compile(r"<w:p\b[^>]*>(?:(?!</w:p>).)*?</w:p>", re.S)
PARA_OPEN_RE = re.compile(r"<w:p\b[^>]*>")
HEADER_FOOTER_REF_RE = re.compile(r"<w:(?:header|footer)Reference\b[^>]*/>")
PGNUM_RE = re.compile(r"<w:pgNumType\b[^>]*/>")
TITLEPG_RE = re.compile(r"<w:titlePg\b[^>]*/>")
SECT_TYPE_RE = re.compile(r"<w:type\b[^>]*/>")

RUN_RE = re.compile(r"<w:r\b[^>]*>.*?</w:r>", re.S)
HYPERLINK_RE = re.compile(r"<w:hyperlink\b[^>]*>.*?</w:hyperlink>", re.S)
STYLE_RE = re.compile(
    r'<w:style\b[^>]*w:styleId="([^"]+)"[^>]*>.*?</w:style>', re.S
)
W_TAG_RE = re.compile(r"<(/?)(w:[A-Za-z0-9]+)\b([^>]*)>")
UPDATE_FIELDS_RE = re.compile(
    r"<w:updateFields\b[^>]*/>|<w:updateFields\b[^>]*>.*?</w:updateFields>",
    re.S,
)
COMPAT_SETTING_RE = re.compile(
    r"<w:compatSetting\b[^>]*/>"
    r"|<w:compatSetting\b[^>]*>.*?</w:compatSetting>",
    re.S,
)
COMPAT_RE = re.compile(
    r"<w:compat\b[^>]*>.*?</w:compat>|<w:compat\b[^>]*/>", re.S
)

# Urutan anak rPr/pPr sesuai skema OOXML agar Word tidak menganggap XML rusak.
RPR_ORDER = (
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
)
PPR_ORDER = (
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
)

CODE_STYLE_IDS = ("SourceCode", "VerbatimChar", "HTMLCode", "HTMLPreformatted")
CODE_STYLE_TYPES = {
    "SourceCode": "paragraph",
    "VerbatimChar": "character",
    "HTMLCode": "character",
    "HTMLPreformatted": "paragraph",
}
CODE_STYLE_NAMES = {
    "SourceCode": "Source Code",
    "VerbatimChar": "Verbatim Char",
    "HTMLCode": "HTML Code",
    "HTMLPreformatted": "HTML Preformatted",
}
CODE_FONT = "Courier New"
CODE_SIZE_HALF_POINTS = 20  # 10 pt
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
COMPAT_MODE_TAG = (
    '<w:compatSetting w:name="compatibilityMode" '
    'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>'
)

# Heading1 yang termasuk front matter. Dipakai sebagai fallback bila tidak
# ada heading "BAB ..." (mis. dokumen tanpa bab bernomor).
FRONT_MATTER_HEADINGS = {
    "LEMBAR PENGESAHAN",
    "HALAMAN PENGESAHAN",
    "HALAMAN PERSETUJUAN",
    "HALAMAN PERSEMBAHAN",
    "PERSEMBAHAN",
    "MOTTO",
    "KATA PENGANTAR",
    "PRAKATA",
    "UCAPAN TERIMA KASIH",
    "ABSTRAK",
    "ABSTRACT",
    "DAFTAR ISI",
    "DAFTAR TABEL",
    "DAFTAR GAMBAR",
    "DAFTAR LAMPIRAN",
    "DAFTAR SINGKATAN",
    "DAFTAR SIMBOL",
}

BODY_CHAPTER_RE = re.compile(r"^BAB\s+(?:[IVXLCDM]+|\d+)\b", re.I)

# Halaman pernyataan/pengesahan berada di zona sampul: tidak diberi nomor.
# Dipakai untuk section terpisah yang hanya berisi heading pernyataan
# (mis. saat metadata `approval` diaktifkan).
NO_NUMBER_HEADING_PREFIXES = (
    "LEMBAR PENGESAHAN",
    "HALAMAN PENGESAHAN",
    "LEMBAR PERSETUJUAN",
    "HALAMAN PERSETUJUAN",
    "LEMBAR PERNYATAAN",
    "HALAMAN PERNYATAAN",
    "PERNYATAAN ",
)

FRONT_FOOTER_SIZE_PT = 12
BODY_HEADER_SIZE_PT = 10
BODY_FOOTER_SIZE_PT = 12

# Urutan elemen CT_SectPr: pgNumType harus berada setelah pgMar dan sebelum
# elemen-elemen berikut.
PGNUM_BEFORE = (
    "cols",
    "formProt",
    "vAlign",
    "noEndnote",
    "titlePg",
    "textDirection",
    "bidi",
    "rtlGutter",
    "docGrid",
    "printerSettings",
)
SECT_TYPE_BEFORE = ("pgSz", "pgMar", "cols", "docGrid")


def para_text(paragraph):
    """Ambil seluruh teks dalam satu paragraf (bisa terdiri dari banyak run)."""
    return " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", paragraph)).strip()


def xml_escape_attr(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def set_tag_attrs(tag, attrs):
    """Ganti/tambah/hapus atribut ``w:*`` pada satu elemen XML."""
    for name, value in attrs.items():
        pattern = re.compile(rf'(\s+w:{re.escape(name)}=")[^"]*(")')
        if value is None:
            tag = pattern.sub("", tag, count=1)
            continue
        if pattern.search(tag):
            tag = pattern.sub(
                lambda match: (
                    f"{match.group(1)}{xml_escape_attr(value)}{match.group(2)}"
                ),
                tag,
                count=1,
            )
            continue
        stripped = tag.rstrip()
        if stripped.endswith("/>"):
            tag = stripped[:-2].rstrip() + f' w:{name}="{xml_escape_attr(value)}"/>'
        elif stripped.endswith(">"):
            tag = stripped[:-1].rstrip() + f' w:{name}="{xml_escape_attr(value)}">'
        else:
            raise ValueError(f"Elemen bukan tag XML yang valid: {tag[:80]}")
    return tag


def iter_top_level_spans(inner):
    """Hasilkan (start, end, tag) untuk elemen top-level dalam container."""
    depth = 0
    start = None
    tag = None

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


def find_top_level_span(inner, tag):
    for start, end, name in iter_top_level_spans(inner):
        if name == tag:
            return start, end
    return None


def remove_top_level_child(inner, tag):
    spans = [
        (start, end)
        for start, end, name in iter_top_level_spans(inner)
        if name == tag
    ]
    for start, end in reversed(spans):
        inner = inner[:start] + inner[end:]
    return inner


def reorder_container_children(inner, container):
    order = RPR_ORDER if container == "rPr" else PPR_ORDER
    order_index = {tag: index for index, tag in enumerate(order)}
    spans = list(iter_top_level_spans(inner))
    if len(spans) < 2:
        return inner

    chunks = []
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

    chunks.sort(
        key=lambda chunk: (
            order_index.get(str(chunk["tag"]), len(order)),
            int(chunk["position"]),
        )
    )
    return "".join(
        f"{chunk['leading']}{chunk['xml']}" for chunk in chunks
    ) + tail


def find_container_span(style_block, container):
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


def ensure_container(style_block, container):
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


def patch_container(style_block, container, updates, drops=()):
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


def patch_style_block(styles_xml, style_id, *, ppr=None, rpr=None,
                      ppr_drops=(), rpr_drops=()):
    match = None
    for candidate in STYLE_RE.finditer(styles_xml):
        if candidate.group(1) == style_id:
            match = candidate
            break
    if match is None:
        return styles_xml, False

    block = match.group(0)
    if ppr or ppr_drops:
        block = patch_container(block, "pPr", ppr or [], ppr_drops)
    if rpr or rpr_drops:
        block = patch_container(block, "rPr", rpr or [], rpr_drops)
    styles_xml = styles_xml[: match.start()] + block + styles_xml[match.end():]
    return styles_xml, True


def style_exists(styles_xml, style_id):
    return bool(
        re.search(
            rf'<w:style\b[^>]*w:styleId="{re.escape(style_id)}"', styles_xml
        )
    )


def ensure_code_style(styles_xml, style_id):
    """Tambahkan definisi style kode yang belum ada di styles.xml."""
    if style_exists(styles_xml, style_id):
        return styles_xml

    name = CODE_STYLE_NAMES[style_id]
    rpr = (
        f'<w:rFonts w:ascii="{CODE_FONT}" w:hAnsi="{CODE_FONT}" '
        f'w:cs="{CODE_FONT}"/>'
        '<w:color w:val="000000"/>'
        f'<w:sz w:val="{CODE_SIZE_HALF_POINTS}"/>'
        f'<w:szCs w:val="{CODE_SIZE_HALF_POINTS}"/>'
    )
    if CODE_STYLE_TYPES[style_id] == "character":
        block = (
            f'<w:style w:type="character" w:customStyle="1" '
            f'w:styleId="{style_id}">\n'
            f'  <w:name w:val="{name}"/>\n'
            '  <w:basedOn w:val="DefaultParagraphFont"/>\n'
            f"  <w:rPr>\n    {rpr}\n  </w:rPr>\n"
            "</w:style>\n"
        )
    else:
        block = (
            f'<w:style w:type="paragraph" w:styleId="{style_id}">\n'
            f'  <w:name w:val="{name}"/>\n'
            '  <w:basedOn w:val="Normal"/>\n'
            "  <w:qFormat/>\n"
            "  <w:pPr>\n"
            '    <w:spacing w:before="0" w:after="0" w:line="240" '
            'w:lineRule="auto"/>\n'
            '    <w:ind w:left="0" w:right="0" w:firstLine="0"/>\n'
            '    <w:jc w:val="left"/>\n'
            "  </w:pPr>\n"
            f"  <w:rPr>\n    {rpr}\n  </w:rPr>\n"
            "</w:style>\n"
        )
    closing = styles_xml.rfind("</w:styles>")
    if closing == -1:
        raise ValueError("</w:styles> tidak ditemukan")
    return styles_xml[:closing] + block + styles_xml[closing:]


def fix_document_styles(styles):
    """Patch style Hyperlink, style kode, dan jarak Heading1-3."""
    for style_id in CODE_STYLE_IDS:
        styles = ensure_code_style(styles, style_id)

    for style_id in CODE_STYLE_IDS:
        is_paragraph = CODE_STYLE_TYPES[style_id] == "paragraph"
        styles, _ = patch_style_block(
            styles,
            style_id,
            rpr=[
                (
                    "rFonts",
                    {
                        "ascii": CODE_FONT,
                        "hAnsi": CODE_FONT,
                        "cs": CODE_FONT,
                        "asciiTheme": None,
                        "hAnsiTheme": None,
                        "cstheme": None,
                        "eastAsiaTheme": None,
                    },
                ),
                (
                    "color",
                    {
                        "val": "000000",
                        "themeColor": None,
                        "themeShade": None,
                        "themeTint": None,
                    },
                ),
                ("sz", {"val": CODE_SIZE_HALF_POINTS}),
                ("szCs", {"val": CODE_SIZE_HALF_POINTS}),
            ],
            rpr_drops=("shd",),
            ppr_drops=("shd",) if is_paragraph else (),
        )

    styles, _ = patch_style_block(
        styles,
        "Hyperlink",
        rpr=[
            (
                "color",
                {
                    "val": "000000",
                    "themeColor": None,
                    "themeShade": None,
                    "themeTint": None,
                },
            ),
            ("u", {"val": "none"}),
        ],
    )

    # Jarak antarsubbab memakai paragraf kosong fisik (insert_blank_lines).
    # Style Heading1/2/3 tidak boleh membawa before/after tambahan.
    for style_id in ("Heading1", "Heading2", "Heading3"):
        styles, _ = patch_style_block(
            styles,
            style_id,
            ppr=[
                (
                    "spacing",
                    {
                        "before": 0,
                        "after": 0,
                        "line": 360,
                        "lineRule": "auto",
                    },
                )
            ],
        )
    return styles


def ensure_run_rpr(run):
    """Pastikan run punya ``<w:rPr>`` dan kembalikan (run, inner, span)."""
    match = re.search(r"<w:rPr(?:\s[^>]*)?>.*?</w:rPr>", run, re.S)
    if match:
        inner_start = match.start() + len(
            re.match(r"<w:rPr(?:\s[^>]*)?>", match.group(0)).group(0)
        )
        inner_end = match.end() - len("</w:rPr>")
        return run, run[inner_start:inner_end], (match.start(), match.end())
    open_match = re.match(r"<w:r\b[^>]*>", run)
    if not open_match:
        return run, None, None
    insert = open_match.end()
    run = run[:insert] + "<w:rPr></w:rPr>" + run[insert:]
    inner_start = insert + len("<w:rPr>")
    inner_end = inner_start
    return run, "", (insert, insert + len("<w:rPr></w:rPr>"))


def patch_run_rpr(run, updates, drops=()):
    run, inner, span = ensure_run_rpr(run)
    if inner is None:
        return run
    for tag in drops:
        inner = remove_top_level_child(inner, tag)
    for child_tag, attrs in updates:
        child_span = find_top_level_span(inner, child_tag)
        if child_span is None:
            inner = inner.rstrip() + set_tag_attrs(
                f"<w:{child_tag}/>", attrs
            )
        else:
            start, end = child_span
            inner = (
                inner[:start]
                + set_tag_attrs(inner[start:end], attrs)
                + inner[end:]
            )
    inner = reorder_container_children(inner, "rPr")
    start, end = span
    rpr_open = re.match(r"<w:rPr(?:\s[^>]*)?>", run[start:end]).group(0)
    return run[:start] + rpr_open + inner + "</w:rPr>" + run[end:]


def is_monospace_run(run):
    for style_id in re.findall(r'<w:rStyle w:val="([^"]+)"/>', run):
        if style_id in CODE_STYLE_IDS:
            return True
    for font_tag in re.findall(r"<w:rFonts\b[^>]*/>", run):
        values = re.findall(
            r'w:(?:ascii|hAnsi|cs|eastAsia)="([^"]*)"', font_tag
        )
        if any(value.strip().lower() in MONOSPACE_FONTS for value in values):
            return True
    return False


def patch_hyperlink_runs(doc):
    def patch_block(match):
        return RUN_RE.sub(
            lambda run: patch_run_rpr(
                run.group(0),
                [
                    (
                        "color",
                        {
                            "val": "000000",
                            "themeColor": None,
                            "themeShade": None,
                            "themeTint": None,
                        },
                    ),
                    ("u", {"val": "none"}),
                ],
            ),
            match.group(0),
        )

    return HYPERLINK_RE.sub(patch_block, doc)


def restore_toc_istilah_style(run):
    """Kembalikan IstilahAsing yang diratakan Word menjadi italic manual.

    Saat memperbarui TOC, Word menyalin format heading sebagai direct
    ``w:i`` + ``w:lang en-US``. ``tools/istilah.py verify`` menganggap itu
    pelanggaran, jadi run TOC seperti ini dikembalikan ke character style
    IstilahAsing.
    """
    match = re.search(r"<w:rPr(?:\s[^>]*)?>.*?</w:rPr>", run, re.S)
    if not match:
        return run
    rpr = match.group(0)
    open_tag = re.match(r"<w:rPr(?:\s[^>]*)?>", rpr).group(0)
    inner = rpr[len(open_tag):-len("</w:rPr>")]
    if re.search(
        r'<w:rStyle w:val="(?:IstilahAsing|IstilahReview)"/>', inner
    ):
        return run
    if not re.search(r"<w:i\b", inner):
        return run
    if not re.search(r'<w:lang\b[^>]*w:val="en-US"', inner):
        return run

    if "<w:rStyle" in inner:
        inner = re.sub(
            r'(<w:rStyle\b[^>]*w:val=")[^"]*(")',
            r"\g<1>IstilahAsing\g<2>",
            inner,
            count=1,
        )
    else:
        inner = '<w:rStyle w:val="IstilahAsing"/>' + inner
    inner = reorder_container_children(inner, "rPr")
    new_rpr = open_tag + inner + "</w:rPr>"
    return run[: match.start()] + new_rpr + run[match.end():]


def restore_toc_istilah_styles(doc):
    def fix_paragraph(match):
        paragraph = match.group(0)
        ppr = re.search(
            r"<w:pPr(?:\s[^>]*)?>.*?</w:pPr>", paragraph, re.S
        )
        if not ppr or not re.search(
            r'<w:pStyle w:val="TOC\d+"/>', ppr.group(0)
        ):
            return paragraph
        return RUN_RE.sub(
            lambda run: restore_toc_istilah_style(run.group(0)), paragraph
        )

    return PARA_RE.sub(fix_paragraph, doc)


def patch_code_run(run):
    return patch_run_rpr(
        run,
        [
            (
                "rFonts",
                {
                    "ascii": CODE_FONT,
                    "hAnsi": CODE_FONT,
                    "cs": CODE_FONT,
                    "asciiTheme": None,
                    "hAnsiTheme": None,
                    "cstheme": None,
                    "eastAsiaTheme": None,
                },
            ),
            (
                "color",
                {
                    "val": "000000",
                    "themeColor": None,
                    "themeShade": None,
                    "themeTint": None,
                },
            ),
            ("sz", {"val": CODE_SIZE_HALF_POINTS}),
            ("szCs", {"val": CODE_SIZE_HALF_POINTS}),
        ],
        drops=("shd",),
    )


def patch_code_paragraph(paragraph):
    ppr = re.search(r"<w:pPr(?:\s[^>]*)?>.*?</w:pPr>", paragraph, re.S)
    if not ppr:
        return paragraph
    style = re.search(r'<w:pStyle w:val="([^"]+)"/>', ppr.group(0))
    if not style or style.group(1) not in CODE_STYLE_IDS:
        return paragraph

    ppr_inner = re.sub(r"<w:shd\b[^>]*/>", "", ppr.group(0))
    paragraph = paragraph[: ppr.start()] + ppr_inner + paragraph[ppr.end():]
    return RUN_RE.sub(lambda m: patch_code_run(m.group(0)), paragraph)


def fix_document_formatting(doc):
    """Bersihkan direct formatting biru Konsolas/DejaVu dari Pandoc/Word."""
    doc = patch_hyperlink_runs(doc)
    doc = restore_toc_istilah_styles(doc)
    doc = PARA_RE.sub(
        lambda match: patch_code_paragraph(match.group(0)), doc
    )
    return RUN_RE.sub(
        lambda match: (
            patch_code_run(match.group(0))
            if is_monospace_run(match.group(0))
            else match.group(0)
        ),
        doc,
    )


def fix_settings(settings):
    """Hapus prompt update field dan paksa Compatibility Mode 15."""
    settings = UPDATE_FIELDS_RE.sub("", settings)

    def drop_compat_mode(match):
        if re.search(r'w:name="compatibilityMode"', match.group(0)):
            return ""
        return match.group(0)

    settings = COMPAT_SETTING_RE.sub(drop_compat_mode, settings)
    match = COMPAT_RE.search(settings)
    if match:
        block = match.group(0)
        if block.rstrip().endswith("/>"):
            new_block = f"<w:compat>{COMPAT_MODE_TAG}</w:compat>"
        else:
            new_block = (
                block[: block.rfind("</w:compat>")]
                + COMPAT_MODE_TAG
                + "</w:compat>"
            )
        settings = settings[: match.start()] + new_block + settings[match.end():]
    else:
        compat = f"<w:compat>{COMPAT_MODE_TAG}</w:compat>"
        insert_at = None
        for tag in ("w:rsids", "w:mathPr", "w:themeFontLang", "w:clrSchemeMapping"):
            position = settings.find(f"<{tag}")
            if position != -1:
                insert_at = position
                break
        if insert_at is None:
            insert_at = settings.rfind("</w:settings>")
        if insert_at == -1:
            raise ValueError("</w:settings> tidak ditemukan")
        settings = settings[:insert_at] + compat + settings[insert_at:]

    return settings


def heading1_paragraphs(doc):
    """Kembalikan daftar (start, end, text) untuk setiap paragraf Heading1."""
    out = []
    for m in PARA_RE.finditer(doc):
        paragraph = m.group(0)
        if re.search(r'<w:pStyle w:val="Heading1"', paragraph):
            out.append((m.start(), m.end(), para_text(paragraph)))
    return out


def is_front_matter_heading(text):
    return text.strip().upper() in FRONT_MATTER_HEADINGS


def is_no_number_heading(text):
    """Heading halaman pernyataan/pengesahan (zona sampul)."""
    upper = text.strip().upper()
    return any(upper.startswith(prefix) for prefix in NO_NUMBER_HEADING_PREFIXES)


def heading_texts_in_section(doc, section):
    return [
        text.strip()
        for start, _end, text in heading1_paragraphs(doc)
        if section["start"] <= start < section["end"] and text.strip()
    ]


def is_no_number_section(doc, section):
    """True bila section hanya berisi heading pernyataan/pengesahan.

    Section seperti ini berada sebelum front matter dan mengikuti aturan
    sampul: tanpa header/footer dan tanpa nomor halaman.
    """
    headings = heading_texts_in_section(doc, section)
    return bool(headings) and all(is_no_number_heading(text) for text in headings)


def first_body_heading(doc):
    """Posisi paragraf Heading1 pertama milik body (BAB I), atau None."""
    headings = heading1_paragraphs(doc)
    for start, _end, text in headings:
        if BODY_CHAPTER_RE.match(text.strip()):
            return start
    # Fallback: heading pertama yang bukan nama front matter.
    for start, _end, text in headings:
        if text.strip() and not is_front_matter_heading(text):
            return start
    return None


def body_chapter_positions(doc):
    """Posisi semua Heading1 bab bernomor (BAB I, BAB II, ...)."""
    return [
        start
        for start, _end, text in heading1_paragraphs(doc)
        if BODY_CHAPTER_RE.match(text.strip())
    ]


def is_cover_section(text):
    return bool(re.search(r'w:pStyle w:val="Cover[^"]*"', text))


def find_sections(doc):
    """Petakan setiap sectPr ke rentang konten seksi yang diakhirinya.

    OOXML menempatkan `w:sectPr` di akhir seksi. Seksi pertama adalah konten
    sebelum sectPr pertama, seksi terakhir adalah konten sebelum sectPr
    body-level terakhir.
    """
    sections = []
    current_start = 0
    for m in SECT_RE.finditer(doc):
        # Cari awal paragraf yang memuat sectPr (section break di tengah dokumen).
        p_start = None
        for pm in PARA_OPEN_RE.finditer(doc, 0, m.start()):
            p_start = pm.start()
        p_end = None
        wrapped = False
        if p_start is not None:
            prefix = doc[p_start:m.start()]
            after = doc[m.end():m.end() + 80]
            wrapped = bool(re.search(r"<w:pPr(?:\s[^>]*)?>\s*$", prefix)) and after.lstrip().startswith("</w:pPr>")
            if wrapped:
                match = PARA_RE.match(doc, p_start)
                if match:
                    p_end = match.end()

        if wrapped and p_end is not None:
            # Paragraf pemuat sectPr adalah bagian dari seksi yang diakhirinya.
            content_end = p_end
            next_start = p_end
        else:
            content_end = m.start()
            next_start = m.end()

        sections.append(
            {
                "start": current_start,
                "end": content_end,
                "sect_start": m.start(),
                "sect_end": m.end(),
            }
        )
        current_start = next_start
    return sections


def section_index_at(sections, pos):
    for i, section in enumerate(sections):
        if section["start"] <= pos < section["end"]:
            return i
    return None


def section_starts_at(section, pos, doc):
    """True bila `pos` adalah konten pertama seksi (hanya bookmark/whitespace)."""
    prefix = doc[section["start"]:pos]
    prefix = re.sub(r"<w:bookmark(?:Start|End)\b[^>]*/>", "", prefix)
    return prefix.strip() == ""


def bookmark_aware_start(doc, para_start):
    """Geser titik sisip ke sebelum bookmarkStart yang menempel pada heading."""
    match = re.search(r"(?:<w:bookmarkStart\b[^>]*/>\s*)+$", doc[:para_start])
    return match.start() if match else para_start


def strip_section_props(sect):
    sect = HEADER_FOOTER_REF_RE.sub("", sect)
    sect = PGNUM_RE.sub("", sect)
    sect = TITLEPG_RE.sub("", sect)
    return sect


def set_section_type_next_page(sect):
    sect = SECT_TYPE_RE.sub("", sect)
    tag = '<w:type w:val="nextPage"/>'
    for name in SECT_TYPE_BEFORE:
        match = re.search(rf"<w:{name}\b", sect)
        if match:
            return sect[:match.start()] + tag + sect[match.start():]
    return sect.replace("</w:sectPr>", tag + "</w:sectPr>")


def set_pgnum(sect, fmt, start=None):
    sect = PGNUM_RE.sub("", sect)
    attrs = f' w:fmt="{fmt}"'
    if start is not None:
        attrs += f' w:start="{start}"'
    tag = f"<w:pgNumType{attrs}/>"
    for name in PGNUM_BEFORE:
        match = re.search(rf"<w:{name}\b", sect)
        if match:
            return sect[:match.start()] + tag + sect[match.start():]
    return sect.replace("</w:sectPr>", tag + "</w:sectPr>")


def set_titlepg(sect):
    """Aktifkan header/footer halaman pertama yang berbeda."""
    sect = TITLEPG_RE.sub("", sect)
    tag = "<w:titlePg/>"
    for name in ("textDirection", "bidi", "rtlGutter", "docGrid", "printerSettings"):
        match = re.search(rf"<w:{name}\b", sect)
        if match:
            return sect[:match.start()] + tag + sect[match.start():]
    return sect.replace("</w:sectPr>", tag + "</w:sectPr>")


def set_references(
    sect,
    header_default=None,
    header_first=None,
    footer_default=None,
    footer_first=None,
):
    sect = HEADER_FOOTER_REF_RE.sub("", sect)
    refs = ""
    if header_default:
        refs += f'<w:headerReference w:type="default" r:id="{header_default}"/>'
    if header_first:
        refs += f'<w:headerReference w:type="first" r:id="{header_first}"/>'
    if footer_default:
        refs += f'<w:footerReference w:type="default" r:id="{footer_default}"/>'
    if footer_first:
        refs += f'<w:footerReference w:type="first" r:id="{footer_first}"/>'
    return re.sub(
        r"(<w:sectPr\b[^>]*>)", lambda m: m.group(1) + refs, sect, count=1
    )


def make_page_part(kind, align, hidden=False, size_pt=None):
    """Part header/footer berisi field PAGE asli.

    `size_pt` ditulis eksplisit ke run properties agar nomor header body
    tetap 10 pt dan footer 12 pt, tidak bergantung pada style Normal.
    """
    root = "hdr" if kind == "header" else "ftr"
    rpr_parts = []
    if hidden:
        # Footer default body harus kosong secara visual. Namun
        # docx-pagenum.py membaca nomor body dari baris terakhir PDF
        # (footer), jadi field PAGE tetap ditulis lalu disembunyikan di
        # Word dengan vanish + warna putih. LibreOffice mengabaikan
        # formatting field PAGE, sehingga nilainya masih terekstrak
        # pdftotext dan daftar isi tetap terisi.
        rpr_parts.append("<w:vanish/>")
        rpr_parts.append('<w:color w:val="FFFFFF"/>')
    if size_pt is not None:
        half_points = int(size_pt * 2)
        rpr_parts.append(f'<w:sz w:val="{half_points}"/>')
        rpr_parts.append(f'<w:szCs w:val="{half_points}"/>')
    rpr = f"<w:rPr>{''.join(rpr_parts)}</w:rPr>" if rpr_parts else ""
    run_open = f"<w:r>{rpr}"
    body = (
        f'<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
        f'<w:ind w:firstLine="0"/><w:jc w:val="{align}"/>{rpr}</w:pPr>'
        + run_open
        + '<w:fldChar w:fldCharType="begin"/></w:r>'
        + run_open
        + '<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        + run_open
        + '<w:fldChar w:fldCharType="separate"/></w:r>'
        + run_open
        + "<w:t>1</w:t></w:r>"
        + run_open
        + '<w:fldChar w:fldCharType="end"/></w:r>'
        "</w:p>"
    )
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:{root} {W_NS}>{body}</w:{root}>'


def make_empty_part(kind):
    root = "hdr" if kind == "header" else "ftr"
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:{root} {W_NS}><w:p/></w:{root}>'


def add_relationship(rels_xml, kind, target):
    used = set(re.findall(r'Id="([^"]+)"', rels_xml))
    numeric = [int(n) for n in re.findall(r'Id="rId(\d+)"', rels_xml)]
    number = max(numeric + [0]) + 1
    while f"rId{number}" in used:
        number += 1
    rid = f"rId{number}"
    entry = (
        f'<Relationship Id="{rid}" Type="{REL_NS}/{kind}" Target="{target}"/>'
    )
    return rels_xml.replace("</Relationships>", entry + "</Relationships>"), rid


def add_content_type(ct_xml, part, kind):
    content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml."
        f"{kind}+xml"
    )
    if f'PartName="/{part}"' in ct_xml:
        return ct_xml
    override = f'<Override PartName="/{part}" ContentType="{content_type}"/>'
    return ct_xml.replace("</Types>", override + "</Types>")


def create_part(items, kind, xml, ct_xml, rels_xml):
    number = 1
    while f"word/{kind}{number}.xml" in items:
        number += 1
    part = f"word/{kind}{number}.xml"
    items[part] = xml.encode("utf-8")
    ct_xml = add_content_type(ct_xml, part, kind)
    rels_xml, rid = add_relationship(rels_xml, kind, part.rsplit("/", 1)[1])
    return rid, ct_xml, rels_xml


def drop_old_header_footer_parts(items, ct_xml, rels_xml):
    for name in list(items):
        if re.match(r"word/(?:header|footer)\d+\.xml$", name):
            del items[name]
    ct_xml = re.sub(
        r'<Override PartName="/word/(?:header|footer)\d+\.xml"[^>]*/>', "", ct_xml
    )
    rels_xml = re.sub(
        r'<Relationship\b[^>]*Type="[^"]*/(?:header|footer)"[^>]*/>', "", rels_xml
    )
    return ct_xml, rels_xml


def sync_section_margins(doc):
    first_mar = re.search(
        r"<w:sectPr[^>]*>.*?(<w:pgMar\b[^>]*/>).*?</w:sectPr>", doc, re.S
    )
    if not first_mar:
        return doc
    target_pgmar = first_mar.group(1)
    return re.sub(r"<w:pgMar\b[^>]*/>", target_pgmar, doc)


def process(doc, items):
    doc = sync_section_margins(doc)
    sections = find_sections(doc)
    if not sections:
        return doc, 0, {}

    ct_xml = items["[Content_Types].xml"].decode("utf-8")
    rels_xml = items["word/_rels/document.xml.rels"].decode("utf-8")
    ct_xml, rels_xml = drop_old_header_footer_parts(items, ct_xml, rels_xml)

    changed = 0
    body_pos = first_body_heading(doc)
    body_idx = section_index_at(sections, body_pos) if body_pos is not None else None
    cover_idx = (
        0
        if sections
        and is_cover_section(doc[sections[0]["start"]:sections[0]["end"]])
        else None
    )

    # Fallback: bila docx.lua tidak menyisipkan break setelah sampul, sampul
    # dan front matter/body masih berada dalam satu seksi. Pisahkan sebelum
    # Heading1 pertama (sampul tidak punya heading).
    if cover_idx is not None and body_idx == cover_idx:
        headings = heading1_paragraphs(doc)
        if headings:
            first_heading = headings[0][0]
            if not section_starts_at(sections[0], first_heading, doc):
                insert_at = bookmark_aware_start(doc, first_heading)
                template = SECT_RE.search(doc, sections[0]["sect_start"]).group(0)
                new_sect = set_section_type_next_page(strip_section_props(template))
                break_para = f"<w:p><w:pPr>{new_sect}</w:pPr></w:p>"
                doc = doc[:insert_at] + break_para + doc[insert_at:]
                sections = find_sections(doc)
                body_pos = first_body_heading(doc)
                body_idx = (
                    section_index_at(sections, body_pos)
                    if body_pos is not None
                    else None
                )
                changed += 1

    # Tambahkan section break baru sebelum BAB I jika heading body belum
    # menjadi awal seksi. Pandoc mungkin hanya membuat break setelah sampul
    # bila `--top-level-division=chapter` tidak dipakai.
    if body_pos is not None and body_idx is not None:
        if not section_starts_at(sections[body_idx], body_pos, doc):
            insert_at = bookmark_aware_start(doc, body_pos)
            template = SECT_RE.search(doc, sections[0]["sect_start"]).group(0)
            new_sect = set_section_type_next_page(strip_section_props(template))
            break_para = f"<w:p><w:pPr>{new_sect}</w:pPr></w:p>"
            doc = doc[:insert_at] + break_para + doc[insert_at:]
            sections = find_sections(doc)
            body_pos = first_body_heading(doc)
            body_idx = section_index_at(sections, body_pos) if body_pos is not None else None
            changed += 1

    # Pastikan setiap bab bernomor menjadi awal section. Dengan begitu
    # `w:titlePg` berlaku untuk halaman pertama tiap bab, bukan hanya bab
    # pertama. Pandoc dengan `--top-level-division=chapter` biasanya sudah
    # melakukannya; langkah ini menjaga dokumen yang tidak memakai opsi itu.
    chapter_positions = body_chapter_positions(doc)
    if chapter_positions:
        for pos in reversed(chapter_positions):
            sections = find_sections(doc)
            index = section_index_at(sections, pos)
            if index is None or section_starts_at(sections[index], pos, doc):
                continue
            insert_at = bookmark_aware_start(doc, pos)
            template = SECT_RE.search(doc, sections[0]["sect_start"]).group(0)
            new_sect = set_section_type_next_page(strip_section_props(template))
            break_para = f"<w:p><w:pPr>{new_sect}</w:pPr></w:p>"
            doc = doc[:insert_at] + break_para + doc[insert_at:]
            changed += 1
        sections = find_sections(doc)
        body_pos = first_body_heading(doc)
        body_idx = section_index_at(sections, body_pos) if body_pos is not None else None

    # Section yang hanya berisi halaman pernyataan/pengesahan mengikuti
    # aturan sampul: tanpa header/footer dan tanpa nomor halaman.
    statement_idxs = {
        i
        for i, section in enumerate(sections)
        if i != cover_idx
        and (body_idx is None or i < body_idx)
        and is_no_number_section(doc, section)
    }

    front_seen = 0
    body_seen = 0
    statement_seen = 0
    mods = []
    for index, section in enumerate(sections):
        sect = doc[section["sect_start"]:section["sect_end"]]
        sect = strip_section_props(sect)

        if (cover_idx is not None and index == cover_idx) or index in statement_idxs:
            # Sampul + halaman pernyataan: tanpa header/footer dan nomor.
            sect = set_references(sect)
            new_sect = sect
            if index in statement_idxs:
                statement_seen += 1
        elif body_idx is not None and index >= body_idx:
            start = "1" if body_seen == 0 else None
            sect = set_pgnum(sect, "decimal", start)
            header_rid, ct_xml, rels_xml = create_part(
                items,
                "header",
                make_page_part(
                    "header", "right", size_pt=BODY_HEADER_SIZE_PT
                ),
                ct_xml,
                rels_xml,
            )
            header_first_rid, ct_xml, rels_xml = create_part(
                items, "header", make_empty_part("header"), ct_xml, rels_xml
            )
            footer_rid, ct_xml, rels_xml = create_part(
                items,
                "footer",
                make_page_part(
                    "footer", "center", hidden=True,
                    size_pt=BODY_FOOTER_SIZE_PT,
                ),
                ct_xml,
                rels_xml,
            )
            footer_first_rid, ct_xml, rels_xml = create_part(
                items,
                "footer",
                make_page_part(
                    "footer", "center", size_pt=BODY_FOOTER_SIZE_PT
                ),
                ct_xml,
                rels_xml,
            )
            sect = set_references(
                sect,
                header_default=header_rid,
                header_first=header_first_rid,
                footer_default=footer_rid,
                footer_first=footer_first_rid,
            )
            # Header tidak boleh muncul di halaman pertama bab: varian
            # first-page header kosong, footer first-page berisi PAGE.
            sect = set_titlepg(sect)
            new_sect = sect
            body_seen += 1
        else:
            start = "1" if front_seen == 0 else None
            sect = set_pgnum(sect, "lowerRoman", start)
            footer_rid, ct_xml, rels_xml = create_part(
                items,
                "footer",
                make_page_part(
                    "footer", "center", size_pt=FRONT_FOOTER_SIZE_PT
                ),
                ct_xml,
                rels_xml,
            )
            # Front matter tidak memakai header sama sekali.
            sect = set_references(sect, footer_default=footer_rid)
            new_sect = sect
            front_seen += 1

        if new_sect != doc[section["sect_start"]:section["sect_end"]]:
            changed += 1
        mods.append((section["sect_start"], section["sect_end"], new_sect))

    for start, end, new_sect in reversed(mods):
        doc = doc[:start] + new_sect + doc[end:]

    items["[Content_Types].xml"] = ct_xml.encode("utf-8")
    items["word/_rels/document.xml.rels"] = rels_xml.encode("utf-8")
    stats = {
        "cover": 1 if cover_idx is not None else 0,
        "statement": statement_seen,
        "front": front_seen,
        "body": body_seen,
    }
    return doc, changed, stats


def get_tab_pos(doc):
    sz = re.search(r'<w:pgSz\b[^>]*w:w="(\d+)"', doc)
    mar_left = re.search(r'<w:pgMar\b[^>]*w:left="(\d+)"', doc)
    mar_right = re.search(r'<w:pgMar\b[^>]*w:right="(\d+)"', doc)
    if sz and mar_left and mar_right:
        try:
            w = int(sz.group(1))
            left = int(mar_left.group(1))
            right = int(mar_right.group(1))
            pos = w - left - right
            if pos > 1000:
                return pos
        except (ValueError, TypeError):
            pass
    return 9072


def fix_daftar_isi_title(doc):
    pattern = re.compile(
        r'(<w:p\b[^>]*><w:pPr>(?:(?!</w:p>).)*?<w:pStyle\s+w:val=["\x27])Heading1(["\x27](?:(?!</w:p>).)*?<w:t[^>]*>\s*DAFTAR ISI\s*</w:t>(?:(?!</w:p>).)*?</w:p>)',
        re.S,
    )
    return pattern.sub(r"\g<1>TOCHeading\g<2>", doc)


def fix_toc_styles(styles, tab_pos):
    tnr = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'
    defs = {
        "TOCHeading": f"""<w:style w:type="paragraph" w:styleId="TOCHeading">
  <w:name w:val="TOC Heading"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="Normal"/>
  <w:uiPriority w:val="39"/>
  <w:qFormat/>
  <w:pPr>
    <w:spacing w:before="0" w:after="0" w:line="360" w:lineRule="auto"/>
    <w:ind w:firstLine="0"/>
    <w:jc w:val="center"/>
    <w:outlineLvl w:val="9"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b/>
    <w:bCs/>
  </w:rPr>
</w:style>""",
        "TOC1": f"""<w:style w:type="paragraph" w:styleId="TOC1">
  <w:name w:val="toc 1"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="right" w:leader="dot" w:pos="{tab_pos}"/>
    </w:tabs>
    <w:spacing w:before="120" w:after="40" w:line="260" w:lineRule="auto"/>
    <w:ind w:left="0" w:right="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b/>
    <w:bCs/>
  </w:rPr>
</w:style>""",
        "TOC2": f"""<w:style w:type="paragraph" w:styleId="TOC2">
  <w:name w:val="toc 2"/>
  <w:basedOn w:val="TOC1"/>
  <w:next w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="right" w:leader="dot" w:pos="{tab_pos}"/>
    </w:tabs>
    <w:spacing w:before="20" w:after="20" w:line="240" w:lineRule="auto"/>
    <w:ind w:left="360" w:right="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b w:val="0"/>
    <w:bCs w:val="0"/>
  </w:rPr>
</w:style>""",
        "TOC3": f"""<w:style w:type="paragraph" w:styleId="TOC3">
  <w:name w:val="toc 3"/>
  <w:basedOn w:val="TOC2"/>
  <w:next w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="right" w:leader="dot" w:pos="{tab_pos}"/>
    </w:tabs>
    <w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>
    <w:ind w:left="720" w:right="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b w:val="0"/>
    <w:bCs w:val="0"/>
  </w:rPr>
</w:style>""",
    }
    missing = []
    for sid, block in defs.items():
        pattern = re.compile(rf'<w:style\b[^>]*w:styleId="{sid}"[^>]*>.*?</w:style>', re.S)
        if pattern.search(styles):
            styles = pattern.sub(block, styles)
        else:
            missing.append(block)
    if missing:
        styles = styles.replace("</w:styles>", "".join(missing) + "</w:styles>")
    return styles


def align_toc_tabs(doc, tab_pos):
    """Sesuaikan tab leader cached TOC agar tepat di margin kanan."""
    return re.sub(
        r'(<w:pStyle w:val="TOC[123]"/>.*?<w:tab w:val="right" '
        r'w:leader="dot" w:pos=)"\d+"',
        rf'\g<1>"{tab_pos}"',
        doc,
    )


def write_items(path, items):
    """Tulis ulang DOCX secara atomik (dipakai mode in-place)."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, temp_name = tempfile.mkstemp(
        prefix=".finalize-", suffix=".docx", dir=directory
    )
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_name, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, data in items.items():
                zout.writestr(name, data)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def read_items(path):
    with zipfile.ZipFile(path, "r") as zin:
        return {name: zin.read(name) for name in zin.namelist()}


def finalize_items(items):
    """Terapkan seluruh finalisasi (section, style, settings) ke items."""
    doc = items["word/document.xml"].decode("utf-8")
    tab_pos = get_tab_pos(doc)
    doc = fix_daftar_isi_title(doc)
    doc = fix_document_formatting(doc)
    doc = align_toc_tabs(doc, tab_pos)
    new_doc, changed, stats = process(doc, items)
    items["word/document.xml"] = new_doc.encode("utf-8")

    if "word/styles.xml" in items:
        styles = items["word/styles.xml"].decode("utf-8")
        styles = fix_toc_styles(fix_document_styles(styles), tab_pos)
        items["word/styles.xml"] = styles.encode("utf-8")

    if "word/settings.xml" in items:
        settings = items["word/settings.xml"].decode("utf-8")
        items["word/settings.xml"] = fix_settings(settings).encode("utf-8")
    return items, changed, stats, tab_pos


def in_place(path):
    """Finalisasi penuh lalu tulis kembali ke berkas yang sama.

    Dipakai setelah Word COM memperbarui field: Word menormalkan ulang
    pgNumType/ukuran font footer, sehingga section dan part nomor halaman
    perlu dibangun ulang agar tetap sesuai spesifikasi.
    """
    items = read_items(path)
    items, changed, stats, tab_pos = finalize_items(items)
    write_items(path, items)
    zones = ", ".join(f"{k}={v}" for k, v in stats.items())
    print(
        f"[OK] finalize-docx --in-place: {changed} sectPr disesuaikan "
        f"({zones}; tab={tab_pos}) -> {path}"
    )


def settings_only(path):
    """Hapus updateFields dan paksa compatibilityMode 15 saja."""
    items = read_items(path)
    if "word/settings.xml" not in items:
        raise ValueError("word/settings.xml tidak ditemukan")
    settings = items["word/settings.xml"].decode("utf-8")
    items["word/settings.xml"] = fix_settings(settings).encode("utf-8")
    write_items(path, items)
    print(f"[OK] finalize-docx --settings-only: {path}")


def main():
    argv = sys.argv[1:]
    if argv[:1] in (["--in-place"], ["--settings-only"]):
        if len(argv) != 2:
            print(
                "Usage: finalize-docx.py "
                "--in-place|--settings-only DOKUMEN.docx",
                file=sys.stderr,
            )
            return 2
        if argv[0] == "--in-place":
            in_place(argv[1])
        else:
            settings_only(argv[1])
        return 0

    if len(argv) != 2:
        print(
            "Usage: finalize-docx.py INPUT.docx OUTPUT.docx\n"
            "       finalize-docx.py --in-place|--settings-only DOKUMEN.docx",
            file=sys.stderr,
        )
        return 2

    src, dst = argv
    items = read_items(src)
    items, changed, stats, tab_pos = finalize_items(items)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in items.items():
            zout.writestr(name, data)

    zones = ", ".join(f"{k}={v}" for k, v in stats.items())
    print(
        f"[OK] finalize-docx: {changed} sectPr disesuaikan "
        f"({zones}; tab={tab_pos}) -> {dst}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
