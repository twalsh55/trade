import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
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
    <main className="mx-auto min-h-screen w-full max-w-5xl px-4 py-8 lg:px-8">
      <section className="relative overflow-hidden rounded-[2rem] border bg-white/85 p-6 shadow-[0_30px_100px_-55px_rgba(15,23,42,0.4)] backdrop-blur md:p-8">
        <BrandMark
          size="md"
          priority
          className="pointer-events-none absolute right-6 top-6 opacity-20 md:right-8 md:top-8"
          imageClassName="saturate-[0.85]"
          href={null}
        />
        <div className="grid gap-8 lg:grid-cols-[0.82fr_1.18fr] lg:items-start">
          <section className="max-w-xl">
            <div>
              <p className="ui-eyebrow bg-gradient-to-r from-[#034CFD] to-[#01113B] bg-clip-text text-transparent">
                Sign In
              </p>
              <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950 md:text-5xl">
                Open Brivoly Client OS.
              </h1>
            </div>
            <p className="mt-5 text-base leading-7 text-slate-600">Pick up every client relationship where you left it.</p>
            <div className="mt-6 space-y-3">
              <SimpleAccessRow label="Inside" value="Today, relationship memory, inbox context, and dropzones" />
              <SimpleAccessRow label="Next" value="Brivoly opens Client OS right away" />
            </div>
            <div className="mt-8 flex flex-wrap gap-3">
              {bootstrap?.clerk_sign_up_url ? (
                <Button asChild size="lg" variant="outline">
                  <Link href="/sign-up?redirectTo=%2Fclientos">Create account</Link>
                </Button>
              ) : null}
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
              <p className="ui-eyebrow">Sign in</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">Sign-in is not ready yet</h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Add <code>CLERK_PUBLISHABLE_KEY</code> so Brivoly can show the sign-in form here.
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
        </div>
      </section>
    </main>
  );
}

function SimpleAccessRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.3rem] border bg-slate-50/80 px-4 py-4">
      <p className="ui-eyebrow">{label}</p>
      <p className="mt-2 text-sm leading-6 text-slate-700">{value}</p>
    </div>
  );
}
