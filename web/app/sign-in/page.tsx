import Link from "next/link";

import { BrandLockup } from "@/components/brand-lockup";
import { ClerkAuthBridge } from "@/components/auth/clerk-auth-bridge";
import { Button } from "@/components/ui/button";
import { getSettingsBootstrap } from "@/lib/api";
import { sanitizeRedirectTo } from "@/lib/auth";

export const dynamic = "force-dynamic";

type SignInPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function SignInPage({ searchParams }: SignInPageProps) {
  const resolvedSearchParams = (await searchParams) ?? {};
  const redirectValue = resolvedSearchParams.redirectTo;
  const redirectTo = sanitizeRedirectTo(Array.isArray(redirectValue) ? redirectValue[0] : redirectValue);
  const bootstrap = await getSettingsBootstrap().catch(() => null);

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
                  Sign in to open your relationship workspace.
                </h1>
              </div>
            </div>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-600">
              You are one step away from the same CRM workspace you land in after sign-in. Brivoly will restore your
              queue, notes, reminders, and follow-up context as soon as your session is secured.
            </p>
            <div className="mt-6 rounded-[1.5rem] border border-amber-200 bg-amber-50 px-5 py-4 text-amber-900">
              <p className="text-xs font-semibold uppercase tracking-[0.22em]">Guest mode in CRM</p>
              <p className="mt-2 text-lg font-semibold">No account session is active yet, so the live CRM queue is still locked.</p>
              <p className="mt-2 text-sm leading-6">
                Finish sign-in below and Brivoly will bring you straight into the follow-up workspace without making
                you re-orient.
              </p>
            </div>
            <div className="mt-8 flex flex-wrap gap-3">
              {bootstrap?.clerk_sign_up_url ? (
                <Button asChild size="lg" variant="outline">
                  <Link href={bootstrap.clerk_sign_up_url}>Create account</Link>
                </Button>
              ) : null}
            </div>
          </div>

          <div className="w-full max-w-md rounded-[1.75rem] border bg-slate-950 p-5 text-slate-50 shadow-[0_24px_80px_-50px_rgba(15,23,42,0.9)]">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">Portal Status</p>
            <div className="mt-4 space-y-3">
              <SignInStatusRow label="Session" value="Signing in on this device" />
              <SignInStatusRow label="Destination" value={redirectTo === "/crm" ? "CRM follow-up workspace" : "Brivoly CRM workspace"} />
              <SignInStatusRow label="Next step" value="Authenticate, then open your queue" />
            </div>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Before You Continue</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">The sign-in step should feel like part of the app.</h2>
          <p className="mt-3 text-sm leading-7 text-slate-600">
            This page now mirrors the CRM entry surface so the handoff feels more like a continuation than a detour.
          </p>
          <div className="mt-5 space-y-3">
            <InfoCard
              label="Current access state"
              body="You are not signed in yet. Complete sign-in here, then Brivoly will return you to the correct workspace."
            />
            <InfoCard
              label="What happens"
              body="Sign in below, Brivoly secures your session, then returns you to your workspace."
            />
            <InfoCard
              label="Why sign in"
              body="Your account unlocks live data, follow-up queues, saved settings, and account-level actions."
            />
          </div>
        </section>

        {bootstrap?.clerk_publishable_key && bootstrap.clerk_frontend_api_host ? (
          <ClerkAuthBridge
            publishableKey={bootstrap.clerk_publishable_key}
            host={bootstrap.clerk_frontend_api_host}
            redirectTo={redirectTo}
          />
        ) : (
          <section className="rounded-[1.75rem] border bg-white/85 p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Configuration</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">Sign-in is not configured yet</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Set <code>CLERK_PUBLISHABLE_KEY</code> so the frontend can render the sign-in form for users.
            </p>
            {bootstrap?.clerk_sign_in_url ? (
              <p className="mt-4 text-sm text-slate-600">
                Hosted fallback:{" "}
                <Link className="font-medium text-primary underline underline-offset-4" href={bootstrap.clerk_sign_in_url}>
                  {bootstrap.clerk_sign_in_url}
                </Link>
              </p>
            ) : null}
          </section>
        )}
      </section>
    </main>
  );
}

function SignInStatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="text-right text-sm text-slate-100">{value}</p>
    </div>
  );
}

function InfoCard({ label, body }: { label: string; body: string }) {
  return (
    <div className="rounded-[1.4rem] border bg-slate-50/80 px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">{label}</p>
      <p className="mt-2 text-sm leading-6 text-slate-700">{body}</p>
    </div>
  );
}
