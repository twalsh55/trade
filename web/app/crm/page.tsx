import Link from "next/link";
import { cookies } from "next/headers";

import { BrandLockup } from "@/components/brand-lockup";
import { CRMFollowUpWorkspace } from "@/components/crm-follow-up-workspace";
import { Button } from "@/components/ui/button";
import { BRIVOLY_SESSION_COOKIE, LEGACY_TRADE_SESSION_COOKIE } from "@/lib/auth";
import { getCrmFollowUpOverview, getSession, getSettingsBootstrap } from "@/lib/api";

export default async function CRMPortalPage() {
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
  const followUps = user ? await getCrmFollowUpOverview({ sessionToken, cookieHeader }).catch(() => null) : null;

  return (
    <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-6 lg:px-8">
      <section className="overflow-hidden rounded-[2rem] border bg-white/85 p-6 shadow-[0_30px_100px_-55px_rgba(15,23,42,0.4)] backdrop-blur md:p-8">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex items-center gap-4">
              <BrandLockup size="lg" priority />
              <div>
                <p className="bg-gradient-to-r from-[#034CFD] to-[#01113B] bg-clip-text text-xs font-semibold uppercase tracking-[0.28em] text-transparent">
                  CRM Portal
                </p>
                <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950 md:text-5xl">
                  Relationship ops, pipeline visibility, and follow-up memory.
                </h1>
              </div>
            </div>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-600">
              This portal gives the CRM product its own destination now, even before the full workflow surface lands.
              It is the place to grow deal tracking, notes, customer follow-up, and operator context without cluttering
              the crash-monitor experience.
            </p>
            <div className={`mt-6 rounded-[1.5rem] border px-5 py-4 ${user ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
              <p className="text-xs font-semibold uppercase tracking-[0.22em]">{user ? "Signed in to CRM" : "Guest mode in CRM"}</p>
              <p className="mt-2 text-lg font-semibold">
                {user
                  ? `${user.display_name ?? user.email ?? user.auth_subject} is recognized on this device.`
                  : "No account session is active, so the live CRM queue is locked."}
              </p>
              <p className="mt-2 text-sm leading-6">
                {user
                  ? `Welcome back, ${user.display_name ?? user.email ?? user.auth_subject}. Your follow-up queue and account history are ready below.`
                  : "You can look around the CRM portal now, but sign in to open the actual follow-up queue, notes, relationship memory, and account history."}
              </p>
            </div>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/">Back to portal hub</Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href="/crash-monitor">Open crash monitor</Link>
              </Button>
              {!user && bootstrap?.clerk_sign_in_url ? (
                <Button asChild size="lg" variant="outline">
                  <Link href="/sign-in?redirectTo=%2Fcrm">Sign in</Link>
                </Button>
              ) : null}
            </div>
          </div>

          <div className="w-full max-w-md rounded-[1.75rem] border bg-slate-950 p-5 text-slate-50 shadow-[0_24px_80px_-50px_rgba(15,23,42,0.9)]">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Portal Status</p>
            <div className="mt-4 space-y-3">
              <CRMStatusRow label="Session" value={user ? "Signed in and recognized" : "Guest access only"} />
              <CRMStatusRow label="Live CRM data" value={followUps ? "Queue, notes, and timeline loaded" : "Blocked until sign-in"} />
              <CRMStatusRow label="Next step" value={user ? "Work the follow-up queue" : "Sign in to unlock your queue"} />
            </div>
          </div>
        </div>
      </section>

      {followUps ? (
        <CRMFollowUpWorkspace initialOverview={followUps} />
      ) : (
        <>
          <section className="mt-6 rounded-[1.75rem] border border-amber-200 bg-amber-50 p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-amber-700">Before you continue</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-amber-950">Sign in to unlock the real CRM workspace.</h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-amber-900">
              The live product starts with a follow-up-first queue. Signing in connects your account so Brivoly can load your leads, notes, timeline, and next actions cleanly.
            </p>
            {bootstrap?.clerk_sign_in_url ? (
              <div className="mt-5">
                <Button asChild size="lg">
                  <Link href="/sign-in?redirectTo=%2Fcrm">Sign in to open CRM</Link>
                </Button>
              </div>
            ) : null}
          </section>
          <section className="mt-6 grid gap-6 lg:grid-cols-3">
            <FeatureCard
              title="Pipeline"
              body="Track active deals, stages, blockers, and next actions in one operational queue."
            />
            <FeatureCard
              title="Relationship Memory"
              body="Keep notes, conversations, and context close to the account instead of scattered across inboxes."
            />
            <FeatureCard
              title="Follow-up Rhythm"
              body="Use reminders and lightweight workflows to keep opportunities warm without manual sprawl."
            />
          </section>
        </>
      )}
    </main>
  );
}

function CRMStatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="text-right text-sm text-slate-100">{value}</p>
    </div>
  );
}

function FeatureCard({ title, body }: { title: string; body: string }) {
  return (
    <section className="rounded-[1.6rem] border bg-white/80 p-6 shadow-sm">
      <h2 className="text-2xl font-semibold tracking-tight text-slate-950">{title}</h2>
      <p className="mt-3 text-sm leading-7 text-slate-600">{body}</p>
    </section>
  );
}
