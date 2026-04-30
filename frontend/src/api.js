const API_BASE =
  import.meta.env.VITE_API_BASE ??
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : window.location.origin);

const DEMO_PAYLOAD_URL = "/demo-dashboard.json";
const LIVE_API_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 120000);
const BATTERY_PARAM_KEYS = [
  "power_mw",
  "capacity_mwh",
  "round_trip_efficiency",
  "min_soc_pct",
  "max_soc_pct",
  "initial_soc_pct",
  "terminal_soc_pct",
  "degradation_cost_eur_mwh",
  "max_cycles_per_day",
];

const DEFAULT_DASHBOARD_QUERY = {
  date: "2026-04-22",
  power_mw: 330,
  capacity_mwh: 790,
  round_trip_efficiency: 0.85,
  min_soc_pct: 10,
  max_soc_pct: 90,
  initial_soc_pct: 50,
  terminal_soc_pct: 50,
  degradation_cost_eur_mwh: 4,
  max_cycles_per_day: 1.0,
  include_forecast: true,
  forecast_history_days: 8,
  validation_days: 1,
};

export async function fetchDashboardData(params = {}) {
  const query = { ...DEFAULT_DASHBOARD_QUERY, ...params };
  const wantsForecast = query.include_forecast === true || query.include_forecast === "true";
  try {
    if (wantsForecast) {
      const livePayload = await fetchLiveDashboard({ ...query, include_forecast: false });
      const demoPayload = await fetchStaticDemoPayload(null, query);
      return mergeCachedForecastPayload(livePayload, demoPayload);
    }
    return await fetchLiveDashboard(query);
  } catch (error) {
    return fetchStaticDemoPayload(error, query);
  }
}

function mergeCachedForecastPayload(livePayload, demoPayload) {
  const forecastRows = new Map((demoPayload.series ?? []).map((row) => [row.timestamp, row]));
  const series = (livePayload.series ?? []).map((row) => {
    const forecast = forecastRows.get(row.timestamp);
    if (!forecast) {
      return row;
    }
    return {
      ...row,
      forecast_price_eur_mwh: forecast.forecast_price_eur_mwh,
      forecast_low_eur_mwh: forecast.forecast_low_eur_mwh,
      forecast_high_eur_mwh: forecast.forecast_high_eur_mwh,
      forecast_charge_mw: forecast.forecast_charge_mw,
      forecast_discharge_mw: forecast.forecast_discharge_mw,
      forecast_soc_pct: forecast.forecast_soc_pct,
    };
  });

  return {
    ...livePayload,
    forecasting: demoPayload.forecasting,
    kpis: demoPayload.kpis ?? livePayload.kpis,
    windows: demoPayload.windows ?? livePayload.windows,
    series,
  };
}

async function fetchLiveDashboard(query = {}) {
  const url = new URL("/api/dashboard", API_BASE);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), LIVE_API_TIMEOUT_MS);

  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });

  try {
    const response = await fetch(url, { signal: controller.signal });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error ?? `API request failed with ${response.status}`);
    }
    return payload;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Dashboard API timed out after ${LIVE_API_TIMEOUT_MS}ms`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function fetchStaticDemoPayload(cause, query = DEFAULT_DASHBOARD_QUERY) {
  const response = await fetch(DEMO_PAYLOAD_URL, { cache: "no-store" });
  if (!response.ok) {
    throw cause instanceof Error ? cause : new Error("Dashboard API and demo payload unavailable");
  }
  const payload = await response.json();
  const batteryParams = Object.fromEntries(
    BATTERY_PARAM_KEYS.map((key) => [key, query[key] ?? payload.asset?.params?.[key]]),
  );
  return {
    ...payload,
    asset: {
      ...(payload.asset ?? {}),
      params: {
        ...(payload.asset?.params ?? {}),
        ...batteryParams,
      },
    },
    deployment_mode: "static-demo-fallback",
    warnings: [
      ...(payload.warnings ?? []),
      "Using committed demo payload because the live optimizer API is unavailable.",
    ],
  };
}

export function formatEuro(value, digits = 0) {
  const number = Number(value ?? 0);
  return `EUR ${number.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })}`;
}

export function formatNumber(value, digits = 0) {
  const number = Number(value ?? 0);
  return number.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}
