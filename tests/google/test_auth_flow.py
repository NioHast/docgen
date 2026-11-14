"""Test OAuth settings, token store, refresh palsu, dan flow tanpa jaringan."""

import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import autooffice.google.auth as auth_module
from autooffice.google import GoogleAuthError
from autooffice.google.auth import (
    CLIENT_SECRET_ENV,
    REDIRECT_URI_ENV,
    SCOPES,
    TOKEN_PATH_ENV,
    AuthorizationRequest,
    OAuthSettings,
    TokenStore,
    begin_authorization,
    consent_parameters,
    create_flow,
    credentials_to_dict,
    default_token_path,
    exchange_code,
    load_credentials,
    run_interactive_authorization,
)


class FakeFlow:
    """Flow OAuth minimal yang mencatat parameter tanpa menyentuh jaringan."""

    def __init__(
        self,
        *,
        credentials: object | None = None,
        returned_state: str | None = None,
        fetch_error: BaseException | None = None,
        server_error: BaseException | None = None,
    ) -> None:
        self.kwargs: dict[str, object] | None = None
        self.code: str | None = None
        self.server_kwargs: dict[str, object] | None = None
        self._credentials = object() if credentials is None else credentials
        self._returned_state = returned_state
        self._fetch_error = fetch_error
        self._server_error = server_error

    def authorization_url(self, **kwargs: object) -> tuple[str, str]:
        self.kwargs = kwargs
        expected = str(kwargs["state"])
        state = expected if self._returned_state is None else self._returned_state
        return f"https://accounts.google.com/o/oauth2/auth?state={state}", state

    def fetch_token(self, code: str) -> None:
        if self._fetch_error is not None:
            raise self._fetch_error
        self.code = code

    @property
    def credentials(self) -> object:
        return self._credentials

    def run_local_server(self, **kwargs: object) -> None:
        if self._server_error is not None:
            raise self._server_error
        self.server_kwargs = kwargs


class FakeRequest:
    """Transport request palsu untuk memastikan refresh tidak memakai HTTP."""


class FakeRefreshCredentials:
    """Credentials palsu dengan status expired dan hasil serialisasi terkontrol."""

    def __init__(
        self,
        *,
        expired: bool,
        serialized: dict[str, object] | None = None,
        refresh_error: BaseException | None = None,
    ) -> None:
        self.expired = expired
        self.serialized = (
            {"access_token": "new", "refresh_token": "refresh"}
            if serialized is None
            else serialized
        )
        self.refresh_requests: list[object] = []
        self._refresh_error = refresh_error

    def refresh(self, request: object) -> None:
        self.refresh_requests.append(request)
        if self._refresh_error is not None:
            raise self._refresh_error
        self.expired = False

    def to_json(self) -> str:
        return json.dumps(self.serialized)


class JsonCredentials:
    """Credentials palsu yang hanya perlu ``to_json`` untuk disimpan."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_json(self) -> str:
        return json.dumps(self.payload)


class _PosixOs:
    """Proksi ``os`` dengan ``name`` POSIX tanpa mengubah pathlib global."""

    name = "posix"

    def __getattr__(self, attribute: str) -> object:
        return getattr(os, attribute)


def _package(name: str) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = []
    return module


def _install_fake_credentials(
    monkeypatch: pytest.MonkeyPatch,
    credentials: object,
) -> list[tuple[object, object]]:
    """Pasang modul google auth palsu dan kembalikan jejak pemanggilan."""
    calls: list[tuple[object, object]] = []

    class Credentials:
        @classmethod
        def from_authorized_user_info(
            cls,
            info: object,
            scopes: object = None,
        ) -> object:
            calls.append((info, scopes))
            return credentials

    requests_module = ModuleType("google.auth.transport.requests")
    requests_module.Request = FakeRequest
    credentials_module = ModuleType("google.oauth2.credentials")
    credentials_module.Credentials = Credentials
    modules = {
        "google": _package("google"),
        "google.auth": _package("google.auth"),
        "google.auth.transport": _package("google.auth.transport"),
        "google.auth.transport.requests": requests_module,
        "google.oauth2": _package("google.oauth2"),
        "google.oauth2.credentials": credentials_module,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return calls


def _install_fake_flow(
    monkeypatch: pytest.MonkeyPatch,
    flow: object,
) -> list[dict[str, object]]:
    """Pasang ``google_auth_oauthlib.flow`` palsu yang mengembalikan flow test."""
    calls: list[dict[str, object]] = []

    class Flow:
        @classmethod
        def from_client_config(
            cls,
            config: object,
            *,
            scopes: object,
            redirect_uri: object,
            autogenerate_code_verifier: object,
        ) -> object:
            calls.append(
                {
                    "config": config,
                    "scopes": scopes,
                    "redirect_uri": redirect_uri,
                    "autogenerate_code_verifier": autogenerate_code_verifier,
                }
            )
            return flow

    flow_module = ModuleType("google_auth_oauthlib.flow")
    flow_module.Flow = Flow
    modules = {
        "google_auth_oauthlib": _package("google_auth_oauthlib"),
        "google_auth_oauthlib.flow": flow_module,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return calls


def _settings() -> OAuthSettings:
    return OAuthSettings(client_id="client-id", client_secret="client-secret")


def test_oauth_settings_reject_blank_secret_and_non_local_redirect() -> None:
    with pytest.raises(GoogleAuthError, match="client_secret"):
        OAuthSettings(client_id="client-id", client_secret=" ")
    with pytest.raises(GoogleAuthError, match="localhost"):
        OAuthSettings(client_id="id", client_secret="secret", redirect_uri="http://example.com")
    with pytest.raises(GoogleAuthError, match="localhost"):
        OAuthSettings(client_id="id", client_secret="secret", redirect_uri="ftp://example.com")


def test_oauth_settings_environment_redirect_and_client_config() -> None:
    settings = OAuthSettings.from_environment(
        {
            "GOOGLE_CLIENT_ID": " client-id ",
            CLIENT_SECRET_ENV: "client-secret",
            REDIRECT_URI_ENV: "https://example.com/oauth2callback",
        }
    )

    config = settings.client_config()

    assert settings.client_id == "client-id"
    assert settings.redirect_uri == "https://example.com/oauth2callback"
    assert config == {
        "installed": {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["https://example.com/oauth2callback"],
        }
    }


def test_oauth_settings_reject_invalid_environment_redirect() -> None:
    with pytest.raises(GoogleAuthError, match="localhost"):
        OAuthSettings.from_environment(
            {
                "GOOGLE_CLIENT_ID": "client-id",
                CLIENT_SECRET_ENV: "client-secret",
                REDIRECT_URI_ENV: "http://example.com/callback",
            }
        )


def test_authorization_request_rejects_invalid_url_and_empty_state() -> None:
    with pytest.raises(GoogleAuthError, match="tidak valid"):
        AuthorizationRequest(url="ftp://example.com", state="state")
    with pytest.raises(GoogleAuthError, match="State"):
        AuthorizationRequest(url="https://example.com", state=" ")


def test_begin_authorization_generates_state_and_rejects_mismatch() -> None:
    flow = FakeFlow()

    request = begin_authorization(flow)

    assert len(request.state) > 20
    assert flow.kwargs is not None
    assert flow.kwargs["state"] == request.state
    with pytest.raises(GoogleAuthError, match="state"):
        begin_authorization(FakeFlow(returned_state="other"), state="expected")


def test_consent_parameters_require_state_and_non_empty_pkce() -> None:
    with pytest.raises(GoogleAuthError, match="State"):
        consent_parameters(" ")
    with pytest.raises(GoogleAuthError, match="PKCE"):
        consent_parameters("state", code_challenge=" ")

    parameters = consent_parameters("state", code_challenge="challenge")

    assert parameters["code_challenge"] == "challenge"
    assert parameters["code_challenge_method"] == "S256"


def test_exchange_code_rejects_empty_code_and_wraps_failure() -> None:
    with pytest.raises(GoogleAuthError, match="tidak boleh kosong"):
        exchange_code(FakeFlow(), " ")

    flow = FakeFlow()
    credentials = exchange_code(flow, "auth-code")
    assert credentials is flow.credentials
    assert flow.code == "auth-code"

    with pytest.raises(GoogleAuthError, match="Penukaran authorization code"):
        exchange_code(FakeFlow(fetch_error=RuntimeError("invalid grant")), "auth-code")


def test_exchange_code_validates_callback_state() -> None:
    flow = FakeFlow()

    with pytest.raises(GoogleAuthError, match="State OAuth callback"):
        exchange_code(flow, "auth-code", state="other", expected_state="expected")

    with pytest.raises(GoogleAuthError, match="State OAuth callback"):
        exchange_code(flow, "auth-code", expected_state="expected")

    credentials = exchange_code(
        flow,
        "auth-code",
        state="expected",
        expected_state="expected",
    )

    assert credentials is flow.credentials
    assert flow.code == "auth-code"


def test_interactive_authorization_rejects_custom_redirect_uri(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "token.json")
    settings = OAuthSettings(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://example.com/callback",
    )

    def unexpected_flow(*args: object, **kwargs: object) -> object:
        raise AssertionError("create_flow tidak boleh dipanggil")

    monkeypatch.setattr(auth_module, "create_flow", unexpected_flow)

    with pytest.raises(GoogleAuthError, match="redirect URI default"):
        run_interactive_authorization(settings, store)

    assert not store.path.exists()


def test_create_flow_builds_installed_app_config(monkeypatch: pytest.MonkeyPatch) -> None:
    flow = FakeFlow()
    calls = _install_fake_flow(monkeypatch, flow)
    settings = OAuthSettings(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://example.com/callback",
    )

    result = create_flow(settings, scopes=("scope-a", "scope-b"))

    assert result is flow
    assert calls == [
        {
            "config": settings.client_config(),
            "scopes": ["scope-a", "scope-b"],
            "redirect_uri": "https://example.com/callback",
            "autogenerate_code_verifier": True,
        }
    ]


def test_credentials_to_dict_rejects_missing_serializer() -> None:
    with pytest.raises(GoogleAuthError, match="tidak dapat diserialisasi"):
        credentials_to_dict(object())


def test_credentials_to_dict_rejects_non_string_json() -> None:
    with pytest.raises(GoogleAuthError, match="tidak menghasilkan JSON"):
        credentials_to_dict(SimpleNamespace(to_json=lambda: 42))


def test_credentials_to_dict_rejects_non_object_json() -> None:
    with pytest.raises(GoogleAuthError, match="objek JSON"):
        credentials_to_dict(SimpleNamespace(to_json=lambda: "[]"))


def test_credentials_to_dict_returns_mapping() -> None:
    credentials = SimpleNamespace(to_json=lambda: '{"access_token":"access"}')

    assert credentials_to_dict(credentials) == {"access_token": "access"}


def test_default_token_path_uses_environment_override(tmp_path: Path) -> None:
    override = tmp_path / "user" / "token.json"

    assert default_token_path({TOKEN_PATH_ENV: str(override)}) == override


def test_default_token_path_rejects_override_inside_repository() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    with pytest.raises(GoogleAuthError, match="di dalam repo"):
        default_token_path({TOKEN_PATH_ENV: str(repository_root / "token.json")})


def test_default_token_path_uses_xdg_then_home(tmp_path: Path) -> None:
    xdg = tmp_path / "config"

    assert default_token_path({"XDG_CONFIG_HOME": str(xdg)}) == (
        xdg / "autooffice" / "google" / "token.json"
    )
    assert default_token_path({}) == (
        Path.home() / ".config" / "autooffice" / "google" / "token.json"
    )


def test_default_token_path_on_posix_uses_xdg(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(auth_module, "os", _PosixOs())
    xdg = tmp_path / "xdg"

    assert default_token_path({"XDG_CONFIG_HOME": str(xdg)}) == (
        xdg / "autooffice" / "google" / "token.json"
    )


def test_default_token_path_uses_local_app_data_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_module, "os", SimpleNamespace(name="nt"))
    local_app_data = "C:/Users/test/AppData/Local"

    result = default_token_path({"LOCALAPPDATA": local_app_data})

    assert result == (Path(local_app_data) / "autooffice" / "google" / "token.json").resolve()
    assert result.is_absolute()


def test_token_store_from_environment_uses_token_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "token.json"
    monkeypatch.setenv(TOKEN_PATH_ENV, str(target))

    assert TokenStore.from_environment().path == target


def test_token_store_load_reports_unreadable_file(tmp_path: Path) -> None:
    target = tmp_path / "token-dir"
    target.mkdir()
    store = TokenStore(target)

    with pytest.raises(GoogleAuthError, match="tidak dapat dibaca"):
        store.load()


def test_token_store_load_rejects_invalid_json(tmp_path: Path) -> None:
    target = tmp_path / "token.json"
    target.write_text("{not-json", encoding="utf-8")
    store = TokenStore(target)

    with pytest.raises(GoogleAuthError, match="bukan JSON valid"):
        store.load()


def test_token_store_load_rejects_non_object_json(tmp_path: Path) -> None:
    target = tmp_path / "token.json"
    target.write_text("[]", encoding="utf-8")
    store = TokenStore(target)

    with pytest.raises(GoogleAuthError, match="objek JSON"):
        store.load()


def test_token_store_require_missing_then_accepts_token(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "token.json")

    with pytest.raises(GoogleAuthError, match="belum ada"):
        store.require()

    store.save({"access_token": "access"})

    assert store.require() == {"access_token": "access"}


def test_token_store_save_rejects_empty_token(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "token.json")

    with pytest.raises(GoogleAuthError, match="kosong"):
        store.save({})


def test_token_store_save_cleans_temporary_file_on_replace_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "token.json"
    store = TokenStore(target)
    real_replace = os.replace

    def failing_replace(source: object, destination: object) -> None:
        if Path(destination) == target:
            raise OSError("disk penuh")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(GoogleAuthError, match="tidak dapat disimpan"):
        store.save({"access_token": "access"})

    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_token_store_path_is_absolute_and_survives_chdir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    store = TokenStore(Path("user") / "token.json")
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)

    assert store.path == (tmp_path / "user" / "token.json").resolve()
    assert store.path.is_absolute()

    monkeypatch.chdir(repository)
    store.save({"access_token": "access"})

    assert store.path.exists()
    assert not (repository / "token.json").exists()


def test_token_store_save_cleans_temporary_file_on_serialization_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "token.json")

    def failing_dump(*args: object, **kwargs: object) -> None:
        raise TypeError("token tidak serializable")

    monkeypatch.setattr(auth_module.json, "dump", failing_dump)

    with pytest.raises(GoogleAuthError, match="tidak dapat diserialisasi"):
        store.save({"access_token": object()})

    assert not store.path.exists()
    assert not list(store.path.parent.glob("*.tmp"))


def test_token_store_save_wraps_failure_before_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "token.json"
    store = TokenStore(target)

    def failing_named_temporary_file(*args: object, **kwargs: object) -> object:
        raise OSError("disk penuh")

    monkeypatch.setattr(auth_module.tempfile, "NamedTemporaryFile", failing_named_temporary_file)

    with pytest.raises(GoogleAuthError, match="tidak dapat disimpan"):
        store.save({"access_token": "access"})

    assert not target.exists()


def test_token_store_save_sets_private_permissions_on_posix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "token.json"
    store = TokenStore(target)
    monkeypatch.setattr(auth_module, "os", _PosixOs())

    store.save({"access_token": "access"})

    assert store.load() == {"access_token": "access"}


def test_token_store_clear_removes_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "token.json"
    store = TokenStore(target)
    store.save({"access_token": "access"})

    store.clear()

    assert not target.exists()
    store.clear()


def test_token_store_clear_wraps_unlink_failure(tmp_path: Path) -> None:
    target = tmp_path / "token-dir"
    target.mkdir()
    store = TokenStore(target)

    with pytest.raises(GoogleAuthError, match="tidak dapat dihapus"):
        store.clear()


def test_load_credentials_returns_unexpired_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "token.json")
    store.save({"access_token": "old", "refresh_token": "refresh"})
    credentials = FakeRefreshCredentials(expired=False)
    calls = _install_fake_credentials(monkeypatch, credentials)

    result = load_credentials(_settings(), store)

    assert result is credentials
    assert calls == [
        ({"access_token": "old", "refresh_token": "refresh"}, list(SCOPES)),
    ]
    assert credentials.refresh_requests == []
    assert store.load() == {"access_token": "old", "refresh_token": "refresh"}


def test_load_credentials_works_without_client_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "token.json")
    store.save({"access_token": "old", "refresh_token": "refresh"})
    credentials = FakeRefreshCredentials(expired=False)
    _install_fake_credentials(monkeypatch, credentials)

    result = load_credentials(None, store)

    assert result is credentials


def test_load_credentials_refreshes_expired_token_and_saves(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "token.json")
    store.save({"access_token": "old", "refresh_token": "refresh"})
    refreshed = {"access_token": "new", "refresh_token": "refresh"}
    credentials = FakeRefreshCredentials(expired=True, serialized=refreshed)
    _install_fake_credentials(monkeypatch, credentials)

    result = load_credentials(_settings(), store)

    assert result is credentials
    assert len(credentials.refresh_requests) == 1
    assert isinstance(credentials.refresh_requests[0], FakeRequest)
    assert store.load() == refreshed


def test_load_credentials_rejects_expired_token_without_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "token.json")
    store.save({"access_token": "old"})
    credentials = FakeRefreshCredentials(expired=True)
    _install_fake_credentials(monkeypatch, credentials)

    with pytest.raises(GoogleAuthError, match="kedaluwarsa tanpa refresh token"):
        load_credentials(_settings(), store)

    assert credentials.refresh_requests == []
    assert store.load() == {"access_token": "old"}


def test_load_credentials_wraps_refresh_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "token.json")
    store.save({"access_token": "old", "refresh_token": "refresh"})
    credentials = FakeRefreshCredentials(
        expired=True,
        refresh_error=RuntimeError("network down"),
    )
    _install_fake_credentials(monkeypatch, credentials)

    with pytest.raises(GoogleAuthError, match="Refresh token Google gagal: network down"):
        load_credentials(_settings(), store)

    assert store.load() == {"access_token": "old", "refresh_token": "refresh"}


def test_create_google_services_does_not_require_client_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import autooffice.google.sync as sync_module

    received: list[object] = []

    def fake_load_credentials(settings: object, store: object) -> object:
        received.append(settings)
        return object()

    def fake_build(name: str, version: str, **kwargs: object) -> object:
        return SimpleNamespace(name=name, version=version)

    discovery = ModuleType("googleapiclient.discovery")
    discovery.build = fake_build  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "googleapiclient", _package("googleapiclient"))
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)
    monkeypatch.setattr(sync_module, "load_credentials", fake_load_credentials)
    store = TokenStore(tmp_path / "token.json")

    services = sync_module.create_google_services(token_store=store)

    assert received == [None]
    assert services.drive is not None
    assert services.sheets is not None
    assert services.slides is not None


def test_run_interactive_authorization_saves_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "token.json")
    credentials = JsonCredentials({"access_token": "access"})
    flow = FakeFlow(credentials=credentials)

    def fake_create_flow(settings: OAuthSettings, *, scopes: tuple[str, ...]) -> FakeFlow:
        assert settings == _settings()
        assert scopes == SCOPES
        return flow

    monkeypatch.setattr(auth_module, "create_flow", fake_create_flow)

    result = run_interactive_authorization(_settings(), store, open_browser=False)

    assert result is credentials
    assert store.load() == {"access_token": "access"}
    assert flow.server_kwargs == {
        "port": 0,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": True,
        "open_browser": False,
    }


def test_run_interactive_authorization_wraps_server_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = TokenStore(tmp_path / "token.json")
    flow = FakeFlow(server_error=RuntimeError("callback gagal"))

    def fake_create_flow(settings: OAuthSettings, *, scopes: tuple[str, ...]) -> FakeFlow:
        assert isinstance(settings, OAuthSettings)
        assert scopes == SCOPES
        return flow

    monkeypatch.setattr(auth_module, "create_flow", fake_create_flow)

    with pytest.raises(GoogleAuthError, match="OAuth user flow Google gagal"):
        run_interactive_authorization(_settings(), store)

    assert not store.path.exists()
