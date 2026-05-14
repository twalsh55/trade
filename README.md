# Trade

Trade is a split-stack market monitoring app:

- Next.js frontend in `web/`
- FastAPI backend in `src/adapters/api/`
- Python domain and application layers as the source of truth
- PostgreSQL-backed auth and personalization
- Stripe-backed subscription billing

The legacy Streamlit UI has been removed. The supported product surface is now the Next.js app talking to the Python API.

## Run

One command for local development:

```bash
./scripts/dev.sh
```

This starts:

- API: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:3000`

You can override ports:

```bash
API_PORT=8001 WEB_PORT=3001 ./scripts/dev.sh
```

Manual commands:

```bash
uv sync
uv run uvicorn src.adapters.api.app:app --reload --host 0.0.0.0 --port 8000
cd web && npm install
cd web && TRADE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Verification:

```bash
uv run pytest
cd web && npm run typecheck
cd web && npm run build
cd web && npm run e2e
```

Production deploy helpers:

```bash
./scripts/deploy_api.sh
./scripts/deploy_web.sh
./scripts/deploy_prod.sh
```

Environment template:

```bash
cp .env.example .env
```

## Authentication

The backend authenticates Clerk session tokens and maps them to internal users stored in Postgres.

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
CLERK_AUTHORIZED_PARTIES=https://your-app.example.com,http://localhost:3000
CLERK_SIGN_IN_URL=https://your-account-portal-domain/sign-in
CLERK_SIGN_UP_URL=https://your-account-portal-domain/sign-up
APP_BASE_URL=http://localhost:3000
TRADE_API_BASE_URL=http://127.0.0.1:8000
```

Stripe billing variables for the API service:

```bash
STRIPE_SECRET_KEY=sk_test_or_live
STRIPE_PRICE_ID=price_123
STRIPE_PORTAL_CONFIGURATION_ID=bpc_123_optional
```

## Deploy

The root `Dockerfile`, `railway.toml`, and `scripts/start_railway.sh` now target the Python API service.

Railway API deployment:

```bash
./scripts/deploy_api.sh
```

Container behavior:

- installs Python dependencies with `uv sync --frozen`
- sends the optional Telegram startup notification
- starts `uvicorn` on `0.0.0.0:$PORT` with proxy headers enabled
- exposes `GET /healthz` for Railway health checks
- exposes `GET /readyz` for config/readiness inspection
- emits an `X-Request-ID` header on API responses for request tracing

Recommended production topology:

- Python API on Railway
- Next.js frontend on Vercel
- PostgreSQL on Railway

Vercel frontend deployment:

- set the project root to `web/`
- install command: `npm install`
- build command: `npm run build`
- output mode is already configured through `web/next.config.ts` with `output: "standalone"`

Combined production release flow:

```bash
./scripts/deploy_prod.sh
```

This runs:

- `scripts/deploy_api.sh` to deploy the FastAPI service with `npx @railway/cli@latest up`
- `scripts/deploy_web.sh` to deploy the frontend with `npx vercel deploy --prod --yes --cwd web`
- hosted smoke checks against `https://api.brivoly.com` and `https://www.brivoly.com`

Required service environment variables:

- Railway API:
  - `DATABASE_URL`
  - Clerk server-side/auth variables
  - `STRIPE_SECRET_KEY`
  - `STRIPE_PRICE_ID`
  - optional `STRIPE_PORTAL_CONFIGURATION_ID`
  - optional Telegram variables
  - `APP_BASE_URL` should point at the deployed frontend origin
- Vercel frontend:
  - `TRADE_API_BASE_URL` set to the deployed Railway API origin
  - `APP_BASE_URL` set to the deployed frontend origin
  - Clerk publishable/sign-in/sign-up variables used by the sign-in bridge

Deployment verification completed locally on 2026-05-14:

```bash
uv run pytest
cd web && npm run typecheck
cd web && npm run build
cd web && npm run e2e
docker build -t trade-api-deploycheck .
docker run -d --rm --name trade-api-deploycheck-run -p 18000:8000 trade-api-deploycheck
curl http://127.0.0.1:18000/healthz
```

Notes:

- `curl` returned `{"status":"ok"}` from the containerized API.
- `curl http://127.0.0.1:18000/readyz` returned `{"status":"ok", ...}` with production-like env values.
- Avoid running `npm run build` and `npm run e2e` against the same `web/.next` directory in parallel; Next can fail with transient build errors in that case.
- `npm run typecheck` now self-generates Next route types, so it works from a clean checkout.
- After the first hosted Railway deploy, you can smoke-test the API with `./scripts/smoke_hosted.sh <railway-api-url>`.

## Telegram

Optional startup and alert notifications use:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_WEBHOOK_SECRET=shared_secret_for_webhook_optional
```

Utilities:

```bash
uv run python scripts/get_telegram_chat_id.py
uv run python scripts/test_telegram_send.py
```

Telegram-triggered prospecting:

- expose `POST /api/telegram/webhook`
- set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and optionally `TELEGRAM_WEBHOOK_SECRET`
- point your Telegram bot webhook at your API, for example `https://api.brivoly.com/api/telegram/webhook`
- supported bot commands from the allowed chat:
  - `/prospect`
  - `/prospect status`
  - `/help`

## Daily Prospecting Agent

There is now a low-cost daily prospecting job for testing outreach ideas without posting publicly.

What it does:

- searches Reddit for recent posts that look relevant to the app
- scores posts with local heuristics first to avoid unnecessary model usage
- uses OpenAI only for a tiny drafting step when `OPENAI_API_KEY` is configured
- sends a plain-text email digest to `tom.mg.walsh@gmail.com` by default
- falls back to Telegram digest delivery when SMTP is not configured but Telegram is
- never posts to Reddit or any other social network

Required email settings:

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_username
SMTP_PASSWORD=your_password
SMTP_FROM_EMAIL=alerts@your-domain.com
SMTP_USE_TLS=true
```

If SMTP is not configured but Telegram is configured, the digest is delivered to the Telegram chat instead so the agent can still run.

Optional AI settings:

```bash
OPENAI_API_KEY=sk-...
PROSPECT_OPENAI_MODEL=gpt-5-nano
PROSPECT_OPENAI_MAX_OUTPUT_TOKENS=500
```

Run it manually:

```bash
uv run python scripts/run_daily_prospecting.py
```

Useful prospecting settings:

```bash
PROSPECT_EMAIL_RECIPIENT=tom.mg.walsh@gmail.com
PROSPECT_REDDIT_SEARCH_TERMS=looking for stock market crash app,portfolio risk dashboard,market crash alert tool
PROSPECT_REDDIT_LIMIT_PER_TERM=8
PROSPECT_MAX_MATCHES=3
```

Scheduling:

- run `uv run python scripts/run_daily_prospecting.py` once per day from a scheduler
- on Railway, the cleanest setup is a separate scheduled worker service or cron-style job using the same repo and env vars
- the main API service should stay focused on serving FastAPI traffic

## Structure

```text
src/
  domain/
  application/
    account.py
    auth.py
    billing.py
    dashboard.py
    dto.py
    ports.py
    use_cases.py
  adapters/
    api/
    auth/
    billing/
    market_data/
    notifications/
    persistence/
web/
  app/
  components/
  lib/
  public/
```

## Notes

- Billing is created and managed through backend-owned Stripe Checkout and Billing Portal sessions exposed by `/api/account/billing`, `/api/account/billing/checkout`, and `/api/account/billing/portal`.
- Domain logic stays in Python, not in Next.js components or routes.
- The web app is an adapter over explicit API contracts.
- Signals are systematic heuristics for research and education, not financial advice.
