from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

DEFAULT_TZ_CACHE_DIR = "/tmp/py-yfinance-cache"


def configure_yfinance_cache() -> None:
    cache_dir = Path(os.getenv("YFINANCE_TZ_CACHE_DIR", DEFAULT_TZ_CACHE_DIR))
    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir))


class YFinanceMarketDataAdapter:
    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        configure_yfinance_cache()
        data = yf.download(
            tickers=tickers,
            start=start_date,
            end=end_date + timedelta(days=1),
            auto_adjust=True,
            progress=False,
        )
        if data.empty:
            return pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"].copy()
        else:
            close = data.rename(columns={"Close": tickers[0] if len(tickers) == 1 else "Close"})

        return close.dropna(how="all")
