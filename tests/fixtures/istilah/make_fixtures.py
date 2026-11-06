"""Buat ulang fixture contoh.docx dengan python-docx.

Jalankan dari akar proyek:

    .venv\\Scripts\\python.exe tests\\fixtures\\istilah\\make_fixtures.py
"""

from pathlib import Path

from docx import Document

BASE = Path(__file__).resolve().parent


def main() -> None:
    glossary = BASE / "istilah.tsv"
    glossary.write_text(
        "\n".join(
            [
                "# contoh glosarium untuk fixture",
                "term\titalic\tgloss_first\tstatus",
                "training data\tyes\tno\tconfirmed",
                "big data\tyes\tno\tconfirmed",
                "data\tno\tno\tconfirmed",
                "Python\tno\tno\tconfirmed",
                "Microsoft Word\tno\tno\tconfirmed",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    doc = Document()
    doc.add_paragraph(
        "Laporan ini memakai training data dan big data; "
        "data pelatihan tetap tegak."
    )
    doc.add_paragraph(
        "Python dan Microsoft Word bukan istilah asing; "
        "datang dan metadata juga aman."
    )
    doc.add_paragraph("Bagian {{?validation dataset?}} belum diputuskan.")

    split = doc.add_paragraph()
    split.add_run("Istilah terpotong: ")
    split.add_run("trai")
    bold = split.add_run("ning")
    bold.bold = True
    split.add_run(" data diuji.")

    doc.save(BASE / "contoh.docx")
    print(f"Fixture ditulis ke {BASE}")


if __name__ == "__main__":
    main()
