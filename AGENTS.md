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
  - `GET /api/crm/calendars`
  - `POST /api/crm/calendars/connect`
  - `POST /api/crm/calendars/events`
  - `POST /api/crm/inbox/mailboxes/oauth/start`
  - `POST /api/crm/inbox/mailboxes/oauth/complete`
  - `POST /api/crm/inbox/watch-events/{provider}`
  - `POST /api/crm/import/preview`
  - `POST /api/crm/import`
  - `GET /api/crm/intake-channel`
- Internal founder-code bridge route is live:
  - `GET /api/internal/founder-code-requests`

## Deployment Notes

- Railway deploys the API from repo root using `Dockerfile`, `railway.toml`, and `scripts/start_railway.sh`.
- Vercel uses `web/` as project root.
- Important envs:
  - API: `DATABASE_URL`, Clerk vars, Stripe vars, Telegram vars, `APP_OPENAI_API_KEY`/`OPENAI_API_KEY`, `ALLOW_ANONYMOUS_CRM`, Google OAuth vars, Microsoft OAuth vars, `MAILBOX_WATCH_WEBHOOK_SECRET`
  - Web: `BRIVOLY_API_BASE_URL`, `APP_BASE_URL`, Clerk frontend vars
- Preferred smoke checks:
  - `uv run pytest`
  - `cd web && rm -rf .next && npm run typecheck`
  - `cd web && npm run build`
  - `cd web && npm run e2e`

## Fast Start

### Current Product

- Brivoly's main live product surface is `clientos`.
- `crash-monitor` still exists in the repo, but Client OS is the active product direction.
- Standing product constraint:
  - optimize for near-zero pain
  - avoid copy/paste and unnecessary typing
  - prefer strong recommendations and acceptance flows over blank forms
  - reduce freelancer mental overhead first
  - keep the product calm, lightweight, and emotionally survivable
  - avoid enterprise dashboards, reporting sprawl, operational clutter, and CRM jargon
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
  - temporary yellow/black sitewide under-construction banner is live
  - left taskbar with dedicated Client OS pages
  - CRM relationship memory now persists in Postgres when `DATABASE_URL` is configured, including imported follow-ups, notes, timeline history, and inbox-ingested thread state
  - anonymous guest mode now bootstraps the sample relationship set once into durable CRM storage instead of rebuilding it from process memory on every restart
  - Today priorities now collapse into one obvious `Start here` move, lighter `Needs care now` and `Freshest opening` summaries, direct draft/review actions, stronger upload-aware next-touch framing, a lightweight `Prepare now` path for upcoming meeting-like moments, and a clearer `Next move` cue on each priority so the daily home asks for less scanning
  - follow-up queue
  - inbox-native relationship page for auto-logging email threads and reconnect-aware next moves
  - mailbox beta now includes real Gmail / Outlook OAuth-ready connection start/complete routes, provider-backed sync for OAuth-linked accounts, provider-watch event callbacks, and provider-backed sending through Gmail API / Microsoft Graph when those accounts are connected
  - calendar beta now includes durable Google Calendar / Outlook Calendar connection records plus meeting-event ingest into relationship memory so upcoming conversations can feed Today and meeting prep
  - connected mailbox cards now support disconnecting accounts, pausing or resuming scheduled background sync per mailbox, refreshing provider watch coverage, and clearer reauth / health-state visibility without losing the saved relationship memory
  - connected mailbox cards now also surface reconnect-needed and stale-sync cues more explicitly, including a direct reconnect path for OAuth inboxes when Brivoly can no longer quietly refresh them
  - connected calendar cards now support connect/disconnect, pause/resume background meeting memory, and a lightweight meeting-ingest path for bringing scheduled conversations straight into relationship memory
  - connected calendar cards now also keep track of the latest meeting context they saved, surface when meeting memory has gone quiet, and help Today / Attention distinguish between truly warm calendar context and merely connected calendar coverage
  - manual mailbox connection still exists as a fallback beta path when provider credentials are not configured yet
  - inbox cards now surface backend-driven relationship pulse, open-loop memory, thread continuity cues, `what changed` hints, unresolved-thread cues, a clearer long-thread `through-line`, and a carry-forward cue for longer threads, grouped into `Needs you now` and `Still warm`
  - email-thread ingestion that can auto-create/update contacts from inbox activity
  - mailbox sync now feeds the same inbox-ingest path Brivoly already uses, so provider-synced email activity and provider watch callbacks land in relationship memory instead of a separate mailbox subsystem
  - sending a drafted note now writes the outbound message back into the same relationship timeline and thread history, including notes sent through the provider-backed mailbox path, now carries forward stored external message ids for better reply continuity, and now keeps the selected inbox thread attached all the way from Inbox / Today into the composer send path
  - provider-backed sends now also return a calmer continuity note so Brivoly can tell the user whether it truly replied inside the same Gmail / Outlook conversation or had to fall back to a fresh provider note while still keeping relationship memory attached
  - account settings now include locale defaults, retention-window defaults, an AI-processing toggle, and privacy-consent metadata as the first localization/GDPR groundwork layer
  - `/api/account/privacy/export` and the settings export action can now download a JSON snapshot of account settings, connected mailboxes, and stored relationship memory for GDPR-oriented export groundwork
  - `/api/account/privacy/erase` and the settings erase actions can now clear stored relationship memory or wipe memory plus connected mailbox links as an early GDPR delete/control path
  - attention view with reconnect-first guidance and direct draft actions
  - complete and snooze actions
  - relationship history + internal notes
  - relationship memory summaries now blend email, notes, uploads, reconnect cues, recent upload context, and upcoming meeting prep signals, with lighter `Conversation memory` and `Latest saved context` reads instead of repetitive stacked boxes
  - relationship pages now surface upcoming meeting-like moments with a direct `Prepare me` path into the meeting-prep memory view when Brivoly detects that a near-term next touch looks like a call, demo, review, or sync
  - explicit calendar events now land as `meeting` timeline context, can temporarily become the next prep moment, and feed the existing meeting-prep summary layer instead of living in a separate calendar silo
  - recent client-shared context now has its own memory view, can be pulled straight into the next drafted note, generates a backend-driven follow-through hint, creates a more natural reconnect path, and now plays a bigger role in meeting prep, 30-day summaries, follow-through guidance, Today priorities, and inbox-side next moves
  - auto note designer for reconnects and follow-ups with in-app draft editing
  - last meaningful interaction tracking
  - dormant client detection
  - warm intro graph
  - referral reminders
  - birthday and company milestone reminders
  - relationship health scoring
  - CSV/XLSX/XLS/Google Sheets import
  - guided field mapping
  - import wording now leans further into memory recovery, lighter `next touch` language, and cleaner `Google Sheets` labels
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
  - client-facing upload flow with quieter `Client dropzone` language, simpler share-link language, calmer set-once defaults, and camera-friendly mobile capture
  - relationship history now visually calls out client-shared upload context instead of burying it in generic activity
  - intake setup now has calmer set-once defaults for channels, handoff notes, source formats, and AI memory prompts to reduce typing and configuration
  - reconnect guidance now includes a clearer `why it can still land` read plus a starter line for reopening stale, drifting, and at-risk relationships, with gentler company-aware and saved-context fallbacks when Brivoly has thinner history and a softer sparse-context restart path when almost nothing is saved yet
  - intake and attention copy now lean further into relationship continuity and away from setup / pipeline language
  - text-heavy card layouts now prefer wider 2-column patterns so copy does not collapse into cramped narrow cards
  - shell, taskbar, import, relationship-memory, and handoff copy now consistently point to Client OS instead of older workspace/portal language
  - overview density is calmer now, with lighter warm-intro panels, a simpler relationship continuity read, a lighter conversation-memory stack in inbox follow-through, a less repetitive relationship-memory panel, and a less dashboard-like fallback shell
  - intake defaults now read more like set-it-and-forget-it guidance, with quieter `Client dropzone` language, lighter `Usual path` / `What to notice` wording, `First / Next / Then` task framing, recommended helper actions, and simple `Save` actions instead of configuration-heavy language
  - auth, shell fallback, API fallback, loading, draft-composer, and client-upload surfaces now use calmer language and lighter guidance with less system-heavy phrasing
  - Today navigation and other dense summary areas are progressively flattening into lighter pills and calmer summaries instead of equal-weight cards
  - scheduled mailbox automation now reports both watch-ready and event-ready inbox coverage so the always-on sync layer is easier to reason about than a raw thread count alone
  - Today, Inbox, Attention, and Relationships now quietly refresh from connected inbox/calendar memory while the page is open, so fresh context can surface without asking the user to manually refresh
  - Today and Attention now surface whether Brivoly is still holding context quietly in the background or whether paused / reconnect-needed inbox and calendar connections are starting to thin that memory layer out
  - Today and Attention now distinguish between event-ready inboxes, warm calendar context, and background memory that is technically on but waiting for fresh live context to land
  - mailbox and calendar DTOs now carry Python-owned continuity states and summaries, so the Client OS shell can describe warm, quiet, paused, reconnect-needed, and event-ready memory without re-deriving those states in TypeScript
  - the CRM follow-up overview now also carries a Python-owned ambient memory summary, so Today and Attention can read one shared continuity posture for inbox + calendar memory instead of rebuilding the top-level story in the frontend
  - that ambient memory summary now also suggests the calmest next recovery move, so Today and Attention can offer one small fix such as checking connections, resuming memory, or connecting a source instead of just describing the state
  - that shared ambient memory summary now also carries specific paused and attention-needed source labels, so Today and Attention can quietly point to the exact inboxes or calendars thinning Brivoly's memory layer without adding a new admin surface
  - that shared ambient memory summary now also carries warm and quiet source labels, and its recovery actions are more specific about whether Brivoly wants the user to check inboxes, calendars, or resume one kind of memory instead of showing one generic fix for every continuity state
  - those ambient-memory recovery actions now also carry a short Python-owned note and route through in-app navigation, so Today and Attention can explain the smallest useful fix without bouncing the user through a full page reload

### Relationship OS Todo

- Positioning and language:
  - [ ] replace remaining visible CRM/pipeline/workflow language with relationship-first language
  - [ ] make `Today` feel like the default home for daily attention, not a dashboard
  - [ ] keep copy focused on memory, continuity, warmth, follow-through, and reduced mental overhead
  - [ ] keep navigation feeling like cognitive states such as `Today`, `Attention`, `Inbox`, `Saved Context`, `Relationships`, and `Dropzones`, not software modules
- Relationship continuity:
  - [ ] strengthen the `Today’s relationship priorities` surface around reply, reconnect, proposal follow-up, and new uploads
  - [ ] make stale and at-risk relationships more prominent than generic stage progress
  - [ ] improve dormant conversation reopening flows and suggested reconnect actions
  - [ ] make the relationship timeline the primary object so everything converges into what happened, what changed, what matters now, and what needs attention
- Inbox-native behavior:
  - [ ] deepen auto-create/update from email so the inbox feels like the default relationship memory source
  - [ ] improve AI summaries for threads so recent context is easier to trust at a glance
  - [ ] add faster inbox search and quick actions with minimal manual entry
- Client Dropzones:
  - [ ] keep no-login upload links extremely mobile-friendly and low-friction
  - [ ] attach uploaded files, screenshots, and notes more clearly to relationship history
  - [ ] continue removing any operator-heavy intake language from the remaining setup surfaces
- UX constraints:
  - [ ] reduce equal-weight panels, counters, and dashboard-style density
  - [ ] keep the interface calm, lightweight, and fast on both desktop and mobile
  - [ ] favor strong defaults and guidance over configuration-heavy controls
  - [ ] keep Brivoly feeling like a quiet background assistant instead of management software
  - [ ] preserve generous whitespace, soft hierarchy, restrained colors, and low visual noise
  - [ ] remove unnecessary helper text, clicks, and visual weight before shipping each surface
- Ambient AI direction:
  - [ ] keep AI embedded inside workflows instead of exposing chatbot-first interfaces
  - [ ] make AI feel like relationship memory, not like a visible assistant asking for prompts
  - [ ] use AI most where users feel uncertainty, forgetfulness, or friction
  - [ ] prefer invisible context recovery, timing nudges, and editable suggestions over autonomous behavior
  - [ ] avoid giant AI sidebars, prompt-heavy UX, agent complexity, and enterprise AI dashboards

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
- Local automation can now also run scheduled mailbox sync when `AUTOMATION_ENABLE_MAILBOX_SYNC=true`.
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
  - harden the mailbox and calendar connection layer so Brivoly can quietly keep relationship memory current with less manual sync, cleaner reconnect flows, and safer provider failure handling
  - move mailbox sync fully toward event-driven continuity through provider webhooks or watch subscriptions so inbox memory updates feel ambient instead of manually maintained
  - deepen provider-backed send and reply behavior so Brivoly can preserve thread continuity after outbound notes, especially in Outlook edge cases
  - keep sharpening `Today` into the unquestioned daily home with the smallest useful next move, less scanning, and more emotionally clear attention cues
  - strengthen the `Attention` model around drifting, stale, and at-risk relationships without introducing lead scoring, forecasting, or enterprise analytics
  - deepen the relationship timeline as the primary object so meetings, uploads, email, notes, decisions, and saved context all converge into one continuity layer
  - deepen inbox-native memory around what changed, what matters now, unresolved topics, and the cleanest next reply across longer conversations
  - expand pre-meeting context so upcoming meetings feel fully prepared from saved context, recent email, uploads, and unresolved threads without a separate planning workflow
  - let client-shared uploads shape more of `Today`, meeting prep, reconnects, and suggested next moves so dropzones feel easier than attachments and more useful than file storage
  - keep simplifying dropzones until they feel like invisible client handoff pages with almost no setup friction
  - strengthen onboarding from real data sources beyond spreadsheets so live inboxes and calendars become the normal path into Client OS memory
  - deepen the real-world client model only where it supports continuity, such as projects, engagements, and decision context, without drifting into project-management sprawl
  - turn the locale groundwork into true multilingual support across Client OS copy, formatting, reminders, memory views, and drafted notes
  - deepen GDPR from groundwork into fuller consent, export, erase, retention, processor-disclosure, and data-minimization controls for relationship memory, uploads, and connected mailbox data
  - keep removing the last pockets of CRM-ish, dashboard-ish, or operational language so the product consistently sounds like calm relationship memory rather than management software
  - keep reducing UI density through fewer counters, fewer equal-weight panels, softer hierarchy, and more whitespace
  - improve production trust and resilience with stronger empty states, safer auth/session behavior, and fewer smart-prototype moments
  - refine billing and packaging so premium boundaries are clear without adding enterprise-style packaging clutter
  - add a fuller reminder layer outside the app through inbox, calendar, and email touchpoints while still keeping the experience low-admin
  - add admin and support visibility for sync state, import failures, and memory health without exposing internal operational complexity to end users
  - keep AI ambient and invisible by embedding timing nudges, context recall, timeline summaries, reconnect suggestions, and draft help directly into workflows instead of adding chatbot-first surfaces

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
