# Market Crash Monitor Dashboard

Python dashboard for monitoring market crash indicators and generating rule-based:
- de-risk suggestions during stress regimes
- buy-the-dip cues when pullbacks become statistically attractive

## Run

```bash
uv sync
uv run streamlit run main.py
```

## Ports and Adapters Structure

```text
src/
  domain/
    models.py       # entities, policies, thresholds
    services.py     # pure business logic for metrics/scoring/actions
  application/
    ports.py        # interfaces used by use-cases
    use_cases.py    # orchestration of the dashboard workflow
  adapters/
    market_data/
      yfinance_provider.py   # outbound adapter for market data
    ui/
      streamlit_dashboard.py # inbound adapter (Streamlit)
main.py              # composition root / entrypoint
```

### Boundaries

- Domain: no Streamlit or yfinance dependencies.
- Application: depends on domain + abstract port only.
- Adapters: implement ports and render UI.

## What It Tracks

- Trend stress: benchmark price vs. 200-day moving average
- Drawdown stress: benchmark drawdown from 252-day high
- Volatility stress: annualized 20-day realized volatility
- Momentum stress: RSI(14) on benchmark
- Breadth stress: share of the risk universe above 200-day moving average
- Yield-curve stress: long-short Treasury spread and inversion flag
- Optional fear/risk overlays: `^VIX` and a risk proxy like `HYG`

## Notes

- Signals are systematic heuristics, not guarantees.
- Intended for education/research, not financial advice.
