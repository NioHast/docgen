"""Konstanta dan helper ukuran halaman kanonis DOCX.

Seluruh nilai ukuran halaman memakai satuan twip; 1 inci = 1440 twip.
``PAGE_SIZES`` menyimpan dimensi orientasi portrait untuk setiap nama ukuran
yang dipakai pipeline. Orientasi landscape diturunkan dengan menukar lebar dan
tinggi, bukan disimpan sebagai entri terpisah.

Nama ukuran bersifat case-sensitive dan mengikuti nilai ``page.size`` pada
konfigurasi (``A4`` dan ``Letter``). Tidak ada fallback untuk nama yang tidak
dikenal: lookup akan menimbulkan ``KeyError`` agar pemanggil dapat
menerjemahkannya menjadi error konfigurasi stage masing-masing.
"""

from collections.abc import Mapping

__all__ = ["PAGE_SIZES", "page_size"]

PAGE_SIZES: Mapping[str, tuple[int, int]] = {
    "A4": (11906, 16838),
    "Letter": (12240, 15840),
}


def page_size(name: str, orientation: str = "portrait") -> tuple[int, int]:
    """Kembalikan ukuran halaman ``(lebar, tinggi)`` dalam twip.

    ``PAGE_SIZES`` menyimpan dimensi portrait. Orientasi ``landscape`` menukar
    lebar dan tinggi; orientasi lain diperlakukan sebagai portrait, sama
    seperti perilaku historis stage ``sections``. Nama yang tidak dikenal
    tidak memiliki fallback dan menimbulkan ``KeyError``.
    """

    width, height = PAGE_SIZES[name]
    if orientation == "landscape":
        return height, width
    return width, height
