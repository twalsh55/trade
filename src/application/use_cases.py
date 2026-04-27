from __future__ import annotations

from src.application.ports import MarketDataPort
from src.domain.models import DashboardConfig, DashboardResult
from src.domain.services import (
    compute_indicator_percentiles,
    compute_metrics,
    compute_risk_score,
    recommend_actions,
)


class BuildCrashDashboardUseCase:
    def __init__(self, market_data: MarketDataPort) -> None:
        self.market_data = market_data

    def execute(self, config: DashboardConfig) -> DashboardResult:
        tickers = sorted(
            set(
                config.universe
                + [
                    config.benchmark,
                    config.vix_symbol,
                    config.risk_proxy,
                    config.short_yield_symbol,
                    config.long_yield_symbol,
                ]
            )
        )
        close = self.market_data.load_close_data(tickers, config.start_date, config.end_date)
        if close.empty or config.benchmark not in close.columns:
            raise ValueError("Could not load market data. Check ticker symbols or network connectivity.")

        metrics = compute_metrics(
            close,
            config.benchmark,
            config.vix_symbol,
            config.risk_proxy,
            config.short_yield_symbol,
            config.long_yield_symbol,
        )
        indicator_percentiles = compute_indicator_percentiles(
            close,
            config.benchmark,
            config.vix_symbol,
            config.risk_proxy,
            config.short_yield_symbol,
            config.long_yield_symbol,
        )
        risk_score, components = compute_risk_score(metrics)
        regime, actions = recommend_actions(risk_score, metrics)
        return DashboardResult(
            close_data=close,
            metrics=metrics,
            indicator_percentiles=indicator_percentiles,
            risk_score=risk_score,
            risk_components=components,
            regime=regime,
            actions=actions,
        )
