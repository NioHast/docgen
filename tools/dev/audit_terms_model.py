"""Model data dan kategori untuk audit istilah asing.

Modul ini hanya berisi nilai kategori dan dataclass hasil audit. Parser,
aturan, dan laporan bergantung ke sini supaya arah dependensi tetap satu arah:
model <- parser/rules <- report <- CLI.
"""

from dataclasses import dataclass, field

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
