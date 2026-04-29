const API_BASE =
  import.meta.env.VITE_API_BASE ??
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : window.location.origin);

const DEMO_PAYLOAD_URL = "/demo-dashboard.json";
const LIVE_API_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 60000);

export async function fetchDashboardData(params = {}) {
  try {
    return await fetchLiveDashboard(params);
  } catch (error) {
    return fetchStaticDemoPayload(error);
  }
}

async function fetchLiveDashboard(params = {}) {
  const url = new URL("/api/dashboard", API_BASE);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), LIVE_API_TIMEOUT_MS);
  const query = {
    date: "2026-04-22",
    power_mw: 330,
    capacity_mwh: 790,
    round_trip_efficiency: 0.85,
    degradation_cost_eur_mwh: 4,
    max_cycles_per_day: 1.5,
    forecast_history_days: 8,
    validation_days: 1,
    ...params,
  };

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

async function fetchStaticDemoPayload(cause) {
  const response = await fetch(DEMO_PAYLOAD_URL, { cache: "no-store" });
  if (!response.ok) {
    throw cause instanceof Error ? cause : new Error("Dashboard API and demo payload unavailable");
  }
  const payload = await response.json();
  return {
    ...payload,
    deployment_mode: "static-demo-fallback",
    warnings: [
      ...(payload.warnings ?? []),
      "Using committed Vercel demo payload because the live optimizer API is unavailable.",
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
