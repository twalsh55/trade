# Brivoly

Brivoly is a split-stack market monitoring app:

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
cd web && BRIVOLY_API_BASE_URL=http://127.0.0.1:8000 npm run dev
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
BRIVOLY_API_BASE_URL=http://127.0.0.1:8000
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
  - `BRIVOLY_API_BASE_URL` set to the deployed Railway API origin
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
  - `/sentiment`
  - `/sentiment status`
  - `/code`
  - `/code <guidance>`
  - `/help`

## Daily Prospecting Agent

There is now a low-cost daily prospecting job for testing outreach ideas without posting publicly.

What it does:

- searches Reddit and Hacker News for recent workflow-pain discussions
- scores posts with local heuristics first to avoid unnecessary model usage
- uses OpenAI only for a small opportunity-idea drafting step when `APP_OPENAI_API_KEY` or `OPENAI_API_KEY` is configured
- can run in a CRM-focused direction mode to steer product decisions for the CRM app
- `/code` runs the same cooperative prospect pass, sends the usual digest/briefing, and appends a structured build recommendation to `AUTONOMOUS_BUILD_QUEUE_FILE`
- `/code <guidance>` treats the trailing text as founder direction and queues it unless it clearly conflicts with the narrow profitable CRM goal
- sends a plain-text email digest to `tom.mg.walsh@gmail.com` by default
- falls back to Telegram digest delivery when SMTP is not configured but Telegram is
- never posts to Reddit, Hacker News, or any other social network
- does not draft public replies or posting suggestions; it returns SaaS ideas only
- records OpenAI token usage in the digest and can append usage entries to a local JSONL log

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
APP_OPENAI_API_KEY=sk-...
OPENAI_API_KEY=sk-... # optional legacy fallback
PROSPECT_OPENAI_MODEL=gpt-5-nano
PROSPECT_OPENAI_MAX_OUTPUT_TOKENS=500
ETF_SENTIMENT_OPENAI_MODEL=gpt-5-nano
ETF_SENTIMENT_OPENAI_MAX_OUTPUT_TOKENS=900
ETF_SENTIMENT_LOOKBACK_DAYS=400
ETF_SENTIMENT_PROMPT_FILE=prompts/ETF_SENTIMENT.md
ETF_SENTIMENT_QUERIES=ETF market sentiment,MSCI World ETF,S&P 500 ETF sentiment,Nasdaq 100 ETF,AI ETF OR semiconductor ETF,bond ETF OR defensive rotation
ETF_SENTIMENT_SIGNAL_LIMIT_PER_QUERY=4
ETF_SENTIMENT_MAX_SIGNALS=18
ETF_SENTIMENT_ENABLE_REDDIT_SIGNALS=true
ETF_SENTIMENT_ENABLE_NEWS_SIGNALS=true
ETF_SENTIMENT_ENABLE_X_SIGNALS=true
ETF_SENTIMENT_ENABLE_DISCORD_SIGNALS=true
ETF_SENTIMENT_REDDIT_USER_AGENT=brivoly-etf-sentiment-bot/0.1
ETF_SENTIMENT_PUBLIC_SEARCH_USER_AGENT=brivoly-etf-sentiment-bot/0.1
```

ETF sentiment Telegram brief:

- `/sentiment` runs a server-side ETF sentiment snapshot and sends the result back to the configured Telegram chat
- `/sentiment status` reports whether the ETF sentiment agent is ready and whether it will use OpenAI or template mode
- the snapshot now combines `yfinance` ETF proxies with lightweight public text signals from Reddit search and Google News RSS
- when the app OpenAI key is missing, the agent still works in template mode using those price and text inputs
- the prompt source lives at `prompts/ETF_SENTIMENT.md`

Run it manually:

```bash
uv run python scripts/run_daily_prospecting.py
```

Useful prospecting settings:

```bash
PROSPECT_EMAIL_RECIPIENT=tom.mg.walsh@gmail.com
PROSPECT_PROFILE=crm_direction
PROSPECT_REDDIT_SEARCH_TERMS=lead follow up manually,sales pipeline spreadsheet,client handoff spreadsheet,crm for agencies spreadsheet,relationship notes follow up
PROSPECT_REDDIT_LIMIT_PER_TERM=8
PROSPECT_MAX_MATCHES=5
PROSPECT_MIN_SCORE=12
PROSPECT_VERBOSE_AUDIT=false
PROSPECT_TRACK_USAGE=true
PROSPECT_USAGE_LOG_FILE=var/prospect_usage_log.jsonl
PROSPECT_PERIODIC_INTERVAL_MINUTES=720
PROSPECT_PERIODIC_MAX_RUNS=1
PROSPECT_PUBLIC_SEARCH_USER_AGENT=trade-prospecting-bot/0.1
PROSPECT_ENABLE_REDDIT_SOURCE=true
PROSPECT_ENABLE_HACKER_NEWS_SOURCE=true
PROSPECT_ENABLE_WEB_SOURCE=true
PROSPECT_ENABLE_INDIE_HACKERS_SOURCE=true
PROSPECT_ENABLE_REVIEW_SOURCE=true
PROSPECT_ENABLE_X_SOURCE=true
PROSPECT_ENABLE_DISCORD_SOURCE=true
PROSPECT_RUN_LOG_FILE=var/prospect_run_log.jsonl
PRODUCT_UPDATE_LOG_FILE=product_updates.jsonl
OPERATOR_BRIEFING_RECIPIENT=tom.mg.walsh@gmail.com
OPERATOR_BRIEFING_LOOKBACK_HOURS=24
OPERATOR_BRIEFING_GOAL=Zero in on a narrow, recurring CRM workflow with measurable ROI, low support burden, and fast time-to-revenue for a solo founder.
INTERNAL_CRON_SECRET=replace-me
```

Scheduling:

- run `uv run python scripts/run_daily_prospecting.py` once per day from a scheduler
- for a simple in-process loop, use `uv run python scripts/run_periodic_prospecting.py`
- for Railway cron, use `./scripts/deploy_prospect_cron.sh` to create or update the `prospect-hourly` function
- the Railway function calls the existing Telegram webhook with `/prospect`, so delivery, token tracking, and CRM-direction prompting stay in one code path
- for the daily operator summary email, use `./scripts/deploy_operator_briefing_cron.sh` to create or update the `operator-daily` function
- the operator summary reads recent prospect runs plus logged product updates, then emails a daily briefing about agent guidance, roadmap changes, and profitability direction
- the main API service should stay focused on serving FastAPI traffic

CRM direction mode:

- set `PROSPECT_PROFILE=crm_direction` to bias the agent toward lead follow-up, pipeline hygiene, client handoff, relationship memory, and adjacent CRM workflows
- when `PROSPECT_REDDIT_SEARCH_TERMS` is empty, the runtime uses CRM-specific defaults automatically in that profile
- public-source discovery can now pull from Reddit, Hacker News, broad web search, Indie Hackers, review sites, X, and public Discord discovery
- the digest includes model token usage when OpenAI drafting runs
- when `PROSPECT_TRACK_USAGE=true`, each run appends a JSONL entry to `PROSPECT_USAGE_LOG_FILE`
- each prospecting run also appends a richer run record to `PROSPECT_RUN_LOG_FILE`

Operator briefing workflow:

- log a shipped feature or refinement with `PYTHONPATH=. uv run python scripts/log_product_update.py ...`
- send the daily operator email manually with `PYTHONPATH=. uv run python scripts/run_daily_operator_briefing.py`
- each successful automated prospect run now sends an operator briefing email automatically
- `APP_OPENAI_API_KEY` is the preferred local app credential when you want the app agents to use a different key from the editor/Codex environment
- the briefing is designed to summarize:
  - what the prospect agent found
  - what product changes were made
  - whether those changes align with a narrow, profitable CRM wedge

Local 24/7 automation:

- start the long-running worker directly with `PYTHONPATH=. uv run python scripts/run_local_automation.py`
- install reboot recovery plus a 5-minute watchdog with `./scripts/install_local_automation.sh`
- inspect health with `PYTHONPATH=. uv run python scripts/local_automation_status.py`
- remove the watchdog and stop the worker with `./scripts/uninstall_local_automation.sh`

Useful automation settings:

```bash
AUTOMATION_POLL_SECONDS=30
AUTOMATION_PROSPECT_INTERVAL_MINUTES=720
AUTOMATION_ENABLE_SCHEDULED_OPERATOR_BRIEFING=false
AUTOMATION_OPERATOR_BRIEFING_INTERVAL_HOURS=24
AUTOMATION_ENABLE_SENTIMENT_JOB=false
AUTOMATION_SENTIMENT_INTERVAL_HOURS=24
AUTOMATION_ALLOW_TEMPLATE_FALLBACK=true
AUTOMATION_JOB_TIMEOUT_SECONDS=45
AUTOMATION_LOCK_FILE=var/automation_worker.lock
AUTOMATION_STATE_FILE=var/automation_state.json
AUTOMATION_HEARTBEAT_FILE=var/automation_heartbeat.json
```

Automation behavior:

- one worker process manages all recurring jobs so we do not stack overlapping cron jobs
- a file lock prevents duplicate workers
- a heartbeat file makes health checks and watchdog recovery straightforward
- state persists last successful run timestamps so the worker can resume cleanly after restarts
- unattended prospect runs fall back to template mode automatically if the local OpenAI credential is invalid
- each successful automated prospect run also sends an operator briefing email so product guidance arrives with the run itself
- the separate scheduled operator briefing job is opt-in via `AUTOMATION_ENABLE_SCHEDULED_OPERATOR_BRIEFING=true`
- each scheduled job gets a hard timeout so one stuck network call does not freeze the whole worker
- `APP_OPENAI_API_KEY` is preferred over `OPENAI_API_KEY` for app-side agent runs so local automation can use a dedicated app credential

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
