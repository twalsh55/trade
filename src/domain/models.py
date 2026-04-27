from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


DEFAULT_UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM"]
RISK_OFF_CUTOFF = 70.0
CAUTION_CUTOFF = 50.0


@dataclass(frozen=True)
class DashboardConfig:
    universe: list[str]
    benchmark: str
    vix_symbol: str
    risk_proxy: str
    short_yield_symbol: str
    long_yield_symbol: str
    start_date: date
    end_date: date


@dataclass(frozen=True)
class DashboardResult:
    close_data: pd.DataFrame
    metrics: dict[str, float]
    indicator_percentiles: pd.DataFrame
    risk_score: float
    risk_components: dict[str, float]
    regime: str
    actions: list[str]
