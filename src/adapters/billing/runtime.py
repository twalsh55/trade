from __future__ import annotations

import os

from src.adapters.billing.stripe_billing import StripeBillingAdapter
from src.adapters.persistence.postgres_user_repository import PostgresUserRepository


def build_billing_adapter() -> StripeBillingAdapter | None:
    secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    price_id = os.getenv("STRIPE_PRICE_ID", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not secret_key or not price_id or not database_url:
        return None

    return StripeBillingAdapter(
        secret_key=secret_key,
        price_id=price_id,
        app_base_url=os.getenv("APP_BASE_URL") or os.getenv("PUBLIC_APP_URL") or "http://localhost:3000",
        users=PostgresUserRepository(database_url=database_url),
        portal_configuration_id=os.getenv("STRIPE_PORTAL_CONFIGURATION_ID", "").strip() or None,
    )
