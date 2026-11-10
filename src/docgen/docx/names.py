"""Nama namespace, tag, dan style DOCX yang dipakai bersama.

Modul ini hanya berisi konstanta dan fungsi murni. Tidak ada parsing,
serialisasi, atau mutasi package di sini.
"""

import re

# Namespace inti WordprocessingML dan DrawingML.
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

# Namespace pendukung yang sering muncul di part DOCX.
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W10_NS = "urn:schemas-microsoft-com:office:word"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
V_NS = "urn:schemas-microsoft-com:vml"
O_NS = "urn:schemas-microsoft-com:office:office"
WPS_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
WPG_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
WP14_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
XML_NS = "http://www.w3.org/XML/1998/namespace"

# Namespace OPC untuk content types dan relationships.
PKG_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

NSMAP: dict[str, str] = {
    "w": W_NS,
    "r": R_NS,
    "wp": WP_NS,
    "a": A_NS,
    "w14": W14_NS,
    "w10": W10_NS,
    "mc": MC_NS,
    "m": M_NS,
    "v": V_NS,
    "o": O_NS,
    "wps": WPS_NS,
    "wpg": WPG_NS,
    "pic": PIC_NS,
    "a14": A14_NS,
    "wp14": WP14_NS,
    "ct": PKG_CT_NS,
    "pr": PKG_REL_NS,
    "xml": XML_NS,
}

# Clark-notation shorthand untuk namespace yang paling sering dipakai.
W = f"{{{W_NS}}}"
R = f"{{{R_NS}}}"
WP = f"{{{WP_NS}}}"
A = f"{{{A_NS}}}"
W14 = f"{{{W14_NS}}}"
M = f"{{{M_NS}}}"
V = f"{{{V_NS}}}"
O = f"{{{O_NS}}}"
PIC = f"{{{PIC_NS}}}"
CT = f"{{{PKG_CT_NS}}}"
PR = f"{{{PKG_REL_NS}}}"
XML = f"{{{XML_NS}}}"

# Tag WordprocessingML.
W_DOCUMENT = W + "document"
W_BODY = W + "body"
W_P = W + "p"
W_R = W + "r"
W_T = W + "t"
W_TAB = W + "tab"
W_PTAB = W + "ptab"
W_BR = W + "br"
W_CR = W + "cr"
W_NO_BREAK_HYPHEN = W + "noBreakHyphen"
W_PPR = W + "pPr"
W_RPR = W + "rPr"
W_PSTYLE = W + "pStyle"
W_RSTYLE = W + "rStyle"
W_VAL = W + "val"
W_TYPE = W + "type"
W_ID = W + "id"
W_NAME = W + "name"
W_INSTR = W + "instr"
W_INSTRTEXT = W + "instrText"
W_FLDCHAR = W + "fldChar"
W_FLDCHARTYPE = W + "fldCharType"
W_FLDSIMPLE = W + "fldSimple"
W_HYPERLINK = W + "hyperlink"
W_SDT = W + "sdt"
W_SDT_CONTENT = W + "sdtContent"
W_TBL = W + "tbl"
W_TR = W + "tr"
W_TC = W + "tc"
W_TBLPR = W + "tblPr"
W_TCPR = W + "tcPr"
W_SECTPR = W + "sectPr"
W_TXBXCONTENT = W + "txbxContent"
W_DRAWING = W + "drawing"
W_PICT = W + "pict"
W_OBJECT = W + "object"
W_BOOKMARK_START = W + "bookmarkStart"
W_BOOKMARK_END = W + "bookmarkEnd"
W_DEL = W + "del"
W_MOVEFROM = W + "moveFrom"
W_DELTEXT = W + "delText"
W_INS = W + "ins"
W_MOVE_TO = W + "moveTo"
W_CUSTOM_XML = W + "customXml"
W_PROOFERR = W + "proofErr"
W_LAST_RENDERED_PAGE_BREAK = W + "lastRenderedPageBreak"

# Tag OPC.
CT_TYPES = CT + "Types"
CT_DEFAULT = CT + "Default"
CT_OVERRIDE = CT + "Override"
PR_RELATIONSHIPS = PR + "Relationships"
PR_RELATIONSHIP = PR + "Relationship"

# Tag DrawingML yang sering dipakai saat memeriksa gambar.
WP_INLINE = WP + "inline"
WP_ANCHOR = WP + "anchor"
A_BLIP = A + "blip"
PIC_BLIP_FILL = PIC + "blipFill"
R_EMBED = R + "embed"
R_ID = R + "id"

# Style ID bawaan yang dipakai bersama.
STYLE_NORMAL = "Normal"
STYLE_HEADING_PREFIX = "Heading"
STYLE_TOC_HEADING = "TOCHeading"
STYLE_CAPTION = "Caption"
STYLE_TABLE_CAPTION = "TableCaption"
STYLE_IMAGE_CAPTION = "ImageCaption"
STYLE_FIGURE = "Figure"
STYLE_BIBLIOGRAPHY = "Bibliography"
STYLE_SOURCE_CODE = "SourceCode"
STYLE_VERBATIM_CHAR = "VerbatimChar"
STYLE_HTML_CODE = "HTMLCode"
STYLE_HTML_PREFORMATTED = "HTMLPreformatted"
STYLE_ISTILAH_ASING = "IstilahAsing"
STYLE_ISTILAH_REVIEW = "IstilahReview"

HEADING_STYLES = tuple(f"{STYLE_HEADING_PREFIX}{level}" for level in range(1, 10))
CAPTION_STYLES = frozenset({STYLE_CAPTION, STYLE_TABLE_CAPTION, STYLE_IMAGE_CAPTION})
CODE_STYLES = frozenset(
    {STYLE_SOURCE_CODE, STYLE_VERBATIM_CHAR, STYLE_HTML_CODE, STYLE_HTML_PREFORMATTED}
)

_CAPTION_NORMALIZED = frozenset({"caption", "tablecaption", "imagecaption"})
_CODE_NORMALIZED = frozenset({"sourcecode", "verbatimchar", "htmlcode", "htmlpreformatted"})

_HEADING_RE = re.compile(r"heading[1-9]")
_HTML_CODE_RE = re.compile(r"htmlcode\d*")
_NORMALIZE_RE = re.compile(r"[\s_\-]+")


def local_name(tag: str) -> str:
    """Kembalikan nama lokal dari Clark-notation atau ``prefix:local``."""

    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag.rsplit(":", 1)[-1]


def normalize_style_id(value: str | None) -> str:
    """Normalisasi style ID: tanpa kapitalisasi, spasi, ``_``, dan ``-``."""

    if value is None:
        return ""
    return _NORMALIZE_RE.sub("", value).casefold()


def is_style(style_id: str | None, *names: str) -> bool:
    """True bila ``style_id`` sama dengan salah satu nama setelah normalisasi."""

    if style_id is None:
        return False
    target = normalize_style_id(style_id)
    return any(normalize_style_id(name) == target for name in names)


def is_heading_style(style_id: str | None) -> bool:
    """True untuk style paragraf ``Heading1`` sampai ``Heading9``."""

    if style_id is None:
        return False
    return _HEADING_RE.fullmatch(normalize_style_id(style_id)) is not None


def is_caption_style(style_id: str | None) -> bool:
    """True untuk style caption gambar/tabel, bukan ``FigureCaption``."""

    if style_id is None:
        return False
    return normalize_style_id(style_id) in _CAPTION_NORMALIZED


def is_code_style(style_id: str | None) -> bool:
    """True untuk style kode yang dipakai pipeline."""

    if style_id is None:
        return False
    normalized = normalize_style_id(style_id)
    return normalized in _CODE_NORMALIZED or _HTML_CODE_RE.fullmatch(normalized) is not None


def is_cover_style(style_id: str | None) -> bool:
    """True untuk seluruh style sampul ``Cover*``."""

    if style_id is None:
        return False
    return normalize_style_id(style_id).startswith("cover")


__all__ = [
    "A14_NS",
    "A_BLIP",
    "A_NS",
    "CAPTION_STYLES",
    "CODE_STYLES",
    "CT",
    "CT_DEFAULT",
    "CT_OVERRIDE",
    "CT_TYPES",
    "HEADING_STYLES",
    "MC_NS",
    "M_NS",
    "NSMAP",
    "O_NS",
    "PIC",
    "PIC_BLIP_FILL",
    "PIC_NS",
    "PKG_CT_NS",
    "PKG_REL_NS",
    "PR",
    "PR_RELATIONSHIP",
    "PR_RELATIONSHIPS",
    "R_EMBED",
    "R_ID",
    "R_NS",
    "STYLE_BIBLIOGRAPHY",
    "STYLE_CAPTION",
    "STYLE_FIGURE",
    "STYLE_HEADING_PREFIX",
    "STYLE_HTML_CODE",
    "STYLE_HTML_PREFORMATTED",
    "STYLE_IMAGE_CAPTION",
    "STYLE_ISTILAH_ASING",
    "STYLE_ISTILAH_REVIEW",
    "STYLE_NORMAL",
    "STYLE_SOURCE_CODE",
    "STYLE_TABLE_CAPTION",
    "STYLE_TOC_HEADING",
    "STYLE_VERBATIM_CHAR",
    "V_NS",
    "W10_NS",
    "W14",
    "W14_NS",
    "WP",
    "WP14_NS",
    "WPS_NS",
    "WP_ANCHOR",
    "WP_INLINE",
    "WP_NS",
    "W_BODY",
    "W_BOOKMARK_END",
    "W_BOOKMARK_START",
    "W_BR",
    "W_CR",
    "W_CUSTOM_XML",
    "W_DEL",
    "W_DELTEXT",
    "W_DOCUMENT",
    "W_DRAWING",
    "W_FLDCHAR",
    "W_FLDCHARTYPE",
    "W_FLDSIMPLE",
    "W_HYPERLINK",
    "W_ID",
    "W_INS",
    "W_INSTR",
    "W_INSTRTEXT",
    "W_LAST_RENDERED_PAGE_BREAK",
    "W_MOVEFROM",
    "W_MOVE_TO",
    "W_NAME",
    "W_NO_BREAK_HYPHEN",
    "W_NS",
    "W_OBJECT",
    "W_P",
    "W_PICT",
    "W_PPR",
    "W_PROOFERR",
    "W_PSTYLE",
    "W_PTAB",
    "W_R",
    "W_RPR",
    "W_RSTYLE",
    "W_SDT",
    "W_SDT_CONTENT",
    "W_SECTPR",
    "W_T",
    "W_TAB",
    "W_TBL",
    "W_TBLPR",
    "W_TC",
    "W_TCPR",
    "W_TR",
    "W_TXBXCONTENT",
    "W_TYPE",
    "W_VAL",
    "XML",
    "XML_NS",
    "A",
    "M",
    "O",
    "R",
    "V",
    "W",
    "is_caption_style",
    "is_code_style",
    "is_cover_style",
    "is_heading_style",
    "is_style",
    "local_name",
    "normalize_style_id",
]
