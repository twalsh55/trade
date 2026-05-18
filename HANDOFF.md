# HANDOFF

## Current Project State

The repo now includes a working Telegram-triggered prospecting agent for Brivoly.

Current production behavior:

- FastAPI backend is live on Railway at `https://api.brivoly.com`
- Telegram webhook is active and secured with `TELEGRAM_WEBHOOK_SECRET`
- `/prospect`, `/prospect status`, and `/help` are handled by the live API
- Prospecting currently works without SMTP by falling back to Telegram digest delivery
- OpenAI API use is still disabled in production because `OPENAI_API_KEY` is not configured
- SMTP email delivery is still disabled in production because SMTP credentials are not configured

Current source coverage:

- Production currently supports Reddit prospecting
- Local repo has new Hacker News support implemented and tested, but it is not yet committed or deployed

## What Was Completed In This Session

### Telegram and production wiring

- Confirmed Telegram bot token/chat wiring
- Fixed missing Telegram webhook registration
- Registered webhook to:
  - `https://api.brivoly.com/api/telegram/webhook`
- Added and activated `TELEGRAM_WEBHOOK_SECRET`
- Verified unsigned webhook requests now return `401`
- Verified signed webhook requests succeed

### Prospecting delivery fallback

- Added Telegram digest fallback when SMTP is missing
- This lets `/prospect` run now instead of failing on missing SMTP vars
- Production remains in Telegram-delivery mode until SMTP is configured

### Output quality and noise reduction

- Tightened prospecting output to top 5 strongest results
- Added minimum score threshold
- Switched default mode to concise audit output
- Added text summaries instead of dumping long raw post bodies

### Prompt / operator docs

- Updated `prompts/PROSPECT.md` to reflect current prospecting behavior and operator intent
- Updated `README.md` and `.env.example` to document the current prospecting and Telegram setup

### Additional source work completed locally

- Added Hacker News support using the public Algolia HN API
- Added a composite lead source combining Reddit + Hacker News
- Updated tests and docs for this
- This work is passing locally but is not yet committed or deployed

## Current Git State

Latest pushed commits:

- `fbacc2d` `Tighten prospecting output to top five summaries`
- `487e87a` `Add Telegram digest fallback for prospecting`
- `0fef15e` `Add daily prospecting agent and Telegram trigger`

Current uncommitted changes:

- `prompts/PROSPECT.md`
- `README.md`
- `src/adapters/prospecting/runtime.py`
- `tests/test_prospecting_runtime.py`
- `src/adapters/social/composite_lead_source.py`
- `src/adapters/social/hacker_news_lead_source.py`
- `tests/test_composite_lead_source.py`
- `tests/test_hacker_news_lead_source.py`

Meaning:

- Hacker News source support is implemented locally
- runtime/docs were updated to use Reddit + Hacker News together
- this work is tested but not committed/pushed/deployed yet

## Verified Status

Local verification completed during this session:

- `uv run pytest`
  - `162` tests
  - `100%` coverage

Production verification completed during this session:

- `https://api.brivoly.com/healthz` returned `{"status":"ok"}`
- `https://api.brivoly.com/readyz` returned status `ok`
- signed POSTs to `/api/telegram/webhook` succeed
- unsigned POSTs to `/api/telegram/webhook` now return `401`
- Telegram webhook info showed:
  - URL set to `https://api.brivoly.com/api/telegram/webhook`
  - `pending_update_count: 0`

## What Is Still In Progress

### Not yet committed/deployed

- Hacker News source support
- composite Reddit + Hacker News lead source
- related README / prompt / runtime updates

### Not yet fully configured in production

- `OPENAI_API_KEY`
- SMTP credentials:
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USERNAME`
  - `SMTP_PASSWORD`
  - `SMTP_FROM_EMAIL`

Because of that:

- AI drafting is still off in production
- email delivery is still off in production
- Telegram digest fallback is currently the active delivery mode

## Recommended Next Steps

1. Review the uncommitted Hacker News and runtime/doc changes.
2. If they look good, commit and push them.
3. Deploy the API again so production uses Reddit + Hacker News.
4. If the user provides secrets, set these on Railway:
   - `OPENAI_API_KEY`
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USERNAME`
   - `SMTP_PASSWORD`
   - `SMTP_FROM_EMAIL`
5. After secrets are set, verify:
   - `/prospect status`
   - `/prospect`
   - AI drafting is active
   - email delivery works

## Important Commands

Local test:

```bash
uv run pytest
```

Deploy API:

```bash
./scripts/deploy_api.sh
```

Railway status:

```bash
npx @railway/cli@latest status
```

Set Railway variables manually:

```bash
npx @railway/cli@latest variable set KEY=value
```

Set a Railway secret from stdin:

```bash
printf '%s' "$VALUE" | npx @railway/cli@latest variable set KEY --stdin
```

## Important Environment / Deployment Assumptions

- Railway project: `alert-optimism`
- Production API service: `trade`
- Production API URL: `https://api.brivoly.com`
- Telegram webhook path:
  - `POST /api/telegram/webhook`
- Telegram webhook secret is now required in production

Current production prospecting defaults already configured on Railway:

- `PROSPECT_OPENAI_MODEL=gpt-5-nano`
- `PROSPECT_OPENAI_MAX_OUTPUT_TOKENS=500`
- `PROSPECT_EMAIL_RECIPIENT=tom.mg.walsh@gmail.com`
- `PROSPECT_REDDIT_SEARCH_TERMS=looking for stock market crash app,portfolio risk dashboard,market crash alert tool`
- `PROSPECT_REDDIT_LIMIT_PER_TERM=8`
- `PROSPECT_MAX_MATCHES=5`
- `PROSPECT_MIN_SCORE=12`
- `PROSPECT_VERBOSE_AUDIT=false`
- `PROSPECT_REDDIT_USER_AGENT=trade-prospecting-bot/0.1`
- `PROSPECT_APP_SUMMARY=Brivoly is a SaaS app for tracking market crash risk with a dashboard, risk signals, and alerts for investors who want to monitor portfolio conditions.`
- `SMTP_USE_TLS=true`

## Known Issues / Caveats

- Railway CLI `up --ci` intermittently times out talking to Railway GraphQL even when a deploy has actually started. Checking `railway status` and external health endpoints was more reliable than trusting CLI completion.
- Focused `pytest` runs fail due to the repo-wide `100%` coverage gate; use full `uv run pytest` for real verification.
- Production still reports:
  - `smtp_email: configured=false`
  - `openai: configured=false`
- The user asked at one point for the agent to “pretend you are human”; this was not implemented. The system remains honest/non-deceptive.

## Suggested Next Commit

Likely next commit after review:

```bash
git add prompts/PROSPECT.md README.md src/adapters/prospecting/runtime.py tests/test_prospecting_runtime.py src/adapters/social/composite_lead_source.py src/adapters/social/hacker_news_lead_source.py tests/test_composite_lead_source.py tests/test_hacker_news_lead_source.py
git commit -m "Add Hacker News source to prospecting agent"
git push origin master
```
