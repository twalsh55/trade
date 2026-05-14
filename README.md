# Trade

Trade is a split-stack market monitoring app:

- Next.js frontend in `web/`
- FastAPI backend in `src/adapters/api/`
- Python domain and application layers as the source of truth
- PostgreSQL-backed auth and personalization

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

## Deploy

The root `Dockerfile`, `railway.toml`, and `scripts/start_railway.sh` now target the Python API service.

Railway API deployment:

```bash
railway up
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

Required service environment variables:

- Railway API:
  - `DATABASE_URL`
  - Clerk server-side/auth variables
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

## Telegram

Optional startup and alert notifications use:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Utilities:

```bash
uv run python scripts/get_telegram_chat_id.py
uv run python scripts/test_telegram_send.py
```

## Structure

```text
src/
  domain/
  application/
    account.py
    auth.py
    dashboard.py
    dto.py
    ports.py
    use_cases.py
  adapters/
    api/
    auth/
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

- Domain logic stays in Python, not in Next.js components or routes.
- The web app is an adapter over explicit API contracts.
- Signals are systematic heuristics for research and education, not financial advice.
