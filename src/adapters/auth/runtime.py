from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from psycopg import OperationalError

from src.adapters.auth.clerk_auth import ClerkAuthConfig, ClerkAuthProvider
from src.adapters.persistence.postgres_user_repository import PostgresUserRepository
from src.application.auth import AuthenticateUserUseCase

CLERK_SESSION_COOKIE = "__session"
CLERK_SESSION_TOKEN_PARAM = "clerk_session_token"


def build_authenticate_user_use_case(
    auth_provider_cls: type[ClerkAuthProvider] = ClerkAuthProvider,
    user_repository_cls: type[PostgresUserRepository] = PostgresUserRepository,
) -> AuthenticateUserUseCase:
    publishable_key = os.getenv("CLERK_PUBLISHABLE_KEY")
    secret_key = os.getenv("CLERK_SECRET_KEY")
    database_url = os.getenv("DATABASE_URL")
    if not publishable_key:
        raise RuntimeError("CLERK_PUBLISHABLE_KEY is required for authentication.")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for authentication.")

    authorized_parties = tuple(
        item.strip() for item in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",") if item.strip()
    )
    auth_provider = auth_provider_cls(
        ClerkAuthConfig(
            publishable_key=publishable_key,
            secret_key=secret_key,
            frontend_api_url=os.getenv("CLERK_FRONTEND_API_URL"),
            jwks_url=os.getenv("CLERK_JWKS_URL"),
            issuer=os.getenv("CLERK_ISSUER"),
            authorized_parties=authorized_parties,
        )
    )
    users = user_repository_cls(database_url=database_url)
    try:
        users.ensure_schema()
    except OperationalError as exc:
        raise RuntimeError(
            "Authentication database is unavailable. Check DATABASE_URL. "
            "Railway internal hostnames such as 'postgres.railway.internal' only work inside Railway's private network."
        ) from exc
    return AuthenticateUserUseCase(auth_provider=auth_provider, users=users)


def derive_clerk_frontend_api_host(publishable_key: str) -> str:
    config = ClerkAuthConfig(publishable_key=publishable_key)
    return config.resolved_frontend_api_url.removeprefix("https://")


def get_app_base_url() -> str:
    return os.getenv("APP_BASE_URL") or os.getenv("PUBLIC_APP_URL") or "http://localhost:3000"


def get_configured_clerk_page_url(page: str) -> str | None:
    env_name = "CLERK_SIGN_IN_URL" if page == "sign-in" else "CLERK_SIGN_UP_URL"
    value = os.getenv(env_name, "").strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return with_redirect_url(value, get_app_base_url())
    return with_redirect_url(f"{get_app_base_url().rstrip('/')}/{value.lstrip('/')}", get_app_base_url())


def with_redirect_url(url: str, redirect_url: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("redirect_url", redirect_url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
