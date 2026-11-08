"""Tes unit untuk ekspor PDF dari DOCX (tanpa memanggil Word/LibreOffice)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_export_pdf():
    spec = importlib.util.spec_from_file_location(
        "export_pdf_uji", ROOT / "tools" / "export_pdf.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_perintah_word_memakai_script_dan_path(tmp_path: Path) -> None:
    module = _load_export_pdf()
    script = tmp_path / "export_pdf.ps1"
    docx = tmp_path / "Laporan.docx"
    pdf = tmp_path / "Laporan.pdf"

    command = module.build_word_command("powershell", script, docx, pdf)

    assert command[:6] == [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
    ]
    assert command[-4:] == [
        "-DocxPath",
        str(docx),
        "-PdfPath",
        str(pdf),
    ]


def test_perintah_libreoffice_headless(tmp_path: Path) -> None:
    module = _load_export_pdf()
    docx = tmp_path / "Laporan.docx"
    outdir = tmp_path / "out"

    command = module.build_libreoffice_command("soffice", docx, outdir)

    assert command == [
        "soffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(outdir),
        str(docx),
    ]


def test_word_tanpa_powershell_gagal_tanpa_memanggil_subprocess(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_export_pdf()
    monkeypatch.setattr(module, "find_powershell", lambda: None)

    assert module.export_with_word(
        tmp_path / "Laporan.docx", tmp_path / "Laporan.pdf", 10
    ) == 1


def test_libreoffice_memindahkan_pdf_ke_nama_tujuan(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_export_pdf()
    docx = tmp_path / "Tugas.docx"
    docx.write_bytes(b"docx")
    pdf = tmp_path / "hasil" / "Tugas-akhir.pdf"
    calls: list[list[str]] = []

    monkeypatch.setattr(module, "find_soffice", lambda: "soffice")

    def fake_run(command: list[str], timeout: int, label: str) -> int:
        calls.append(command)
        outdir = Path(command[command.index("--outdir") + 1])
        (outdir / "Tugas.pdf").write_bytes(b"%PDF-1.4")
        return 0

    monkeypatch.setattr(module, "_run", fake_run)

    assert module.export_with_libreoffice(docx, pdf, 10) == 0
    assert pdf.read_bytes() == b"%PDF-1.4"
    assert calls == [
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf.parent),
            str(docx),
        ]
    ]


def test_main_menolak_docx_yang_tidak_ada(tmp_path: Path) -> None:
    module = _load_export_pdf()

    assert module.main([str(tmp_path / "tidak-ada.docx")]) == 1
