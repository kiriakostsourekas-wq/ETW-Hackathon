# Energy Management Dashboard UI

React single-page dashboard built with Vite, Tailwind CSS, and Recharts.

## Run Locally

Start the Python API from the repository root:

```bash
PYTHONPATH=src python3 -m batteryhack.api_server --port 8000
```

Then start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Default dev URL:

```text
http://127.0.0.1:5173/
```

## Build

```bash
cd frontend
npm run build
```

## Vercel

The repo-level `vercel.json` builds this folder and serves `dist/`.

When no live API is configured, Vercel serves `public/demo-dashboard.json` through `/api/dashboard`
so the deployed dashboard remains functional. To use a hosted optimizer API instead, set:

```text
VITE_API_BASE=https://your-api-host.example
```

## Structure

- `src/App.jsx`: fixed viewport dashboard layout.
- `src/api.js`: dashboard API client.
- `src/components/TopNav.jsx`: top navigation bar.
- `src/components/HeroStatus.jsx`: site greeting, animated power flow, and asset summary.
- `src/components/KPIStrip.jsx`: API-backed KPI cards with sparklines.
- `src/components/OperationsPanel.jsx`: API-backed public market and dispatch chart.
- `src/components/ReportsPanel.jsx`: lightweight report view backed by the same optimizer payload.

## Backend Fields Used

The dashboard calls `/api/dashboard` with the demo-date METLEN asset defaults plus a light
`forecast_history_days=8` and `validation_days=1` refresh. Use the backend defaults or
`scripts/train_forecast_registry.py` for the fuller 21-day production-style run.

It renders:

- `series[].dam_price_eur_mwh`: published HEnEx DAM MCP when available.
- `series[].forecast_price_eur_mwh`: selected model base forecast.
- `series[].storage_adjusted_forecast_eur_mwh`: storage-feedback scenario forecast.
- `series[].charge_mw` / `series[].discharge_mw`: DAM price-taker dispatch.
- `series[].storage_charge_mw` / `series[].storage_discharge_mw`: storage-aware dispatch.
- `forecasting.registry`: selected model, feature columns, training window, and leakage audit.
- `forecasting.metrics`: MAE/RMSE, capture metrics, price-taker value, storage-aware value, and spread compression.

If `forecasting.available` is false, the UI stays usable and falls back to the direct DAM optimizer payload.
If the live API request itself fails, the UI falls back to `/demo-dashboard.json`.
