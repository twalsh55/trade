import Link from "next/link";
import { cookies } from "next/headers";

import { BrandLockup } from "@/components/brand-lockup";
import { Button } from "@/components/ui/button";
import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";
import { getSession, getSettingsBootstrap } from "@/lib/api";

export default async function HomePage() {
  const cookieStore = await cookies();
  const sessionToken =
    cookieStore.get(BRIVOLY_SESSION_COOKIE)?.value ?? cookieStore.get(LEGACY_TRADE_SESSION_COOKIE)?.value ?? null;
  const sessionCookie = cookieStore.get("__session")?.value;
  const cookieHeader = sessionCookie ? `__session=${sessionCookie}` : null;

  const [bootstrap, session] = await Promise.all([
    getSettingsBootstrap().catch(() => null),
    getSession({ sessionToken, cookieHeader }).catch(() => null),
  ]);

  const user = session?.user;

  return (
    <main className="min-h-screen overflow-hidden">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-6 lg:px-8">
        <section className="relative overflow-hidden rounded-[2rem] border border-white/70 bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(18,52,86,0.94)_42%,rgba(10,97,94,0.86))] px-6 py-8 text-white shadow-[0_30px_120px_-50px_rgba(15,23,42,0.8)] md:px-8 md:py-10">
          <div className="absolute inset-y-0 right-0 w-[40%] bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.22),transparent_55%)]" />
          <div className="relative flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <div className="flex items-center gap-4">
                <BrandLockup size="lg" priority />
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-200">Brivoly Workspace</p>
                  <h1 className="mt-2 text-4xl font-semibold tracking-tight md:text-6xl">
                    Two product portals.
                    <br />
                    One operating surface.
                  </h1>
                </div>
              </div>
              <p className="mt-6 max-w-2xl text-base leading-7 text-slate-200 md:text-lg">
                Choose the workflow you want to enter: the live market crash monitor that already runs today, or the
                CRM workspace for relationship and pipeline operations.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link href="/crash-monitor">Open Crash Monitor</Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="border-white/25 bg-white/10 text-white hover:bg-white/20">
                  <Link href="/crm">Open CRM Portal</Link>
                </Button>
                {user ? (
                  <div className="inline-flex items-center rounded-[1.25rem] border border-emerald-300/30 bg-emerald-300/15 px-4 py-3 text-sm font-medium text-emerald-50">
                    Signed in as {user.display_name ?? user.email ?? user.auth_subject}
                  </div>
                ) : bootstrap?.clerk_sign_in_url ? (
                  <Button asChild size="lg" variant="outline" className="border-white/25 bg-transparent text-white hover:bg-white/10">
                    <Link href="/sign-in?redirectTo=%2Fcrash-monitor">Sign in</Link>
                  </Button>
                ) : null}
              </div>
            </div>

            <div className="grid w-full gap-3 sm:grid-cols-3 lg:w-[360px] lg:grid-cols-1">
              <StatusChip label="Portal Count" value="2 active" tone="neutral" />
              <StatusChip label="Crash Monitor" value="Live today" tone="positive" />
              <StatusChip label="CRM" value="Portal ready" tone="warning" />
            </div>
          </div>
        </section>

        <section className="mt-6 grid gap-6 lg:grid-cols-2">
          <PortalCard
            eyebrow="Live Product"
            title="Market Crash Monitor"
            blurb="Track stress, participation, volatility, drawdowns, and action cues through the existing Python-backed dashboard."
            href="/crash-monitor"
            accent="from-emerald-100 via-white to-cyan-100"
            points={[
              "Authenticated dashboard with live charts and alert history",
              "Risk-score model remains in Python, not duplicated in the frontend",
              "Billing, settings, and dashboard refresh are already wired",
            ]}
            ctaLabel="Enter monitor"
          />

          <PortalCard
            eyebrow="Second Product"
            title="CRM App"
            blurb="A dedicated portal for pipeline, operator relationships, notes, follow-ups, and team memory as the CRM product takes shape."
            href="/crm"
            accent="from-amber-100 via-white to-rose-100"
            points={[
              "Reserved product surface instead of hiding future work in the root nav",
              "Clear destination for upcoming CRM workflows and onboarding",
              "Lets the homepage behave like a compact product switcher",
            ]}
            ctaLabel="Enter CRM portal"
          />
        </section>

        <section className="mt-6 grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="rounded-[1.75rem] border bg-white/80 p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Access Status</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
              {user ? "You are signed in and ready to work." : "Choose a workspace, then sign in when you’re ready."}
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
              {user
                ? "Your account is active on this device, so both product portals can load authenticated data and account-aware actions."
                : "You can browse the workspace hub first. When you open a protected flow, Brivoly will guide you through a clean sign-in and send you back to the right product area."}
            </p>
            <div className="mt-6 grid gap-3 md:grid-cols-3">
              <MiniTile label="Status" value={user ? "Signed in" : "Not signed in"} />
              <MiniTile label="Next stop" value={user ? "Open either portal" : "Sign in from CRM or crash monitor"} />
              <MiniTile label="Connection" value={bootstrap ? "Backend connected" : "Bootstrap unavailable"} />
            </div>
          </div>

          <div className="rounded-[1.75rem] border bg-slate-950 p-6 text-slate-50 shadow-[0_20px_70px_-45px_rgba(15,23,42,0.9)]">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">How Access Works</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight">Clear portal entry, clear sign-in state.</h2>
            <ul className="mt-5 space-y-3 text-sm leading-6 text-slate-300">
              <li>Each portal keeps its own purpose instead of mixing products on one screen.</li>
              <li>Protected flows now have a more explicit sign-in handoff and return path.</li>
              <li>The homepage tells you plainly whether your account is already active.</li>
            </ul>
          </div>
        </section>
      </div>
    </main>
  );
}

function PortalCard({
  eyebrow,
  title,
  blurb,
  href,
  accent,
  points,
  ctaLabel,
}: {
  eyebrow: string;
  title: string;
  blurb: string;
  href: string;
  accent: string;
  points: string[];
  ctaLabel: string;
}) {
  return (
    <section className={`rounded-[1.9rem] border bg-gradient-to-br ${accent} p-6 shadow-[0_24px_80px_-48px_rgba(15,23,42,0.35)]`}>
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{title}</h2>
      <p className="mt-3 max-w-xl text-sm leading-7 text-slate-700">{blurb}</p>
      <ul className="mt-6 space-y-3 text-sm leading-6 text-slate-700">
        {points.map((point) => (
          <li key={point} className="rounded-2xl border border-white/70 bg-white/65 px-4 py-3">
            {point}
          </li>
        ))}
      </ul>
      <div className="mt-6">
        <Button asChild size="lg">
          <Link href={href}>{ctaLabel}</Link>
        </Button>
      </div>
    </section>
  );
}

function StatusChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "positive" | "warning" | "neutral";
}) {
  const toneClass =
    tone === "positive"
      ? "border-emerald-300/30 bg-emerald-300/15 text-emerald-50"
      : tone === "warning"
        ? "border-amber-300/30 bg-amber-300/15 text-amber-50"
        : "border-white/15 bg-white/10 text-slate-100";

  return (
    <div className={`rounded-[1.4rem] border px-4 py-4 backdrop-blur ${toneClass}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.22em] opacity-80">{label}</p>
      <p className="mt-2 text-lg font-semibold">{value}</p>
    </div>
  );
}

function MiniTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="mt-3 text-base font-medium text-slate-900">{value}</p>
    </div>
  );
}
