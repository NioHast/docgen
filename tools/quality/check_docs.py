#!/usr/bin/env python3
"""Pemeriksa dokumentasi AutoOffice yang read-only dan deterministik.

Checker memindai `README.md` akar, `docs/**/*.md`, README paket docgen, serta
README `tests`, `tools`, dan `scripts`. Pemeriksaan mencakup tautan relatif,
TOC dokumen panjang, judul level 1, bahasa code fence, keterjangkauan halaman
dari indeks dokumentasi, dan registry referensi. `docs/dev/archive/**`
dikecualikan karena arsip dibekukan. README internal `src/autooffice/**`
dimiliki lane domain dan bukan bagian kontrak dokumentasi ini.

Pemakaian:
    python tools/quality/check_docs.py [akar-repo]

Kode keluar 0 bila bersih dan 1 bila ada temuan. Skrip tidak mengakses
jaringan dan tidak menulis berkas.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

AKAR = Path(__file__).resolve().parents[2]
BERKAS_REGISTRY = Path("docs/dev/references.md")
DOKUMEN_AKAR = Path("README.md")
DIREKTORI_DOKUMEN = Path("docs")
DIREKTORI_SRC = Path("src/docgen")
DIREKTORI_ARSIP = Path("docs/dev/archive")
README_MODUL = (
    Path("tests/README.md"),
    Path("tools/README.md"),
    Path("scripts/README.md"),
)
AMBANG_TOC = 150
SLUG_DAFTAR_ISI = frozenset({"daftar-isi", "table-of-contents"})
INDEKS_UTAMA = Path("docs/README.md")

POLA_TAUTAN = re.compile(
    r"(?<!!)\[(?P<teks>[^\]\n]*)\]\(\s*"
    r"(?:<(?P<bersudut>[^>\n]*)>|(?P<polos>[^\s)\n]+))"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)\n]*\)))?\s*\)"
)
POLA_PAGAR = re.compile(r"^[ \t]*(?P<pagar>`{3,}|~{3,})(?P<info>.*)$")
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


@dataclass(frozen=True)
class Pagar:
    """Satu code fence dengan nomor baris pembuka dan penutup."""

    buka: int
    tutup: int
    info: str
    tertutup: bool


def _samarkan(pola: re.Pattern[str], teks: str) -> str:
    """Ganti bagian yang cocok dengan spasi tanpa mengubah nomor baris."""

    def kosong(cocok: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", cocok.group(0))

    return pola.sub(kosong, teks)


def _pagar(teks: str) -> list[Pagar]:
    """Kembalikan code fence dengan aturan panjang penutup CommonMark."""
    hasil: list[Pagar] = []
    aktif: tuple[str, int, int, str] | None = None
    baris = teks.splitlines()
    for nomor, isi in enumerate(baris, 1):
        cocok = POLA_PAGAR.match(isi)
        if aktif is None:
            if cocok is not None:
                token = cocok.group("pagar")
                aktif = (token[0], len(token), nomor, cocok.group("info").strip())
            continue
        if (
            cocok is not None
            and cocok.group("pagar")[0] == aktif[0]
            and len(cocok.group("pagar")) >= aktif[1]
            and not cocok.group("info").strip()
        ):
            hasil.append(Pagar(aktif[2], nomor, aktif[3], True))
            aktif = None
    if aktif is not None:
        hasil.append(Pagar(aktif[2], len(baris), aktif[3], False))
    return hasil


def _tanpa_pagar(teks: str) -> str:
    """Kosongkan seluruh code fence tanpa mengubah jumlah baris."""
    baris = teks.splitlines(keepends=True)
    for pagar in _pagar(teks):
        for posisi in range(pagar.buka - 1, pagar.tutup):
            if posisi < len(baris):
                akhir = "\n" if baris[posisi].endswith("\n") else ""
                baris[posisi] = akhir
    return "".join(baris)


def _tanpa_kode(teks: str) -> str:
    """Kosongkan code fence, komentar HTML, dan inline code."""
    teks = _tanpa_pagar(teks)
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
    teks = _samarkan(POLA_KOMENTAR, _tanpa_pagar(teks))
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


def _periksa_judul(teks: str, nama: str) -> list[Masalah]:
    """Pastikan dokumen punya tepat satu judul level 1 di luar code fence."""
    jumlah = sum(1 for _, level, _ in _judul_dokumen(teks) if level == 1)
    if jumlah == 1:
        return []
    return [Masalah(nama, 0, f"judul level 1 harus tepat satu, ditemukan {jumlah}")]


def _periksa_pagar(teks: str, nama: str) -> list[Masalah]:
    """Pastikan setiap code fence ditutup dan punya bahasa."""
    masalah: list[Masalah] = []
    for pagar in _pagar(teks):
        if not pagar.tertutup:
            masalah.append(Masalah(nama, pagar.buka, "code fence tidak ditutup"))
        elif not pagar.info:
            masalah.append(Masalah(nama, pagar.buka, "code fence tanpa bahasa"))
    return masalah


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


def _target_halaman(jalur: Path) -> Path | None:
    """Resolve tautan ke berkas Markdown, termasuk tautan direktori."""
    if jalur.is_dir():
        jalur = jalur / "README.md"
    if jalur.suffix == ".md" and jalur.is_file():
        return jalur
    return None


def _tautan_halaman(teks: str, jalur: Path) -> set[Path]:
    """Kumpulkan target Markdown yang resolve dari satu dokumen."""
    hasil: set[Path] = set()
    for cocok in POLA_TAUTAN.finditer(_tanpa_kode(teks)):
        relatif = _tujuan_relatif(_destinasi(cocok))
        if relatif is None:
            continue
        target = _target_halaman(jalur.parent / relatif)
        if target is not None:
            hasil.add(target)
    return hasil


def _periksa_indeks(akar: Path) -> list[Masalah]:
    """Pastikan semua halaman docs terjangkau dari `docs/README.md`."""
    direktori = akar / DIREKTORI_DOKUMEN
    if not direktori.is_dir():
        return []
    indeks = akar / INDEKS_UTAMA
    if not indeks.is_file():
        return [Masalah(INDEKS_UTAMA.as_posix(), 0, "indeks dokumentasi tidak ditemukan")]
    halaman = {
        jalur.resolve()
        for jalur in direktori.rglob("*.md")
        if not jalur.resolve().is_relative_to((akar / DIREKTORI_ARSIP).resolve())
    }
    terlihat: set[Path] = set()
    antrean = [indeks.resolve()]
    while antrean:
        jalur = antrean.pop()
        if jalur in terlihat:
            continue
        terlihat.add(jalur)
        for tujuan in _tautan_halaman(jalur.read_text(encoding="utf-8"), jalur):
            if tujuan.resolve() in halaman and tujuan.resolve() not in terlihat:
                antrean.append(tujuan.resolve())
    masalah: list[Masalah] = []
    for jalur in sorted(halaman - terlihat):
        masalah.append(
            Masalah(
                jalur.relative_to(akar.resolve()).as_posix(),
                0,
                "halaman tidak terjangkau dari docs/README.md",
            )
        )
    return masalah


def periksa_dokumen(akar: Path = AKAR) -> Hasil:
    """Periksa tautan, TOC, judul, code fence, dan indeks dokumentasi."""
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
        masalah.extend(_periksa_judul(teks, nama))
        masalah.extend(_periksa_pagar(teks, nama))
    masalah.extend(_periksa_indeks(akar))
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
    parser = argparse.ArgumentParser(
        prog="check_docs.py",
        description="Periksa tautan, TOC, judul, code fence, indeks, dan registry dokumentasi.",
    )
    parser.add_argument("root", nargs="?", type=Path, default=AKAR, help="akar repo")
    args = parser.parse_args(argv)
    hasil = periksa(args.root)
    print(f"Dokumen diperiksa: {hasil.berkas}")
    print(f"Tautan relatif diperiksa: {hasil.tautan}")
    print(f"TOC diperiksa: {hasil.toc}")
    print(f"Entri registry: {hasil.entri}")
    if hasil.masalah:
        print(f"Broken: {len(hasil.masalah)}")
        for masalah in sorted(
            hasil.masalah, key=lambda item: (item.berkas, item.baris, item.pesan)
        ):
            print(f"- {masalah}")
        return 1
    print("Broken: 0")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    raise SystemExit(main(sys.argv[1:]))
