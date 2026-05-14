from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import stripe

from src.application.billing import BillingOverview
from src.domain.auth import User

ACTIVE_BILLING_STATUSES = ("active", "trialing", "past_due", "paused", "unpaid", "incomplete")


class StripeBillingAdapter:
    def __init__(
        self,
        *,
        secret_key: str,
        price_id: str,
        app_base_url: str,
        users: Any,
        portal_configuration_id: str | None = None,
    ) -> None:
        self.secret_key = secret_key
        self.price_id = price_id
        self.app_base_url = app_base_url.rstrip("/")
        self.users = users
        self.portal_configuration_id = portal_configuration_id

    def get_billing_overview(self, user: User) -> BillingOverview:
        customer_id = self._resolve_customer_id(user)
        if not customer_id:
            return BillingOverview(
                enabled=True,
                customer_id=None,
                subscription_id=None,
                subscription_status=None,
                price_id=self.price_id,
                cancel_at_period_end=False,
                current_period_end=None,
                checkout_available=True,
                portal_available=False,
            )

        subscription = self._get_primary_subscription(customer_id)
        if subscription is None:
            return BillingOverview(
                enabled=True,
                customer_id=customer_id,
                subscription_id=None,
                subscription_status=None,
                price_id=self.price_id,
                cancel_at_period_end=False,
                current_period_end=None,
                checkout_available=True,
                portal_available=True,
            )

        price_id = self._extract_price_id(subscription) or self.price_id
        return BillingOverview(
            enabled=True,
            customer_id=customer_id,
            subscription_id=subscription.get("id"),
            subscription_status=subscription.get("status"),
            price_id=price_id,
            cancel_at_period_end=bool(subscription.get("cancel_at_period_end")),
            current_period_end=_optional_unix_timestamp(subscription.get("current_period_end")),
            checkout_available=subscription.get("status") not in ACTIVE_BILLING_STATUSES,
            portal_available=True,
        )

    def create_checkout_session(self, user: User, return_url: str | None = None) -> str:
        customer_id = self._ensure_customer(user)
        stripe.api_key = self.secret_key
        base_url = return_url or self.app_base_url
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=str(user.id),
            line_items=[{"price": self.price_id, "quantity": 1}],
            allow_promotion_codes=True,
            success_url=self._build_return_url("checkout=success", base_url=base_url),
            cancel_url=self._build_return_url("checkout=cancelled", base_url=base_url),
            metadata={"app_user_id": str(user.id), "auth_subject": user.auth_subject},
        )
        url = session.get("url")
        if not isinstance(url, str) or not url:
            raise RuntimeError("Stripe Checkout did not return a redirect URL.")
        return url

    def create_portal_session(self, user: User, return_url: str | None = None) -> str:
        customer_id = self._ensure_customer(user)
        stripe.api_key = self.secret_key
        payload: dict[str, object] = {
            "customer": customer_id,
            "return_url": return_url or self._build_return_url("billing=return"),
        }
        if self.portal_configuration_id:
            payload["configuration"] = self.portal_configuration_id
        session = stripe.billing_portal.Session.create(**payload)
        url = session.get("url")
        if not isinstance(url, str) or not url:
            raise RuntimeError("Stripe Billing Portal did not return a redirect URL.")
        return url

    def _resolve_customer_id(self, user: User) -> str | None:
        if user.stripe_customer_id:
            return user.stripe_customer_id
        stripe.api_key = self.secret_key
        if user.email:
            customers = stripe.Customer.list(email=user.email, limit=10)
            for customer in customers.get("data", []):
                if customer.get("email") == user.email:
                    customer_id = customer.get("id")
                    if isinstance(customer_id, str) and customer_id:
                        self.users.set_stripe_customer_id(user.id, customer_id)
                        return customer_id
        return None

    def _ensure_customer(self, user: User) -> str:
        customer_id = self._resolve_customer_id(user)
        if customer_id:
            return customer_id

        stripe.api_key = self.secret_key
        customer = stripe.Customer.create(
            email=user.email,
            name=user.display_name or user.email or user.auth_subject,
            metadata={"app_user_id": str(user.id), "auth_subject": user.auth_subject},
        )
        customer_id = customer.get("id")
        if not isinstance(customer_id, str) or not customer_id:
            raise RuntimeError("Stripe customer creation did not return a customer id.")
        self.users.set_stripe_customer_id(user.id, customer_id)
        return customer_id

    def _get_primary_subscription(self, customer_id: str) -> dict[str, Any] | None:
        stripe.api_key = self.secret_key
        subscriptions = stripe.Subscription.list(customer=customer_id, status="all", limit=10)
        data = subscriptions.get("data", [])
        if not isinstance(data, list):
            return None
        prioritized = sorted(data, key=_subscription_rank)
        return prioritized[0] if prioritized else None

    def _extract_price_id(self, subscription: dict[str, Any]) -> str | None:
        items = subscription.get("items", {})
        if not isinstance(items, dict):
            return None
        data = items.get("data", [])
        if not isinstance(data, list) or not data:
            return None
        first = data[0]
        if not isinstance(first, dict):
            return None
        price = first.get("price", {})
        if not isinstance(price, dict):
            return None
        price_id = price.get("id")
        return price_id if isinstance(price_id, str) else None

    def _build_return_url(self, query: str, base_url: str | None = None) -> str:
        target = (base_url or self.app_base_url).rstrip("/")
        joiner = "&" if "?" in target else "?"
        return f"{target}{joiner}{query}"


def _optional_unix_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


def _subscription_rank(subscription: dict[str, Any]) -> tuple[int, int]:
    status = subscription.get("status")
    if isinstance(status, str) and status in ACTIVE_BILLING_STATUSES:
        priority = ACTIVE_BILLING_STATUSES.index(status)
    else:
        priority = len(ACTIVE_BILLING_STATUSES)
    created = int(subscription.get("created") or 0)
    return (priority, -created)
