# Kontrak Coverage

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 12.3, 12.11, 18.9, dan keputusan L17.
Pemilik kontrak: integration owner.

## Tujuan

Kontrak ini membekukan definisi coverage, kebijakan exclusion, dan bukti yang
diterima gate. Targetnya bukan angka semata, melainkan keyakinan bahwa jalur
produksi benar-benar dieksekusi.

## Invarian

1. Coverage dihitung hanya untuk `src/autooffice`, bukan test, tools, atau
   contoh.
2. Line coverage dan branch coverage wajib 100%.
3. Gate memakai `--cov-fail-under=100` dan menghasilkan report terminal serta
   HTML.
4. Tidak ada `omit` global untuk modul bisnis.
5. Exclusion default hanya:
   - blok `if TYPE_CHECKING:`;
   - deklarasi `@overload`;
   - baris yang tidak dapat dieksekusi oleh Python karena deklarasi tipe.
6. Exclusion tambahan wajib terdaftar di tabel kontrak ini dengan file,
   baris atau fungsi, alasan, dan approver. Tanpa entri, exclusion tidak sah.
7. Dilarang mengecualikan seluruh file `cli/main.py`, `google/*`, `pdf/*`,
   atau modul bisnis lain.
8. Dilarang memakai `coverage combine` untuk menutupi modul yang tidak pernah
   dijalankan.
9. COM dan Google diuji dengan fake di unit dan contract test. Jalur nyata
   dijalankan integration test atau smoke final di Windows.
10. Coverage report ditinjau oleh integration owner saat merge dan gate final.
    Angka 100% tanpa assertion perilaku tetap dianggap gagal oleh
    test-quality checker.

## Exclusion terdaftar

Belum ada exclusion tambahan per F0. Setiap penambahan wajib mengisi tabel:

| File | Baris/fungsi | Alasan | Approver | Tanggal |
| --- | --- | --- | --- | --- |
| - | - | - | - | - |

Entri `-` bukan exclusion; ia hanya menandai tabel kosong. Menghapus entri
yang masih dipakai berarti gate harus dijalankan ulang.

## Perintah gate

```bash
uv run pytest --cov=autooffice --cov-branch --cov-fail-under=100
uv run python -m coverage html
```

Report HTML ditulis ke `htmlcov/` dan tidak di-track Git. Report terminal
harus menunjukkan 100% untuk line dan branch.

## Contoh

```text
Name                              Stmts   Miss Branch BrPart  Cover
-------------------------------------------------------------------
src/autooffice/deck/copy/rules.py    84      0     32      0   100%
src/autooffice/google/slides.py      61      0     18      0   100%
-------------------------------------------------------------------
TOTAL                              1842      0    512      0   100%
```

Contoh ini sah hanya bila test benar-benar mengeksekusi cabang error dan
sukses, bukan karena file di-omit.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Line dan branch 100% | `pytest --cov-branch --cov-fail-under=100`; F1-TEST dan F3-GATE. |
| Tidak ada omit global | Review `pyproject.toml` dan coverage config. |
| Exclusion tertulis | Tabel di halaman ini; review integration owner. |
| Fake COM dan Google | `tests/pdf/**` (planned), `tests/google/**` (planned); bagian 12.7 dan 12.8. |
| Tidak ada whole-file exclusion | `tools/quality/check_tests.py` (planned) dan review gate. |
| Report dihasilkan | `htmlcov/` dan terminal report pada gate final. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
