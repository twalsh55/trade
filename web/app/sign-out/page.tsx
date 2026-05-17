import { BrandMark } from "@/components/brand-mark";
import { SignOutBridge } from "@/components/auth/sign-out-bridge";
import { getSettingsBootstrap } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SignOutPage() {
  const bootstrap = await getSettingsBootstrap().catch(() => null);

  return (
    <main className="mx-auto min-h-screen w-full max-w-4xl px-4 py-8 lg:px-8">
      <section className="relative overflow-hidden rounded-[2rem] border bg-white/88 p-6 shadow-[0_30px_100px_-55px_rgba(15,23,42,0.35)] backdrop-blur md:p-8">
        <BrandMark
          size="md"
          priority
          className="pointer-events-none absolute right-6 top-6 opacity-20 md:right-8 md:top-8"
          imageClassName="saturate-[0.85]"
          href={null}
        />
        <SignOutBridge
          publishableKey={bootstrap?.clerk_publishable_key ?? null}
          host={bootstrap?.clerk_frontend_api_host ?? null}
        />
      </section>
    </main>
  );
}
