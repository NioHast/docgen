# Kontrak Coverage

Status: F0 contract, version 1, diamendemen ADR 0010 untuk kebijakan
coverage berbasis risiko.
Sumber: `AUTO_OFFICE_PLAN.md` bagian 12.3, 12.11, 18.9, keputusan L17, dan
[ADR 0010](../decisions/0010-risk-based-coverage.md).
Pemilik kontrak: integration owner.

## Tujuan

Kontrak ini membekukan definisi coverage, target berbasis risiko, kebijakan
exclusion, dan bukti yang diterima gate. Coverage adalah alat risiko, bukan
jaminan correctness: angka tinggi hanya berarti kode dieksekusi, bukan bahwa
assertion memeriksa perilaku yang benar.

## Target berbasis risiko

| Cakupan | Target | Dasar |
| --- | ---: | --- |
| Global line+branch | >= 90.0% | Sinyal kesehatan suite; menahan regresi luas. |
| Modul kritis | 100.0% | Jalur kontrak dan keputusan yang mahal bila salah. |
| Modul adapter | >= 85.0% | Boundary COM, Google, CLI, dan DOCX sulit diuji penuh. |
| Kode baru per commit | 95-99% | Mendorong test untuk perubahan tanpa menuntut angka sempurna. |

Modul kritis:

- `autooffice.deck.model.keys`
- `autooffice.deck.model.bindings`
- `autooffice.deck.layout.grid`
- `autooffice.deck.layout.spec`
- `autooffice.deck.copy.rules.title_case`
- `autooffice.deck.copy.rules.patterns`
- `autooffice.deck.charts.spec`
- `autooffice.deck.transcript.parser`

Modul adapter memakai pola:

- `autooffice.google.*`
- `autooffice.pdf.*`
- `autooffice.cli.*`
- `autooffice.docx.*`

Target kode baru 95-99% adalah target review, bukan ambang gate terpisah.
Perubahan yang menurunkan coverage global, kritis, atau adapter wajib
dijelaskan di PR dan disetujui integration owner.

## Rasional

- Google Testing Blog, *Code Coverage Best Practices*, menempatkan coverage
  sebagai alat menemukan area yang belum diuji. Pengejaran 100% di seluruh repo
  memberi diminishing returns dan mendorong test tanpa assertion.
- CMU SEI, *Don't Play Developer Testing Roulette: How to Use Test Coverage*,
  memperingatkan bahwa partial coverage dapat menyembunyikan risiko. Karena itu
  modul kritis tetap 100%; angka global 90% adalah lantai untuk suite, bukan
  izin melemahkan test pada jalur berisiko.
- Mutation testing, misalnya `mutmut`, menguji kekuatan assertion. Coverage
  100% tetap bisa memiliki mutan yang bertahan; mutation testing menyusul untuk
  modul kritis dan bukan pengganti gate coverage.

Label referensi tersedia di [registry referensi](../dev/references.md#registry).
Target 100% global tidak cost-effective: biaya mengejar baris terakhir lebih
baik dialokasikan ke modul kritis, mutation testing, dan test perilaku.

## Invarian

1. Coverage dihitung hanya untuk `src/autooffice`, bukan test, tools, atau
   contoh.
2. Line dan branch global wajib minimal 90.0%.
3. Setiap modul kritis wajib 100.0% line dan branch.
4. Setiap kelompok adapter wajib minimal 85.0% line dan branch.
5. Gate memakai `--cov-fail-under=90` dan langkah `coverage-policy` setelah
   `tests`.
6. `tools/quality/check_coverage.py` keluar 1 bila kebijakan gagal dan
   mencetak baris serta branch yang hilang.
7. Tidak ada `omit` global untuk modul bisnis.
8. Exclusion default hanya:
   - blok `if TYPE_CHECKING:`;
   - deklarasi `@overload`;
   - baris yang tidak dapat dieksekusi oleh Python karena deklarasi tipe.
9. Exclusion tambahan wajib terdaftar di tabel kontrak ini dengan file, baris
   atau fungsi, alasan, dan approver. Tanpa entri, exclusion tidak sah.
10. Dilarang mengecualikan seluruh file `cli/main.py`, `google/*`, `pdf/*`,
    `docx/*`, atau modul bisnis lain.
11. Dilarang memakai `coverage combine` untuk menutupi modul yang tidak pernah
    dijalankan.
12. COM dan Google diuji dengan fake di unit dan contract test. Jalur nyata
    dijalankan integration test atau smoke final di Windows.
13. Coverage report ditinjau oleh integration owner saat merge dan gate final.
14. Angka 100% tanpa assertion perilaku tetap dianggap gagal oleh test-quality
    checker.
15. Data branch wajib ada; checker menolak `.coverage` tanpa arc branch.

## Exclusion terdaftar

Setiap exclusion tambahan wajib mengisi tabel:

| File | Baris/fungsi | Alasan | Approver | Tanggal |
| --- | --- | --- | --- | --- |
| `src/autooffice/deck/copy/rules/patterns.py` | `parse_closer_key`, baris 171-172 | `_ONE_LINE_CLOSER_KEY` menjamin `index` memuat minimal satu digit, sehingga `numeric is None` tidak dapat terjadi. | integration owner | 2026-11-14 |
| `src/autooffice/deck/transcript/parser.py` | `_start_language`, baris 242-248 | `### English` mensyaratkan `builder.indonesian` sudah ada; `### Indonesia` berikutnya selalu ditangkap cabang duplikat Indonesia di baris 235. | integration owner | 2026-11-14 |
| `src/autooffice/deck/transcript/parser.py` | `_buffer_for`, baris 370-371 | `_buffer_for` hanya dipanggil setelah `_start_language` membuat buffer Indonesia; fallback `builder.indonesian is None` tidak dapat dijangkau lewat parser publik. | integration owner | 2026-11-14 |
| `src/autooffice/deck/transcript/parser.py` | `_buffer_for`, baris 373-374 | `_buffer_for` hanya dipanggil setelah `_start_language` membuat buffer English; fallback `builder.english is None` tidak dapat dijangkau lewat parser publik. | integration owner | 2026-11-14 |

Menghapus entri yang masih dipakai berarti gate harus dijalankan ulang.

## Perintah gate

```bash
uv run pytest --cov=autooffice --cov-branch --cov-fail-under=90
uv run python tools/quality/check_coverage.py
uv run python tools/quality/check_coverage.py --format json
uv run python tools/quality/check_coverage.py --list
uv run python -m coverage html
```

Report terminal harus menunjukkan angka global, setiap modul kritis, dan
setiap kelompok adapter. Report HTML ditulis ke `htmlcov/` dan tidak di-track
Git.

## Contoh

```text
coverage policy: FAIL
PASS global: 92.40% (minimum 90.00%; line 94.10%, branch 88.20%)
FAIL critical autooffice.deck.model.keys: 90.00% (minimum 100.00%; line 90.00%, branch 100.00%)
  autooffice.deck.model.keys: missing lines 4
PASS adapter autooffice.google.*: 86.00% (minimum 85.00%; line 87.00%, branch 82.00%)
```

Contoh ini sah hanya bila test benar-benar mengeksekusi cabang error dan
sukses, bukan karena file di-omit.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan
`tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini
dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Global 90%, kritis 100%, adapter 85% | `tools/quality/check_coverage.py` dan `tests/tools/test_coverage_policy.py`. |
| Gate memakai ambang 90% | Step `tests` di `tools/quality/gate.py`. |
| Tidak ada omit global | Review `pyproject.toml` dan coverage config. |
| Exclusion tertulis | Tabel di halaman ini; review integration owner. |
| Fake COM dan Google | `tests/pdf/**`, `tests/google/**`; bagian 12.7 dan 12.8. |
| Tidak ada whole-file exclusion | Review gate dan tabel exclusion. |
| Report dihasilkan | `htmlcov/` dan terminal report pada gate final. |
| Kebijakan berbasis risiko | [ADR 0010](../decisions/0010-risk-based-coverage.md). |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
