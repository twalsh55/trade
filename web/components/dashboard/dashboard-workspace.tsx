"use client";

import { useEffect, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { DashboardCharts } from "@/components/charts/dashboard-charts";
import type { AccountSettings, DashboardFilters, DashboardSnapshot, SettingsBootstrap } from "@/lib/types";

type DashboardWorkspaceProps = {
  initialDashboard: DashboardSnapshot | null;
  settings: AccountSettings | null;
  bootstrap: SettingsBootstrap | null;
};

type DashboardResponse = DashboardSnapshot | { error?: string };

const LOOKBACK_PRESETS = [1, 3, 5, 10];

export function DashboardWorkspace({ initialDashboard, settings, bootstrap }: DashboardWorkspaceProps) {
  const [dashboard, setDashboard] = useState(initialDashboard);
  const [status, setStatus] = useState<string | null>(null);
  const [errors, setErrors] = useState<Partial<Record<keyof DashboardFilters, string>>>({});
  const [isPending, startTransition] = useTransition();
  const [filters, setFilters] = useState(() => buildInitialFilters(initialDashboard, settings, bootstrap));

  useEffect(() => {
    function handleSavedSettings(event: Event) {
      const customEvent = event as CustomEvent<AccountSettings>;
      if (!customEvent.detail) {
        return;
      }
      const nextFilters: DashboardFilters = {
        ...customEvent.detail,
      };
      setFilters(nextFilters);
      setStatus("Saved defaults applied. Refreshing dashboard...");
      void refreshDashboard(nextFilters);
    }

    window.addEventListener("trade:settings-saved", handleSavedSettings as EventListener);
    return () => {
      window.removeEventListener("trade:settings-saved", handleSavedSettings as EventListener);
    };
  }, []);

  function updateFilter<K extends keyof DashboardFilters>(key: K, value: DashboardFilters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  }

  function resetToSavedDefaults() {
    const next = buildInitialFilters(initialDashboard, settings, bootstrap);
    setFilters(next);
    setErrors({});
    setStatus("Controls reset to saved defaults.");
  }

  async function refreshDashboard(nextFilters: DashboardFilters = filters) {
    const validationErrors = validateFilters(nextFilters);
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) {
      setStatus("Fix the highlighted dashboard filters before refreshing.");
      return;
    }

    setStatus("Refreshing dashboard...");
    const params = new URLSearchParams();
    nextFilters.universe.forEach((symbol) => params.append("universe", symbol));
    params.set("benchmark", nextFilters.benchmark);
    params.set("vix_symbol", nextFilters.vix_symbol);
    params.set("risk_proxy", nextFilters.risk_proxy);
    params.set("short_yield_symbol", nextFilters.short_yield_symbol);
    params.set("long_yield_symbol", nextFilters.long_yield_symbol);
    params.set("lookback_years", String(nextFilters.lookback_years));

    const response = await fetch(`/api/dashboard?${params.toString()}`, { cache: "no-store" });
    const payload = (await response.json().catch(() => null)) as DashboardResponse | null;
    const errorMessage =
      payload && "error" in payload && typeof payload.error === "string" ? payload.error : null;
    if (!response.ok || !payload || errorMessage) {
      setStatus(errorMessage || "Unable to refresh dashboard.");
      return;
    }

    setDashboard(payload as DashboardSnapshot);
    setStatus("Dashboard refreshed.");
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    startTransition(() => {
      void refreshDashboard();
    });
  }

  const actions = dashboard?.actions ?? [];
  const riskScore = dashboard?.risk_score ?? null;
  const riskComponents = dashboard?.risk_components ?? {};

  return (
    <div className="space-y-6">
      <section id="overview" className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Panel
          eyebrow="Overview"
          title={dashboard?.regime ?? "Awaiting authenticated dashboard snapshot"}
          description={
            dashboard
              ? `Refreshed at ${formatDateTime(dashboard.refreshed_at)} for ${dashboard.config.benchmark}.`
              : "Use the controls below once an authenticated session is available."
          }
        >
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Benchmark" error={errors.benchmark}>
                <input
                  data-testid="dashboard-benchmark-input"
                  className={inputClassName(Boolean(errors.benchmark))}
                  value={filters.benchmark}
                  onChange={(event) => updateFilter("benchmark", normalizeSymbol(event.target.value))}
                />
              </Field>
              <Field label="Universe" error={errors.universe}>
                <input
                  className={inputClassName(Boolean(errors.universe))}
                  value={filters.universe.join(", ")}
                  onChange={(event) => updateFilter("universe", parseUniverseText(event.target.value))}
                />
              </Field>
              <Field label="Fear Gauge" error={errors.vix_symbol}>
                <input
                  className={inputClassName(Boolean(errors.vix_symbol))}
                  value={filters.vix_symbol}
                  onChange={(event) => updateFilter("vix_symbol", normalizeSymbol(event.target.value))}
                />
              </Field>
              <Field label="Risk Proxy" error={errors.risk_proxy}>
                <input
                  className={inputClassName(Boolean(errors.risk_proxy))}
                  value={filters.risk_proxy}
                  onChange={(event) => updateFilter("risk_proxy", normalizeSymbol(event.target.value))}
                />
              </Field>
              <Field label="Short Yield" error={errors.short_yield_symbol}>
                <input
                  className={inputClassName(Boolean(errors.short_yield_symbol))}
                  value={filters.short_yield_symbol}
                  onChange={(event) => updateFilter("short_yield_symbol", normalizeSymbol(event.target.value))}
                />
              </Field>
              <Field label="Long Yield" error={errors.long_yield_symbol}>
                <input
                  className={inputClassName(Boolean(errors.long_yield_symbol))}
                  value={filters.long_yield_symbol}
                  onChange={(event) => updateFilter("long_yield_symbol", normalizeSymbol(event.target.value))}
                />
              </Field>
            </div>

            <div className="rounded-2xl border bg-slate-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Lookback window</p>
                  <p className="mt-2 text-sm text-slate-600">Quick presets update the dashboard request without changing saved defaults.</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {LOOKBACK_PRESETS.map((years) => (
                    <button
                      key={years}
                      type="button"
                      onClick={() => updateFilter("lookback_years", years)}
                      className={`rounded-full border px-4 py-2 text-sm transition ${
                        filters.lookback_years === years ? "border-primary bg-primary text-primary-foreground" : "bg-white text-slate-700 hover:bg-secondary"
                      }`}
                    >
                      {years}Y
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={isPending} data-testid="dashboard-refresh-button">
                {isPending ? "Refreshing..." : "Refresh dashboard"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={resetToSavedDefaults}
                disabled={isPending}
                data-testid="dashboard-reset-button"
              >
                Reset to saved defaults
              </Button>
              {status ? (
                <p className="text-sm text-slate-500" data-testid="dashboard-status">
                  {status}
                </p>
              ) : null}
            </div>
          </form>

          <div className="mt-6 grid gap-3 md:grid-cols-2">
            <InfoTile label="Crash Risk" value={riskScore === null ? "N/A" : `${riskScore.toFixed(1)}/100`} />
            <InfoTile label="Lookback" value={`${filters.lookback_years} years`} />
            <InfoTile
              label="Benchmark"
              value={dashboard?.config.benchmark ?? filters.benchmark}
              valueTestId="dashboard-benchmark-value"
            />
            <InfoTile label="Universe size" value={String(filters.universe.length)} />
          </div>

          <div className="mt-6 grid gap-3">
            {actions.length > 0 ? (
              actions.slice(0, 4).map((action) => (
                <div key={action} className="rounded-2xl border bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
                  {action}
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed bg-slate-50 px-4 py-6 text-sm text-slate-500">
                Action suggestions will appear here when the authenticated dashboard endpoint is reachable.
              </div>
            )}
          </div>
        </Panel>

        <Panel
          eyebrow="Snapshot"
          title="Risk components"
          description="These values are now tied to the live dashboard refresh controls above."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.keys(riskComponents).length > 0 ? (
              Object.entries(riskComponents)
                .slice(0, 8)
                .map(([label, value]) => <InfoTile key={label} label={label} value={value.toFixed(1)} />)
            ) : (
              <>
                <InfoTile label="Trend stress" value="Pending" />
                <InfoTile label="Drawdown stress" value="Pending" />
                <InfoTile label="Volatility stress" value="Pending" />
                <InfoTile label="Breadth stress" value="Pending" />
              </>
            )}
          </div>

          <div className="mt-6 space-y-3">
            {dashboard?.indicator_percentiles.slice(0, 4).map((indicator) => (
              <div key={indicator.name} className="rounded-2xl border bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-slate-900">{indicator.name}</p>
                  <p className="text-sm text-slate-500">
                    Current {indicator.current === null ? "N/A" : indicator.current.toFixed(2)}
                  </p>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-3 text-xs uppercase tracking-[0.18em] text-slate-400">
                  <span>P5 {indicator.p5 === null ? "N/A" : indicator.p5.toFixed(2)}</span>
                  <span>P50 {indicator.p50 === null ? "N/A" : indicator.p50.toFixed(2)}</span>
                  <span>P95 {indicator.p95 === null ? "N/A" : indicator.p95.toFixed(2)}</span>
                </div>
              </div>
            )) ?? null}
          </div>
        </Panel>
      </section>

      <DashboardCharts dashboard={dashboard} />
    </div>
  );
}

function buildInitialFilters(
  dashboard: DashboardSnapshot | null,
  settings: AccountSettings | null,
  bootstrap: SettingsBootstrap | null,
): DashboardFilters {
  if (dashboard) {
    return {
      universe: [...dashboard.config.universe],
      benchmark: dashboard.config.benchmark,
      vix_symbol: dashboard.config.vix_symbol,
      risk_proxy: dashboard.config.risk_proxy,
      short_yield_symbol: dashboard.config.short_yield_symbol,
      long_yield_symbol: dashboard.config.long_yield_symbol,
      lookback_years: deriveLookbackYears(dashboard.config.start_date, dashboard.config.end_date),
    };
  }

  if (settings) {
    return { ...settings };
  }

  return {
    universe: [...(bootstrap?.default_universe ?? ["SPY", "QQQ", "IWM", "EFA", "EEM"])],
    benchmark: bootstrap?.default_benchmark ?? "SPY",
    vix_symbol: bootstrap?.default_vix_symbol ?? "^VIX",
    risk_proxy: bootstrap?.default_risk_proxy ?? "HYG",
    short_yield_symbol: bootstrap?.default_short_yield_symbol ?? "^IRX",
    long_yield_symbol: bootstrap?.default_long_yield_symbol ?? "^TNX",
    lookback_years: bootstrap?.default_lookback_years ?? 4,
  };
}

function deriveLookbackYears(startDate: string, endDate: string) {
  const start = new Date(startDate);
  const end = new Date(endDate);
  const diff = Math.max(end.getTime() - start.getTime(), 0);
  return Math.max(1, Math.round(diff / (365 * 24 * 60 * 60 * 1000)));
}

function parseUniverseText(value: string) {
  return value
    .split(",")
    .map((item) => normalizeSymbol(item))
    .filter(Boolean);
}

function normalizeSymbol(value: string) {
  return value.trim().toUpperCase();
}

function validateFilters(filters: DashboardFilters) {
  const nextErrors: Partial<Record<keyof DashboardFilters, string>> = {};
  if (!filters.benchmark) {
    nextErrors.benchmark = "Benchmark is required.";
  }
  if (filters.universe.length === 0) {
    nextErrors.universe = "Enter at least one ticker in the universe.";
  }
  if (!filters.vix_symbol) {
    nextErrors.vix_symbol = "Fear gauge symbol is required.";
  }
  if (!filters.risk_proxy) {
    nextErrors.risk_proxy = "Risk proxy symbol is required.";
  }
  if (!filters.short_yield_symbol) {
    nextErrors.short_yield_symbol = "Short yield symbol is required.";
  }
  if (!filters.long_yield_symbol) {
    nextErrors.long_yield_symbol = "Long yield symbol is required.";
  }
  if (filters.lookback_years < 1 || filters.lookback_years > 10) {
    nextErrors.lookback_years = "Lookback must be between 1 and 10 years.";
  }
  return nextErrors;
}

function Panel({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[1.75rem] border bg-white/80 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">{eyebrow}</p>
      <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">{title}</h3>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">{description}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</span>
      {children}
      {error ? <span className="text-sm text-rose-600">{error}</span> : null}
    </label>
  );
}

function InfoTile({
  label,
  value,
  valueTestId,
}: {
  label: string;
  value: string;
  valueTestId?: string;
}) {
  return (
    <div className="rounded-2xl border bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="mt-3 text-base font-medium text-slate-900" data-testid={valueTestId}>
        {value}
      </p>
    </div>
  );
}

function inputClassName(hasError: boolean) {
  return `w-full rounded-2xl border bg-white px-4 py-3 text-sm outline-none transition focus:border-primary ${
    hasError ? "border-rose-300" : ""
  }`;
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
