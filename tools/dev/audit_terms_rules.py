"""Aturan, regex, dan heuristik kata untuk audit istilah asing.

Modul ini tidak membaca DOCX dan tidak menulis laporan. Daftar kata, regex,
dan heuristik dipertahankan dari implementasi sebelumnya supaya hasil audit
tidak berubah.
"""

import itertools
import re

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\u2019\-]*")
NON_PROSE_RE = re.compile(r"(?:https?://|www\.)\S+|\S+@\S+", re.IGNORECASE)
CONTEXT_WORD_RE = re.compile(r"\S+")

# Kata Indonesia yang sering muncul dan tidak perlu diputuskan sebagai istilah.
# Daftar ini sengaja tidak lengkap; tujuannya hanya mengurangi noise. Istilah
# yang ada di glosarium selalu diproses lebih dulu, jadi "data", "sistem", dan
# "metode" tetap diklasifikasikan lewat glosarium.
#
# Kata isi Indonesia yang umum di laporan akademik. Daftar ini tetap bukan
# kamus lengkap; istilah asing yang belum diputuskan harus tetap muncul.
INDONESIAN_NOISE = set(
    re.findall(
        r"\S+",
        """
    abstrak acara ada adalah adanya adapun agak agar agenda akademik akademisi akan akankah akar
    akhir akhirnya aktif aktivitas aktual aku akurasi alat algoritma algoritme alumni amat
    analisis anggota angka angket anova antara antaranya antarmuka apa apabila apakah apalagi
    apatah aplikasi arab argumen arsitektur asumsi atau ataupun atribut aturan bab badan
    bagaimana bagaimanakah bagaimanapun bagi bagian bahan bahasa bahkan bahwa bahwasanya baik
    bakal banyak baris basis batasan beban beberapa begitu belajar belakang belum benar bentuk
    berada berapa berarti berat berbagai berbasis berhasil berikut berkas berlaku bersama bersih
    betul biasa biasanya biaya bidang bila bilakah biografi bisa bisnis bobot boleh buat budaya
    bukan bukankah bukanlah bukannya buku bulan butir cabang cara cepat citra contoh cukup cuma
    daftar dahulu dalam dampak dan dapat dari daripada dasar data datang daun definisi demi
    dengan depan derajat desa deskripsi detik di dia diagram diakses dialah dianalisis dianggap
    diantaranya dibahas dibangun dibuat dibuka digital digunakan dihapus dihitung dilakukan
    dilatih dilihat dinamis dipasang diperoleh diproses dirancang disebut ditutup diuji diukur
    diunduh dokumen dokumentasi dosen dua dukungan dunia efektif efisien ekonomi eksperimen
    elemen empiris entri etika evaluasi faktor fakultas fiksi filsafat fisika fitur font formal
    format frasa fungsi galat gambar ganda gaya gedung gelar generik geometri gizi global
    glosarium gradien graf grafik hal halaman hambatan hampir hanya harga hari harus hasil hidup
    himpunan hingga hipotesis hukum huruf ia ilmiah implementasi indeks indikator indonesia
    inferensial informan informasi informatika infrastruktur ini instalasi instrumen integrasi
    internasional isi istilah itu jadi jadwal jalur jam jaringan jika jikalau judul juga jumlah
    jurnal jurusan justru kabupaten kala kalau kalaulah kalaupun kali kalimat kampus kamus kan
    kapan kapankah kapanpun karakter karena karenanya karya kasih kasus kata kategori kausal
    keadaan keamanan kebutuhan kecil kedua keempat kegiatan kelas kelima kemampuan kemudian
    kenapa kendala kepada keras kerja kesimpulan ketiga ketika ketua khusus khususnya kimia
    kinerja kini kita klaster kode kok kolom komponen konsep konsisten konstanta konten
    kontribusi korelasi korelasional kota kovarians kredibel kualitas kuantitas kuasi kuliah
    kunci kurang kurikulum kursi laboratorium lagi lagian lah lain lainnya lalu lama lampiran
    langsung lanjutan lapisan laporan laptop latar lebar lebih lembar letak level lingkungan
    lintasan lokakarya lokal lokasi lunak mahasiswa maka makanya makin maksimal maksimum malah
    malahan malam mampu mana manajemen manakala manfaat manual margin masa masalah masih masing
    mata matematika matriks mau maupun meja melainkan melalui melatih memastikan membaca
    membangun membuat membutuhkan memilih memiliki memori memungkinkan mendapat mendatang
    mendengar menerima mengambil mengapa mengenai mengirim menit menjadi menulis menurut
    menyatakan mereka merupakan mesin meski meskipun metode metodologis minimal minimum minta
    misal misalnya model moderasi moderator modul modus motto mudah nah nama namun nanti
    narasumber nasional negara neuron nilai nomor nyaris objek objektif olahraga oleh optimal
    orang otomatis pada padahal pagi paket paling panduan panitia panjang pantas para paragraf
    pariwisata pasangan pasti peluang pembaca pembahasan pembimbing pendahuluan peneliti
    penelitian pengantar pengguna penguji pengujian penulis penulisan perangkat perintah perlu
    pernah persen persentase pertama peserta pohon poin ponsel prakata praktis prasarana presets
    produktif profesional profil program properti proses prosesor prosiding proyek pula pun
    pustaka rasa rasio rata-rata referensi relatif relevan rerata residu residual responden
    ringan risiko riwayat romawi ruang rumus rupanya saat saja salah saling sama sambil sampai
    sampel sampul sana sandi sangat saran sarana sastra sebab sebagai sebagaimana sebagainya
    sebaliknya sebanyak sebelum sebelumnya sebenarnya seberapa sebuah secara sedang sedangkan
    sedikit segala segera seharusnya sehingga sejak sejenak sekali sekalian sekalipun sekarang
    sekitar sekretaris seksi sektor sela selagi selain selaku selalu selama selanjutnya seluruh
    semacam semakin semester seminar semoga semua semula senarai sendiri seni sensus seorang
    sepanjang seperti serta sesaat sesama sesuai sesudah setelah setempat setengah seterusnya
    setiap setidaknya sewaktu siang siapa signifikan silabus simpul sini sintaks sisi sistem
    sistematis situs skala skor skrip soal sore spasi spesifik standar statis struktur studi
    suatu subjek subjektif sudah sulit supaya surat survei susunan tabel tadi tahap tahun tak
    taksi tampaknya tampilan tanpa tantangan tapi taraf tata tautan teks telah telepon tempat
    template tentang teorema teoretis teori tepat terhadap terima termasuk tersebut tertentu
    tesis tetapi tiap tidak tiga tinggi tingkat tipe toh tugas tujuan uang ucapan uji ukuran
    umum unduhan unggahan untuk utama valid variabel varians vektor versi visi visual waktu
    walau walaupun warna wawancara yaitu yakin yang
        """,
    )
)

# Kata fungsi Inggris yang lazim muncul di sitasi/abstract dan bukan istilah
# yang perlu diputuskan.
ENGLISH_STOPWORDS = set(
    re.findall(
        r"\S+",
        """
    about across after again against all already also although always am among and any api are
    around as at be because been before being between both by can could did do does done during
    each either especially etc ever few for from furthermore generally had has have having he
    hence her here him his how however http https i in including instead into is it its just may
    me might more moreover most must my neither never nevertheless no nor not of often on only
    onto other otherwise our over own particularly per same shall she should since so some
    sometimes specifically still such that the their them there therefore these they this those
    though through thus to too under unless until url us usually very via was we were what when
    where whereas whether which while who whom whose why will with within without would www yet
    you your
        """,
    )
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
