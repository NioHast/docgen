# Fixture chart

`charts.yaml` memuat satu slide per kind chart agar test chart layer tidak
mencampur tiga problem:

- `s01.chart1`: bar vertikal empat seri, dipakai untuk batas empat warna
  `chartSeries`.
- `s02.chart1`: bar horizontal satu seri.
- `s03.chart1`: line dua seri dengan `unit`.
- `s04.chart1`: donut satu seri dengan empat kategori berwarna.

Nilai dan label sengaja kecil dan deterministik. Fixture ini tidak menyentuh
network, Google, COM, atau file output.
