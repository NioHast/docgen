"""Render laporan Markdown audit istilah asing.

Modul ini hanya mengubah ``AuditResult`` menjadi teks laporan deterministik;
tidak membaca DOCX dan tidak menjalankan CLI.
"""

from pathlib import Path

from tools.dev.audit_terms_model import (
    CATEGORY_ABBREVIATION,
    CATEGORY_LABEL,
    CATEGORY_ORDER,
    AuditResult,
    Group,
)


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
