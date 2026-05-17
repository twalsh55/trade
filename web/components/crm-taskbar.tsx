"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { BrandMark } from "@/components/brand-mark";

const items = [
  { href: "/crm", label: "Overview", body: "High-level CRM status" },
  { href: "/crm/follow-ups", label: "Follow-Ups", body: "Queue, memory, and email" },
  { href: "/crm/pipeline", label: "Pipeline", body: "Stage board and flow" },
  { href: "/crm/import", label: "Import", body: "Spreadsheet and preview tools" },
  { href: "/crm/intake", label: "Intake", body: "AI profile and remote capture" },
];

export function CRMTaskbar() {
  const pathname = usePathname();
  const [isSigningOut, setIsSigningOut] = useState(false);

  function handleSignOut() {
    setIsSigningOut(true);
    window.location.assign("/sign-out");
  }

  return (
    <aside className="h-fit rounded-[1.9rem] border bg-slate-950 p-5 text-slate-50 shadow-[0_24px_80px_-50px_rgba(15,23,42,0.85)] xl:sticky xl:top-6">
      <div className="flex items-center gap-3">
        <BrandMark
          size="sm"
          className="rounded-[1rem] border border-white/10 bg-white/5 p-1"
          imageClassName="opacity-90"
        />
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">CRM Taskbar</p>
          <p className="mt-1 text-xs text-slate-400">Brivoly</p>
        </div>
      </div>
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
      <div className="mt-6 border-t border-white/10 pt-4">
        <button
          type="button"
          onClick={handleSignOut}
          disabled={isSigningOut}
          className="w-full rounded-[1.1rem] border border-white/10 bg-white/5 px-4 py-3 text-left text-sm text-slate-200 transition hover:border-white/25 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSigningOut ? "Signing out..." : "Sign out"}
        </button>
      </div>
    </aside>
  );
}
