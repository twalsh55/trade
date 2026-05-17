"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/crm", label: "Overview", body: "High-level CRM status" },
  { href: "/crm/follow-ups", label: "Follow-Ups", body: "Queue, memory, and email" },
  { href: "/crm/pipeline", label: "Pipeline", body: "Stage board and flow" },
  { href: "/crm/import", label: "Import", body: "Spreadsheet and preview tools" },
  { href: "/crm/intake", label: "Intake", body: "AI profile and remote capture" },
];

export function CRMTaskbar() {
  const pathname = usePathname();

  return (
    <aside className="h-fit rounded-[1.9rem] border bg-slate-950 p-5 text-slate-50 shadow-[0_24px_80px_-50px_rgba(15,23,42,0.85)] xl:sticky xl:top-6">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">CRM Taskbar</p>
      <h2 className="mt-3 text-2xl font-semibold tracking-tight">Move like an app, not a landing page.</h2>
      <nav className="mt-6 space-y-3">
        {items.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded-[1.25rem] border px-4 py-4 transition ${
                active
                  ? "border-cyan-300/40 bg-cyan-400/10 text-white"
                  : "border-white/10 bg-white/5 text-slate-200 hover:border-white/25 hover:bg-white/10"
              }`}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">{item.label}</p>
              <p className="mt-2 text-sm text-slate-200">{item.body}</p>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
