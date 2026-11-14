"""API publik pembangunan DOCX.

Modul ini menggantikan entry point CLI ``docgen build --target docx`` dengan
fungsi Python bertipe. Pemanggil CLI cukup memanggil :func:`build_docx`; modul
ini tidak memuat parser argumen dan tidak mengimpor ``autooffice.cli``.
"""

from dataclasses import dataclass
from pathlib import Path

from .errors import OutputError
from .pipeline import BuildOptions, Pipeline

__all__ = ["DocxResult", "build_docx"]


@dataclass(frozen=True)
class DocxResult:
    """Hasil build DOCX beserta artefak dan workspace yang tersedia."""

    docx: Path
    manifest: Path | None
    terms: Path | None
    warnings: tuple[str, ...]
    workspace: Path | None


def build_docx(
    input: Path,
    out: Path | None = None,
    terms: bool = False,
    keep_intermediate: bool = False,
) -> DocxResult:
    """Bangun DOCX dari satu ``document.md`` dan kembalikan :class:`DocxResult`.

    ``out`` menimpa aturan direktori keluaran bawaan (``out/`` untuk contoh
    repo, direktori dokumen untuk dokumen pengguna). ``terms`` mengaktifkan
    check/apply/verify/gate istilah dan mengisi ``DocxResult.terms`` bila
    ``.laporan/istilah-baru.txt`` terbentuk. ``keep_intermediate``
    mempertahankan workspace ``.laporan-build`` yang dikembalikan lewat
    ``DocxResult.workspace``.
    """

    document_path = Path(input).expanduser()
    output_dir = Path(out).expanduser() if out is not None else None
    options = BuildOptions(
        target="docx",
        keep=keep_intermediate,
        terms=terms,
    )
    result = Pipeline().run(document_path, options, output_dir=output_dir)
    docx_path = result.docx
    if docx_path is None or not docx_path.is_file():
        raise OutputError(
            "DOCX tidak terbentuk setelah pipeline selesai",
            code="OUTPUT-DOCX",
            path=docx_path or document_path,
        )
    terms_path = document_path.parent / ".laporan" / "istilah-baru.txt"
    return DocxResult(
        docx=docx_path,
        manifest=result.manifest,
        terms=terms_path if terms and terms_path.exists() else None,
        warnings=result.warnings,
        workspace=result.kept_workspace,
    )
