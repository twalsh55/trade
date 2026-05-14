from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from psycopg import connect
from psycopg.rows import dict_row

from src.domain.auth import ExternalIdentity, User


class PostgresUserRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def ensure_schema(self) -> None:
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE EXTENSION IF NOT EXISTS pgcrypto
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_user (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        auth_provider TEXT NOT NULL,
                        auth_issuer TEXT NOT NULL,
                        auth_subject TEXT NOT NULL,
                        stripe_customer_id TEXT,
                        email TEXT,
                        given_name TEXT,
                        family_name TEXT,
                        display_name TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_login_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (auth_provider, auth_subject)
                    )
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE app_user
                    ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT
                    """
                )
            connection.commit()

    def upsert_authenticated_user(self, identity: ExternalIdentity) -> User:
        now = datetime.now(UTC)
        with connect(self.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO app_user (
                        auth_provider,
                        auth_issuer,
                        auth_subject,
                        stripe_customer_id,
                        email,
                        given_name,
                        family_name,
                        display_name,
                        created_at,
                        updated_at,
                        last_login_at
                    )
                    VALUES (%(auth_provider)s, %(auth_issuer)s, %(auth_subject)s, %(stripe_customer_id)s, %(email)s, %(given_name)s, %(family_name)s, %(display_name)s, %(now)s, %(now)s, %(now)s)
                    ON CONFLICT (auth_provider, auth_subject) DO UPDATE
                    SET
                        auth_issuer = EXCLUDED.auth_issuer,
                        email = EXCLUDED.email,
                        given_name = EXCLUDED.given_name,
                        family_name = EXCLUDED.family_name,
                        display_name = EXCLUDED.display_name,
                        updated_at = EXCLUDED.updated_at,
                        last_login_at = EXCLUDED.last_login_at
                    RETURNING
                        id,
                        auth_provider,
                        auth_issuer,
                        auth_subject,
                        stripe_customer_id,
                        email,
                        given_name,
                        family_name,
                        display_name,
                        created_at,
                        updated_at,
                        last_login_at
                    """,
                    {
                        "auth_provider": identity.provider,
                        "auth_issuer": identity.issuer,
                        "auth_subject": identity.subject,
                        "stripe_customer_id": None,
                        "email": identity.email,
                        "given_name": identity.given_name,
                        "family_name": identity.family_name,
                        "display_name": identity.display_name,
                        "now": now,
                    },
                )
                row = cursor.fetchone()
            connection.commit()

        if row is None:
            raise RuntimeError("User upsert did not return a row.")

        return User(
            id=_parse_uuid(row["id"]),
            auth_provider=str(row["auth_provider"]),
            auth_issuer=str(row["auth_issuer"]),
            auth_subject=str(row["auth_subject"]),
            stripe_customer_id=_optional_string(row["stripe_customer_id"]),
            email=_optional_string(row["email"]),
            given_name=_optional_string(row["given_name"]),
            family_name=_optional_string(row["family_name"]),
            display_name=_optional_string(row["display_name"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login_at=row["last_login_at"],
        )

    def set_stripe_customer_id(self, user_id: UUID, stripe_customer_id: str) -> None:
        with connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE app_user
                    SET stripe_customer_id = %(stripe_customer_id)s,
                        updated_at = NOW()
                    WHERE id = %(user_id)s
                    """,
                    {"user_id": user_id, "stripe_customer_id": stripe_customer_id},
                )
            connection.commit()


def _parse_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
