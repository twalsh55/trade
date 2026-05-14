from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ExternalIdentity:
    provider: str
    issuer: str
    subject: str
    session_id: str | None
    email: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class User:
    id: UUID
    auth_provider: str
    auth_issuer: str
    auth_subject: str
    stripe_customer_id: str | None
    email: str | None
    given_name: str | None
    family_name: str | None
    display_name: str | None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime
