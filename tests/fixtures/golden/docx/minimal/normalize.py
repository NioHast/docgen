"""Normalisasi paket DOCX dan bangun/verifikasi golden baseline.

Baseline disimpan sebagai JSON yang memuat part XML ternormalisasi dan hash
part biner. Dengan begitu perubahan dapat direview sebagai diff teks tanpa
menyimpan DOCX biner besar.

Normalisasi yang dilakukan:

- timestamp ``dcterms:created``/``dcterms:modified`` menjadi ``<TIMESTAMP>``;
- Id relationship menjadi ``rId1``, ``rId2``, ... berdasarkan
  (type, target, target mode) yang stabil;
- referensi ``r:id``/``r:embed``/``r:link`` dan nama part media yang memuat
  Id relationship ikut dinormalisasi;
- path absolut direktori data paket menjadi ``<PACKAGE_DATA>`` dengan
  pemisah path seragam ``/``;
- XML diserialisasi ulang secara pretty-print agar diff mudah dibaca;
- part non-XML diringkas menjadi ukuran byte dan SHA-256.

Jalankan ``python normalize.py --update`` untuk membuat ulang baseline dan
``python normalize.py`` untuk memeriksa baseline tanpa menulis file.
"""

import argparse
import hashlib
import json
import posixpath
import re
import shutil
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from unittest import mock

from lxml import etree

GOLDEN_DIR = Path(__file__).resolve().parent
REPO_ROOT = GOLDEN_DIR.parents[4]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "docx" / "minimal"
BASELINE_PATH = GOLDEN_DIR / "baseline.json"

SCHEMA_VERSION = 1
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_ATTR_PREFIX = f"{{{REL_NS}}}"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DCTERMS_NS = "http://purl.org/dc/terms/"
DCTERMS_CREATED = f"{{{DCTERMS_NS}}}created"
DCTERMS_MODIFIED = f"{{{DCTERMS_NS}}}modified"
CONTENT_TYPES_PART = "[Content_Types].xml"

# Cocok untuk path absolut maupun relatif menuju data paket, di Windows
# maupun POSIX. Suffix ikut ditangkap agar pemisah path bisa diseragamkan.
_DATA_PATH_RE = re.compile(
    r"(?:[A-Za-z]:)?[^\s\"'<>]*?[\\/]autooffice[\\/]docx[\\/]data"
    r"(?P<suffix>(?:[\\/][^\s\"'<>]*)?)"
)


def _normalize_text(value: str) -> str:
    """Ganti path direktori data paket dengan placeholder lintas platform."""

    def replace(match: re.Match[str]) -> str:
        suffix = (match.group("suffix") or "").replace("\\", "/")
        return f"<PACKAGE_DATA>{suffix}"

    return _DATA_PATH_RE.sub(replace, value)


def _replace_id_token(value: str, old: str, new: str) -> str:
    return re.sub(
        rf"(?<![A-Za-z0-9]){re.escape(old)}(?![A-Za-z0-9])",
        new,
        value,
    )


def _rels_owner(rels_name: str) -> str | None:
    """Kembalikan part pemilik relationship, atau ``""`` untuk root paket."""

    if rels_name == "_rels/.rels":
        return ""
    directory, filename = posixpath.split(rels_name)
    if posixpath.basename(directory) != "_rels":
        return None
    owner_directory = posixpath.dirname(directory)
    owner_name = filename.removesuffix(".rels")
    return posixpath.join(owner_directory, owner_name) if owner_directory else owner_name


def _relationship_elements(root: etree._Element) -> list[etree._Element]:
    relationship_tag = f"{{{PKG_REL_NS}}}Relationship"
    return [element for element in root if element.tag == relationship_tag]


def _canonicalize_relationships(
    parts: Mapping[str, bytes],
) -> tuple[dict[str, dict[str, str]], dict[str, str], dict[str, bytes]]:
    """Normalisasi Id relationship dan kembalikan peta Id serta nama part."""

    owner_mapping: dict[str, dict[str, str]] = {}
    part_name_map: dict[str, str] = {}
    rels_records: dict[str, list[dict[str, Any]]] = {}
    rels_roots: dict[str, etree._Element] = {}

    for name in sorted(parts):
        if not name.endswith(".rels"):
            continue
        owner = _rels_owner(name)
        if owner is None:
            continue
        root = etree.fromstring(parts[name])
        records: list[dict[str, Any]] = []
        for element in _relationship_elements(root):
            records.append(
                {
                    "element": element,
                    "old_id": element.get("Id") or "",
                    "type": element.get("Type") or "",
                    "target": element.get("Target") or "",
                    "mode": element.get("TargetMode") or "",
                }
            )
        records.sort(
            key=lambda record: (
                record["type"],
                record["target"],
                record["mode"],
                record["old_id"],
            )
        )
        mapping = {
            str(record["old_id"]): f"rId{index}" for index, record in enumerate(records, start=1)
        }
        owner_mapping[owner] = mapping
        rels_records[name] = records
        rels_roots[name] = root
        owner_directory = posixpath.dirname(owner)

        for record in records:
            old_id = str(record["old_id"])
            new_id = mapping[old_id]
            old_target = str(record["target"])
            new_target = _replace_id_token(old_target, old_id, new_id)
            record["new_id"] = new_id
            record["new_target"] = new_target

            if old_target == new_target or record["mode"].lower() == "external":
                continue
            old_part = posixpath.normpath(posixpath.join(owner_directory, old_target))
            new_part = posixpath.normpath(posixpath.join(owner_directory, new_target))
            if old_part in parts and old_part != new_part:
                part_name_map[old_part] = new_part

    for records in rels_records.values():
        for record in records:
            element = record["element"]
            element.set("Id", record["new_id"])
            element.set("Target", record["new_target"])

    serialized_rels = {
        name: etree.tostring(root, encoding="utf-8") for name, root in rels_roots.items()
    }
    return owner_mapping, part_name_map, serialized_rels


def _normalize_xml(
    data: bytes,
    *,
    part_name: str,
    owner_mapping: Mapping[str, Mapping[str, str]],
    part_name_map: Mapping[str, str],
) -> str:
    root = etree.fromstring(data)
    ids = owner_mapping.get(part_name, {})

    for element in root.iter():
        if element.tag in {DCTERMS_CREATED, DCTERMS_MODIFIED}:
            element.text = "<TIMESTAMP>"
        if element.text is not None:
            element.text = _normalize_text(element.text)
        if element.tail is not None:
            element.tail = _normalize_text(element.tail)
        for attribute, value in list(element.attrib.items()):
            normalized = _normalize_text(value)
            if attribute.startswith(REL_ATTR_PREFIX):
                normalized = ids.get(normalized, normalized)
            if part_name == CONTENT_TYPES_PART and etree.QName(attribute).localname == "PartName":
                old_name = normalized.removeprefix("/")
                if old_name in part_name_map:
                    normalized = f"/{part_name_map[old_name]}"
            element.set(attribute, normalized)

    return etree.tostring(root, encoding="unicode", pretty_print=True)


def normalize_parts(parts: Mapping[str, bytes]) -> dict[str, Any]:
    """Kembalikan manifest part ternormalisasi yang siap dibandingkan."""

    owner_mapping, part_name_map, serialized_rels = _canonicalize_relationships(parts)
    working_parts = dict(parts)
    working_parts.update(serialized_rels)
    normalized: dict[str, Any] = {}

    for name in sorted(parts):
        payload = working_parts[name]
        normalized_name = part_name_map.get(name, name)
        if normalized_name in normalized:
            raise ValueError(f"nama part bertabrakan setelah normalisasi: {normalized_name}")
        if name.endswith((".xml", ".rels")):
            normalized[normalized_name] = _normalize_xml(
                payload,
                part_name=name,
                owner_mapping=owner_mapping,
                part_name_map=part_name_map,
            )
        else:
            normalized[normalized_name] = {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }

    return normalized


def _read_parts(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {
            info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()
        }


def build_baseline() -> dict[str, Any]:
    """Bangun fixture dengan ``build_docx`` lalu normalisasi seluruh part."""

    from autooffice.docx.command import build_docx
    from autooffice.docx.stages import office

    with tempfile.TemporaryDirectory(prefix="autooffice-docx-golden-") as temporary:
        root = Path(temporary)
        project = root / "project"
        shutil.copytree(FIXTURE_ROOT, project)
        # Word di-disable agar baseline deterministik dan tidak bergantung pada
        # versi Word. Perilaku COM nyata diuji terpisah dan tidak masuk golden.
        with mock.patch.object(office, "word_available", return_value=False):
            result = build_docx(
                project / "document.md",
                out=root / "out",
                terms=False,
                keep_intermediate=False,
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "fixture": "tests/fixtures/docx/minimal/document.md",
            "build": {
                "api": "autooffice.docx.command.build_docx",
                "terms": False,
                "keep_intermediate": False,
                "word": "disabled",
            },
            "normalization": [
                "dcterms:created/dcterms:modified -> <TIMESTAMP>",
                "relationship Ids -> rId1, rId2, ...",
                "r:id/r:embed/r:link references and media part names follow relationship Ids",
                "package data paths -> <PACKAGE_DATA> with '/' separators",
                "XML reserialized with pretty-print",
                "binary parts represented by byte size and SHA-256",
            ],
            "parts": normalize_parts(_read_parts(result.docx)),
        }


def _changed_parts(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> list[str]:
    names = sorted(set(expected) | set(actual))
    return [name for name in names if expected.get(name) != actual.get(name)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="tulis ulang baseline.json dari build saat ini",
    )
    args = parser.parse_args(argv)

    baseline = build_baseline()
    payload = json.dumps(baseline, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    if args.update:
        BASELINE_PATH.write_text(payload, encoding="utf-8", newline="\n")
        print(f"Baseline ditulis: {BASELINE_PATH}")
        return 0

    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    changed = _changed_parts(expected.get("parts", {}), baseline["parts"])
    if changed:
        print("Baseline tidak cocok pada part berikut:")
        for name in changed:
            print(f"  - {name}")
        print("Jalankan dengan --update setelah perubahan output direview.")
        return 1

    print(f"Baseline cocok: {BASELINE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
