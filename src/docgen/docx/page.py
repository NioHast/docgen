"""Konstanta dan helper ukuran halaman kanonis DOCX.

Seluruh nilai ukuran halaman memakai satuan twip; 1 inci = 1440 twip.
``PAGE_SIZES`` menyimpan dimensi orientasi portrait untuk setiap nama ukuran
yang dipakai pipeline. Orientasi landscape diturunkan dengan menukar lebar dan
tinggi, bukan disimpan sebagai entri terpisah.

Nama ukuran bersifat case-sensitive dan mengikuti nilai ``page.size`` pada
konfigurasi (``A4`` dan ``Letter``). Tidak ada fallback untuk nama yang tidak
dikenal: lookup akan menimbulkan ``KeyError`` agar pemanggil dapat
menerjemahkannya menjadi error konfigurasi stage masing-masing.

``content_width`` adalah satu-satunya sumber lebar area teks. Nilainya dibaca
dari ``w:sectPr`` terakhir; tidak ada lebar cadangan, sehingga section atau
atribut wajib yang tidak lengkap menimbulkan ``PageError`` alih-alih angka
tebakan. ``w:pgMar/@w:gutter`` bersifat opsional dan dihitung 0 bila tidak
ada.

Referensi: https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing?view=openxml-3.0.1
"""

from collections.abc import Mapping

from lxml import etree

from . import DocxError, paragraphs
from .names import W_SECTPR
from .xml import qn

__all__ = ["PAGE_SIZES", "PageError", "content_width", "page_size"]

PAGE_SIZES: Mapping[str, tuple[int, int]] = {
    "A4": (11906, 16838),
    "Letter": (12240, 15840),
}

W_GUTTER = qn("w:gutter")


class PageError(DocxError):
    """Ukuran halaman atau margin ``w:sectPr`` tidak lengkap."""

    default_code = "PAGE"


def page_size(name: str, orientation: str = "portrait") -> tuple[int, int]:
    """Kembalikan ukuran halaman ``(lebar, tinggi)`` dalam twip.

    ``PAGE_SIZES`` menyimpan dimensi portrait. Orientasi ``landscape`` menukar
    lebar dan tinggi; orientasi lain diperlakukan sebagai portrait. Nama yang
    tidak dikenal tidak memiliki fallback dan menimbulkan ``KeyError``.
    """

    width, height = PAGE_SIZES[name]
    if orientation == "landscape":
        return height, width
    return width, height


def content_width(body: etree._Element) -> int:
    """Lebar area teks dari ``w:sectPr`` dokumen, dalam twip.

    ``w:sectPr`` dicari sebagai child langsung ``w:body`` lebih dulu, lalu
    sebagai descendant terakhir (section di dalam ``w:pPr``). Lebar dihitung
    dari satu section saja: ``w:pgSz/@w:w`` dikurangi ``w:pgMar/@w:left``,
    ``@w:right``, dan ``@w:gutter``.

    Tidak ada fallback angka. Section hilang, ``w:pgSz``/``w:pgMar`` hilang,
    ``@w:w``/``@w:left``/``@w:right`` hilang atau bukan bilangan bulat, serta
    lebar tidak positif menimbulkan ``PageError`` berkode ``PAGE-WIDTH``.
    ``@w:gutter`` opsional dan dihitung 0 bila tidak ada.
    """

    section = body.find(W_SECTPR)
    if section is None:
        sections = body.findall(f".//{W_SECTPR}")
        section = sections[-1] if sections else None
    if section is None:
        raise PageError("w:sectPr tidak ditemukan pada body", code="PAGE-WIDTH")

    page_size_element = section.find(qn("w:pgSz"))
    page_margin_element = section.find(qn("w:pgMar"))
    if page_size_element is None or page_margin_element is None:
        raise PageError(
            "w:sectPr tidak memiliki w:pgSz atau w:pgMar",
            code="PAGE-WIDTH",
        )

    width = paragraphs.int_attribute(page_size_element, qn("w:w"))
    left = paragraphs.int_attribute(page_margin_element, qn("w:left"))
    right = paragraphs.int_attribute(page_margin_element, qn("w:right"))
    gutter = paragraphs.int_attribute(page_margin_element, W_GUTTER) or 0
    if width is None or left is None or right is None:
        raise PageError(
            "w:pgSz/@w:w atau w:pgMar/@w:left,@w:right tidak valid",
            code="PAGE-WIDTH",
        )

    result = width - left - right - gutter
    if result <= 0:
        raise PageError(
            f"lebar konten tidak positif: {result} twip",
            code="PAGE-WIDTH",
        )
    return result
