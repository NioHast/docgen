"""Copy checker deterministik untuk DeckIR, TranscriptIR, dan ``copy.yaml``.

Checker hanya membaca IR dan konfigurasi. Ia tidak mengimpor renderer, Google,
DOCX, PDF, atau CLI. Keluaran berupa tuple ``Diagnostic`` yang stabil dan siap
dipakai build gate.

Teks diperiksa sebagai teks tampil: label link dipertahankan, sedangkan tujuan
link, URL, penanda daftar, emphasis, dan backtick kode dilucuti. ``source.text``
diperlakukan sebagai prosa biasa, tetapi bukan title atau teks display.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from autooffice.deck.model.deck_ir import BlockIR, DeckIR, KeyBinding, SlideIR
from autooffice.deck.transcript.model import TranscriptIR
from autooffice.deck.transcript.parser import TranscriptError

from .config import (
    DEFAULT_MAX_WORDS,
    CopyConfig,
    CopyConfigError,
    Language,
    RuleConfig,
    load_copy_config,
    normalize_language,
    validate_allowlist,
)
from .diagnostics import Diagnostic, RuleViolation, Severity
from .prose import render_visible_text
from .rules.banned_phrases import check_banned_phrases
from .rules.dash import check_dash
from .rules.patterns import (
    check_contrast_pattern,
    check_forced_triad,
    check_negative_parallelism,
    check_paired_clause_label,
    is_one_line_closer,
    parse_closer_key,
)
from .rules.sentence_length import check_sentence_length
from .rules.title_case import check_title_case

_TEXT_KINDS = frozenset({"text", "media_text"})


@dataclass(frozen=True, slots=True)
class _ProseEntry:
    """Satu nilai teks yang akan diperiksa beserta lokasinya."""

    key: str
    text: str
    language: Language
    file: str | None
    line: int | None
    is_title: bool = False
    is_display: bool = False
    is_block: bool = False
    allow_alias: str | None = None
    raw_text: str | None = None
    offset_map: tuple[int, ...] = ()

    def original_offset(self, offset: int) -> int:
        """Petakan offset teks tampil kembali ke teks asal."""
        if 0 <= offset < len(self.offset_map):
            return self.offset_map[offset]
        if offset == len(self.offset_map) and self.offset_map:
            return self.offset_map[-1] + 1
        return offset


def check_copy(
    deck: DeckIR,
    transcript: TranscriptIR | None = None,
    copy_path: str | Path | None = None,
    *,
    config: CopyConfig | None = None,
    deck_file: str | Path | None = None,
    transcript_file: str | Path | None = None,
) -> tuple[Diagnostic, ...]:
    """Jalankan seluruh rule copy pada deck dan transkrip opsional.

    Teks diperiksa dalam bentuk tampil (Markdown umum dilucuti). Bila transkrip
    tidak tersedia, allow entry ber-key transkrip tetap valid tetapi inert,
    bukan error stale.
    """
    if copy_path is not None and config is not None:
        raise CopyConfigError("copy_path dan config tidak boleh diberikan bersamaan.")
    resolved = (
        config
        if config is not None
        else load_copy_config(copy_path, deck_dir=_deck_directory(deck_file))
    )
    transcript_label = _label(transcript_file)
    if transcript is not None and transcript_label is None:
        transcript_label = transcript.source
    if transcript is not None and resolved.targets.transcript:
        _validate_transcript_mapping(deck, transcript)

    known_keys = _known_keys(
        deck,
        transcript if resolved.targets.transcript else None,
    )
    validate_allowlist(resolved, known_keys)

    entries = _render_entries(_deck_entries(deck, resolved, deck_file=_label(deck_file)))
    diagnostics = _check_entries(entries, resolved)
    diagnostics.extend(_one_line_closer_diagnostics(entries, resolved))
    if transcript is not None and resolved.targets.transcript:
        transcript_entries = _render_entries(
            _transcript_entries(
                deck,
                transcript,
                resolved,
                file=transcript_label,
            )
        )
        diagnostics.extend(_check_entries(transcript_entries, resolved))
    return tuple(diagnostics)


def has_errors(diagnostics: Iterable[Diagnostic]) -> bool:
    """True bila minimal satu diagnostic berperingkat error."""
    return any(diagnostic.severity == "error" for diagnostic in diagnostics)


def _deck_entries(
    deck: DeckIR,
    config: CopyConfig,
    *,
    deck_file: str | None,
) -> list[_ProseEntry]:
    language = normalize_language(deck.meta.get("language", "id"))
    entries: list[_ProseEntry] = []
    bindings = _bindings_by_slide(deck)
    blocks = _blocks_by_slide(deck)
    for slide in deck.slides:
        title_block = _title_block(slide)
        if config.targets.slides:
            if title_block is not None:
                title_text = _field_text(title_block, "text")
                if title_text is not None:
                    entries.append(
                        _ProseEntry(
                            key=f"{slide.slide_id}.title",
                            text=title_text,
                            language=language,
                            file=deck_file,
                            line=None,
                            is_title=True,
                            is_display=True,
                            allow_alias=f"{slide.slide_id}.{title_block.block_id}.text",
                        )
                    )
            slide_blocks = blocks.get(slide.slide_id, {})
            for binding in bindings.get(slide.slide_id, ()):
                if binding.kind == "source":
                    if binding.plain_text.strip():
                        entries.append(
                            _ProseEntry(
                                key=binding.key,
                                text=binding.plain_text,
                                language=language,
                                file=deck_file,
                                line=None,
                            )
                        )
                    continue
                entry = _block_entry(
                    binding,
                    slide_blocks,
                    title_block=title_block,
                    language=language,
                    file=deck_file,
                )
                if entry is not None:
                    entries.append(entry)
        if config.targets.notes and slide.notes is not None:
            entries.append(
                _ProseEntry(
                    key=f"{slide.slide_id}.notes",
                    text=slide.notes,
                    language=language,
                    file=deck_file,
                    line=None,
                )
            )
    return entries


def _block_entry(
    binding: KeyBinding,
    blocks: Mapping[str, BlockIR],
    *,
    title_block: BlockIR | None,
    language: Language,
    file: str | None,
) -> _ProseEntry | None:
    if binding.block_id is None or binding.kind not in _TEXT_KINDS:
        return None
    block = blocks.get(binding.block_id)
    if block is None or block.block_type == "code":
        return None
    if title_block is not None and block is title_block and binding.leaf == "text":
        return None
    if not binding.plain_text.strip():
        return None
    return _ProseEntry(
        key=binding.key,
        text=binding.plain_text,
        language=language,
        file=file,
        line=None,
        is_display=True,
        is_block=True,
    )


def _transcript_entries(
    deck: DeckIR,
    transcript: TranscriptIR,
    config: CopyConfig,
    *,
    file: str | None,
) -> list[_ProseEntry]:
    if not config.targets.transcript:
        return []
    sections = transcript.by_slide_id
    entries: list[_ProseEntry] = []
    for slide in deck.slides:
        section = sections.get(slide.slide_id)
        if section is None:
            continue
        entries.append(
            _ProseEntry(
                key=section.id_key,
                text=section.indonesian.text,
                language="id",
                file=file,
                line=section.indonesian.line,
            )
        )
        if section.english is not None:
            entries.append(
                _ProseEntry(
                    key=section.en_key,
                    text=section.english.text,
                    language="en",
                    file=file,
                    line=section.english.line,
                )
            )
    return entries


def _render_entries(entries: Iterable[_ProseEntry]) -> list[_ProseEntry]:
    rendered: list[_ProseEntry] = []
    for entry in entries:
        visible = render_visible_text(entry.text)
        if visible.text == entry.text:
            rendered.append(entry)
            continue
        rendered.append(
            replace(
                entry,
                text=visible.text,
                raw_text=entry.text,
                offset_map=visible.offsets,
            )
        )
    return rendered


def _check_entries(entries: Iterable[_ProseEntry], config: CopyConfig) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    seen: set[tuple[str, str, int]] = set()
    for entry in entries:
        for name, rule, violation in _violations_for_entry(entry, config):
            identity = (name, entry.key, violation.offset)
            if identity in seen:
                continue
            seen.add(identity)
            if _allowed(config, entry, name):
                continue
            severity = rule.diagnostic_severity
            if severity is None:
                continue
            diagnostics.append(_diagnostic(entry, name, severity, violation))
    return diagnostics


def _allowed(config: CopyConfig, entry: _ProseEntry, rule: str) -> bool:
    if config.allowed(entry.key, rule):
        return True
    return entry.allow_alias is not None and config.allowed(entry.allow_alias, rule)


def _violations_for_entry(
    entry: _ProseEntry,
    config: CopyConfig,
) -> Iterable[tuple[str, RuleConfig, RuleViolation]]:
    banned = config.active_rule("banned_phrases")
    if banned is not None:
        for violation in check_banned_phrases(
            entry.text,
            language=entry.language,
            extra=banned.extra,
        ):
            yield "banned_phrases", banned, violation

    if entry.is_title:
        title_case = config.active_rule("title_case")
        if title_case is not None:
            for violation in check_title_case(entry.text, language=entry.language):
                yield "title_case", title_case, violation

    dash = config.active_rule("dash")
    if dash is not None:
        for violation in check_dash(entry.text):
            yield "dash", dash, violation

    negative = config.active_rule("negative_parallelism")
    if negative is not None:
        for violation in check_negative_parallelism(entry.text, language=entry.language):
            yield "negative_parallelism", negative, violation

    if entry.language == "id":
        contrast = config.active_rule("contrast_pattern")
        if contrast is not None:
            for violation in check_contrast_pattern(entry.text):
                yield "contrast_pattern", contrast, violation

    sentence = config.active_rule("sentence_length")
    if sentence is not None:
        max_words = sentence.max_words or DEFAULT_MAX_WORDS
        for violation in check_sentence_length(entry.text, max_words=max_words):
            yield "sentence_length", sentence, violation

    if entry.language == "id":
        triad = config.active_rule("forced_triad")
        if triad is not None:
            for violation in check_forced_triad(entry.text):
                yield "forced_triad", triad, violation

    if entry.language == "id" and entry.is_display:
        paired = config.active_rule("paired_clause_label")
        if paired is not None:
            for violation in check_paired_clause_label(entry.text):
                yield "paired_clause_label", paired, violation


def _one_line_closer_diagnostics(
    entries: Iterable[_ProseEntry],
    config: CopyConfig,
) -> list[Diagnostic]:
    rule = config.active_rule("one_line_closer")
    if rule is None:
        return []
    severity = rule.diagnostic_severity
    if severity is None:
        return []
    groups: dict[tuple[str, str], dict[int, _ProseEntry]] = {}
    for entry in entries:
        if not entry.is_block or entry.language != "id":
            continue
        group = parse_closer_key(entry.key)
        if group is None:
            continue
        # Binding duplikat untuk item yang sama tidak boleh menambah ukuran grup;
        # nomor item adalah identitas logis dalam satu prefix/leaf.
        groups.setdefault((group.prefix, group.leaf), {}).setdefault(group.number, entry)
    diagnostics: list[Diagnostic] = []
    for items in groups.values():
        if len(items) < 3:
            continue
        entry = items[max(items)]
        if not is_one_line_closer(entry.text):
            continue
        if config.allowed(entry.key, "one_line_closer"):
            continue
        diagnostics.append(
            Diagnostic(
                rule="one_line_closer",
                severity=severity,
                key=entry.key,
                message=(
                    f"Item terakhir pada grup '{entry.key}' hanya memuat "
                    f"{len(entry.text.split())} kata."
                ),
                hint="Hapus closer yang hanya menjadi punchline; akhiri dengan isi konkret.",
                file=entry.file,
                line=entry.line,
            )
        )
    return diagnostics


def _diagnostic(
    entry: _ProseEntry,
    rule: str,
    severity: Severity,
    violation: RuleViolation,
) -> Diagnostic:
    line = entry.line
    if line is not None and violation.offset > 0:
        raw_text = entry.raw_text if entry.raw_text is not None else entry.text
        line += raw_text.count("\n", 0, entry.original_offset(violation.offset))
    return Diagnostic(
        rule=rule,
        severity=severity,
        key=entry.key,
        message=violation.message,
        hint=violation.hint,
        file=entry.file,
        line=line,
    )


def _validate_transcript_mapping(deck: DeckIR, transcript: TranscriptIR) -> None:
    source = transcript.source
    deck_ids = [slide.slide_id for slide in deck.slides]
    deck_set = set(deck_ids)
    seen: set[str] = set()
    for section in transcript.sections:
        if section.slide_id in seen:
            raise TranscriptError(
                f"Slide ID '{section.slide_id}' duplikat pada transkrip.",
                source=source,
                line=section.heading_line,
                slide_id=section.slide_id,
            )
        if section.slide_id not in deck_set:
            raise TranscriptError(
                f"Slide ID '{section.slide_id}' tidak dikenal pada deck.",
                source=source,
                line=section.heading_line,
                slide_id=section.slide_id,
            )
        seen.add(section.slide_id)
    missing = [slide_id for slide_id in deck_ids if slide_id not in seen]
    if missing:
        raise TranscriptError(
            f"Transkrip tidak memuat bagian untuk slide: {', '.join(missing)}.",
            source=source,
        )


def _known_keys(deck: DeckIR, transcript: TranscriptIR | None) -> set[str]:
    keys = set(deck.keys.keys())
    for slide in deck.slides:
        if slide.notes is not None:
            keys.add(f"{slide.slide_id}.notes")
        if _title_block(slide) is not None:
            keys.add(f"{slide.slide_id}.title")
            title_block = _title_block(slide)
            if title_block is not None:
                keys.add(f"{slide.slide_id}.{title_block.block_id}.text")
        if transcript is None:
            # Transkrip opsional: allow entry ber-key transkrip tetap valid
            # tetapi inert sampai transkrip tersedia.
            keys.add(f"{slide.slide_id}.transcript.id")
            keys.add(f"{slide.slide_id}.transcript.en")
    if transcript is not None:
        keys.update(transcript.keys())
    return keys


def _deck_directory(deck_file: str | Path | None) -> Path | None:
    if deck_file is None:
        return None
    source = Path(deck_file)
    try:
        resolved = source.resolve()
    except OSError, RuntimeError:
        return source.parent
    return resolved if resolved.is_dir() else resolved.parent


def _title_block(slide: SlideIR) -> BlockIR | None:
    title_fallback: BlockIR | None = None
    display_fallback: BlockIR | None = None
    for block in slide.blocks:
        if block.block_type != "text":
            continue
        if block.role == "title":
            return block
        if block.role == "display" and display_fallback is None:
            display_fallback = block
        if title_fallback is None and block.block_id == "title":
            title_fallback = block
    return title_fallback or display_fallback


def _bindings_by_slide(deck: DeckIR) -> dict[str, tuple[KeyBinding, ...]]:
    result: dict[str, list[KeyBinding]] = {}
    for binding in deck.keys.bindings:
        result.setdefault(binding.slide_id, []).append(binding)
    return {slide_id: tuple(bindings) for slide_id, bindings in result.items()}


def _blocks_by_slide(deck: DeckIR) -> dict[str, dict[str, BlockIR]]:
    return {
        slide.slide_id: {block.block_id: block for block in slide.blocks} for slide in deck.slides
    }


def _field_text(block: BlockIR, name: str) -> str | None:
    value = block.fields.get(name)
    return value if isinstance(value, str) else None


def _label(value: str | Path | None) -> str | None:
    return str(value) if value is not None else None
