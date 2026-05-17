import type { ReactNode } from "react";

import { CRMTaskbar } from "@/components/crm-taskbar";

export default function CRMLayout({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto min-h-screen w-full max-w-7xl px-4 py-6 lg:px-8">
      <div className="grid gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
        <div className="xl:self-start">
          <CRMTaskbar />
        </div>
        <div className="min-w-0">{children}</div>
      </div>
    </main>
  );
}
