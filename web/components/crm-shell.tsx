"use client";

import { usePathname } from "next/navigation";

import { CRMFollowUpWorkspace, type CRMWorkspaceView } from "@/components/crm-follow-up-workspace";
import type { CRMPageData } from "@/lib/crm-page-data";

export function CRMShell({ data }: { data: CRMPageData }) {
  const pathname = usePathname();
  const view = resolveCRMView(pathname ?? "/crm");

  if (data.followUps) {
    return (
      <CRMFollowUpWorkspace
        initialOverview={data.followUps}
        initialSettings={data.accountSettings}
        initialBilling={data.billing}
        initialIntakeChannel={data.intakeChannel}
        view={view}
      />
    );
  }

  return (
    <>
      <section className="mt-6 rounded-[1.75rem] border border-amber-200 bg-amber-50 p-6 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-amber-700">CRM Load Issue</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-amber-950">We could not load the workspace data.</h2>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-amber-900">
          Your session is active, but the CRM payload did not finish loading. Refresh and Brivoly should try again with the same account context.
        </p>
        {data.userLabel ? <p className="mt-4 text-sm font-medium text-amber-950">Current account: {data.userLabel}</p> : null}
        <div className="mt-5">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-full bg-amber-950 px-5 py-3 text-sm font-medium text-white transition hover:bg-amber-900"
          >
            Reload CRM
          </button>
        </div>
      </section>
      <section className="mt-6 grid gap-6 lg:grid-cols-4">
        <FeatureCard title="Overview" body="See the current health of the CRM without skimming every section." />
        <FeatureCard title="Follow-Ups" body="Work the next actions and keep relationship memory attached to the right lead." />
        <FeatureCard title="Pipeline" body="Review stage progression, overdue items, and current pressure." />
        <FeatureCard title="Import + Intake" body="Bring in spreadsheets and note images, then review intake settings." />
      </section>
    </>
  );
}

function resolveCRMView(pathname: string): CRMWorkspaceView {
  if (pathname === "/crm/follow-ups") {
    return "followups";
  }
  if (pathname === "/crm/pipeline") {
    return "pipeline";
  }
  if (pathname === "/crm/import") {
    return "import";
  }
  if (pathname === "/crm/intake" || pathname.startsWith("/crm/intake/")) {
    return "intake";
  }
  return "overview";
}

function FeatureCard({ title, body }: { title: string; body: string }) {
  return (
    <section className="rounded-[1.6rem] border bg-white/80 p-6 shadow-sm">
      <h2 className="text-2xl font-semibold tracking-tight text-slate-950">{title}</h2>
      <p className="mt-3 text-sm leading-7 text-slate-600">{body}</p>
    </section>
  );
}
