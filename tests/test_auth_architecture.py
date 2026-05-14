from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import jwt
import pytest
from psycopg import OperationalError

from src.adapters.auth import runtime
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
        stripe_customer_id=None,
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

    assert identity == make_identity()


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
        lambda *args, **kwargs: {
            "iss": "https://example.clerk.accounts.dev",
            "sub": "user_123",
            "azp": "https://wrong.example",
        },
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
        lambda *args, **kwargs: {
            "iss": "https://example.clerk.accounts.dev",
            "sub": "user_123",
            "azp": "https://allowed.example",
            "exp": 1,
            "iat": 1,
            "nbf": 1,
        },
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
    assert "ADD COLUMN IF NOT EXISTS stripe_customer_id" in cursor.executed[2][0]
    assert connection.commit_calls == 1


def test_postgres_user_repository_upserts_and_maps_internal_user(monkeypatch) -> None:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "auth_provider": "clerk",
        "auth_issuer": "https://example.clerk.accounts.dev",
        "auth_subject": "user_123",
        "stripe_customer_id": "cus_123",
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
    assert user.stripe_customer_id == "cus_123"
    assert cursor.executed[0][1]["auth_subject"] == "user_123"
    assert cursor.executed[0][1]["stripe_customer_id"] is None
    assert connection.commit_calls == 1


def test_postgres_user_repository_updates_stripe_customer_id(monkeypatch) -> None:
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(repo_module, "connect", lambda *args, **kwargs: connection)

    repository = PostgresUserRepository("postgres://example")
    repository.set_stripe_customer_id(UUID("11111111-1111-1111-1111-111111111111"), "cus_123")

    assert "UPDATE app_user" in cursor.executed[0][0]
    assert cursor.executed[0][1]["stripe_customer_id"] == "cus_123"
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


def test_runtime_build_authenticate_user_use_case_requires_env(monkeypatch) -> None:
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="CLERK_PUBLISHABLE_KEY"):
        runtime.build_authenticate_user_use_case()

    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        runtime.build_authenticate_user_use_case()


def test_runtime_build_authenticate_user_use_case_builds_repository_and_provider(monkeypatch) -> None:
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

        def authenticate_session_token(self, session_token: str) -> ExternalIdentity:
            return make_identity()

    class FakeUsers:
        def __init__(self, database_url: str) -> None:
            captured["database_url"] = database_url

        def ensure_schema(self) -> None:
            captured["ensure_schema"] = True

        def upsert_authenticated_user(self, identity: ExternalIdentity) -> User:
            return make_user()

    use_case = runtime.build_authenticate_user_use_case(
        auth_provider_cls=FakeProvider,
        user_repository_cls=FakeUsers,
    )

    assert isinstance(use_case, AuthenticateUserUseCase)
    assert captured["database_url"] == "postgres://example"
    assert captured["ensure_schema"] is True
    assert captured["config"].authorized_parties == ("https://a.example", "https://b.example")


def test_runtime_build_authenticate_user_use_case_surfaces_database_connectivity_error(monkeypatch) -> None:
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk")
    monkeypatch.setenv("DATABASE_URL", "postgres://example")

    class FakeUsers:
        def __init__(self, database_url: str) -> None:
            self.database_url = database_url

        def ensure_schema(self) -> None:
            raise OperationalError("dns failed")

    with pytest.raises(RuntimeError, match="Authentication database is unavailable"):
        runtime.build_authenticate_user_use_case(user_repository_cls=FakeUsers)


def test_runtime_url_helpers(monkeypatch) -> None:
    publishable_key = "pk_test_ZXhhbXBsZS5jbGVyay5hY2NvdW50cy5kZXYk"
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("CLERK_SIGN_IN_URL", "https://accounts.example.com/sign-in")
    monkeypatch.setenv("CLERK_SIGN_UP_URL", "/sign-up")

    assert runtime.derive_clerk_frontend_api_host(publishable_key) == "example.clerk.accounts.dev"
    assert runtime.get_app_base_url() == "https://app.example.com"
    assert runtime.get_configured_clerk_page_url("sign-in") == (
        "https://accounts.example.com/sign-in?redirect_url=https%3A%2F%2Fapp.example.com"
    )
    assert runtime.get_configured_clerk_page_url("sign-up") == (
        "https://app.example.com/sign-up?redirect_url=https%3A%2F%2Fapp.example.com"
    )


def test_runtime_url_helpers_handle_fallbacks_and_preserve_existing_redirect(monkeypatch) -> None:
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("CLERK_SIGN_IN_URL", raising=False)
    monkeypatch.delenv("CLERK_SIGN_UP_URL", raising=False)

    assert runtime.get_app_base_url() == "http://localhost:3000"
    assert runtime.get_configured_clerk_page_url("sign-in") is None
    assert runtime.with_redirect_url(
        "https://accounts.example.com/sign-in?redirect_url=https%3A%2F%2Falready.example.com",
        "https://app.example.com",
    ) == "https://accounts.example.com/sign-in?redirect_url=https%3A%2F%2Falready.example.com"
    assert runtime.CLERK_SESSION_COOKIE == "__session"
    assert runtime.CLERK_SESSION_TOKEN_PARAM == "clerk_session_token"
