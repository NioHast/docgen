"""OAuth user flow Google untuk AutoOffice.

Tidak ada service account, tidak ada client secret di dalam repo, dan token
disimpan di direktori pengguna. Modul ini tidak membuat client atau menyentuh
jaringan saat diimpor; semua dependensi Google dimuat di dalam fungsi.
"""

import contextlib
import json
import os
import secrets
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from . import GoogleAuthError

SCOPES: tuple[str, str, str] = (
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/spreadsheets",
)
CLIENT_ID_ENV = "GOOGLE_CLIENT_ID"
CLIENT_SECRET_ENV = "GOOGLE_CLIENT_SECRET"
REDIRECT_URI_ENV = "GOOGLE_REDIRECT_URI"
TOKEN_PATH_ENV = "AUTOOFFICE_GOOGLE_TOKEN"
DEFAULT_REDIRECT_URI = "http://localhost:4173/oauth2callback"
TOKEN_DIRECTORY = Path("autooffice") / "google"
TOKEN_FILENAME = "token.json"
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class OAuthFlow(Protocol):
    """Bagian ``google_auth_oauthlib.flow.Flow`` yang dipakai AutoOffice."""

    def authorization_url(self, **kwargs: object) -> tuple[str, str]:
        """Kembalikan URL consent dan state yang dipakai."""

    def fetch_token(self, code: str) -> None:
        """Tukar authorization code menjadi token."""

    @property
    def credentials(self) -> object:
        """Credentials hasil flow."""


@dataclass(frozen=True, slots=True)
class OAuthSettings:
    """Kredensial client OAuth yang berasal dari environment, bukan kode."""

    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str = DEFAULT_REDIRECT_URI

    def __post_init__(self) -> None:
        for name in ("client_id", "client_secret", "redirect_uri"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise GoogleAuthError(f"OAuth {name} wajib berupa teks non-kosong.")
        if not self.redirect_uri.startswith(("http://localhost", "https://")):
            raise GoogleAuthError(
                f"OAuth redirect_uri harus localhost atau https, bukan {self.redirect_uri!r}."
            )

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> OAuthSettings:
        """Baca client id/secret/redirect dari environment tanpa default rahasia."""
        env = os.environ if environment is None else environment
        client_id = env.get(CLIENT_ID_ENV, "").strip()
        client_secret = env.get(CLIENT_SECRET_ENV, "").strip()
        if not client_id or not client_secret:
            raise GoogleAuthError(
                "Kredensial Google OAuth tidak ditemukan. Set "
                f"{CLIENT_ID_ENV} dan {CLIENT_SECRET_ENV}; jangan menaruh secret di repo."
            )
        redirect_uri = env.get(REDIRECT_URI_ENV, DEFAULT_REDIRECT_URI).strip()
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )

    def client_config(self) -> dict[str, object]:
        """Bentuk client config installed app untuk google-auth-oauthlib."""
        return {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": _AUTH_URI,
                "token_uri": _TOKEN_URI,
                "redirect_uris": [self.redirect_uri],
            }
        }


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """URL consent dan state acak yang harus dicocokkan callback."""

    url: str
    state: str

    def __post_init__(self) -> None:
        if not self.url.startswith(("https://", "http://")):
            raise GoogleAuthError(f"URL consent Google tidak valid: {self.url!r}.")
        if not self.state.strip():
            raise GoogleAuthError("State OAuth tidak boleh kosong.")


def default_token_path(environment: Mapping[str, str] | None = None) -> Path:
    """Path token absolut di direktori pengguna, bukan di repo."""
    env = os.environ if environment is None else environment
    override = env.get(TOKEN_PATH_ENV, "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        _require_outside_repository(path)
        return path
    if os.name == "nt":
        root = env.get("LOCALAPPDATA") or env.get("APPDATA")
        if root:
            return (Path(root) / TOKEN_DIRECTORY / TOKEN_FILENAME).resolve()
    xdg = env.get("XDG_CONFIG_HOME")
    if xdg:
        return (Path(xdg) / TOKEN_DIRECTORY / TOKEN_FILENAME).resolve()
    return (Path.home() / ".config" / TOKEN_DIRECTORY / TOKEN_FILENAME).resolve()


def _require_outside_repository(path: Path) -> None:
    resolved = path.expanduser().resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / ".git").exists():
            raise GoogleAuthError(
                f"Token OAuth tidak boleh disimpan di dalam repo: {resolved}. "
                "Pilih direktori pengguna di luar repo."
            )


class TokenStore:
    """Penyimpanan token JSON di luar repo dengan tulisan atomik."""

    def __init__(self, path: str | Path | None = None) -> None:
        target = default_token_path() if path is None else Path(path).expanduser().resolve()
        _require_outside_repository(target)
        self.path = target

    @classmethod
    def from_environment(cls) -> TokenStore:
        """Token store dari ``AUTOOFFICE_GOOGLE_TOKEN`` atau default pengguna."""
        return cls(default_token_path())

    def load(self) -> dict[str, object] | None:
        """Baca token atau kembalikan ``None`` bila belum ada."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as error:
            raise GoogleAuthError(
                f"Token OAuth tidak dapat dibaca: {self.path}: {error}"
            ) from error
        try:
            raw: object = json.loads(text)
        except json.JSONDecodeError as error:
            raise GoogleAuthError(f"Token OAuth bukan JSON valid: {self.path}: {error}") from error
        if not isinstance(raw, Mapping):
            raise GoogleAuthError(f"Token OAuth harus berupa objek JSON: {self.path}.")
        return {str(key): value for key, value in cast("Mapping[object, object]", raw).items()}

    def require(self) -> dict[str, object]:
        """Baca token wajib atau gagal dengan instruksi login."""
        tokens = self.load()
        if tokens is None:
            raise GoogleAuthError(
                f"Token OAuth belum ada di {self.path}; jalankan alur login Google."
            )
        if not tokens.get("access_token") and not tokens.get("refresh_token"):
            raise GoogleAuthError(
                f"Token OAuth di {self.path} tidak memuat access/refresh token; login ulang."
            )
        return tokens

    def save(self, tokens: Mapping[str, object]) -> Path:
        """Simpan token secara atomik dengan permission ketat bila didukung."""
        payload = dict(tokens)
        if not payload:
            raise GoogleAuthError("Token OAuth kosong tidak boleh disimpan.")
        # Path sudah absolut, tetapi cek ulang sebelum menulis agar perubahan
        # direktori kerja tidak pernah memindahkan token ke dalam repo.
        _require_outside_repository(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=self.path.parent,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                try:
                    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                except (TypeError, ValueError) as error:
                    raise GoogleAuthError(
                        f"Token OAuth tidak dapat diserialisasi: {self.path}: {error}"
                    ) from error
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            if os.name != "nt":
                temporary.chmod(0o600)
            os.replace(temporary, self.path)
            temporary = None
        except OSError as error:
            raise GoogleAuthError(
                f"Token OAuth tidak dapat disimpan: {self.path}: {error}"
            ) from error
        finally:
            if temporary is not None:
                with contextlib.suppress(OSError):
                    temporary.unlink(missing_ok=True)
        return self.path

    def clear(self) -> None:
        """Hapus token lokal bila ada; tidak menyentuh file remote."""
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            raise GoogleAuthError(
                f"Token OAuth tidak dapat dihapus: {self.path}: {error}"
            ) from error


def consent_parameters(
    state: str,
    *,
    scopes: tuple[str, ...] = SCOPES,
    code_challenge: str | None = None,
) -> dict[str, object]:
    """Parameter consent user flow: offline, prompt consent, scope lengkap."""
    if not state.strip():
        raise GoogleAuthError("State OAuth tidak boleh kosong.")
    parameters: dict[str, object] = {
        "scope": list(scopes),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": True,
    }
    if code_challenge is not None:
        if not code_challenge.strip():
            raise GoogleAuthError("PKCE code challenge tidak boleh kosong.")
        parameters["code_challenge"] = code_challenge
        parameters["code_challenge_method"] = "S256"
    return parameters


def create_flow(
    settings: OAuthSettings,
    *,
    scopes: tuple[str, ...] = SCOPES,
) -> OAuthFlow:
    """Buat flow OAuth installed-app dengan PKCE otomatis."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as error:  # pragma: no cover - extra google belum terpasang
        raise GoogleAuthError(
            "Extra 'google' belum terpasang; jalankan uv sync --extra google."
        ) from error
    flow = Flow.from_client_config(
        settings.client_config(),
        scopes=list(scopes),
        redirect_uri=settings.redirect_uri,
        autogenerate_code_verifier=True,
    )
    return cast("OAuthFlow", flow)


def begin_authorization(
    flow: OAuthFlow,
    *,
    state: str | None = None,
    scopes: tuple[str, ...] = SCOPES,
) -> AuthorizationRequest:
    """Bentuk URL consent dengan state acak dan parameter kontrak."""
    expected = secrets.token_urlsafe(32) if state is None else state
    parameters = consent_parameters(expected, scopes=scopes)
    url, returned_state = flow.authorization_url(**parameters)
    if returned_state and returned_state != expected:
        raise GoogleAuthError("Flow OAuth mengembalikan state yang berbeda dari permintaan.")
    return AuthorizationRequest(url=url, state=expected)


def build_consent_url(
    flow: OAuthFlow,
    *,
    state: str | None = None,
    scopes: tuple[str, ...] = SCOPES,
) -> str:
    """URL consent untuk flow tertentu."""
    return begin_authorization(flow, state=state, scopes=scopes).url


def exchange_code(
    flow: OAuthFlow,
    code: str,
    *,
    state: str | None = None,
    expected_state: str | None = None,
) -> object:
    """Tukar authorization code dan kembalikan credentials flow.

    Bila ``expected_state`` diberikan, ``state`` callback wajib cocok sebelum
    code ditukar.
    """
    if not code.strip():
        raise GoogleAuthError("Authorization code Google tidak boleh kosong.")
    if expected_state is not None and (
        state is None or not secrets.compare_digest(state, expected_state)
    ):
        raise GoogleAuthError("State OAuth callback tidak cocok dengan permintaan.")
    try:
        flow.fetch_token(code=code)
    except Exception as error:
        raise GoogleAuthError(f"Penukaran authorization code Google gagal: {error}") from error
    return flow.credentials


def credentials_to_dict(credentials: object) -> dict[str, object]:
    """Ubah credentials google-auth menjadi dict token JSON."""
    if not hasattr(credentials, "to_json"):
        raise GoogleAuthError("Credentials Google tidak dapat diserialisasi.")
    raw = cast("Any", credentials).to_json()
    if not isinstance(raw, str):
        raise GoogleAuthError("Credentials Google tidak menghasilkan JSON.")
    decoded: object = json.loads(raw)
    if not isinstance(decoded, Mapping):
        raise GoogleAuthError("Credentials Google tidak menghasilkan objek JSON.")
    return {str(key): value for key, value in cast("Mapping[object, object]", decoded).items()}


def load_credentials(
    settings: OAuthSettings | None,
    store: TokenStore,
    *,
    scopes: tuple[str, ...] = SCOPES,
) -> object:
    """Muat token, refresh bila kedaluwarsa, dan simpan token baru.

    ``settings`` opsional: token tersimpan sudah memuat client id/secret yang
    diperlukan untuk refresh, sehingga environment client hanya wajib untuk
    login interaktif.
    """
    del settings
    tokens = store.require()
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as error:  # pragma: no cover - extra google belum terpasang
        raise GoogleAuthError(
            "Extra 'google' belum terpasang; jalankan uv sync --extra google."
        ) from error
    credentials = Credentials.from_authorized_user_info(  # type: ignore[no-untyped-call]
        tokens, scopes=list(scopes)
    )
    if getattr(credentials, "expired", False):
        if not tokens.get("refresh_token"):
            raise GoogleAuthError(
                f"Token OAuth di {store.path} kedaluwarsa tanpa refresh token; login ulang."
            )
        try:
            credentials.refresh(Request())
        except Exception as error:
            raise GoogleAuthError(f"Refresh token Google gagal: {error}") from error
        store.save(credentials_to_dict(credentials))
    return credentials


def run_interactive_authorization(
    settings: OAuthSettings,
    store: TokenStore,
    *,
    scopes: tuple[str, ...] = SCOPES,
    open_browser: bool = True,
) -> object:
    """Jalankan consent user flow lewat browser lokal lalu simpan token.

    Parameter ``open_browser`` memudahkan environment tanpa browser; flow tetap
    mencetak URL consent dan menunggu callback lokal. Redirect URI kustom
    ditolak eksplisit karena ``run_local_server`` hanya menangani callback
    localhost; gunakan ``create_flow`` dan ``exchange_code`` untuk flow manual.
    """
    if settings.redirect_uri != DEFAULT_REDIRECT_URI:
        raise GoogleAuthError(
            "run_interactive_authorization hanya mendukung redirect URI default "
            f"{DEFAULT_REDIRECT_URI}; redirect kustom {settings.redirect_uri!r} "
            "harus memakai flow manual create_flow/exchange_code."
        )
    flow = create_flow(settings, scopes=scopes)
    concrete = cast("Any", flow)
    try:
        concrete.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
            include_granted_scopes=True,
            open_browser=open_browser,
        )
    except Exception as error:
        raise GoogleAuthError(f"OAuth user flow Google gagal: {error}") from error
    credentials = flow.credentials
    store.save(credentials_to_dict(credentials))
    return credentials


__all__ = [
    "CLIENT_ID_ENV",
    "CLIENT_SECRET_ENV",
    "DEFAULT_REDIRECT_URI",
    "REDIRECT_URI_ENV",
    "SCOPES",
    "TOKEN_PATH_ENV",
    "AuthorizationRequest",
    "OAuthFlow",
    "OAuthSettings",
    "TokenStore",
    "begin_authorization",
    "build_consent_url",
    "consent_parameters",
    "create_flow",
    "credentials_to_dict",
    "default_token_path",
    "exchange_code",
    "load_credentials",
    "run_interactive_authorization",
]
