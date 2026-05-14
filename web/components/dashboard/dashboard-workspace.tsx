"use client";

import { useEffect, useState, useTransition } from "react";

import { DashboardCharts } from "@/components/charts/dashboard-charts";
import { Button } from "@/components/ui/button";
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

      const nextFilters: DashboardFilters = { ...customEvent.detail };
      setFilters(nextFilters);
      setStatus("Saved defaults applied. Refreshing dashboard...");
      void refreshDashboard(nextFilters);
    }

    window.addEventListener("brivoly:settings-saved", handleSavedSettings as EventListener);
    window.addEventListener("trade:settings-saved", handleSavedSettings as EventListener);
    return () => {
      window.removeEventListener("brivoly:settings-saved", handleSavedSettings as EventListener);
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
  const metrics = dashboard?.metrics ?? {};

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
                  <p className="mt-2 text-sm text-slate-600">
                    Quick presets update the dashboard request without changing saved defaults.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {LOOKBACK_PRESETS.map((years) => (
                    <button
                      key={years}
                      type="button"
                      onClick={() => updateFilter("lookback_years", years)}
                      className={`rounded-full border px-4 py-2 text-sm transition ${
                        filters.lookback_years === years
                          ? "border-primary bg-primary text-primary-foreground"
                          : "bg-white text-slate-700 hover:bg-secondary"
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

          <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <InfoTile label="252D Drawdown" value={formatMetricPercent(metrics.drawdown_252)} />
            <InfoTile label="20D Vol (Ann.)" value={formatMetricPercent(metrics.vol20)} />
            <InfoTile label="Breadth >200D" value={formatMetricPercent(metrics.breadth_ratio)} />
            <InfoTile label="Yield Spread (L-S)" value={formatMetricSpread(metrics.yield_curve_spread)} />
          </div>
        </Panel>

        <div id="crash-components" className="scroll-mt-24">
          <Panel
            eyebrow="Snapshot"
            title="Risk components"
            description="These scores come directly from the Python crash-risk model and mirror the old dashboard calculations."
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
              {Object.keys(riskComponents).length > 0 ? (
                Object.entries(riskComponents)
                  .sort(([, left], [, right]) => right - left)
                  .map(([label, value]) => <ComponentMeter key={label} label={label} value={value} />)
              ) : (
                <div className="rounded-2xl border border-dashed bg-slate-50 px-4 py-6 text-sm text-slate-500">
                  Risk component scores will populate after the first authenticated dashboard refresh.
                </div>
              )}
            </div>
          </Panel>
        </div>
      </section>

      <DashboardCharts dashboard={dashboard} />

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Panel
          eyebrow="Indicator Percentiles"
          title="Full indicator table"
          description="Current readings and rolling percentile bands from the Python risk model."
        >
          {dashboard?.indicator_percentiles.length ? (
            <div className="overflow-hidden rounded-[1.5rem] border bg-slate-50">
              <div className="grid grid-cols-[minmax(0,2fr)_repeat(4,minmax(0,1fr))] gap-3 border-b bg-slate-100/80 px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                <span>Indicator</span>
                <span>Current</span>
                <span>P5</span>
                <span>P50</span>
                <span>P95</span>
              </div>
              <div className="divide-y">
                {dashboard.indicator_percentiles.map((indicator) => (
                  <div
                    key={indicator.name}
                    className="grid grid-cols-[minmax(0,2fr)_repeat(4,minmax(0,1fr))] gap-3 px-4 py-3 text-sm text-slate-700"
                  >
                    <span className="font-medium text-slate-900">{indicator.name}</span>
                    <span>{formatIndicatorValue(indicator.current, indicator.name)}</span>
                    <span>{formatIndicatorValue(indicator.p5, indicator.name)}</span>
                    <span>{formatIndicatorValue(indicator.p50, indicator.name)}</span>
                    <span>{formatIndicatorValue(indicator.p95, indicator.name)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-[1.5rem] border border-dashed bg-slate-50 px-4 py-12 text-center text-sm text-slate-500">
              Indicator percentiles will appear once an authenticated dashboard snapshot is available.
            </div>
          )}
        </Panel>

        <Panel
          eyebrow="Readout"
          title="Latest calculated state"
          description="The same quick operational readout the old dashboard surfaced for market conditions."
        >
          <div className="space-y-3">
            {[
              ["Price", formatMetricNumber(metrics.price)],
              ["50D MA", formatMetricNumber(metrics.ma50)],
              ["200D MA", formatMetricNumber(metrics.ma200)],
              ["RSI(14)", formatMetricNumber(metrics.rsi14)],
              ["VIX", formatMetricNumber(metrics.vix)],
              ["Risk Proxy / 50D MA", formatMetricNumber(metrics.risk_proxy)],
              ["Buyer Participation (20D)", formatMetricPercent(metrics.buyer_participation_20d)],
              ["New High Ratio (252D)", formatMetricPercent(metrics.new_high_ratio_252)],
              ["Buyer Exhaustion", formatMetricNumber(metrics.buyer_exhaustion)],
            ].map(([label, value]) => (
              <InfoRow key={label} label={label} value={value} />
            ))}
          </div>
        </Panel>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Panel
          eyebrow="Guidance"
          title="Systematic action cues"
          description="These suggestions are generated from the same Python regime rules that drove the prior app."
        >
          <div className="space-y-3">
            {actions.length > 0 ? (
              actions.map((action, index) => (
                <div key={action} className="flex gap-3 rounded-2xl border bg-slate-50 p-4">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-sm font-semibold text-white">
                    {index + 1}
                  </div>
                  <p className="text-sm leading-6 text-slate-700">{action}</p>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed bg-slate-50 px-4 py-6 text-sm text-slate-500">
                Guidance will populate once the crash-risk engine returns a live snapshot.
              </div>
            )}
          </div>
        </Panel>

        <Panel
          eyebrow="Filters"
          title="Current dashboard inputs"
          description="These are the symbols and settings currently feeding the Python calculation layer."
        >
          <div className="space-y-3">
            {[
              ["Universe", filters.universe.join(", ") || "N/A"],
              ["Benchmark", dashboard?.config.benchmark ?? filters.benchmark],
              ["Fear Gauge", dashboard?.config.vix_symbol ?? filters.vix_symbol],
              ["Risk Proxy", dashboard?.config.risk_proxy ?? filters.risk_proxy],
              ["Short Yield", dashboard?.config.short_yield_symbol ?? filters.short_yield_symbol],
              ["Long Yield", dashboard?.config.long_yield_symbol ?? filters.long_yield_symbol],
              ["Start Date", dashboard?.config.start_date ?? "Pending"],
              ["End Date", dashboard?.config.end_date ?? "Pending"],
            ].map(([label, value]) => (
              <InfoRow key={label} label={label} value={value} />
            ))}
          </div>
        </Panel>
      </section>
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

function ComponentMeter({ label, value }: { label: string; value: number }) {
  const clampedValue = Math.max(0, Math.min(value, 100));
  return (
    <div className="rounded-2xl border bg-slate-50 p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-900">{label}</p>
        <p className="text-sm text-slate-500">{clampedValue.toFixed(1)}</p>
      </div>
      <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-200">
        <div
          className={`h-full rounded-full ${
            clampedValue >= 70 ? "bg-rose-500" : clampedValue >= 50 ? "bg-amber-500" : "bg-emerald-500"
          }`}
          style={{ width: `${clampedValue}%` }}
        />
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border bg-slate-50 px-4 py-3">
      <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</span>
      <span className="text-sm font-medium text-slate-900">{value}</span>
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

function formatMetricNumber(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A";
  }
  return value.toFixed(2);
}

function formatMetricPercent(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatMetricSpread(value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A";
  }
  return `${value.toFixed(2)}%`;
}

function formatIndicatorValue(value: number | null, indicatorName: string) {
  if (value === null || Number.isNaN(value)) {
    return "N/A";
  }

  if (
    indicatorName.includes("Drawdown") ||
    indicatorName.includes("Vol") ||
    indicatorName.includes("Breadth") ||
    indicatorName.includes("Ratio") ||
    indicatorName.includes("Participation")
  ) {
    return `${(value * 100).toFixed(1)}%`;
  }

  return value.toFixed(2);
}
