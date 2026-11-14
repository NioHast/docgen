"""Pembuatan, penyalinan, dan pembersihan run WordprocessingML.

Modul ini adalah satu sumber helper run untuk lapisan DOCX:
:func:`build_run`, :func:`make_run`, :func:`append_text_run`,
:func:`clone_run`, :func:`copy_rpr`, dan :func:`strip_bold_from_rpr`.
Modul DOCX dan stage memakai API ini agar struktur ``w:r``/``w:rPr``
konsisten, tanpa bergantung pada ``python-docx`` atau traversal lxml milik
masing-masing pemanggil.

Semua fungsi memutasi elemen lxml yang diberikan; tidak ada akses package
atau berkas di sini.
"""

import copy

from lxml import etree

from .names import W_R, W_T, W_TAB
from .xml import is_on, qn

W_B = qn("w:b")
W_BCS = qn("w:bCs")
XML_SPACE = qn("xml:space")


def build_run(
    *,
    text: str | None = None,
    rpr: etree._Element | None = None,
) -> etree._Element:
    """Buat ``w:r`` lepas tanpa parent.

    ``rpr`` diperlakukan sebagai templat dan disalin dalam lewat
    :func:`copy_rpr`, sehingga run baru tidak berbagi node dengan sumber.
    Bila ``text`` diberikan, satu ``w:t`` ditambahkan setelah ``w:rPr``;
    ``xml:space="preserve"`` hanya dipasang saat tepi teks berupa spasi.
    """

    run = etree.Element(W_R)
    if rpr is not None:
        run.append(copy_rpr(rpr))
    if text is not None:
        node = etree.SubElement(run, W_T)
        node.text = text
        if text[:1].isspace() or text[-1:].isspace():
            node.set(XML_SPACE, "preserve")
    return run


def make_run(
    paragraph: etree._Element,
    *,
    text: str | None = None,
    rpr: etree._Element | None = None,
) -> etree._Element:
    """Buat ``w:r`` baru sebagai anak terakhir ``paragraph``.

    Run dibuat lewat :func:`build_run`, lalu ditambahkan sebagai anak
    terakhir ``paragraph``. ``rpr`` diperlakukan sebagai templat dan disalin
    dalam, sehingga run baru tidak berbagi node dengan sumber.
    """

    run = build_run(text=text, rpr=rpr)
    paragraph.append(run)
    return run


def append_text_run(
    paragraph: etree._Element,
    text: str,
    *,
    rpr: etree._Element | None = None,
) -> etree._Element:
    """Tambahkan run teks ke ``paragraph``; tab dipecah menjadi ``w:tab``.

    ``w:rPr`` ditulis tepat satu kali di awal run bila ``rpr`` diberikan.
    Teks dipecah pada setiap karakter tab; setiap potongan non-kosong menjadi
    satu ``w:t`` dengan ``xml:space="preserve"``, sedangkan potongan kosong
    (mis. teks yang diawali atau diakhiri tab) tidak menghasilkan ``w:t``.
    """

    run = make_run(paragraph, rpr=rpr)
    for index, part in enumerate(text.split("\t")):
        if index:
            run.append(etree.Element(W_TAB))
        if not part:
            continue
        node = etree.SubElement(run, W_T)
        node.set(XML_SPACE, "preserve")
        node.text = part
    return run


def clone_run(run: etree._Element) -> etree._Element:
    """Salin dalam ``run`` beserta atribut dan seluruh anaknya.

    Hasil salinan tidak memiliki parent, sehingga aman disisipkan ke
    paragraf lain tanpa memindahkan atau mengubah run asli.
    """

    return copy.deepcopy(run)


def copy_rpr(rpr: etree._Element) -> etree._Element:
    """Salin dalam ``w:rPr`` tanpa berbagi node anak dengan sumber."""

    return copy.deepcopy(rpr)


def strip_bold_from_rpr(rpr: etree._Element) -> int:
    """Hapus ``w:b``/``w:bCs`` aktif langsung dari satu ``w:rPr``.

    Status aktif dibaca lewat :func:`docgen.docx.xml.is_on`, sehingga nilai
    ``0``, ``false``, ``off``, dan ``no`` dipertahankan sebagai nonaktif,
    sedangkan ``none`` diperlakukan aktif seperti helper XML kanonis.
    Kembalikan jumlah elemen yang benar-benar dihapus.
    """

    removed = 0
    for tag in (W_B, W_BCS):
        for element in list(rpr.findall(tag)):
            if not is_on(element):
                continue
            rpr.remove(element)
            removed += 1
    return removed


__all__ = [
    "append_text_run",
    "build_run",
    "clone_run",
    "copy_rpr",
    "make_run",
    "strip_bold_from_rpr",
]
