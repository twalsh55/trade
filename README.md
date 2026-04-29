# Market Crash Monitor Dashboard

Python dashboard for monitoring market crash indicators and generating rule-based:
- de-risk suggestions during stress regimes
- buy-the-dip cues when pullbacks become statistically attractive

## Run

```bash
uv sync
uv run streamlit run main.py
```

## Authentication

The app now authenticates users through an auth-provider adapter and stores its own internal user records in Postgres.

Required environment variables:

```bash
CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

Optional Clerk variables:

```bash
CLERK_SECRET_KEY=your_clerk_secret_key
CLERK_FRONTEND_API_URL=https://your-instance.clerk.accounts.dev
CLERK_JWKS_URL=https://your-instance.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://your-instance.clerk.accounts.dev
CLERK_AUTHORIZED_PARTIES=https://your-app.example.com,http://localhost:8501
CLERK_SIGN_IN_URL=https://your-account-portal-domain/sign-in
CLERK_SIGN_UP_URL=https://your-account-portal-domain/sign-up
APP_BASE_URL=http://localhost:8501
```

Notes:
- The dashboard uses Clerk's signed session token and validates it with JWKS.
- The app keeps its own `app_user` table in Postgres with an internal UUID primary key.
- Clerk is isolated behind an application auth port so a future migration can swap adapters without rewriting the dashboard or domain logic.
- For hosted Account Portal links, use the exact URLs shown in Clerk Dashboard > Account Portal > Pages instead of trying to derive them from the publishable key.
- Hosted sign-in and sign-up links should redirect back to `APP_BASE_URL`, so set that to your real local or deployed app URL.

## Deploy on Railway

This repo includes a `Dockerfile` and `railway.toml` for Railway deployment.

Railway setup:
```bash
railway up
```

Container behavior:
- installs dependencies with `uv sync --frozen`
- starts Streamlit directly on `0.0.0.0:$PORT`
- serves `GET /_stcore/health` for Railway healthchecks
- disables CORS/XSRF protections for proxy compatibility

Set these Railway environment variables if you want Telegram alerts:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Telegram Alerts

Create a local `.env` file or export these before running if you want Telegram messages when the dashboard produces an actionable alert:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Alerts are sent once per distinct signal and will re-send only when the regime/actions change.

To discover your `TELEGRAM_CHAT_ID` after messaging the bot:

```bash
uv run python scripts/get_telegram_chat_id.py
```

To test whether your bot token and chat ID can send successfully:

```bash
uv run python scripts/test_telegram_send.py
```

## Ports and Adapters Structure

```text
src/
  domain/
    auth.py         # provider-agnostic identity and internal user models
    models.py       # entities, policies, thresholds
    services.py     # pure business logic for metrics/scoring/actions
  application/
    ports.py        # interfaces used by use-cases
    auth.py         # authentication use-case
    use_cases.py    # orchestration of the dashboard workflow
  adapters/
    auth/
      clerk_auth.py             # Clerk JWT verification + profile lookup adapter
    market_data/
      yfinance_provider.py   # outbound adapter for market data
    persistence/
      postgres_user_repository.py # Postgres user persistence adapter
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
