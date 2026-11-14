# Humanizer AutoOffice

Halaman ini menjelaskan batas antara aturan naskah yang diperiksa mesin dan
bagian yang tetap menjadi penilaian editor. Kontrak normatifnya ada di
[kontrak copy](../contracts/copy.md); halaman ini adalah panduan kerja, bukan
gate tambahan.

Copy checker AutoOffice deterministik: tidak ada LLM, tidak ada jaringan, dan
tidak ada pemeriksaan selera. Yang bisa diperiksa secara mekanis masuk gate.
Yang membutuhkan konteks, angka, atau sumber tetap menjadi checklist editorial.

## Yang diperiksa mesin

| Rule | Yang ditolak | Sifat |
| --- | --- | --- |
| `banned_phrases` | Frasa stok Indonesia dan Inggris | error |
| `title_case` | Judul yang bukan Title Case, berakhir titik, atau memuat koma | error |
| `dash` | Em dash U+2014 dan en dash U+2013 | error |
| `negative_parallelism` | `bukan hanya ... tetapi juga` dan padanannya | error |
| `contrast_pattern` | Pola `, bukan ` | error |
| `sentence_length` | Kalimat lebih dari 25 kata (dapat dikonfigurasi) | warning |
| `forced_triad` | Tiga frasa `A, B, dan C` yang dipaksakan | warning |
| `one_line_closer` | Item terakhir grup body/text yang kurang dari enam kata | warning |
| `paired_clause_label` | Label dua fragmen tanpa verba, maksimal delapan kata | warning |

Error menghentikan build sebelum layout. Warning dicetak dan build tetap jalan.
Escape hatch hanya `copy.yaml`: severity, disable, atau allowlist dengan alasan.
Allowlist tidak menekan error schema dan tidak menekan kegagalan transkrip.

## Yang tidak bisa diperiksa mesin

Beberapa masalah hanya terlihat dari maksud, bukti, dan konteks. Jangan
menambahkan heuristik rapuh untuk hal-hal berikut; tinjau manual.

### Klaim tanpa bukti

Superlatif seperti "terbaik", "terdepan", atau "paling lengkap" membutuhkan
angka, sumber, atau perbandingan. Ganti dengan ukuran yang bisa diuji.

- Lemah: "Peningkatan yang signifikan."
- Lebih baik: "Naik 8,3 persen dibanding kuartal sebelumnya."

### Atribusi samar

"Banyak ahli mengatakan", "berbagai studi menunjukkan", dan "diyakini bahwa"
tidak memberi pembaca sumber yang bisa diperiksa. Sebut nama lembaga, tahun,
atau tautan singkat. Bila sumber tidak ada, hapus klaimnya.

### Kata stok yang lolos daftar

Daftar `banned_phrases` hanya menangkap frasa yang sudah dikenal. Kata seperti
"optimal", "holistik", atau "komprehensif" tetap perlu dinilai dari konteks.
Tanyakan apakah kata itu membatasi makna atau hanya menambah kesan penting.

### Pembuka bertahap

"Di tengah perkembangan zaman", "pada akhirnya", dan "tidak dapat dipungkiri"
menunda inti. Mulai dari angka, keputusan, atau nama hal yang dibahas.

### Irama dan kepadatan

Kalimat pendek bukan tujuan akhir. Naskah yang hanya berisi potongan pendek
juga melelahkan. Periksa apakah setiap kalimat membawa satu fakta, keputusan,
atau alasan yang berbeda.

### Hubungan antaride

Triad yang sah, daftar panjang, dan label pendek bisa benar bila hubungannya
jelas. Yang salah adalah pola yang memaksa pembaca menebak hubungan antar
fragmen. Ganti dengan satu frasa benda yang memakai pewatas.

## Checklist editorial

- Setiap klaim penting punya angka, nama, atau sumber.
- Tidak ada superlatif tanpa pembanding.
- Tidak ada atribusi samar.
- Setiap kalimat membawa satu informasi baru.
- Pembuka langsung menyebut hal konkret.
- Daftar memakai jumlah item sesuai isi, bukan demi irama.
- Label dua fragmen sudah diganti frasa benda yang jelas.
- Istilah teknis dan angka tidak diubah hanya demi gaya.
- Transkrip Indonesia dan Inggris menyampaikan isi yang sama.

## Alur kerja

1. Tulis naskah dalam bahasa utama deck.
2. Jalankan copy checker lewat build atau `check`.
3. Perbaiki seluruh error.
4. Tinjau warning; allowlist hanya bila ada alasan yang bisa ditulis.
5. Jalankan checklist editorial di atas sebelum review manusia.

Untuk aturan transkrip, lihat [kontrak transcript](../contracts/transcript.md).
Untuk aturan schema dan severity, lihat [kontrak copy](../contracts/copy.md).
