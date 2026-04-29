const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export async function fetchDashboardData(params = {}) {
  const url = new URL("/api/dashboard", API_BASE);
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

  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error ?? `API request failed with ${response.status}`);
  }
  return payload;
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
