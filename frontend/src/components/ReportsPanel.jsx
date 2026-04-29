import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatEuro, formatNumber } from "../api.js";

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border border-dashboard-accent bg-[#111111] px-3 py-2 text-xs shadow-[0_0_18px_rgba(212,247,0,0.16)]">
      <div className="mb-1 font-extrabold text-white">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2 text-dashboard-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} />
          <span>{entry.name}</span>
          <span className="font-bold text-white">{formatNumber(entry.value, 1)} MW</span>
        </div>
      ))}
    </div>
  );
}

function SelectBox({ label, wide = false }) {
  return (
    <button
      type="button"
      className={`flex h-9 items-center justify-between rounded-lg bg-black px-4 text-sm font-bold text-white shadow-[0_0_0_1px_#2a2a2a] ${wide ? "w-[330px]" : "w-[250px]"}`}
    >
      <span>{label}</span>
      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <path d="M3 4.5 6 7.5l3-3" stroke="#888888" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

function EmptyState({ loading }) {
  return (
    <section className="dashboard-card flex min-h-0 items-center justify-center p-5">
      <div className="text-center">
        <div className="text-2xl font-black text-white">{loading ? "Loading report data" : "Dashboard API unavailable"}</div>
        <div className="mt-2 text-sm font-semibold text-dashboard-muted">
          Reports use the same public-data optimizer payload as the operations view.
        </div>
      </div>
    </section>
  );
}

function ReportChart({ title, data, metrics, compact = false }) {
  return (
    <article className={`grid min-h-0 ${compact ? "grid-rows-[48px_minmax(0,1fr)]" : "grid-rows-[70px_minmax(0,1fr)]"}`}>
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-black text-white">{title}</h3>
          <div className="mt-2 text-sm font-semibold text-white/75">Summary:</div>
          <div className="mt-1 text-xs font-semibold text-dashboard-muted">
            Avg price {formatEuro(metrics.avg_price_eur_mwh, 2)}/MWh - low {formatEuro(metrics.low_price_eur_mwh, 2)} - high {formatEuro(metrics.high_price_eur_mwh, 2)}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="inline-flex items-center gap-2 text-xs font-bold"><span className="h-2 w-5 rounded-full bg-[#1fa8f2]" />Load</span>
          <span className="inline-flex items-center gap-2 text-xs font-bold"><span className="h-2 w-5 rounded-full bg-[#3dd0ad]" />Net After BESS</span>
          <span className="inline-flex items-center gap-2 text-xs font-bold"><span className="h-2 w-5 rounded-full bg-dashboard-accent" />Battery Net</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 20, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="#343434" vertical={false} />
          <XAxis dataKey="time" axisLine={false} tickLine={false} interval={7} tick={{ fill: "#cfcfcf", fontSize: 11, fontWeight: 700 }} />
          <YAxis axisLine={false} tickLine={false} width={68} tickFormatter={(value) => `${formatNumber(value, 0)}`} tick={{ fill: "#cfcfcf", fontSize: 11, fontWeight: 700 }} />
          <Tooltip content={<ChartTooltip />} />
          <Line name="Load" type="monotone" dataKey="load_forecast_mw" stroke="#1fa8f2" strokeWidth={2.2} dot={false} />
          <Line name="Net After BESS" type="monotone" dataKey="net_system_after_battery_mw" stroke="#3dd0ad" strokeWidth={2.2} dot={false} />
          <Line name="Battery Net" type="stepAfter" dataKey="battery_net_mw" stroke="#d4f700" strokeWidth={2.2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </article>
  );
}

export default function ReportsPanel({ dashboard, loading }) {
  if (!dashboard?.series?.length) {
    return <EmptyState loading={loading} />;
  }

  const data = dashboard.series;
  const metrics = dashboard.metrics;

  return (
    <section className="dashboard-card grid min-h-0 grid-rows-[42px_112px_minmax(0,1fr)_34px] p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-black">Statistic Reports</h2>
        <div className="flex items-center gap-4">
          <SelectBox label={dashboard.delivery_date} />
          <SelectBox label={`${dashboard.asset.name} + DAM`} wide />
          <button type="button" className="h-9 rounded-lg bg-dashboard-accent/35 px-8 text-sm font-extrabold text-dashboard-accent shadow-[0_0_0_1px_rgba(212,247,0,0.4)]">Generate</button>
          <button type="button" className="h-9 rounded-lg bg-black px-8 text-sm font-extrabold text-white/65 shadow-[0_0_0_1px_#2a2a2a]">Reports</button>
        </div>
      </div>

      <div className="border-b border-dashboard-border pt-4">
        <div className="mb-5 flex gap-12 text-sm font-black uppercase tracking-[0.12em] text-dashboard-muted">
          <span className="border-b-2 border-dashboard-accent pb-3 text-dashboard-accent">Charts</span>
          <span>Data</span>
          <span>Log</span>
          <span>Comments</span>
        </div>
        <div className="grid grid-cols-4 gap-5">
          <SelectBox label="Dispatch Report" />
          <SelectBox label="Load, RES, Battery" />
          <SelectBox label="15-Minute MTU" />
          <SelectBox label="METLEN Thessaly" />
        </div>
      </div>

      <div className="grid min-h-0 grid-rows-[1.55fr_0.8fr] gap-4 pt-4">
        <ReportChart title="Operation Status Config" data={data} metrics={metrics} />
        <ReportChart title="Battery Net Dispatch" data={data} metrics={metrics} compact />
      </div>

      <div className="flex items-center justify-between text-xs font-bold text-dashboard-muted">
        <span>{data.length} intervals - {formatNumber(metrics.total_load_mwh, 0)} MWh load forecast</span>
        <div className="flex items-center gap-6">
          <span className="rounded bg-dashboard-accent px-3 py-2 text-black">1</span>
          <span>2</span>
          <span>3</span>
        </div>
        <div className="flex items-center gap-7 uppercase tracking-[0.12em]">
          <span>Public Sources: {Object.keys(dashboard.sources ?? {}).length}</span>
          <span className="text-dashboard-accent">Optimizer: Optimal</span>
        </div>
      </div>
    </section>
  );
}
