from __future__ import annotations

from datetime import date

import pandas as pd

from src.adapters.market_data.yfinance_provider import (
    YFinanceMarketDataAdapter,
    configure_yfinance_cache,
)


def test_configure_yfinance_cache_uses_default_location(monkeypatch, tmp_path) -> None:
    target = tmp_path / "yf-cache"
    monkeypatch.setenv("YFINANCE_TZ_CACHE_DIR", str(target))

    captured: list[str] = []

    def fake_set_tz_cache_location(path: str) -> None:
        captured.append(path)

    monkeypatch.setattr("src.adapters.market_data.yfinance_provider.yf.set_tz_cache_location", fake_set_tz_cache_location)

    configure_yfinance_cache()

    assert target.is_dir()
    assert captured == [str(target)]


def test_yfinance_adapter_returns_empty_frame_when_download_is_empty(monkeypatch) -> None:
    def fake_download(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["tickers"] == ["SPY"]
        return pd.DataFrame()

    monkeypatch.setattr("src.adapters.market_data.yfinance_provider.yf.download", fake_download)
    monkeypatch.setattr("src.adapters.market_data.yfinance_provider.yf.set_tz_cache_location", lambda path: None)

    adapter = YFinanceMarketDataAdapter()
    result = adapter.load_close_data(["SPY"], date(2024, 1, 1), date(2024, 1, 31))

    assert result.empty


def test_yfinance_adapter_handles_multiindex_and_single_symbol_downloads(monkeypatch) -> None:
    dates = pd.bdate_range("2024-01-01", periods=3)
    multi = pd.DataFrame(
        {
            ("Close", "SPY"): [1.0, 2.0, 3.0],
            ("Close", "QQQ"): [4.0, 5.0, 6.0],
        },
        index=dates,
    )
    single = pd.DataFrame({"Close": [10.0, None, 12.0]}, index=dates)
    responses = [multi, single]

    def fake_download(**kwargs):  # type: ignore[no-untyped-def]
        return responses.pop(0)

    monkeypatch.setattr("src.adapters.market_data.yfinance_provider.yf.download", fake_download)
    monkeypatch.setattr("src.adapters.market_data.yfinance_provider.yf.set_tz_cache_location", lambda path: None)

    adapter = YFinanceMarketDataAdapter()

    multi_result = adapter.load_close_data(["SPY", "QQQ"], date(2024, 1, 1), date(2024, 1, 31))
    assert list(multi_result.columns) == ["SPY", "QQQ"]
    assert multi_result.iloc[-1].to_dict() == {"SPY": 3.0, "QQQ": 6.0}

    single_result = adapter.load_close_data(["SPY"], date(2024, 1, 1), date(2024, 1, 31))
    assert list(single_result.columns) == ["SPY"]
    assert len(single_result) == 2
