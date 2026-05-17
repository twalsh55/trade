import { BrandMark } from "@/components/brand-mark";
import { IntakeMagicLinkUpload } from "@/components/intake-magic-link-upload";

type IntakePageProps = {
  params: Promise<{ token: string }>;
};

export default async function IntakeMagicLinkPage({ params }: IntakePageProps) {
  const { token } = await params;

  return (
    <main className="mx-auto min-h-screen w-full max-w-3xl px-4 py-8 lg:px-8">
      <section className="relative overflow-hidden rounded-[2rem] border bg-white/88 p-6 shadow-[0_30px_100px_-55px_rgba(15,23,42,0.35)] backdrop-blur md:p-8">
        <BrandMark
          size="md"
          priority
          className="pointer-events-none absolute right-6 top-6 opacity-20 md:right-8 md:top-8"
          imageClassName="saturate-[0.85]"
          href={null}
        />
        <div>
          <p className="bg-gradient-to-r from-[#034CFD] to-[#01113B] bg-clip-text text-xs font-semibold uppercase tracking-[0.28em] text-transparent">
            Client Update Link
          </p>
          <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950 md:text-5xl">
            Send a file or screenshot without logging in.
          </h1>
        </div>

        <p className="mt-6 max-w-2xl text-base leading-7 text-slate-600">
          Use this page from your phone to send a screenshot, whiteboard photo, or handwritten note. Brivoly will attach it to the right relationship history so the context is easy to pick back up later.
        </p>

        <IntakeMagicLinkUpload token={token} />
      </section>
    </main>
  );
}
