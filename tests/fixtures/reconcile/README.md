# Fixture rekonsiliasi

Fixture ini dipakai oleh `tests/test_reconcile.py`.

- `manifest.json` adalah manifest versi 1 dengan tujuh paragraf contoh.
- `chapters/` adalah sumber Markdown yang cocok dengan teks di manifest.

Berkas DOCX tidak disimpan sebagai biner. Tes membangun DOCX sementara dari
manifest dengan `python-docx`, lalu menyisipkan bookmark `pNNNN`, sehingga
setiap skenario (edit body, edit caption terlindungi, paragraf baru, ID hilang)
bisa dibuat eksplisit dan deterministik.
