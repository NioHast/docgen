# Kontrak Transcript

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 4.15, 8.7, 12.13, dan keputusan L24.
Pemilik kontrak: copy owner.

## Tujuan

Kontrak ini membekukan `transcripts.md` sebagai berkas pendamping opsional
untuk naskah pembicara. Transkrip bukan teks slide, bukan notes, dan bukan
sumber key YAML.

## Invarian

1. Berkas bernama `transcripts.md`, berada di folder deck yang sama dengan
   `deck.yaml`. Keberadaannya opsional.
2. Encoding UTF-8 dengan newline LF.
3. Judul dokumen H1 bebas dan tidak dipakai sebagai key.
4. Satu bagian per slide memakai heading `## <slide_id>. <judul slide>`.
   `<slide_id>` harus cocok dengan slide di YAML, tidak boleh duplikat, dan
   tidak boleh merujuk slide asing.
5. Bila `transcripts.md` ada, semua slide harus punya tepat satu bagian.
   Urutan bagian bebas; mapping memakai ID, bukan posisi array.
6. Heading memakai titik setelah slide ID, bukan em dash atau en dash.
7. `### Indonesia` wajib. `### English` opsional. Bila ada, isi Inggris
   diperiksa dengan rule pack Inggris.
8. `**Perkiraan durasi:** <detik> detik` opsional. Bila ada, nilainya bilangan
   bulat positif.
9. Isi bagian adalah prosa Markdown biasa. Tidak ada key YAML, field
   terstruktur, atau metadata selain durasi.
10. Transkrip tidak disimpan di `deck.yaml`, tidak masuk PPTX notes, dan tidak
    disinkronkan ke Google Slides.
11. Transkrip disalin ke output sebagai `<stem>.transcript.md` di direktori
    output yang sama dengan PPTX. `--out DIR` memindahkan salinan ini juga.
12. Copy checker memeriksa transkrip bila `targets.transcript` bernilai true
    (default). `targets.transcript: true` tanpa `transcripts.md` tidak
    menghasilkan error.
13. Key transkrip untuk diagnostic adalah `sNN.transcript.id` atau
    `sNN.transcript.en`. Diagnostic menyebut file dan line bila tersedia.
14. Parser menolak heading duplikat, slide hilang, slide asing, section bahasa
    yang tidak dikenal, dan durasi tidak valid. Pesan menyebut slide ID dan
    line.

## Bentuk berkas

```markdown
# Transkrip Demo Deck

## s01. Pembuka

### Indonesia

Selamat pagi. Hari ini kita membahas tiga prioritas utama.

### English

Good morning. Today we discuss three main priorities.

**Perkiraan durasi:** 45 detik

## s02. Konteks

### Indonesia

Latar keputusan ini dimulai dari kebutuhan pengguna.
```

Urutan `s02` sebelum `s01` tetap sah karena mapping memakai ID. Semua slide
wajib muncul tepat satu kali.

## Aturan bagian

- Heading `##` adalah batas bagian. Heading `###` adalah bahasa.
- `### Indonesia` wajib. `### English` opsional.
- Isi sebelum `### Indonesia` dianggap error.
- Heading bahasa lain, misalnya `### Deutsch`, ditolak.
- Baris `**Perkiraan durasi:**` hanya boleh muncul sekali per bagian.
- Isi prosa boleh memuat list dan penekanan Markdown, tanpa key YAML.

## Contoh output

```text
examples/demo-deck/
  deck.yaml
  transcripts.md
  out/
    demo-deck.pptx
    demo-deck.pdf
    demo-deck.transcript.md
```

`demo-deck.transcript.md` adalah salinan tervalidasi, bukan hasil sinkronisasi
Google Slides dan bukan pengganti notes.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Parser heading dan ID | `tests/deck/copy/test_transcript.py` (planned); bagian 12.13. |
| Semua slide tercakup | Contract test missing, duplicate, unknown slide. |
| Bilingual | Fixture `id` dan `en`; rule pack terpisah. |
| Durasi | Test batas bilangan positif dan nilai invalid. |
| Output copy | Integration test `build` menulis `<stem>.transcript.md`. |
| Tanpa file tetap valid | `targets.transcript: true` tanpa `transcripts.md` tidak error. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
