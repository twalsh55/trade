import Link from "next/link";

import { BrandLockup } from "@/components/brand-lockup";
import { ClerkAuthBridge } from "@/components/auth/clerk-auth-bridge";
import { getSettingsBootstrap } from "@/lib/api";

type SignInPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function SignInPage({ searchParams }: SignInPageProps) {
  const resolvedSearchParams = (await searchParams) ?? {};
  const redirectValue = resolvedSearchParams.redirectTo;
  const redirectTo = Array.isArray(redirectValue) ? redirectValue[0] : redirectValue || "/";
  const bootstrap = await getSettingsBootstrap().catch(() => null);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col justify-center gap-6 px-4 py-10 lg:px-8">
      <section className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="rounded-[2rem] border bg-slate-950 p-8 text-slate-50 shadow-[0_30px_90px_-50px_rgba(15,23,42,0.8)]">
          <BrandLockup size="xl" priority />
          <div className="inline-flex items-center rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-cyan-200">
            Python API + Next.js
          </div>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight">Secure sign-in for Trade</h1>
          <p className="mt-4 text-sm leading-7 text-slate-300">
            This sign-in flow exchanges a Clerk session token for an application cookie. That lets the new Next.js UI
            hydrate against the Python backend without depending on third-party cookies across domains.
          </p>
          <div className="mt-8 space-y-3 text-sm text-slate-300">
            <p>1. Sign in with Clerk.</p>
            <p>2. Trade stores a local session token cookie.</p>
            <p>3. Server-rendered pages can fetch authenticated dashboard data from Python.</p>
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
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">Clerk sign-in is not configured yet</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Set <code>CLERK_PUBLISHABLE_KEY</code> so the Next.js frontend can mount the Clerk sign-in surface.
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
