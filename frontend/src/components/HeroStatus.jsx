import { formatEuro, formatNumber } from "../api.js";

function BatteryNode() {
  return (
    <g>
      <rect x="-8" y="-5" width="16" height="10" rx="2" stroke="#f2b35e" strokeWidth="1.5" fill="#242424" />
      <rect x="8" y="-2" width="2" height="4" rx="1" fill="#f2b35e" />
      <path d="M-2 -1h4M0 -3v4" stroke="#f2b35e" strokeWidth="1.3" strokeLinecap="round" />
    </g>
  );
}

function BuildingNode({ color = "#d4f700" }) {
  return (
    <g>
      <rect x="-8" y="-8" width="16" height="16" rx="1.5" stroke={color} strokeWidth="1.4" fill="#242424" />
      <path d="M-4 -4h2M2 -4h2M-4 0h2M2 0h2M-4 4h2M2 4h2" stroke={color} strokeWidth="1.1" strokeLinecap="round" />
    </g>
  );
}

function SolarNode() {
  return (
    <g>
      <rect x="-8" y="-5" width="16" height="10" rx="1" stroke="#666666" strokeWidth="1.4" fill="#242424" />
      <path d="M-4 -5v10M2 -5v10M-8 -1h16M-8 3h16" stroke="#666666" strokeWidth="0.9" />
    </g>
  );
}

function TowerNode() {
  return (
    <g>
      <path d="M0-11 8 10H-8L0-11Z" stroke="#f2b35e" strokeWidth="1.5" fill="#242424" />
      <path d="M0-5v12M-5 7h10" stroke="#f2b35e" strokeWidth="1.4" strokeLinecap="round" />
    </g>
  );
}

function FlowDot({ path, delay = "0s" }) {
  return (
    <circle r="3.2" fill="#d4f700" className="flow-dot">
      <animateMotion dur="2.6s" repeatCount="indefinite" begin={delay} path={path} />
    </circle>
  );
}

function WidePowerFlow({ dashboard }) {
  const metrics = dashboard?.metrics ?? {};
  const asset = dashboard?.asset ?? {};
  const topPath = "M92 42 H276 C294 42 292 70 318 70 H462";
  const bottomPath = "M46 82 H274 C296 82 292 70 318 70 H548";
  const power = asset.params?.power_mw ? `${formatNumber(asset.params.power_mw)} MW` : "330 MW";
  const charge = metrics.charged_mwh ? `${formatNumber(metrics.charged_mwh, 0)} MWh` : "loading";
  const discharge = metrics.discharged_mwh ? `${formatNumber(metrics.discharged_mwh, 0)} MWh` : "loading";

  return (
    <article className="dashboard-card flex h-full items-center justify-center overflow-hidden">
      <svg viewBox="0 0 620 106" className="h-full w-full" role="img" aria-label="Battery, building, grid, and solar power flow">
        <defs>
          <linearGradient id="activeFlow" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#f2b35e" />
            <stop offset="48%" stopColor="#d4f700" />
            <stop offset="100%" stopColor="#f2b35e" />
          </linearGradient>
        </defs>

        <path d={topPath} stroke="url(#activeFlow)" strokeWidth="3" fill="none" opacity="0.95" />
        <path d={bottomPath} stroke="#585858" strokeWidth="3" fill="none" opacity="0.8" />
        <FlowDot path={topPath} />
        <FlowDot path={topPath} delay="0.9s" />

        <g transform="translate(92 42)">
          <circle r="18" fill="#222222" stroke="#f2b35e" strokeWidth="2" />
          <BatteryNode />
        </g>
        <g transform="translate(318 70)">
          <circle r="18" fill="#222222" stroke="#f2b35e" strokeWidth="2" />
          <BuildingNode color="#f2b35e" />
        </g>
        <g transform="translate(462 42)">
          <circle r="18" fill="#222222" stroke="#f2b35e" strokeWidth="2" />
          <TowerNode />
        </g>
        <g transform="translate(46 82)">
          <circle r="18" fill="#222222" stroke="#555555" strokeWidth="2" />
          <BuildingNode color="#666666" />
        </g>
        <g transform="translate(548 82)">
          <circle r="18" fill="#222222" stroke="#555555" strokeWidth="2" />
          <SolarNode />
        </g>
        <text x="72" y="25" fill="#f2b35e" fontSize="11" fontWeight="800">{power}</text>
        <text x="278" y="54" fill="#d4f700" fontSize="11" fontWeight="800">dispatch</text>
        <text x="408" y="25" fill="#f2b35e" fontSize="11" fontWeight="800">{discharge}</text>
        <text x="50" y="102" fill="#888888" fontSize="10" fontWeight="700">charge {charge}</text>
      </svg>
    </article>
  );
}

function GreetingCard({ dashboard, error, loading, onRefresh }) {
  const asset = dashboard?.asset;
  const metrics = dashboard?.metrics;
  const forecasting = dashboard?.forecasting;
  const date = dashboard?.delivery_date ?? "2026-04-22";

  return (
    <article className="flex h-full flex-col justify-center px-5">
      <h1 className="text-2xl font-black tracking-normal text-white">Hello, METLEN!</h1>
      <div className="mt-1 text-sm font-extrabold text-dashboard-accent">
        {asset ? `${asset.name} "${formatNumber(asset.params.power_mw)}MW_${formatNumber(asset.params.capacity_mwh)}MWH"` : "Connecting to battery optimizer"}
      </div>
      <div className="mt-3 flex items-center gap-2 text-sm font-semibold text-dashboard-muted">
        <span>Delivery day {date}</span>
        <span className="rounded bg-white/10 px-2 py-1 text-[10px] font-extrabold text-dashboard-accent">EUROPE/ATHENS</span>
      </div>
      <div className="mt-3 text-xs font-semibold text-white/65">
        {error ? (
          <button type="button" onClick={onRefresh} className="rounded bg-red-500/15 px-3 py-1 text-red-200">
            Backend offline: {error}
          </button>
        ) : loading ? (
          "Loading public DAM, IPTO forecasts, and optimizer output..."
        ) : forecasting?.available ? (
          `${forecasting.registry.selected_model} forecast, ${formatEuro(forecasting.metrics.storage_aware_objective_net_revenue_eur)} storage-aware value`
        ) : (
          `${formatEuro(metrics.net_revenue_eur)} net revenue, ${formatNumber(metrics.equivalent_cycles, 2)} cycles`
        )}
      </div>
    </article>
  );
}

function CompactAssetCard({ dashboard }) {
  const asset = dashboard?.asset;
  const metrics = dashboard?.metrics ?? {};
  const forecasting = dashboard?.forecasting;
  const impact = forecasting?.metrics ?? {};

  return (
    <article className="dashboard-card flex h-full flex-col justify-center px-5">
      <div className="text-xs font-extrabold uppercase tracking-[0.14em] text-dashboard-muted">Asset Mode</div>
      <div className="mt-2 text-xl font-black text-white">{asset?.mode ?? "DAM Optimizer"}</div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs font-bold">
        <span className="rounded bg-black/45 px-2 py-2 text-dashboard-accent">{formatNumber(asset?.duration_hours ?? 2.39, 2)}h duration</span>
        <span className="rounded bg-black/45 px-2 py-2 text-dashboard-blue">{formatNumber((asset?.params?.round_trip_efficiency ?? 0.85) * 100, 0)}% RTE</span>
        <span className="rounded bg-black/45 px-2 py-2 text-white/80">{formatNumber(impact.impact_spread_compression_pct ?? 0, 1)}% compression</span>
        <span className="rounded bg-black/45 px-2 py-2 text-white/80">{formatNumber(asset?.usable_energy_mwh ?? 632, 0)} MWh usable</span>
      </div>
    </article>
  );
}

export default function HeroStatus({ dashboard, error, loading, onRefresh }) {
  return (
    <section className="grid min-h-0 grid-cols-[0.9fr_1.8fr_0.62fr] gap-4">
      <GreetingCard dashboard={dashboard} error={error} loading={loading} onRefresh={onRefresh} />
      <WidePowerFlow dashboard={dashboard} />
      <CompactAssetCard dashboard={dashboard} />
    </section>
  );
}
