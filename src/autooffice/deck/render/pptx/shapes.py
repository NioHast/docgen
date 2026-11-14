"""Primitive shape, geometri, metadata key, dan error renderer PPTX.

Modul ini adalah lapisan rendah renderer. Ia tidak mengetahui block type dan
tidak membuat teks; semua nilai teks berasal dari ``BlockIR`` atau chrome
terdaftar. Warna, ukuran, dan jarak selalu berasal dari ``Theme`` yang sudah
diresolusi.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from lxml import etree
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.shapes.base import BaseShape
from pptx.text.text import TextFrame, _Paragraph, _Run
from pptx.util import Emu, Pt

from autooffice.deck.layout.spec import PlacedBlock
from autooffice.design.fonts import FONT_FAMILY
from autooffice.errors import AutoOfficeError

KEY_MARKER = "autooffice:key:"
TABLE_MARKER = "autooffice:table:"
CHART_MARKER = "autooffice:chart:"
IMAGE_MARKER = "autooffice:image:"
DIAGRAM_MARKER = "autooffice:diagram:"
CHROME_PREFIX = "chrome:"

KEY_EXTENSION_NS = "urn:autooffice:key"
KEY_EXTENSION_TAG = f"{{{KEY_EXTENSION_NS}}}key"
KEY_EXTENSION_URI = "{6F8D3C8E-6A5D-4C2B-9D70-1E6E4F5A8B21}"

_GENERIC_TYPEFFACES = frozenset(
    {
        "cursive",
        "fantasy",
        "monospace",
        "sans-serif",
        "serif",
        "system-ui",
        "ui-monospace",
        "ui-sans-serif",
        "ui-serif",
    }
)

# Nama family TTF bundled: SemiBold dan ExtraBold adalah family terpisah,
# sedangkan Bold adalah style dari family dasar (lihat name table aset).
_BUNDLED_WEIGHT_TYPEFFACES = frozenset(
    {
        f"{FONT_FAMILY} SemiBold",
        f"{FONT_FAMILY} ExtraBold",
    }
)

etree.register_namespace("aoo", KEY_EXTENSION_NS)


class PptxRenderError(AutoOfficeError, ValueError):
    """Satu block atau request tidak dapat dirender menjadi PPTX."""


@dataclass(frozen=True, slots=True)
class Box:
    """Kotak EMU yang sudah dihitung layout engine."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise PptxRenderError(
                f"Kotak shape harus memiliki lebar dan tinggi positif, bukan "
                f"{self.width}x{self.height} EMU."
            )

    @property
    def right(self) -> int:
        """Batas kanan kotak."""
        return self.left + self.width

    @property
    def bottom(self) -> int:
        """Batas bawah kotak."""
        return self.top + self.height

    def inset(self, padding_emu: int) -> Box:
        """Kembalikan kotak yang sudah dikurangi padding seragam."""
        if padding_emu < 0:
            raise PptxRenderError("Padding shape tidak boleh negatif.")
        width = self.width - 2 * padding_emu
        height = self.height - 2 * padding_emu
        if width <= 0 or height <= 0:
            raise PptxRenderError(
                f"Padding {padding_emu} EMU terlalu besar untuk kotak "
                f"{self.width}x{self.height} EMU."
            )
        return Box(
            left=self.left + padding_emu,
            top=self.top + padding_emu,
            width=width,
            height=height,
        )


def box_from_placed(placed: PlacedBlock) -> Box:
    """Ubah ``PlacedBlock`` layout menjadi ``Box`` renderer."""
    return Box(
        left=placed.left_emu,
        top=placed.top_emu,
        width=placed.width_emu,
        height=placed.height_emu,
    )


def validate_box_within_slide(box: Box, *, slide_width_emu: int, slide_height_emu: int) -> None:
    """Pastikan shape tidak keluar dari kanvas presentasi."""
    if box.left < 0 or box.top < 0:
        raise PptxRenderError(f"Kotak shape memiliki posisi negatif ({box.left}, {box.top}) EMU.")
    if box.right > slide_width_emu or box.bottom > slide_height_emu:
        raise PptxRenderError(
            f"Kotak shape {box.left},{box.top},{box.width},{box.height} EMU "
            f"keluar dari kanvas {slide_width_emu}x{slide_height_emu} EMU."
        )


def rgb(color: str) -> RGBColor:
    """Ubah warna token heksadesimal menjadi ``RGBColor`` PowerPoint."""
    if len(color) != 7 or not color.startswith("#"):
        raise PptxRenderError(f"Warna token harus heksadesimal enam digit, bukan {color!r}.")
    digits = color[1:]
    try:
        return RGBColor(  # type: ignore[no-untyped-call]
            int(digits[0:2], 16),
            int(digits[2:4], 16),
            int(digits[4:6], 16),
        )
    except ValueError as error:
        raise PptxRenderError(f"Warna token tidak valid: {color!r}.") from error


def primary_typeface(family: str) -> str:
    """Ambil typeface pertama yang konkret dari stack font token."""
    candidates = [part.strip().strip("'\"") for part in family.split(",")]
    for candidate in candidates:
        if candidate and candidate.lower() not in _GENERIC_TYPEFFACES:
            return candidate
    if candidates:
        return candidates[0]
    raise PptxRenderError("Family font token tidak boleh kosong.")


def c_nv_pr(shape: BaseShape) -> etree._Element | None:
    """Kembalikan node ``p:cNvPr`` milik shape."""
    return shape._element.find(".//" + qn("p:cNvPr"))


def shape_name(shape: BaseShape) -> str:
    """Kembalikan nama shape; string kosong bila tidak ada."""
    node = c_nv_pr(shape)
    return "" if node is None else node.get("name", "")


def shape_title(shape: BaseShape) -> str:
    """Kembalikan atribut ``title`` shape; string kosong bila tidak ada."""
    node = c_nv_pr(shape)
    return "" if node is None else node.get("title", "")


def shape_description(shape: BaseShape) -> str:
    """Kembalikan atribut ``descr`` shape; string kosong bila tidak ada."""
    node = c_nv_pr(shape)
    return "" if node is None else node.get("descr", "")


def set_non_visual_properties(
    shape: BaseShape,
    *,
    name: str,
    title: str | None = None,
    description: str | None = None,
) -> None:
    """Tulis nama, judul, dan deskripsi aksesibilitas shape."""
    node = c_nv_pr(shape)
    if node is None:
        raise PptxRenderError(f"Shape '{shape_name(shape) or 'tanpa nama'}' tidak punya cNvPr.")
    node.set("name", name)
    if title is None:
        node.attrib.pop("title", None)
    else:
        node.set("title", title)
    if description is None:
        node.attrib.pop("descr", None)
    else:
        node.set("descr", description)


def set_keyed_shape(shape: BaseShape, key: str, *, description: str) -> None:
    """Tandai shape sebagai pemilik satu key datar."""
    if not key:
        raise PptxRenderError("Key shape tidak boleh kosong.")
    set_non_visual_properties(
        shape,
        name=f"{KEY_MARKER}{key}",
        title=key,
        description=description,
    )


def set_namespace_marker(
    shape: BaseShape,
    marker: str,
    namespace: str,
    *,
    description: str,
) -> None:
    """Tandai shape media dengan namespace block, bukan key leaf."""
    if not namespace:
        raise PptxRenderError("Namespace block tidak boleh kosong.")
    set_non_visual_properties(
        shape,
        name=f"{marker}{namespace}",
        title=namespace,
        description=description,
    )


def set_chrome_shape(shape: BaseShape, name: str, *, description: str = "") -> None:
    """Tandai shape sebagai chrome yang tidak diperiksa coverage."""
    if not name:
        raise PptxRenderError("Nama chrome tidak boleh kosong.")
    set_non_visual_properties(
        shape,
        name=f"{CHROME_PREFIX}{name}",
        title=None,
        description=description,
    )


def key_from_shape(shape: BaseShape) -> str | None:
    """Baca key shape dari marker nama atau atribut ``title``."""
    name = shape_name(shape)
    title = shape_title(shape)
    if name.startswith(KEY_MARKER):
        key = name[len(KEY_MARKER) :]
        return key or None
    if name.startswith((TABLE_MARKER, CHART_MARKER, IMAGE_MARKER, DIAGRAM_MARKER, CHROME_PREFIX)):
        return None
    if title and not title.startswith(("autooffice:", CHROME_PREFIX)):
        return title
    return None


def namespace_from_shape(shape: BaseShape, marker: str) -> str | None:
    """Baca namespace block dari marker nama shape media."""
    name = shape_name(shape)
    if name.startswith(marker):
        namespace = name[len(marker) :]
        return namespace or None
    return None


def _extension_list(parent: etree._Element) -> etree._Element:
    ext_lst = parent.find(qn("a:extLst"))
    if ext_lst is None:
        ext_lst = OxmlElement("a:extLst")
        parent.append(ext_lst)
    return ext_lst


def add_extension_keys(parent: etree._Element, keys: Iterable[str]) -> None:
    """Simpan key datar di ``a:extLst`` parent tanpa mengubah tabel native."""
    unique = tuple(dict.fromkeys(key for key in keys if key))
    if not unique:
        return
    ext_lst = _extension_list(parent)
    ext = ext_lst.find(f"{qn('a:ext')}[@uri='{KEY_EXTENSION_URI}']")
    if ext is None:
        ext = OxmlElement("a:ext")
        ext.set("uri", KEY_EXTENSION_URI)
        ext_lst.append(ext)
    existing = {element.text for element in ext.iter(KEY_EXTENSION_TAG) if element.text}
    for key in unique:
        if key in existing:
            continue
        element = etree.SubElement(ext, KEY_EXTENSION_TAG)
        element.text = key


def extension_keys(parent: etree._Element) -> tuple[str, ...]:
    """Baca seluruh key datar dari ``a:extLst`` parent secara deterministik."""
    return tuple(
        dict.fromkeys(element.text for element in parent.iter(KEY_EXTENSION_TAG) if element.text)
    )


def shape_extension_keys(shape: BaseShape) -> tuple[str, ...]:
    """Baca key tambahan dari ``cNvPr`` shape, bukan dari isi tabel."""
    node = c_nv_pr(shape)
    if node is None:
        return ()
    return extension_keys(node)


def field_text(fields: Mapping[str, object], name: str, *, block_id: str) -> str:
    """Baca satu field string wajib dari ``BlockIR``."""
    value = fields.get(name)
    if not isinstance(value, str) or not value:
        raise PptxRenderError(f"Block '{block_id}' tidak memiliki field teks '{name}'.")
    return value


def field_optional_text(fields: Mapping[str, object], name: str) -> str:
    """Baca field string opsional dari ``BlockIR``."""
    value = fields.get(name)
    return value if isinstance(value, str) else ""


def field_sequence(fields: Mapping[str, object], name: str, *, block_id: str) -> tuple[str, ...]:
    """Baca field tuple string dari ``BlockIR``."""
    value = fields.get(name)
    if not isinstance(value, tuple | list):
        raise PptxRenderError(f"Block '{block_id}' tidak memiliki field daftar '{name}'.")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise PptxRenderError(f"Field '{name}' pada block '{block_id}' harus string.")
        items.append(item)
    return tuple(items)


def field_rows(
    fields: Mapping[str, object],
    name: str,
    *,
    block_id: str,
) -> tuple[tuple[str, ...], ...]:
    """Baca field tuple baris string dari ``BlockIR``."""
    value = fields.get(name)
    if not isinstance(value, tuple | list):
        raise PptxRenderError(f"Block '{block_id}' tidak memiliki field baris '{name}'.")
    rows: list[tuple[str, ...]] = []
    for raw_row in value:
        if not isinstance(raw_row, tuple | list):
            raise PptxRenderError(f"Field '{name}' pada block '{block_id}' harus baris string.")
        cells: list[str] = []
        for cell in raw_row:
            if not isinstance(cell, str):
                raise PptxRenderError(f"Field '{name}' pada block '{block_id}' harus string.")
            cells.append(cell)
        rows.append(tuple(cells))
    return tuple(rows)


def sequence(value: object) -> tuple[object, ...]:
    """Normalisasi list atau tuple menjadi tuple tanpa mengubah isi."""
    if isinstance(value, Sequence) and not isinstance(value, bytes | str):
        return tuple(value)
    return ()


def configure_text_frame(
    text_frame: TextFrame,
    *,
    vertical_anchor: MSO_ANCHOR = MSO_ANCHOR.TOP,
) -> None:
    """Aktifkan word wrap, matikan shrink, dan nol-kan margin shape."""
    text_frame.word_wrap = True
    text_frame.auto_size = MSO_AUTO_SIZE.NONE
    text_frame.vertical_anchor = vertical_anchor
    text_frame.margin_left = Emu(0)
    text_frame.margin_right = Emu(0)
    text_frame.margin_top = Emu(0)
    text_frame.margin_bottom = Emu(0)


def _weight_typeface(base: str, weight: int) -> tuple[str, bool, str | None]:
    """Pilih typeface bobot bernama, atau fallback family dasar + bold.

    ``Plus Jakarta Sans SemiBold`` dan ``Plus Jakarta Sans ExtraBold`` adalah
    family TTF terpisah, jadi run-nya tidak boleh diberi ``bold`` sintetis.
    Bila typeface turunan tidak tersedia, renderer memakai family dasar dengan
    bold dan mengembalikan peringatan agar pemanggil dapat melaporkannya.
    """
    if weight >= 800:
        candidate = f"{base} ExtraBold"
    elif weight >= 700:
        return base, True, None
    elif weight >= 600:
        candidate = f"{base} SemiBold"
    else:
        return base, False, None
    if candidate in _BUNDLED_WEIGHT_TYPEFFACES:
        return candidate, False, None
    return (
        base,
        True,
        f"font-weight: typeface '{candidate}' tidak tersedia; memakai '{base}' dengan bold=True.",
    )


def apply_run_style(
    run: _Run,
    *,
    family: str,
    size_pt: float,
    weight: int,
    color: str,
    tracking_em: float,
) -> str | None:
    """Terapkan family, ukuran, warna, bobot, dan tracking ke satu run.

    Kembalikan peringatan bila family bobot yang diminta tidak tersedia dan
    run memakai fallback family dasar + bold.
    """
    font = run.font
    typeface, bold, warning = _weight_typeface(primary_typeface(family), weight)
    font.name = typeface
    font.size = Pt(size_pt)
    font.bold = bold
    font.italic = False
    font.color.rgb = rgb(color)
    r_pr = font._element
    r_pr.set("spc", str(round(tracking_em * size_pt * 100)))
    return warning


def apply_paragraph_style(
    paragraph: _Paragraph,
    *,
    line_height: float,
    font_size_pt: float,
    alignment: PP_ALIGN = PP_ALIGN.LEFT,
) -> None:
    """Terapkan line-height eksak, spacing, dan alignment paragraf.

    ``line_height`` adalah multiplier ukuran font, sama dengan semantik
    pengukuran layout. Nilai ditulis sebagai ``a:spcPts`` dalam satuan
    seperseratus poin, bukan ``a:spcPct`` yang berarti persentase tinggi baris
    tunggal.
    """
    if line_height <= 0:
        raise PptxRenderError("Line-height paragraf harus positif.")
    if font_size_pt <= 0:
        raise PptxRenderError("Ukuran font paragraf harus positif.")
    p_pr = paragraph._p.get_or_add_pPr()
    existing = p_pr.find(qn("a:lnSpc"))
    if existing is not None:
        p_pr.remove(existing)
    line_spacing = OxmlElement("a:lnSpc")
    spacing_points = OxmlElement("a:spcPts")
    spacing_points.set("val", str(round(line_height * font_size_pt * 100)))
    line_spacing.append(spacing_points)
    p_pr.insert(0, line_spacing)
    paragraph.space_before = Pt(0)
    paragraph.space_after = Pt(0)
    paragraph.alignment = alignment
