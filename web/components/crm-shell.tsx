"use client";

import { usePathname } from "next/navigation";

import { CRMFollowUpWorkspace, type CRMWorkspaceView } from "@/components/crm-follow-up-workspace";
import type { CRMPageData } from "@/lib/crm-page-data";

export function CRMShell({ data }: { data: CRMPageData }) {
  const pathname = usePathname();
  const view = resolveCRMView(pathname ?? "/clientos");

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
        <p className="ui-eyebrow-strong text-amber-700">Client OS Load Issue</p>
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-amber-950">We could not load the workspace data.</h2>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-amber-900">
          {describeLoadFailure(data)}
        </p>
        {data.userLabel ? <p className="mt-4 text-sm font-medium text-amber-950">Current account: {data.userLabel}</p> : null}
        {data.loadErrors.length ? (
          <div className="mt-4 rounded-[1.25rem] border border-amber-200/80 bg-white/70 px-4 py-4 text-sm leading-6 text-amber-950">
            <p className="ui-eyebrow-strong text-amber-700">Latest error</p>
            <p className="mt-2">{data.loadErrors[0]}</p>
          </div>
        ) : null}
        <div className="mt-5">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-full bg-amber-950 px-5 py-3 text-sm font-medium text-white transition hover:bg-amber-900"
          >
            Reload Client OS
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

function describeLoadFailure(data: CRMPageData): string {
  if (data.session?.authenticated) {
    return "Your account session is active, but the relationship workspace did not finish loading. Refresh and Brivoly should retry with the same account context.";
  }
  return "Brivoly could not finish loading the client workspace data. Refresh and it should retry the guest workspace automatically.";
}

function resolveCRMView(pathname: string): CRMWorkspaceView {
  if (pathname === "/crm/follow-ups" || pathname === "/clientos/follow-ups") {
    return "followups";
  }
  if (pathname === "/crm/inbox" || pathname === "/clientos/inbox") {
    return "inbox";
  }
  if (pathname === "/crm/pipeline" || pathname === "/clientos/pipeline") {
    return "pipeline";
  }
  if (pathname === "/crm/import" || pathname === "/clientos/import") {
    return "import";
  }
  if (
    pathname === "/crm/intake" ||
    pathname.startsWith("/crm/intake/") ||
    pathname === "/clientos/intake" ||
    pathname.startsWith("/clientos/intake/")
  ) {
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
