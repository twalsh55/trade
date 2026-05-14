"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { AlertHistoryEntry } from "@/lib/types";

type AlertsPanelProps = {
  initialItems: AlertHistoryEntry[];
};

export function AlertsPanel({ initialItems }: AlertsPanelProps) {
  const [items, setItems] = useState(initialItems);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function refreshAlerts() {
    setIsLoading(true);
    setStatus(null);
    try {
      const response = await fetch("/api/alerts/history?limit=20", { cache: "no-store" });
      const payload = (await response.json().catch(() => null)) as { items?: AlertHistoryEntry[]; error?: string } | null;
      if (!response.ok || !payload?.items) {
        setStatus(payload?.error ?? "Unable to refresh alerts.");
        return;
      }
      setItems(payload.items);
      setStatus("Alert feed refreshed.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500">Recent signals and settings activity from the backend alert history feed.</p>
        <Button type="button" variant="outline" onClick={refreshAlerts} disabled={isLoading} data-testid="alerts-refresh-button">
          {isLoading ? "Refreshing..." : "Refresh feed"}
        </Button>
      </div>
      <div className="space-y-3">
        {items.length > 0 ? (
          items.map((item) => (
            <article key={`${item.occurred_at}-${item.title}`} className="rounded-2xl border bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                <span className="rounded-full bg-slate-900 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-white">
                  {item.severity}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-600">{item.message}</p>
              <p className="mt-3 text-xs uppercase tracking-[0.18em] text-slate-400">
                {item.category} · {formatDateTime(item.occurred_at)}
              </p>
            </article>
          ))
        ) : (
          <div className="rounded-2xl border border-dashed bg-slate-50 px-4 py-6 text-sm text-slate-500">
            No alerts were available for this session.
          </div>
        )}
      </div>
      {status ? (
        <p className="text-sm text-slate-500" data-testid="alerts-status">
          {status}
        </p>
      ) : null}
    </div>
  );
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
