# Mutation Testing

Mutation testing manual untuk modul pure-logic kritis AutoOffice. Dokumen ini
mencatat tool, scope, perintah, runtime, dan cara membaca mutant yang bertahan.
Mutation testing bukan bagian gate default.

## Tool dan kompatibilitas

Tool yang dipakai: **cosmic-ray 8.9.0**, dipin di `[project.optional-dependencies].dev`.
Mutmut dicoba lebih dulu karena konfigurasinya lebih ringkas, tetapi gagal
dipasang pada Python 3.15.2 Windows. Rantai dependensinya `mutmut -> libcst ->
pyyaml`; PyYAML 6.0.3 tidak menyediakan wheel `cp315-win_amd64`, sehingga uv
membangun dari sdist dan berhenti dengan:

```text
error: Microsoft Visual C++ 14.0 or greater is required. Get it with
"Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

Environment ini tidak memiliki compiler MSVC, jadi mutmut tidak dipaksakan.
Cosmic-ray 8.9.0 dan dependensinya terpasang dari wheel pada Python 3.15.2.

## Scope

Target penuh ada di `tools/mutation/cosmic-ray.toml` dan sama dengan modul
critical coverage (1.248 mutant saat dokumen ini ditulis):

- `autooffice.deck.model.keys`
- `autooffice.deck.model.bindings`
- `autooffice.deck.layout.spec`
- `autooffice.deck.copy.rules.title_case`
- `autooffice.deck.charts.spec`

Untuk iterasi cepat ada scope kecil `tools/mutation/cosmic-ray-title-case.toml`
(81 mutant) yang menjalankan test Title Case saja. Scope kecil dipakai untuk
smoke run pertama; scope penuh dijalankan berkala karena jauh lebih mahal.

## Perintah

```bash
uv sync --extra dev
mkdir -p .autooffice-build/mutation

# Scope penuh.
uv run --no-sync cosmic-ray init tools/mutation/cosmic-ray.toml \
    .autooffice-build/mutation/critical.sqlite
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --no-sync cosmic-ray exec \
    tools/mutation/cosmic-ray.toml .autooffice-build/mutation/critical.sqlite

# Scope kecil Title Case.
uv run --no-sync cosmic-ray init tools/mutation/cosmic-ray-title-case.toml \
    .autooffice-build/mutation/title-case.sqlite
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --no-sync cosmic-ray exec \
    tools/mutation/cosmic-ray-title-case.toml .autooffice-build/mutation/title-case.sqlite
```

Baseline sebelum sesi mutasi:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --no-sync cosmic-ray baseline \
    tools/mutation/cosmic-ray-title-case.toml
```

Dump hasil sesi (satu baris JSON per mutant):

```bash
uv run --no-sync cosmic-ray dump \
    .autooffice-build/mutation/title-case.sqlite > results.jsonl
```

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` hanya mematikan autoload plugin pytest yang
tidak dipakai test ini (coverage dan hypothesis). Tanpa itu, setiap mutant
membayar import plugin dan runtime naik sekitar dua kali.

## Hasil awal 2026-11-14

- Environment: Windows, Python 3.15.2, cosmic-ray 8.9.0.
- Scope: `deck/copy/rules/title_case.py`, 81 mutant.
- Runtime: 4 menit 22 detik wall clock.
- Hasil: 59 killed, 22 survived, 0 incompetent.
- Mutation score: **72,8%** (59/81).

## Membaca survivor

Mutation score adalah diagnostik, bukan target. Baca diff tiap survivor dan
klasifikasikan sebelum mengubah test:

- **Equivalent mutant**: perilaku tidak benar-benar berubah. Contoh pada run
  ini: `*` pada signature berubah menjadi `/` oleh operator binary, atau
  `index == len(tokens) - 1` menjadi `>=` yang ekuivalen untuk indeks
  non-negatif. Tidak perlu dikejar.
- **Assertion gap**: test hanya memeriksa pesan, bukan `offset`. Sebelas
  mutant `offset=len(text.rstrip()) - 1` bertahan karena offset tidak pernah
  di-assert.
- **Boundary gap**: `first`/`last` dan `max(position, 0)` tidak diuji pada
  batas token; mutan `== 0` menjadi `<= 0` dan perubahan konstanta bertahan.
- **Control-flow gap**: `continue` yang berubah menjadi `break` bertahan karena
  belum ada judul dengan token tanda baca saja atau kata invalid setelah kata
  fungsi di tengah.

Survivor adalah pertanyaan: assertion apa yang hilang, atau apakah mutannya
ekuivalen? Jangan mengubah production code atau test hanya untuk menaikkan
skor; catat survivor dan serahkan keputusan ke owner modul. Lihat juga
[test-quality.md](test-quality.md).

## Kenapa bukan gate default

Satu modul kecil butuh lebih dari empat menit; scope penuh jauh lebih lama dan
tidak sebanding dengan feedback loop gate. Mutation testing dijalankan manual
saat menyentuh modul kritis atau sebagai audit berkala, bukan pada setiap
perubahan. Gate default tetap memakai coverage berbasis risiko dan checker
deterministik; lihat [quality-gates.md](quality-gates.md).
