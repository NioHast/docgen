# Panduan Menulis Naskah Skripsi untuk LLM/Agent

Berlaku untuk seluruh naskah skripsi berbahasa Indonesia di proyek ini. Periksa setiap aturan
sebelum menyerahkan draf. Aturan mengikat; contoh hanya ilustrasi.

## 1. Nada

1. Tulis kalimat berita. Jangan menyapa pembaca, mengajak ("mari kita"), atau memberi tahu
   pembaca apa yang harus diingat ("perlu diingat", "penting untuk dipahami").
2. Mulai setiap bagian dengan kalimat yang memuat minimal satu unsur konkret: angka, nama
   tempat, nama lembaga, atau peristiwa bertanggal. Hapus kalimat pembuka yang tidak memuat
   satu pun unsur itu.
3. Samakan kekuatan klaim dengan bukti. Tulis "berhubungan" untuk korelasi, "berpengaruh" hanya
   bila ada uji yang mendukung, dan "meningkat" tanpa "sangat", "pesat", atau "signifikan"
   kecuali ada dasar statistik.
4. Jangan menilai karya sendiri ("inovatif", "efektif", "menarik"). Ganti penilaian dengan
   ukuran yang bisa diperiksa.
5. Hapus kata penekan yang tidak mengubah makna: "sangat", "benar-benar", "tentu saja", "pada
   dasarnya", "secara umum". Uji dengan membaca kalimat tanpa kata itu; bila maknanya tetap,
   kata itu dibuang.

## 2. Struktur kalimat

1. Pastikan setiap kalimat punya subjek berupa nomina atau frasa nomina, bukan frasa
   preposisional. Uji: buang kata depan di awal; bila kalimat menjadi bersubjek, kata depan
   itulah penyebabnya.
   - Salah: "Dari hasil analisis menunjukkan bahwa kepuasan pasien rendah."
   - Benar: "Hasil analisis menunjukkan bahwa kepuasan pasien rendah."
2. Jangan memulai kalimat dengan "Dari", "Dalam", "Pada", "Bagi", "Berdasarkan", atau "Menurut"
   lalu langsung memasang verba. Jadikan frasa itu subjek, atau pertahankan kata depan dan
   pakai bentuk pasif ("Dalam penelitian ini dibahas ...").
3. Jangan menulis kalimat lebih dari 35 kata. Hitung kata, bukan klausa. Bila lebih, pecah di
   koma atau di klausa "yang" pertama.
4. Pakai satu predikat utama per kalimat. Jangan menumpuk lebih dari dua klausa "yang" dalam
   satu frasa.
5. Pakai "di mana" hanya sebagai kata tanya. Sebagai perangkai, ganti dengan "tempat", "yang",
   "saat", atau pecah kalimatnya.
   - Salah: "Desa Sukamaju di mana mayoritas penduduknya petani."
   - Benar: "Desa Sukamaju, yang sebagian besar penduduknya petani."
6. Ganti "hal ini" atau "hal tersebut" dengan nomina yang ditunjuk. Bila nomina itu tidak bisa
   disebut, kalimatnya tidak memuat klaim yang jelas.
7. Pasif "di-" boleh di bab Metode ("Sampel diambil ..."). Jangan memaksakan aktif, dan jangan
   menumpuk pasif ("telah dilakukan pengambilan sampel" menjadi "sampel diambil").

## 3. Klaim dan sitasi

1. Beri sitasi pada setiap klaim faktual: angka, proporsi, hubungan antarvariabel, temuan
   penelitian lain, definisi yang diperdebatkan, dan isi kebijakan. Sitasi berada di kalimat
   yang memuat klaim, bukan di akhir paragraf.
2. Jangan menulis angka tanpa sumber. Untuk data sendiri, sumbernya tabel, gambar, atau
   lampiran ("Tabel 4.3"); untuk data orang lain, sumbernya publikasi.
3. Jangan mengarang rujukan, penulis, tahun, jurnal, volume, halaman, atau DOI. Bila belum
   terverifikasi, tulis `TODO-SITASI: <klaim yang perlu didukung>` lalu lanjutkan kalimat lain.
   Jangan menutupi penanda itu dengan sitasi yang tampak meyakinkan.
4. Saat menyunting, jangan memindahkan, menghapus, atau mengganti sitasi. Sitasi menempel pada
   klaim aslinya.
5. Verifikasi sebelum mengutip: buka abstrak atau isi sumber dan pastikan klaimnya ada di sana,
   bukan hanya topiknya mirip. Rujukan yang tidak ditemukan di mana pun dianggap tidak ada.
6. Ikuti gaya sitasi yang ditetapkan proyek atau kampus; bila belum ada, pakai APA 7. Pakai
   "dkk." dan "hlm." dalam naskah berbahasa Indonesia.
7. Satu klaim cukup satu sitasi utama. Sitasi berderet untuk satu klaim hanya boleh bila
   beberapa sumber memang diuji dan dibandingkan.

## 4. Paragraf

1. Tulis satu gagasan per paragraf. Kalimat pertama menyatakan gagasan itu, bukan latar
   belakang umum.
2. Panjang wajar: 3-7 kalimat atau 80-150 kata. Paragraf di atas 200 kata dipecah; paragraf di
   bawah tiga kalimat digabung dengan paragraf yang sejenis.
3. Jangan membuat rangkaian paragraf satu kalimat. Satu paragraf satu kalimat hanya boleh
   sekali sebagai penekanan atau peralihan.
4. Akhiri paragraf dengan implikasi atau lanjutan, bukan dengan pengulangan isi. Hapus
   "Dengan demikian dapat disimpulkan bahwa ..." di akhir paragraf.
5. Hubungkan paragraf lewat isi. Jangan mengandalkan "Selain itu", "Oleh karena itu", atau
   "Lebih lanjut" di awal setiap paragraf; bila logikanya sudah jelas, penghubung dibuang.
6. Sampaikan argumen dalam paragraf. Daftar berbutir hanya untuk prosedur, kriteria, atau
   rumusan, bukan untuk pembahasan.

## 5. Istilah asing

1. Tulis istilah asing yang belum diserap dengan miring: `*machine learning*`,
   `*grounded theory*`, `*in vitro*`. Berlaku setiap kali istilah itu muncul.
2. Tulis istilah yang sudah diserap KBBI dengan tegak: mikrokontroler, sensor, prevalensi,
   daring, unduh.
3. Jangan menebak status serapan atau padanan. Bila ragu, tulis `{{?istilah?}}` tepat pada
   bentuk yang diragukan. *Build* menolak penanda ini sampai ada keputusan; jangan menghapusnya
   dengan menebak.
4. Jangan menerjemahkan nama diri, nama algoritma, nama produk, standar, lambang satuan, dan
   nama takson. Contoh: *Random Forest*, ISO 9001, 10 V, *Oryza sativa*.
5. Tetapkan satu bentuk untuk satu konsep dan pakai di seluruh naskah. "Basis data" di Bab 2
   dan *database* di Bab 4 adalah kesalahan.
6. Pada kemunculan pertama, tulis kepanjangan lalu singkatan: *Internet of Things* (IoT).
   Kepanjangan asing dicetak miring; singkatannya tegak.
7. Untuk kata asing berimbuhan, pakai tanda hubung (di-*input*) atau, lebih baik, padanannya
   (dimasukkan).

## 6. Daftar larangan

Daftar lengkap ada di `writing/larangan.txt`; jalankan pemeriksa proyek sebelum menyerahkan
draf. Delapan pola yang paling sering muncul:

1. **Pembuka kosmik.** "Di era digital ini, ...", "Seiring perkembangan zaman, ...", "Tidak
   dapat dipungkiri bahwa ...". Hapus dan mulai dari fakta.
   Salah: "Di era digital ini, teknologi informasi berkembang pesat." Benar: hapus kalimat itu;
   tulis masalah konkret, atau `TODO-SITASI` bila datanya belum ada.
2. **Subjek hilang karena kata depan.** "Dari hasil analisis menunjukkan ..." → "Hasil analisis
   menunjukkan ...". Pola serupa: "Dalam penelitian ini membahas ...", "Berdasarkan hasil
   penelitian menyimpulkan ...".
3. **"di mana" sebagai perangkai.** "... desa di mana penduduknya petani" → "... desa yang
   penduduknya petani". "Di mana" hanya untuk pertanyaan.
4. **"hal ini" tanpa anteseden.** "Kadar hemoglobin rendah. Hal ini menunjukkan ..." → "Kadar
   hemoglobin yang rendah ini menunjukkan ...". Sebut nomina yang ditunjuk.
5. **"dapat disimpulkan bahwa".** Jangan pakai sebagai perangkai paragraf. "Dengan demikian
   dapat disimpulkan bahwa program berhasil" → "Program berhasil"; di bab Simpulan tulis
   "Simpulannya, program berhasil".
6. **Kontras retoris "bukan X melainkan Y" dan "tidak hanya ... tetapi juga".** Jangan pakai
   untuk membungkus klaim biasa; pakai hanya bila kalimat membetulkan salah paham yang nyata.
   Uji: tulis ulang sebagai klaim langsung; bila tidak ada informasi yang hilang, pola itu
   hiasan.
   - Salah: "Bukan hanya cepat, tetapi juga akurat." Benar: "Proses ini cepat dan akurat."
   - Salah: "Ini bukan solusi murah, melainkan solusi cepat." Benar: "Ini solusi cepat."
7. **Kalke verba Inggris.** "memainkan peran" → "berperan"; "mengambil tempat" → "berlangsung";
   "memberikan kontribusi" → "menyumbang".
8. **Nominalisasi berlapis.** "melakukan pengukuran terhadap" → "mengukur"; "mengalami
   peningkatan" → "meningkat"; "telah dilakukan pengujian" → "diuji".

## 7. Contoh sebelum/sesudah

Fakta pada versi "sesudah" harus sama persis dengan "sebelum": angka, sitasi, nama, dan arah
hubungan tidak berubah. Sitasi pada contoh ini rekaan dan hanya menunjukkan format.

**1. Pembuka kosmik**
- Sebelum: "Di era digital ini, tidak dapat dipungkiri bahwa Puskesmas di Kabupaten X masih
  mencatat kunjungan ibu hamil di buku register."
- Sesudah: "Puskesmas di Kabupaten X masih mencatat kunjungan ibu hamil di buku register."

**2. Subjek hilang, sitasi tetap**
- Sebelum: "Dari hasil analisis menunjukkan bahwa kepuasan pasien rendah, di mana hanya 42%
  responden menyatakan puas (Santoso, 2021)."
- Sesudah: "Hasil analisis menunjukkan bahwa kepuasan pasien rendah: hanya 42% responden
  menyatakan puas (Santoso, 2021)."

**3. "di mana" dan "hal ini"**
- Sebelum: "Penelitian dilakukan di Desa Sukamaju. Di mana kelompok tani berperan penting
  dalam distribusi pupuk. Hal ini terlihat dari 27 dari 40 petani yang membeli pupuk melalui
  kelompok."
- Sesudah: "Penelitian dilakukan di Desa Sukamaju, tempat kelompok tani berperan penting dalam
  distribusi pupuk. Sebanyak 27 dari 40 petani membeli pupuk melalui kelompok."

**4. Kontras retoris dan klaim digelembungkan**
- Sebelum: "Program ini bukan hanya meningkatkan cakupan imunisasi (Tabel 4.3), tetapi juga
  merupakan solusi inovatif; dapat disimpulkan bahwa program ini sangat signifikan."
- Sesudah: "Program ini meningkatkan cakupan imunisasi (Tabel 4.3)."

**5. Nominalisasi dan paragraf satu kalimat**
- Sebelum: "Dilakukan pengukuran terhadap tekanan darah. Pengukuran ini dilakukan dua kali.
  Pengukuran dilakukan oleh dua petugas. Hasilnya menunjukkan penurunan."
- Sesudah: "Tekanan darah diukur dua kali oleh dua petugas. Hasil pengukuran menunjukkan
  penurunan."

**Atribusi:** Diparafrasekan dari proyek naskah-id (github.com/nothinx/naskah-id), lisensi MIT; kaidah EYD V, KBBI, dan Tata Bahasa Baku Bahasa Indonesia.
