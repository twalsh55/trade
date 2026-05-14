import Link from "next/link";

import { AlertsPanel } from "@/components/alerts/alerts-panel";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { BillingPanel } from "@/components/billing/billing-panel";
import { BrandLockup } from "@/components/brand-lockup";
import { DashboardWorkspace } from "@/components/dashboard/dashboard-workspace";
import { SettingsEditor } from "@/components/settings/settings-editor";
import type { ShellData } from "@/lib/types";

const navItems = [
  { label: "Overview", href: "#overview" },
  { label: "Components", href: "#crash-components" },
  { label: "Alerts", href: "#alerts" },
  { label: "Settings", href: "#settings" },
  { label: "Contracts", href: "#contracts" },
];

type AppShellProps = {
  data: ShellData;
};

export function AppShell({ data }: AppShellProps) {
  const user = data.session?.user;
  const alertItems = data.alerts?.items ?? [];
  const settings = data.settings;
  const riskScore = data.dashboard?.risk_score ?? null;
  const crashTone = getCrashTone(riskScore);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl gap-6 px-4 py-6 lg:px-8">
      <aside className="hidden w-72 shrink-0 rounded-[2rem] border bg-slate-950 p-6 text-slate-50 shadow-[0_24px_80px_-40px_rgba(15,23,42,0.7)] lg:block">
        <div className="space-y-3">
          <BrandLockup size="lg" priority />
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-300">Trade Control</p>
          <h1 className="text-3xl font-semibold tracking-tight">Crash Monitor</h1>
          <p className="text-sm leading-6 text-slate-300">
            Monitor market stress, participation, and crash-risk cues while Python remains the calculation engine.
          </p>
        </div>
        <nav className="mt-8 space-y-2">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="block rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-200 transition hover:border-cyan-300/40 hover:bg-white/10"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="mt-8 rounded-[1.5rem] border border-cyan-300/20 bg-cyan-300/10 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-200">Session</p>
          <p className="mt-2 text-lg font-medium">
            {user ? user.display_name ?? user.email ?? user.auth_subject : "Signed out"}
          </p>
          <p className="mt-2 text-sm text-slate-300">
            {user ? "Authenticated through the Python API layer." : "Connect Clerk session cookies to unlock live data."}
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col gap-6">
        <div className="rounded-[1.75rem] border bg-white/70 p-4 shadow-[0_20px_60px_-40px_rgba(15,23,42,0.35)] backdrop-blur lg:hidden">
          <BrandLockup size="md" priority />
        </div>

        <section className="rounded-[2rem] border bg-white/85 p-6 shadow-[0_30px_90px_-50px_rgba(15,23,42,0.35)] backdrop-blur md:p-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div className="max-w-3xl space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border bg-slate-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Live market dashboard
              </div>
              <h2 className="text-4xl font-semibold tracking-tight text-slate-950 md:text-5xl">
                Systematic crash-risk monitoring with live charts, percentiles, and action cues.
              </h2>
              <p className="max-w-2xl text-base leading-7 text-slate-600">
                The dashboard pulls price history, breadth, volatility, yield, and participation signals from the
                Python backend so the web app behaves like the original product rather than a thin frontend wrapper.
              </p>
            </div>

            <div className="grid min-w-[280px] gap-3 md:w-[360px]">
              <CrashIndicatorCard score={riskScore} tone={crashTone} />
              <div className="grid gap-3 md:grid-cols-2">
                <MetricCard
                  label="Alert Feed"
                  value={data.alerts ? `${data.alerts.count} recent items` : "Unavailable"}
                  tone={data.alerts ? "positive" : "neutral"}
                />
                <MetricCard
                  label="Environment"
                  value={data.bootstrap ? "Connected to bootstrap API" : "Bootstrap unavailable"}
                  tone={data.bootstrap ? "positive" : "warning"}
                />
              </div>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            {user ? (
              <SignOutButton />
            ) : (
              <Link
                href="/sign-in?redirectTo=%2F"
                className="inline-flex items-center justify-center rounded-full bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-sm transition hover:opacity-90"
              >
                Sign in
              </Link>
            )}
            {data.bootstrap?.clerk_sign_up_url ? (
              <Link
                href={data.bootstrap.clerk_sign_up_url}
                className="inline-flex items-center justify-center rounded-full border bg-white px-5 py-2.5 text-sm font-medium text-foreground transition hover:bg-secondary"
              >
                Create account
              </Link>
            ) : null}
          </div>
        </section>

        {data.errors.length > 0 ? (
          <section className="rounded-[1.75rem] border border-amber-300 bg-amber-50 p-5 text-amber-900">
            <p className="text-sm font-semibold uppercase tracking-[0.22em]">Connection notes</p>
            <ul className="mt-3 space-y-2 text-sm leading-6">
              {data.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </section>
        ) : null}

        <DashboardWorkspace initialDashboard={data.dashboard} settings={settings} bootstrap={data.bootstrap} />

        <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <Panel
            eyebrow="Account"
            title={user ? "Authenticated API session" : "Session bridge still pending"}
            description={
              user
                ? `${user.display_name ?? user.email ?? user.auth_subject} is mapped to an internal application user.`
                : "The Next.js shell is ready for Clerk session bootstrap, but no authenticated backend session was available for this render."
            }
          >
            <div className="space-y-3">
              <InfoRow label="Auth provider" value={user?.auth_provider ?? "clerk"} />
              <InfoRow label="Email" value={user?.email ?? "Not available"} />
              <InfoRow label="Last login" value={user ? formatDateTime(user.last_login_at) : "Pending session bridge"} />
              <InfoRow label="Sign up URL" value={data.bootstrap?.clerk_sign_up_url ?? "Configure CLERK_SIGN_UP_URL"} />
            </div>
          </Panel>

          <Panel
            eyebrow="Status"
            title="Latest backend snapshot"
            description="A concise readout of the most recent dashboard response returned from the Python API."
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <InfoTile label="Regime" value={data.dashboard?.regime ?? "Pending"} />
              <InfoTile
                label="Refreshed"
                value={data.dashboard ? formatDateTime(data.dashboard.refreshed_at) : "No snapshot"}
              />
              <InfoTile
                label="252D Drawdown"
                value={
                  typeof data.dashboard?.metrics.drawdown_252 === "number"
                    ? `${(data.dashboard.metrics.drawdown_252 * 100).toFixed(1)}%`
                    : "N/A"
                }
              />
              <InfoTile
                label="20D Vol"
                value={
                  typeof data.dashboard?.metrics.vol20 === "number"
                    ? `${(data.dashboard.metrics.vol20 * 100).toFixed(1)}%`
                    : "N/A"
                }
              />
              <InfoTile
                label="Breadth >200D"
                value={
                  typeof data.dashboard?.metrics.breadth_ratio === "number"
                    ? `${(data.dashboard.metrics.breadth_ratio * 100).toFixed(1)}%`
                    : "N/A"
                }
              />
              <InfoTile
                label="Yield Spread"
                value={
                  typeof data.dashboard?.metrics.yield_curve_spread === "number"
                    ? `${data.dashboard.metrics.yield_curve_spread.toFixed(2)}%`
                    : "N/A"
                }
              />
            </div>
          </Panel>
        </section>

        {user ? (
          <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
            <Panel
              eyebrow="Billing"
              title="Stripe subscription access"
              description="Manage the paid plan through Stripe Checkout and the customer portal without moving billing logic into the frontend."
            >
              <BillingPanel initialBilling={data.billing} />
            </Panel>
          </section>
        ) : null}

        <section id="alerts" className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
          <Panel
            eyebrow="Alert History"
            title="Recent feed"
            description="Refreshes through the Next.js proxy route while keeping Python as the source of truth."
          >
            <AlertsPanel initialItems={alertItems} />
          </Panel>

          <Panel
            eyebrow="Signals"
            title="Live dashboard plumbing"
            description="The frontend refreshes through local API routes while the Python backend owns the calculations."
          >
            <ul className="space-y-3 text-sm leading-6 text-slate-700">
              <li>Dashboard filters refresh live through <code>/api/dashboard</code>.</li>
              <li>Settings save through <code>/api/account/settings</code> and emit a local refresh event.</li>
              <li>Alert history refreshes independently through <code>/api/alerts/history</code>.</li>
              <li>Server-rendered pages still hydrate from the Python backend for consistency.</li>
            </ul>
          </Panel>
        </section>

        <section id="settings" className="grid gap-6 xl:grid-cols-[1fr_1fr]">
          <Panel
            eyebrow="Settings"
            title="User dashboard defaults"
            description="Persist settings changes through the local Next.js proxy and trigger a fresh dashboard snapshot."
          >
            <SettingsEditor
              initialSettings={settings}
              fallbackUniverse={data.bootstrap?.default_universe ?? ["SPY", "QQQ", "IWM", "EFA", "EEM"]}
              fallbackLookbackYears={data.bootstrap?.default_lookback_years ?? 4}
            />
          </Panel>

          <div id="contracts">
            <Panel
              eyebrow="Contracts"
              title="Active API surface"
              description="These routes now power the live web app and are covered by the Python test suite."
            >
              <ul className="space-y-3 text-sm leading-6 text-slate-700">
                <li><code>GET /api/session</code> for auth bootstrap</li>
                <li><code>GET /api/dashboard</code> for snapshot data</li>
                <li><code>GET /api/dashboard?...filters</code> for interactive refresh</li>
                <li><code>GET/PUT /api/account/settings</code> for user defaults</li>
                <li><code>GET /api/alerts/history</code> for the alert feed</li>
              </ul>
            </Panel>
          </div>
        </section>
      </div>
    </main>
  );
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "positive" | "warning" | "critical" | "neutral";
}) {
  const toneClass =
    tone === "positive"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : tone === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-900"
        : tone === "critical"
          ? "border-rose-200 bg-rose-50 text-rose-900"
          : "border-slate-200 bg-slate-50 text-slate-900";

  return (
    <div className={`rounded-[1.4rem] border p-4 ${toneClass}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.22em]">{label}</p>
      <p className="mt-2 text-lg font-semibold">{value}</p>
    </div>
  );
}

function CrashIndicatorCard({
  score,
  tone,
}: {
  score: number | null;
  tone: "positive" | "warning" | "critical" | "neutral";
}) {
  const shellClass =
    tone === "positive"
      ? "border-emerald-200 bg-gradient-to-br from-emerald-50 via-white to-emerald-100/80 text-emerald-950"
      : tone === "warning"
        ? "border-amber-200 bg-gradient-to-br from-amber-50 via-white to-amber-100/80 text-amber-950"
        : tone === "critical"
          ? "border-rose-200 bg-gradient-to-br from-rose-50 via-white to-rose-100/80 text-rose-950"
          : "border-slate-200 bg-gradient-to-br from-slate-50 via-white to-slate-100 text-slate-950";

  const chipClass =
    tone === "positive"
      ? "bg-emerald-600"
      : tone === "warning"
        ? "bg-amber-500"
        : tone === "critical"
          ? "bg-rose-500"
          : "bg-slate-400";

  const meterClass =
    tone === "positive" ? "bg-emerald-500" : tone === "warning" ? "bg-amber-500" : tone === "critical" ? "bg-rose-500" : "bg-slate-400";

  const clampedScore = score === null ? 0 : Math.max(0, Math.min(score, 100));

  return (
    <Link
      href="#crash-components"
      aria-label="View crash components"
      className={`block rounded-[1.6rem] border p-5 shadow-sm transition hover:shadow-md ${shellClass}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] opacity-75">Crash Indicator</p>
          <p className="mt-3 text-5xl font-semibold tracking-tight">{score === null ? "N/A" : `${score.toFixed(1)}%`}</p>
          <p className="mt-3 max-w-xs text-sm leading-6 opacity-80">
            {score === null
              ? "Sign in to load the current crash indicator."
              : tone === "critical"
                ? "High stress. Scroll down to inspect the largest component penalties."
                : tone === "warning"
                  ? "Fragile regime. Scroll down to see which components are driving caution."
                  : "Constructive regime. Scroll down to inspect the component mix behind the score."}
          </p>
        </div>
        <div className="shrink-0 rounded-full border border-black/5 bg-white/70 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em]">
          <span className={`mr-2 inline-block h-2.5 w-2.5 rounded-full ${chipClass}`} />
          Components
        </div>
      </div>
      <div className="mt-5 h-3 overflow-hidden rounded-full bg-white/70">
        <div className={`h-full rounded-full ${meterClass}`} style={{ width: `${clampedScore}%` }} />
      </div>
    </Link>
  );
}

function Panel({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[1.75rem] border bg-white/80 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">{eyebrow}</p>
      <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">{title}</h3>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="mt-3 text-base font-medium text-slate-900">{value}</p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl border bg-slate-50 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="text-right text-sm text-slate-700">{value}</p>
    </div>
  );
}

function getCrashTone(score: number | null): "positive" | "warning" | "critical" | "neutral" {
  if (score === null) {
    return "neutral";
  }
  if (score >= 70) {
    return "critical";
  }
  if (score >= 50) {
    return "warning";
  }
  return "positive";
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
