# AGENTS

## Current Dev Stack

- Language/runtime: Python 3.12
- Package manager: `uv`
- Virtual environment: local `.venv`
- Primary UI: Next.js + TypeScript in `web/`
- Styling: Tailwind CSS
- Component direction: `shadcn/ui` on top of accessible primitives
- API layer: FastAPI in `src/adapters/api/`
- Data and analytics: NumPy, pandas, Plotly
- Market data provider: `yfinance`
- Database: PostgreSQL via `psycopg`
- Authentication: Clerk JWT auth with internal Postgres-backed user records
- Billing: Stripe Checkout + Billing Portal
- Notifications: Telegram bot integration
- Testing: `pytest` with `pytest-cov`
- Containerization: Docker
- Deployment target: Railway for the API, Vercel for the web frontend

## Architecture

This repo uses a hexagonal, ports-and-adapters style:

- `src/domain`: business entities and pure domain logic
- `src/application`: use-cases and port interfaces
- `src/adapters`: auth, persistence, notifications, market-data, and HTTP API delivery
- `web/`: Next.js application acting as the primary user-facing adapter

Use hexagonal architecture for new features and refactors. Keep domain logic independent from frameworks, I/O, and third-party services by expressing integrations through ports and implementing them in adapters.

Follow SOLID principles in all code changes:

- Single Responsibility Principle
- Open/Closed Principle
- Liskov Substitution Principle
- Interface Segregation Principle
- Dependency Inversion Principle

## Common Commands

```bash
uv sync
uv run uvicorn src.adapters.api.app:app --reload
./scripts/dev.sh
./scripts/deploy_api.sh
./scripts/deploy_web.sh
./scripts/deploy_prod.sh
cp .env.example .env
pytest
cd web && npm install
cd web && npm run dev
cd web && npm run typecheck
cd web && npm run build
cd web && npm run e2e
```

## Product Direction

Python remains the source of truth for domain logic and application use-cases. The Next.js app is the primary product UI and communicates with Python only through explicit API boundaries.

### Responsibility Split

- `src/domain`: pure business rules, entities, calculations, policies, and invariants in Python
- `src/application`: Python use-cases, DTOs, and port definitions
- `src/adapters`: Python adapters for persistence, external APIs, notifications, auth, and HTTP API delivery
- `web/`: Next.js application for authenticated SaaS UI

### Current API Surface

The backend exposes these routes from `src/adapters/api/app.py`:

- `GET /healthz`
- `GET /readyz`
- `GET /api/settings/bootstrap`
- `GET /api/session`
- `GET /api/dashboard`
- `GET /api/account/settings`
- `PUT /api/account/settings`
- `GET /api/account/billing`
- `POST /api/account/billing/checkout`
- `POST /api/account/billing/portal`
- `GET /api/alerts/history`

Notes:

- `account/settings` and `alerts/history` use a Postgres-backed personalization adapter when `DATABASE_URL` is configured.
- Stripe billing routes are enabled when `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, and `DATABASE_URL` are configured on the API service.
- The in-memory personalization adapter remains available as a fallback for local or isolated test contexts.
- The Next.js app supports sign-in bootstrap, dashboard rendering, interactive dashboard filters, editable settings, refreshable alert history, and richer chart rendering on top of the Python API contracts.
- API responses include `X-Request-ID` for request tracing.

## Execution Checklist

- [x] Move decision-making logic out of the retired Streamlit adapter and into `src/domain` or `src/application`.
- [x] Introduce Python DTOs for frontend-safe dashboard responses instead of leaking UI-specific shapes.
- [x] Add a Python HTTP adapter layer under `src/adapters/api/`.
- [x] Define initial API routes for session bootstrap, dashboard data, alerts, and settings.
- [x] Add contract tests for those API routes.
- [x] Create `web/` frontend scaffold for Next.js + TypeScript.
- [x] Add Tailwind CSS base setup in the frontend scaffold.
- [x] Add `shadcn/ui`-ready aliases and component configuration.
- [x] Add shared frontend app shell, navigation, and authenticated layout.
- [x] Implement typed API client utilities in `web/lib/`.
- [x] Implement sign-in/session bootstrap flow against the Python backend.
- [x] Rebuild the dashboard overview in Next.js using backend API responses.
- [x] Rebuild chart, alerts, and settings flows in the Next.js UI.
- [x] Add end-to-end tests for critical user journeys.
- [x] Cut traffic from Streamlit to Next.js and remove the Streamlit runtime.

## Deployment Notes

- Railway deploys the Python API from the repo root using `Dockerfile`, `railway.toml`, and `scripts/start_railway.sh`.
- Vercel should use `web/` as the frontend project root.
- Preferred release helpers:
  - `./scripts/deploy_api.sh`
  - `./scripts/deploy_web.sh`
  - `./scripts/deploy_prod.sh`
- Required frontend deployment env: `TRADE_API_BASE_URL` pointing at the deployed Railway API origin.
- Required shared/auth env depends on environment:
  - API service: `DATABASE_URL`, Clerk variables, `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, optional `STRIPE_PORTAL_CONFIGURATION_ID`, optional Telegram variables
  - Frontend service: `TRADE_API_BASE_URL`, `APP_BASE_URL`, Clerk publishable/sign-in/sign-up values as needed by the sign-in bridge
- Local verification completed for the current split:
  - `uv run pytest`
  - `cd web && npm run typecheck`
  - `cd web && npm run build`
  - `cd web && npm run e2e`
  - `docker build -t trade-api-deploycheck .`
  - `docker run ... trade-api-deploycheck` returning `GET /healthz -> {"status":"ok"}`
  - `uv run pytest` now includes a real `uvicorn` smoke test for `/healthz`, `/readyz`, and bootstrap routes
- Use `.env.example` as the baseline local/shared environment template.
- After the first hosted Railway deploy, `./scripts/smoke_hosted.sh <railway-api-url>` can verify `/healthz`, `/readyz`, and bootstrap responses quickly.

## Directory Direction

```text
src/
  domain/
  application/
  adapters/
    api/
    auth/
    billing/
    persistence/
    notifications/
    market_data/
web/
  app/
  components/
  lib/
  public/
```

## Non-Goals

- Do not move domain rules into Next.js server actions or client components.
- Do not duplicate calculation logic across Python and TypeScript.
- Do not couple frontend components directly to database structure.
- Do not break hexagonal boundaries just to speed up delivery.

## Maintenance Rule

Keep this file up to date whenever the stack, deployment model, architecture, or core tooling changes. Update it when adding or removing major frameworks, infrastructure dependencies, auth providers, databases, package managers, or primary developer workflows.

## Handoff Rule

Always read `HANDOFF.md` at the start of a new session if it exists.

When the user writes the exact prompt `handoff`, create or overwrite `HANDOFF.md` with the information needed for a useful next-session handoff. Include at minimum:

- current project state
- what was completed in the current session
- what is still in progress
- next recommended steps
- important environment or run commands
- known issues, risks, or caveats
- any active architectural or deployment assumptions
