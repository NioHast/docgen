"""Parser ``structure.yml`` dan aturan struktur dokumen.

Modul ini memuat :func:`load_structure` serta parser front matter, body, back
matter, numbering, lists, dan cover. Aturan source front/back matter, ID bab,
dan konsistensi daftar adalah tanggung jawab khusus struktur dan tidak dipakai
parser format.

Semua kegagalan input dilempar sebagai ``ConfigError`` dengan kode stabil;
modul ini tidak menulis berkas dan tidak menyediakan fallback struktur.
Kontrak data ada di ``docs/dev/formats.md``.
"""

import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .. import paths as path_mod
from ..errors import ConfigError
from .common import _boolean, _dimension, _enum, _text, load_yaml_mapping
from .models import (
    BackMatterItem,
    BodyChapter,
    CoverOverrides,
    FrontMatterItem,
    ListSettings,
    Numbering,
    Structure,
)
from .validation import (
    _check_unknown,
    _err,
    _expect_list,
    _expect_mapping,
    _required,
)

_STRUCTURE_KEYS = frozenset(
    {"format", "front_matter", "body", "back_matter", "toc", "numbering", "lists", "cover"}
)
_FRONT_MATTER_RULES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "cover": frozenset({"generated"}),
        "approval": frozenset({"template"}),
        "statement": frozenset({"template"}),
        "preface": frozenset({"document"}),
        "abstract_id": frozenset({"document"}),
        "abstract_en": frozenset({"document"}),
        "toc": frozenset({"generated"}),
        "list_of_tables": frozenset({"generated"}),
        "list_of_figures": frozenset({"generated"}),
    }
)
_BACK_MATTER_RULES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "bibliography": frozenset({"generated"}),
        "appendices": frozenset({"document"}),
    }
)
_FRONT_ITEM_KEYS = frozenset({"id", "source", "template"})
_BODY_KEYS = frozenset({"id", "title"})
_BACK_KEYS = frozenset({"id", "source"})
_NUMBERING_KEYS = frozenset({"body", "sub_dot", "subsub_dot"})
_LISTS_KEYS = frozenset({"figures", "tables"})
_COVER_KEYS = frozenset({"show_lecturer", "logo_width", "title_split"})
_BODY_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def _normalize_title(title: str) -> str:
    return " ".join(title.split()).casefold()


def _parse_front_matter(
    data: Any,
    *,
    path: Path,
    templates: Path,
    toc: bool,
    lists: ListSettings,
) -> tuple[FrontMatterItem, ...]:
    """Validasi ``front_matter`` terhadap aturan source, ``toc``, dan ``lists``.

    Mengembalikan tuple unik berurutan; template di-resolve terhadap
    ``templates``. Melempar ``ConfigError`` untuk ID/source tidak dikenal,
    duplikat, template hilang, atau kombinasi ``front_matter`` yang tidak
    konsisten.
    """

    entries = _expect_list(data, path=path, key="front_matter")
    if not entries:
        raise _err(
            "front_matter minimal memuat satu entri",
            code="CFG-REQUIRED",
            path=path,
            key="front_matter",
        )
    result: list[FrontMatterItem] = []
    seen: set[str] = set()
    for index, raw in enumerate(entries, start=1):
        key = f"front_matter[{index}]"
        item = _expect_mapping(raw, path=path, key=key)
        _check_unknown(item, _FRONT_ITEM_KEYS, path=path, key=key)
        item_id = _text(
            _required(item, "id", path=path, key=key),
            path=path,
            key=f"{key}.id",
        )
        if item_id not in _FRONT_MATTER_RULES:
            raise _err(
                f"ID front matter '{item_id}' tidak didukung",
                code="CFG-UNKNOWN-FRONT-MATTER",
                path=path,
                key=f"{key}.id",
            )
        if item_id in seen:
            raise _err(
                f"ID front matter '{item_id}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.id",
            )
        seen.add(item_id)
        source = _text(
            _required(item, "source", path=path, key=key),
            path=path,
            key=f"{key}.source",
        )
        if source not in _FRONT_MATTER_RULES[item_id]:
            allowed = ", ".join(sorted(_FRONT_MATTER_RULES[item_id]))
            raise _err(
                f"front matter '{item_id}' tidak mendukung source '{source}'; gunakan {allowed}",
                code="CFG-CONDITIONAL",
                path=path,
                key=f"{key}.source",
            )
        template_value = item.get("template")
        if source == "template":
            template = _text(
                template_value,
                path=path,
                key=f"{key}.template",
            )
            if not template.lower().endswith(".md"):
                raise _err(
                    f"template '{item_id}' harus berekstensi .md",
                    code="CFG-TYPE",
                    path=path,
                    key=f"{key}.template",
                )
            resolved = path_mod.safe_relative_path(
                template,
                base=templates,
                label=f"{key}.template",
                code="CFG-TEMPLATE-MISSING",
                must_exist=True,
                expect_file=True,
            )
            result.append(FrontMatterItem(id=item_id, source=source, template=resolved.name))
        else:
            if template_value is not None:
                raise _err(
                    f"template hanya boleh untuk source 'template' ({item_id})",
                    code="CFG-CONDITIONAL",
                    path=path,
                    key=f"{key}.template",
                )
            result.append(FrontMatterItem(id=item_id, source=source))

    if "cover" not in seen:
        raise _err(
            "front_matter wajib memuat 'cover'",
            code="CFG-REQUIRED",
            path=path,
            key="front_matter",
        )
    if toc and "toc" not in seen:
        raise _err(
            "front_matter wajib memuat 'toc' karena structure.toc bernilai true",
            code="CFG-CONDITIONAL",
            path=path,
            key="front_matter",
        )
    if not toc and "toc" in seen:
        raise _err(
            "front_matter tidak boleh memuat 'toc' karena structure.toc bernilai false",
            code="CFG-CONDITIONAL",
            path=path,
            key="front_matter",
        )
    tables_expected = "list_of_tables" in seen
    figures_expected = "list_of_figures" in seen
    if lists.tables != tables_expected:
        raise _err(
            "front_matter.list_of_tables tidak konsisten dengan lists.tables",
            code="CFG-CONDITIONAL",
            path=path,
            key="lists.tables",
        )
    if lists.figures != figures_expected:
        raise _err(
            "front_matter.list_of_figures tidak konsisten dengan lists.figures",
            code="CFG-CONDITIONAL",
            path=path,
            key="lists.figures",
        )
    return tuple(result)


def _parse_body(data: Any, *, path: Path) -> tuple[BodyChapter, ...]:
    """Validasi ``body``: minimal satu bab, ID unik, dan judul unik casefold."""

    entries = _expect_list(data, path=path, key="body")
    if not entries:
        raise _err(
            "body minimal memuat satu bab",
            code="CFG-REQUIRED",
            path=path,
            key="body",
        )
    result: list[BodyChapter] = []
    ids: set[str] = set()
    titles: set[str] = set()
    for index, raw in enumerate(entries, start=1):
        key = f"body[{index}]"
        item = _expect_mapping(raw, path=path, key=key)
        _check_unknown(item, _BODY_KEYS, path=path, key=key)
        chapter_id = _text(
            _required(item, "id", path=path, key=key),
            path=path,
            key=f"{key}.id",
        )
        if not _BODY_ID_RE.fullmatch(chapter_id):
            raise _err(
                f"ID bab '{chapter_id}' tidak valid; gunakan [a-z][a-z0-9-]*",
                code="CFG-TYPE",
                path=path,
                key=f"{key}.id",
            )
        if chapter_id in ids:
            raise _err(
                f"ID bab '{chapter_id}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.id",
            )
        ids.add(chapter_id)
        title = _text(
            _required(item, "title", path=path, key=key),
            path=path,
            key=f"{key}.title",
        )
        normalized = _normalize_title(title)
        if normalized in titles:
            raise _err(
                f"judul bab '{title}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.title",
            )
        titles.add(normalized)
        result.append(BodyChapter(id=chapter_id, title=title))
    return tuple(result)


def _parse_back_matter(data: Any, *, path: Path) -> tuple[BackMatterItem, ...]:
    """Validasi ``back_matter`` opsional; ID dan source harus sesuai aturan."""

    if data is None:
        return ()
    entries = _expect_list(data, path=path, key="back_matter")
    result: list[BackMatterItem] = []
    seen: set[str] = set()
    for index, raw in enumerate(entries, start=1):
        key = f"back_matter[{index}]"
        item = _expect_mapping(raw, path=path, key=key)
        _check_unknown(item, _BACK_KEYS, path=path, key=key)
        item_id = _text(
            _required(item, "id", path=path, key=key),
            path=path,
            key=f"{key}.id",
        )
        if item_id not in _BACK_MATTER_RULES:
            raise _err(
                f"ID back matter '{item_id}' tidak didukung",
                code="CFG-UNKNOWN-FRONT-MATTER",
                path=path,
                key=f"{key}.id",
            )
        if item_id in seen:
            raise _err(
                f"ID back matter '{item_id}' duplikat",
                code="CFG-DUPLICATE",
                path=path,
                key=f"{key}.id",
            )
        seen.add(item_id)
        source = _text(
            _required(item, "source", path=path, key=key),
            path=path,
            key=f"{key}.source",
        )
        if source not in _BACK_MATTER_RULES[item_id]:
            allowed = ", ".join(sorted(_BACK_MATTER_RULES[item_id]))
            raise _err(
                f"back matter '{item_id}' tidak mendukung source '{source}'; gunakan {allowed}",
                code="CFG-CONDITIONAL",
                path=path,
                key=f"{key}.source",
            )
        result.append(BackMatterItem(id=item_id, source=source))
    return tuple(result)


def _parse_numbering(data: Any, *, path: Path) -> Numbering:
    mapping = _expect_mapping(data, path=path, key="numbering")
    _check_unknown(mapping, _NUMBERING_KEYS, path=path, key="numbering")
    return Numbering(
        body=_enum(
            _required(mapping, "body", path=path, key="numbering"),
            path=path,
            key="numbering.body",
            choices=("BAB_ROMAN", "ARABIC_DOTTED"),
        ),
        sub_dot=_boolean(mapping.get("sub_dot"), path=path, key="numbering.sub_dot", default=True),
        subsub_dot=_boolean(
            mapping.get("subsub_dot"),
            path=path,
            key="numbering.subsub_dot",
            default=True,
        ),
    )


def _parse_lists(data: Any, *, path: Path) -> ListSettings:
    mapping = _expect_mapping(data, path=path, key="lists")
    _check_unknown(mapping, _LISTS_KEYS, path=path, key="lists")
    return ListSettings(
        figures=_boolean(
            _required(mapping, "figures", path=path, key="lists"),
            path=path,
            key="lists.figures",
        ),
        tables=_boolean(
            _required(mapping, "tables", path=path, key="lists"),
            path=path,
            key="lists.tables",
        ),
    )


def _parse_cover(data: Any, *, path: Path) -> CoverOverrides:
    if data is None:
        return CoverOverrides()
    mapping = _expect_mapping(data, path=path, key="cover")
    _check_unknown(mapping, _COVER_KEYS, path=path, key="cover")
    return CoverOverrides(
        show_lecturer=_boolean(
            mapping.get("show_lecturer"),
            path=path,
            key="cover.show_lecturer",
            default=True,
        ),
        logo_width=_dimension(
            mapping.get("logo_width"),
            path=path,
            key="cover.logo_width",
            default="4.88cm",
            positive=True,
        ),
        title_split=_boolean(
            mapping.get("title_split"),
            path=path,
            key="cover.title_split",
            default=True,
        ),
    )


def load_structure(structure_id: str, *, root: Path | None = None) -> Structure:
    """Muat dan validasi ``structures/<structure_id>/structure.yml``.

    Mengembalikan ``Structure`` immutable; template front matter di-resolve
    terhadap direktori struktur. ``root`` opsional mengganti direktori data
    paket. Semua kegagalan skema, referensi format, template, dan kombinasi
    field dilempar sebagai ``ConfigError``.
    """

    path_mod.validate_id(structure_id, kind="struktur")
    directory = path_mod.structure_dir(structure_id, root=root)
    path = directory / "structure.yml"
    if not path.is_file():
        raise ConfigError(
            f"struktur '{structure_id}': structure.yml tidak ditemukan",
            code="CFG-STRUCTURE-MISSING",
            path=path,
        )
    data = load_yaml_mapping(path, label="structure.yml")
    _check_unknown(
        data,
        _STRUCTURE_KEYS,
        path=path,
        key="structure",
    )
    format_id = _text(
        _required(data, "format", path=path, key="structure"),
        path=path,
        key="format",
    )
    path_mod.validate_id(format_id, kind="format")

    toc = _boolean(
        _required(data, "toc", path=path, key="structure"),
        path=path,
        key="toc",
    )
    numbering = _parse_numbering(
        _required(data, "numbering", path=path, key="structure"),
        path=path,
    )
    lists = _parse_lists(
        _required(data, "lists", path=path, key="structure"),
        path=path,
    )
    templates = directory / "templates"
    if templates.exists() and not templates.is_dir():
        raise _err(
            "'templates' harus berupa direktori",
            code="CFG-ASSET-MISSING",
            path=templates,
            key="templates",
        )
    path_mod.check_case_collisions(templates, label="templates")
    front_matter = _parse_front_matter(
        _required(data, "front_matter", path=path, key="structure"),
        path=path,
        templates=templates,
        toc=toc,
        lists=lists,
    )
    body = _parse_body(
        _required(data, "body", path=path, key="structure"),
        path=path,
    )
    back_matter = _parse_back_matter(data.get("back_matter"), path=path)
    cover = _parse_cover(data.get("cover"), path=path)

    return Structure(
        id=structure_id,
        format_id=format_id,
        path=directory,
        data=MappingProxyType(dict(data)),
        front_matter=front_matter,
        body=body,
        back_matter=back_matter,
        toc=toc,
        numbering=numbering,
        lists=lists,
        cover=cover,
    )
