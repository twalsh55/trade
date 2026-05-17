import type { ReactNode } from "react";

import { CRMShell } from "@/components/crm-shell";
import { CRMTaskbar } from "@/components/crm-taskbar";
import { loadCRMPageData } from "@/lib/crm-page-data";

export default async function CRMLayout({ children }: { children: ReactNode }) {
  const data = await loadCRMPageData();

  return (
    <main className="mx-auto min-h-screen w-full max-w-7xl px-4 py-6 lg:px-8">
      <div className="grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
        <div className="xl:self-start">
          <CRMTaskbar authenticated={Boolean(data.session?.authenticated)} />
        </div>
        <div className="min-w-0">
          <CRMShell data={data} />
          <div className="hidden">{children}</div>
        </div>
      </div>
    </main>
  );
}
