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
- Notifications: Telegram bot integration and SMTP email delivery
- AI drafting: OpenAI API for optional low-cost prospecting reply generation
- Social lead sourcing: Reddit read-only search for daily prospecting workflows
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
- `GET /api/internal/founder-code-requests`

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
- Required frontend deployment env: `BRIVOLY_API_BASE_URL` pointing at the deployed Railway API origin.
- Required shared/auth env depends on environment:
  - API service: `DATABASE_URL`, Clerk variables, `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, optional `STRIPE_PORTAL_CONFIGURATION_ID`, optional Telegram variables
  - Frontend service: `BRIVOLY_API_BASE_URL`, `APP_BASE_URL`, Clerk publishable/sign-in/sign-up values as needed by the sign-in bridge
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

## Fast Start

Use this section to give the next session a fast, practical starting point. Refresh it at the end of every meaningful session so a new session can get oriented quickly without re-discovering the current product state.

### Current Product Progress

- The product is now a multi-surface SaaS app with two active tracks:
  - `crash-monitor` for market risk monitoring
  - `crm` for the new greenfield CRM wedge
- The CRM direction is currently the main build focus.
- The CRM app already has:
  - a homepage portal entry
  - an authenticated `/crm` workspace
  - a lead follow-up queue
  - complete and snooze/reschedule actions
  - contact timeline history per lead
  - lightweight internal note capture
- The current CRM wedge is:
  - follow-up-first
  - spreadsheet-friendly
  - relationship-memory oriented
  - aimed at operators, agencies, and similar SMB workflows

### Current Agent Progress

- The prospect agent is being used as a research partner to guide CRM direction.
- The prospecting profile is tuned toward `crm_direction`.
- Prospect discovery now spans:
  - Reddit
  - Hacker News
  - broad public web search
  - Indie Hackers
  - review sites like G2, Capterra, and Shopify app listings
  - X
  - public Discord discovery
- Cooperative runs have repeatedly reinforced:
  - follow-up discipline
  - spreadsheet-held CRM workflows
  - pipeline hygiene
  - relationship memory
- The strongest recurring adjacent idea is later `message / DM capture` into CRM, but that is still secondary to the core follow-up workflow.
- The sentiment agent is live separately for ETF analysis and is not the main product direction.
- Telegram now has a `/code` command that runs the cooperative prospect pass, makes a build/no-build judgment, and appends a structured recommendation to `var/autonomous_build_queue.jsonl` by default.
- `/code <guidance>` should treat the trailing text as explicit founder direction unless it clearly harms the current goal of building a narrow, profitable CRM wedge.
- `/code` requests are now also stored durably in Postgres so this always-on machine can mirror them into a local inbox.
- Strong unguided prospect-agent build recommendations now use that same durable queue path, tagged as `agent:prospect`, so the server can hand off autonomous build suggestions to the local machine without inventing a second inbox.

### Current Automation Progress

- Local automation is the primary reliable 24/7 path.
- The local automation worker can run prospecting and operator briefing jobs continuously on this machine.
- The operator briefing system can email the founder with:
  - agent interaction summaries
  - guidance received
  - features/refinements shipped
  - profitability progress
- Prospecting automation cadence is currently set to every 12 hours, not every hour.
- Each successful automated prospect run should trigger an operator briefing email; the separate scheduled operator briefing job is optional rather than the default.
- Local app agents should prefer `APP_OPENAI_API_KEY` over `OPENAI_API_KEY` so app automation can use a dedicated credential path separate from the editor/Codex environment.
- `/code` does not let Railway self-edit the repo. It truthfully triggers research, queues a build brief, and notifies the founder; actual code changes still happen through this coding agent.
- The newest bridge layer is a founder-code sync job: Railway stores both `/code` requests and prospect-agent build prompts, and the local automation worker can poll them into `var/founder_code_inbox.jsonl` when the sync env vars are configured.
- This bridge has now been proven end to end with a live production `/prospect` run; the first mirrored `agent:prospect` prompt recommended `CSV and Google Sheets import`.

### Current Deployment Status

- API deploy target: Railway
- Frontend deploy target: Vercel
- Latest autonomous CRM follow-up action feature has already been:
  - implemented
  - tested
  - deployed to Railway and Vercel
  - logged into `product_updates.jsonl`
  - summarized by email through the operator briefing flow
- The latest platform automation addition is the Telegram `/code` workflow on the API side; it is production-facing and should be kept in sync with the fast-start notes and README.
- The newest reliability fix is that `/code` and `/prospect` now tolerate SMTP failure as long as Telegram delivery still works.
- The newest remote-autonomy bridge is that production prospect runs can now queue strong build recommendations into the same durable inbox path used for founder `/code` requests.

### Current Verification Notes

- Backend verification standard:
  - `uv run pytest`
- Frontend verification standard:
  - `cd web && npm run build`
- `cd web && npm run typecheck` currently has a known pre-existing issue with missing `.next/types/**` generated files referenced by `web/tsconfig.json`. Treat this as a repo issue unless the failure changes shape.

### Next Recommended Product Moves

- Highest-conviction next CRM features:
  - CSV or spreadsheet import / cleanup
  - richer handoff history and stage memory
  - consultant / agency specific templates or checklists
- Broader CRM expansion should stay constrained until the follow-up-first wedge shows stronger pull.

## Autonomy Rule

- The agent should proactively implement the next high-conviction feature set when product direction is already clear, without waiting for explicit step-by-step instructions.
- Each autonomous change set should include implementation, local verification, commit, push, and deployment when the affected surface is production-facing and deployment credentials are already available.
- The agent should use existing email and operator-briefing mechanisms to keep the founder updated on shipped work, validation learnings, and profitability progress.
- The agent should still pause when a change would introduce hidden risk, destructive actions, major architectural drift, or unclear product tradeoffs.
- The agent should update the `Fast Start` section in this file at the end of each meaningful session so the next session begins with a current snapshot.

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
