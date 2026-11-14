# Kontrak Copy

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 4.16, 8.7, 12.13, dan keputusan L23-L25.
Pemilik kontrak: copy owner.

## Daftar Isi

- [Tujuan](#tujuan)
- [Invarian](#invarian)
- [Tabel rule](#tabel-rule)
- [Teks tampil](#teks-tampil)
- [Detail heuristik](#detail-heuristik)
- [Diagnostic](#diagnostic)
- [Contoh copy.yaml](#contoh-copyyaml)
- [Pemetaan acceptance](#pemetaan-acceptance)

## Tujuan

Kontrak ini membekukan copy checker deterministik sebagai stage first-class
untuk deck. Checker tidak memanggil LLM, layanan network, atau Office. Aturan
yang tidak bisa diperiksa secara mekanis tetap menjadi checklist editorial di
[humanizer.md](../learn/humanizer.md), bukan gate.

## Invarian

1. Copy checker berjalan sebelum layout. Input: Deck IR, Transcript IR, dan
   `copy.yaml`. Output: daftar diagnostic. Rule memeriksa teks tampil, bukan
   Markdown mentah: label link dipertahankan; tujuan link, autolink, URL
   telanjang, penanda daftar, emphasis, dan backtick dibuang. `source.text`
   diperiksa sebagai prosa.
2. Checker deterministik dan tidak bergantung pada waktu, urutan dictionary,
   locale, atau network.
3. Target default: `slides: true`, `notes: true`, `transcript: true`. Bila
   blok `targets` tidak ditulis, ketiganya berlaku.
4. `targets.transcript: true` tanpa `transcripts.md` tidak menghasilkan
   error. Transkrip tetap opsional. Allow entry ber-key transkrip tetap valid
   tetapi inert bila transkrip tidak ada atau `targets.transcript: false`;
   kondisi itu bukan stale key.
5. DOCX tidak memakai humanizer, tidak membaca `copy.yaml`, dan tetap memakai
   `--terms`.
6. `meta.language` dinormalisasi menjadi `id` atau `en`: lowercase dan ambil
   subtag utama (`id-ID` menjadi `id`, `en-US` menjadi `en`). Bahasa lain
   ditolak sebagai error schema tanpa fallback diam-diam.
7. Teks slide dan notes memakai rule pack bahasa utama:
   - `id`: semua rule.
   - `en`: `banned_phrases` versi Inggris, `dash`, `sentence_length`, dan
     `negative_parallelism`.
   - `title_case` hanya berlaku untuk slide title berbahasa Inggris, bukan
     prosa Inggris.
8. Transkrip memilih rule pack dari heading `### Indonesia` atau
   `### English`, bukan dari `meta.language`.
9. Error menghentikan build sebelum layout. Warning dicetak dan build tetap
   jalan. Tidak ada flag untuk melewati checker; escape hatch hanya
   `copy.yaml`.
10. Path `copy.yaml` di-resolve sebelum dibaca. `..` boleh dipakai selama
    berkas hasil resolve tetap berada di dalam folder deck; path yang resolve
    ke luar deck ditolak. `load_copy_config` mandiri tanpa `deck_dir` hanya
    me-resolve path dan tidak dapat menegakkan containment deck.
11. Merge dilakukan per rule. Key yang tidak ditulis memakai default.
    `enabled: false` atau `severity: off` mematikan rule. `allow` wajib punya
    `reason`, `key` harus ada, dan `rules` harus nama rule yang dikenal.
    `allow` hanya menekan diagnostic yang cocok, bukan error schema atau
    kegagalan transcript.
12. `extra` adalah map per bahasa (`id`, `en`) berisi frasa literal, bukan
    regex. Frasa `id` hanya diperiksa pada teks Indonesia; frasa `en` hanya
    pada teks Inggris.
13. Atribusi: aturan diadaptasi dari deck-studio. Arsip verbatim tidak
    menjadi runtime dan tidak disalin ke repo.

## Tabel rule

| Rule | Severity default | Cakupan | Perilaku |
| --- | --- | --- | --- |
| `banned_phrases` | error | semua prosa | Frasa literal dari daftar Indonesia/Inggris; apostrof tipografis dinormalisasi dan varian infleksi yang terdaftar eksplisit ikut diperiksa. |
| `title_case` | error | slide title | Title Case per bahasa; skrip tanpa kapitalisasi diterima; tanpa titik akhir, tanpa koma. |
| `dash` | error | semua prosa | Menolak U+2014 dan U+2013. |
| `negative_parallelism` | error | semua prosa | Menolak `bukan hanya ... tetapi juga`, `tidak hanya ... tetapi juga`, `bukan hanya ... tapi juga`, `tidak hanya ... tapi juga`, `bukan hanya ... melainkan juga`, `tidak hanya ... melainkan juga` dalam jarak 200 karakter. |
| `contrast_pattern` | error | semua prosa | Menolak pola `, bukan `. |
| `sentence_length` | warning | semua prosa | Kalimat lebih dari `max_words` (default 25); penanda daftar tidak dihitung dan kutip penutup dikenali sebagai batas kalimat. |
| `forced_triad` | warning | semua prosa | Regex `[^\s,.;:!?][^,.;:!?]*,\s*[^,.;:!?]+,\s*dan\s+[^,.;:!?]+` dalam satu kalimat. |
| `one_line_closer` | warning | body/text keys | Grup minimal 3 item; item berindeks tertinggi dianggap closer bila kurang dari 6 kata. |
| `paired_clause_label` | warning | teks tampil | Dua fragmen dipisah satu koma, masing-masing tanpa verba dan total maksimal 8 kata. |

`forced_triad`, `one_line_closer`, dan `paired_clause_label` adalah warning
dan tidak menghentikan build.

## Teks tampil

Semua rule memeriksa hasil `render_visible_text`, bukan Markdown mentah.

- Label link inline `[label](tujuan)` dipertahankan; tujuan link dibuang.
- Autolink `<https://...>` dan URL telanjang `https://...` atau `www....`
  dibuang.
- Penanda daftar di awal baris (`- `, `* `, `+ `, `1. `, `1) `), penanda
  emphasis (`*`, `_`, `~`), dan backtick kode dibuang. Underscore di dalam
  kata dipertahankan.
- Peta offset menjaga nomor baris diagnostic tetap menunjuk teks asal.
- `source.text` diperiksa sebagai prosa biasa; ia bukan title dan bukan teks
  display, sehingga `title_case` dan `paired_clause_label` tidak berlaku.

## Detail heuristik

`banned_phrases`:

- Pencocokan case-insensitive dengan batas kata.
- Apostrof tipografis U+2018 dan U+2019 dinormalisasi menjadi `'` pada teks
  dan frasa; `in today’s` cocok dengan `in today's`.
- Daftar default memuat varian infleksi eksplisit, misalnya `align with`,
  `aligns with`, `aligned with`, `aligning with`, serta `delve`, `delved`,
  `delves`, dan `delving`.
- `extra` menambah frasa literal, bukan regex.

`title_case`:

- Tokenisasi per whitespace; strip tanda baca di tepi token.
- Kata pertama dan terakhir selalu kapital.
- Kata fungsi di tengah lowercase. Daftar `id` memakai `LOWERCASE_WORDS`
  deck-studio. Daftar `en`: a, an, and, as, at, but, by, for, from, in, nor,
  of, on, or, per, the, to, via, vs.
- Kata lain kapital; akronim dan istilah teknis yang seluruhnya kapital
  dipertahankan; angka diizinkan.
- Skrip tanpa huruf besar/kecil (misalnya CJK, Arab, Ibrani, Thai) diterima
  tanpa kapitalisasi paksa.
- Tidak boleh ada titik akhir atau koma.
- Tidak berlaku untuk notes atau transkrip.

`sentence_length`:

- Kalimat dipisah pada `.`, `!`, atau `?` yang diikuti whitespace, termasuk
  bila ada kutip penutup `”`, `"`, `’`, atau `'` sebelum whitespace.
- Teks tanpa tanda akhir dianggap satu kalimat.
- Penanda daftar `-`, `*`, `+`, `1.`, dan `1)` di awal baris tidak dihitung
  sebagai kata.
- Kalimat yang melebihi `max_words` (default 25) dilaporkan.

`one_line_closer` memakai key yang valid, misalnya `s07.points.item3.text`.
Regex `^(.*)\.((?:[A-Za-z]+)?\d+)\.(body|text)$` tidak boleh salah membaca
`item3` sebagai angka tanpa awalan. Rule ini hanya berlaku untuk grup key
block `body`/`text`; notes dan transkrip tidak memakai rule ini.

`paired_clause_label`:

- Tepat satu koma.
- Tidak diakhiri titik, tanda tanya, tanda seru, titik dua, titik koma, atau
  newline.
- Maksimal 8 kata.
- Setiap fragmen memuat kata minimal 3 huruf.
- Tidak ada verba di kedua fragmen.
- Verba dideteksi dari `KNOWN_VERBS` dan awalan `me`, `men`, `mem`, `meng`,
  `meny`, `menge`, `di`, `ber`, `ter` yang diikuti minimal dua huruf.

## Diagnostic

Setiap diagnostic wajib memuat `rule`, `severity`, `key`, `file`, `line` bila
tersedia, `message`, dan `hint`. Key slide memakai `sNN.title`, `sNN.notes`,
atau key block. Key transkrip memakai `sNN.transcript.id` atau
`sNN.transcript.en`. Diagnostic error menghentikan build sebelum layout.
`copy.yaml` yang kosong, hanya berisi komentar, atau berisi dokumen YAML
`null` dilaporkan sebagai error `tidak boleh kosong`.

## Contoh `copy.yaml`

```yaml
schema: 1

targets:
  slides: true
  notes: true
  transcript: true

rules:
  banned_phrases:
    severity: error
    extra:
      id: ["frasa yang dilarang"]
      en: ["phrase to ban"]
  title_case:
    severity: error
  dash:
    severity: error
  sentence_length:
    severity: warning
    max_words: 25
  negative_parallelism:
    severity: error
  contrast_pattern:
    severity: error
  forced_triad:
    severity: warning
  one_line_closer:
    severity: warning
  paired_clause_label:
    severity: warning

allow:
  - key: "s05.chart.title"
    rules: [sentence_length]
    reason: "Label chart pendek"
```

## Pemetaan acceptance

| Invarian | Bukti |
| --- | --- |
| Teks tampil dan `source.text` | `tests/deck/copy/test_copy_correctness.py`. |
| Rule positif, negatif, batas | `tests/deck/copy/test_rules.py`; bagian 12.13. |
| Merge config, severity, dan path | `tests/deck/copy/test_copy_config.py`; `test_copy_correctness.py`. |
| Rule pack bilingual | `tests/deck/copy/test_language.py`. |
| Transcript mapping dan allow inert | `tests/deck/copy/test_transcript.py`; `test_copy_correctness.py`. |
| Golden diagnostic | `tests/golden/copy/demo.json` (planned); F1-COPY. |
| Build gagal pada error | Integration `tests/deck/copy/test_build_gate.py` (planned). |
| Tanpa network atau LLM | `tests/deck/copy/test_checker.py`; bagian 8.7. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
