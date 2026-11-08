# Indeks Dokumentasi

Dokumentasi dibagi menjadi dua kelompok:

| Kelompok | Untuk siapa | Mulai dari |
| --- | --- | --- |
| [dev/](dev/architecture.md) | Pengembang dan pemelihara pipeline | [dev/architecture.md](dev/architecture.md) |
| [agent/](agent/README.md) | Penulis dan agent yang mengerjakan naskah | [agent/README.md](agent/README.md) |

Kembali ke [README utama](../README.md).

## Untuk agent

| Dokumen | Isi |
| --- | --- |
| [agent/README.md](agent/README.md) | Indeks panduan agent. |
| [agent/quickstart.md](agent/quickstart.md) | Lima langkah memilih struktur, menulis, check, build, dan output. |
| [agent/document-format.md](agent/document-format.md) | Front matter, heading, caption, gambar, Mermaid, dan sitasi. |
| [agent/writing-rules.md](agent/writing-rules.md) | Ringkasan aturan prosa dan cara menjalankan checker. |
| [agent/troubleshooting.md](agent/troubleshooting.md) | Masalah caption, `mmdc`, Word/LibreOffice, `ruamel.yaml`, dan path. |
| [agent/single-file.md](agent/single-file.md) | Mode satu berkas Markdown dengan `build-file`. |
| [agent/mermaid.md](agent/mermaid.md) | Diagram Mermaid inline dan renderer `mmdc`. |
| [../writing/guide.md](../writing/guide.md) | Panduan menulis lengkap. |

## Untuk pengembang

### Arsitektur dan pipeline

| Dokumen | Isi |
| --- | --- |
| [dev/architecture.md](dev/architecture.md) | Empat lapis format, struktur, konten, dan platform; kontrak CLI serta build. |
| [dev/proposal.md](dev/proposal.md) | Pipeline proposal tesis MSI dan preset `undip-msi-proposal`. |
| [dev/pdf.md](dev/pdf.md) | Ekspor PDF dari DOCX final melalui Word COM atau LibreOffice. |
| [dev/style-generator.md](dev/style-generator.md) | Generator `reference.docx` dari preset. |

### Format DOCX

| Dokumen | Isi |
| --- | --- |
| [dev/format-undip.md](dev/format-undip.md) | Format UNDIP, margin, heading, caption, dan sitasi author-date. |
| [dev/format-figures.md](dev/format-figures.md) | Caption wajib, penomoran per bab, lebar gambar, dan tabel. |
| [dev/format-code.md](dev/format-code.md) | Blok kode menjadi tabel 1x1. |
| [dev/format-equations.md](dev/format-equations.md) | Penomoran persamaan OMML. |
| [dev/format-numbering.md](dev/format-numbering.md) | Penyeragaman daftar bernomor. |
| [dev/normalize-layout.md](dev/normalize-layout.md) | Spasi, perataan, dan penghapusan bold langsung. |
| [dev/word-fields.md](dev/word-fields.md) | Field DOCX dan nomor halaman daftar isi. |
| [dev/dotx.md](dev/dotx.md) | Ekspor dan distribusi template `.dotx`. |

### Istilah dan prosa

| Dokumen | Isi |
| --- | --- |
| [dev/terms.md](dev/terms.md) | Glosarium, penanda `{{?istilah?}}`, dan perintah `terms.py`. |
| [dev/audit-terms.md](dev/audit-terms.md) | Audit italic istilah pada DOCX hasil build. |
| [dev/prosa.md](dev/prosa.md) | Pemeriksa prosa dan kode temuan. |

### Review dan paragraf

| Dokumen | Isi |
| --- | --- |
| [dev/paragraph-ids.md](dev/paragraph-ids.md) | Bookmark `pNNNN`, manifest, dan status `protected`. |
| [dev/adeu-integration.md](dev/adeu-integration.md) | Rekonsiliasi edit Word ke Markdown. |

### Deployment

| Dokumen | Isi |
| --- | --- |
| [dev/deployment/windows.md](dev/deployment/windows.md) | Deployment Windows-native dengan Git Bash dan Word. |
| [dev/deployment/debian.md](dev/deployment/debian.md) | Deployment Debian-native dengan Pandoc dan LibreOffice. |
