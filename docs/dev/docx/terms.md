# Istilah dan Glosarium

Halaman ini menjelaskan fitur glosarium, penanda istilah, verifikasi, dan audit
DOCX. Kontrak API ada di [../contracts/docx-api.md](../contracts/docx-api.md);
kontrak stage ada di [../contracts/stage-api.md](../contracts/stage-api.md).
Glosarium menentukan istilah asing yang ditulis miring. Stage `terms`
menerapkan style, memverifikasi invariant, dan menulis daftar tinjauan. Stage
ini hanya aktif bila build memakai `--terms`.

## Berkas glosarium

Glosarium paket berada di:

```text
src/docgen/data/glossary/istilah.tsv
```

Glosarium pengguna opsional berada di samping `document.md`:

```text
istilah.tsv
```

Format TSV wajib memakai header `term` dan `italic`:

```tsv
term	italic
machine learning	yes
data	no
```

Header wajib persis `term<TAB>italic`; header lain ditolak dengan error
`GLOSSARY-HEADER`. Setiap baris harus memiliki tepat dua kolom. Nilai
`italic` hanya `yes` atau `no`. Baris kosong dan baris berawalan `#`
diabaikan.

Pencocokan istilah:

- case-insensitive;
- hanya cocok sebagai kata utuh, bukan bagian kata lain;
- entri pengguna menimpa entri paket dengan kunci casefold yang sama;
- entri pengguna lain ditambahkan ke glosarium paket.

Presedensi: pengguna di atas paket.

## Penanda istilah

Bila istilah belum diputuskan, tulis:

```markdown
Sistem memakai {{?machine learning?}} untuk klasifikasi.
```

Penanda yang valid adalah `{{?` diikuti isi non-kosong dan diakhiri `?}}`.
Isi tidak boleh memuat `{{`, `}}`, atau newline. Penanda kosong atau tidak
tertutup menghasilkan error saat stage `terms` berjalan.

Tanpa `--terms`, tidak ada pemrosesan penanda, tidak ada review file, dan
tidak ada verifikasi.

## Stage `terms`

Stage berjalan pada package DOCX setelah Pandoc dan sebelum TOC:

1. Muat glosarium paket.
2. Muat dan gabungkan `istilah.tsv` pengguna bila ada.
3. Kumpulkan penanda dari Markdown.
4. Terapkan style pada istilah dan penanda.
5. Verifikasi invariant.
6. Tulis `.laporan/istilah-baru.txt`.

Perilaku penanda:

- kurung `{{?` dan `?}}` dihapus dari teks;
- isi penanda diberi style `IstilahReview`;
- isi penanda masuk daftar review;
- build tidak otomatis gagal hanya karena ada penanda.

Style:

| Style | Efek |
| --- | --- |
| `IstilahAsing` | Italic dan `w:lang en-US`. |
| `IstilahReview` | Highlight kuning untuk istilah yang perlu keputusan. |

## Verifikasi

`verify_terms` memeriksa:

- istilah `italic: yes` harus memakai style `IstilahAsing`;
- run `IstilahAsing` harus efektif italic dan memakai `en-US`;
- istilah `italic: no` tidak boleh miring atau memakai `IstilahAsing`;
- run `IstilahAsing` harus berisi istilah yang ada di glosarium;
- penanda yang masih tersisa adalah pelanggaran;
- formatting italic manual tanpa style dilaporkan sebagai peringatan.

Pelanggaran menggagalkan build dengan `TermsError` dan exit code 1. Perbaiki
naskah atau glosarium, bukan DOCX.

## Review file

`--terms` selalu menulis:

```text
.laporan/istilah-baru.txt
```

Isinya satu istilah per baris, unik, deterministik, tanpa timestamp. File ini
adalah daftar keputusan, bukan output dokumen. Setelah istilah diputuskan:

1. ganti penanda di `document.md` dengan istilah yang benar; atau
2. tambahkan entri ke `istilah.tsv`;
3. build ulang.

## Audit DOCX

`tools/dev/audit_terms.py` memeriksa DOCX hasil build tanpa mengubahnya:

```bash
uv run --project <repo> python tools/dev/audit_terms.py \
  --docx Tugas.docx \
  --glossary src/docgen/data/glossary/istilah.tsv \
  --out .laporan/istilah-audit.md
```

Alat ini menulis laporan Markdown dan mengembalikan exit code 2 bila ada
istilah yang perlu diperbaiki atau diputuskan. Alat tidak mengubah DOCX,
glosarium, atau naskah.

## API package

`docx/terms/` menyediakan:

- `load_glossary` dan `merge_glossaries`;
- `apply_terms` untuk style `IstilahAsing` dan `IstilahReview`;
- `verify_terms` untuk memeriksa invariant;
- `write_review_file` untuk `.laporan/istilah-baru.txt`.

Stage `terms` memakai API ini; stage tidak memuat atau menyimpan package
target sendiri. Lihat [../pipeline/stages.md](../pipeline/stages.md) untuk
posisi stage.

## Batasan

- Glosarium hanya mengatur italic istilah, bukan padanan atau definisi.
- Istilah di dalam field atau hyperlink eksternal tidak diubah; penanda di
  sana dilaporkan sebagai peringatan atau pelanggaran.
- Bibliografi dilewati agar sitasi tidak diubah.
- Stage `terms` tidak berjalan tanpa `--terms`.
