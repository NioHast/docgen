"""Test OAuth scope, consent, dan token di luar repo."""

from pathlib import Path

import pytest

from autooffice.google import GoogleAuthError
from autooffice.google.auth import (
    SCOPES,
    OAuthSettings,
    TokenStore,
    begin_authorization,
    build_consent_url,
    consent_parameters,
    default_token_path,
)


class FakeFlow:
    """Flow OAuth minimal untuk memeriksa parameter consent tanpa jaringan."""

    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None
        self.code: str | None = None
        self._credentials = object()

    def authorization_url(self, **kwargs: object) -> tuple[str, str]:
        self.kwargs = kwargs
        state = str(kwargs["state"])
        return f"https://accounts.google.com/o/oauth2/auth?state={state}", state

    def fetch_token(self, code: str) -> None:
        self.code = code

    @property
    def credentials(self) -> object:
        return self._credentials


def test_scopes_are_exactly_the_user_flow_scopes() -> None:
    assert SCOPES == (
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/presentations",
        "https://www.googleapis.com/auth/spreadsheets",
    )


def test_consent_parameters_are_offline_and_explicit() -> None:
    parameters = consent_parameters("state-1")

    assert parameters["scope"] == list(SCOPES)
    assert parameters["state"] == "state-1"
    assert parameters["access_type"] == "offline"
    assert parameters["prompt"] == "consent"
    assert parameters["include_granted_scopes"] is True
    assert "code_challenge" not in parameters


def test_begin_authorization_passes_consent_shape_to_flow() -> None:
    flow = FakeFlow()

    request = begin_authorization(flow, state="state-abc")

    assert request.state == "state-abc"
    assert request.url.startswith("https://accounts.google.com/o/oauth2/auth")
    assert flow.kwargs is not None
    assert flow.kwargs["scope"] == list(SCOPES)
    assert flow.kwargs["state"] == "state-abc"
    assert flow.kwargs["access_type"] == "offline"
    assert flow.kwargs["prompt"] == "consent"


def test_build_consent_url_returns_url() -> None:
    flow = FakeFlow()

    url = build_consent_url(flow, state="state-2")

    assert "state=state-2" in url


def test_oauth_settings_reads_environment_without_default_secret() -> None:
    settings = OAuthSettings.from_environment(
        {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
        }
    )

    assert settings.client_id == "client-id"
    assert settings.redirect_uri.startswith("http://localhost")
    with pytest.raises(GoogleAuthError, match="GOOGLE_CLIENT_ID"):
        OAuthSettings.from_environment({})


def test_token_store_roundtrip_and_atomic_file(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "user" / "token.json")

    store.save({"access_token": "access", "refresh_token": "refresh"})

    loaded = store.load()
    assert loaded == {"access_token": "access", "refresh_token": "refresh"}
    assert not list(store.path.parent.glob("*.tmp"))


def test_default_token_path_is_outside_repository() -> None:
    path = default_token_path({"LOCALAPPDATA": "C:/Users/test/AppData/Local"})

    assert "autooffice" in path.parts
    assert path.name == "token.json"
    assert not any((parent / ".git").exists() for parent in path.parents)


def test_token_store_rejects_path_inside_repository(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    with pytest.raises(GoogleAuthError, match="di dalam repo"):
        TokenStore(tmp_path / "token.json")


def test_token_store_require_rejects_empty_token(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "token.json")
    store.save({"client_id": "only-client"})

    with pytest.raises(GoogleAuthError, match="access/refresh"):
        store.require()
