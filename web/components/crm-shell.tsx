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
        <h2 className="mt-3 text-3xl font-semibold tracking-tight text-amber-950">We could not load your relationships right now.</h2>
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
      <section className="mt-6 rounded-[1.5rem] border bg-white/85 p-5 shadow-sm">
        <p className="ui-eyebrow text-slate-500">What should appear here</p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <FeatureCard title="Today" body="Start with the relationships that need you first, plus the freshest client context." />
          <FeatureCard title="Relationship memory" body="Keep notes, continuity, uploads, and the next touch close together." />
        </div>
      </section>
    </>
  );
}

function describeLoadFailure(data: CRMPageData): string {
  if (data.session?.authenticated) {
    return "Your account session is active, but the relationship view did not finish loading. Refresh and Brivoly should retry with the same account context.";
  }
  return "Brivoly could not finish loading the relationship view. Refresh and it should retry the guest view automatically.";
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
    <section className="rounded-[1.25rem] border bg-slate-50/80 px-4 py-4">
      <h2 className="text-lg font-semibold tracking-tight text-slate-950">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
    </section>
  );
}
