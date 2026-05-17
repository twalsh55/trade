export function SiteConstructionBanner() {
  return (
    <div className="sticky top-0 z-50 border-b-2 border-slate-950 bg-[#ffd54a] text-slate-950 shadow-sm">
      <div className="bg-[repeating-linear-gradient(-45deg,rgba(15,23,42,0.16)_0,rgba(15,23,42,0.16)_10px,transparent_10px,transparent_20px)]">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-center px-4 py-3 text-center lg:px-8">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] sm:text-[0.8rem]">
            Under construction: Brivoly is still being shaped, so some flows and details may change.
          </p>
        </div>
      </div>
    </div>
  );
}
