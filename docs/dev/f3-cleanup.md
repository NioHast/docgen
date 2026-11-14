# Status Pembersihan F3

Status: penghapusan legacy sudah diterapkan pada working tree branch ini.
Sumber keputusan: [ADR 0011](../decisions/0011-f3-cleanup.md). Plan migrasi:
[`AUTO_OFFICE_PLAN.md`](../../AUTO_OFFICE_PLAN.md) bagian 13.5 dan 16.

Halaman ini hanya ringkasan status. Daftar berkas, urutan operasi, inventaris
referensi, risiko, dan rollback ada di ADR 0011.

## Selesai di tree

- Package dan entry point lama dihapus; `autooffice` menjadi satu-satunya
  permukaan perintah.
- Suite legacy dan adapter PowerShell dihapus.
- Tool pengembang aktif berada di `tools/quality/`.
- Kontrak aktif berada di `docs/contracts/`.
- Dokumentasi aktif memakai path `src/autooffice/**`, `tests/**`, dan
  `tools/quality/**`.

## Verifikasi

```bash
python tools/quality/check_docs.py
uv run python tools/quality/gate.py
```

Gate final dan smoke Windows mengikuti ADR 0011. Rename repo adalah langkah
terpisah dan tidak menjadi bagian halaman ini.
