from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import yfinance as yf


class YFinanceMarketDataAdapter:
    def load_close_data(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
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
