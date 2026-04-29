import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BatteryCharging,
  CircleDollarSign,
  Database,
  HeartPulse,
  LineChart as LineChartIcon,
  RefreshCw,
  Settings2,
  Zap,
} from "lucide-react";
import { fetchDashboardData, formatEuro, formatNumber } from "./api.js";

const navItems = ["Dashboard", "Optimization", "Battery Health", "Configuration"];

const actionStyles = {
  Charge: { fill: "#2f9d66", label: "Charge" },
  Idle: { fill: "#b8bbc2", label: "Idle" },
  Discharge: { fill: "#df6b45", label: "Discharge" },
};

const scheduleModes = [
  { id: "forecast", label: "Forecast model" },
  { id: "dam", label: "Published DAM" },
];

function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

function asNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatPercent(value, digits = 1) {
  return `${formatNumber(asNumber(value), digits)}%`;
}

function formatPower(value, digits = 0) {
  return `${formatNumber(asNumber(value), digits)} MW`;
}

function formatDateLabel(value) {
  if (!value) return "Delivery day pending";
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

function getEndTime(rows, index) {
  if (rows[index + 1]?.time) return rows[index + 1].time;
  return "24:00";
}

function getSeriesAction(chargeMw, dischargeMw) {
  if (chargeMw > 1e-3) return "Charge";
  if (dischargeMw > 1e-3) return "Discharge";
  return "Idle";
}

function getReason(point, mode) {
  if (point.action === "Charge") {
    return mode === "forecast" ? "Model found a low forecast price interval" : "Published price is attractive for charging";
  }
  if (point.action === "Discharge") {
    return mode === "forecast" ? "Model spread clears the dispatch threshold" : "Published spread covers battery wear";
  }
  return "No spread strong enough to justify cycling";
}

function buildSchedule(dashboard, mode) {
  const rows = dashboard?.series ?? [];
  const useForecast = mode === "forecast" && dashboard?.forecasting?.available;
  const initialSoc = dashboard?.asset?.params?.initial_soc_pct ?? 50;

  return rows
    .map((row, index) => {
      const chargeMw = asNumber(useForecast ? row.forecast_charge_mw : row.charge_mw);
      const dischargeMw = asNumber(useForecast ? row.forecast_discharge_mw : row.discharge_mw);
      const prev = rows[index - 1];
      const socStart = asNumber(
        useForecast ? prev?.forecast_soc_pct ?? prev?.soc_pct : prev?.soc_pct,
        index === 0 ? initialSoc : asNumber(row.soc_pct, initialSoc),
      );
      const socEnd = asNumber(useForecast ? row.forecast_soc_pct ?? row.soc_pct : row.soc_pct, socStart);
      const price = asNumber(
        useForecast ? row.forecast_price_eur_mwh ?? row.dam_price_eur_mwh : row.dam_price_eur_mwh,
      );
      const action = getSeriesAction(chargeMw, dischargeMw);

      return {
        ...row,
        time: row.time,
        endTime: getEndTime(rows, index),
        price,
        damPrice: asNumber(row.dam_price_eur_mwh, price),
        forecastPrice: row.forecast_price_eur_mwh,
        action,
        chargeMw,
        dischargeMw,
        powerAbs: Math.max(Math.abs(chargeMw), Math.abs(dischargeMw)),
        powerLabel: action === "Charge" ? `+${formatPower(chargeMw)}` : action === "Discharge" ? `-${formatPower(dischargeMw)}` : "0 MW",
        netSystemAfterBattery: asNumber(row.net_load_mw) + chargeMw - dischargeMw,
        socStart,
        socEnd,
        reason: getReason({ action }, useForecast ? "forecast" : "dam"),
      };
    })
    .map((point, index, list) => ({
      ...point,
      transition: point.action !== "Idle" && (list[index - 1]?.action !== point.action || list[index + 1]?.action !== point.action),
    }));
}

function buildKpis(dashboard) {
  const metrics = dashboard?.metrics ?? {};
  const forecasting = dashboard?.forecasting;
  const forecastMetrics = forecasting?.metrics ?? {};
  const registry = forecasting?.registry ?? {};
  const hasForecast = Boolean(forecasting?.available);
  const capture = asNumber(forecastMetrics.price_taker_capture_ratio_vs_oracle) * 100;

  return [
    {
      id: "profit",
      label: hasForecast ? "Forecast Dispatch Net" : "Net Revenue",
      value: formatEuro(hasForecast ? forecastMetrics.price_taker_objective_net_revenue_eur : metrics.net_revenue_eur),
      detail: hasForecast
        ? `Realized ${formatEuro(forecastMetrics.price_taker_realized_net_revenue_eur)} against published DAM`
        : `After ${formatEuro(metrics.degradation_cost_eur)} degradation cost`,
      icon: CircleDollarSign,
      featured: true,
    },
    {
      id: "forecast",
      label: hasForecast ? "Model Error" : "Captured Spread",
      value: hasForecast ? `${formatEuro(forecastMetrics.base_forecast_mae_eur_mwh, 2)}/MWh` : `${formatEuro(metrics.captured_spread_eur_mwh, 2)}/MWh`,
      detail: hasForecast
        ? `${registry.selected_model ?? "Selected model"} MAE, ${formatPercent(asNumber(forecastMetrics.base_spread_direction_accuracy) * 100, 1)} spread direction`
        : "Direct DAM optimizer without forecast registry",
      icon: LineChartIcon,
    },
    {
      id: "energy",
      label: "Energy Shifted",
      value: `${formatNumber(metrics.discharged_mwh, 1)} MWh`,
      detail: `${formatNumber(metrics.charged_mwh, 1)} MWh charged, ${formatPower(dashboard?.asset?.params?.power_mw)} asset`,
      icon: BatteryCharging,
    },
    {
      id: "cycles",
      label: hasForecast ? "Capture vs Oracle" : "Equivalent Cycles",
      value: hasForecast ? formatPercent(capture, 1) : formatNumber(metrics.equivalent_cycles, 2),
      detail: hasForecast
        ? `Oracle value ${formatEuro(forecastMetrics.oracle_net_revenue_eur)}`
        : `Limit ${metrics.max_cycles_per_day ?? dashboard?.asset?.params?.max_cycles_per_day ?? "off"} per day`,
      icon: HeartPulse,
    },
  ];
}

function Card({ children, className = "" }) {
  return <section className={cx("rounded-lg border border-stone-200/80 bg-white shadow-soft", className)}>{children}</section>;
}

function Header({ activeTab, setActiveTab, dashboard, loading, onRefresh }) {
  const dataQuality = dashboard?.data_quality ?? "waiting for optimizer";

  return (
    <header className="sticky top-0 z-30 border-b border-stone-200/80 bg-[#f7f5f0]/95 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[#202326] text-white shadow-sm">
            <Zap size={18} strokeWidth={2.4} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-tight text-[#202326]">METLEN Battery Optimizer</p>
            <p className="truncate text-xs text-stone-500">Greek day-ahead electricity market</p>
          </div>
        </div>

        <nav className="hidden md:block">
          <NavPills activeTab={activeTab} setActiveTab={setActiveTab} />
        </nav>

        <div className="flex items-center gap-2">
          <span
            className={cx(
              "hidden rounded-full border px-3 py-1.5 text-xs font-semibold sm:inline-flex",
              dashboard?.metrics?.public_price_data ? "border-[#cfe5d7] bg-[#f2faf5] text-[#2f9d66]" : "border-stone-200 bg-white text-stone-500",
            )}
          >
            {loading ? "Loading" : dataQuality}
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
          <button
            type="button"
            onClick={() => setActiveTab("Configuration")}
            className="grid h-10 w-10 place-items-center rounded-lg border border-stone-200 bg-white text-stone-600 shadow-sm transition hover:text-[#202326] md:hidden"
            aria-label="Configuration"
            title="Configuration"
          >
            <Settings2 size={17} />
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

function ScenarioToggle({ value, onChange, disabledForecast = false }) {
  return (
    <div className="inline-flex rounded-full border border-stone-200 bg-white p-1 text-sm font-semibold text-stone-500 shadow-sm">
      {scheduleModes.map((item) => {
        const disabled = item.id === "forecast" && disabledForecast;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => !disabled && onChange(item.id)}
            disabled={disabled}
            className={cx(
              "rounded-full px-4 py-2 transition-colors disabled:cursor-not-allowed disabled:opacity-45",
              value === item.id ? "bg-[#202326] text-white" : "hover:bg-stone-100 hover:text-[#202326]",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

function KpiCard({ item, active = false, onClick }) {
  const Icon = item.icon;

  return (
    <Card
      className={cx(
        "h-full p-5 transition-all",
        item.featured && "border-[#cfe5d7] bg-[#fffefb] shadow-[0_22px_55px_rgba(47,157,102,0.12)]",
        active && "ring-2 ring-[#365f93]/25",
      )}
    >
      <button type="button" onClick={onClick} className="block h-full w-full text-left">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-stone-500">{item.label}</p>
            <p className={cx("mt-3 break-words font-semibold tracking-tight text-[#202326]", item.featured ? "text-4xl" : "text-3xl")}>
              {item.value}
            </p>
          </div>
          <div className={cx("grid h-10 w-10 shrink-0 place-items-center rounded-lg", item.featured ? "bg-[#eaf6ef] text-[#2f9d66]" : "bg-stone-100 text-[#202326]")}>
            <Icon size={18} />
          </div>
        </div>
        <p className={cx("mt-4 text-sm leading-6", item.featured ? "font-medium text-stone-700" : "text-stone-500")}>{item.detail}</p>
      </button>
    </Card>
  );
}

function LegendItem({ color, label, line = false, dashed = false }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white px-3 py-1.5">
      <span
        className={cx(line ? "h-0.5 w-6" : "h-2.5 w-2.5", "rounded-full")}
        style={{ backgroundColor: color, opacity: dashed ? 0.72 : 1 }}
      />
      {label}
    </span>
  );
}

function FilterChip({ label, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
        active ? "border-[#202326] bg-[#202326] text-white" : "border-stone-200 bg-white text-stone-500 hover:text-[#202326]",
      )}
    >
      {label}
    </button>
  );
}

function DailyOptimizationPlan({ dashboard, schedule, mode, setMode, activeHighlight }) {
  const defaultSlot = useMemo(() => schedule.find((point) => point.action !== "Idle") ?? schedule[0], [schedule]);
  const [selectedTime, setSelectedTime] = useState(null);
  const [filter, setFilter] = useState("All");
  const selectedSlot = schedule.find((point) => point.time === selectedTime) ?? defaultSlot;
  const hasForecast = Boolean(dashboard?.forecasting?.available);
  const width = 1120;
  const height = 366;
  const pad = { top: 30, right: 46, bottom: 58, left: 58 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const allPrices = schedule
    .flatMap((point) => [point.damPrice, point.forecastPrice])
    .map((value) => Number(value))
    .filter(Number.isFinite);
  const minPrice = allPrices.length ? Math.min(...allPrices) - 8 : 0;
  const maxPrice = allPrices.length ? Math.max(...allPrices) + 8 : 100;
  const priceRange = Math.max(1, maxPrice - minPrice);
  const slotWidth = schedule.length ? innerWidth / schedule.length : innerWidth;
  const maxPower = Math.max(asNumber(dashboard?.asset?.params?.power_mw, 1), ...schedule.map((point) => point.powerAbs), 1);
  const highPriceThreshold = allPrices.length ? minPrice + priceRange * 0.74 : 0;

  useEffect(() => {
    setSelectedTime(defaultSlot?.time ?? null);
  }, [defaultSlot?.time]);

  function yForPrice(value) {
    return pad.top + innerHeight - ((asNumber(value, minPrice) - minPrice) / priceRange) * innerHeight;
  }

  function lineFor(key) {
    return schedule
      .map((point, index) => {
        const value = point[key];
        if (!Number.isFinite(Number(value))) return null;
        const x = pad.left + index * slotWidth + slotWidth / 2;
        return `${x.toFixed(1)},${yForPrice(value).toFixed(1)}`;
      })
      .filter(Boolean)
      .join(" ");
  }

  function isHighlighted(point) {
    if (activeHighlight === "profit") return point.action === "Discharge" && point.price >= highPriceThreshold;
    if (activeHighlight === "forecast") return hasForecast && point.action !== "Idle";
    if (activeHighlight === "energy") return point.action !== "Idle";
    if (activeHighlight === "cycles") return point.transition;
    return false;
  }

  function getOpacity(point) {
    const filterMatch = filter === "All" || point.action === filter;
    const highlightOn = Boolean(activeHighlight);
    if (!filterMatch) return 0.16;
    if (highlightOn && !isHighlighted(point)) return 0.24;
    return point.action === "Idle" ? 0.42 : 0.92;
  }

  if (!schedule.length) {
    return (
      <Card className="flex min-h-[360px] items-center justify-center p-8">
        <div className="text-center">
          <p className="text-xl font-semibold text-[#202326]">Waiting for optimizer output</p>
          <p className="mt-2 text-sm text-stone-500">The dashboard will render once `/api/dashboard` returns series data.</p>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-5 sm:p-7">
      <div className="mb-7 flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-[#202326]">Daily Optimization Plan</h2>
          <p className="mt-2 text-sm font-semibold text-[#2f9d66]">Battery action every 15 minutes</p>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-stone-500">
            Dispatch bars use the selected optimizer mode; price lines show the published DAM and model forecast when available.
          </p>
        </div>
        <div className="flex flex-col items-start gap-3 lg:items-end">
          <ScenarioToggle value={mode} onChange={setMode} disabledForecast={!hasForecast} />
          <div className="flex flex-wrap justify-start gap-2 text-xs font-semibold text-stone-500 lg:justify-end">
            <LegendItem color={actionStyles.Charge.fill} label="Charge" />
            <LegendItem color={actionStyles.Idle.fill} label="Idle" />
            <LegendItem color={actionStyles.Discharge.fill} label="Discharge" />
            <LegendItem color="#365f93" label="DAM price" line />
            {hasForecast && <LegendItem color="#7c6fbd" label="Forecast price" line dashed />}
          </div>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {["All", "Charge", "Discharge", "Idle"].map((item) => (
          <FilterChip key={item} label={item} active={filter === item} onClick={() => setFilter(item)} />
        ))}
      </div>

      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="min-w-[900px]" role="img" aria-label="15-minute battery dispatch and price chart">
          {[minPrice, minPrice + priceRange / 2, maxPrice].map((tick) => {
            const y = yForPrice(tick);
            return (
              <g key={tick}>
                <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} stroke="#e7e2d8" strokeDasharray="5 8" />
                <text x={18} y={y + 4} className="fill-stone-400 text-[12px]">
                  {formatNumber(tick, 0)}
                </text>
              </g>
            );
          })}

          {schedule.map((point, index) => {
            const x = pad.left + index * slotWidth + 0.8;
            const style = actionStyles[point.action];
            const barHeight = point.action === "Idle" ? 22 : 34 + (point.powerAbs / maxPower) * 116;
            const y = pad.top + innerHeight - barHeight;
            const highlighted = isHighlighted(point);

            return (
              <rect
                key={`${point.time}-${mode}`}
                x={x}
                y={y}
                width={Math.max(4, slotWidth - 2)}
                height={barHeight}
                rx="3"
                fill={style.fill}
                opacity={getOpacity(point)}
                stroke={highlighted ? "#202326" : "transparent"}
                strokeWidth={highlighted ? 2 : 0}
                className="cursor-pointer transition-opacity"
                onMouseEnter={() => setSelectedTime(point.time)}
                onClick={() => setSelectedTime(point.time)}
              />
            );
          })}

          <polyline points={lineFor("damPrice")} fill="none" stroke="#365f93" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          {hasForecast && (
            <polyline
              points={lineFor("forecastPrice")}
              fill="none"
              stroke="#7c6fbd"
              strokeWidth="3"
              strokeDasharray="7 8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {[0, 12, 24, 36, 48, 60, 72, 84, Math.max(0, schedule.length - 1)].map((index) => {
            const point = schedule[index];
            if (!point) return null;
            return (
              <text key={`${point.time}-${index}`} x={pad.left + index * slotWidth} y={height - 24} textAnchor="middle" className="fill-stone-500 text-[12px]">
                {point.time}
              </text>
            );
          })}
        </svg>
      </div>

      {selectedSlot && (
        <div className="mt-5 rounded-lg border border-stone-200 bg-stone-50 p-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Selected interval</p>
              <p className="mt-1 text-lg font-semibold tracking-tight text-[#202326]">
                {selectedSlot.time}-{selectedSlot.endTime} / {selectedSlot.action}
              </p>
            </div>
            <div className="grid gap-3 text-sm sm:grid-cols-3 lg:min-w-[760px] lg:grid-cols-6">
              <DetailStat label={mode === "forecast" ? "Forecast price" : "DAM price"} value={`${formatEuro(selectedSlot.price, 2)}/MWh`} />
              <DetailStat label="Power" value={selectedSlot.powerLabel} />
              <DetailStat label="State of charge" value={`${formatPercent(selectedSlot.socStart, 1)} to ${formatPercent(selectedSlot.socEnd, 1)}`} />
              <DetailStat label="Net system" value={formatPower(selectedSlot.netSystemAfterBattery)} />
              <DetailStat
                label={mode === "forecast" ? "Published DAM" : "Interval value"}
                value={mode === "forecast" ? `${formatEuro(selectedSlot.damPrice, 2)}/MWh` : formatEuro(selectedSlot.net_revenue_eur, 2)}
              />
              <DetailStat label="Reason" value={selectedSlot.reason} />
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function DetailStat({ label, value }) {
  return (
    <div>
      <p className="text-xs font-medium text-stone-500">{label}</p>
      <p className="mt-1 break-words font-semibold text-[#202326]">{value}</p>
    </div>
  );
}

function SmoothLineChart({ points, stroke = "#2f9d66", fill = "#eaf6ef" }) {
  const width = 620;
  const height = 254;
  const pad = { top: 20, right: 26, bottom: 42, left: 44 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const safePoints = points.length ? points : [{ label: "00:00", value: 0 }];
  const coords = safePoints.map((point, index) => ({
    ...point,
    x: pad.left + (safePoints.length === 1 ? 0 : (index / (safePoints.length - 1)) * innerWidth),
    y: pad.top + innerHeight - (asNumber(point.value) / 100) * innerHeight,
  }));
  const line = coords.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const area = `${pad.left},${pad.top + innerHeight} ${line} ${pad.left + innerWidth},${pad.top + innerHeight}`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="State of charge line chart">
      {[25, 50, 75, 100].map((tick) => {
        const y = pad.top + innerHeight - (tick / 100) * innerHeight;
        return (
          <g key={tick}>
            <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} stroke="#e7e2d8" strokeDasharray="5 8" />
            <text x={8} y={y + 4} className="fill-stone-400 text-[11px]">
              {tick}%
            </text>
          </g>
        );
      })}
      <polygon points={area} fill={fill} />
      <polyline points={line} fill="none" stroke={stroke} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      {coords.filter((_, index) => index % 12 === 0 || index === coords.length - 1).map((point) => (
        <text key={`${point.label}-${point.x}`} x={point.x} y={height - 14} textAnchor="middle" className="fill-stone-500 text-[11px]">
          {point.label}
        </text>
      ))}
    </svg>
  );
}

function StateOfChargeCard({ schedule }) {
  const points = schedule.map((point) => ({ label: point.time, value: point.socEnd }));

  return (
    <Card className="p-6">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[#202326]">State of Charge Forecast</h2>
          <p className="mt-1 text-sm leading-6 text-stone-500">Expected battery state of charge across the operating day.</p>
        </div>
        <span className="rounded-full border border-stone-200 bg-stone-50 px-3 py-1.5 text-xs font-semibold text-stone-500">SoC %</span>
      </div>
      <SmoothLineChart points={points} />
    </Card>
  );
}

function BatteryLifetimeImpact({ dashboard }) {
  const metrics = dashboard?.metrics ?? {};
  const params = dashboard?.asset?.params ?? {};
  const forecasting = dashboard?.forecasting;
  const modelStatus = forecasting?.available ? `${forecasting.registry?.selected_model ?? "model"} forecast active` : "DAM optimizer only";

  return (
    <Card className="p-6">
      <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Battery Lifetime Impact</h2>
          <p className="mt-1 text-sm leading-6 text-stone-500">The schedule weighs revenue against degradation and cycle limits.</p>
        </div>
        <div className="inline-flex rounded-full bg-[#eaf6ef] px-3 py-1.5 text-xs font-semibold text-[#2f9d66]">{modelStatus}</div>
      </div>

      <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
        <p className="text-xs font-medium text-stone-500">Optimization status</p>
        <p className="mt-2 text-lg font-semibold tracking-tight text-[#202326]">{dashboard?.optimizer_status ?? "Pending"}</p>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
          <p className="text-xs font-medium text-stone-500">Daily cycle target</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-[#202326]">{params.max_cycles_per_day ?? "Off"}</p>
        </div>
        <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
          <p className="text-xs font-medium text-stone-500">Used today</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-[#202326]">{formatNumber(metrics.equivalent_cycles, 2)}</p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 rounded-lg border border-stone-200 bg-white p-3 text-sm">
        <ConstraintItem label="Capacity" value={`${formatNumber(params.capacity_mwh, 0)} MWh`} />
        <ConstraintItem label="Max power" value={formatPower(params.power_mw)} />
        <ConstraintItem label="Efficiency" value={formatPercent(asNumber(params.round_trip_efficiency) * 100, 0)} />
        <ConstraintItem label="Degradation" value={`${formatEuro(params.degradation_cost_eur_mwh, 2)}/MWh`} />
      </div>

      <div className="mt-5 rounded-lg border border-stone-200 bg-[#fbfaf7] p-4">
        <p className="text-sm font-semibold text-[#202326]">Degradation cost included</p>
        <p className="mt-1 text-sm leading-6 text-stone-500">
          The current run includes {formatEuro(metrics.degradation_cost_eur)} in wear cost before reporting net revenue.
        </p>
      </div>
    </Card>
  );
}

function ConstraintItem({ label, value }) {
  return (
    <div className="rounded-lg bg-stone-50 px-3 py-2">
      <p className="text-xs text-stone-500">{label}</p>
      <p className="mt-1 break-words font-semibold text-[#202326]">{value}</p>
    </div>
  );
}

function ModelEvidenceCard({ dashboard }) {
  const forecasting = dashboard?.forecasting;
  const registry = forecasting?.registry ?? {};
  const metrics = forecasting?.metrics ?? {};
  const rows = forecasting?.model_performance ?? [];

  return (
    <Card className="p-6">
      <div className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Forecast Model Evidence</h2>
          <p className="mt-1 text-sm leading-6 text-stone-500">
            Live-safe forecast registry, validation metrics, and the selected model used by the forecast dispatch.
          </p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-stone-200 bg-stone-50 px-3 py-1.5 text-xs font-semibold text-stone-600">
          <Database size={14} />
          {registry.selected_model ?? "No model selected"}
        </span>
      </div>

      {!forecasting?.available ? (
        <p className="rounded-lg border border-stone-200 bg-stone-50 p-4 text-sm text-stone-600">
          Forecasting is unavailable for this payload. The UI is showing the direct published-DAM optimizer output.
        </p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MiniStat label="MAE" value={`${formatEuro(metrics.base_forecast_mae_eur_mwh, 2)}/MWh`} />
            <MiniStat label="RMSE" value={`${formatEuro(metrics.base_forecast_rmse_eur_mwh, 2)}/MWh`} />
            <MiniStat label="Top quartile" value={formatPercent(asNumber(metrics.base_top_quartile_accuracy) * 100, 1)} />
            <MiniStat label="Training rows" value={formatNumber(registry.training_rows, 0)} />
          </div>
          <div className="mt-5 overflow-x-auto">
            <table className="min-w-[680px] w-full border-separate border-spacing-0 text-left text-sm">
              <thead className="text-xs uppercase tracking-[0.14em] text-stone-500">
                <tr>
                  <th className="border-b border-stone-200 pb-3 font-semibold">Model</th>
                  <th className="border-b border-stone-200 pb-3 font-semibold">MAE</th>
                  <th className="border-b border-stone-200 pb-3 font-semibold">RMSE</th>
                  <th className="border-b border-stone-200 pb-3 font-semibold">Spread Direction</th>
                  <th className="border-b border-stone-200 pb-3 font-semibold">Bottom Quartile</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 4).map((row) => (
                  <tr key={row.model} className={row.model === registry.selected_model ? "text-[#202326]" : "text-stone-500"}>
                    <td className="border-b border-stone-100 py-3 font-semibold">{row.model}</td>
                    <td className="border-b border-stone-100 py-3">{formatEuro(row.mae_eur_mwh, 2)}</td>
                    <td className="border-b border-stone-100 py-3">{formatEuro(row.rmse_eur_mwh, 2)}</td>
                    <td className="border-b border-stone-100 py-3">{formatPercent(asNumber(row.spread_direction_accuracy) * 100, 1)}</td>
                    <td className="border-b border-stone-100 py-3">{formatPercent(asNumber(row.bottom_quartile_accuracy) * 100, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}

function MiniStat({ label, value }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
      <p className="text-xs font-medium text-stone-500">{label}</p>
      <p className="mt-2 break-words text-lg font-semibold tracking-tight text-[#202326]">{value}</p>
    </div>
  );
}

function PageIntro({ eyebrow, title, subtitle, action }) {
  return (
    <section className="mb-8 flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
      <div>
        <p className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-stone-500">{eyebrow}</p>
        <h1 className="max-w-4xl text-4xl font-semibold tracking-tight text-[#202326] sm:text-5xl">{title}</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-stone-500">{subtitle}</p>
      </div>
      {action}
    </section>
  );
}

function StatusBanner({ dashboard, loading, error }) {
  const forecasting = dashboard?.forecasting;
  const metrics = dashboard?.metrics ?? {};
  const forecastMetrics = forecasting?.metrics ?? {};
  const deliveryDate = formatDateLabel(dashboard?.delivery_date);
  const netValue = forecasting?.available
    ? forecastMetrics.price_taker_objective_net_revenue_eur
    : metrics.net_revenue_eur;

  return (
    <section className="mb-8 flex flex-col gap-3">
      <div className="inline-flex max-w-full flex-wrap items-center gap-3 rounded-lg border border-[#dfeee5] bg-[#f2faf5] px-4 py-3 text-sm shadow-sm">
        <span className="font-semibold text-[#2f9d66]">
          {loading ? "Refreshing optimizer payload" : "Recommended schedule generated"}
        </span>
        <span className="hidden h-4 w-px bg-[#cfe5d7] sm:block" />
        <span className="text-stone-600">
          {deliveryDate} / expected net value {formatEuro(netValue)}
        </span>
      </div>
      {(error || dashboard?.warnings?.length > 0) && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {error || dashboard.warnings.slice(0, 2).join(" ")}
        </div>
      )}
    </section>
  );
}

function DashboardView({ dashboard, schedule, scheduleMode, setScheduleMode, kpis, activeHighlight, setActiveHighlight, loading, error }) {
  return (
    <>
      <PageIntro
        eyebrow="Day-ahead battery schedule"
        title="Battery Optimization Dashboard"
        subtitle="15-minute operating plan backed by public HEnEx/IPTO data, the optimizer, and the forecast registry."
      />
      <StatusBanner dashboard={dashboard} loading={loading} error={error} />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {kpis.map((item) => (
          <KpiCard
            key={item.id}
            item={item}
            active={activeHighlight === item.id}
            onClick={() => setActiveHighlight(activeHighlight === item.id ? null : item.id)}
          />
        ))}
      </section>

      <div className="mt-5">
        <DailyOptimizationPlan
          dashboard={dashboard}
          schedule={schedule}
          mode={scheduleMode}
          setMode={setScheduleMode}
          activeHighlight={activeHighlight}
        />
      </div>

      <section className="mt-5 grid gap-5 lg:grid-cols-[1.12fr_0.88fr]">
        <StateOfChargeCard schedule={schedule} />
        <BatteryLifetimeImpact dashboard={dashboard} />
      </section>

      <div className="mt-5">
        <ModelEvidenceCard dashboard={dashboard} />
      </div>
    </>
  );
}

function OptimizationView({ dashboard, schedule, scheduleMode, setScheduleMode }) {
  const metrics = dashboard?.metrics ?? {};
  const forecasting = dashboard?.forecasting;
  const forecastMetrics = forecasting?.metrics ?? {};
  const netValue = forecasting?.available && scheduleMode === "forecast" ? forecastMetrics.price_taker_objective_net_revenue_eur : metrics.net_revenue_eur;

  return (
    <>
      <PageIntro
        title="Optimization Schedule"
        subtitle="Inspect charge, discharge, and idle decisions for the selected optimizer mode."
        eyebrow="Optimization"
        action={<ScenarioToggle value={scheduleMode} onChange={setScheduleMode} disabledForecast={!forecasting?.available} />}
      />
      <div className="mb-5 grid gap-3 md:grid-cols-4">
        <CompactMetric label="Net value" value={formatEuro(netValue)} />
        <CompactMetric label="Captured spread" value={`${formatEuro(metrics.captured_spread_eur_mwh, 2)}/MWh`} />
        <CompactMetric label="Charge intervals" value={formatNumber(metrics.charge_intervals, 0)} />
        <CompactMetric label="Discharge intervals" value={formatNumber(metrics.discharge_intervals, 0)} />
      </div>
      <DailyOptimizationPlan dashboard={dashboard} schedule={schedule} mode={scheduleMode} setMode={setScheduleMode} activeHighlight={null} />
    </>
  );
}

function CompactMetric({ label, value }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium text-stone-500">{label}</p>
      <p className="mt-2 break-words text-base font-semibold tracking-tight text-[#202326]">{value}</p>
    </Card>
  );
}

function BatteryHealthView({ dashboard, schedule }) {
  const metrics = dashboard?.metrics ?? {};
  const params = dashboard?.asset?.params ?? {};

  return (
    <>
      <PageIntro
        title="Battery Health"
        subtitle="Schedule quality measured against degradation cost, state of charge, and daily cycle limits."
        eyebrow="Battery health"
      />
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <HealthMetric label="Cycle limit" value={params.max_cycles_per_day ?? "Off"} />
        <HealthMetric label="Used today" value={formatNumber(metrics.equivalent_cycles, 2)} />
        <HealthMetric label="Wear cost included" value={formatEuro(metrics.degradation_cost_eur)} />
        <HealthMetric label="Usable energy" value={`${formatNumber(dashboard?.asset?.usable_energy_mwh, 0)} MWh`} />
      </section>
      <section className="mt-5 grid gap-5 lg:grid-cols-[1.12fr_0.88fr]">
        <StateOfChargeCard schedule={schedule} />
        <BatteryLifetimeImpact dashboard={dashboard} />
      </section>
    </>
  );
}

function HealthMetric({ label, value }) {
  return (
    <Card className="p-5">
      <p className="text-sm font-medium text-stone-500">{label}</p>
      <p className="mt-3 break-words text-3xl font-semibold tracking-tight text-[#202326]">{value}</p>
    </Card>
  );
}

function ConfigurationView({ dashboard }) {
  const asset = dashboard?.asset ?? {};
  const params = asset.params ?? {};
  const forecasting = dashboard?.forecasting;
  const registry = forecasting?.registry ?? {};
  const sourceEntries = Object.entries(dashboard?.sources ?? {});
  const config = [
    ["Battery capacity", `${formatNumber(params.capacity_mwh, 0)} MWh`],
    ["Max charge/discharge power", formatPower(params.power_mw)],
    ["Round-trip efficiency", formatPercent(asNumber(params.round_trip_efficiency) * 100, 0)],
    ["Daily cycle target", params.max_cycles_per_day ?? "Off"],
    ["Market", asset.market ?? "HEnEx Day-Ahead Market"],
    ["Time interval", "15 minutes"],
    ["Delivery day", formatDateLabel(dashboard?.delivery_date)],
    ["Timezone", "Europe/Athens"],
  ];

  return (
    <>
      <PageIntro
        title="Configuration"
        subtitle="Battery, market, and model assumptions used by the optimizer payload currently rendered in the UI."
        eyebrow="Assumptions"
      />
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {config.map(([label, value]) => (
          <Card key={label} className="p-5">
            <p className="text-sm font-medium text-stone-500">{label}</p>
            <p className="mt-3 break-words text-2xl font-semibold tracking-tight text-[#202326]">{value}</p>
          </Card>
        ))}
      </section>

      <section className="mt-5 grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <Card className="p-6">
          <div className="mb-5 flex items-center gap-3">
            <Activity className="text-[#2f9d66]" size={20} />
            <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Forecast Registry</h2>
          </div>
          <div className="grid gap-3 text-sm">
            <DetailStat label="Selected model" value={registry.selected_model ?? "Unavailable"} />
            <DetailStat label="Training window" value={registry.training_start ? `${registry.training_start} to ${registry.training_end}` : "Unavailable"} />
            <DetailStat label="Validation window" value={registry.validation_start ? `${registry.validation_start} to ${registry.validation_end}` : "Unavailable"} />
            <DetailStat label="Leakage audit" value={registry.leakage_audit?.live_safe ? "Live-safe features only" : "Unavailable"} />
          </div>
        </Card>

        <Card className="p-6">
          <div className="mb-5 flex items-center gap-3">
            <Database className="text-[#365f93]" size={20} />
            <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Public Data Sources</h2>
          </div>
          <div className="grid gap-3">
            {sourceEntries.length ? (
              sourceEntries.map(([label, value]) => (
                <div key={label} className="rounded-lg border border-stone-200 bg-stone-50 p-3">
                  <p className="text-sm font-semibold text-[#202326]">{label}</p>
                  <p className="mt-1 break-all text-xs leading-5 text-stone-500">{String(value)}</p>
                </div>
              ))
            ) : (
              <p className="rounded-lg border border-stone-200 bg-stone-50 p-4 text-sm text-stone-600">No source metadata is available yet.</p>
            )}
          </div>
        </Card>
      </section>

      {registry.feature_columns?.length > 0 && (
        <Card className="mt-5 p-6">
          <h2 className="text-lg font-semibold tracking-tight text-[#202326]">Live-Safe Feature Columns</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            {registry.feature_columns.map((feature) => (
              <span key={feature} className="rounded-full border border-stone-200 bg-stone-50 px-3 py-1.5 text-xs font-semibold text-stone-600">
                {feature}
              </span>
            ))}
          </div>
        </Card>
      )}
    </>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState("Dashboard");
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [scheduleMode, setScheduleMode] = useState("forecast");
  const [activeHighlight, setActiveHighlight] = useState(null);

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchDashboardData();
      setDashboard(payload);
      if (!payload?.forecasting?.available) {
        setScheduleMode("dam");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard API failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  const schedule = useMemo(() => buildSchedule(dashboard, scheduleMode), [dashboard, scheduleMode]);
  const kpis = useMemo(() => buildKpis(dashboard), [dashboard]);

  return (
    <div className="min-h-screen bg-[#f7f5f0] text-[#202326]">
      <Header activeTab={activeTab} setActiveTab={setActiveTab} dashboard={dashboard} loading={loading} onRefresh={loadDashboard} />

      <main className="mx-auto max-w-7xl px-5 py-8 sm:px-8 lg:py-10">
        <div className="animate-[fadeIn_180ms_ease-out]">
          {activeTab === "Dashboard" && (
            <DashboardView
              dashboard={dashboard}
              schedule={schedule}
              scheduleMode={scheduleMode}
              setScheduleMode={setScheduleMode}
              kpis={kpis}
              activeHighlight={activeHighlight}
              setActiveHighlight={setActiveHighlight}
              loading={loading}
              error={error}
            />
          )}
          {activeTab === "Optimization" && (
            <OptimizationView dashboard={dashboard} schedule={schedule} scheduleMode={scheduleMode} setScheduleMode={setScheduleMode} />
          )}
          {activeTab === "Battery Health" && <BatteryHealthView dashboard={dashboard} schedule={schedule} />}
          {activeTab === "Configuration" && <ConfigurationView dashboard={dashboard} />}
        </div>
      </main>
    </div>
  );
}
