# HANDOFF

## Current Project State

This repo is now a split app:

- FastAPI backend in `src/adapters/api/`
- Next.js frontend in `web/`
- Railway is the intended API host
- Vercel is the intended frontend host
- Clerk remains the app auth provider
- PostgreSQL remains on Railway

The migration itself is functionally complete. The remaining work is deployment topology cleanup, not application rebuild.

## What Was Completed

### Code and test work already finished

- Removed the retired Streamlit runtime and completed the cutover to FastAPI + Next.js
- Added backend request tracing and readiness checks
- Added hosted smoke helpers and environment examples
- Added Playwright E2E coverage for the key user flows
- Verified:
  - `uv run pytest`
  - `cd web && npm run typecheck`
  - `cd web && npm run build`
  - `cd web && npm run e2e`
  - `docker build -t trade-api-deploycheck .`
  - containerized `/healthz` and `/readyz`

### Railway production work completed in the last session

- Logged into Railway CLI successfully
- Linked this repo to Railway project `alert-optimism`
- Confirmed production service is `trade`
- Patched missing live env on the Railway service:
  - `APP_BASE_URL`
  - `TRADE_API_BASE_URL`
  - `DATABASE_URL`
  - Clerk publishable/sign-in/sign-up settings
  - Clerk authorized parties
- Redeployed Railway successfully
- Verified the live API was healthy on the Railway-backed domain:
  - `/healthz` returned OK
  - `/readyz` returned OK
  - `/api/settings/bootstrap` returned the expected payload

### Vercel frontend work completed in the last session

- Logged into Vercel CLI successfully
- Created Vercel project `brivoly-web`
- Set Vercel production env `TRADE_API_BASE_URL=https://trade-production-5635.up.railway.app`
- Disabled Vercel deployment SSO protection for this project so public checks work
- Fixed Vercel framework detection by adding `web/vercel.json`
- Deployed the frontend successfully to:
  - `https://brivoly-web.vercel.app`
- Attached custom domains to the Vercel project:
  - `www.brivoly.com`
  - `brivoly.com`
- Verified:
  - `GET /` returned the Next.js app
  - `GET /sign-in` returned the sign-in page

### Additional deployment cleanup completed after the first handoff

- Corrected the Railway API service variable `TRADE_API_BASE_URL` to point at the live Railway service origin instead of `https://www.brivoly.com`
- Confirmed Railway readiness is still healthy after that change
- Confirmed the remaining blocker is DNS delegation at Porkbun, not app health or deployment packaging

## What Is Still In Progress

The last unfinished task is the public domain split:

- `www.brivoly.com` should point to the Vercel frontend
- `api.brivoly.com` should point to the Railway API

Right now the Railway API has been verified live, but `www.brivoly.com` was still serving the backend when the session ended, which means root `/` returned FastAPI `{"detail":"Not Found"}`. The Vercel frontend itself is healthy at `https://brivoly-web.vercel.app`.

The Vercel domain attachment is done. DNS is the only remaining blocker:

- `A www.brivoly.com 76.76.21.21`
- `A brivoly.com 76.76.21.21`

Current resolution still points the public domains at Railway, so the cutover is not live yet.

## Uncommitted Changes

Current worktree status:

- `HANDOFF.md`
- `web/.gitignore`
- `web/vercel.json`

Notes:

- `web/vercel.json` is intentional and needed so Vercel treats `web/` as a Next.js project.
- `web/.gitignore` currently contains only `.vercel`

These files have not been committed yet.

## Important Commands

### Local development

```bash
./scripts/dev.sh
```

Backend only:

```bash
uv sync
uv run uvicorn src.adapters.api.app:app --reload --host 0.0.0.0 --port 8000
```

Frontend only:

```bash
cd web
npm install
TRADE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

### Verification

```bash
uv run pytest
cd web && npm run typecheck
cd web && npm run build
cd web && npm run e2e
docker build -t trade-api-deploycheck .
```

### Railway

```bash
npx @railway/cli@latest whoami
npx @railway/cli@latest status --json
npx @railway/cli@latest variable list --json
npx @railway/cli@latest logs --lines 80
npx @railway/cli@latest redeploy -y --json
```

### Vercel

```bash
npx vercel whoami
npx vercel project inspect brivoly-web --cwd web
npx vercel deploy --prod --yes --cwd web
npx vercel domains ls
npx vercel domains inspect www.brivoly.com
npx vercel domains inspect brivoly.com
```

## Environment and Deployment Assumptions

- Root `.env` is still the source for local backend config
- The frontend uses `TRADE_API_BASE_URL` to call the API
- In production, the frontend currently points to the Railway-generated API URL:
  - `https://trade-production-5635.up.railway.app`
- The intended final topology is:
  - `www.brivoly.com` -> Vercel
  - `brivoly.com` -> Vercel or redirect to `www`
  - `api.brivoly.com` -> Railway

## Known Issues / Caveats

- Railway CLI auth worked earlier, but the `railway domain api.brivoly.com ...` action still returned an unauthorized error even after a successful login. Railway service management otherwise worked.
- The API is healthy, and the Vercel frontend is healthy. The remaining blocker is DNS at Porkbun.
- `next build` and Playwright should not share the same `web/.next` directory concurrently.

## Recommended Next Steps

1. Update Porkbun DNS:

```bash
A www.brivoly.com 76.76.21.21
A brivoly.com 76.76.21.21
```

2. Wait for Vercel verification to clear, then verify:

```bash
npx vercel domains inspect www.brivoly.com
curl -I https://www.brivoly.com
curl -I https://brivoly.com
```

3. After the frontend domain is live on Vercel, remove `www.brivoly.com` / `brivoly.com` from the Railway `trade` service if they are still attached there.

4. Retry adding `api.brivoly.com` to Railway. If the CLI still misbehaves, use the Railway dashboard as a fallback and keep `TRADE_API_BASE_URL` on the Railway-generated domain until `api.brivoly.com` is working.

5. Commit the pending frontend hosting files:

```bash
git add web/.gitignore web/vercel.json
git commit -m "Configure Vercel frontend hosting"
git push
```

## Last Pushed Commits

- `d197e40` `Add hosted deployment smoke helpers`
- `312e2dc` `Harden deployment readiness and observability`
- `56fac6f` `Document verified deployment workflow`
- `e64d681` `Migrate app shell to FastAPI and Next.js`
