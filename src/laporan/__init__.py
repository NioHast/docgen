"""Fondasi struktur modular untuk pipeline laporan akademik.

Paket ini memisahkan empat lapis:

- ``formats/``    : aturan visual (preset, CSL, bibliografi);
- ``structures/`` : urutan bagian dan penomoran dokumen;
- ``content/``    : naskah Markdown dan metadata proyek;
- ``platform.py`` : deteksi OS, shell, dan perkakas build.

CLI dijalankan dengan ``python -m laporan`` dari akar repositori.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
