# Kontrak Copy

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 4.16, 8.7, 12.13, dan keputusan L23-L25.
Pemilik kontrak: copy owner.

## Daftar Isi

- [Tujuan](#tujuan)
- [Invarian](#invarian)
- [Tabel rule](#tabel-rule)
- [Detail heuristik](#detail-heuristik)
- [Diagnostic](#diagnostic)
- [Contoh copy.yaml](#contoh-copyyaml)
- [Pemetaan acceptance](#pemetaan-acceptance)

## Tujuan

Kontrak ini membekukan copy checker deterministik sebagai stage first-class
untuk deck. Checker tidak memanggil LLM, layanan network, atau Office. Aturan
yang tidak bisa diperiksa secara mekanis tetap menjadi checklist editorial di
`docs/learn/humanizer.md`, bukan gate.

## Invarian

1. Copy checker berjalan sebelum layout. Input: Deck IR, Transcript IR, dan
   `copy.yaml`. Output: daftar diagnostic.
2. Checker deterministik dan tidak bergantung pada waktu, urutan dictionary,
   locale, atau network.
3. Target default: `slides: true`, `notes: true`, `transcript: true`. Bila
   blok `targets` tidak ditulis, ketiganya berlaku.
4. `targets.transcript: true` tanpa `transcripts.md` tidak menghasilkan
   error. Transkrip tetap opsional.
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
10. `copy.yaml` harus berada di folder deck yang sama dengan YAML. Path
    traversal ditolak. Schema strict; key unknown ditolak.
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
| `banned_phrases` | error | semua prosa | Frasa literal dari daftar Indonesia/Inggris. |
| `title_case` | error | slide title | Title Case per bahasa, tanpa titik akhir, tanpa koma. |
| `dash` | error | semua prosa | Menolak U+2014 dan U+2013. |
| `negative_parallelism` | error | semua prosa | Menolak `bukan hanya ... tetapi juga`, `tidak hanya ... tetapi juga`, `bukan hanya ... tapi juga`, `tidak hanya ... tapi juga`, `bukan hanya ... melainkan juga`, `tidak hanya ... melainkan juga` dalam jarak 200 karakter. |
| `contrast_pattern` | error | semua prosa | Menolak pola `, bukan `. |
| `sentence_length` | warning | semua prosa | Kalimat lebih dari `max_words` (default 25). |
| `forced_triad` | warning | semua prosa | Regex `[^\s,.;:!?][^,.;:!?]*,\s*[^,.;:!?]+,\s*dan\s+[^,.;:!?]+` dalam satu kalimat. |
| `one_line_closer` | warning | body/text keys | Grup minimal 3 item; item berindeks tertinggi dianggap closer bila kurang dari 6 kata. |
| `paired_clause_label` | warning | teks tampil | Dua fragmen dipisah satu koma, masing-masing tanpa verba dan total maksimal 8 kata. |

`forced_triad`, `one_line_closer`, dan `paired_clause_label` adalah warning
dan tidak menghentikan build.

## Detail heuristik

`title_case`:

- Tokenisasi per whitespace; strip tanda baca di tepi token.
- Kata pertama dan terakhir selalu kapital.
- Kata fungsi di tengah lowercase. Daftar `id` memakai `LOWERCASE_WORDS`
  deck-studio. Daftar `en`: a, an, and, as, at, but, by, for, from, in, nor,
  of, on, or, per, the, to, via, vs.
- Kata lain kapital; akronim dan istilah teknis yang seluruhnya kapital
  dipertahankan; angka diizinkan.
- Tidak boleh ada titik akhir atau koma.
- Tidak berlaku untuk notes atau transkrip.

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

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Rule positif, negatif, batas | `tests/deck/copy/test_rules.py` (planned); bagian 12.13. |
| Merge config dan severity | `tests/deck/copy/test_config.py` (planned). |
| Rule pack bilingual | `tests/deck/copy/test_language.py` (planned). |
| Transcript mapping | `tests/deck/copy/test_transcript.py` (planned). |
| Golden diagnostic | `tests/golden/copy/demo.json` (planned); F1-COPY. |
| Build gagal pada error | Integration `tests/deck/copy/test_build_gate.py` (planned). |
| Tanpa network atau LLM | Contract test dan checker; bagian 8.7. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
