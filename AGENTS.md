# AGENTS.md — Panduan Cepat

## Pilih struktur

| Kebutuhan | Struktur | Penomoran |
| --- | --- | --- |
| Tesis (5 bab, daftar isi) | `thesis` | `BAB_ROMAN` |
| Proposal tesis (4 bab) | `proposal` | `ARABIC_DOTTED` |
| Tugas kuliah (3 bab) | `assignment` | `ARABIC_DOTTED` |

Format yang tersedia: `undip-msi`. Aturan visual ada di `formats/`, urutan bab di `structures/`.

## Alur kerja

```bash
# 1. Lihat pilihan
python -m laporan list

# 2. Buat proyek konten
python -m laporan new assignment --format undip-msi --out tugas

# 3. Edit metadata.yml dan chapters/*.md (Markdown + sitasi BibTeX)

# 4. Validasi
python -m laporan check tugas

# 5. Build DOCX (atau --target pdf / both)
python -m laporan build tugas --target docx

# 6. Cek perkakas
python -m laporan doctor
```

## Aturan

- Satu sumber kebenaran: struktur menentukan urutan bab, format menentukan preset.
- Jangan menyalin logika `build-docx.sh` atau `build.sh`; `build` hanya memanggil keduanya.
- Jangan mengedit artefak hasil build: `Laporan.docx`, `Laporan.pdf`, `build/manifest*.json`, `review/`, dan `acuan/`.
- Jangan mengubah `chapters/`, `presets/`, `tools/`, atau tes lama saat menambah konten contoh.
- Jalankan `check` sebelum `build`; perbaiki bab yang hilang, bukan menghapusnya dari struktur.
