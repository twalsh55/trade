# AGENTS

## Core Rules

- Read `HANDOFF.md` at the start of a new session if it exists.
- Keep domain logic in Python (`src/domain`, `src/application`); keep the web app as a UI/API client.
- Preserve hexagonal boundaries and SOLID principles.
- Do not duplicate core business logic in TypeScript.
- Update this file when the stack, architecture, deployment model, or core workflows materially change.
- Refresh `Fast Start` at the end of each meaningful session.

## Stack

- Backend: Python 3.12, `uv`, FastAPI, PostgreSQL (`psycopg`)
- Frontend: Next.js, TypeScript, Tailwind, `shadcn/ui`
- Auth: Clerk with internal Postgres-backed users
- Billing: Stripe
- Notifications: Telegram + SMTP email
- AI: OpenAI API
- Deploy: Railway (API), Vercel (web)
- Tests: `pytest`, Playwright

## Architecture

- `src/domain`: pure business rules and entities
- `src/application`: use-cases, DTOs, ports
- `src/adapters`: HTTP, persistence, auth, billing, notifications, external integrations
- `web/`: authenticated SaaS UI

Python is the source of truth for product logic. The web app should only cross the boundary through explicit API contracts.

## Common Commands

```bash
uv sync
uv run uvicorn src.adapters.api.app:app --reload
uv run pytest
./scripts/deploy_api.sh
./scripts/deploy_web.sh
./scripts/deploy_prod.sh
cd web && npm run dev
cd web && rm -rf .next && npm run typecheck
cd web && npm run build
cd web && npm run e2e
```

## Key API Surface

- Health/session/dashboard/settings/billing routes are live.
- CRM routes are live, including:
  - `GET /api/crm/followups`
  - `PATCH /api/crm/followups/{id}`
  - `POST /api/crm/import/preview`
  - `POST /api/crm/import`
  - `GET /api/crm/intake-channel`
- Internal founder-code bridge route is live:
  - `GET /api/internal/founder-code-requests`

## Deployment Notes

- Railway deploys the API from repo root using `Dockerfile`, `railway.toml`, and `scripts/start_railway.sh`.
- Vercel uses `web/` as project root.
- Important envs:
  - API: `DATABASE_URL`, Clerk vars, Stripe vars, Telegram vars, `APP_OPENAI_API_KEY`/`OPENAI_API_KEY`, `ALLOW_ANONYMOUS_CRM`
  - Web: `BRIVOLY_API_BASE_URL`, `APP_BASE_URL`, Clerk frontend vars
- Preferred smoke checks:
  - `uv run pytest`
  - `cd web && rm -rf .next && npm run typecheck`
  - `cd web && npm run build`
  - `cd web && npm run e2e`

## Fast Start

### Current Product

- Brivoly has two live surfaces:
  - `crash-monitor`
  - `clientos`
- Standing product constraint:
  - optimize for near-zero pain
  - avoid copy/paste and unnecessary typing
  - prefer strong recommendations and acceptance flows over blank forms
- Current main focus: Client OS.
- Current Client OS wedge:
  - follow-up-first
  - spreadsheet-friendly
  - relationship-memory oriented
  - aimed at freelancers, consultants, agencies, and SMB service workflows

### Client OS State

- `/clientos` is the primary production route and currently allows anonymous guest access when `ALLOW_ANONYMOUS_CRM=true`.
- `/crm` remains as a compatibility alias.
- Current Client OS capabilities:
  - left taskbar with dedicated Client OS pages
  - follow-up queue
  - inbox-native relationship page for auto-logging email threads
  - email-thread ingestion that can auto-create/update contacts from inbox activity
  - attention board view by relationship stage
  - complete and snooze actions
  - relationship history + internal notes
  - auto email designer for reconnects and follow-ups with in-app draft editing
  - last meaningful interaction tracking
  - dormant client detection
  - warm intro graph
  - referral reminders
  - birthday and company milestone reminders
  - relationship health scoring
  - CSV/XLSX/XLS/Google Sheets import
  - guided field mapping
  - import now preserves mapped priority, contact channel, and next step from source sheets instead of replacing them with generic defaults
  - import preview now shows the actual staged priority, channel, and next step before commit
  - duplicate detection + validation preview
  - AI header rescue for messy spreadsheets
  - interactive AI clarification questions when mapping is still ambiguous
  - clarification is now presented one question at a time with automatic re-check after each answer
  - best-effort import preview retry and friendlier fallback messaging instead of raw request-failure text
  - commit blocked until required clarification is resolved
  - paid AI intake profile per user
  - first-login business onboarding with skip-for-now path
  - paid image-note intake
  - magic-link remote note capture for phone image uploads

### Relationship OS Todo

- Positioning and language:
  - [ ] replace remaining visible CRM/pipeline/workflow language with relationship-first language
  - [ ] make `Today` feel like the default home for daily attention, not a dashboard
  - [ ] keep copy focused on memory, continuity, warmth, follow-through, and reduced mental overhead
- Relationship continuity:
  - [ ] strengthen the `Today’s relationship priorities` surface around reply, reconnect, proposal follow-up, and new uploads
  - [ ] make stale and at-risk relationships more prominent than generic stage progress
  - [ ] improve dormant conversation reopening flows and suggested reconnect actions
- Inbox-native behavior:
  - [ ] deepen auto-create/update from email so the inbox feels like the default relationship memory source
  - [ ] improve AI summaries for threads so recent context is easier to trust at a glance
  - [ ] add faster inbox search and quick actions with minimal manual entry
- Client Dropzones:
  - [ ] keep no-login upload links extremely mobile-friendly and low-friction
  - [ ] attach uploaded files, screenshots, and notes more clearly to relationship history
  - [ ] continue removing any operator-heavy intake language from the capture flow
- UX constraints:
  - [ ] reduce equal-weight panels, counters, and dashboard-style density
  - [ ] keep the interface calm, lightweight, and fast on both desktop and mobile
  - [ ] favor strong defaults and guidance over configuration-heavy controls
  - [ ] keep Brivoly feeling like a quiet background assistant instead of management software

### Agent / Automation State

- Prospect agent is currently disabled by default via `PROSPECT_AGENT_ENABLED=false`.
- Prospecting is tuned to `crm_direction`.
- Repeated validated signals:
  - follow-up discipline
  - spreadsheet-held CRM workflows
  - pipeline hygiene
  - relationship memory
- Strong secondary idea, still not core: message / DM capture.
- `/code` in Telegram can:
  - take founder guidance
  - queue durable work items
- when the prospect agent is re-enabled, `/code` can also run cooperative prospecting for a build recommendation
- Prospect-agent recommendations can also enter that same durable queue.
- Local always-on automation is the main 24/7 path.
- Local worker can sync/stage remote requests and launch headless `codex exec` runs.
- Progress from remote runs is forwarded via Telegram/email.
- Local app automation should prefer `APP_OPENAI_API_KEY` over `OPENAI_API_KEY`.

### Current Deployment / Verification Reality

- API target: Railway
- Web target: Vercel
- Local typecheck is safest with:
  - `cd web && rm -rf .next && npm run typecheck`
- Current reliable verification standard:
  - `uv run pytest`
  - `cd web && npm run build`
  - `cd web && npm run e2e`

### Next Likely Moves

- Highest-conviction Client OS next steps:
  - finish the relationship-OS copy cleanup across remaining user-facing surfaces
  - make `Today` the clearest expression of who needs attention right now
  - deepen inbox-native memory and thread summaries
  - make dropzones feel more like lightweight client handoff pages and less like intake tooling
  - deeper AI-assisted messy file / image intake behind the paid gate
  - richer stage memory / handoff history
  - spreadsheet cleanup and field-mapping controls after preview
  - consultant / agency templates

## Autonomy Rule

- If product direction is already clear, proactively implement the next high-conviction feature set.
- Each coherent change set should include:
  - implementation
  - local verification
  - commit
  - push
  - deploy when the affected surface is live and credentials already exist
- Use existing briefing/email mechanisms to keep the founder updated.
- Pause only for hidden-risk, destructive, or high-ambiguity changes.

## Handoff Rule

If the user writes the exact prompt `handoff`, create or overwrite `HANDOFF.md` with:

- current project state
- what was completed this session
- what is still in progress
- next recommended steps
- important run/deploy commands
- known issues, risks, or caveats
- active architectural or deployment assumptions
