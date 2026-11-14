"""Domain Google AutoOffice: OAuth, Drive, Sheets, Slides, sync, dan fake.

Import publik dilakukan lazy melalui :func:`__getattr__` supaya memuat paket
ini tidak menarik dependensi Google, tidak membuat client, dan tidak menyentuh
jaringan. Error dasar didefinisikan di sini agar modul domain lain dapat
memakainya tanpa import melingkar.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from autooffice.errors import AutoOfficeError


class GoogleError(AutoOfficeError):
    """Kegagalan operasi Google yang dapat ditampilkan ke pengguna."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class GoogleAuthError(GoogleError):
    """OAuth, token, atau kredensial Google tidak valid."""


class DriveError(GoogleError):
    """Upload atau akses Drive gagal."""


class SheetsError(GoogleError):
    """Operasi spreadsheet, tab, nilai, atau chart Sheets gagal."""


class SlidesError(GoogleError):
    """Operasi presentasi Google Slides gagal."""


class ChartPlaceholderError(SlidesError):
    """Placeholder chart hilang, ganda, atau bertipe salah."""


class TablePreflightError(SlidesError):
    """Table native tidak memenuhi kontrak preflight."""


class GoogleStateError(GoogleError):
    """State Google tidak ada, rusak, atau tidak aman."""


class GoogleSyncError(GoogleError):
    """Push, pull, diff, atau apply teks Google gagal."""


class FakeGoogleError(GoogleError):
    """Fake Google menolak request yang tidak didukung atau tidak valid."""


_EXPORTS: dict[str, tuple[str, str]] = {
    "SLIDES_MIME_TYPE": ("autooffice.google.drive", "SLIDES_MIME_TYPE"),
    "PPTX_MIME_TYPE": ("autooffice.google.drive", "PPTX_MIME_TYPE"),
    "DriveApi": ("autooffice.google.drive", "DriveApi"),
    "GoogleDriveApi": ("autooffice.google.drive", "GoogleDriveApi"),
    "UploadedPresentation": ("autooffice.google.drive", "UploadedPresentation"),
    "upload_presentation": ("autooffice.google.drive", "upload_presentation"),
    "SCOPES": ("autooffice.google.auth", "SCOPES"),
    "OAuthSettings": ("autooffice.google.auth", "OAuthSettings"),
    "TokenStore": ("autooffice.google.auth", "TokenStore"),
    "AuthorizationRequest": ("autooffice.google.auth", "AuthorizationRequest"),
    "begin_authorization": ("autooffice.google.auth", "begin_authorization"),
    "build_consent_url": ("autooffice.google.auth", "build_consent_url"),
    "consent_parameters": ("autooffice.google.auth", "consent_parameters"),
    "create_flow": ("autooffice.google.auth", "create_flow"),
    "default_token_path": ("autooffice.google.auth", "default_token_path"),
    "exchange_code": ("autooffice.google.auth", "exchange_code"),
    "load_credentials": ("autooffice.google.auth", "load_credentials"),
    "run_interactive_authorization": (
        "autooffice.google.auth",
        "run_interactive_authorization",
    ),
    "SheetsApi": ("autooffice.google.sheets", "SheetsApi"),
    "GoogleSheetsApi": ("autooffice.google.sheets", "GoogleSheetsApi"),
    "SpreadsheetRef": ("autooffice.google.sheets", "SpreadsheetRef"),
    "SheetRef": ("autooffice.google.sheets", "SheetRef"),
    "ChartRecord": ("autooffice.google.sheets", "ChartRecord"),
    "ChartLink": ("autooffice.google.charts", "ChartLink"),
    "build_chart_specs": ("autooffice.google.charts", "build_chart_specs"),
    "ensure_sheet_chart": ("autooffice.google.charts", "ensure_sheet_chart"),
    "ensure_workbook": ("autooffice.google.charts", "ensure_workbook"),
    "sheet_values": ("autooffice.google.charts", "sheet_values"),
    "sheets_chart_spec": ("autooffice.google.charts", "sheets_chart_spec"),
    "tab_name_for": ("autooffice.google.charts", "tab_name_for"),
    "PresentationSnapshot": ("autooffice.google.slides", "PresentationSnapshot"),
    "SlideSnapshot": ("autooffice.google.slides", "SlideSnapshot"),
    "PageElement": ("autooffice.google.slides", "PageElement"),
    "ElementSize": ("autooffice.google.slides", "ElementSize"),
    "ElementTransform": ("autooffice.google.slides", "ElementTransform"),
    "SlidesApi": ("autooffice.google.slides", "SlidesApi"),
    "GoogleSlidesApi": ("autooffice.google.slides", "GoogleSlidesApi"),
    "ChartReplacementPlan": ("autooffice.google.slides", "ChartReplacementPlan"),
    "find_chart_placeholders": ("autooffice.google.slides", "find_chart_placeholders"),
    "preflight_chart_replacements": (
        "autooffice.google.slides",
        "preflight_chart_replacements",
    ),
    "preflight_native_tables": ("autooffice.google.slides", "preflight_native_tables"),
    "replace_chart_placeholders": (
        "autooffice.google.slides",
        "replace_chart_placeholders",
    ),
    "table_requirements": ("autooffice.google.slides", "table_requirements"),
    "TextDiff": ("autooffice.google.sync", "TextDiff"),
    "TextChange": ("autooffice.google.sync", "TextChange"),
    "GoogleServices": ("autooffice.google.sync", "GoogleServices"),
    "apply_diff": ("autooffice.google.sync", "apply_diff"),
    "create_google_services": ("autooffice.google.sync", "create_google_services"),
    "diff_text": ("autooffice.google.sync", "diff_text"),
    "pull_text": ("autooffice.google.sync", "pull_text"),
    "push_deck": ("autooffice.google.sync", "push_deck"),
    "push_text": ("autooffice.google.sync", "push_text"),
    "sync_deck": ("autooffice.google.sync", "sync_deck"),
    "ChartState": ("autooffice.google.state", "ChartState"),
    "GoogleState": ("autooffice.google.state", "GoogleState"),
    "STATE_SCHEMA": ("autooffice.google.state", "STATE_SCHEMA"),
    "atomic_write_json": ("autooffice.google.state", "atomic_write_json"),
    "deck_sha256": ("autooffice.google.state", "deck_sha256"),
    "load_state": ("autooffice.google.state", "load_state"),
    "new_state": ("autooffice.google.state", "new_state"),
    "save_state": ("autooffice.google.state", "save_state"),
    "state_path": ("autooffice.google.state", "state_path"),
    "TextEntry": ("autooffice.google.extract", "TextEntry"),
    "PulledText": ("autooffice.google.extract", "PulledText"),
    "extract_text": ("autooffice.google.extract", "extract_text"),
    "FakeDrive": ("autooffice.google.fake", "FakeDrive"),
    "FakeSlides": ("autooffice.google.fake", "FakeSlides"),
    "FakeSheets": ("autooffice.google.fake", "FakeSheets"),
    "FakeGoogleServices": ("autooffice.google.fake", "FakeGoogleServices"),
}

__all__ = [
    "PPTX_MIME_TYPE",
    "SCOPES",
    "SLIDES_MIME_TYPE",
    "STATE_SCHEMA",
    "AuthorizationRequest",
    "ChartLink",
    "ChartPlaceholderError",
    "ChartRecord",
    "ChartReplacementPlan",
    "ChartState",
    "DriveApi",
    "DriveError",
    "ElementSize",
    "ElementTransform",
    "FakeDrive",
    "FakeGoogleError",
    "FakeGoogleServices",
    "FakeSheets",
    "FakeSlides",
    "GoogleAuthError",
    "GoogleDriveApi",
    "GoogleError",
    "GoogleServices",
    "GoogleSheetsApi",
    "GoogleSlidesApi",
    "GoogleState",
    "GoogleStateError",
    "GoogleSyncError",
    "OAuthSettings",
    "PageElement",
    "PresentationSnapshot",
    "PulledText",
    "SheetRef",
    "SheetsApi",
    "SheetsError",
    "SlideSnapshot",
    "SlidesApi",
    "SlidesError",
    "SpreadsheetRef",
    "TablePreflightError",
    "TextChange",
    "TextDiff",
    "TextEntry",
    "TokenStore",
    "UploadedPresentation",
    "apply_diff",
    "atomic_write_json",
    "begin_authorization",
    "build_chart_specs",
    "build_consent_url",
    "consent_parameters",
    "create_flow",
    "create_google_services",
    "deck_sha256",
    "default_token_path",
    "diff_text",
    "ensure_sheet_chart",
    "ensure_workbook",
    "exchange_code",
    "extract_text",
    "find_chart_placeholders",
    "load_credentials",
    "load_state",
    "new_state",
    "preflight_chart_replacements",
    "preflight_native_tables",
    "pull_text",
    "push_deck",
    "push_text",
    "replace_chart_placeholders",
    "run_interactive_authorization",
    "save_state",
    "sheet_values",
    "sheets_chart_spec",
    "state_path",
    "sync_deck",
    "tab_name_for",
    "table_requirements",
    "upload_presentation",
]


def __getattr__(name: str) -> Any:
    """Impor simbol publik dari modul pemiliknya secara lazy."""
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'autooffice.google' tidak memiliki atribut {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


if TYPE_CHECKING:  # pragma: no cover - bantuan tipe, bukan kode runtime
    from autooffice.google.auth import (
        SCOPES,
        OAuthSettings,
        TokenStore,
        default_token_path,
    )
    from autooffice.google.charts import ChartLink
    from autooffice.google.drive import DriveApi, UploadedPresentation
    from autooffice.google.extract import PulledText, TextEntry
    from autooffice.google.fake import FakeDrive, FakeGoogleServices, FakeSheets, FakeSlides
    from autooffice.google.sheets import (
        ChartRecord,
        GoogleSheetsApi,
        SheetRef,
        SheetsApi,
        SpreadsheetRef,
    )
    from autooffice.google.slides import (
        ChartReplacementPlan,
        ElementSize,
        ElementTransform,
        GoogleSlidesApi,
        PageElement,
        PresentationSnapshot,
        SlidesApi,
        SlideSnapshot,
    )
    from autooffice.google.state import ChartState, GoogleState
    from autooffice.google.sync import GoogleServices, TextChange, TextDiff
