# Indeks Dokumentasi

Dokumen di bawah diurutkan mengikuti alur pemakaian: menulis, membangun,
memproses DOCX, meninjau, lalu mendistribusikan. Kembali ke
[README utama](../README.md).

| No | Dokumen | Penjelasan |
| --- | --- | --- |
| 1 | [prosa.md](prosa.md) | Panduan dan pemeriksa prosa Indonesia: kode temuan, `make lint-prosa`, `--banding`, dan batasan pemeriksaan berbasis regex. |
| 2 | [format-undip.md](format-undip.md) | Format target UNDIP, ringkasan preset `undip-skripsi`, dan sitasi IEEE; nilai `heading_subsub_dot` dan catatan integrasi `refs/` di bagian akhir sudah usang. |
| 3 | [style-generator.md](style-generator.md) | Cara `tools/build_style.py` menghasilkan `reference.docx` dari preset serta pemetaan margin, font, dan spasi ke DOCX. |
| 4 | [pdf.md](pdf.md) | Pipeline PDF Pandoc ke Typst, peran `template.typ` dan `tools/env.sh`, serta perbedaan tata letak PDF dan DOCX. |
| 5 | [istilah.md](istilah.md) | Glosarium `writing/istilah.tsv`, penanda `{{?istilah?}}`, perintah `check`/`apply`/`verify`/`review`, dan batasannya. |
| 6 | [format-figures.md](format-figures.md) | Penomoran caption per bab, pembatasan lebar gambar 14 cm, dan penyeragaman border serta margin tabel. |
| 7 | [word-fields.md](word-fields.md) | Sebab nomor TOC bisa `0`, peran `docx-pagenum.py`, dan finalisasi field dengan `make finalize-word`. |
| 8 | [paragraph-ids.md](paragraph-ids.md) | Bookmark `pNNNN`, bentuk `build/manifest.json`, deteksi `kind`, dan aturan `protected`. |
| 9 | [adeu-integration.md](adeu-integration.md) | Alur rekonsiliasi edit Word ke Markdown, exit code `reconcile.py`, dan blok yang dilindungi. |
| 10 | [dotx.md](dotx.md) | Ekspor DOCX ke `.dotx`, perbedaan content type, distribusi template, dan batasan `python-docx`. |
