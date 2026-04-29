import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatEuro, formatNumber } from "../api.js";

function BadgeButton({ children, active = false }) {
  return (
    <button type="button" className={`h-9 rounded-lg px-5 text-xs font-extrabold shadow-[0_0_0_1px_#2a2a2a] ${active ? "bg-dashboard-accent/35 text-dashboard-accent" : "bg-black text-white/80"}`}>
      {children}
    </button>
  );
}

function CalendarIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="5" width="16" height="15" rx="2" stroke="#d4f700" strokeWidth="2" />
      <path d="M8 3v4M16 3v4M4 10h16" stroke="#d4f700" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border border-dashboard-accent bg-[#111111] px-3 py-2 text-xs shadow-[0_0_18px_rgba(212,247,0,0.16)]">
      <div className="mb-1 font-extrabold text-white">{label}</div>
      {payload.slice(0, 7).map((entry) => {
        const isPrice = [
          "dam_price_eur_mwh",
          "forecast_price_eur_mwh",
          "storage_adjusted_forecast_eur_mwh",
        ].includes(entry.dataKey);
        const suffix = isPrice ? " EUR/MWh" : entry.dataKey === "soc_pct" ? "%" : " MW";
        return (
          <div key={entry.dataKey} className="flex items-center gap-2 text-dashboard-muted">
            <span className="h-2 w-2 rounded-full" style={{ background: entry.color }} />
            <span>{entry.name}</span>
            <span className="font-bold text-white">{formatNumber(entry.value, isPrice ? 2 : 0)}{suffix}</span>
          </div>
        );
      })}
    </div>
  );
}

function LegendItem({ color, label }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs font-bold text-white/75">
      <span className="h-2 w-5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function EmptyState({ loading }) {
  return (
    <section className="dashboard-card flex min-h-0 items-center justify-center p-5">
      <div className="text-center">
        <div className="text-2xl font-black text-white">{loading ? "Loading public market data" : "Dashboard API unavailable"}</div>
        <div className="mt-2 text-sm font-semibold text-dashboard-muted">
          Start the backend with `PYTHONPATH=src python3 -m batteryhack.api_server`.
        </div>
      </div>
    </section>
  );
}

export default function OperationsPanel({ dashboard, loading }) {
  if (!dashboard?.series?.length) {
    return <EmptyState loading={loading} />;
  }

  const { asset, metrics, windows, series, sources, forecasting } = dashboard;
  const sourceCount = Object.keys(sources ?? {}).length;
  const forecastMetrics = forecasting?.metrics ?? {};
  const registry = forecasting?.registry ?? {};

  return (
    <section className="dashboard-card grid min-h-0 grid-rows-[72px_minmax(0,1fr)] p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black tracking-normal text-white">
            Operations <span className="text-dashboard-muted">&gt;</span> <span className="text-dashboard-accent">{asset.name}</span>
          </h2>
          <div className="mt-3 flex items-center gap-4 text-sm font-bold text-white/75">
            <span>{forecasting?.available ? registry.selected_model : "DAM optimizer"}</span>
            <span>{formatEuro(forecastMetrics.storage_aware_objective_net_revenue_eur ?? metrics.net_revenue_eur)} storage-aware</span>
            <span>{formatNumber(forecastMetrics.base_forecast_mae_eur_mwh ?? 0, 2)} EUR/MWh MAE</span>
            <span>{formatNumber(metrics.res_share_pct, 1)}% RES/load</span>
            <span>{sourceCount} public sources</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex h-9 items-center gap-8 rounded-lg bg-black px-4 text-xs font-bold shadow-[0_0_0_1px_#2a2a2a]">
            <span className="text-white">Delivery Day</span>
            <span className="text-dashboard-accent">{dashboard.delivery_date}</span>
            <CalendarIcon />
          </div>
          <div className="flex rounded-lg bg-black p-0.5 shadow-[0_0_0_1px_#2a2a2a]">
            <BadgeButton>Signals</BadgeButton>
            <BadgeButton active>Dispatch</BadgeButton>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 grid-rows-[28px_minmax(0,1fr)]">
        <div className="flex items-center justify-end gap-4">
          <LegendItem color="#ffffff" label="Load" />
          <LegendItem color="#65b8f2" label="RES" />
          <LegendItem color="#d4f700" label="DAM" />
          <LegendItem color="#b9b35b" label="Base Forecast" />
          <LegendItem color="#ff8f5c" label="Storage Forecast" />
          <LegendItem color="#f2b35e" label="Discharge" />
          <LegendItem color="#4fc3f7" label="Charge" />
        </div>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={series} margin={{ top: 4, right: 36, bottom: 0, left: 8 }}>
            <CartesianGrid stroke="#343434" vertical={false} />
            <XAxis dataKey="time" axisLine={false} tickLine={false} interval={7} tick={{ fill: "#cfcfcf", fontSize: 10, fontWeight: 700 }} />
            <YAxis yAxisId="mw" axisLine={false} tickLine={false} tickFormatter={(value) => `${formatNumber(value, 0)}`} tick={{ fill: "#cfcfcf", fontSize: 11, fontWeight: 700 }} />
            <YAxis yAxisId="price" orientation="right" axisLine={false} tickLine={false} tickFormatter={(value) => `${formatNumber(value, 0)}`} tick={{ fill: "#cfcfcf", fontSize: 11, fontWeight: 700 }} />
            <Tooltip content={<ChartTooltip />} />
            {windows?.map((window) => (
              <ReferenceArea
                key={`${window.kind}-${window.start}-${window.end}`}
                yAxisId="mw"
                x1={window.start}
                x2={window.end}
                fill={window.kind === "Charging" ? "#4fc3f7" : "#d4f700"}
                fillOpacity={window.kind === "Charging" ? 0.14 : 0.18}
              />
            ))}
            <Area yAxisId="mw" type="monotone" dataKey="load_forecast_mw" name="Load Forecast" fill="#666666" stroke="#ffffff" fillOpacity={0.18} strokeWidth={1.8} />
            <Area yAxisId="mw" type="monotone" dataKey="res_forecast_mw" name="RES Forecast" fill="#65b8f2" stroke="#65b8f2" fillOpacity={0.42} strokeWidth={1.8} />
            <Bar yAxisId="mw" dataKey="charge_mw" name="Charge" fill="#4fc3f7" fillOpacity={0.75} radius={[3, 3, 0, 0]} />
            <Bar yAxisId="mw" dataKey="discharge_mw" name="Discharge" fill="#f2b35e" fillOpacity={0.9} radius={[3, 3, 0, 0]} />
            <Line yAxisId="price" type="monotone" dataKey="dam_price_eur_mwh" name="DAM Price" stroke="#d4f700" strokeWidth={2.4} dot={false} />
            <Line yAxisId="price" type="monotone" dataKey="forecast_price_eur_mwh" name="Base Forecast" stroke="#b9b35b" strokeWidth={1.8} strokeDasharray="4 4" dot={false} connectNulls />
            <Line yAxisId="price" type="monotone" dataKey="storage_adjusted_forecast_eur_mwh" name="Storage Forecast" stroke="#ff8f5c" strokeWidth={1.9} strokeDasharray="6 4" dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
