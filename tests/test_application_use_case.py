from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

import pandas as pd

from src.application.crm import AddLeadFollowUpNoteUseCase, CompleteLeadFollowUpUseCase, SnoozeLeadFollowUpUseCase
from src.application.use_cases import BuildCrashDashboardUseCase
from src.domain.auth import User
from src.domain.models import DashboardConfig


class StubMarketData:
    def __init__(self, close: pd.DataFrame) -> None:
        self.close = close
        self.calls: list[tuple[list[str], date, date]] = []

    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        self.calls.append((tickers, start_date, end_date))
        return self.close


class StubLeadFollowUpRepository:
    def __init__(self) -> None:
        self.completed: list[tuple[str, datetime]] = []
        self.snoozed: list[tuple[str, datetime]] = []
        self.notes: list[tuple[str, str, datetime]] = []

    def list_lead_follow_ups(self, user: User):  # type: ignore[no-untyped-def]
        return []

    def complete_lead_follow_up(self, user: User, follow_up_id: str, completed_at: datetime) -> None:
        self.completed.append((follow_up_id, completed_at))

    def snooze_lead_follow_up(self, user: User, follow_up_id: str, next_follow_up_at: datetime) -> None:
        self.snoozed.append((follow_up_id, next_follow_up_at))

    def append_note_to_lead_follow_up(self, user: User, follow_up_id: str, note_body: str, noted_at: datetime) -> None:
        self.notes.append((follow_up_id, note_body, noted_at))


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


def test_use_case_executes_and_deduplicates_tickers() -> None:
    dates = pd.bdate_range("2020-01-01", periods=320)
    close = pd.DataFrame(
        {
            "SPY": range(320),
            "QQQ": range(100, 420),
            "^VIX": range(20, 340),
            "HYG": range(50, 370),
            "^IRX": range(60, 380),
            "^TNX": range(70, 390),
        },
        index=dates,
    ).astype(float)
    market_data = StubMarketData(close)
    use_case = BuildCrashDashboardUseCase(market_data=market_data)
    config = DashboardConfig(
        universe=["SPY", "QQQ", "SPY"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        start_date=date(2020, 1, 1),
        end_date=date(2021, 3, 31),
    )

    result = use_case.execute(config)

    tickers, start_date, end_date = market_data.calls[0]
    assert tickers == ["HYG", "QQQ", "SPY", "^IRX", "^TNX", "^VIX"]
    assert start_date == config.start_date
    assert end_date == config.end_date
    assert result.close_data.equals(close)
    assert result.metrics["price"] == float(close["SPY"].iloc[-1])
    assert result.regime
    assert result.actions


def test_use_case_raises_when_market_data_is_missing() -> None:
    market_data = StubMarketData(pd.DataFrame())
    use_case = BuildCrashDashboardUseCase(market_data=market_data)
    config = DashboardConfig(
        universe=["QQQ"],
        benchmark="SPY",
        vix_symbol="^VIX",
        risk_proxy="HYG",
        short_yield_symbol="^IRX",
        long_yield_symbol="^TNX",
        start_date=date(2020, 1, 1),
        end_date=date(2020, 12, 31),
    )

    try:
        use_case.execute(config)
    except ValueError as exc:
        assert str(exc) == "Could not load market data. Check ticker symbols or network connectivity."
    else:
        raise AssertionError("Expected missing data to raise ValueError")


def test_crm_follow_up_action_use_cases_delegate_with_expected_times() -> None:
    repository = StubLeadFollowUpRepository()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)
    user = make_user()

    complete = CompleteLeadFollowUpUseCase(repository=repository, now=lambda: now).execute(user, "lead-1")
    assert complete.follow_up_id == "lead-1"
    assert complete.action == "complete"
    assert repository.completed == [("lead-1", now)]

    snooze = SnoozeLeadFollowUpUseCase(repository=repository, now=lambda: now).execute(user, "lead-2", 24)
    assert snooze.follow_up_id == "lead-2"
    assert snooze.action == "snooze"
    assert repository.snoozed == [("lead-2", datetime(2024, 5, 7, 12, 30, tzinfo=UTC))]

    note = AddLeadFollowUpNoteUseCase(repository=repository, now=lambda: now).execute(user, "lead-3", "Need tighter rollout framing.")
    assert note.follow_up_id == "lead-3"
    assert note.action == "note"
    assert repository.notes == [("lead-3", "Need tighter rollout framing.", now)]


def test_add_lead_follow_up_note_requires_non_empty_body() -> None:
    repository = StubLeadFollowUpRepository()
    now = datetime(2024, 5, 6, 12, 30, tzinfo=UTC)

    try:
        AddLeadFollowUpNoteUseCase(repository=repository, now=lambda: now).execute(make_user(), "lead-1", "   ")
    except ValueError as exc:
        assert str(exc) == "Note body is required."
    else:
        raise AssertionError("Expected ValueError for empty note")
