# Kontrak State Google

Status: F0 contract, version 1
Sumber: `AUTO_OFFICE_PLAN.md` bagian 9 (9.1-9.8), 8.4, dan keputusan L09,
L11, L22, A15, dan A22.
Pemilik kontrak: Google owner.

## Daftar Isi

- [Tujuan](#tujuan)
- [Identitas](#identitas)
- [Layout tab](#layout-tab)
- [Linked chart dan placeholder](#linked-chart-dan-placeholder)
- [State JSON](#state-json)
- [Ownership dan OAuth](#ownership-dan-oauth)
- [Preflight table native](#preflight-table-native)
- [Urutan kegagalan](#urutan-kegagalan)
- [Pemetaan acceptance](#pemetaan-acceptance)

## Tujuan

Kontrak ini membekukan identitas spreadsheet, tab, chart, bentuk state JSON,
linked chart, dan preflight table native. State bukan sumber kebenaran
konten; ia hanya mencatat objek remote yang dimiliki satu deck.

## Identitas

1. Satu spreadsheet per deck, satu tab per chart, satu chart object per tab.
2. `chart_id` logis adalah `<slide_id>.<block_id>`, misalnya `s04.chart1`.
   `chart_id` unik per deck.
3. `tab_name` adalah `chart_id` bila aman dan tidak bentrok. Bila lebih dari
   100 karakter, potong dan tambah hash 8 karakter.
4. Nama spreadsheet adalah `AutoOffice Charts - <meta.title>`.
5. Nama tab stabil. Rename tab tidak boleh mengubah `chart_id`.
6. State menyimpan `chart_id`, `tab_name`, `sheet_id`, dan
   `embedded_chart_id` per chart.

## Layout tab

```text
A1: Category      B1: Seri 1      C1: Seri 2
A2: Q1            B2: 12          C2: 20
A3: Q2            B3: 18          C3: 29
A4: Q3            B4: 27          C4: 41
A5: Q4            B5: 35          C5: 52
```

Untuk donut:

```text
A1: Label         B1: Nilai
A2: Langsung      B2: 42
A3: Referral      B3: 28
```

- Baris 1 adalah header. Kolom A adalah kategori. Kolom B dan seterusnya
  adalah seri.
- Tidak ada formula dan tidak ada data dua arah.
- Chart object diletakkan di area yang tidak menutupi data, misalnya mulai
  baris 8. Satu tab hanya berisi satu chart.
- Warna dan font chart berasal dari token theme.

## Linked chart dan placeholder

1. Staging PPTX memakai placeholder di posisi chart, bukan native chart yang
   diganti. Nama dan alt placeholder deterministik:
   `autooffice:chart:<chart_id>`.
2. Preflight semua placeholder sebelum menghapus satu pun. Placeholder yang
   hilang atau ganda menggagalkan push.
3. Hapus placeholder dengan `deleteObject`. Buat linked chart dengan
   `createSheetsChart`, `spreadsheetId`, `chartId`, dan
   `linkingMode: LINKED`.
4. Posisi dan ukuran linked chart diambil dari placeholder.
5. Bila sudah ada linked chart untuk `chart_id`, jangan membuat duplikat.
   Verifikasi link dan update data saja.
6. Bila ada linked chart dengan `chart_id` lain di posisi yang sama, gagal.
7. Bila spec berubah, gunakan update chart spec agar `embedded_chart_id`
   tetap dan link Slides tidak putus. Bila tab atau chart hilang, buat ulang
   dan tandai link lama rusak; jangan menebak.
8. Bila replacement gagal di tengah, state mencatat progress dan rerun harus
   idempoten.

## State JSON

Lokasi: `.autooffice/state/<stem>.json` di samping YAML. `--out` tidak
mengubah identitas state.

```json
{
  "schema": "autooffice.state/v1",
  "deck_path": "deck.yaml",
  "deck_sha256": "...",
  "presentation_id": "...",
  "presentation_url": "...",
  "spreadsheet_id": "...",
  "spreadsheet_url": "...",
  "last_pulled_revision_id": "...",
  "last_pushed_at": "2026-11-14T00:00:00Z",
  "charts": {
    "s04.chart1": {
      "tab_name": "s04.chart1",
      "sheet_id": 123,
      "embedded_chart_id": 456,
      "last_data_sha256": "..."
    }
  }
}
```

Aturan state:

- State bukan source of truth konten.
- State tidak boleh menyimpan token OAuth.
- State boleh dihapus; push berikutnya membuat ulang spreadsheet dan
  presentasi.
- State ditulis atomik, dan tidak boleh masuk Git. `.autooffice/**` dan
  `.autooffice-build/**` di-ignore.
- State diperiksa terhadap `deck_sha256`; perbedaan bukan error, hanya memicu
  perencanaan sync.
- State tanpa `presentation_id` membuat `pull`, `diff`, dan `apply` gagal
  dengan pesan agar push dilakukan lebih dulu.

## Ownership dan OAuth

- OAuth user flow, bukan service account. File dimiliki akun yang memberi
  consent.
- Scope: `drive.file`, `presentations`, dan `spreadsheets` (URL lengkap sesuai
  bagian 9.7).
- Client secret tidak boleh ada di repo. Token cache berada di direktori
  user, bukan repo.
- Bila akun berganti dan state menunjuk file yang tidak bisa diakses, error
  harus jelas: minta login akun yang sama atau reset state.
- Setiap push membuat presentasi baru dan menyimpan ID aktif. Presentasi lama
  tidak dihapus otomatis.

## Preflight table native

1. Staging PPTX memuat table native untuk setiap block table.
2. Sebelum placeholder chart dihapus, preflight memastikan setiap block table
   menjadi page element `table` native dengan jumlah baris dan kolom yang
   benar.
3. Elemen `image`, shape group, atau table dengan dimensi berbeda menggagalkan
   push dengan menyebut slide ID dan block ID.
4. Kegagalan preflight berarti tidak ada placeholder dihapus, tidak ada
   linked chart dibuat, dan state tidak ditulis.
5. `CreateTableRequest` tersedia sebagai fallback masa depan, tetapi tidak
   dipakai otomatis di v1.

## Urutan kegagalan

- Spreadsheet gagal dibuat: tidak ada upload presentasi.
- Tab gagal dibuat: state tidak mencatat chart.
- Data gagal ditulis: chart tidak boleh di-link.
- Chart object gagal dibuat: tidak ada replacement.
- Placeholder tidak lengkap: tidak ada penghapusan.
- Table preflight gagal: tidak ada mutasi remote.
- Replacement gagal: state mencatat chart yang sudah siap; rerun melanjutkan.
- Kuota API: retry terbatas dengan backoff, lalu gagal.
- Jangan menghapus spreadsheet atau presentasi user secara otomatis.
- Jangan membuat spreadsheet kedua bila state masih valid. Bila spreadsheet
  dihapus user, buat ulang dan tandai presentasi lama tidak sinkron.

## Pemetaan acceptance

Catatan F0: test bentuk ada di `tests/contract/test_contract_shapes.py` dan `tests/contract/test_f0_scaffold.py`. Test perilaku yang disebut di tabel ini dijadwalkan di lane implementasi terkait.

| Invarian | Bukti |
| --- | --- |
| Satu spreadsheet dan tab per chart | `tests/google/test_sheets.py` (planned); F2-GOOGLE. |
| State JSON dan atomic write | `tests/google/test_state.py` (planned). |
| Linked chart replacement | Fake `createSheetsChart`; `tests/google/test_linked_chart.py` (planned). |
| Tanpa duplikat chart | Idempotency test rerun; bagian 9.5. |
| Preflight table native | Fake page element; `tests/google/test_table_preflight.py` (planned). |
| Ownership dan scope | Smoke akun bersih; bagian 9.7 dan 18.5. |

[Rencana AutoOffice](../../AUTO_OFFICE_PLAN.md)
