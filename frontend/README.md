# Energy Management Dashboard UI

React single-page dashboard built with Vite, Tailwind CSS, and Recharts.

## Run Locally

From the repository root, run both the optimizer API and dashboard:

```bash
python3 run_dashboard.py
```

Or start each server manually.

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

- `src/App.jsx`: single maintained dashboard UI, including dashboard, optimization, battery health, and configuration views.
- `src/api.js`: dashboard API client.

## Backend Fields Used

The dashboard calls `/api/dashboard` with the demo-date METLEN asset defaults plus a light
`forecast_history_days=8` and `validation_days=1` refresh. Use the backend defaults or
`scripts/train_forecast_registry.py` for the fuller 21-day production-style run.

It renders:

- `series[].dam_price_eur_mwh`: published HEnEx DAM MCP when available.
- `series[].forecast_price_eur_mwh`: selected model base forecast.
- `series[].charge_mw` / `series[].discharge_mw`: DAM price-taker dispatch.
- `series[].forecast_charge_mw` / `series[].forecast_discharge_mw`: forecast-driven price-taker dispatch.
- `series[].forecast_soc_pct`: forecast-driven state of charge.
- `forecasting.registry`: selected model, feature columns, training window, and leakage audit.
- `forecasting.metrics`: MAE/RMSE, quartile capture, forecast dispatch value, realized backtest value, and capture versus oracle.

If `forecasting.available` is false, the UI stays usable and falls back to the direct DAM optimizer payload.
If the live API request itself fails, the UI falls back to `/demo-dashboard.json`.
