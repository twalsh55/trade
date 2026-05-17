export default function CRMRouteLoading() {
  return (
    <div className="min-w-0">
      <section className="rounded-[2rem] border bg-white/88 p-6 shadow-[0_30px_100px_-55px_rgba(15,23,42,0.4)] backdrop-blur md:p-8">
        <div className="inline-flex items-center rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-cyan-800">
          Opening CRM
        </div>
        <div className="mt-5 h-14 w-full max-w-2xl animate-pulse rounded-[1.25rem] bg-slate-200" />
        <div className="mt-5 space-y-3">
          <div className="h-4 w-full max-w-2xl animate-pulse rounded-full bg-slate-200" />
          <div className="h-4 w-5/6 animate-pulse rounded-full bg-slate-200" />
        </div>
      </section>

      <section className="mt-6 rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
        <div className="h-3 w-28 animate-pulse rounded-full bg-slate-200" />
        <div className="mt-4 h-10 w-80 animate-pulse rounded-[1rem] bg-slate-200" />
        <div className="mt-4 h-4 w-full max-w-3xl animate-pulse rounded-full bg-slate-200" />
      </section>

      <section className="mt-6 grid gap-6 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="rounded-[1.4rem] border bg-white p-5 shadow-sm">
            <div className="h-3 w-20 animate-pulse rounded-full bg-slate-200" />
            <div className="mt-4 h-8 w-14 animate-pulse rounded-full bg-slate-200" />
          </div>
        ))}
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <div className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
          <div className="h-3 w-32 animate-pulse rounded-full bg-slate-200" />
          <div className="mt-4 h-10 w-72 animate-pulse rounded-[1rem] bg-slate-200" />
          <div className="mt-6 space-y-4">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="rounded-[1.4rem] border bg-slate-50/80 p-5">
                <div className="h-4 w-40 animate-pulse rounded-full bg-slate-200" />
                <div className="mt-3 h-3 w-full animate-pulse rounded-full bg-slate-200" />
                <div className="mt-2 h-3 w-5/6 animate-pulse rounded-full bg-slate-200" />
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[1.75rem] border bg-white/90 p-6 shadow-sm">
          <div className="h-3 w-32 animate-pulse rounded-full bg-slate-200" />
          <div className="mt-4 h-10 w-60 animate-pulse rounded-[1rem] bg-slate-200" />
          <div className="mt-6 space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="rounded-[1.25rem] border bg-slate-50 p-4">
                <div className="h-3 w-28 animate-pulse rounded-full bg-slate-200" />
                <div className="mt-3 h-3 w-full animate-pulse rounded-full bg-slate-200" />
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
