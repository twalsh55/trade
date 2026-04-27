from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd


class MarketDataPort(Protocol):
    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Return close prices indexed by date with ticker columns."""
