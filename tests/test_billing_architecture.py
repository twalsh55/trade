from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from src.adapters.billing import runtime
from src.adapters.billing import stripe_billing as stripe_module
from src.adapters.billing.stripe_billing import StripeBillingAdapter, _optional_unix_timestamp, _subscription_rank
from src.domain.auth import User


def make_user(*, stripe_customer_id: str | None = None, email: str | None = "user@example.com") -> User:
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    return User(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        auth_provider="clerk",
        auth_issuer="https://example.clerk.accounts.dev",
        auth_subject="user_123",
        stripe_customer_id=stripe_customer_id,
        email=email,
        given_name="Ada",
        family_name="Lovelace",
        display_name="Ada Lovelace",
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


class FakeUsers:
    def __init__(self) -> None:
        self.saved: list[tuple[UUID, str]] = []

    def set_stripe_customer_id(self, user_id: UUID, stripe_customer_id: str) -> None:
        self.saved.append((user_id, stripe_customer_id))


def test_build_billing_adapter_requires_env(monkeypatch) -> None:
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert runtime.build_billing_adapter() is None


def test_build_billing_adapter_constructs_stripe_adapter(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    monkeypatch.setenv("DATABASE_URL", "postgres://example")
    monkeypatch.setenv("APP_BASE_URL", "https://www.brivoly.com")
    monkeypatch.setenv("STRIPE_PORTAL_CONFIGURATION_ID", "bpc_123")

    class FakeRepository:
        def __init__(self, database_url: str) -> None:
            captured["database_url"] = database_url

    monkeypatch.setattr(runtime, "PostgresUserRepository", FakeRepository)

    adapter = runtime.build_billing_adapter()

    assert isinstance(adapter, StripeBillingAdapter)
    assert captured["database_url"] == "postgres://example"
    assert adapter.price_id == "price_123"
    assert adapter.portal_configuration_id == "bpc_123"


def test_stripe_billing_adapter_returns_checkout_ready_overview_without_customer(monkeypatch) -> None:
    users = FakeUsers()
    monkeypatch.setattr(stripe_module.stripe.Customer, "list", lambda **kwargs: {"data": []})
    adapter = StripeBillingAdapter(
        secret_key="sk_test_123",
        price_id="price_123",
        app_base_url="https://www.brivoly.com",
        users=users,
    )

    overview = adapter.get_billing_overview(make_user())

    assert overview.enabled is True
    assert overview.customer_id is None
    assert overview.checkout_available is True
    assert overview.portal_available is False
    assert users.saved == []


def test_stripe_billing_adapter_recovers_customer_and_subscription_from_stripe(monkeypatch) -> None:
    users = FakeUsers()
    monkeypatch.setattr(
        stripe_module.stripe.Customer,
        "list",
        lambda **kwargs: {"data": [{"id": "cus_123", "email": "user@example.com"}]},
    )
    monkeypatch.setattr(
        stripe_module.stripe.Subscription,
        "list",
        lambda **kwargs: {
            "data": [
                {
                    "id": "sub_123",
                    "status": "active",
                    "cancel_at_period_end": True,
                    "current_period_end": 1717200000,
                    "items": {"data": [{"price": {"id": "price_live"}}]},
                    "created": 2,
                }
            ]
        },
    )
    adapter = StripeBillingAdapter(
        secret_key="sk_test_123",
        price_id="price_123",
        app_base_url="https://www.brivoly.com",
        users=users,
    )

    overview = adapter.get_billing_overview(make_user())

    assert overview.customer_id == "cus_123"
    assert overview.subscription_id == "sub_123"
    assert overview.subscription_status == "active"
    assert overview.price_id == "price_live"
    assert overview.cancel_at_period_end is True
    assert overview.current_period_end == datetime.fromtimestamp(1717200000, tz=UTC)
    assert overview.checkout_available is False
    assert overview.portal_available is True
    assert users.saved == [(UUID("11111111-1111-1111-1111-111111111111"), "cus_123")]


def test_stripe_billing_adapter_handles_customer_without_subscription(monkeypatch) -> None:
    users = FakeUsers()
    monkeypatch.setattr(
        stripe_module.stripe.Customer,
        "list",
        lambda **kwargs: {"data": [{"id": "cus_123", "email": "user@example.com"}]},
    )
    monkeypatch.setattr(stripe_module.stripe.Subscription, "list", lambda **kwargs: {"data": []})
    adapter = StripeBillingAdapter(
        secret_key="sk_test_123",
        price_id="price_123",
        app_base_url="https://www.brivoly.com",
        users=users,
    )

    overview = adapter.get_billing_overview(make_user())

    assert overview.customer_id == "cus_123"
    assert overview.subscription_id is None
    assert overview.portal_available is True
    assert overview.checkout_available is True


def test_stripe_billing_adapter_creates_customer_and_checkout_session(monkeypatch) -> None:
    users = FakeUsers()
    monkeypatch.setattr(stripe_module.stripe.Customer, "list", lambda **kwargs: {"data": []})
    monkeypatch.setattr(
        stripe_module.stripe.Customer,
        "create",
        lambda **kwargs: {"id": "cus_new", **kwargs},
    )
    captured_session: dict[str, object] = {}

    def fake_checkout_create(**kwargs):  # type: ignore[no-untyped-def]
        captured_session.update(kwargs)
        return {"url": "https://checkout.stripe.test/session_123"}

    monkeypatch.setattr(stripe_module.stripe.checkout.Session, "create", fake_checkout_create)
    adapter = StripeBillingAdapter(
        secret_key="sk_test_123",
        price_id="price_123",
        app_base_url="https://www.brivoly.com",
        users=users,
    )

    url = adapter.create_checkout_session(make_user(), return_url="https://www.brivoly.com/account")

    assert url == "https://checkout.stripe.test/session_123"
    assert captured_session["success_url"] == "https://www.brivoly.com/account?checkout=success"
    assert captured_session["cancel_url"] == "https://www.brivoly.com/account?checkout=cancelled"
    assert users.saved == [(UUID("11111111-1111-1111-1111-111111111111"), "cus_new")]


def test_stripe_billing_adapter_creates_billing_portal_session(monkeypatch) -> None:
    users = FakeUsers()
    captured_portal: dict[str, object] = {}

    def fake_portal_create(**kwargs):  # type: ignore[no-untyped-def]
        captured_portal.update(kwargs)
        return {"url": "https://billing.stripe.test/session_123"}

    monkeypatch.setattr(stripe_module.stripe.billing_portal.Session, "create", fake_portal_create)
    adapter = StripeBillingAdapter(
        secret_key="sk_test_123",
        price_id="price_123",
        app_base_url="https://www.brivoly.com",
        users=users,
        portal_configuration_id="bpc_123",
    )

    url = adapter.create_portal_session(
        make_user(stripe_customer_id="cus_123"),
        return_url="https://www.brivoly.com/account",
    )

    assert url == "https://billing.stripe.test/session_123"
    assert captured_portal["customer"] == "cus_123"
    assert captured_portal["configuration"] == "bpc_123"
    assert captured_portal["return_url"] == "https://www.brivoly.com/account"


def test_stripe_billing_adapter_validates_missing_urls_and_chooses_subscription_priority(monkeypatch) -> None:
    users = FakeUsers()
    monkeypatch.setattr(stripe_module.stripe.Customer, "list", lambda **kwargs: {"data": []})
    monkeypatch.setattr(stripe_module.stripe.Customer, "create", lambda **kwargs: {"id": "cus_new"})
    monkeypatch.setattr(stripe_module.stripe.checkout.Session, "create", lambda **kwargs: {})
    monkeypatch.setattr(
        stripe_module.stripe.Subscription,
        "list",
        lambda **kwargs: {
            "data": [
                {"id": "sub_old", "status": "canceled", "created": 100},
                {"id": "sub_active", "status": "active", "created": 1},
            ]
        },
    )
    adapter = StripeBillingAdapter(
        secret_key="sk_test_123",
        price_id="price_123",
        app_base_url="https://www.brivoly.com?from=dashboard",
        users=users,
    )

    with pytest.raises(RuntimeError, match="redirect URL"):
        adapter.create_checkout_session(make_user())

    assert adapter._build_return_url("checkout=success") == "https://www.brivoly.com?from=dashboard&checkout=success"
    assert adapter._get_primary_subscription("cus_123")["id"] == "sub_active"
    assert _subscription_rank({"status": "active", "created": 5}) < _subscription_rank({"status": "canceled", "created": 10})
    assert _optional_unix_timestamp(None) is None


def test_stripe_billing_adapter_covers_remaining_error_and_shape_paths(monkeypatch) -> None:
    users = FakeUsers()
    adapter = StripeBillingAdapter(
        secret_key="sk_test_123",
        price_id="price_123",
        app_base_url="https://www.brivoly.com",
        users=users,
    )

    monkeypatch.setattr(stripe_module.stripe.billing_portal.Session, "create", lambda **kwargs: {})
    with pytest.raises(RuntimeError, match="redirect URL"):
        adapter.create_portal_session(make_user(stripe_customer_id="cus_123"))

    monkeypatch.setattr(stripe_module.stripe.Customer, "list", lambda **kwargs: {"data": []})
    monkeypatch.setattr(stripe_module.stripe.Customer, "create", lambda **kwargs: {})
    with pytest.raises(RuntimeError, match="customer id"):
        adapter.create_checkout_session(make_user(email=None))

    monkeypatch.setattr(stripe_module.stripe.Subscription, "list", lambda **kwargs: {"data": "bad"})
    assert adapter._get_primary_subscription("cus_123") is None

    assert adapter._extract_price_id({"items": []}) is None
    assert adapter._extract_price_id({"items": {"data": []}}) is None
    assert adapter._extract_price_id({"items": {"data": ["bad"]}}) is None
    assert adapter._extract_price_id({"items": {"data": [{"price": []}]}}) is None
