import type { DashboardSnapshot, MarketBreadthPoint, PriceHistoryPoint } from "@/lib/types";

type DashboardChartsProps = {
  dashboard: DashboardSnapshot | null;
};

export function DashboardCharts({ dashboard }: DashboardChartsProps) {
  if (!dashboard) {
    return (
      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard title="Price trend" subtitle="Sign in to load benchmark history.">
          <EmptyChartCopy />
        </ChartCard>
        <ChartCard title="Participation breadth" subtitle="Sign in to load market breadth history.">
          <EmptyChartCopy />
        </ChartCard>
      </div>
    );
  }

  const recentPrice = dashboard.price_history.slice(-90);
  const recentBreadth = dashboard.market_breadth_history.slice(-90);

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <ChartCard
        title={`${dashboard.config.benchmark} trend`}
        subtitle="Price with medium- and long-term moving averages from the Python dashboard snapshot."
      >
        <LineChart
          series={[
            { label: "Price", color: "#1650ff", values: recentPrice.map((point) => point.price) },
            { label: "50D MA", color: "#0f766e", values: recentPrice.map((point) => point.ma50) },
            { label: "200D MA", color: "#f59e0b", values: recentPrice.map((point) => point.ma200) },
          ]}
        />
        <div className="mt-4 flex flex-wrap gap-3 text-xs uppercase tracking-[0.18em] text-slate-400">
          <span>{recentPrice[0]?.date}</span>
          <span>to</span>
          <span>{recentPrice[recentPrice.length - 1]?.date}</span>
        </div>
      </ChartCard>

      <ChartCard
        title="Participation breadth"
        subtitle="Buyer participation and new-high ratio from the current dashboard snapshot."
      >
        <LineChart
          series={[
            {
              label: "Buyer participation",
              color: "#d97706",
              values: recentBreadth.map((point) => point.buyer_participation_20d),
            },
            {
              label: "New high ratio",
              color: "#0f766e",
              values: recentBreadth.map((point) => point.new_high_ratio_252),
            },
          ]}
          percentage
        />
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <StatPill
            label="Latest buyer participation"
            value={formatPercent(recentBreadth[recentBreadth.length - 1]?.buyer_participation_20d)}
          />
          <StatPill
            label="Latest new-high ratio"
            value={formatPercent(recentBreadth[recentBreadth.length - 1]?.new_high_ratio_252)}
          />
        </div>
      </ChartCard>
    </div>
  );
}

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[1.75rem] border bg-white/80 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Visuals</p>
      <h3 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">{subtitle}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function LineChart({
  series,
  percentage = false,
}: {
  series: Array<{ label: string; color: string; values: Array<number | null> }>;
  percentage?: boolean;
}) {
  const cleanValues = series.flatMap((item) => item.values).filter((value): value is number => typeof value === "number");
  if (cleanValues.length === 0) {
    return <EmptyChartCopy />;
  }

  const min = Math.min(...cleanValues);
  const max = Math.max(...cleanValues);
  const width = 720;
  const height = 260;
  const padding = 18;

  const paths = series.map((item) => ({
    ...item,
    path: buildPath(item.values, { min, max, width, height, padding }),
  }));

  return (
    <div className="rounded-[1.5rem] border bg-slate-50 p-4">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[260px] w-full">
        <rect x="0" y="0" width={width} height={height} rx="24" fill="transparent" />
        {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
          <line
            key={ratio}
            x1={padding}
            x2={width - padding}
            y1={padding + ratio * (height - padding * 2)}
            y2={padding + ratio * (height - padding * 2)}
            stroke="rgba(148,163,184,0.25)"
            strokeDasharray="4 8"
          />
        ))}
        {paths.map((item) =>
          item.path ? (
            <path
              key={item.label}
              d={item.path}
              fill="none"
              stroke={item.color}
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null,
        )}
      </svg>
      <div className="mt-4 flex flex-wrap gap-3">
        {paths.map((item) => (
          <div key={item.label} className="inline-flex items-center gap-2 rounded-full border bg-white px-3 py-1 text-xs text-slate-600">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
            {item.label}
          </div>
        ))}
        {percentage ? (
          <div className="inline-flex items-center rounded-full border bg-white px-3 py-1 text-xs text-slate-600">Scaled as ratio</div>
        ) : null}
      </div>
      <div className="mt-4 flex items-center justify-between text-xs uppercase tracking-[0.18em] text-slate-400">
        <span>{percentage ? formatPercent(min) : min.toFixed(2)}</span>
        <span>{percentage ? formatPercent(max) : max.toFixed(2)}</span>
      </div>
    </div>
  );
}

function buildPath(
  values: Array<number | null>,
  bounds: { min: number; max: number; width: number; height: number; padding: number },
) {
  const { min, max, width, height, padding } = bounds;
  const usableWidth = width - padding * 2;
  const usableHeight = height - padding * 2;
  const range = max - min || 1;

  return values.reduce((path, value, index) => {
    if (value === null || Number.isNaN(value)) {
      return path;
    }

    const x = padding + (index / Math.max(values.length - 1, 1)) * usableWidth;
    const y = padding + (1 - (value - min) / range) * usableHeight;
    return `${path} ${path ? "L" : "M"} ${x.toFixed(2)} ${y.toFixed(2)}`.trim();
  }, "");
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
      <p className="mt-3 text-lg font-medium text-slate-900">{value}</p>
    </div>
  );
}

function EmptyChartCopy() {
  return (
    <div className="rounded-[1.5rem] border border-dashed bg-slate-50 px-4 py-12 text-center text-sm text-slate-500">
      This chart will populate once an authenticated dashboard snapshot is available.
    </div>
  );
}

function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "N/A";
  }
  return `${(value * 100).toFixed(1)}%`;
}
