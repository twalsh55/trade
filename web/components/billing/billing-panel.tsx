"use client";

import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import type { BillingOverview } from "@/lib/types";

type BillingPanelProps = {
  initialBilling: BillingOverview | null;
};

export function BillingPanel({ initialBilling }: BillingPanelProps) {
  const [isPending, startTransition] = useTransition();
  const [status, setStatus] = useState<string | null>(null);
  const billing = initialBilling;

  async function handleRedirect(path: "/api/account/billing/checkout" | "/api/account/billing/portal") {
    setStatus(path.includes("checkout") ? "Opening Stripe Checkout..." : "Opening Stripe customer portal...");
    startTransition(async () => {
      try {
        const response = await fetch(path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ return_url: window.location.origin }),
        });
        const payload = (await response.json().catch(() => null)) as { url?: string; error?: string } | null;
        if (!response.ok || !payload?.url) {
          setStatus(payload?.error ?? "Unable to open Stripe right now.");
          return;
        }
        window.location.href = payload.url;
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Unable to open Stripe right now.");
      }
    });
  }

  if (!billing) {
    return <p className="text-sm text-slate-500">Billing status is unavailable for this session.</p>;
  }

  if (!billing.enabled) {
    return (
      <div className="space-y-3">
        <p className="text-sm leading-6 text-slate-600">
          Stripe is not configured yet. Add `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID`, and `DATABASE_URL` on the API
          service to enable checkout and portal flows.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <BillingInfo label="Status" value={formatStatus(billing.subscription_status)} />
        <BillingInfo label="Price" value={billing.price_id ?? "Not configured"} />
        <BillingInfo
          label="Renewal"
          value={billing.current_period_end ? new Date(billing.current_period_end).toLocaleString() : "Not scheduled"}
        />
        <BillingInfo
          label="Cancellation"
          value={billing.cancel_at_period_end ? "Ends at period close" : "Auto-renews"}
        />
      </div>
      <div className="flex flex-wrap gap-3">
        <Button
          type="button"
          disabled={isPending || !billing.checkout_available}
          onClick={() => void handleRedirect("/api/account/billing/checkout")}
        >
          {billing.subscription_status ? "Change plan in Checkout" : "Start subscription"}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={isPending || !billing.portal_available}
          onClick={() => void handleRedirect("/api/account/billing/portal")}
        >
          Manage billing
        </Button>
      </div>
      {status ? <p className="text-sm text-slate-500">{status}</p> : null}
    </div>
  );
}

function BillingInfo({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-white px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="mt-2 text-sm font-medium text-slate-800">{value}</p>
    </div>
  );
}

function formatStatus(status: string | null) {
  if (!status) {
    return "No active subscription";
  }
  return status
    .split("_")
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(" ");
}
