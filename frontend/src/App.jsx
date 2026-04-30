import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Zap } from "lucide-react";
import { fetchDashboardData, formatEuro, formatNumber } from "./api.js";

const navItems = ["Live Dispatch", "Evidence", "Details"];
const DEMO_CYCLE_CAP = 1.0;

const LIVE_DEMO_PARAMS = {
  power_mw: 330,
  capacity_mwh: 790,
  round_trip_efficiency: 0.85,
  min_soc_pct: 10,
  max_soc_pct: 90,
  initial_soc_pct: 50,
  terminal_soc_pct: 50,
  max_cycles_per_day: DEMO_CYCLE_CAP,
  degradation_cost_eur_mwh: 4,
};

const RESEARCH_PARAMS = {
  ...LIVE_DEMO_PARAMS,
  max_cycles_per_day: 1.5,
};

const PARAMETER_FIELDS = [
  { key: "power_mw", label: "Power MW", min: 1, step: 10 },
  { key: "capacity_mwh", label: "Capacity MWh", min: 1, step: 10 },
  { key: "round_trip_efficiency", label: "Round-trip efficiency", min: 0.1, max: 1, step: 0.01 },
  { key: "min_soc_pct", label: "SoC min %", min: 0, max: 100, step: 1 },
  { key: "max_soc_pct", label: "SoC max %", min: 0, max: 100, step: 1 },
  { key: "initial_soc_pct", label: "Initial SoC %", min: 0, max: 100, step: 1 },
  { key: "terminal_soc_pct", label: "Terminal SoC %", min: 0, max: 100, step: 1 },
  { key: "max_cycles_per_day", label: "Max cycles/day", min: 0.1, step: 0.1 },
  { key: "degradation_cost_eur_mwh", label: "Degradation cost EUR/MWh", min: 0, step: 0.5 },
];

const actionStyles = {
  Charge: { fill: "#2f9d66", chip: "bg-[#eaf6ef] text-[#2f9d66] border-[#cfe5d7]" },
  Discharge: { fill: "#df6b45", chip: "bg-[#fff0ea] text-[#b64f2f] border-[#f4c7b8]" },
  Idle: { fill: "#b8bbc2", chip: "bg-stone-100 text-stone-500 border-stone-200" },
};

const PRESENTATION_EVIDENCE = {
  available: false,
  strategy_comparison: {
    headline: {
      evaluated_days: 38,
      best_model: "scarcity_ensemble",
      best_ml_strategy: "ml_scarcity_ensemble",
      ml_total_pnl_eur: 2968322.4877469926,
      uk_baseline_total_pnl_eur: 2571165.347645675,
      uplift_eur: 397157.1401013178,
      uplift_pct: 0.15446581079080757,
      win_rate_vs_uk_baseline: 0.7894736842105263,
      best_ml_by_total_realized_net_revenue_eur: {
        strategy: "ml_scarcity_ensemble",
        model_or_method: "scarcity_ensemble",
        days: 38,
        total_realized_net_revenue_eur: 2968322.4877469926,
      },
      best_ml_by_forecast_mae_eur_mwh: {
        strategy: "ml_scarcity_ensemble",
        model_or_method: "scarcity_ensemble",
        days: 38,
        forecast_mae_eur_mwh: 20.514628014739337,
        total_realized_net_revenue_eur: 2968322.487746992,
      },
      uk_baseline: {
        total_realized_net_revenue_eur: 2571165.347645675,
      },
    },
  },
  model_stability: [
    {
      criterion: "mae",
      winning_model: "extra_trees",
      winning_value: 19.491981800828103,
    },
  ],
  paired_uplift: [
    {
      primary_model: "scarcity_ensemble",
      comparison_model: "ridge",
      paired_days: 38,
      total_pnl_uplift_eur: 86763.48625999191,
      primary_win_days: 28,
      comparison_win_days: 10,
    },
  ],
  future_market_impact: {
    notice: "Strategic spread-compression stress test only; not a Greek price forecast.",
    strategy_model: "ml_scarcity_ensemble",
    scenarios: [
      {
        scenario: "conservative",
        fixed_schedule_degradation_pct: 16.230721,
        reoptimized_degradation_pct: -3.552894,
        reoptimization_recovery_eur: 587241.489955,
        interpretation_label: "redispatch improves this sample day",
        sample_days: 38,
      },
      {
        scenario: "base",
        fixed_schedule_degradation_pct: 38.297636,
        reoptimized_degradation_pct: 22.256624,
        reoptimization_recovery_eur: 476148.975218,
        interpretation_label: "redispatch partially offsets compression",
        sample_days: 38,
      },
      {
        scenario: "aggressive",
        fixed_schedule_degradation_pct: 62.597974,
        reoptimized_degradation_pct: 49.519451,
        reoptimization_recovery_eur: 388212.731973,
        interpretation_label: "severe compression stress",
        sample_days: 38,
      },
    ],
  },
};

function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

function asNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function asParameterNumber(value, fallback) {
  if (value === "" || value === null || value === undefined) return fallback;
  return asNumber(value, fallback);
}

function sanitizeBatteryParams(params) {
  return Object.fromEntries(
    PARAMETER_FIELDS.map((field) => [field.key, asParameterNumber(params[field.key], LIVE_DEMO_PARAMS[field.key])]),
  );
}

function sameBatteryParams(a, b) {
  return PARAMETER_FIELDS.every((field) => Math.abs(asNumber(a[field.key]) - asNumber(b[field.key])) < 1e-9);
}

function getPresetName(params) {
  if (sameBatteryParams(params, LIVE_DEMO_PARAMS)) return "demo";
  if (sameBatteryParams(params, RESEARCH_PARAMS)) return "research";
  return "custom";
}

function getCycleCapLabel(health) {
  const cap = asNumber(health?.cycleCap, DEMO_CYCLE_CAP);
  if (Math.abs(cap - DEMO_CYCLE_CAP) < 1e-9) return "Demo cycle cap: 1.0/day";
  return `Live cycle cap: ${formatNumber(cap, 1)}/day`;
}

function formatPercent(value, digits = 1) {
  return `${formatNumber(asNumber(value), digits)}%`;
}

function formatPower(value, digits = 0) {
  return `${formatNumber(asNumber(value), digits)} MW`;
}

function formatEuroCompact(value, digits = 3) {
  const number = asNumber(value, null);
  if (number === null) return "Unavailable";
  const abs = Math.abs(number);
  if (abs >= 1_000_000) return `EUR ${(number / 1_000_000).toFixed(digits)}M`;
  if (abs >= 1_000) return `EUR ${Math.round(number / 1_000).toLocaleString()}k`;
  return formatEuro(number, 0);
}

function formatAxisEuro(value) {
  const number = asNumber(value);
  if (Math.abs(number) >= 1_000_000) return `EUR ${formatNumber(number / 1_000_000, 0)}M`;
  if (Math.abs(number) >= 1_000) return `EUR ${formatNumber(number / 1_000, 0)}k`;
  return `EUR ${formatNumber(number, 0)}`;
}

function formatDateLabel(value) {
  if (!value) return "Delivery day";
  try {
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }).format(new Date(`${value}T00:00:00`));
  } catch {
    return value;
  }
}

function normalizeModelKey(value) {
  if (!value) return "";
  return String(value).replace(/^ml_/, "");
}

function formatModelName(value) {
  const normalized = normalizeModelKey(value);
  const labels = {
    extra_trees: "ExtraTrees",
    ridge: "Ridge",
    scarcity_ensemble: "Scarcity Ensemble",
    scarcity_ensemble_conservative: "Conservative Scarcity Ensemble",
    uk_naive_baseline: "UK naive baseline",
  };
  return labels[normalized] ?? String(value ?? "Unavailable");
}

function getEvidenceSlice(dashboard) {
  const evidence = dashboard?.evidence ?? {};
  return {
    raw: evidence,
    headline: evidence.strategy_comparison?.headline ?? PRESENTATION_EVIDENCE.strategy_comparison.headline,
    cumulativePnl: Array.isArray(evidence.strategy_comparison?.cumulative_pnl)
      ? evidence.strategy_comparison.cumulative_pnl
      : [],
    modelStability: evidence.model_stability ?? PRESENTATION_EVIDENCE.model_stability,
    pairedUplift: evidence.paired_uplift ?? PRESENTATION_EVIDENCE.paired_uplift,
    futureMarketImpact: evidence.future_market_impact ?? PRESENTATION_EVIDENCE.future_market_impact,
  };
}

function buildSchedule(dashboard) {
  const rows = dashboard?.series ?? [];
  const useForecast = Boolean(dashboard?.forecasting?.available);
  const initialSoc = dashboard?.asset?.params?.initial_soc_pct ?? 50;

  return rows.map((row, index) => {
    const prev = rows[index - 1];
    const chargeMw = asNumber(useForecast ? row.forecast_charge_mw : row.charge_mw);
    const dischargeMw = asNumber(useForecast ? row.forecast_discharge_mw : row.discharge_mw);
    const socEnd = asNumber(useForecast ? row.forecast_soc_pct ?? row.soc_pct : row.soc_pct, initialSoc);
    const socStart = asNumber(
      useForecast ? prev?.forecast_soc_pct ?? prev?.soc_pct : prev?.soc_pct,
      index === 0 ? initialSoc : socEnd,
    );
    const price = asNumber(useForecast ? row.forecast_price_eur_mwh ?? row.dam_price_eur_mwh : row.dam_price_eur_mwh);
    const action = chargeMw > 1e-3 ? "Charge" : dischargeMw > 1e-3 ? "Discharge" : "Idle";

    return {
      ...row,
      action,
      time: row.time,
      endTime: rows[index + 1]?.time ?? "24:00",
      chargeMw,
      dischargeMw,
      powerAbs: Math.max(chargeMw, dischargeMw),
      price,
      socStart,
      socEnd,
    };
  });
}

function buildActionWindows(schedule) {
  const windows = [];
  let current = null;

  schedule.forEach((point) => {
    if (point.action === "Idle") {
      if (current) {
        windows.push(current);
        current = null;
      }
      return;
    }

    if (!current || current.action !== point.action) {
      if (current) windows.push(current);
      current = {
        start: point.time,
        end: point.endTime,
        action: point.action,
        mw: point.powerAbs,
        socEnd: point.socEnd,
      };
      return;
    }

    current.end = point.endTime;
    current.mw = Math.max(current.mw, point.powerAbs);
    current.socEnd = point.socEnd;
  });

  if (current) windows.push(current);
  return windows;
}

function getHealth(dashboard, schedule) {
  const metrics = dashboard?.metrics ?? {};
  const params = dashboard?.asset?.params ?? {};
  const minBand = asNumber(params.min_soc_pct, 10);
  const maxBand = asNumber(params.max_soc_pct, 90);
  const socValues = schedule.flatMap((point) => [point.socStart, point.socEnd]).filter((value) => Number.isFinite(Number(value)));
  const minSoc = socValues.length ? Math.min(...socValues) : minBand;
  const maxSoc = socValues.length ? Math.max(...socValues) : maxBand;
  const noSimultaneous = schedule.every((point) => !(point.chargeMw > 1e-3 && point.dischargeMw > 1e-3));
  const cycles = asNumber(metrics.equivalent_cycles);
  const cycleCap = asNumber(params.max_cycles_per_day, DEMO_CYCLE_CAP);

  return {
    cycles,
    cycleCap,
    minSoc,
    maxSoc,
    minBand,
    maxBand,
    noSimultaneous,
    socRespected: minSoc >= minBand - 0.05 && maxSoc <= maxBand + 0.05,
    cycleRespected: cycles <= cycleCap + 0.01,
    degradationCost: metrics.degradation_cost_eur,
  };
}

function Card({ children, className = "" }) {
  return <section className={cx("rounded-lg border border-stone-200/80 bg-white shadow-soft", className)}>{children}</section>;
}

function Header({ activeTab, setActiveTab, dashboard, loading, onRefresh }) {
  return (
    <header className="sticky top-0 z-30 border-b border-stone-200/80 bg-[#f7f5f0]/95 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[#202326] text-white shadow-sm">
            <Zap size={18} strokeWidth={2.4} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-tight text-[#202326]">METLEN Battery Optimizer</p>
            <p className="truncate text-xs text-stone-500">{formatDateLabel(dashboard?.delivery_date)} / Greek DAM</p>
          </div>
        </div>

        <nav className="hidden md:block">
          <NavPills activeTab={activeTab} setActiveTab={setActiveTab} />
        </nav>

        <div className="flex items-center gap-2">
          <span className="hidden rounded-full border border-[#cfe5d7] bg-[#f2faf5] px-3 py-1.5 text-xs font-semibold text-[#2f9d66] sm:inline-flex">
            {loading ? "Loading" : dashboard?.data_quality ?? "Ready"}
          </span>
          <button
            type="button"
            onClick={onRefresh}
            className="grid h-10 w-10 place-items-center rounded-lg border border-stone-200 bg-white text-stone-600 shadow-sm transition hover:text-[#202326]"
            aria-label="Refresh dashboard data"
            title="Refresh dashboard data"
          >
            <RefreshCw size={17} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>
      <div className="mx-auto max-w-7xl px-5 pb-4 sm:px-8 md:hidden">
        <NavPills activeTab={activeTab} setActiveTab={setActiveTab} compact />
      </div>
    </header>
  );
}

function NavPills({ activeTab, setActiveTab, compact = false }) {
  return (
    <div
      className={cx(
        "flex items-center gap-1 overflow-x-auto rounded-full border border-stone-200 bg-white p-1 font-medium text-stone-500 shadow-sm",
        compact ? "text-xs" : "text-sm",
      )}
    >
      {navItems.map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => setActiveTab(item)}
          className={cx(
            "shrink-0 rounded-full px-4 py-2 transition-colors",
            activeTab === item ? "bg-[#202326] text-white" : "hover:bg-stone-100 hover:text-[#202326]",
          )}
        >
          {item}
        </button>
      ))}
    </div>
  );
}

function TodayView({ dashboard, schedule, actionWindows, health, loading, error }) {
  const metrics = dashboard?.metrics ?? {};
  const forecastMetrics = dashboard?.forecasting?.metrics ?? {};
  const primaryPnl = dashboard?.forecasting?.available
    ? forecastMetrics.price_taker_objective_net_revenue_eur
    : metrics.net_revenue_eur;
  const modeLabel = dashboard?.forecasting?.available ? "Forecast-optimized day PnL" : "Optimized net day PnL";

  return (
    <div className="grid gap-5">
      {(error || dashboard?.warnings?.length > 0) && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {error || dashboard.warnings.slice(0, 1).join(" ")}
        </div>
      )}

      <section className="grid gap-4 lg:grid-cols-[0.95fr_1.05fr]">
        <Card className="p-6 sm:p-7">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">{modeLabel}</p>
          <p className="mt-4 break-words text-5xl font-semibold tracking-tight text-[#202326] sm:text-6xl">
            {loading ? "Loading" : formatEuro(primaryPnl)}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <SmallChip label={getCycleCapLabel(health)} tone="green" />
            <SmallChip label={dashboard?.forecasting?.available ? "ML dispatch" : "DAM dispatch"} />
          </div>
        </Card>

        <BatteryHealthCard health={health} />
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.45fr_0.55fr]">
        <DispatchChart schedule={schedule} />
        <ActionTimetable windows={actionWindows} />
      </section>
    </div>
  );
}

function DispatchChart({ schedule }) {
  if (!schedule.length) {
    return (
      <Card className="flex min-h-[360px] items-center justify-center p-8">
        <p className="text-sm font-semibold text-stone-500">Waiting for dispatch data</p>
      </Card>
    );
  }

  const width = 1120;
  const height = 420;
  const pad = { top: 26, right: 28, bottom: 42, left: 52 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const prices = schedule.map((point) => point.price).filter((value) => Number.isFinite(Number(value)));
  const minPrice = Math.min(...prices) - 8;
  const maxPrice = Math.max(...prices) + 8;
  const priceRange = Math.max(1, maxPrice - minPrice);
  const slotWidth = innerWidth / schedule.length;
  const maxPower = Math.max(...schedule.map((point) => point.powerAbs), 1);
  const midY = pad.top + innerHeight * 0.62;
  const points = schedule
    .map((point, index) => {
      const x = pad.left + index * slotWidth + slotWidth / 2;
      const y = pad.top + innerHeight * 0.52 - ((point.price - minPrice) / priceRange) * (innerHeight * 0.48);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <Card className="p-5 sm:p-6">
      <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Price + Battery Action</h2>
        <div className="flex flex-wrap gap-2 text-xs font-semibold">
          <SmallChip label="Charge" tone="charge" />
          <SmallChip label="Discharge" tone="discharge" />
          <SmallChip label="Idle" />
        </div>
      </div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="min-w-[900px]" role="img" aria-label="Battery action and price chart">
          {[minPrice, (minPrice + maxPrice) / 2, maxPrice].map((tick) => {
            const y = pad.top + innerHeight * 0.52 - ((tick - minPrice) / priceRange) * (innerHeight * 0.48);
            return (
              <g key={tick}>
                <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} stroke="#e7e2d8" strokeDasharray="5 8" />
                <text x={12} y={y + 4} className="fill-stone-400 text-[12px]">
                  {formatNumber(tick, 0)}
                </text>
              </g>
            );
          })}
          <line x1={pad.left} x2={width - pad.right} y1={midY} y2={midY} stroke="#d7d0c4" />

          {schedule.map((point, index) => {
            const x = pad.left + index * slotWidth + 0.9;
            const barHeight = point.action === "Idle" ? 10 : 24 + (point.powerAbs / maxPower) * 120;
            const y = point.action === "Charge" ? midY : midY - barHeight;
            return (
              <rect
                key={`${point.time}-${point.action}`}
                x={x}
                y={y}
                width={Math.max(4, slotWidth - 2)}
                height={barHeight}
                rx="3"
                fill={actionStyles[point.action].fill}
                opacity={point.action === "Idle" ? 0.3 : 0.88}
              />
            );
          })}

          <polyline points={points} fill="none" stroke="#365f93" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />

          {[0, 16, 32, 48, 64, 80, schedule.length - 1].map((index) => {
            const point = schedule[index];
            if (!point) return null;
            return (
              <text key={`${point.time}-${index}`} x={pad.left + index * slotWidth} y={height - 16} textAnchor="middle" className="fill-stone-500 text-[12px]">
                {point.time}
              </text>
            );
          })}
        </svg>
      </div>
    </Card>
  );
}

function ActionTimetable({ windows }) {
  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Action Windows</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[360px] text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.12em] text-stone-500">
            <tr>
              <th className="border-b border-stone-200 pb-2 font-semibold">Time</th>
              <th className="border-b border-stone-200 pb-2 font-semibold">Action</th>
              <th className="border-b border-stone-200 pb-2 font-semibold">MW</th>
              <th className="border-b border-stone-200 pb-2 font-semibold">SoC end</th>
            </tr>
          </thead>
          <tbody>
            {windows.length ? (
              windows.map((window) => (
                <tr key={`${window.start}-${window.action}`}>
                  <td className="border-b border-stone-100 py-3 font-semibold text-[#202326]">{window.start}-{window.end}</td>
                  <td className="border-b border-stone-100 py-3">
                    <span className={cx("rounded-full border px-2 py-1 text-xs font-semibold", actionStyles[window.action].chip)}>
                      {window.action}
                    </span>
                  </td>
                  <td className="border-b border-stone-100 py-3 text-stone-600">{formatNumber(window.mw, 0)}</td>
                  <td className="border-b border-stone-100 py-3 text-stone-600">{formatPercent(window.socEnd, 1)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="4" className="py-5 text-sm text-stone-500">No active windows in this payload.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function BatteryHealthCard({ health }) {
  return (
    <Card className="p-6 sm:p-7">
      <div className="mb-5 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Battery Constraints</h2>
        <SmallChip label={getCycleCapLabel(health)} tone="green" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <HealthChip label="Equivalent cycles" value={formatNumber(health.cycles, 2)} pass={health.cycleRespected} />
        <HealthChip label="Cycle cap" value={`${formatNumber(health.cycleCap, 1)}/day`} pass={health.cycleRespected} />
        <HealthChip label="SoC band" value={`${formatPercent(health.minSoc, 0)}-${formatPercent(health.maxSoc, 0)}`} pass={health.socRespected} />
        <HealthChip label="Single mode" value={health.noSimultaneous ? "No overlap" : "Overlap"} pass={health.noSimultaneous} />
      </div>
      <div className="mt-4 rounded-lg border border-stone-200 bg-stone-50 p-3">
        <p className="text-xs font-medium text-stone-500">Estimated battery wear cost</p>
        <p className="mt-1 text-base font-semibold text-[#202326]">{formatEuro(health.degradationCost)}</p>
      </div>
    </Card>
  );
}

function HealthChip({ label, value, pass }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-stone-500">{label}</p>
          <p className="mt-1 font-semibold text-[#202326]">{value}</p>
        </div>
        <span className={cx("rounded-full px-2 py-1 text-xs font-semibold", pass ? "bg-[#eaf6ef] text-[#2f9d66]" : "bg-amber-100 text-amber-800")}>
          {pass ? "Pass" : "Check"}
        </span>
      </div>
    </div>
  );
}

function EvidenceView({ dashboard }) {
  const { raw, headline, cumulativePnl, modelStability, pairedUplift, futureMarketImpact } = getEvidenceSlice(dashboard);
  const bestTotal = headline.best_ml_by_total_realized_net_revenue_eur ?? {};
  const bestModel = normalizeModelKey(headline.best_model ?? bestTotal.model_or_method ?? bestTotal.strategy);
  const bestLabel = formatModelName(bestModel);
  const baseline = headline.uk_baseline ?? {};
  const mlPnl = headline.ml_total_pnl_eur ?? bestTotal.total_realized_net_revenue_eur;
  const baselinePnl = headline.uk_baseline_total_pnl_eur ?? baseline.total_realized_net_revenue_eur;
  const maeWinner = modelStability.find((row) => row.criterion === "mae") ?? {};
  const ridgePair = pairedUplift.find((row) => normalizeModelKey(row.comparison_model) === "ridge") ?? {};
  const statusLabel = raw.available ? "Research artifacts loaded" : "Fallback demo values shown";
  const stressStrategy = formatModelName(futureMarketImpact.strategy_model);

  return (
    <div className="grid gap-5">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">38-day evidence</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#202326]">ML beats the UK naive baseline</h1>
        </div>
        <SmallChip label={statusLabel} tone={raw.available ? "default" : "amber"} />
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <EvidenceMetric label={bestLabel} value="EUR 2.968M" detail={formatEuro(mlPnl)} />
        <EvidenceMetric label="UK naive baseline" value="EUR 2.571M" detail={formatEuro(baselinePnl)} />
        <EvidenceMetric label="Uplift" value="EUR 397k / 15.45%" detail={formatEuro(headline.uplift_eur)} />
        <EvidenceMetric label="Win rate" value="78.9%" detail={`${formatNumber(asNumber(headline.win_rate_vs_uk_baseline) * 100, 1)}% of days`} />
      </section>

      <CumulativePnlChart cumulativePnl={cumulativePnl} mlPnl={mlPnl} baselinePnl={baselinePnl} />

      <section className="grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
        <Card className="p-6">
          <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Model Notes</h2>
          <div className="mt-4 grid gap-3">
            <CompactFact label="Forecast MAE challenger" value={formatModelName(maeWinner.winning_model)} />
            <CompactFact label="Best vs Ridge days" value={ridgePair.primary_win_days ? `${ridgePair.primary_win_days} vs ${ridgePair.comparison_win_days}` : "Available in paired output"} />
          </div>
        </Card>

        <Card className="p-6">
          <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Future BESS Stress Test</h2>
            <SmallChip label={`Stress strategy: ${stressStrategy}`} tone="green" />
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {(futureMarketImpact.scenarios ?? []).map((scenario) => (
              <div key={scenario.scenario} className="rounded-lg border border-stone-200 bg-stone-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">{scenario.scenario}</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-[#202326]">{formatPercent(scenario.reoptimized_degradation_pct, 1)}</p>
                <p className="mt-1 text-xs text-stone-500">reoptimized degradation</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-stone-500">Spread-compression stress only; not a Greek price forecast.</p>
        </Card>
      </section>
    </div>
  );
}

function CumulativePnlChart({ cumulativePnl, mlPnl, baselinePnl }) {
  const rows = (cumulativePnl ?? []).filter(
    (row) =>
      Number.isFinite(Number(row.ml_cumulative_pnl_eur)) &&
      Number.isFinite(Number(row.baseline_cumulative_pnl_eur)),
  );

  if (rows.length < 2) {
    return (
      <Card className="p-6">
        <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Cumulative PnL over 38-day walk-forward test</h2>
          <SmallChip label="daily path unavailable" tone="amber" />
        </div>
        <ComparisonBars mlPnl={mlPnl} baselinePnl={baselinePnl} />
      </Card>
    );
  }

  const width = 980;
  const height = 390;
  const pad = { top: 26, right: 172, bottom: 42, left: 78 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const maxValue = Math.max(
    3_000_000,
    ...rows.map((row) => asNumber(row.ml_cumulative_pnl_eur)),
    ...rows.map((row) => asNumber(row.baseline_cumulative_pnl_eur)),
  );
  const yMax = Math.ceil(maxValue / 1_000_000) * 1_000_000;
  const ticks = Array.from({ length: Math.floor(yMax / 1_000_000) + 1 }, (_, index) => index * 1_000_000);

  const pointFor = (row, index, key) => {
    const x = pad.left + (index / Math.max(rows.length - 1, 1)) * innerWidth;
    const y = pad.top + innerHeight - (asNumber(row[key]) / yMax) * innerHeight;
    return { x, y };
  };
  const pathFor = (key) =>
    rows
      .map((row, index) => {
        const point = pointFor(row, index, key);
        return `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
      })
      .join(" ");

  const finalRow = rows[rows.length - 1];
  const finalIndex = rows.length - 1;
  const finalMl = pointFor(finalRow, finalIndex, "ml_cumulative_pnl_eur");
  const finalBaseline = pointFor(finalRow, finalIndex, "baseline_cumulative_pnl_eur");
  const finalGap = asNumber(finalRow.cumulative_uplift_eur, asNumber(mlPnl) - asNumber(baselinePnl));

  return (
    <Card className="p-6">
      <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Cumulative PnL over 38-day walk-forward test</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            <SmallChip label="Scarcity Ensemble" tone="green" />
            <SmallChip label="UK naive baseline" />
          </div>
        </div>
        <SmallChip label={`+${formatEuroCompact(finalGap, 0)} final gap`} tone="green" />
      </div>

      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="min-w-[760px]" role="img" aria-label="Cumulative PnL for Scarcity Ensemble and UK naive baseline">
          <style>{`
            .pnl-path {
              stroke-dasharray: 1;
              stroke-dashoffset: 1;
              animation: pnlLineDraw 1200ms cubic-bezier(.2,.8,.2,1) forwards;
            }
            .pnl-path-muted {
              animation-delay: 140ms;
            }
            @keyframes pnlLineDraw {
              to { stroke-dashoffset: 0; }
            }
            @media (prefers-reduced-motion: reduce) {
              .pnl-path {
                animation: none;
                stroke-dashoffset: 0;
              }
            }
          `}</style>

          {ticks.map((tick) => {
            const y = pad.top + innerHeight - (tick / yMax) * innerHeight;
            return (
              <g key={tick}>
                <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} stroke="#e7e2d8" strokeDasharray="5 8" />
                <text x={16} y={y + 4} className="fill-stone-400 text-[12px]">
                  {formatAxisEuro(tick)}
                </text>
              </g>
            );
          })}

          <path d={pathFor("baseline_cumulative_pnl_eur")} pathLength="1" fill="none" stroke="#9ca3af" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" className="pnl-path pnl-path-muted" />
          <path d={pathFor("ml_cumulative_pnl_eur")} pathLength="1" fill="none" stroke="#2f9d66" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" className="pnl-path" />

          <line x1={finalMl.x} x2={finalMl.x} y1={finalMl.y} y2={finalBaseline.y} stroke="#d7d0c4" strokeWidth="2" />
          <circle cx={finalMl.x} cy={finalMl.y} r="5.5" fill="#2f9d66" />
          <circle cx={finalBaseline.x} cy={finalBaseline.y} r="5" fill="#9ca3af" />

          <text x={finalMl.x + 14} y={finalMl.y + 4} className="fill-[#202326] text-[14px] font-semibold">
            {formatEuroCompact(finalRow.ml_cumulative_pnl_eur, 3)}
          </text>
          <text x={finalBaseline.x + 14} y={finalBaseline.y + 4} className="fill-stone-500 text-[14px] font-semibold">
            {formatEuroCompact(finalRow.baseline_cumulative_pnl_eur, 3)}
          </text>
          <text x={finalMl.x + 14} y={(finalMl.y + finalBaseline.y) / 2 - 9} className="fill-[#2f9d66] text-[13px] font-semibold">
            +{formatEuroCompact(finalGap, 0)}
          </text>

          <text x={pad.left} y={height - 12} className="fill-stone-500 text-[12px]">
            {formatDateLabel(rows[0].delivery_date)}
          </text>
          <text x={width - pad.right} y={height - 12} textAnchor="end" className="fill-stone-500 text-[12px]">
            {formatDateLabel(finalRow.delivery_date)}
          </text>
        </svg>
      </div>
    </Card>
  );
}

function ComparisonBars({ mlPnl, baselinePnl }) {
  const maxValue = Math.max(asNumber(mlPnl), asNumber(baselinePnl), 1);
  const rows = [
    { label: "Scarcity Ensemble", value: mlPnl, color: "#2f9d66" },
    { label: "UK naive baseline", value: baselinePnl, color: "#b8bbc2" },
  ];

  return (
    <div className="grid gap-4">
      {rows.map((row) => (
        <div key={row.label}>
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="font-semibold text-[#202326]">{row.label}</span>
            <span className="text-stone-500">{formatEuro(row.value)}</span>
          </div>
          <div className="h-7 overflow-hidden rounded-full bg-stone-100">
            <div className="h-full rounded-full" style={{ width: `${(asNumber(row.value) / maxValue) * 100}%`, backgroundColor: row.color }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function EvidenceMetric({ label, value, detail }) {
  return (
    <Card className="p-5">
      <p className="text-sm font-medium text-stone-500">{label}</p>
      <p className="mt-3 text-2xl font-semibold tracking-tight text-[#202326]">{value}</p>
      <p className="mt-2 text-xs text-stone-500">{detail}</p>
    </Card>
  );
}

function DetailsView({ dashboard, schedule, health, batteryParams, loading, onApplyBatteryParams }) {
  const params = dashboard?.asset?.params ?? {};
  const forecasting = dashboard?.forecasting ?? {};
  const registry = forecasting.registry ?? {};

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <BatteryParametersPanel
        batteryParams={batteryParams}
        loading={loading}
        onApply={onApplyBatteryParams}
      />

      <Card className="p-6">
        <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Asset</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <CompactFact label="Power" value={formatPower(params.power_mw)} />
          <CompactFact label="Capacity" value={`${formatNumber(params.capacity_mwh, 0)} MWh`} />
          <CompactFact label="Efficiency" value={formatPercent(asNumber(params.round_trip_efficiency) * 100, 0)} />
          <CompactFact label="SoC band" value={`${formatPercent(health.minBand, 0)}-${formatPercent(health.maxBand, 0)}`} />
        </div>
      </Card>

      <Card className="p-6">
        <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Run</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <CompactFact label="Delivery date" value={formatDateLabel(dashboard?.delivery_date)} />
          <CompactFact label="Market" value={dashboard?.asset?.market ?? "HEnEx Day-Ahead Market"} />
          <CompactFact label="Forecast mode" value={forecasting.available ? "Available" : "Unavailable"} />
          <CompactFact label="Selected model" value={registry.selected_model ?? "Direct optimizer"} />
        </div>
      </Card>

      <Card className="p-6 lg:col-span-2">
        <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Dispatch Summary</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <CompactFact label="Intervals" value={formatNumber(schedule.length, 0)} />
          <CompactFact label="Charge intervals" value={formatNumber(schedule.filter((point) => point.action === "Charge").length, 0)} />
          <CompactFact label="Discharge intervals" value={formatNumber(schedule.filter((point) => point.action === "Discharge").length, 0)} />
        </div>
      </Card>
    </div>
  );
}

function BatteryParametersPanel({ batteryParams, loading, onApply }) {
  const [draft, setDraft] = useState(() => sanitizeBatteryParams(batteryParams));
  const presetName = getPresetName(draft);

  useEffect(() => {
    setDraft(sanitizeBatteryParams(batteryParams));
  }, [batteryParams]);

  function updateField(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function applyParams(nextParams) {
    const normalized = sanitizeBatteryParams(nextParams);
    setDraft(normalized);
    onApply(normalized);
  }

  function submitParams(event) {
    event.preventDefault();
    applyParams(draft);
  }

  const presetButtonClass = (active) =>
    cx(
      "rounded-full border px-3 py-1.5 text-xs font-semibold transition",
      active ? "border-[#202326] bg-[#202326] text-white" : "border-stone-200 bg-white text-stone-600 hover:border-stone-300",
    );

  return (
    <Card className="p-6 lg:col-span-2">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Battery Parameters</h2>
          <p className="mt-2 text-sm text-stone-500">Battery constraints are adjustable inputs; METLEN scale is the demo preset.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => applyParams(LIVE_DEMO_PARAMS)} className={presetButtonClass(presetName === "demo")}>
            Demo: 1.0 cycle/day
          </button>
          <button type="button" onClick={() => applyParams(RESEARCH_PARAMS)} className={presetButtonClass(presetName === "research")}>
            Research: 1.5 cycles/day
          </button>
          <button type="button" className={presetButtonClass(presetName === "custom")} aria-pressed={presetName === "custom"}>
            Custom
          </button>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <SmallChip label={`Live cycle cap: ${formatNumber(asNumber(batteryParams.max_cycles_per_day, DEMO_CYCLE_CAP), 1)}/day`} tone="green" />
        <SmallChip label="Evidence artifacts: research preset 1.5 cycles/day" />
        <SmallChip label="38-day evidence unchanged" />
      </div>

      <form onSubmit={submitParams} className="mt-5 grid gap-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {PARAMETER_FIELDS.map((field) => (
            <label key={field.key} className="grid gap-1.5 text-sm font-medium text-stone-600">
              <span>{field.label}</span>
              <input
                type="number"
                min={field.min}
                max={field.max}
                step={field.step}
                value={draft[field.key]}
                onChange={(event) => updateField(field.key, event.target.value)}
                className="h-10 rounded-lg border border-stone-200 bg-stone-50 px-3 font-semibold text-[#202326] outline-none transition focus:border-[#202326] focus:bg-white"
              />
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs font-medium text-stone-500">Applies to the live daily schedule only.</p>
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-[#202326] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-black disabled:cursor-wait disabled:opacity-60"
          >
            {loading ? "Applying..." : "Apply to live day"}
          </button>
        </div>
      </form>
    </Card>
  );
}

function CompactFact({ label, value }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
      <p className="text-xs font-medium text-stone-500">{label}</p>
      <p className="mt-2 break-words font-semibold text-[#202326]">{value ?? "Unavailable"}</p>
    </div>
  );
}

function SmallChip({ label, tone = "default" }) {
  const tones = {
    default: "border-stone-200 bg-white text-stone-600",
    green: "border-[#cfe5d7] bg-[#f2faf5] text-[#2f9d66]",
    charge: "border-[#cfe5d7] bg-[#f2faf5] text-[#2f9d66]",
    discharge: "border-[#f4c7b8] bg-[#fff0ea] text-[#b64f2f]",
    amber: "border-amber-200 bg-amber-50 text-amber-800",
  };
  return <span className={cx("inline-flex rounded-full border px-3 py-1.5 text-xs font-semibold", tones[tone])}>{label}</span>;
}

export default function App() {
  const [activeTab, setActiveTab] = useState("Live Dispatch");
  const [dashboard, setDashboard] = useState(null);
  const [batteryParams, setBatteryParams] = useState(() => LIVE_DEMO_PARAMS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDashboard(params = batteryParams) {
    setLoading(true);
    setError("");
    try {
      setDashboard(await fetchDashboardData(params));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API failed");
    } finally {
      setLoading(false);
    }
  }

  function applyBatteryParams(nextParams) {
    const normalized = sanitizeBatteryParams(nextParams);
    setBatteryParams(normalized);
    loadDashboard(normalized);
  }

  useEffect(() => {
    loadDashboard(LIVE_DEMO_PARAMS);
  }, []);

  const schedule = useMemo(() => buildSchedule(dashboard), [dashboard]);
  const actionWindows = useMemo(() => buildActionWindows(schedule), [schedule]);
  const health = useMemo(() => getHealth(dashboard, schedule), [dashboard, schedule]);

  return (
    <div className="min-h-screen bg-[#f7f5f0] text-[#202326]">
      <Header activeTab={activeTab} setActiveTab={setActiveTab} dashboard={dashboard} loading={loading} onRefresh={() => loadDashboard(batteryParams)} />

      <main className="mx-auto max-w-7xl px-5 py-8 sm:px-8 lg:py-10">
        <div className="animate-[fadeIn_180ms_ease-out]">
          {activeTab === "Live Dispatch" && (
            <TodayView
              dashboard={dashboard}
              schedule={schedule}
              actionWindows={actionWindows}
              health={health}
              loading={loading}
              error={error}
            />
          )}
          {activeTab === "Evidence" && <EvidenceView dashboard={dashboard} />}
          {activeTab === "Details" && (
            <DetailsView
              dashboard={dashboard}
              schedule={schedule}
              health={health}
              batteryParams={batteryParams}
              loading={loading}
              onApplyBatteryParams={applyBatteryParams}
            />
          )}
        </div>
      </main>
    </div>
  );
}
