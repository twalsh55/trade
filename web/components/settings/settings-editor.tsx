"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import type { AccountSettings } from "@/lib/types";

type SettingsEditorProps = {
  initialSettings: AccountSettings | null;
  fallbackUniverse: string[];
  fallbackLookbackYears: number;
};

export function SettingsEditor({
  initialSettings,
  fallbackUniverse,
  fallbackLookbackYears,
}: SettingsEditorProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [status, setStatus] = useState<string | null>(null);
  const [errors, setErrors] = useState<Partial<Record<keyof AccountSettings, string>>>({});
  const [form, setForm] = useState<AccountSettings>(
    initialSettings ?? {
      universe: fallbackUniverse,
      benchmark: "SPY",
      vix_symbol: "^VIX",
      risk_proxy: "HYG",
      short_yield_symbol: "^IRX",
      long_yield_symbol: "^TNX",
      lookback_years: fallbackLookbackYears,
      telegram_enabled: false,
    },
  );

  function updateField<K extends keyof AccountSettings>(key: K, value: AccountSettings[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus(null);
    const payload: AccountSettings = {
      ...form,
      universe: form.universe.map((item) => item.trim().toUpperCase()).filter(Boolean),
      benchmark: form.benchmark.trim().toUpperCase(),
      vix_symbol: form.vix_symbol.trim().toUpperCase(),
      risk_proxy: form.risk_proxy.trim().toUpperCase(),
      short_yield_symbol: form.short_yield_symbol.trim().toUpperCase(),
      long_yield_symbol: form.long_yield_symbol.trim().toUpperCase(),
    };
    const validationErrors = validateForm(payload);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      setStatus("Fix the highlighted settings fields before saving.");
      return;
    }

    setStatus("Saving settings...");

    const response = await fetch("/api/account/settings", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const body = (await response.json().catch(() => null)) as AccountSettings | { error?: string } | null;
    if (!response.ok) {
      setStatus((body && "error" in body && body.error) || "Unable to save settings.");
      return;
    }

    setForm(body as AccountSettings);
    setStatus("Settings saved. Refreshing dashboard snapshot...");
    window.dispatchEvent(new CustomEvent("trade:settings-saved", { detail: body }));
    startTransition(() => {
      router.refresh();
    });
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Benchmark">
          <input
            data-testid="settings-benchmark-input"
            className={inputClassName(Boolean(errors.benchmark))}
            value={form.benchmark}
            onChange={(event) => updateField("benchmark", event.target.value)}
          />
          {errors.benchmark ? <FieldError message={errors.benchmark} /> : null}
        </Field>
        <Field label="Universe">
          <input
            className={inputClassName(Boolean(errors.universe))}
            value={form.universe.join(", ")}
            onChange={(event) =>
              updateField(
                "universe",
                event.target.value.split(",").map((item) => item.trim()),
              )
            }
          />
          {errors.universe ? <FieldError message={errors.universe} /> : null}
        </Field>
        <Field label="Fear Gauge">
          <input
            className={inputClassName(Boolean(errors.vix_symbol))}
            value={form.vix_symbol}
            onChange={(event) => updateField("vix_symbol", event.target.value)}
          />
          {errors.vix_symbol ? <FieldError message={errors.vix_symbol} /> : null}
        </Field>
        <Field label="Risk Proxy">
          <input
            className={inputClassName(Boolean(errors.risk_proxy))}
            value={form.risk_proxy}
            onChange={(event) => updateField("risk_proxy", event.target.value)}
          />
          {errors.risk_proxy ? <FieldError message={errors.risk_proxy} /> : null}
        </Field>
        <Field label="Short Yield">
          <input
            className={inputClassName(Boolean(errors.short_yield_symbol))}
            value={form.short_yield_symbol}
            onChange={(event) => updateField("short_yield_symbol", event.target.value)}
          />
          {errors.short_yield_symbol ? <FieldError message={errors.short_yield_symbol} /> : null}
        </Field>
        <Field label="Long Yield">
          <input
            className={inputClassName(Boolean(errors.long_yield_symbol))}
            value={form.long_yield_symbol}
            onChange={(event) => updateField("long_yield_symbol", event.target.value)}
          />
          {errors.long_yield_symbol ? <FieldError message={errors.long_yield_symbol} /> : null}
        </Field>
        <Field label="Lookback (years)">
          <input
            type="number"
            min={1}
            max={10}
            className={inputClassName(Boolean(errors.lookback_years))}
            value={form.lookback_years}
            onChange={(event) => updateField("lookback_years", Number(event.target.value))}
          />
          {errors.lookback_years ? <FieldError message={errors.lookback_years} /> : null}
        </Field>
        <Field label="Telegram">
          <label className="flex h-[50px] items-center gap-3 rounded-2xl border bg-white px-4 py-3 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.telegram_enabled}
              onChange={(event) => updateField("telegram_enabled", event.target.checked)}
            />
            Enable Telegram alerts in dashboard defaults
          </label>
        </Field>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={isPending} data-testid="settings-save-button">
          {isPending ? "Saving..." : "Save settings"}
        </Button>
        {status ? (
          <p className="text-sm text-slate-500" data-testid="settings-status">
            {status}
          </p>
        ) : null}
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</span>
      {children}
    </label>
  );
}

function FieldError({ message }: { message: string }) {
  return <p className="text-sm text-rose-600">{message}</p>;
}

function inputClassName(hasError: boolean) {
  return `w-full rounded-2xl border bg-white px-4 py-3 text-sm outline-none transition focus:border-primary ${
    hasError ? "border-rose-300" : ""
  }`;
}

function validateForm(form: AccountSettings) {
  const nextErrors: Partial<Record<keyof AccountSettings, string>> = {};
  if (!form.benchmark) {
    nextErrors.benchmark = "Benchmark is required.";
  }
  if (form.universe.length === 0) {
    nextErrors.universe = "Enter at least one universe symbol.";
  }
  if (!form.vix_symbol) {
    nextErrors.vix_symbol = "Fear gauge symbol is required.";
  }
  if (!form.risk_proxy) {
    nextErrors.risk_proxy = "Risk proxy symbol is required.";
  }
  if (!form.short_yield_symbol) {
    nextErrors.short_yield_symbol = "Short yield symbol is required.";
  }
  if (!form.long_yield_symbol) {
    nextErrors.long_yield_symbol = "Long yield symbol is required.";
  }
  if (form.lookback_years < 1 || form.lookback_years > 10) {
    nextErrors.lookback_years = "Lookback must be between 1 and 10 years.";
  }
  return nextErrors;
}
