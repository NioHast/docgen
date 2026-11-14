"""Fixture bersama AutoOffice yang deterministik dan sepenuhnya offline.

Fixture di sini tidak menyentuh Word/PowerPoint COM, Google API, jaringan, atau
jam sistem. Test domain dapat memakai workspace sementara, fake clock, fake COM,
fake Google, dan normalizer golden tanpa menulis ke repo.
"""

from collections import deque
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest


@dataclass(frozen=True)
class TempWorkspace:
    """Direktori kerja terisolasi di bawah `tmp_path`."""

    root: Path
    input: Path
    output: Path
    cache: Path

    def path(self, name: str) -> Path:
        """Path di dalam direktori kerja tanpa membuat berkas."""
        return self.root / name


@pytest.fixture
def temp_workspace(tmp_path: Path) -> TempWorkspace:
    """Workspace sementara dengan direktori input, output, dan cache."""
    root = tmp_path / "workspace"
    input_dir = root / "input"
    output_dir = root / "output"
    cache_dir = root / "cache"
    for direktori in (root, input_dir, output_dir, cache_dir):
        direktori.mkdir(parents=True, exist_ok=True)
    return TempWorkspace(root=root, input=input_dir, output=output_dir, cache=cache_dir)


@dataclass
class FakeClock:
    """Jam palsu yang hanya berubah saat `advance` dipanggil."""

    current: datetime

    def now(self, tz: Any = None) -> datetime:
        """Kembalikan waktu tetap, dikonversi ke zona waktu bila diminta."""
        if tz is None:
            return self.current
        return self.current.astimezone(tz)

    def advance(self, seconds: float) -> datetime:
        """Majukan jam dan kembalikan waktu baru."""
        self.current = self.current + timedelta(seconds=seconds)
        return self.current


@pytest.fixture
def fake_clock() -> FakeClock:
    """Jam palsu mulai 2026-01-01T00:00:00Z."""
    return FakeClock(datetime(2026, 1, 1, tzinfo=UTC))


@dataclass(frozen=True)
class ComCall:
    """Satu panggilan COM palsu yang tercatat."""

    name: str
    args: tuple[Any, ...]
    kwargs: tuple[tuple[str, Any], ...]


class FakeComSequence:
    """Urutan respons COM palsu yang dicatat per panggilan.

    Pemakaian:
        com = FakeComSequence([{"Name": "Dokumen"}])
        com.call("Documents.Open", path)
        assert com.calls[0].name == "Documents.Open"
    """

    def __init__(self, responses: Sequence[Any] = ()) -> None:
        self._responses: deque[Any] = deque(responses)
        self.calls: list[ComCall] = []

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Catat panggilan dan kembalikan respons berikutnya."""
        self.calls.append(ComCall(name=name, args=tuple(args), kwargs=tuple(kwargs.items())))
        if not self._responses:
            raise AssertionError(f"Fake COM kehabisan respons untuk {name}")
        return self._responses.popleft()

    def __call__(self, name: str, *args: Any, **kwargs: Any) -> Any:
        return self.call(name, *args, **kwargs)

    @property
    def remaining(self) -> int:
        """Jumlah respons yang belum dikonsumsi."""
        return len(self._responses)


@pytest.fixture
def fake_com() -> FakeComSequence:
    """Fake COM tanpa `win32com`, `pythoncom`, atau proses Word nyata."""
    return FakeComSequence()


@dataclass(frozen=True)
class GoogleResponse:
    """Respons Google palsu dengan body yang dalam keadaan bersih."""

    status: int = 200
    body: Mapping[str, Any] = field(default_factory=dict)


class FakeGoogleApi:
    """Skeleton Google API dengan respons terdaftar per method.

    Method memakai nama bertitik seperti `slides.presentations.get` dan
    `sheets.spreadsheets.values.update`. Tidak ada transport HTTP.
    """

    def __init__(self) -> None:
        self._responses: dict[str, deque[GoogleResponse]] = {}
        self.calls: list[tuple[str, tuple[tuple[str, Any], ...]]] = []

    def stub(self, method: str, *responses: GoogleResponse) -> None:
        """Daftarkan satu atau lebih respons untuk method tertentu."""
        antrean = self._responses.setdefault(method, deque())
        antrean.extend(responses)

    def call(self, method: str, **payload: Any) -> GoogleResponse:
        """Catat panggilan dan kembalikan respons terdaftar atau respons kosong."""
        self.calls.append((method, tuple(payload.items())))
        antrean = self._responses.get(method)
        if antrean:
            return deepcopy(antrean.popleft())
        return GoogleResponse()

    def remaining(self, method: str) -> int:
        """Jumlah respons tersisa untuk satu method."""
        return len(self._responses.get(method, ()))


@pytest.fixture
def fake_google() -> FakeGoogleApi:
    """Fake Google skeleton tanpa google-api-python-client atau OAuth."""
    return FakeGoogleApi()


class GoldenNormalizer:
    """Normalisasi teks, XML, dan part ZIP agar golden deterministik."""

    def normalize_text(self, text: str) -> str:
        """Samakan line ending dan hapus whitespace di akhir baris."""
        return "\n".join(baris.rstrip() for baris in text.replace("\r\n", "\n").split("\n"))

    def normalize_xml(self, text: str) -> str:
        """Hapus timestamp, UUID, dan relationship ID yang tidak stabil."""
        import re

        hasil = text.replace("\r\n", "\n")
        hasil = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", "<timestamp>", hasil)
        hasil = re.sub(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            "<uuid>",
            hasil,
        )
        hasil = re.sub(r"rId\d+", "rId#", hasil)
        hasil = re.sub(r">\s+<", "><", hasil.strip())
        return hasil

    def normalize_zip(self, path: Path) -> dict[str, str]:
        """Baca ZIP dan normalisasi setiap part teks XML/RELS."""
        import zipfile

        hasil: dict[str, str] = {}
        with zipfile.ZipFile(path) as arsip:
            for nama in sorted(arsip.namelist()):
                data = arsip.read(nama)
                if nama.endswith((".xml", ".rels")):
                    hasil[nama] = self.normalize_xml(data.decode("utf-8"))
                else:
                    hasil[nama] = data.hex()
        return hasil


@pytest.fixture
def golden_normalizer() -> GoldenNormalizer:
    """Normalizer golden untuk part DOCX/PPTX dan teks."""
    return GoldenNormalizer()
