#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 nothinx
"""Pemeriksa tautan dokumentasi, TOC dokumen panjang, dan registry referensi.

Skrip ini memindai `README.md` akar, `docs/**/*.md`, `src/**/README.md`,
`tests/README.md`, `tools/README.md`, dan `scripts/README.md`. Setiap tautan
relatif `[teks](target)` diperiksa agar targetnya ada. Tautan eksternal,
anchor same-file, inline code, code fence, dan komentar HTML dilewati.
`docs/dev/archive/**` dikecualikan karena arsip dibekukan dan tautan lamanya
tidak boleh memaksa perubahan isi sejarah.

Dokumen lebih dari 150 baris wajib punya bagian `Daftar isi`. Setiap tautan
anchor di bagian itu harus cocok dengan slug heading gaya GitHub.

Registry `docs/dev/references.md` diperiksa terpisah: setiap baris tabel tiga
kolom harus memuat URL `http`/`https` yang valid, label unik, dan URL unik.
Pemeriksaan bersifat read-only dan tidak mengakses jaringan.

Pemakaian:
    python tools/dev/check_docs.py
    python tools/dev/check_docs.py <akar-repo>

Kode keluar 1 bila ada tautan relatif rusak, TOC tidak valid, atau entri
registry tidak valid, 0 bila semuanya bersih.
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

AKAR = Path(__file__).resolve().parents[2]
BERKAS_REGISTRY = Path("docs/dev/references.md")
DOKUMEN_AKAR = Path("README.md")
DIREKTORI_DOKUMEN = Path("docs")
DIREKTORI_SRC = Path("src")
DIREKTORI_ARSIP = Path("docs/dev/archive")
README_MODUL = (
    Path("tests/README.md"),
    Path("tools/README.md"),
    Path("scripts/README.md"),
)
AMBANG_TOC = 150
SLUG_DAFTAR_ISI = frozenset({"daftar-isi", "table-of-contents"})

POLA_TAUTAN = re.compile(
    r"(?<!!)\[(?P<teks>[^\]\n]*)\]\(\s*"
    r"(?:<(?P<bersudut>[^>\n]*)>|(?P<polos>[^\s)\n]+))"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)\n]*\)))?\s*\)"
)
POLA_PAGAR = re.compile(
    r"^[ \t]*(?P<pagar>`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*(?P=pagar)[ \t]*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
POLA_KODE_SEBARIS = re.compile(r"(`+)(?P<isi>[^\n]+?)\1")
POLA_KOMENTAR = re.compile(r"<!--.*?-->", re.DOTALL)
POLA_SKEMA = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
POLA_JUDUL = re.compile(r"^(?P<pagar>#{1,6})[ \t]+(?P<teks>.+?)[ \t]*#*[ \t]*$")
POLA_TAUTAN_TOC = re.compile(r"^[ \t]*[-*+][ \t]+\[[^\]\n]*\]\(#(?P<anchor>[^)\n]+)\)")


@dataclass(frozen=True)
class Masalah:
    """Satu temuan checker dengan lokasi berkas dan baris."""

    berkas: str
    baris: int
    pesan: str

    def __str__(self) -> str:
        return f"{self.berkas}:{self.baris}: {self.pesan}"


@dataclass(frozen=True)
class Hasil:
    """Ringkasan hasil pemeriksaan."""

    berkas: int = 0
    tautan: int = 0
    toc: int = 0
    entri: int = 0
    masalah: tuple[Masalah, ...] = ()


@dataclass(frozen=True)
class Entri:
    """Satu baris registry referensi."""

    label: str
    url: str
    baris: int


def _samarkan(pola: re.Pattern[str], teks: str) -> str:
    """Ganti bagian yang cocok dengan spasi tanpa mengubah nomor baris."""

    def kosong(cocok: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", cocok.group(0))

    return pola.sub(kosong, teks)


def _tanpa_kode(teks: str) -> str:
    """Kosongkan code fence, komentar HTML, dan inline code."""
    teks = _samarkan(POLA_PAGAR, teks)
    teks = _samarkan(POLA_KOMENTAR, teks)
    return _samarkan(POLA_KODE_SEBARIS, teks)


def _destinasi(cocok: re.Match[str]) -> str:
    bersudut = cocok.group("bersudut")
    if bersudut is not None:
        return bersudut
    return cocok.group("polos") or ""


def _tujuan_relatif(tujuan: str) -> str | None:
    """Kembalikan path relatif yang harus diperiksa, atau None bila dilewati."""
    tujuan = tujuan.strip()
    if not tujuan or tujuan.startswith("#") or tujuan.startswith("//"):
        return None
    if POLA_SKEMA.match(tujuan):
        return None
    jalur = tujuan.split("#", 1)[0].split("?", 1)[0]
    if not jalur or jalur.startswith("/"):
        return None
    return unquote(jalur)


def _berkas_dokumen(akar: Path) -> list[Path]:
    """Daftar README dan dokumen Markdown aktif di luar arsip."""
    akar = akar.resolve()
    arsip = (akar / DIREKTORI_ARSIP).resolve()
    kandidat = [akar / DOKUMEN_AKAR]
    direktori = akar / DIREKTORI_DOKUMEN
    if direktori.is_dir():
        kandidat.extend(sorted(direktori.rglob("*.md")))
    direktori_src = akar / DIREKTORI_SRC
    if direktori_src.is_dir():
        kandidat.extend(sorted(direktori_src.rglob("README.md")))
    kandidat.extend(akar / jalur for jalur in README_MODUL)
    berkas: list[Path] = []
    terlihat: set[Path] = set()
    for jalur in kandidat:
        if not jalur.is_file() or jalur in terlihat or jalur.is_relative_to(arsip):
            continue
        terlihat.add(jalur)
        berkas.append(jalur)
    return berkas


def _teks_judul(teks: str) -> str:
    """Ambil teks yang terlihat dari heading Markdown."""
    teks = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", teks)
    teks = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", teks)
    teks = re.sub(r"<[^>]*>", "", teks)
    teks = teks.replace("`", "")
    teks = re.sub(r"\*\*(.+?)\*\*", r"\1", teks)
    teks = re.sub(r"(?<!\w)__(.+?)__(?!\w)", r"\1", teks)
    teks = re.sub(r"\*(.+?)\*", r"\1", teks)
    return teks.strip()


def _slug_judul(teks: str) -> str:
    """Ubah teks heading menjadi slug anchor gaya GitHub."""
    teks = _teks_judul(teks).lower()
    teks = re.sub(r"[^\w\- ]", "", teks)
    return teks.replace(" ", "-")


def _judul_dokumen(teks: str) -> list[tuple[int, int, str]]:
    """Kembalikan pasangan (baris, level, slug) untuk setiap heading."""
    teks = _samarkan(POLA_KOMENTAR, _samarkan(POLA_PAGAR, teks))
    judul: list[tuple[int, int, str]] = []
    terlihat: dict[str, int] = {}
    for nomor, baris in enumerate(teks.splitlines(), 1):
        cocok = POLA_JUDUL.match(baris)
        if cocok is None:
            continue
        level = len(cocok.group("pagar"))
        slug = _slug_judul(cocok.group("teks"))
        jumlah = terlihat.get(slug, 0)
        terlihat[slug] = jumlah + 1
        if jumlah:
            slug = f"{slug}-{jumlah}"
        judul.append((nomor, level, slug))
    return judul


def periksa_toc_berkas(teks: str, nama: str) -> tuple[int, list[Masalah]]:
    """Periksa keberadaan TOC dan validitas anchor untuk satu dokumen."""
    baris = teks.splitlines()
    judul = _judul_dokumen(teks)
    indeks = next(
        (posisi for posisi, (_, _, slug) in enumerate(judul) if slug in SLUG_DAFTAR_ISI),
        None,
    )
    if indeks is None:
        if len(baris) > AMBANG_TOC:
            return 0, [Masalah(nama, 0, f"dokumen {len(baris)} baris tanpa daftar isi")]
        return 0, []
    nomor_toc, level_toc, _ = judul[indeks]
    anchor_heading = {slug for _, _, slug in judul}
    batas = len(baris) + 1
    for nomor, level, _ in judul[indeks + 1 :]:
        if level <= level_toc:
            batas = nomor
            break
    jumlah = 0
    masalah: list[Masalah] = []
    for nomor in range(nomor_toc + 1, batas):
        cocok = POLA_TAUTAN_TOC.match(baris[nomor - 1])
        if cocok is None:
            continue
        anchor = cocok.group("anchor")
        if anchor not in anchor_heading:
            masalah.append(Masalah(nama, nomor, f"anchor daftar isi tidak valid: #{anchor}"))
        jumlah += 1
    if not jumlah:
        masalah.append(Masalah(nama, nomor_toc, "daftar isi tidak berisi tautan anchor"))
    return 1, masalah


def periksa_tautan_berkas(teks: str, jalur: Path, nama: str) -> tuple[int, list[Masalah]]:
    """Periksa tautan relatif dalam satu teks Markdown."""
    bersih = _tanpa_kode(teks)
    jumlah = 0
    masalah: list[Masalah] = []
    for cocok in POLA_TAUTAN.finditer(bersih):
        relatif = _tujuan_relatif(_destinasi(cocok))
        if relatif is None:
            continue
        jumlah += 1
        target = jalur.parent / relatif
        if not target.exists():
            baris = bersih.count("\n", 0, cocok.start()) + 1
            masalah.append(Masalah(nama, baris, f"tautan rusak: {relatif}"))
    return jumlah, masalah


def periksa_dokumen(akar: Path = AKAR) -> Hasil:
    """Periksa tautan relatif dan TOC di dokumentasi aktif."""
    akar = akar.resolve()
    jumlah_berkas = 0
    jumlah_tautan = 0
    jumlah_toc = 0
    masalah: list[Masalah] = []
    for jalur in _berkas_dokumen(akar):
        nama = jalur.relative_to(akar).as_posix()
        teks = jalur.read_text(encoding="utf-8")
        tautan, temuan = periksa_tautan_berkas(teks, jalur, nama)
        toc, temuan_toc = periksa_toc_berkas(teks, nama)
        jumlah_berkas += 1
        jumlah_tautan += tautan
        jumlah_toc += toc
        masalah.extend(temuan)
        masalah.extend(temuan_toc)
    return Hasil(
        berkas=jumlah_berkas,
        tautan=jumlah_tautan,
        toc=jumlah_toc,
        masalah=tuple(masalah),
    )


def _kolom_tabel(baris: str) -> list[str] | None:
    isi = baris.strip()
    if "|" not in isi:
        return None
    if isi.startswith("|"):
        isi = isi[1:]
    if isi.endswith("|"):
        isi = isi[:-1]
    return [kolom.strip() for kolom in isi.split("|")]


def _baris_pemisah(kolom: list[str]) -> bool:
    return bool(kolom) and all(re.fullmatch(r":?-{3,}:?", sel) for sel in kolom)


def baca_registry(teks: str) -> list[Entri]:
    """Ambil entri dari tabel tiga kolom `Label | URL | Dipakai untuk`."""
    entri: list[Entri] = []
    for nomor, baris in enumerate(teks.splitlines(), 1):
        kolom = _kolom_tabel(baris)
        if kolom is None or len(kolom) != 3 or _baris_pemisah(kolom):
            continue
        if [isi.casefold() for isi in kolom[:2]] == ["label", "url"]:
            continue
        entri.append(Entri(label=kolom[0], url=kolom[1], baris=nomor))
    return entri


def _url_valid(url: str) -> bool:
    if not url or any(karakter.isspace() for karakter in url):
        return False
    try:
        hasil = urlsplit(url)
        _ = hasil.port
    except ValueError:
        return False
    return hasil.scheme in {"http", "https"} and bool(hasil.hostname)


def periksa_registry(jalur: Path = AKAR / BERKAS_REGISTRY) -> Hasil:
    """Periksa sintaks URL, label unik, dan URL unik di registry."""
    try:
        teks = jalur.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Hasil(masalah=(Masalah(BERKAS_REGISTRY.as_posix(), 0, "registry tidak ditemukan"),))
    entri = baca_registry(teks)
    nama = BERKAS_REGISTRY.as_posix()
    masalah: list[Masalah] = []
    if not entri:
        masalah.append(Masalah(nama, 0, "registry tidak berisi entri tabel"))
    label_terlihat: dict[str, Entri] = {}
    url_terlihat: dict[str, Entri] = {}
    for item in entri:
        url = item.url.removeprefix("<").removesuffix(">")
        if not item.label:
            masalah.append(Masalah(nama, item.baris, "label registry kosong"))
        kunci_label = item.label.casefold()
        if kunci_label in label_terlihat:
            masalah.append(Masalah(nama, item.baris, f"label duplikat: {item.label}"))
        else:
            label_terlihat[kunci_label] = item
        if not _url_valid(url):
            masalah.append(
                Masalah(nama, item.baris, f"URL tidak valid (harus http/https): {item.url}")
            )
            continue
        if url in url_terlihat:
            masalah.append(Masalah(nama, item.baris, f"URL duplikat: {url}"))
        else:
            url_terlihat[url] = item
    return Hasil(berkas=1, entri=len(entri), masalah=tuple(masalah))


def periksa(akar: Path = AKAR) -> Hasil:
    """Periksa dokumentasi dan registry di bawah akar repo."""
    akar = akar.resolve()
    dokumen = periksa_dokumen(akar)
    registry = periksa_registry(akar / BERKAS_REGISTRY)
    return Hasil(
        berkas=dokumen.berkas,
        tautan=dokumen.tautan,
        toc=dokumen.toc,
        entri=registry.entri,
        masalah=dokumen.masalah + registry.masalah,
    )


def main(argv: list[str] | None = None) -> int:
    """Jalankan checker dan kembalikan kode keluar 0 atau 1."""
    argumen = list(argv or [])
    if len(argumen) > 1:
        print("pemakaian: check_docs.py [akar-repo]")
        return 2
    akar = Path(argumen[0]).resolve() if argumen else AKAR
    hasil = periksa(akar)
    print(f"Dokumen diperiksa: {hasil.berkas}")
    print(f"Tautan relatif diperiksa: {hasil.tautan}")
    print(f"TOC diperiksa: {hasil.toc}")
    print(f"Entri registry: {hasil.entri}")
    if hasil.masalah:
        print(f"Broken: {len(hasil.masalah)}")
        for masalah in hasil.masalah:
            print(f"- {masalah}")
        return 1
    print("Broken: 0")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main(sys.argv[1:]))
