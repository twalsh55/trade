from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import jwt
import pytest
from psycopg import OperationalError

from src.adapters.auth.clerk_auth import (
    AuthenticationError,
    ClerkAuthConfig,
    ClerkAuthProvider,
    _coerce_optional_string,
    _first_non_empty,
    _get_primary_email_from_profile,
)
from src.adapters.persistence import postgres_user_repository as repo_module
from src.adapters.persistence.postgres_user_repository import PostgresUserRepository
from src.adapters.ui import streamlit_dashboard as dashboard
from src.application.auth import AuthenticateUserUseCase
from src.domain.auth import ExternalIdentity, User


def make_identity() -> ExternalIdentity:
    return ExternalIdentity(
        provider="clerk",
        issuer="https://example.clerk.accounts.dev",
        subject="user_123",
        session_id="sess_123",
        email="user@example.com",
        given_name="Ada",
        family_name="Lovelace",
        display_name="Ada Lovelace",
    )


def make_user() -> User:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    return User(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        auth_provider="clerk",
        auth_issuer="https://example.clerk.accounts.dev",
        auth_subject="user_123",
        email="user@example.com",
        given_name="Ada",
        family_name="Lovelace",
        display_name="Ada Lovelace",
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


class FakeAuthProvider:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def authenticate_session_token(self, session_token: str) -> ExternalIdentity:
        self.tokens.append(session_token)
        return make_identity()


class FakeUserRepository:
    def __init__(self) -> None:
        self.identities: list[ExternalIdentity] = []

    def upsert_authenticated_user(self, identity: ExternalIdentity) -> User:
        self.identities.append(identity)
        return make_user()


def test_authenticate_user_use_case_returns_none_without_token() -> None:
    use_case = AuthenticateUserUseCase(auth_provider=FakeAuthProvider(), users=FakeUserRepository())

    assert use_case.execute(None) is None
    assert use_case.execute("") is None


def test_authenticate_user_use_case_maps_provider_identity_to_internal_user() -> None:
    auth_provider = FakeAuthProvider()
    users = FakeUserRepository()
    use_case = AuthenticateUserUseCase(auth_provider=auth_provider, users=users)

    user = use_case.execute("session-token")

    assert user == make_user()
    assert auth_provider.tokens == ["session-token"]
    assert users.identities == [make_identity()]


def test_clerk_auth_config_resolves_urls_from_explicit_values() -> None:
    config = ClerkAuthConfig(
        publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk",
        frontend_api_url="https://frontend.example/",
        jwks_url="https://jwks.example",
        issuer="https://issuer.example",
    )

    assert config.resolved_frontend_api_url == "https://frontend.example"
    assert config.resolved_jwks_url == "https://jwks.example"
    assert config.resolved_issuer == "https://issuer.example"


def test_clerk_auth_config_derives_urls_from_publishable_key() -> None:
    config = ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")

    assert config.resolved_frontend_api_url == "https://example.clerk.accounts.dev"
    assert config.resolved_jwks_url == "https://example.clerk.accounts.dev/.well-known/jwks.json"
    assert config.resolved_issuer is None


def test_clerk_auth_config_rejects_unparseable_publishable_key() -> None:
    config = ClerkAuthConfig(publishable_key="bad-key")

    with pytest.raises(AuthenticationError, match="Unable to derive"):
        _ = config.resolved_frontend_api_url


def test_clerk_auth_provider_authenticates_and_normalizes_profile(monkeypatch) -> None:
    claims = {
        "iss": "https://example.clerk.accounts.dev",
        "sub": "user_123",
        "sid": "sess_123",
        "given_name": "Claim Ada",
        "family_name": "Claim Lovelace",
    }
    profile = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "full_name": "Ada Lovelace",
        "primary_email_address_id": "email_123",
        "email_addresses": [{"id": "email_123", "email_address": "user@example.com"}],
    }

    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: None))
    provider = ClerkAuthProvider(ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"))
    monkeypatch.setattr(provider, "_verify_session_token", lambda token: claims)
    monkeypatch.setattr(provider, "_load_user_profile", lambda user_id: profile)

    identity = provider.authenticate_session_token("session-token")

    assert identity == ExternalIdentity(
        provider="clerk",
        issuer="https://example.clerk.accounts.dev",
        subject="user_123",
        session_id="sess_123",
        email="user@example.com",
        given_name="Ada",
        family_name="Lovelace",
        display_name="Ada Lovelace",
    )


def test_clerk_auth_provider_falls_back_to_claims_and_subject(monkeypatch) -> None:
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: None))
    provider = ClerkAuthProvider(ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"))
    monkeypatch.setattr(
        provider,
        "_verify_session_token",
        lambda token: {
            "iss": "https://example.clerk.accounts.dev",
            "sub": "user_123",
            "given_name": "Ada",
            "family_name": "Lovelace",
        },
    )
    monkeypatch.setattr(provider, "_load_user_profile", lambda user_id: {})

    identity = provider.authenticate_session_token("session-token")

    assert identity.email is None
    assert identity.display_name == "user_123"
    assert identity.given_name == "Ada"
    assert identity.family_name == "Lovelace"
    assert identity.session_id is None


def test_verify_session_token_rejects_invalid_header(monkeypatch) -> None:
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: None))
    provider = ClerkAuthProvider(ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"))
    monkeypatch.setattr(jwt, "get_unverified_header", lambda token: (_ for _ in ()).throw(jwt.PyJWTError("bad")))

    with pytest.raises(AuthenticationError, match="Invalid session token header"):
        provider._verify_session_token("session-token")


def test_verify_session_token_rejects_unexpected_algorithm(monkeypatch) -> None:
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: None))
    provider = ClerkAuthProvider(ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"))
    monkeypatch.setattr(jwt, "get_unverified_header", lambda token: {"alg": "HS256"})

    with pytest.raises(AuthenticationError, match="Unexpected session token signing algorithm"):
        provider._verify_session_token("session-token")


def test_verify_session_token_rejects_decode_errors(monkeypatch) -> None:
    signing_key = SimpleNamespace(key="public-key")
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: signing_key))
    provider = ClerkAuthProvider(ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"))
    monkeypatch.setattr(jwt, "get_unverified_header", lambda token: {"alg": "RS256"})
    monkeypatch.setattr(jwt, "decode", lambda *args, **kwargs: (_ for _ in ()).throw(jwt.PyJWTError("bad")))

    with pytest.raises(AuthenticationError, match="Session token verification failed"):
        provider._verify_session_token("session-token")


def test_verify_session_token_rejects_disallowed_authorized_party(monkeypatch) -> None:
    signing_key = SimpleNamespace(key="public-key")
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: signing_key))
    provider = ClerkAuthProvider(
        ClerkAuthConfig(
            publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk",
            authorized_parties=("https://allowed.example",),
        )
    )
    monkeypatch.setattr(jwt, "get_unverified_header", lambda token: {"alg": "RS256"})
    monkeypatch.setattr(
        jwt,
        "decode",
        lambda *args, **kwargs: {"iss": "https://example.clerk.accounts.dev", "sub": "user_123", "azp": "https://wrong.example"},
    )

    with pytest.raises(AuthenticationError, match="authorized party is not allowed"):
        provider._verify_session_token("session-token")


def test_verify_session_token_accepts_valid_claims(monkeypatch) -> None:
    signing_key = SimpleNamespace(key="public-key")
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: signing_key))
    provider = ClerkAuthProvider(
        ClerkAuthConfig(
            publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk",
            authorized_parties=("https://allowed.example",),
        )
    )
    monkeypatch.setattr(jwt, "get_unverified_header", lambda token: {"alg": "RS256"})
    monkeypatch.setattr(
        jwt,
        "decode",
        lambda *args, **kwargs: {"iss": "https://example.clerk.accounts.dev", "sub": "user_123", "azp": "https://allowed.example"},
    )

    claims = provider._verify_session_token("session-token")

    assert claims["sub"] == "user_123"


def test_verify_session_token_skips_issuer_validation_when_unconfigured(monkeypatch) -> None:
    captured_kwargs: dict[str, object] = {}
    signing_key = SimpleNamespace(key="public-key")
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: signing_key))
    provider = ClerkAuthProvider(ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"))
    monkeypatch.setattr(jwt, "get_unverified_header", lambda token: {"alg": "RS256"})

    def fake_decode(token, key, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return {"iss": "https://unexpected.example", "sub": "user_123"}

    monkeypatch.setattr(jwt, "decode", fake_decode)

    claims = provider._verify_session_token("session-token")

    assert claims["sub"] == "user_123"
    assert "issuer" not in captured_kwargs


def test_verify_session_token_passes_configured_issuer(monkeypatch) -> None:
    captured_kwargs: dict[str, object] = {}
    signing_key = SimpleNamespace(key="public-key")
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: signing_key))
    provider = ClerkAuthProvider(
        ClerkAuthConfig(
            publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk",
            issuer="https://issuer.example",
        )
    )
    monkeypatch.setattr(jwt, "get_unverified_header", lambda token: {"alg": "RS256"})

    def fake_decode(token, key, **kwargs):  # type: ignore[no-untyped-def]
        captured_kwargs.update(kwargs)
        return {"iss": "https://issuer.example", "sub": "user_123"}

    monkeypatch.setattr(jwt, "decode", fake_decode)

    claims = provider._verify_session_token("session-token")

    assert claims["sub"] == "user_123"
    assert captured_kwargs["issuer"] == "https://issuer.example"


def test_load_user_profile_handles_secretless_and_error_cases(monkeypatch) -> None:
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: None))
    provider = ClerkAuthProvider(ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"))
    assert provider._load_user_profile("user_123") == {}

    provider_with_secret = ClerkAuthProvider(
        ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk", secret_key="secret")
    )
    monkeypatch.setattr(repo_module, "connect", repo_module.connect)
    monkeypatch.setattr(
        dashboard,
        "st",
        SimpleNamespace(),
        raising=False,
    )
    monkeypatch.setattr(
        __import__("urllib.request").request,
        "urlopen",
        lambda request: (_ for _ in ()).throw(__import__("urllib.error").error.URLError("offline")),
    )
    assert provider_with_secret._load_user_profile("user_123") == {}


def test_load_user_profile_handles_json_and_shape_variants(monkeypatch) -> None:
    monkeypatch.setattr(jwt, "PyJWKClient", lambda url: SimpleNamespace(get_signing_key_from_jwt=lambda token: None))
    provider = ClerkAuthProvider(
        ClerkAuthConfig(publishable_key="pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk", secret_key="secret")
    )

    class FakeResponse:
        def __init__(self, payload: str) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
            return False

        def read(self) -> bytes:
            return self.payload.encode("utf-8")

    payloads = iter(["not-json", json.dumps(["not-a-dict"]), json.dumps({"id": "user_123"})])
    monkeypatch.setattr(
        __import__("urllib.request").request,
        "urlopen",
        lambda request: FakeResponse(next(payloads)),
    )

    assert provider._load_user_profile("user_123") == {}
    assert provider._load_user_profile("user_123") == {}
    assert provider._load_user_profile("user_123") == {"id": "user_123"}


def test_clerk_auth_helper_functions_cover_optional_paths() -> None:
    assert _coerce_optional_string("value") == "value"
    assert _coerce_optional_string("") is None
    assert _first_non_empty(None, "  ", " value ") == "value"
    assert _first_non_empty(None, "") is None
    assert _get_primary_email_from_profile({}) is None
    assert _get_primary_email_from_profile({"email_addresses": ["bad"]}) is None
    assert (
        _get_primary_email_from_profile(
            {
                "primary_email_address_id": "email_123",
                "email_addresses": [
                    {"id": "email_999", "email_address": "ignored@example.com"},
                    {"id": "email_123", "email_address": " user@example.com "},
                ],
            }
        )
        == "user@example.com"
    )


class FakeCursor:
    def __init__(self, fetchone_result=None) -> None:  # type: ignore[no-untyped-def]
        self.executed: list[tuple[str, object | None]] = []
        self.fetchone_result = fetchone_result

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    def execute(self, sql: str, params=None) -> None:  # type: ignore[no-untyped-def]
        self.executed.append((sql, params))

    def fetchone(self):  # type: ignore[no-untyped-def]
        return self.fetchone_result


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor
        self.commit_calls = 0

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commit_calls += 1


def test_postgres_user_repository_ensure_schema_executes_setup_sql(monkeypatch) -> None:
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: connection)

    repository = PostgresUserRepository("postgres://example")
    repository.ensure_schema()

    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in cursor.executed[0][0]
    assert "CREATE TABLE IF NOT EXISTS app_user" in cursor.executed[1][0]
    assert connection.commit_calls == 1


def test_postgres_user_repository_upserts_and_maps_internal_user(monkeypatch) -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "auth_provider": "clerk",
        "auth_issuer": "https://example.clerk.accounts.dev",
        "auth_subject": "user_123",
        "email": "user@example.com",
        "given_name": "Ada",
        "family_name": "Lovelace",
        "display_name": "Ada Lovelace",
        "created_at": now,
        "updated_at": now,
        "last_login_at": now,
    }
    cursor = FakeCursor(fetchone_result=row)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: connection)

    repository = PostgresUserRepository("postgres://example")
    user = repository.upsert_authenticated_user(make_identity())

    assert user.id == UUID("11111111-1111-1111-1111-111111111111")
    assert user.display_name == "Ada Lovelace"
    assert cursor.executed[0][1]["auth_subject"] == "user_123"
    assert connection.commit_calls == 1


def test_postgres_user_repository_raises_if_upsert_returns_no_row(monkeypatch) -> None:
    cursor = FakeCursor(fetchone_result=None)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: connection)

    repository = PostgresUserRepository("postgres://example")

    with pytest.raises(RuntimeError, match="did not return a row"):
        repository.upsert_authenticated_user(make_identity())


def test_postgres_user_repository_parse_and_optional_helpers() -> None:
    parsed = repo_module._parse_uuid("11111111-1111-1111-1111-111111111111")

    assert parsed == UUID("11111111-1111-1111-1111-111111111111")
    assert repo_module._parse_uuid(parsed) == parsed
    assert repo_module._optional_string("value") == "value"
    assert repo_module._optional_string(123) is None


def test_get_request_cookie_handles_missing_and_present_context(monkeypatch) -> None:
    monkeypatch.setattr(dashboard, "st", SimpleNamespace())
    assert dashboard.get_request_cookie("name") is None

    monkeypatch.setattr(dashboard, "st", SimpleNamespace(context=SimpleNamespace(cookies={"name": "value"})))
    assert dashboard.get_request_cookie("name") == "value"


def test_build_authenticate_user_use_case_requires_env(monkeypatch) -> None:
    dashboard.build_authenticate_user_use_case.cache_clear()
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="CLERK_PUBLISHABLE_KEY"):
        dashboard.build_authenticate_user_use_case()

    dashboard.build_authenticate_user_use_case.cache_clear()
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        dashboard.build_authenticate_user_use_case()


def test_build_authenticate_user_use_case_builds_and_initializes_repository(monkeypatch) -> None:
    dashboard.build_authenticate_user_use_case.cache_clear()
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")
    monkeypatch.setenv("CLERK_SECRET_KEY", "secret")
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    monkeypatch.setenv("CLERK_FRONTEND_API_URL", "https://frontend.example")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://jwks.example")
    monkeypatch.setenv("CLERK_ISSUER", "https://issuer.example")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://a.example, https://b.example")

    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, config: ClerkAuthConfig) -> None:
            captured["config"] = config

    class FakeUsers:
        def __init__(self, database_url: str) -> None:
            captured["database_url"] = database_url

        def ensure_schema(self) -> None:
            captured["ensure_schema"] = True

    monkeypatch.setattr(dashboard, "ClerkAuthProvider", FakeProvider)
    monkeypatch.setattr(dashboard, "PostgresUserRepository", FakeUsers)

    use_case = dashboard.build_authenticate_user_use_case()

    assert isinstance(use_case, AuthenticateUserUseCase)
    assert captured["database_url"] == "postgres://example"
    assert captured["ensure_schema"] is True
    assert captured["config"].authorized_parties == ("https://a.example", "https://b.example")


def test_build_authenticate_user_use_case_surfaces_database_connectivity_error(monkeypatch) -> None:
    dashboard.build_authenticate_user_use_case.cache_clear()
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")
    monkeypatch.setenv("DATABASE_URL", "postgres://example")

    class FakeUsers:
        def __init__(self, database_url: str) -> None:
            self.database_url = database_url

        def ensure_schema(self) -> None:
            raise OperationalError("dns failed")

    monkeypatch.setattr(dashboard, "PostgresUserRepository", FakeUsers)

    with pytest.raises(RuntimeError, match="Authentication database is unavailable"):
        dashboard.build_authenticate_user_use_case()


def test_get_current_user_reads_cookie_and_handles_authentication_error(monkeypatch) -> None:
    fake_st = SimpleNamespace(session_state={}, query_params={})
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "get_request_cookie", lambda name: "session-token")
    monkeypatch.setattr(dashboard, "get_query_param", lambda name: None)
    monkeypatch.setattr(
        dashboard,
        "build_authenticate_user_use_case",
        lambda: SimpleNamespace(execute=lambda token: make_user()),
    )

    assert dashboard.get_current_user() == make_user()
    assert fake_st.query_params == {}

    monkeypatch.setattr(
        dashboard,
        "build_authenticate_user_use_case",
        lambda: SimpleNamespace(execute=lambda token: (_ for _ in ()).throw(AuthenticationError("bad token"))),
    )
    assert dashboard.get_current_user() is None
    assert fake_st.session_state[dashboard.AUTH_ERROR_KEY] == "Authentication failed: bad token"

    monkeypatch.setattr(
        dashboard,
        "build_authenticate_user_use_case",
        lambda: (_ for _ in ()).throw(RuntimeError("missing config")),
    )
    assert dashboard.get_current_user() is None
    assert fake_st.session_state[dashboard.AUTH_ERROR_KEY] == "missing config"


def test_get_current_user_skips_bootstrap_without_session_cookie(monkeypatch) -> None:
    fake_st = SimpleNamespace(session_state={dashboard.AUTH_ERROR_KEY: "old error"}, query_params={})
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "get_request_cookie", lambda name: None)
    monkeypatch.setattr(dashboard, "get_query_param", lambda name: None)

    def fail() -> AuthenticateUserUseCase:
        raise AssertionError("should not build auth use case without a session cookie")

    monkeypatch.setattr(dashboard, "build_authenticate_user_use_case", fail)

    assert dashboard.get_current_user() is None
    assert dashboard.AUTH_ERROR_KEY not in fake_st.session_state


def test_get_current_user_prefers_query_param_token_and_clears_it(monkeypatch) -> None:
    fake_st = SimpleNamespace(session_state={}, query_params={dashboard.CLERK_SESSION_TOKEN_PARAM: "token-123"})
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "get_request_cookie", lambda name: "cookie-token")

    captured: list[str] = []
    monkeypatch.setattr(
        dashboard,
        "build_authenticate_user_use_case",
        lambda: SimpleNamespace(
            execute=lambda token: captured.append(token) or make_user()
        ),
    )

    assert dashboard.get_current_user() == make_user()
    assert captured == ["token-123"]
    assert dashboard.CLERK_SESSION_TOKEN_PARAM not in fake_st.query_params


def test_mount_clerk_auth_bridge_reads_session_token_from_component(monkeypatch) -> None:
    class FakeBridgeResult:
        session_token = "token-123"

    monkeypatch.setattr(dashboard, "get_clerk_auth_bridge", lambda: lambda **kwargs: FakeBridgeResult())

    assert dashboard.mount_clerk_auth_bridge("pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk", None) == "token-123"


def test_get_clerk_auth_bridge_registers_v2_component(monkeypatch) -> None:
    dashboard.get_clerk_auth_bridge.cache_clear()
    captured: dict[str, object] = {}

    def fake_component(name: str, **kwargs):  # type: ignore[no-untyped-def]
        captured["name"] = name
        captured.update(kwargs)
        return "bridge"

    monkeypatch.setattr(dashboard.components_v2, "component", fake_component)

    assert dashboard.get_clerk_auth_bridge() == "bridge"
    assert captured["name"] == "clerk_auth_bridge"
    assert captured["html"] == dashboard.CLERK_AUTH_BRIDGE_HTML
    assert captured["js"] == dashboard.CLERK_AUTH_BRIDGE_JS
    assert captured["css"] == dashboard.CLERK_AUTH_BRIDGE_CSS
    assert captured["isolate_styles"] is False


def test_get_image_data_uri_and_panel_html(tmp_path, monkeypatch) -> None:
    original_get_image_data_uri = dashboard.get_image_data_uri
    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(b"fake-png")
    logo_text_path = tmp_path / "logo_text.png"
    logo_text_path.write_bytes(b"fake-png-text")

    data_uri = original_get_image_data_uri(str(logo_path))

    assert data_uri is not None
    assert data_uri.startswith("data:image/png;base64,")
    text_data_uri = original_get_image_data_uri(str(logo_text_path))
    assert text_data_uri is not None

    monkeypatch.setattr(
        dashboard,
        "get_image_data_uri",
        lambda path: data_uri if path == "logo.png" else text_data_uri if path == "logo_text.png" else None,
    )
    html = dashboard.build_brivoly_auth_panel_html()
    assert "alt=\"Brivoly logo\"" in html
    assert dashboard.BRIVOLY_LOGO_IMAGE_PLACEHOLDER not in html
    assert dashboard.BRIVOLY_LOGO_TEXT_IMAGE_PLACEHOLDER not in html

    monkeypatch.setattr(dashboard, "get_image_data_uri", lambda path: data_uri if path == "logo.png" else None)
    symbol_only_html = dashboard.build_brivoly_auth_panel_html()
    assert "alt=\"Brivoly symbol\"" in symbol_only_html
    assert "alt=\"Brivoly logo\"" not in symbol_only_html

    monkeypatch.setattr(dashboard, "get_image_data_uri", lambda path: None)
    fallback_html = dashboard.build_brivoly_auth_panel_html()
    assert "Brivoly</div>" in fallback_html

    assert original_get_image_data_uri(str(tmp_path / "missing.png")) is None


def test_render_brivoly_auth_panel_mounts_component(monkeypatch) -> None:
    rendered: list[dict[str, object]] = []
    monkeypatch.setattr(dashboard, "build_brivoly_auth_panel_html", lambda: "<div>panel</div>")
    monkeypatch.setattr(
        dashboard,
        "get_html_block_renderer",
        lambda: lambda **kwargs: rendered.append(kwargs),
    )

    dashboard.render_brivoly_auth_panel()

    assert rendered == [{"data": {"html": "<div>panel</div>"}, "key": "brivoly_auth_panel"}]


def test_get_html_block_renderer_registers_v2_component(monkeypatch) -> None:
    dashboard.get_html_block_renderer.cache_clear()
    captured: dict[str, object] = {}

    def fake_component(name: str, **kwargs):  # type: ignore[no-untyped-def]
        captured["name"] = name
        captured.update(kwargs)
        return "html-block"

    monkeypatch.setattr(dashboard.components_v2, "component", fake_component)

    assert dashboard.get_html_block_renderer() == "html-block"
    assert captured["name"] == "trade_html_block"
    assert captured["html"] == dashboard.HTML_BLOCK_COMPONENT_HTML
    assert captured["js"] == dashboard.HTML_BLOCK_COMPONENT_JS
    assert captured["isolate_styles"] is False


def test_get_clerk_account_widget_registers_v2_component(monkeypatch) -> None:
    dashboard.get_clerk_account_widget.cache_clear()
    captured: dict[str, object] = {}

    def fake_component(name: str, **kwargs):  # type: ignore[no-untyped-def]
        captured["name"] = name
        captured.update(kwargs)
        return "widget"

    monkeypatch.setattr(dashboard.components_v2, "component", fake_component)

    assert dashboard.get_clerk_account_widget() == "widget"
    assert captured["name"] == "clerk_account_widget"
    assert captured["html"] == dashboard.CLERK_ACCOUNT_WIDGET_HTML
    assert captured["css"] == dashboard.CLERK_ACCOUNT_WIDGET_CSS
    assert captured["js"] == dashboard.CLERK_ACCOUNT_WIDGET_JS
    assert captured["isolate_styles"] is False


def test_render_auth_gate_requires_config_and_renders_clerk_component(monkeypatch) -> None:
    messages: list[str] = []
    bridge_calls: list[tuple[str, str | None]] = []
    brand_calls: list[str] = []
    monkeypatch.setattr(
        dashboard,
        "st",
        SimpleNamespace(
            markdown=lambda value: messages.append(value),
            caption=lambda value: messages.append(value),
            error=lambda value: messages.append(value),
        ),
    )
    monkeypatch.setattr(dashboard, "render_brivoly_auth_panel", lambda: brand_calls.append("panel"))
    monkeypatch.setattr(dashboard, "mount_clerk_auth_bridge", lambda publishable_key, auth_error: bridge_calls.append((publishable_key, auth_error)) or None)
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert dashboard.render_auth_gate() is None
    assert "Authentication is not configured. Set CLERK_PUBLISHABLE_KEY." in messages

    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")
    assert dashboard.render_auth_gate() is None

    assert "Authentication database is not configured. Set DATABASE_URL before completing sign-in." in messages
    assert any("Need self-service signup?" in message for message in messages)
    assert bridge_calls[0] == ("pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk", None)
    assert brand_calls == ["panel", "panel"]

    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    monkeypatch.setenv("CLERK_SIGN_UP_URL", "https://accounts.example.com/sign-up")
    assert dashboard.render_auth_gate() is None

    assert bridge_calls[1] == ("pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk", None)
    assert any("New to Brivoly?" in message for message in messages)
    assert any("Create an account" in message for message in messages)


def test_render_auth_gate_surfaces_bootstrap_error(monkeypatch) -> None:
    messages: list[str] = []
    bridge_calls: list[tuple[str, str | None]] = []
    brand_calls: list[str] = []
    monkeypatch.setattr(
        dashboard,
        "st",
        SimpleNamespace(
            session_state={dashboard.AUTH_ERROR_KEY: "database unavailable"},
            markdown=lambda value: messages.append(value),
            caption=lambda value: messages.append(value),
            error=lambda value: messages.append(value),
        ),
    )
    monkeypatch.setattr(dashboard, "render_brivoly_auth_panel", lambda: brand_calls.append("panel"))
    monkeypatch.setattr(dashboard, "mount_clerk_auth_bridge", lambda publishable_key, auth_error: bridge_calls.append((publishable_key, auth_error)) or None)
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")
    monkeypatch.setenv("DATABASE_URL", "postgres://example")

    assert dashboard.render_auth_gate() is None

    assert "database unavailable" in messages
    assert bridge_calls[0] == ("pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk", "database unavailable")
    assert brand_calls == ["panel"]


def test_render_account_widget_skips_without_key_and_renders_with_key(monkeypatch) -> None:
    mounted: list[dict[str, object]] = []
    monkeypatch.setattr(
        dashboard,
        "get_clerk_account_widget",
        lambda: lambda **kwargs: mounted.append(kwargs),
    )
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)

    dashboard.render_account_widget()
    assert mounted == []

    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")
    dashboard.render_account_widget()

    assert mounted[0]["key"] == "clerk_account_widget"
    assert mounted[0]["data"]["publishableKey"] == "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"
    assert mounted[0]["data"]["host"] == "example.clerk.accounts.dev"
