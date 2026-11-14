"""Helper ketersediaan Pandoc untuk dekorator collection pytest."""

from autooffice.docx.errors import ToolMissingError
from autooffice.docx.stages.pandoc import find_pandoc


def pandoc_available() -> bool:
    """True bila Pandoc dapat ditemukan; override environment invalid = tidak ada.

    ``find_pandoc()`` sengaja gagal keras di produksi saat override environment
    diisi tetapi tidak valid. Dekorator ``skipif`` dievaluasi saat collection,
    jadi helper ini menangkap error tersebut dan menganggap Pandoc tidak
    tersedia agar suite tetap dapat dikoleksi.
    """

    try:
        return find_pandoc() is not None
    except ToolMissingError:
        return False
