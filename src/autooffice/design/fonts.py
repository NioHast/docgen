"""Metadata font Plus Jakarta Sans yang dibundel AutoOffice."""

import hashlib
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

FONT_FAMILY = "Plus Jakarta Sans"
FONT_LICENSE = "SIL Open Font License 1.1"
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "plus-jakarta-sans"
LICENSE_FILE = "OFL.txt"
FONT_FILES: tuple[str, ...] = (
    "PlusJakartaSans-Regular.ttf",
    "PlusJakartaSans-SemiBold.ttf",
    "PlusJakartaSans-Bold.ttf",
    "PlusJakartaSans-ExtraBold.ttf",
)
FONT_HASHES: Mapping[str, str] = MappingProxyType(
    {
        "PlusJakartaSans-Regular.ttf": (
            "bd6276d4060e3b1ebc45047469e0bb86b08f301ba681cdf1ceb6245ea10478d2"
        ),
        "PlusJakartaSans-SemiBold.ttf": (
            "65dbcedb6596a41c30869729eb31cb57d1f5edfe365684314bba8a1994eaa4cb"
        ),
        "PlusJakartaSans-Bold.ttf": (
            "5f5342ef76862b5b5365d1dff1a667629dfa484e388dd602552f647219c3870f"
        ),
        "PlusJakartaSans-ExtraBold.ttf": (
            "7d60d21b5dec501c77437e80aabd539f1d7a7b0ac7d4ada361d4d42abc7c55ea"
        ),
    }
)
LICENSE_SHA256 = "995c7199cab65954f545996326755daee7b63cc6b42b06c13da1f9502ab08a99"
ASSET_FILES: tuple[str, ...] = (*FONT_FILES, LICENSE_FILE)
ASSET_HASHES: Mapping[str, str] = MappingProxyType({**FONT_HASHES, LICENSE_FILE: LICENSE_SHA256})


def font_path(file_name: str) -> Path:
    """Kembalikan path aset font yang terdaftar."""
    if file_name not in ASSET_HASHES:
        raise KeyError(f"aset font tidak terdaftar: {file_name}")
    return FONT_DIR / file_name


def sha256(path: Path) -> str:
    """Hitung digest SHA256 sebuah berkas aset."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
