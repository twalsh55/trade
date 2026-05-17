import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { ClerkAuthBridge } from "@/components/auth/clerk-auth-bridge";
import { Button } from "@/components/ui/button";
import { getSettingsBootstrap } from "@/lib/api";
import { sanitizeRedirectTo } from "@/lib/auth";

export const dynamic = "force-dynamic";

type SignUpPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function SignUpPage({ searchParams }: SignUpPageProps) {
  const resolvedSearchParams = (await searchParams) ?? {};
  const redirectValue = resolvedSearchParams.redirectTo;
  const redirectTo = sanitizeRedirectTo(Array.isArray(redirectValue) ? redirectValue[0] : redirectValue);
  const bootstrap = await getSettingsBootstrap().catch(() => null);

  return (
    <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-6 lg:px-8">
      <section className="relative overflow-hidden rounded-[2rem] border bg-white/85 p-6 shadow-[0_30px_100px_-55px_rgba(15,23,42,0.4)] backdrop-blur md:p-8">
        <BrandMark
          size="md"
          priority
          className="pointer-events-none absolute right-6 top-6 opacity-20 md:right-8 md:top-8"
          imageClassName="saturate-[0.85]"
          href={null}
        />
        <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div>
              <p className="ui-eyebrow bg-gradient-to-r from-[#034CFD] to-[#01113B] bg-clip-text text-transparent">
                Client OS
              </p>
              <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950 md:text-5xl">
                Create your account and step into Client OS.
              </h1>
            </div>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-600">
              Create your account here, then Brivoly brings you straight into your relationship flow.
            </p>
            <div className="mt-6 rounded-[1.5rem] border border-cyan-200 bg-cyan-50 px-5 py-4 text-cyan-950">
              <p className="ui-eyebrow-strong text-cyan-900">New account</p>
              <p className="mt-2 text-lg font-semibold">Create the account here, then Brivoly opens Client OS.</p>
              <p className="mt-2 text-sm leading-6">
                One clean handoff, no extra re-entry.
              </p>
            </div>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg" variant="outline">
                <Link href="/sign-in?redirectTo=%2Fclientos">Already have an account?</Link>
              </Button>
            </div>
          </div>

          <div className="w-full max-w-md rounded-[1.75rem] border bg-slate-950 p-5 text-slate-50 shadow-[0_24px_80px_-50px_rgba(15,23,42,0.9)]">
            <p className="ui-eyebrow-inverse text-cyan-300">Account flow</p>
            <div className="mt-4 space-y-3">
              <SignUpStatusRow label="Session" value="Creating a new account here" />
              <SignUpStatusRow label="Destination" value={redirectTo === "/clientos" ? "Client OS" : "Brivoly"} />
              <SignUpStatusRow label="Next" value="Create account, then open your relationship flow" />
            </div>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <section className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
          <p className="ui-eyebrow">Before you continue</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Account creation stays inside Brivoly.</h2>
          <p className="mt-3 text-sm leading-7 text-slate-600">
            This keeps the first handoff calm so new users continue straight into their relationship flow.
          </p>
          <div className="mt-5 space-y-3">
            <InfoCard
              label="Right now"
              body="You do not have an active account session yet. Create the account here and Brivoly finishes the handoff automatically."
            />
            <InfoCard
              label="Next"
              body="Create the account below, then Brivoly secures your session and opens Client OS."
            />
            <InfoCard
              label="Why here"
              body="Keeping account creation in-app avoids broken redirects and makes the first run feel calmer."
            />
          </div>
        </section>

        {bootstrap?.clerk_publishable_key && bootstrap.clerk_frontend_api_host ? (
          <ClerkAuthBridge
            publishableKey={bootstrap.clerk_publishable_key}
            host={bootstrap.clerk_frontend_api_host}
            redirectTo={redirectTo}
            mode="sign-up"
          />
        ) : (
          <section className="rounded-[1.75rem] border bg-white/85 p-6 shadow-sm">
            <p className="ui-eyebrow">Create account</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">Account creation is not ready yet</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              Add <code>CLERK_PUBLISHABLE_KEY</code> so Brivoly can show account creation here.
            </p>
            {bootstrap?.clerk_sign_up_url ? (
              <p className="mt-4 text-sm text-slate-600">
                Hosted fallback:{" "}
                <Link className="font-medium text-primary underline underline-offset-4" href={bootstrap.clerk_sign_up_url}>
                  {bootstrap.clerk_sign_up_url}
                </Link>
              </p>
            ) : null}
          </section>
        )}
      </section>
    </main>
  );
}

function SignUpStatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="ui-eyebrow-inverse text-slate-400">{label}</p>
      <p className="text-right text-sm text-slate-100">{value}</p>
    </div>
  );
}

function InfoCard({ label, body }: { label: string; body: string }) {
  return (
    <div className="rounded-[1.4rem] border bg-slate-50/80 px-4 py-4">
      <p className="ui-eyebrow">{label}</p>
      <p className="mt-2 text-sm leading-6 text-slate-700">{body}</p>
    </div>
  );
}
