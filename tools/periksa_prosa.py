#!/usr/bin/env python3
"""Alias tipis untuk tools/check_prose.py.

Nama lama dipertahankan agar Makefile, dokumentasi, dan kebiasaan pengguna
tidak putus. Seluruh perilaku, aturan, dan tes berada di check_prose.py dan
writing/rules.yml; berkas ini tidak menyimpan pola.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_prose import (  # noqa: E402,F401
    AKRONIM,
    BUKAN_NAMA_DIRI,
    KATA_BAKU,
    POLA,
    SINGKATAN_UMUM,
    baca,
    banding,
    bersihkan,
    fakta,
    kalimat_panjang,
    label_butir,
    main,
    penanda_istilah,
    periksa,
    singkatan,
    tes,
    validasi,
)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main(sys.argv[1:]))
