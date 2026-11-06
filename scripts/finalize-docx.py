#!/usr/bin/env python3
"""Finalisasi document.xml hasil pandoc agar penomoran halaman DOCX
mengikuti kaidah laporan akademik Indonesia:

  - Sampul                 : tanpa nomor halaman
  - Front matter           : i, ii, iii ... (lowerRoman, mulai 1), bawah tengah
  - Body (BAB I s.d. akhir): 1, 2, 3 ... (decimal, mulai 1), kanan atas

Pandoc/docx.lua hanya menyisipkan satu section break di akhir sampul.
Script ini:

  1. Menambahkan section break baru tepat sebelum Heading1 body pertama
     (BAB I) bila belum ada, sehingga dokumen memiliki tiga seksi.
  2. Menulis ulang setiap `w:sectPr` agar memiliki `w:pgNumType` yang
     sesuai zona.
  3. Membuat part header/footer baru yang tidak saling di-link antar
     seksi: footer front matter (PAGE, tengah), header body (PAGE, kanan),
     header kosong untuk front matter, serta footer body kosong secara
     visual. Footer body tetap memuat field PAGE tersembunyi sebagai probe
     agar `docx-pagenum.py` (yang membaca footer PDF) tetap dapat mengisi
     nomor halaman daftar isi.
  4. Membersihkan part header/footer lama yang tidak lagi dipakai.

Field PAGE ditulis sebagai field OpenXML asli (fldChar begin/separate/end),
bukan teks biasa, sehingga Word/LibreOffice tetap memperbaruinya.

Usage:
  python3 scripts/finalize-docx.py input.docx output.docx
"""

import re
import sys
import zipfile

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

SECT_RE = re.compile(r"<w:sectPr\b[^>]*>.*?</w:sectPr>", re.S)
PARA_RE = re.compile(r"<w:p\b[^>]*>(?:(?!</w:p>).)*?</w:p>", re.S)
PARA_OPEN_RE = re.compile(r"<w:p\b[^>]*>")
HEADER_FOOTER_REF_RE = re.compile(r"<w:(?:header|footer)Reference\b[^>]*/>")
PGNUM_RE = re.compile(r"<w:pgNumType\b[^>]*/>")
TITLEPG_RE = re.compile(r"<w:titlePg\b[^>]*/>")
SECT_TYPE_RE = re.compile(r"<w:type\b[^>]*/>")

# Heading1 yang termasuk front matter. Dipakai sebagai fallback bila tidak
# ada heading "BAB ..." (mis. dokumen tanpa bab bernomor).
FRONT_MATTER_HEADINGS = {
    "LEMBAR PENGESAHAN",
    "HALAMAN PENGESAHAN",
    "HALAMAN PERSETUJUAN",
    "HALAMAN PERSEMBAHAN",
    "PERSEMBAHAN",
    "MOTTO",
    "KATA PENGANTAR",
    "PRAKATA",
    "UCAPAN TERIMA KASIH",
    "ABSTRAK",
    "ABSTRACT",
    "DAFTAR ISI",
    "DAFTAR TABEL",
    "DAFTAR GAMBAR",
    "DAFTAR LAMPIRAN",
    "DAFTAR SINGKATAN",
    "DAFTAR SIMBOL",
}

BODY_CHAPTER_RE = re.compile(r"^BAB\s+(?:[IVXLCDM]+|\d+)\b", re.I)

# Urutan elemen CT_SectPr: pgNumType harus berada setelah pgMar dan sebelum
# elemen-elemen berikut.
PGNUM_BEFORE = (
    "cols",
    "formProt",
    "vAlign",
    "noEndnote",
    "titlePg",
    "textDirection",
    "bidi",
    "rtlGutter",
    "docGrid",
    "printerSettings",
)
SECT_TYPE_BEFORE = ("pgSz", "pgMar", "cols", "docGrid")


def para_text(paragraph):
    """Ambil seluruh teks dalam satu paragraf (bisa terdiri dari banyak run)."""
    return " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", paragraph)).strip()


def heading1_paragraphs(doc):
    """Kembalikan daftar (start, end, text) untuk setiap paragraf Heading1."""
    out = []
    for m in PARA_RE.finditer(doc):
        paragraph = m.group(0)
        if re.search(r'<w:pStyle w:val="Heading1"', paragraph):
            out.append((m.start(), m.end(), para_text(paragraph)))
    return out


def is_front_matter_heading(text):
    return text.strip().upper() in FRONT_MATTER_HEADINGS


def first_body_heading(doc):
    """Posisi paragraf Heading1 pertama milik body (BAB I), atau None."""
    headings = heading1_paragraphs(doc)
    for start, _end, text in headings:
        if BODY_CHAPTER_RE.match(text.strip()):
            return start
    # Fallback: heading pertama yang bukan nama front matter.
    for start, _end, text in headings:
        if text.strip() and not is_front_matter_heading(text):
            return start
    return None


def is_cover_section(text):
    return bool(re.search(r'w:pStyle w:val="Cover[^"]*"', text))


def find_sections(doc):
    """Petakan setiap sectPr ke rentang konten seksi yang diakhirinya.

    OOXML menempatkan `w:sectPr` di akhir seksi. Seksi pertama adalah konten
    sebelum sectPr pertama, seksi terakhir adalah konten sebelum sectPr
    body-level terakhir.
    """
    sections = []
    current_start = 0
    for m in SECT_RE.finditer(doc):
        # Cari awal paragraf yang memuat sectPr (section break di tengah dokumen).
        p_start = None
        for pm in PARA_OPEN_RE.finditer(doc, 0, m.start()):
            p_start = pm.start()
        p_end = None
        wrapped = False
        if p_start is not None:
            prefix = doc[p_start:m.start()]
            after = doc[m.end():m.end() + 80]
            wrapped = bool(re.search(r"<w:pPr(?:\s[^>]*)?>\s*$", prefix)) and after.lstrip().startswith("</w:pPr>")
            if wrapped:
                match = PARA_RE.match(doc, p_start)
                if match:
                    p_end = match.end()

        if wrapped and p_end is not None:
            # Paragraf pemuat sectPr adalah bagian dari seksi yang diakhirinya.
            content_end = p_end
            next_start = p_end
        else:
            content_end = m.start()
            next_start = m.end()

        sections.append(
            {
                "start": current_start,
                "end": content_end,
                "sect_start": m.start(),
                "sect_end": m.end(),
            }
        )
        current_start = next_start
    return sections


def section_index_at(sections, pos):
    for i, section in enumerate(sections):
        if section["start"] <= pos < section["end"]:
            return i
    return None


def section_starts_at(section, pos, doc):
    """True bila `pos` adalah konten pertama seksi (hanya bookmark/whitespace)."""
    prefix = doc[section["start"]:pos]
    prefix = re.sub(r"<w:bookmark(?:Start|End)\b[^>]*/>", "", prefix)
    return prefix.strip() == ""


def bookmark_aware_start(doc, para_start):
    """Geser titik sisip ke sebelum bookmarkStart yang menempel pada heading."""
    match = re.search(r"(?:<w:bookmarkStart\b[^>]*/>\s*)+$", doc[:para_start])
    return match.start() if match else para_start


def strip_section_props(sect):
    sect = HEADER_FOOTER_REF_RE.sub("", sect)
    sect = PGNUM_RE.sub("", sect)
    sect = TITLEPG_RE.sub("", sect)
    return sect


def set_section_type_next_page(sect):
    sect = SECT_TYPE_RE.sub("", sect)
    tag = '<w:type w:val="nextPage"/>'
    for name in SECT_TYPE_BEFORE:
        match = re.search(rf"<w:{name}\b", sect)
        if match:
            return sect[:match.start()] + tag + sect[match.start():]
    return sect.replace("</w:sectPr>", tag + "</w:sectPr>")


def set_pgnum(sect, fmt, start=None):
    sect = PGNUM_RE.sub("", sect)
    attrs = f' w:fmt="{fmt}"'
    if start is not None:
        attrs += f' w:start="{start}"'
    tag = f"<w:pgNumType{attrs}/>"
    for name in PGNUM_BEFORE:
        match = re.search(rf"<w:{name}\b", sect)
        if match:
            return sect[:match.start()] + tag + sect[match.start():]
    return sect.replace("</w:sectPr>", tag + "</w:sectPr>")


def set_references(sect, header_rid=None, footer_rid=None):
    sect = HEADER_FOOTER_REF_RE.sub("", sect)
    refs = ""
    if header_rid:
        refs += f'<w:headerReference w:type="default" r:id="{header_rid}"/>'
    if footer_rid:
        refs += f'<w:footerReference w:type="default" r:id="{footer_rid}"/>'
    return re.sub(
        r"(<w:sectPr\b[^>]*>)", lambda m: m.group(1) + refs, sect, count=1
    )


def make_page_part(kind, align, hidden=False):
    """Part header/footer berisi field PAGE asli."""
    root = "hdr" if kind == "header" else "ftr"
    rpr = ""
    if hidden:
        # Dipakai hanya oleh footer body. Nomor body yang terlihat berada di
        # header kanan atas. docx-pagenum.py membaca nomor body dari baris
        # terakhir PDF (footer), jadi footer tetap memuat field PAGE yang
        # disembunyikan di Word (vanish + putih). LibreOffice mengabaikan
        # formatting field PAGE, sehingga nilainya masih terekstrak pdftotext.
        rpr = '<w:rPr><w:vanish/><w:color w:val="FFFFFF"/></w:rPr>'
    run_open = f"<w:r>{rpr}"
    body = (
        f'<w:p><w:pPr><w:jc w:val="{align}"/>{rpr}</w:pPr>'
        + run_open
        + '<w:fldChar w:fldCharType="begin"/></w:r>'
        + run_open
        + '<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        + run_open
        + '<w:fldChar w:fldCharType="separate"/></w:r>'
        + run_open
        + "<w:t>1</w:t></w:r>"
        + run_open
        + '<w:fldChar w:fldCharType="end"/></w:r>'
        "</w:p>"
    )
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:{root} {W_NS}>{body}</w:{root}>'


def make_empty_part(kind):
    root = "hdr" if kind == "header" else "ftr"
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:{root} {W_NS}><w:p/></w:{root}>'


def add_relationship(rels_xml, kind, target):
    used = set(re.findall(r'Id="([^"]+)"', rels_xml))
    numeric = [int(n) for n in re.findall(r'Id="rId(\d+)"', rels_xml)]
    number = max(numeric + [0]) + 1
    while f"rId{number}" in used:
        number += 1
    rid = f"rId{number}"
    entry = (
        f'<Relationship Id="{rid}" Type="{REL_NS}/{kind}" Target="{target}"/>'
    )
    return rels_xml.replace("</Relationships>", entry + "</Relationships>"), rid


def add_content_type(ct_xml, part, kind):
    content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml."
        f"{kind}+xml"
    )
    if f'PartName="/{part}"' in ct_xml:
        return ct_xml
    override = f'<Override PartName="/{part}" ContentType="{content_type}"/>'
    return ct_xml.replace("</Types>", override + "</Types>")


def create_part(items, kind, xml, ct_xml, rels_xml):
    number = 1
    while f"word/{kind}{number}.xml" in items:
        number += 1
    part = f"word/{kind}{number}.xml"
    items[part] = xml.encode("utf-8")
    ct_xml = add_content_type(ct_xml, part, kind)
    rels_xml, rid = add_relationship(rels_xml, kind, part.rsplit("/", 1)[1])
    return rid, ct_xml, rels_xml


def drop_old_header_footer_parts(items, ct_xml, rels_xml):
    for name in list(items):
        if re.match(r"word/(?:header|footer)\d+\.xml$", name):
            del items[name]
    ct_xml = re.sub(
        r'<Override PartName="/word/(?:header|footer)\d+\.xml"[^>]*/>', "", ct_xml
    )
    rels_xml = re.sub(
        r'<Relationship\b[^>]*Type="[^"]*/(?:header|footer)"[^>]*/>', "", rels_xml
    )
    return ct_xml, rels_xml


def sync_section_margins(doc):
    first_mar = re.search(
        r"<w:sectPr[^>]*>.*?(<w:pgMar\b[^>]*/>).*?</w:sectPr>", doc, re.S
    )
    if not first_mar:
        return doc
    target_pgmar = first_mar.group(1)
    return re.sub(r"<w:pgMar\b[^>]*/>", target_pgmar, doc)


def process(doc, items):
    doc = sync_section_margins(doc)
    sections = find_sections(doc)
    if not sections:
        return doc, 0, {}

    ct_xml = items["[Content_Types].xml"].decode("utf-8")
    rels_xml = items["word/_rels/document.xml.rels"].decode("utf-8")
    ct_xml, rels_xml = drop_old_header_footer_parts(items, ct_xml, rels_xml)

    changed = 0
    body_pos = first_body_heading(doc)
    body_idx = section_index_at(sections, body_pos) if body_pos is not None else None
    cover_idx = (
        0
        if sections
        and is_cover_section(doc[sections[0]["start"]:sections[0]["end"]])
        else None
    )

    # Fallback: bila docx.lua tidak menyisipkan break setelah sampul, sampul
    # dan front matter/body masih berada dalam satu seksi. Pisahkan sebelum
    # Heading1 pertama (sampul tidak punya heading).
    if cover_idx is not None and body_idx == cover_idx:
        headings = heading1_paragraphs(doc)
        if headings:
            first_heading = headings[0][0]
            if not section_starts_at(sections[0], first_heading, doc):
                insert_at = bookmark_aware_start(doc, first_heading)
                template = SECT_RE.search(doc, sections[0]["sect_start"]).group(0)
                new_sect = set_section_type_next_page(strip_section_props(template))
                break_para = f"<w:p><w:pPr>{new_sect}</w:pPr></w:p>"
                doc = doc[:insert_at] + break_para + doc[insert_at:]
                sections = find_sections(doc)
                body_pos = first_body_heading(doc)
                body_idx = (
                    section_index_at(sections, body_pos)
                    if body_pos is not None
                    else None
                )
                changed += 1

    # Tambahkan section break baru sebelum BAB I jika heading body belum
    # menjadi awal seksi. Template pandoc hanya membuat break setelah sampul.
    if body_pos is not None and body_idx is not None:
        if not section_starts_at(sections[body_idx], body_pos, doc):
            insert_at = bookmark_aware_start(doc, body_pos)
            template = SECT_RE.search(doc, sections[0]["sect_start"]).group(0)
            new_sect = set_section_type_next_page(strip_section_props(template))
            break_para = f"<w:p><w:pPr>{new_sect}</w:pPr></w:p>"
            doc = doc[:insert_at] + break_para + doc[insert_at:]
            sections = find_sections(doc)
            body_pos = first_body_heading(doc)
            body_idx = section_index_at(sections, body_pos) if body_pos is not None else None
            changed += 1

    front_seen = 0
    body_seen = 0
    mods = []
    for index, section in enumerate(sections):
        sect = doc[section["sect_start"]:section["sect_end"]]
        sect = strip_section_props(sect)

        if cover_idx is not None and index == cover_idx:
            # Sampul: tidak ada header/footer sama sekali dan tidak ada nomor.
            sect = set_references(sect)
            new_sect = sect
        elif body_idx is not None and index >= body_idx:
            start = "1" if body_seen == 0 else None
            sect = set_pgnum(sect, "decimal", start)
            header_rid, ct_xml, rels_xml = create_part(
                items, "header", make_page_part("header", "right"),
                ct_xml, rels_xml
            )
            footer_rid, ct_xml, rels_xml = create_part(
                items, "footer", make_page_part("footer", "center", hidden=True),
                ct_xml, rels_xml
            )
            sect = set_references(sect, header_rid, footer_rid)
            new_sect = sect
            body_seen += 1
        else:
            start = "1" if front_seen == 0 else None
            sect = set_pgnum(sect, "lowerRoman", start)
            header_rid, ct_xml, rels_xml = create_part(
                items, "header", make_empty_part("header"), ct_xml, rels_xml
            )
            footer_rid, ct_xml, rels_xml = create_part(
                items, "footer", make_page_part("footer", "center"),
                ct_xml, rels_xml
            )
            sect = set_references(sect, header_rid, footer_rid)
            new_sect = sect
            front_seen += 1

        if new_sect != doc[section["sect_start"]:section["sect_end"]]:
            changed += 1
        mods.append((section["sect_start"], section["sect_end"], new_sect))

    for start, end, new_sect in reversed(mods):
        doc = doc[:start] + new_sect + doc[end:]

    items["[Content_Types].xml"] = ct_xml.encode("utf-8")
    items["word/_rels/document.xml.rels"] = rels_xml.encode("utf-8")
    stats = {
        "cover": 1 if cover_idx is not None else 0,
        "front": front_seen,
        "body": body_seen,
    }
    return doc, changed, stats


def get_tab_pos(doc):
    sz = re.search(r'<w:pgSz\b[^>]*w:w="(\d+)"', doc)
    mar_left = re.search(r'<w:pgMar\b[^>]*w:left="(\d+)"', doc)
    mar_right = re.search(r'<w:pgMar\b[^>]*w:right="(\d+)"', doc)
    if sz and mar_left and mar_right:
        try:
            w = int(sz.group(1))
            left = int(mar_left.group(1))
            right = int(mar_right.group(1))
            pos = w - left - right
            if pos > 1000:
                return pos
        except (ValueError, TypeError):
            pass
    return 9072


def fix_daftar_isi_title(doc):
    pattern = re.compile(
        r'(<w:p\b[^>]*><w:pPr>(?:(?!</w:p>).)*?<w:pStyle\s+w:val=["\x27])Heading1(["\x27](?:(?!</w:p>).)*?<w:t[^>]*>\s*DAFTAR ISI\s*</w:t>(?:(?!</w:p>).)*?</w:p>)',
        re.S,
    )
    return pattern.sub(r"\g<1>TOCHeading\g<2>", doc)


def fix_toc_styles(styles, tab_pos):
    tnr = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>'
    defs = {
        "TOCHeading": f"""<w:style w:type="paragraph" w:styleId="TOCHeading">
  <w:name w:val="TOC Heading"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="Normal"/>
  <w:uiPriority w:val="39"/>
  <w:qFormat/>
  <w:pPr>
    <w:spacing w:before="360" w:after="360" w:line="240" w:lineRule="auto"/>
    <w:jc w:val="center"/>
    <w:outlineLvl w:val="9"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="28"/>
    <w:szCs w:val="28"/>
    <w:b/>
    <w:bCs/>
  </w:rPr>
</w:style>""",
        "TOC1": f"""<w:style w:type="paragraph" w:styleId="TOC1">
  <w:name w:val="toc 1"/>
  <w:basedOn w:val="Normal"/>
  <w:next w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="right" w:leader="dot" w:pos="{tab_pos}"/>
    </w:tabs>
    <w:spacing w:before="120" w:after="40" w:line="260" w:lineRule="auto"/>
    <w:ind w:left="0" w:right="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b/>
    <w:bCs/>
  </w:rPr>
</w:style>""",
        "TOC2": f"""<w:style w:type="paragraph" w:styleId="TOC2">
  <w:name w:val="toc 2"/>
  <w:basedOn w:val="TOC1"/>
  <w:next w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="right" w:leader="dot" w:pos="{tab_pos}"/>
    </w:tabs>
    <w:spacing w:before="20" w:after="20" w:line="240" w:lineRule="auto"/>
    <w:ind w:left="360" w:right="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b w:val="0"/>
    <w:bCs w:val="0"/>
  </w:rPr>
</w:style>""",
        "TOC3": f"""<w:style w:type="paragraph" w:styleId="TOC3">
  <w:name w:val="toc 3"/>
  <w:basedOn w:val="TOC2"/>
  <w:next w:val="Normal"/>
  <w:qFormat/>
  <w:pPr>
    <w:tabs>
      <w:tab w:val="right" w:leader="dot" w:pos="{tab_pos}"/>
    </w:tabs>
    <w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>
    <w:ind w:left="720" w:right="0"/>
    <w:jc w:val="left"/>
  </w:pPr>
  <w:rPr>
    {tnr}
    <w:color w:val="000000"/>
    <w:sz w:val="24"/>
    <w:szCs w:val="24"/>
    <w:b w:val="0"/>
    <w:bCs w:val="0"/>
  </w:rPr>
</w:style>""",
    }
    missing = []
    for sid, block in defs.items():
        pattern = re.compile(rf'<w:style\b[^>]*w:styleId="{sid}"[^>]*>.*?</w:style>', re.S)
        if pattern.search(styles):
            styles = pattern.sub(block, styles)
        else:
            missing.append(block)
    if missing:
        styles = styles.replace("</w:styles>", "".join(missing) + "</w:styles>")
    return styles


def main():
    src = sys.argv[1]
    dst = sys.argv[2]

    with zipfile.ZipFile(src, "r") as zin:
        names = zin.namelist()
        items = {n: zin.read(n) for n in names}

    doc = items["word/document.xml"].decode("utf-8")
    tab_pos = get_tab_pos(doc)
    doc = fix_daftar_isi_title(doc)
    # Sesuaikan tab leader pada cached TOC entries agar tepat di margin kanan
    doc = re.sub(
        r'(<w:pStyle w:val="TOC[123]"/>.*?<w:tab w:val="right" w:leader="dot" w:pos=)"\d+"',
        rf'\g<1>"{tab_pos}"',
        doc,
    )
    new_doc, changed, stats = process(doc, items)
    items["word/document.xml"] = new_doc.encode("utf-8")

    if "word/styles.xml" in items:
        styles = items["word/styles.xml"].decode("utf-8")
        items["word/styles.xml"] = fix_toc_styles(styles, tab_pos).encode("utf-8")

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in items:
            zout.writestr(n, items[n])

    zones = ", ".join(f"{k}={v}" for k, v in stats.items())
    print(
        f"[OK] finalize-docx: {changed} sectPr disesuaikan "
        f"({zones}; tab={tab_pos}) -> {dst}"
    )


if __name__ == "__main__":
    main()
