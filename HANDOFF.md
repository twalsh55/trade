# HANDOFF

## Current Project State

This repo now runs as a split application:

- Python backend/API in `src/adapters/api/` using FastAPI
- Next.js frontend in `web/`
- Python domain and application layers remain the source of truth
- Postgres-backed auth and personalization are wired on the backend
- The legacy Streamlit UI has been removed

The frontend supports:

- Clerk-based sign-in bootstrap through a local app session cookie
- server-rendered dashboard overview
- interactive dashboard filter refresh
- editable account/dashboard settings
- refreshable alert history
- richer chart rendering on top of Python API responses

## What Was Completed

### Earlier migration work already present

- Added FastAPI API layer in `src/adapters/api/app.py`
- Added DTOs in `src/application/dto.py`
- Added account/settings and alert-history application layer in `src/application/account.py`
- Added shared auth runtime helpers in `src/adapters/auth/runtime.py`
- Added Postgres-backed personalization repository
- Added Next.js app shell, sign-in flow, local proxy routes, charts, alerts, and settings UI

### This session

- Removed `main.py` and the Streamlit dashboard adapter
- Removed Streamlit-only test coverage and replaced it with auth/runtime coverage that still exercises the Python backend architecture
- Added shared dashboard settings/config logic in `src/application/dashboard.py` as part of the earlier migration work, then completed the cutover away from the Streamlit runtime
- Updated Railway deployment files to start the FastAPI app instead of Streamlit
- Updated `README.md` and `AGENTS.md` to reflect the new primary architecture
- Set `web/next.config.ts` to `output: "standalone"` for cleaner frontend deployment packaging
- Added Playwright end-to-end coverage for session bootstrap, dashboard refresh, settings save, and alert refresh
- Verified the split deployment path locally, including the Railway Docker image and Next standalone build
- Added `.dockerignore` to keep the Railway build context focused on deployable files

## Verified Status

Last verified successfully:

- Backend tests:
  - `uv run pytest`
- Frontend checks:
  - `cd web && npm run typecheck`
  - `cd web && npm run build`
  - `cd web && npm run e2e`
- Deployment checks:
  - `docker build -t trade-api-deploycheck .`
  - `docker run ... trade-api-deploycheck`
  - `GET /healthz` returned `{"status":"ok"}`

## Important Run Commands

### One-command local dev

```bash
./scripts/dev.sh
```

Defaults:

- API: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:3000`

### Manual local run

Backend:

```bash
uv sync
uv run uvicorn src.adapters.api.app:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd web
npm install
TRADE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## Environment Assumptions

Root `.env` currently contains local values for:

- `DATABASE_URL`
- Clerk variables
- Telegram config

Notes:

- Python loads root `.env`
- Next.js uses `TRADE_API_BASE_URL` for backend access
- `APP_BASE_URL` should point to the frontend origin, typically `http://localhost:3000` in local development

## Deployment Assumptions

Current root deployment files now target the Python API:

- `Dockerfile`
- `railway.toml`
- `scripts/start_railway.sh`

Recommended production topology:

- Python API on Railway
- Next.js frontend on Vercel
- Postgres on Railway

## Known Risks / Caveats

- The Playwright suite currently uses a mock backend for deterministic browser coverage rather than the live FastAPI app.
- `next build` and the Playwright suite should not be run against the same `web/.next` directory in parallel; doing so can produce transient Next build errors.
- Production deployment still depends on correct per-service environment configuration in Railway and Vercel.

## What Is Still In Progress

Remaining high-value items:

- Add a thin real-stack smoke test layer that exercises the live FastAPI app in addition to the mocked Playwright suite
- Continue hardening environment setup and observability for separate frontend/backend production services

## Recommended Next Steps

1. Configure the real Railway and Vercel services using the verified split deployment settings and environment variables.
2. Add a thin smoke test against the live FastAPI app to complement the mocked Playwright suite.
3. Add structured logging and auth-boundary observability for production readiness.
