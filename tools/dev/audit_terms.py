r"""Audit italic istilah asing pada dokumen DOCX.

Alat ini membaca DOCX hasil build, mengelompokkan kata/frasa Latin, lalu
menulis laporan Markdown untuk ditinjau agent. Alat tidak mengubah DOCX,
glosarium, atau naskah; keputusan tetap di tangan peninjau.

Pemakaian:
    python tools/dev/audit_terms.py --docx Laporan.docx \\
        --glossary src/docgen/data/glossary/istilah.tsv \\
        --out .laporan/istilah-audit.md

Kode keluar:
    0  tidak ada temuan yang perlu diperbaiki/diputuskan
    2  ada ``PERLU DIPERBAIKI`` atau ``PERLU KEPUTUSAN``
    1  kesalahan input (DOCX/glosarium tidak valid)
"""

import argparse
import itertools
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from docgen.docx import DocxError
from docgen.docx.paragraphs import paragraph_style_id
from docgen.docx.terms import (
    BIBLIOGRAPHY_STYLE,
    Glossary,
    StyleResolver,
    build_paragraph_model,
    load_glossary,
    match_terms,
    open_docx,
)
from docgen.docx.xml import iter_paragraphs

DOCUMENT_PART = "word/document.xml"
HEADER_FOOTER_RE = re.compile(r"^word/(?:header|footer)\d*\.xml$")


# ---------------------------------------------------------------------------
# Kategori dan konstanta

CATEGORY_GLOSSARY_ITALIC = "glossary_italic"
CATEGORY_GLOSSARY_PLAIN = "glossary_plain"
CATEGORY_ITALIC_MISSING = "glossary_italic_missing"
CATEGORY_PLAIN_BUT_ITALIC = "glossary_plain_but_italic"
CATEGORY_UNKNOWN = "unknown"
CATEGORY_MIXED_CASE_NAME = "mixed_case_name"
CATEGORY_ABBREVIATION = "abbreviation"

FIX_CATEGORIES = {CATEGORY_ITALIC_MISSING, CATEGORY_PLAIN_BUT_ITALIC}
DECISION_CATEGORIES = {CATEGORY_UNKNOWN, CATEGORY_MIXED_CASE_NAME}
OK_CATEGORIES = {CATEGORY_GLOSSARY_ITALIC, CATEGORY_GLOSSARY_PLAIN}

CATEGORY_ORDER = (
    CATEGORY_GLOSSARY_ITALIC,
    CATEGORY_GLOSSARY_PLAIN,
    CATEGORY_ITALIC_MISSING,
    CATEGORY_PLAIN_BUT_ITALIC,
    CATEGORY_UNKNOWN,
    CATEGORY_MIXED_CASE_NAME,
)

CATEGORY_LABEL = {
    CATEGORY_GLOSSARY_ITALIC: "OK",
    CATEGORY_GLOSSARY_PLAIN: "OK",
    CATEGORY_ITALIC_MISSING: "perlu diperbaiki",
    CATEGORY_PLAIN_BUT_ITALIC: "perlu diperbaiki",
    CATEGORY_UNKNOWN: "perlu keputusan",
    CATEGORY_MIXED_CASE_NAME: "perlu keputusan (nama)",
}

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\u2019\-]*")
NON_PROSE_RE = re.compile(r"(?:https?://|www\.)\S+|\S+@\S+", re.IGNORECASE)
CONTEXT_WORD_RE = re.compile(r"\S+")

# Kata Indonesia yang sering muncul dan tidak perlu diputuskan sebagai istilah.
# Daftar ini sengaja tidak lengkap; tujuannya hanya mengurangi noise. Istilah
# yang ada di glosarium selalu diproses lebih dulu, jadi "data", "sistem", dan
# "metode" tetap diklasifikasikan lewat glosarium.
INDONESIAN_NOISE = set(
    [
        "ada",
        "adalah",
        "adanya",
        "adapun",
        "agak",
        "agar",
        "akan",
        "akankah",
        "akhir",
        "akhirnya",
        "aku",
        "amat",
        "antara",
        "antaranya",
        "apa",
        "apabila",
        "apakah",
        "apalagi",
        "apatah",
        "atau",
        "ataupun",
        "bagaimana",
        "bagaimanakah",
        "bagaimanapun",
        "bagi",
        "bagian",
        "bahkan",
        "bahwa",
        "bahwasanya",
        "baik",
        "bakal",
        "banyak",
        "beberapa",
        "begitu",
        "belum",
        "benar",
        "berapa",
        "berada",
        "berarti",
        "berikut",
        "bersama",
        "betul",
        "biasa",
        "biasanya",
        "bila",
        "bilakah",
        "bisa",
        "boleh",
        "buat",
        "bukan",
        "bukankah",
        "bukanlah",
        "bukannya",
        "cara",
        "cukup",
        "cuma",
        "dahulu",
        "dalam",
        "dan",
        "dapat",
        "dari",
        "daripada",
        "datang",
        "demi",
        "dengan",
        "di",
        "dia",
        "dialah",
        "diantaranya",
        "dilakukan",
        "digunakan",
        "hal",
        "hampir",
        "hanya",
        "harus",
        "hingga",
        "ia",
        "ini",
        "itu",
        "jadi",
        "jika",
        "jikalau",
        "juga",
        "justru",
        "kala",
        "kalau",
        "kalaulah",
        "kalaupun",
        "kali",
        "kan",
        "kapan",
        "kapankah",
        "kapanpun",
        "karena",
        "karenanya",
        "kata",
        "keadaan",
        "kecil",
        "kemudian",
        "kenapa",
        "kepada",
        "ketika",
        "khususnya",
        "kini",
        "kita",
        "kok",
        "lagi",
        "lagian",
        "lah",
        "lain",
        "lainnya",
        "lalu",
        "lama",
        "langsung",
        "lebih",
        "maka",
        "makanya",
        "makin",
        "malah",
        "malahan",
        "mampu",
        "mana",
        "manakala",
        "masih",
        "masing",
        "mau",
        "maupun",
        "melainkan",
        "melalui",
        "membuat",
        "memastikan",
        "membutuhkan",
        "memiliki",
        "memungkinkan",
        "mengenai",
        "mengapa",
        "menjadi",
        "menurut",
        "merupakan",
        "menyatakan",
        "mereka",
        "meski",
        "meskipun",
        "minta",
        "misal",
        "misalnya",
        "nah",
        "namun",
        "nanti",
        "nyaris",
        "oleh",
        "pada",
        "padahal",
        "paling",
        "pantas",
        "para",
        "pasti",
        "pernah",
        "perlu",
        "pula",
        "pun",
        "rasa",
        "rupanya",
        "saat",
        "saja",
        "saling",
        "sama",
        "sambil",
        "sampai",
        "sana",
        "sangat",
        "sebab",
        "sebagai",
        "sebagaimana",
        "sebagainya",
        "sebaliknya",
        "sebanyak",
        "sebelum",
        "sebelumnya",
        "sebenarnya",
        "seberapa",
        "sebuah",
        "secara",
        "sedang",
        "sedangkan",
        "sedikit",
        "segala",
        "segera",
        "seharusnya",
        "sehingga",
        "sejak",
        "sejenak",
        "sekali",
        "sekalian",
        "sekalipun",
        "sekarang",
        "sekitar",
        "sela",
        "selagi",
        "selain",
        "selaku",
        "selalu",
        "selama",
        "selanjutnya",
        "seluruh",
        "semacam",
        "semakin",
        "semoga",
        "semua",
        "semula",
        "sendiri",
        "seorang",
        "sepanjang",
        "seperti",
        "serta",
        "sesaat",
        "sesama",
        "sesudah",
        "setelah",
        "setempat",
        "setengah",
        "seterusnya",
        "setiap",
        "setidaknya",
        "sewaktu",
        "siapa",
        "sini",
        "suatu",
        "sudah",
        "supaya",
        "tadi",
        "tak",
        "tanpa",
        "tampaknya",
        "tapi",
        "telah",
        "tentang",
        "terhadap",
        "termasuk",
        "tersebut",
        "tertentu",
        "tetapi",
        "tiap",
        "tidak",
        "toh",
        "walaupun",
        "walau",
        "yaitu",
        "yakin",
        "yang",
        "untuk",
        "sesuai",
        "berbasis",
        "data",
        "akademik",
        "akurasi",
        "algoritma",
        "analisis",
        "angka",
        "aplikasi",
        "arsitektur",
        "bagian",
        "bentuk",
        "berkas",
        "budaya",
        "contoh",
        "dampak",
        "dasar",
        "deskripsi",
        "digital",
        "dokumen",
        "evaluasi",
        "faktor",
        "fitur",
        "font",
        "format",
        "formal",
        "fungsi",
        "gambar",
        "global",
        "halaman",
        "hasil",
        "ilmiah",
        "implementasi",
        "informasi",
        "instalasi",
        "integrasi",
        "internasional",
        "jumlah",
        "judul",
        "karakter",
        "karya",
        "kata",
        "kebutuhan",
        "kegiatan",
        "keamanan",
        "kemampuan",
        "kerja",
        "kesimpulan",
        "khusus",
        "kualitas",
        "kuantitas",
        "kunci",
        "lampiran",
        "latar",
        "lembar",
        "letak",
        "lokal",
        "mahasiswa",
        "manual",
        "margin",
        "masalah",
        "metode",
        "model",
        "nasional",
        "nilai",
        "nomor",
        "objek",
        "otomatis",
        "panduan",
        "paragraf",
        "pembahasan",
        "pendahuluan",
        "pengantar",
        "penelitian",
        "pengguna",
        "pengujian",
        "penulisan",
        "penulis",
        "perangkat",
        "perintah",
        "persen",
        "presets",
        "proses",
        "proyek",
        "pustaka",
        "referensi",
        "responden",
        "sampel",
        "sampul",
        "sistem",
        "skor",
        "standar",
        "struktur",
        "tabel",
        "tahap",
        "tampilan",
        "teks",
        "template",
        "tingkat",
        "tujuan",
        "uji",
        "ukuran",
        "umum",
        "utama",
        "variabel",
        "versi",
        "visual",
        "waktu",
        "warna",
    ]
)

# Kata isi Indonesia yang umum di laporan akademik. Daftar ini tetap bukan
# kamus lengkap; istilah asing yang belum diputuskan harus tetap muncul.
INDONESIAN_NOISE |= set(
    [
        "aktif",
        "aktivitas",
        "akademisi",
        "akar",
        "alat",
        "algoritme",
        "anggota",
        "aplikasi",
        "arab",
        "arsitektur",
        "asumsi",
        "atribut",
        "badan",
        "bahan",
        "baris",
        "batasan",
        "beban",
        "belajar",
        "belakang",
        "bentuk",
        "berbagai",
        "berat",
        "berlaku",
        "biaya",
        "bidang",
        "bobot",
        "budaya",
        "bulan",
        "buku",
        "cabang",
        "cepat",
        "contoh",
        "daftar",
        "dampak",
        "dasar",
        "data",
        "definisi",
        "depan",
        "desa",
        "detik",
        "diagram",
        "digital",
        "dokumen",
        "dokumentasi",
        "dosen",
        "dunia",
        "dukungan",
        "efektif",
        "efisien",
        "faktor",
        "fakultas",
        "fiksi",
        "fitur",
        "font",
        "formal",
        "format",
        "fungsi",
        "gambar",
        "gaya",
        "gelar",
        "grafik",
        "halaman",
        "hari",
        "harga",
        "hasil",
        "huruf",
        "indonesia",
        "indikator",
        "informasi",
        "infrastruktur",
        "aktual",
        "kampus",
        "konten",
        "instalasi",
        "integrasi",
        "internasional",
        "isi",
        "jam",
        "jaringan",
        "jumlah",
        "judul",
        "jurusan",
        "karakter",
        "karya",
        "kasus",
        "kategori",
        "kebutuhan",
        "kegiatan",
        "kedua",
        "keamanan",
        "kecil",
        "kemampuan",
        "kerja",
        "kesimpulan",
        "khusus",
        "kinerja",
        "klaster",
        "kode",
        "kolom",
        "komponen",
        "konsep",
        "konstanta",
        "kontribusi",
        "korelasi",
        "kota",
        "kualitas",
        "kuantitas",
        "kunci",
        "kurang",
        "kursi",
        "lampiran",
        "lama",
        "lapisan",
        "laptop",
        "latar",
        "lebar",
        "lembar",
        "level",
        "lingkungan",
        "lintasan",
        "lokal",
        "lokasi",
        "lunak",
        "mahasiswa",
        "malam",
        "manfaat",
        "manual",
        "margin",
        "masalah",
        "mata",
        "meja",
        "memori",
        "menit",
        "metode",
        "model",
        "modul",
        "mudah",
        "negara",
        "nilai",
        "nomor",
        "objek",
        "objektif",
        "orang",
        "otomatis",
        "pagi",
        "paket",
        "panduan",
        "panjang",
        "paragraf",
        "pasangan",
        "peluang",
        "pembaca",
        "penelitian",
        "pengguna",
        "pengujian",
        "peneliti",
        "penulisan",
        "penulis",
        "perangkat",
        "perintah",
        "persen",
        "peserta",
        "proses",
        "prosesor",
        "produktif",
        "program",
        "properti",
        "prosiding",
        "pustaka",
        "referensi",
        "relatif",
        "responden",
        "risiko",
        "romawi",
        "ruang",
        "rumus",
        "salah",
        "sampel",
        "sampul",
        "sandi",
        "saran",
        "sektor",
        "semester",
        "senarai",
        "simpul",
        "sintaks",
        "sistem",
        "siang",
        "skor",
        "skrip",
        "soal",
        "sore",
        "spasi",
        "standar",
        "struktur",
        "studi",
        "subjek",
        "subjektif",
        "sulit",
        "tabel",
        "tahap",
        "tahun",
        "taksi",
        "tampilan",
        "tata",
        "tautan",
        "teks",
        "tepat",
        "teori",
        "tinggi",
        "tingkat",
        "tujuan",
        "uji",
        "ukuran",
        "umum",
        "unduhan",
        "unggahan",
        "utama",
        "variabel",
        "versi",
        "visual",
        "visi",
        "waktu",
        "warna",
        "abstrak",
        "acara",
        "agenda",
        "alumni",
        "antarmuka",
        "argumen",
        "aturan",
        "bab",
        "basis",
        "bersih",
        "berhasil",
        "biografi",
        "butir",
        "citra",
        "daun",
        "depan",
        "dua",
        "elemen",
        "entri",
        "frasa",
        "galat",
        "ganda",
        "gedung",
        "geometri",
        "glosarium",
        "gradien",
        "graf",
        "hambatan",
        "hidup",
        "himpunan",
        "hipotesis",
        "indeks",
        "istilah",
        "jalur",
        "jadwal",
        "jurnal",
        "kabupaten",
        "kalimat",
        "kamus",
        "kasih",
        "kelas",
        "kendala",
        "keras",
        "ketiga",
        "keempat",
        "kelima",
        "ketua",
        "kontribusi",
        "kurikulum",
        "kuliah",
        "laboratorium",
        "laporan",
        "lanjutan",
        "lokakarya",
        "masa",
        "membangun",
        "mendatang",
        "mesin",
        "moderasi",
        "moderator",
        "motto",
        "nama",
        "narasumber",
        "neuron",
        "panitia",
        "pembimbing",
        "penguji",
        "ponsel",
        "poin",
        "pohon",
        "prakata",
        "prasarana",
        "pertama",
        "profil",
        "ringan",
        "riwayat",
        "sarana",
        "sekretaris",
        "seksi",
        "seminar",
        "silabus",
        "sisi",
        "situs",
        "surat",
        "susunan",
        "tantangan",
        "telepon",
        "tempat",
        "teorema",
        "terima",
        "tesis",
        "tiga",
        "tipe",
        "tugas",
        "ucapan",
        "uang",
        "anova",
        "angket",
        "bahasa",
        "bisnis",
        "derajat",
        "dinamis",
        "ekonomi",
        "empiris",
        "etika",
        "eksperimen",
        "filsafat",
        "fisika",
        "generik",
        "gizi",
        "hukum",
        "inferensial",
        "informatika",
        "instrumen",
        "informan",
        "kausal",
        "kimia",
        "konsisten",
        "korelasional",
        "kovarians",
        "kredibel",
        "kuasi",
        "manajemen",
        "matematika",
        "matriks",
        "maksimal",
        "maksimum",
        "metodologis",
        "minimal",
        "minimum",
        "modus",
        "olahraga",
        "optimal",
        "pariwisata",
        "persentase",
        "praktis",
        "profesional",
        "rasio",
        "relevan",
        "rerata",
        "residu",
        "residual",
        "rata-rata",
        "sastra",
        "seni",
        "sensus",
        "signifikan",
        "sistematis",
        "skala",
        "spesifik",
        "statis",
        "survei",
        "taraf",
        "teoretis",
        "valid",
        "varians",
        "vektor",
        "wawancara",
        "dibahas",
        "dibangun",
        "dibuka",
        "dibuat",
        "dianggap",
        "diakses",
        "dianalisis",
        "dipasang",
        "dihapus",
        "dihitung",
        "dilihat",
        "diproses",
        "dirancang",
        "disebut",
        "diukur",
        "diunduh",
        "diuji",
        "ditutup",
        "diperoleh",
        "dilatih",
        "membaca",
        "membuat",
        "mendapat",
        "melatih",
        "menerima",
        "mengirim",
        "mengambil",
        "memilih",
        "mendengar",
        "menulis",
    ]
)

# Kata fungsi Inggris yang lazim muncul di sitasi/abstract dan bukan istilah
# yang perlu diputuskan.
ENGLISH_STOPWORDS = set(
    [
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "of",
        "in",
        "on",
        "at",
        "to",
        "by",
        "without",
        "within",
        "into",
        "onto",
        "over",
        "under",
        "about",
        "after",
        "before",
        "between",
        "during",
        "through",
        "across",
        "against",
        "among",
        "around",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "do",
        "does",
        "did",
        "done",
        "have",
        "has",
        "had",
        "having",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "its",
        "our",
        "their",
        "not",
        "no",
        "nor",
        "so",
        "as",
        "such",
        "very",
        "too",
        "also",
        "just",
        "only",
        "own",
        "same",
        "any",
        "all",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "can",
        "could",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "how",
        "why",
        "whether",
        "while",
        "because",
        "although",
        "though",
        "since",
        "until",
        "unless",
        "however",
        "therefore",
        "thus",
        "hence",
        "moreover",
        "furthermore",
        "nevertheless",
        "otherwise",
        "instead",
        "whereas",
        "either",
        "neither",
        "yet",
        "still",
        "already",
        "again",
        "ever",
        "never",
        "always",
        "often",
        "sometimes",
        "usually",
        "generally",
        "specifically",
        "particularly",
        "especially",
        "including",
        "etc",
        "via",
        "per",
        "url",
        "api",
        "http",
        "https",
        "www",
    ]
)

INDONESIAN_PREFIXES = (
    "memper",
    "diper",
    "meng",
    "meny",
    "mem",
    "men",
    "ber",
    "ter",
    "per",
    "pem",
    "pen",
    "peng",
    "peny",
    "me",
    "di",
    "ke",
    "se",
    "pe",
)


# ---------------------------------------------------------------------------
# Resolusi italic


def iter_audit_paragraphs(
    package: object,
) -> list[tuple[object, dict[str, object]]]:
    """Paragraf body, tabel, header, dan footer beserta relasinya.

    Resolver style dan istilah ada di ``docgen.docx``; alat dev ini hanya
    membaca data dari package DOCX, bukan menjalankan kode dari folder input.
    """

    names = [DOCUMENT_PART]
    names.extend(
        name
        for name in package.part_names()  # type: ignore[attr-defined]
        if HEADER_FOOTER_RE.match(name)
    )
    paragraphs: list[tuple[object, dict[str, object]]] = []
    for name in names:
        root = package.xml(name)  # type: ignore[attr-defined]
        relations = {
            rel.rel_id: rel
            for rel in package.relationships(name)  # type: ignore[attr-defined]
        }
        for paragraph in iter_paragraphs(root):
            if paragraph_style_id(paragraph) == BIBLIOGRAPHY_STYLE:
                continue
            paragraphs.append((paragraph, relations))
    return paragraphs


# ---------------------------------------------------------------------------
# Heuristik kata


def _letter_count(text: str) -> int:
    return sum(character.isalpha() for character in text)


def is_abbreviation(token: str) -> bool:
    """True untuk akronim kapital pendek: LSTM, CNN, COVID-19."""

    letters = [character for character in token if character.isalpha()]
    return bool(letters) and len(letters) <= 6 and token.isupper()


def is_mixed_case_name(token: str) -> bool:
    """True untuk nama dengan kapital di tengah: PostgreSQL, JavaScript.

    Kata yang hanya berawal kapital (``Graphical``, ``Python``) tidak dianggap
    CamelCase. Dengan begitu ``Graphical`` tetap muncul sebagai ``unknown`` dan
    perlu diputuskan, sesuai perilaku yang diuji.
    """

    letters = [character for character in token if character.isalpha()]
    if len(letters) < 2 or token.isupper():
        return False
    return any(
        previous.islower() and current.isupper()
        for previous, current in itertools.pairwise(letters)
    )


def looks_indonesian(token: str) -> bool:
    """Heuristik konservatif untuk kata Indonesia yang tidak perlu diaudit."""

    lower = token.casefold()
    if lower in INDONESIAN_NOISE:
        return True
    if len(lower) >= 4 and lower.endswith(("nya", "lah", "kah", "pun", "ku", "mu")):
        return True
    if len(lower) >= 4 and lower.endswith("kan"):
        return True
    # Akhiran -an dengan awalan Indonesia: dilakukan, penggunaan, penelitian.
    # Minimal 7 huruf agar "median"/"mean"/"human"/"organ" tidak ikut hilang.
    if len(lower) >= 7 and lower.endswith("an") and lower.startswith(INDONESIAN_PREFIXES):
        return True
    # Akhiran nominal/verba Indonesia yang jarang bertabrakan dengan istilah
    # teknis Inggris. Batas panjang menjaga kata pendek seperti "taxi" tetap
    # diperiksa.
    if len(lower) >= 6 and lower.endswith(("si", "ik", "ah")):
        return True
    if len(lower) >= 7 and lower.endswith(("isme", "itas", "ologi", "ografi")):
        return True
    if len(lower) >= 5 and lower.endswith("if"):
        return True
    # Verba berawalan me-/di- berakhiran -i atau -ai: memakai, dipakai,
    # mengatasi, menghadapi. Batas 6 huruf menghindari "media"/"dime".
    return len(lower) >= 6 and lower.startswith(("me", "di")) and lower.endswith("i")


def is_english_stopword(token: str) -> bool:
    return token.casefold() in ENGLISH_STOPWORDS


def normalize_key(text: str) -> str:
    return text.casefold().replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")


# ---------------------------------------------------------------------------
# Model hasil audit


@dataclass(frozen=True)
class Occurrence:
    key: str
    display: str
    category: str
    paragraph: int
    start: int
    end: int
    context: str
    is_name: bool = False
    italic: bool = False


@dataclass
class Group:
    key: str
    display: str
    category: str
    is_name: bool
    occurrences: list[Occurrence] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.occurrences)


@dataclass
class AuditResult:
    occurrences: list[Occurrence]
    groups: list[Group]
    paragraph_count: int
    abbreviation_count: int
    abbreviation_terms: set[str]
    noise_count: int

    def groups_for(self, categories: set[str]) -> list[Group]:
        return [group for group in self.groups if group.category in categories]

    @property
    def needs_fix(self) -> list[Group]:
        return self.groups_for(FIX_CATEGORIES)

    @property
    def needs_decision(self) -> list[Group]:
        return self.groups_for(DECISION_CATEGORIES)

    @property
    def ok_groups(self) -> list[Group]:
        return self.groups_for(OK_CATEGORIES)


# ---------------------------------------------------------------------------
# Pengumpulan temuan


def make_context(text: str, start: int, end: int, window: int = 8) -> str:
    """Ambil 8 kata sebelum/sesudah dengan target ditebalkan."""

    words = list(CONTEXT_WORD_RE.finditer(text))
    before = [word for word in words if word.end() <= start]
    after = [word for word in words if word.start() >= end]
    selected_before = before[-window:]
    selected_after = after[:window]

    target = text[start:end]
    parts = [word.group(0) for word in selected_before]
    parts.append(f"**{target}**")
    parts.extend(word.group(0) for word in selected_after)

    context = " ".join(parts)
    if len(before) > window:
        context = "… " + context
    if len(after) > window:
        context = context + " …"
    context = context.replace("\ufffc", "…")
    context = re.sub(r"\s+", " ", context).strip()
    context = re.sub(r"…+", "…", context)
    return context or "—"


def _ranges(text: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    return [(match.start(), match.end()) for match in pattern.finditer(text)]


def _overlaps_any(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < range_end and range_start < end for range_start, range_end in ranges)


def collect_occurrences(docx_path: Path, glossary: Glossary) -> AuditResult:
    """Baca DOCX dan kumpulkan semua kemunculan yang relevan."""

    docx_path = Path(docx_path)
    package = open_docx(docx_path)
    resolver = StyleResolver(package)
    occurrences: list[Occurrence] = []
    paragraph_count = 0
    abbreviation_count = 0
    abbreviation_terms: set[str] = set()
    noise_count = 0

    for paragraph_no, (paragraph, relations) in enumerate(iter_audit_paragraphs(package), start=1):
        model = build_paragraph_model(paragraph, relations)
        text = model.text
        if not text.strip():
            continue
        paragraph_count += 1

        non_prose_ranges = _ranges(text, NON_PROSE_RE)
        occupied = bytearray(len(text))

        # 1. Istilah/frasa dari glosarium. Frasa terpanjang menang, sehingga
        #    "training data" tidak dipecah menjadi "training" + "data".
        for match in match_terms(text, glossary):
            start, end = match.start, match.end
            if _overlaps_any(start, end, non_prose_ranges):
                continue
            if any(occupied[start:end]):
                continue
            chars = model.chars[start:end]
            if not chars or any(char is None for char in chars):
                continue

            # Spasi/tanda baca di antara kata tidak menentukan status italic;
            # yang dinilai adalah huruf-hurufnya. Ini penting saat istilah
            # terpotong beberapa run dan spasi berada di run tegak.
            span = text[start:end]
            flags = [
                resolver.effective(char.run, paragraph)  # type: ignore[union-attr]
                for char, character in zip(chars, span, strict=True)
                if char is not None and character.isalpha()
            ]
            if not flags:
                flags = [
                    resolver.effective(char.run, paragraph)  # type: ignore[union-attr]
                    for char in chars
                    if char is not None
                ]
            any_italic = any(flags)
            all_italic = all(flags)

            if match.entry.italic:
                category = CATEGORY_GLOSSARY_ITALIC if all_italic else CATEGORY_ITALIC_MISSING
            else:
                category = CATEGORY_PLAIN_BUT_ITALIC if any_italic else CATEGORY_GLOSSARY_PLAIN

            display = text[start:end]
            occurrences.append(
                Occurrence(
                    key=normalize_key(match.entry.term),
                    display=display,
                    category=category,
                    paragraph=paragraph_no,
                    start=start,
                    end=end,
                    context=make_context(text, start, end),
                    italic=all_italic,
                )
            )
            occupied[start:end] = b"\x01" * (end - start)

        # 2. Kata Latin lain yang belum tercakup glosarium.
        for match in TOKEN_RE.finditer(text):
            start, end = match.start(), match.end()
            while end > start and text[end - 1] in {"'", "\u2019", "-"}:
                end -= 1
            token = text[start:end]

            if _letter_count(token) < 3:
                continue
            if any(occupied[start:end]):
                continue
            if _overlaps_any(start, end, non_prose_ranges):
                continue

            chars = model.chars[start:end]
            if not chars or any(char is None for char in chars):
                continue

            if is_abbreviation(token):
                abbreviation_count += 1
                abbreviation_terms.add(normalize_key(token))
                continue

            if is_mixed_case_name(token):
                category = CATEGORY_MIXED_CASE_NAME
                is_name = True
            elif looks_indonesian(token) or is_english_stopword(token):
                noise_count += 1
                continue
            else:
                category = CATEGORY_UNKNOWN
                is_name = False

            letter_flags = [
                resolver.effective(char.run, paragraph)  # type: ignore[union-attr]
                for char, character in zip(chars, token, strict=True)
                if char is not None and character.isalpha()
            ]
            occurrences.append(
                Occurrence(
                    key=normalize_key(token),
                    display=token,
                    category=category,
                    paragraph=paragraph_no,
                    start=start,
                    end=end,
                    context=make_context(text, start, end),
                    is_name=is_name,
                    italic=bool(letter_flags) and all(letter_flags),
                )
            )

    occurrences.sort(key=lambda occurrence: (occurrence.paragraph, occurrence.start))
    groups = _group_occurrences(occurrences)
    groups.sort(key=lambda group: (-group.count, group.key, group.category))
    return AuditResult(
        occurrences=occurrences,
        groups=groups,
        paragraph_count=paragraph_count,
        abbreviation_count=abbreviation_count,
        abbreviation_terms=abbreviation_terms,
        noise_count=noise_count,
    )


def _group_occurrences(occurrences: list[Occurrence]) -> list[Group]:
    groups: dict[tuple[str, str, bool], Group] = {}
    for occurrence in occurrences:
        group_key = (occurrence.category, occurrence.key, occurrence.is_name)
        group = groups.get(group_key)
        if group is None:
            group = Group(
                key=occurrence.key,
                display=occurrence.display,
                category=occurrence.category,
                is_name=occurrence.is_name,
            )
            groups[group_key] = group
        group.occurrences.append(occurrence)
    return list(groups.values())


def audit_docx(docx_path: Path, glossary: Glossary) -> AuditResult:
    """API utama untuk tes dan pemakaian internal."""

    return collect_occurrences(docx_path, glossary)


# ---------------------------------------------------------------------------
# Render Markdown


def _escape_cell(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "'")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _word_cell(group: Group) -> str:
    word = f"`{_escape_cell(group.display)}`"
    if group.is_name:
        word += " (`name`)"
    return word


def _contexts(group: Group, limit: int) -> str:
    contexts: list[str] = []
    seen: set[str] = set()
    for occurrence in group.occurrences:
        context = _escape_cell(occurrence.context)
        if context in seen:
            continue
        seen.add(context)
        contexts.append(context)
        if len(contexts) >= limit:
            break
    return "<br>".join(contexts) if contexts else "—"


def _plural_occurrences(count: int) -> str:
    return f"{count} kemunculan"


def render_report(result: AuditResult, docx_path: Path, glossary_path: Path) -> str:
    """Hasilkan laporan Markdown deterministik (tanpa timestamp)."""

    docx_path = Path(docx_path)
    glossary_path = Path(glossary_path)
    lines: list[str] = []
    lines.append("# Audit Italic Istilah")
    lines.append("")
    lines.append(f"- Dokumen: `{_escape_cell(docx_path.as_posix())}`")
    lines.append(f"- Glosarium: `{_escape_cell(glossary_path.as_posix())}`")
    lines.append(f"- Paragraf diperiksa: {result.paragraph_count}")
    lines.append("")
    lines.append("## Ringkasan")
    lines.append("")
    lines.append("| Kategori | Istilah unik | Kemunculan |")
    lines.append("|---|---:|---:|")
    for category in CATEGORY_ORDER:
        groups = [group for group in result.groups if group.category == category]
        occurrences = sum(group.count for group in groups)
        label = CATEGORY_LABEL[category]
        lines.append(f"| `{category}` ({label}) | {len(groups)} | {occurrences} |")
    lines.append(
        f"| `{CATEGORY_ABBREVIATION}` (diabaikan) | "
        f"{len(result.abbreviation_terms)} | {result.abbreviation_count} |"
    )
    lines.append("")
    lines.append(f"Kata Indonesia/Inggris umum yang dilewati: {result.noise_count} kemunculan.")
    lines.append("")

    fix_groups = result.needs_fix
    decision_groups = result.needs_decision
    fix_occurrences = sum(group.count for group in fix_groups)
    decision_occurrences = sum(group.count for group in decision_groups)
    lines.append(
        f"**PERLU DIPERBAIKI:** {len(fix_groups)} istilah "
        f"({_plural_occurrences(fix_occurrences)}) · "
        f"**PERLU KEPUTUSAN:** {len(decision_groups)} istilah "
        f"({_plural_occurrences(decision_occurrences)})"
    )
    lines.append("")

    lines.append("## PERLU DIPERBAIKI")
    lines.append("")
    if not fix_groups:
        lines.append("_Tidak ada._")
    else:
        lines.append("| Kata/frasa | Status | Jumlah | Contoh konteks |")
        lines.append("|---|---|---:|---|")
        for group in fix_groups:
            lines.append(
                f"| {_word_cell(group)} | `{group.category}` | {group.count} "
                f"| {_contexts(group, 1)} |"
            )
    lines.append("")

    lines.append("## PERLU KEPUTUSAN")
    lines.append("")
    if not decision_groups:
        lines.append("_Tidak ada._")
    else:
        lines.append("| Kata/frasa | Jumlah | 3 contoh konteks |")
        lines.append("|---|---:|---|")
        for group in decision_groups:
            lines.append(f"| {_word_cell(group)} | {group.count} | {_contexts(group, 3)} |")
    lines.append("")

    lines.append("## OK")
    lines.append("")
    ok_groups = result.ok_groups
    if not ok_groups:
        lines.append("_Tidak ada._")
    else:
        lines.append("| Kata/frasa | Jumlah |")
        lines.append("|---|---:|")
        for group in ok_groups:
            lines.append(f"| `{_escape_cell(group.display)}` | {group.count} |")
    lines.append("")

    lines.append("## Cara menindaklanjuti")
    lines.append("")
    lines.append(
        "1. **`glossary_italic_missing`** — istilah sudah `italic=yes` di "
        "glosarium tetapi belum italic. Periksa konteks; jika memang harus "
        "italic, build ulang dengan `uv run --project . docgen build "
        "document.md --terms` agar stage terms memberi style "
        "`IstilahAsing`. Jika keputusannya berubah, ubah `italic=no` di "
        "`src/docgen/data/glossary/istilah.tsv`."
    )
    lines.append(
        "2. **`glossary_plain_but_italic`** — istilah `italic=no` muncul "
        "italic. Hapus penekanan italic di `document.md`, atau ubah baris "
        "glosarium menjadi `italic=yes` bila keputusan berubah."
    )
    lines.append(
        "3. **`unknown` / `mixed_case_name`** — belum ada keputusan. Tambahkan "
        "baris ke `src/docgen/data/glossary/istilah.tsv` (`term`, `italic` dengan "
        "nilai `yes` atau `no`) atau pastikan istilah memang tegak dan tidak "
        "perlu masuk glosarium. Nama dengan kapital di tengah ditandai `name`."
    )
    lines.append(
        "4. Setelah mengubah `src/docgen/data/glossary/istilah.tsv` atau "
        "`document.md`, build ulang, lalu jalankan audit ini lagi sampai "
        "tidak ada temuan dan exit code `0`."
    )
    lines.append("")
    lines.append(
        "Alat ini tidak mengubah DOCX, glosarium, atau naskah. Semua keputusan "
        "tetap di tangan agent/penulis."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Audit italic istilah asing pada DOCX dan tulis laporan Markdown.")
    )
    parser.add_argument(
        "--docx",
        type=Path,
        required=True,
        help="file DOCX yang diaudit (mis. Laporan.docx)",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        default=Path("src/docgen/data/glossary/istilah.tsv"),
        help="glosarium TSV (default: src/docgen/data/glossary/istilah.tsv)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".laporan/istilah-audit.md"),
        help="laporan Markdown (default: .laporan/istilah-audit.md)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        glossary = load_glossary(args.glossary)
        result = audit_docx(args.docx, glossary)
        report = render_report(result, args.docx, args.glossary)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(report)

        fix_terms = len(result.needs_fix)
        decision_terms = len(result.needs_decision)
        print(f"Laporan audit: {args.out.as_posix()}")
        print(
            f"Paragraf diperiksa: {result.paragraph_count}; "
            f"perlu diperbaiki: {fix_terms} istilah; "
            f"perlu keputusan: {decision_terms} istilah."
        )
        return 2 if (fix_terms or decision_terms) else 0
    except (DocxError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except AttributeError, OSError:
        pass
    raise SystemExit(main())
