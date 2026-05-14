# HANDOFF

## Current Project State

This repo is fully migrated to the split production architecture:

- FastAPI backend in `src/adapters/api/`
- Next.js frontend in `web/`
- Railway hosts the API
- Vercel hosts the frontend
- Clerk handles app auth
- PostgreSQL remains on Railway

The live topology is now in place:

- `https://www.brivoly.com` -> Vercel frontend
- `https://brivoly.com` -> Vercel frontend
- `https://api.brivoly.com` -> Railway API

The migration/cutover work is done. The remaining work is polish and cleanup of uncommitted improvements made in the latest session.

## What Was Completed

### Production deployment and domain split

- Railway API deploy is working
- Vercel frontend deploy is working
- Public domains were cut over successfully
- Vercel frontend env was switched to `TRADE_API_BASE_URL=https://api.brivoly.com`
- `www.brivoly.com` was removed from Railway after DNS moved to Vercel
- The final split is verified live:
  - `https://www.brivoly.com`
  - `https://brivoly.com`
  - `https://api.brivoly.com/healthz`
  - `https://www.brivoly.com/api/session`

### Repo work already committed and pushed

Recent pushed commits:

- `aabc4eb` `Add production deploy helper scripts`
- `4cfe6ba` `Restore dashboard calculations and charts`
- `cc6e514` `Remove legacy env utils shim`
- `75f99dc` `Configure Vercel frontend hosting`
- `d197e40` `Add hosted deployment smoke helpers`
- `312e2dc` `Harden deployment readiness and observability`
- `56fac6f` `Document verified deployment workflow`
- `e64d681` `Migrate app shell to FastAPI and Next.js`

### Product behavior restored

- The web dashboard now surfaces the Python crash-risk calculations again instead of only a thin migration shell
- Restored UI now includes:
  - richer dashboard metrics
  - risk component breakdowns
  - indicator percentile table
  - action cues
  - fuller dashboard readout

## What Was Completed In This Session

- Added production deploy helper scripts:
  - `scripts/deploy_api.sh`
  - `scripts/deploy_web.sh`
  - `scripts/deploy_prod.sh`
- Added better deploy-script logging and retry/timeout behavior in:
  - `scripts/deploy_api.sh`
  - `scripts/deploy_web.sh`
  - `scripts/deploy_prod.sh`
  - `scripts/smoke_hosted.sh`
- Removed more migration-era wording from the frontend shell
- Added a top-of-page crash indicator card:
  - shows crash percentage
  - uses green/amber/red shading
  - links to the component breakdown section
- Anchored the risk-component section with `#crash-components`
- Patched the yfinance adapter to set an explicit timezone-cache directory before downloads to reduce Railway log noise:
  - `src/adapters/market_data/yfinance_provider.py`

## Verified Status

Most recent verified checks:

- `uv run pytest` passed
  - `89` tests
  - `100%` coverage
- `cd web && npm run typecheck` passed
- `cd web && npm run build` passed
- `cd web && npm run e2e` passed

Live production checks previously verified:

- `curl https://api.brivoly.com/healthz`
- `curl https://www.brivoly.com/api/session`
- `curl -I https://www.brivoly.com`
- `curl -I https://brivoly.com`

## Uncommitted Changes

Current worktree status:

- `scripts/deploy_api.sh`
- `scripts/deploy_prod.sh`
- `scripts/deploy_web.sh`
- `scripts/smoke_hosted.sh`
- `src/adapters/market_data/yfinance_provider.py`
- `tests/test_market_data_adapter.py`
- `web/app/layout.tsx`
- `web/components/app-shell.tsx`
- `web/components/dashboard/dashboard-workspace.tsx`
- `HANDOFF.md`

Meaning of those changes:

- deploy scripts were hardened so they fail faster and look less “hung”
- hosted smoke checks now retry with bounded curl timeouts
- yfinance cache path is configured explicitly
- top-of-page crash indicator UI was added
- leftover migration placeholder wording was removed from the UI metadata/shell

None of those latest changes are committed yet.

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
```

### Production deploy helpers

API only:

```bash
./scripts/deploy_api.sh
```

Frontend only:

```bash
./scripts/deploy_web.sh
```

Deploy both:

```bash
./scripts/deploy_prod.sh
```

### Manual platform commands

Railway:

```bash
npx @railway/cli@latest whoami
npx @railway/cli@latest status
npx @railway/cli@latest up
```

Vercel:

```bash
npx vercel whoami
npx vercel deploy --prod --yes --cwd web
```

## Environment and Deployment Assumptions

- Root `.env` remains the local backend config source
- The frontend uses `TRADE_API_BASE_URL` to call the API
- Production frontend should use:
  - `TRADE_API_BASE_URL=https://api.brivoly.com`
  - `APP_BASE_URL=https://www.brivoly.com`
- Production backend should use:
  - `APP_BASE_URL=https://www.brivoly.com`
  - `DATABASE_URL`
  - Clerk auth variables

## Known Issues / Caveats

- The “deploy all” script can appear to hang because Railway/Vercel deploy commands block on remote build/deploy work; this session added better logging and retry behavior, but those script changes are still uncommitted.
- Focused `pytest` invocations fail the coverage gate because the repo enforces global 100% coverage; use full `uv run pytest` for final verification.
- Railway CLI auth can expire unexpectedly; if deploy helpers fail on auth, rerun:

```bash
npx @railway/cli@latest login
```

- `next build` and Playwright should not run concurrently against the same `web/.next` directory.

## Recommended Next Steps

1. Review the current uncommitted changes in the deploy scripts, yfinance cache fix, and crash-indicator UI.
2. If they look good, commit them together or as two commits:
   - deploy/runtime hardening
   - UI polish
3. Push and redeploy:

```bash
./scripts/deploy_prod.sh
```

4. Confirm the yfinance warning is gone or reduced in Railway logs after the next production API deploy.

## Suggested Commit Split

Option A: one commit

```bash
git add scripts/deploy_api.sh scripts/deploy_prod.sh scripts/deploy_web.sh scripts/smoke_hosted.sh src/adapters/market_data/yfinance_provider.py tests/test_market_data_adapter.py web/app/layout.tsx web/components/app-shell.tsx web/components/dashboard/dashboard-workspace.tsx HANDOFF.md
git commit -m "Polish deploy workflow and crash indicator UI"
git push
```

Option B: two commits

Runtime/deploy:

```bash
git add scripts/deploy_api.sh scripts/deploy_prod.sh scripts/deploy_web.sh scripts/smoke_hosted.sh src/adapters/market_data/yfinance_provider.py tests/test_market_data_adapter.py
git commit -m "Harden deploy scripts and yfinance cache setup"
```

UI/docs:

```bash
git add web/app/layout.tsx web/components/app-shell.tsx web/components/dashboard/dashboard-workspace.tsx HANDOFF.md
git commit -m "Polish crash indicator and remove migration copy"
git push
```
