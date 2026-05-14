from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.ports import BillingPort
from src.domain.auth import User


@dataclass(frozen=True)
class BillingOverview:
    enabled: bool
    customer_id: str | None
    subscription_id: str | None
    subscription_status: str | None
    price_id: str | None
    cancel_at_period_end: bool
    current_period_end: datetime | None
    checkout_available: bool
    portal_available: bool


class GetBillingOverviewUseCase:
    def __init__(self, billing: BillingPort) -> None:
        self.billing = billing

    def execute(self, user: User) -> BillingOverview:
        return self.billing.get_billing_overview(user)


class CreateCheckoutSessionUseCase:
    def __init__(self, billing: BillingPort) -> None:
        self.billing = billing

    def execute(self, user: User, return_url: str | None = None) -> str:
        return self.billing.create_checkout_session(user, return_url=return_url)


class CreateBillingPortalSessionUseCase:
    def __init__(self, billing: BillingPort) -> None:
        self.billing = billing

    def execute(self, user: User, return_url: str | None = None) -> str:
        return self.billing.create_portal_session(user, return_url=return_url)
