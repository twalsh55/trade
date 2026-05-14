from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID

from src.application.account import UserDashboardSettings
from src.domain.models import DEFAULT_UNIVERSE, DashboardConfig

DEFAULT_LOOKBACK_YEARS = 4
DEFAULT_BENCHMARK = "SPY"
DEFAULT_VIX_SYMBOL = "^VIX"
DEFAULT_RISK_PROXY = "HYG"
DEFAULT_SHORT_YIELD_SYMBOL = "^IRX"
DEFAULT_LONG_YIELD_SYMBOL = "^TNX"


def build_default_dashboard_settings(user_id: UUID, *, telegram_enabled: bool) -> UserDashboardSettings:
    return UserDashboardSettings(
        user_id=user_id,
        universe=list(DEFAULT_UNIVERSE),
        benchmark=DEFAULT_BENCHMARK,
        vix_symbol=DEFAULT_VIX_SYMBOL,
        risk_proxy=DEFAULT_RISK_PROXY,
        short_yield_symbol=DEFAULT_SHORT_YIELD_SYMBOL,
        long_yield_symbol=DEFAULT_LONG_YIELD_SYMBOL,
        lookback_years=DEFAULT_LOOKBACK_YEARS,
        telegram_enabled=telegram_enabled,
    )


def normalize_dashboard_settings(settings: UserDashboardSettings) -> UserDashboardSettings:
    return replace(
        settings,
        universe=_normalize_universe(settings.universe),
        benchmark=_normalize_symbol(settings.benchmark, DEFAULT_BENCHMARK),
        vix_symbol=_normalize_symbol(settings.vix_symbol, DEFAULT_VIX_SYMBOL),
        risk_proxy=_normalize_symbol(settings.risk_proxy, DEFAULT_RISK_PROXY),
        short_yield_symbol=_normalize_symbol(settings.short_yield_symbol, DEFAULT_SHORT_YIELD_SYMBOL),
        long_yield_symbol=_normalize_symbol(settings.long_yield_symbol, DEFAULT_LONG_YIELD_SYMBOL),
    )


def build_dashboard_config(settings: UserDashboardSettings, *, end_date: date) -> DashboardConfig:
    normalized = normalize_dashboard_settings(settings)
    return DashboardConfig(
        universe=list(normalized.universe),
        benchmark=normalized.benchmark,
        vix_symbol=normalized.vix_symbol,
        risk_proxy=normalized.risk_proxy,
        short_yield_symbol=normalized.short_yield_symbol,
        long_yield_symbol=normalized.long_yield_symbol,
        start_date=end_date - timedelta(days=365 * normalized.lookback_years),
        end_date=end_date,
    )


def _normalize_universe(universe: list[str]) -> list[str]:
    normalized = [_normalize_symbol(item, "") for item in universe]
    cleaned = [item for item in normalized if item]
    return cleaned or list(DEFAULT_UNIVERSE)


def _normalize_symbol(value: str, fallback: str) -> str:
    normalized = value.upper().strip()
    return normalized or fallback
