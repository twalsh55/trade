import Link from "next/link";

import { BrandLockup } from "@/components/brand-lockup";
import { ClerkAuthBridge } from "@/components/auth/clerk-auth-bridge";
import { getSettingsBootstrap } from "@/lib/api";
import { sanitizeRedirectTo } from "@/lib/auth";

type SignInPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function SignInPage({ searchParams }: SignInPageProps) {
  const resolvedSearchParams = (await searchParams) ?? {};
  const redirectValue = resolvedSearchParams.redirectTo;
  const redirectTo = sanitizeRedirectTo(Array.isArray(redirectValue) ? redirectValue[0] : redirectValue);
  const bootstrap = await getSettingsBootstrap().catch(() => null);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col justify-center gap-6 px-4 py-10 lg:px-8">
      <section className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="rounded-[2rem] border bg-slate-950 p-8 text-slate-50 shadow-[0_30px_90px_-50px_rgba(15,23,42,0.8)]">
          <BrandLockup size="xl" priority />
          <div className="inline-flex items-center rounded-full border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-emerald-200">
            Welcome
          </div>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight">Your Brivoly workspace is one sign-in away.</h1>
          <p className="mt-4 text-sm leading-7 text-slate-300">
            Sign in once to open the CRM workspace or the crash monitor with your saved account access. The goal here
            is simple: make it obvious where you are, get you authenticated cleanly, and send you back into the app.
          </p>
          <div className="mt-8 grid gap-3 text-sm text-slate-300">
            <div className="rounded-[1.4rem] border border-white/10 bg-white/5 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-200">What happens</p>
              <p className="mt-2 leading-6">Sign in below, Brivoly secures your session, then returns you to your workspace.</p>
            </div>
            <div className="rounded-[1.4rem] border border-white/10 bg-white/5 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-200">Where you’ll land</p>
              <p className="mt-2 leading-6">
                {redirectTo === "/crm" ? "CRM follow-up workspace" : redirectTo === "/crash-monitor" ? "Crash monitor dashboard" : "Brivoly workspace hub"}
              </p>
            </div>
            <div className="rounded-[1.4rem] border border-white/10 bg-white/5 px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-amber-200">Why sign in</p>
              <p className="mt-2 leading-6">Your account unlocks live data, follow-up queues, saved settings, and account-level actions.</p>
            </div>
          </div>
          {bootstrap?.clerk_sign_up_url ? (
            <p className="mt-8 text-sm text-slate-300">
              Need an account?{" "}
              <Link className="font-medium text-cyan-200 underline underline-offset-4" href={bootstrap.clerk_sign_up_url}>
                Create one here
              </Link>
              .
            </p>
          ) : null}
        </div>

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
