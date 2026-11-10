#!/usr/bin/env python3
# MIT License
# Copyright (c) 2026 nothinx
# Turunan naskah-id: https://github.com/nothinx/naskah-id
# Salinan lisensi lengkap: LICENSE. Berkas contoh/korpus/ (CC BY-SA 4.0) tidak disertakan.
"""Pemeriksa pola kaidah, gaya, dan klise mesin dalam naskah Indonesia.

Seluruh pola dibaca dari tools/dev/rules.yml. Skrip ini tidak menyimpan salinan
regex aturan. Hasilnya petunjuk, bukan putusan: setiap temuan perlu dibaca
dalam konteksnya. Jangan dipakai untuk menilai apakah sebuah teks ditulis mesin.

Pemakaian:
    python tools/dev/check_prose.py naskah.md [skripsi.docx ...]
        # periksa berkas (.md, .txt, .docx)
    python tools/dev/check_prose.py -  # baca dari stdin
    python tools/dev/check_prose.py --banding asli.md hasil.md
        # angka, sitasi, kutipan yang berubah
    python tools/dev/check_prose.py --self-test  # uji mandiri (109 kasus)
    python tools/dev/check_prose.py --abaikan SG-04,KL-01 naskah.md
        # lewati kode tertentu

Pada berkas .docx, teks diambil per paragraf dari word/document.xml dan nomor baris laporan
adalah nomor paragraf. Paragraf bergaya Heading1/Heading2/Heading3 diberi penanda Markdown
(#, ##, ###) agar batas bagian tetap terbaca seperti pada berkas Markdown.

Teks yang dilewati: blok kode, `kode sebaris`, ~~coret~~, URL, dan wilayah antara
<!-- periksa:abaikan --> dan <!-- periksa:lanjut -->, serta baris yang diawali
**Sebelum:** atau **Waspadai:**. Contoh kalimat salah di dokumentasi ditulis dengan cara itu.
Bagian Daftar Pustaka/Referensi/Abstract (sampai judul berikutnya) juga dilewati.

Penanda istilah {{?…?}} yang belum diputuskan dilaporkan sebagai IS-01; teks tidak diubah.

Kode keluar 1 bila ada temuan K (atau, pada --banding, ada fakta yang berubah), 0 bila tidak.
"""

import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

from ruamel.yaml import YAML

AKAR = Path(__file__).resolve().parent
BERKAS_ATURAN = AKAR / "rules.yml"
FLAG_I = re.IGNORECASE
# Awal kalimat; berlaku pada teks yang penanda Markdown-nya sudah dibuang.
AWAL = r"(?:^|(?<=[.!?])\s+)"


# ---------------------------------------------------------------------------
# Pembaca aturan
# ---------------------------------------------------------------------------
DATA = YAML(typ="safe").load(BERKAS_ATURAN.read_text(encoding="utf-8"))
ATURAN = DATA["aturan"]
_PETA = {a["kode"]: a for a in ATURAN}
KATA_BAKU = dict(DATA["kamus"])
AKRONIM = dict(DATA["akronim"])
SINGKATAN_UMUM = set(DATA["singkatan_umum"])
BUKAN_NAMA_DIRI = list(DATA["bukan_nama_diri"])

FLAGS = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL, "x": re.VERBOSE}


def _flag(teks):
    hasil = 0
    for c in teks or "":
        hasil |= FLAGS[c]
    return hasil


def _saran_imbuhan_singkatan(c):
    return "imbuhan dan singkatan dirangkai tanda hubung: " + re.sub(
        r"^([a-z]+)(?=[A-Z])|(?<=[A-Z])(?=[a-z]+$)",
        lambda m: (m.group(1) + "-") if m.group(1) else "-",
        c,
    )


def _saran_titik_singkatan(c):
    return "singkatan umum: " + (
        {"s/d": "s.d.", "a/n": "a.n.", "d/a": "d.a.", "u/p": "u.p."}.get(c) or c + "."
    )


def _saran_desimal_koma(c):
    return "desimal memakai koma: " + c.replace(".", ",")


def _saran_spasi_satuan(c):
    return "beri spasi antara angka dan lambang satuan: " + re.sub(
        r"(?<=\d)(?=[^\d.,])", " ", c, count=1
    )


SARAN_DINAMIS = {
    "imbuhan_singkatan": _saran_imbuhan_singkatan,
    "titik_singkatan": _saran_titik_singkatan,
    "desimal_koma": _saran_desimal_koma,
    "spasi_satuan": _saran_spasi_satuan,
}


def _saran(aturan):
    if "saran_jenis" in aturan:
        return SARAN_DINAMIS[aturan["saran_jenis"]]
    return aturan["saran"]


# Bentuk lama tetap tersedia untuk pemanggil yang mengimpor POLA/POLA_C.
POLA = [
    (a["kode"], a["label"], a["pola"], _flag(a.get("flag", "")), _saran(a), a.get("min", 1))
    for a in ATURAN
    if a["jenis"] == "regex"
]
POLA_C = [(i, lab, re.compile(rx, fl | re.M), sar, mn) for i, lab, rx, fl, sar, mn in POLA]

POLA_KB = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, KATA_BAKU), key=len, reverse=True)) + r")\b",
    FLAG_I,
)

PENANDA_JUDUL = {"heading1": "# ", "heading2": "## ", "heading3": "### "}


def _nama_lokal(tag):
    return tag.rsplit("}", 1)[-1]


def _gaya_paragraf(p):
    """Ambil w:pStyle/@w:val dari w:pPr langsung, tanpa bergantung pada awalan namespace."""
    for anak in p:
        if _nama_lokal(anak.tag) == "pPr":
            for x in anak:
                if _nama_lokal(x.tag) == "pStyle":
                    return next((v for k, v in x.attrib.items() if _nama_lokal(k) == "val"), "")
    return ""


def baca(nama):
    """Baca teks dari stdin ('-'), berkas .docx (satu paragraf per baris), atau berkas teks."""
    if nama == "-":
        return sys.stdin.read()
    jalur = Path(nama)
    if jalur.suffix.lower() == ".docx":
        with zipfile.ZipFile(jalur) as z, z.open("word/document.xml") as f:
            akar = ET.parse(f).getroot()
        paragraf = []
        for p in akar.iter():
            if not (p.tag.endswith(("}p", ":p")) or p.tag == "p"):
                continue
            teks = "".join(
                t.text or "" for t in p.iter() if t.tag.endswith(("}t", ":t")) or t.tag == "t"
            ).replace("\n", " ")
            gaya = re.sub(r"\s+", "", _gaya_paragraf(p)).lower()
            paragraf.append(PENANDA_JUDUL.get(gaya, "") + teks)
        return "\n".join(paragraf)  # paragraf kosong ikut agar nomor baris = nomor paragraf
    return jalur.read_text(encoding="utf-8")


def _mask(teks):
    """Kosongkan bagian yang dilewati, tetapi pertahankan penanda butir dan tebal.

    Dipakai oleh bersihkan() dan oleh aturan yang harus membaca teks mentah
    (AI-20). Posisi baris tetap karena setiap karakter selain newline diganti
    spasi.
    """

    def kosong(m):
        return re.sub(r"[^\n]", " ", m.group(0))

    teks = re.sub(
        r"<!--\s*periksa:abaikan\s*-->.*?(?:<!--\s*periksa:lanjut\s*-->|\Z)",
        kosong,
        teks,
        flags=re.S,
    )
    teks = re.sub(r"^[ \t>*+-]*\*\*(?:Sebelum|Waspadai):\*\*.*$", kosong, teks, flags=re.M)
    teks = re.sub(r"^(```|~~~).*?^\1", kosong, teks, flags=re.S | re.M)
    teks = re.sub(r"`[^`\n]*`|~~[^~\n]*~~|https?://\S+|<!--.*?-->", kosong, teks, flags=re.S)
    teks = re.sub(r"^\s*---\n.*?\n---\n", kosong, teks, count=1, flags=re.S)  # frontmatter
    # ponytail: bagian berakhir di judul Markdown berikutnya; naskah polos
    # tanpa # dilewati sampai akhir berkas.
    teks = re.sub(
        r"^(?:#+[ \t]*)?(?:daftar pustaka|daftar rujukan|referensi|bibliografi|references|"
        r"bibliography|abstract)"
        r"[ \t]*:?[ \t]*$.*?(?=^#|\Z)",
        kosong,
        teks,
        flags=re.S | re.M | re.I,
    )
    return teks


def bersihkan(teks):
    """Ganti bagian yang dilewati dengan spasi agar posisi baris tetap."""

    def kosong(m):
        return re.sub(r"[^\n]", " ", m.group(0))

    teks = _mask(teks)
    # Penanda Markdown di awal baris (judul, kutipan, butir, nomor)
    # diperlakukan sebagai awal kalimat.
    teks = re.sub(
        r"^[ \t]*(?:#+|>+|[-*+]|\d+[.)])[ \t]+(?:\*\*[^*\n]*\*\*[:.]?[ \t]*)?",
        kosong,
        teks,
        flags=re.M,
    )
    return re.sub(r"[*_]", " ", teks)


def periksa(teks):
    """Kembalikan daftar (baris, id, label, cuplikan, saran)."""
    t = bersihkan(teks)

    # Awal temuan adalah karakter tak-kosong pertama; pola AWAL ikut menelan
    # spasi dan baris baru sebelumnya.
    def baris(m):
        return t.count("\n", 0, m.start() + len(m.group(0)) - len(m.group(0).lstrip())) + 1

    hasil = []
    for i, lab, rx, sar, mn in POLA_C:
        cocok = list(rx.finditer(t))
        if len(cocok) >= mn:
            for m in cocok:
                c = " ".join(m.group(0).split())
                hasil.append((baris(m), i, lab, c, sar(c) if callable(sar) else sar))
    for m in POLA_KB.finditer(t):
        hasil.append((baris(m), "KB-01", "K", m.group(0), "baku: " + KATA_BAKU[m.group(0).lower()]))
    hasil += kalimat_panjang(teks, t) + singkatan(t) + penanda_istilah(t) + label_butir(teks, t)
    return sorted(hasil)


BATAS_BLOK = re.compile(r"\n(?=[ \t]*(?:\n|>[ \t]*\n|[-*+|#]|\d+[.)][ \t]))")

# Akronim yang sering salah ditulis kapital semua (EYD V: nama diri dari suku
# kata -> huruf awal kapital, bukan nama diri -> huruf kecil). Dicek per token
# kapital penuh, di luar baris judul berhuruf kapital.
POLA_AKRONIM = re.compile(r"\b(" + "|".join(AKRONIM) + r")\b")
POLA_KEPANJANGAN = re.compile(
    r"\b[A-Z][a-z]+(?:,?\s+(?:dan\s+|&\s+)?[A-Z][a-z]+)+\s*\(\s*(?:"
    + "|".join(BUKAN_NAMA_DIRI)
    + r")\s*\)"
)
# SG-04: token berhuruf kapital minimal dua dan minimal separuhnya kapital: UMKM, IoT, BUMDes
POLA_TOKEN = re.compile(r"\b[A-Z][A-Za-z0-9]{1,7}\b")
ROMAWI = re.compile(r"[IVXLCDM]+")


def baris_kapital(t, pos):
    """Baris judul berhuruf kapital semua (BAB I PENDAHULUAN) tidak diperiksa untuk singkatan."""
    awal, akhir = t.rfind("\n", 0, pos) + 1, t.find("\n", pos)
    huruf = [c for c in t[awal : akhir if akhir >= 0 else None] if c.isalpha()]
    return len(huruf) > 3 and all(c.isupper() for c in huruf)


def singkatan(t):
    """SG-04, SG-05, SG-06. Kembalikan daftar temuan."""

    def baris(pos):
        return t.count("\n", 0, pos) + 1

    hasil, pertama = [], {}
    for m in POLA_AKRONIM.finditer(t):
        if not baris_kapital(t, m.start()):
            hasil.append(
                (baris(m.start()), "SG-05", "K", m.group(0), "akronim: " + AKRONIM[m.group(0)])
            )
    for m in POLA_KEPANJANGAN.finditer(t):
        kep, sing = m.group(0).split("(")
        # Buang kata awal kalimat yang bukan bagian kepanjangan
        # ("Namun Usaha Mikro, ..."): ambil kata isi sebanyak huruf kapital
        # singkatan (UMKM -> 4, BUMDes -> 4).
        isi = [k for k in re.finditer(r"[A-Z][a-z]+", kep)]
        n = sum(c.isupper() for c in sing)
        if 2 <= n < len(isi):
            kep = kep[isi[-n].start() :]
        if len(re.findall(r"[A-Z][a-z]+", kep)) >= 2:
            hasil.append(
                (
                    baris(m.start()),
                    "SG-06",
                    "G",
                    " ".join((kep + "(" + sing).split()),
                    "kepanjangan singkatan bukan nama diri ditulis huruf kecil: "
                    + " ".join(kep.lower().split()),
                )
            )
    for m in POLA_TOKEN.finditer(t):
        w = m.group(0)
        besar = sum(c.isupper() for c in w)
        sesudah = t[m.end() : m.end() + 2]
        if (
            besar < 2
            or besar * 2 < sum(c.isalpha() for c in w)
            or w in SINGKATAN_UMUM
            or ROMAWI.fullmatch(w)
            or w in AKRONIM
            or baris_kapital(t, m.start())
            or re.match(r"-\d", sesudah)  # KE-01, COVID-19
            or (
                len(w) > 3 and any(c.isdigit() for c in w)
            )  # ESP32, STM32; K3 dan B3 tetap diperiksa
            or re.search(
                r"\bCC[\s-]+(?:(?:BY|NC|ND|SA)[\s-]*)*$", t[max(0, m.start() - 20) : m.start()]
            )  # CC BY-SA
            or t[t.rfind("\n", 0, m.start()) + 1 :].lstrip().startswith("|")  # baris tabel
            or re.search(
                r"\[[^\]]*$", t[max(0, m.start() - 200) : m.start()]
            )  # [PERLU DATA: …], [NAMA ALAT]
            or (w.isupper() and re.match(r"\s+[A-Z]{3,}\b", t[m.end() :]))
        ):  # label: TIDAK DITEMUKAN
            continue
        pertama.setdefault(w, []).append(m.start())
    for w, posisi in pertama.items():

        def menjelaskan(i, w=w):  # "(..., UMKM)" atau "UMKM (kepanjangan)"
            return bool(
                re.search(r"\([^()\n]*$", t[max(0, i - 120) : i])
                and re.match(r"\s*[)\],;]", t[i + len(w) :])
            ) or bool(re.match(r"\s*\((?!\s*\d)", t[i + len(w) :]))

        if menjelaskan(posisi[0]):
            continue
        ket = (
            "dijelaskan setelah dipakai; pindahkan kepanjangan ke kemunculan pertama"
            if any(map(menjelaskan, posisi[1:]))
            else (
                "belum dijelaskan: tulis kepanjangan (SINGKATAN) pada kemunculan pertama, "
                "kecuali sudah di bagian sebelumnya"
            )
        )
        hasil.append((baris(posisi[0]), "SG-04", "G", w, ket))
    return hasil


_ATURAN_IS01 = _PETA["IS-01"]
POLA_ISTILAH = re.compile(_ATURAN_IS01["pola"], _flag(_ATURAN_IS01.get("flag", "")))


def penanda_istilah(t):
    """IS-01: penanda {{?istilah?}} belum diputuskan. Pemeriksa tidak menebak atau mengubah teks."""

    def baris(pos):
        return t.count("\n", 0, pos) + 1

    return [
        (baris(m.start()), "IS-01", "K", " ".join(m.group(0).split()), _ATURAN_IS01["saran"])
        for m in POLA_ISTILAH.finditer(t)
    ]


def kalimat_panjang(teks, t, maks=None):
    """KL-01 (G): kalimat lebih dari maks kata.

    Blok dipisah di baris kosong, butir, judul, dan tabel teks asli.
    """
    maks = maks or _PETA["KL-01"].get("maks_kata", 35)
    hasil, awal = [], 0
    for m in [*BATAS_BLOK.finditer(teks), None]:
        akhir = m.start() if m else len(t)
        blok = t[awal:akhir]
        if "|" not in teks[awal:akhir]:
            for k in re.finditer(
                r"[^.!?]+[.!?]?", blok
            ):  # titik desimal dan singkatan memotong: hanya mengurangi temuan
                kata = re.findall(r"[^\W\d_]+", k.group(0))
                if len(kata) > maks:
                    pos = awal + k.start() + len(k.group(0)) - len(k.group(0).lstrip())
                    hasil.append(
                        (
                            t.count("\n", 0, pos) + 1,
                            "KL-01",
                            "G",
                            " ".join(kata[:6]) + " …",
                            f"{len(kata)} kata; pecah menjadi dua kalimat atau lebih",
                        )
                    )
        awal = akhir
    return hasil


_ATURAN_AI20 = _PETA["AI-20"]
POLA_BUTIR = re.compile(_ATURAN_AI20["pola"], _flag(_ATURAN_AI20.get("flag", "")) | re.M)
HENTI_LABEL = tuple(w.casefold() for w in _ATURAN_AI20.get("henti_label", []))
HENTI_AWAL = tuple(w.casefold() for w in _ATURAN_AI20.get("henti_awal", []))


def label_butir(teks, t):
    """AI-20 (AI): butir berlabel tebal 'X: penjelasan X'.

    Aturan ini membaca teks mentah karena bersihkan() membuang penanda butir
    dan tebal. Label prosedur/definisi dilewati lewat stoplist di rules.yml.
    Minimal dua butir per berkas supaya satu definisi wajar tidak langsung
    menjadi temuan.
    """
    hasil = []
    for m in POLA_BUTIR.finditer(_mask(teks)):
        label = " ".join(m.group(1).split())
        if not label:
            continue
        awal = label.casefold()
        if any(re.match(rf"{re.escape(w)}\b", awal) for w in HENTI_LABEL):
            continue
        if "/" in label or "\\" in label or re.search(r"\.\w+$", label):
            continue
        penjelasan = m.group(2).strip().casefold()
        if any(re.match(rf"{re.escape(w)}\b", penjelasan) for w in HENTI_AWAL):
            continue
        hasil.append((t.count("\n", 0, m.start()) + 1, "AI-20", "AI", label, _ATURAN_AI20["saran"]))
    return hasil if len(hasil) >= _ATURAN_AI20.get("min", 1) else []


KUTIPAN = re.compile(r'"[^"\n]{3,}"|“[^”]{3,}”')
SITASI = re.compile(
    r"\[\d+(?:\s*[-\u2013,]\s*\d+)*\]"  # [3], [3-5], [1, 4]
    r"|(?:[A-Z][\w'-]+(?:\s+(?:et al\.|dkk\.)|\s+(?:&|dan)\s+[A-Z][\w'-]+)?\s+)?"
    r"\((?=[^()]*\b(?:19|20)\d{2}[a-z]?\b)[^()\n]{1,200}\)"
)  # (Nama, 2020), Nama (2020)
ANGKA = re.compile(r"(?:[<>≤≥]\s*)?(?<![\w.,])\d+(?:[.,]\d+)*(?:\s?%)?")


def fakta(teks):
    """Ambil kutipan, sitasi, dan angka (berurutan; yang sudah diambil dibuang) sebagai multiset."""
    hasil = {}
    for jenis, rx in (("KUTIPAN", KUTIPAN), ("SITASI", SITASI), ("ANGKA", ANGKA)):
        hasil[jenis] = Counter(
            re.sub(r"\s+", "" if jenis == "ANGKA" else " ", m.group(0)) for m in rx.finditer(teks)
        )
        teks = rx.sub(" ", teks)
    return hasil


def banding(asli, hasil):
    """Kembalikan daftar (jenis, keterangan) untuk fakta yang hilang atau bertambah."""
    # ponytail: dibandingkan sebagai multiset, posisi tidak dicek; angka yang
    # ditulis ulang dengan huruf ikut terlapor hilang.
    a, h = fakta(asli), fakta(hasil)
    laporan = []
    for jenis in a:
        hilang, baru = (
            list((a[jenis] - h[jenis]).elements()),
            list((h[jenis] - a[jenis]).elements()),
        )
        if jenis == "ANGKA":  # 0.5 -> 0,5 adalah koreksi EYD yang sah; laporkan terpisah
            for x in list(hilang):
                y = x.translate(str.maketrans(".,", ",."))
                if y in baru:
                    hilang.remove(x)
                    baru.remove(y)
                    laporan.append(
                        ("PEMISAH", f"{x} -> {y} (cek: koreksi desimal atau nilai berubah?)")
                    )
        laporan += [(jenis, f"hilang: {x}") for x in hilang] + [(jenis, f"baru: {x}") for x in baru]
    return laporan


def tes():
    salah = {
        "Dari hasil pengujian menunjukkan bahwa galat turun.": "KE-01",
        "Menurut Sugiono mengatakan bahwa sampel cukup.": "KE-01",
        "Metode ini adalah merupakan metode baru.": "KE-02",
        "Penurunannya sangat besar sekali.": "KE-04",
        "Para peneliti-peneliti sepakat.": "KE-05",
        "Alat ini terdiri dari berbagai macam modul.": "KE-06",
        "Kami memakai sensor seperti DHT22, LM35, dan lain-lain.": "KE-09",
        "Nilai dihitung berdasarkan pada rumus 2.": "KE-10",
        "Perbedaan antara metode A dengan metode B kecil.": "KE-11",
        "Ini bukan galat acak, tetapi galat sistematis.": "KE-13",
        "Meskipun mahal, tetapi alat ini awet.": "KE-14",
        "Karena arus berlebih, maka sekring putus.": "KE-15",
        "Berdasarkan uraian tersebut, maka perlu dilakukan penelitian.": "KE-15",
        "Kami melakukan pengukuran tegangan.": "NM-01",
        "Nilai galat mengalami penurunan.": "NM-01",
        "Hal ini membuktikan bahwa tidur menyebabkan nilai naik.": "KK-01",
        " ".join(["kata"] * 36) + ".": "KL-01",
        "Galat naik. Sehingga hasil tidak valid.": "KE-16",
        "Metode A lebih baik dari metode B.": "KE-17",
        "Ruang dimana alat diuji.": "EJ-01",
        "Data di analisis dengan SPSS.": "EJ-02",
        "Sensor dipasang diatas meja.": "EJ-03",
        "Kerjasama antarlembaga diperlukan.": "EJ-04",
        "Sistem ini memakai antar muka web.": "EJ-05",
        "25 responden dilibatkan.": "EJ-06",
        "Tegangan terukur 0.5 V.": "EJ-07",
        "Catu daya 12V dipakai.": "EJ-08",
        "Catu daya 12 Volt dipakai.": "EJ-09",
        "Di era digital ini, data penting.": "AI-01",
        "Tidak dapat dipungkiri bahwa IoT berkembang.": "AI-03",
        "Sensor memainkan peran penting.": "AI-05",
        "Hasilnya sangat signifikan.": "AI-12",
        "Nilai galat besar, yang mana memengaruhi hasil.": "AI-13",
        "Sistem di mana data dikirim tiap detik.": "AI-14",
        "Kami melakukan analisa data.": "KB-01",
        "Berdasarkan hasil penelitian menyimpulkan bahwa nilainya sedang.": "KE-01",
        "Hasil uji menunjukan nilai r.": "KB-01",
        "Data dikumpulkan dengan kuisioner untuk menguji hirarki dan kelembaban.": "KB-01",
        "Sistem antrian ini handal untuk melatih kemampuan berfikir.": "KB-01",
        "Peneliti mengkategorikan dan mempublikasikan hasil.": "KB-01",
        "Galat turun, sehingga akurasi naik.": "EJ-10",
        "Galat turun—akurasi naik.": "EJ-11",
        "Hal ini benar. Hal ini salah. Hal ini lagi.": "AI-15",
        "Antar muka dibuat dengan Qt.": "EJ-05",
        "Non parametrik dipakai.": "EJ-05",
        "Pengujian pada suhu 25 C.": "EJ-09",
        "Karyawan itu diPHK tahun lalu.": "SG-01",
        "Omzet UMKMnya naik.": "SG-01",
        "Bahan, alat, dll disiapkan.": "SG-02",
        "Data 2019 s/d 2021 dipakai.": "SG-02",
        "Usaha mikro, kecil, dan menengah (UMKM) tumbuh. UMKM-UMKM itu kecil.": "SG-03",
        "Data UMKM diambil dari BPS.": "SG-04",
        "Data UMKM diambil. Usaha mikro, kecil, dan menengah (UMKM) tumbuh.": "SG-04",
        "Data dari BAPPENAS dipakai.": "SG-05",
        "Perkembangan IPTEK pesat.": "SG-05",
        "Usaha Mikro, Kecil, dan Menengah (UMKM) tumbuh.": "SG-06",
        "Catu daya 3.3V dipakai.": "EJ-08",
    }
    benar = [
        "Hasil pengujian menunjukkan bahwa galat turun.",
        "Dalam penelitian ini kami membahas metode baru.",
        "Pada Gambar 3, kami menunjukkan hasilnya.",
        "Sampel diambil secara acak dan dianalisis dengan uji-t.",
        "Penurunan ini signifikan (p < 0,01).",
        "Di mana sampel disimpan?",
        "Antara lain dengan cara ini, galat turun.",
        "Bukan hanya murah, tetapi juga awet.",
        "Jumlahnya lebih dari 50 orang.",
        "Biaya ini lebih kecil daripada biaya lama.",
        "Galat naik sehingga hasil tidak valid.",
        "Sebanyak 25 responden dilibatkan.",
        "Tegangan terukur 0,5 V dan beratnya 1.000 kg.",
        "Contoh kalimat salah: `Dari hasil uji menunjukkan`.",
        "<!-- periksa:abaikan -->\nDi era digital ini.\n<!-- periksa:lanjut -->\nTeks bersih.",
        "Hal ini benar. Hal ini juga benar.",
        "Versi Python 3.12 dipakai; lihat Bagian 2.1.",
        "Gaya selingkung dan kebijakan jurnal didahulukan.",
        "- Sampel diambil di laboratorium.",
        "Peserta keluar ruangan. Data bisa disimpan di mana saja.",
        "| 5 km | 2 kg |",
        "**Sebelum:** Dari hasil uji menunjukkan galat turun.",
        "Data diolah oleh Tri Wahyuni dan Dwi Santoso.",
        "Data diolah.\n\n## Daftar Pustaka\n\n"
        "Smith, J. (2020). Multi agent systems for inter vehicle use.",
        "DAFTAR PUSTAKA\nGarcia, L. (2019). Ultra wideband sensing. Respon sistem.",
        "Suhu 25 °C dipakai.",
        "Karyawan itu di-PHK (pemutusan hubungan kerja). Omzet usaha mikro, kecil, "
        "dan menengah (UMKM) dan UMKM-nya naik.",
        "Bahan, alat, dll. disiapkan dari 2019 s.d. 2021 (Santoso dkk., 2020).",
        "Usaha mikro, kecil, dan menengah (UMKM) tumbuh. Banyak UMKM kecil.",
        "Data diambil dari Badan Pusat Statistik (BPS). BPS mencatat kenaikan.",
        "*Internet of Things* (IoT) dipakai. Sistem IoT ini murah.",
        "Bab IV membahas hasil pada frekuensi 433 MHz.",
        "BAB I PENDAHULUAN DAN BAPPENAS",
        "Data dari Bappenas dan puskesmas dipakai.",
        "Sistem memakai ESP32 dan modul LoRa (*long range*).",
        "Artikel ini berlisensi CC BY-SA 4.0 dan CC BY-NC-ND, sedangkan kodenya MIT dan GPL.",
        "Sampel diambil dari siswa SD/MI, SMP/MTs, dan SMA/MA.",
        "Prevalensi masih tinggi [PERLU DATA: angka\nterbaru dan sumbernya, misalnya SSGI].",
        " ".join(["kata"] * 35) + ".",
        "- " + " ".join(["butir"] * 20) + "\n- " + " ".join(["butir"] * 20),
        "| " + " | ".join(["sel"] * 40) + " |",
    ]
    gagal = 0
    for teks, id_ in salah.items():
        ids = {h[1] for h in periksa(teks)}
        if id_ not in ids:
            gagal += 1
            print(f"GAGAL (tidak terdeteksi {id_}): {teks!r} -> {sorted(ids)}")
    for teks in benar:
        h = periksa(teks)
        if h:
            gagal += 1
            print(f"GAGAL (salah positif): {teks!r} -> {[x[1] for x in h]}")
    # nomor baris dan saran dinamis
    h = periksa("Baris satu.\nDalam Tabel 2 menunjukkan hasil.")
    if [x[0] for x in h if x[1] == "KE-01"] != [2]:
        gagal += 1
        print("GAGAL nomor baris KE-01:", h)
    h = {x[1]: x for x in periksa("Catu daya 3.3V dipakai.")}
    if h.get("EJ-08", ("",) * 5)[3:] != (
        "3.3V",
        "beri spasi antara angka dan lambang satuan: 3.3 V",
    ) or not h.get("EJ-07", ("",) * 5)[4].endswith("3,3V"):
        gagal += 1
        print("GAGAL saran dinamis:", h)
    h = [
        x
        for x in periksa("Namun Usaha Mikro, Kecil, dan Menengah (UMKM) sulit.")
        if x[1] == "SG-06"
    ]
    if [x[3] for x in h] != ["Usaha Mikro, Kecil, dan Menengah (UMKM)"]:
        gagal += 1
        print("GAGAL kepanjangan SG-06:", h)
    # berkas .docx: nomor baris = nomor paragraf, dan --banding mendukung .docx
    with tempfile.TemporaryDirectory() as d:
        ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

        def buat(nama, par):
            with zipfile.ZipFile(Path(d) / nama, "w") as z:
                z.writestr(
                    "word/document.xml",
                    f"<w:document {ns}><w:body>"
                    + "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in par)
                    + "</w:body></w:document>",
                )

        buat(
            "uji.docx",
            ["Paragraf pertama bersih.", "Dari hasil pengujian menunjukkan analisa salah."],
        )
        buat(
            "hasil.docx",
            [
                "Paragraf pertama bersih dan galat 1,5%.",
                "Hasil pengujian menunjukkan analisis benar.",
            ],
        )
        h_docx = [(x[0], x[1]) for x in periksa(baca(Path(d) / "uji.docx"))]
        if h_docx != [(2, "KB-01"), (2, "KE-01")] or banding(
            baca(Path(d) / "uji.docx"), baca(Path(d) / "hasil.docx")
        ) != [("ANGKA", "baru: 1,5%")]:
            gagal += 1
            print("GAGAL docx:", h_docx)
    # banding: (asli, hasil, laporan yang diharapkan)
    kasus_banding = [
        (
            "Galat turun dari 4,8% menjadi 1,2% (p < 0,01).",
            "Galat turun dari 4,8% ke 1,2% (p < 0,01).",
            [],
        ),
        (
            "Galat turun dari 4,8% menjadi 1,2%.",
            "Galat turun dari 4,8% menjadi 1,5%.",
            [("ANGKA", "hilang: 1,2%"), ("ANGKA", "baru: 1,5%")],
        ),
        (
            "Nilai p < 0,05.",
            "Nilai p > 0,05.",
            [("ANGKA", "hilang: <0,05"), ("ANGKA", "baru: >0,05")],
        ),
        (
            "Tegangan 0.5 V.",
            "Tegangan 0,5 V.",
            [("PEMISAH", "0.5 -> 0,5 (cek: koreksi desimal atau nilai berubah?)")],
        ),
        (
            "Hal ini sesuai (Santoso, 2020) dan [3].",
            "Temuan ini sesuai dengan [3].",
            [("SITASI", "hilang: (Santoso, 2020)")],
        ),
        (
            "Menurut Santoso (2020), galat kecil.",
            "Santoso (2021) menemukan galat kecil.",
            [("SITASI", "hilang: Santoso (2020)"), ("SITASI", "baru: Santoso (2021)")],
        ),
        (
            'Informan berkata, "Dana telat, kami berhenti."',
            'Informan berkata, "Dana terlambat, kami berhenti."',
            [
                ("KUTIPAN", 'hilang: "Dana telat, kami berhenti."'),
                ("KUTIPAN", 'baru: "Dana terlambat, kami berhenti."'),
            ],
        ),
    ]
    for asli, hasil, harap in kasus_banding:
        if sorted(banding(asli, hasil)) != sorted(harap):
            gagal += 1
            print(f"GAGAL banding: {asli!r} -> {banding(asli, hasil)}")
    total = len(salah) + len(benar) + 4 + len(kasus_banding)
    print(f"{total - gagal}/{total} kasus lulus")
    return 1 if gagal else 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] in ("--tes", "--self-test"):
        return tes()
    if argv[0] == "--banding":
        if len(argv) != 3:
            print("pemakaian: check_prose.py --banding asli.md hasil.md")
            return 2
        laporan = banding(*(baca(n) for n in argv[1:]))
        for jenis, ket in laporan:
            print(f"[{jenis}] {ket}")
        print(
            "Angka, sitasi, dan kutipan sama."
            if not laporan
            else f"{len(laporan)} perbedaan; periksa satu per satu."
        )
        return 1 if any(j != "PEMISAH" for j, _ in laporan) else 0
    abaikan = set()
    if argv[0] == "--abaikan":
        abaikan, argv = set(argv[1].split(",")), argv[2:]
    ada_k = False
    for nama in (
        p for a in argv for p in (sorted(map(str, Path().glob(a))) if "*" in a or "?" in a else [a])
    ):
        teks = baca(nama)
        temuan = [x for x in periksa(teks) if x[1] not in abaikan]
        for baris, id_, lab, cuplikan, saran in temuan:
            ada_k |= lab == "K"
            print(f"{nama}:{baris}: [{id_} {lab}] {cuplikan!r}: {saran}")
        if temuan:
            jumlah = Counter(x[2] for x in temuan)
            rincian = ", ".join(
                f"{label} {jumlah[label]}" for label in ("K", "G", "AI") if jumlah[label]
            )
            print(f"{nama}: {len(temuan)} temuan ({rincian})")
    return 1 if ada_k else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main(sys.argv[1:]))
