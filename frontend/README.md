# Energy Management Dashboard UI

React single-page dashboard built with Vite and Tailwind CSS.

## Run Locally

From the repository root, run both the optimizer API and dashboard:

```bash
python3 run_dashboard.py
```

The runner installs missing Python/frontend dependencies by default. Or start each server manually.

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

## Structure

- `src/App.jsx`: single maintained dashboard UI, including dashboard, optimization, battery health, and configuration views.
- `src/api.js`: dashboard API client.

## Backend Fields Used

The dashboard calls `/api/dashboard` with the demo-date METLEN asset defaults.
The API uses cached public-data artifacts when available so the presentation UI
does not depend on slow public-source calls.

It renders:

- `series[].dam_price_eur_mwh`: published HEnEx DAM MCP when available.
- `series[].charge_mw` / `series[].discharge_mw`: DAM price-taker dispatch.
- `asset.params`: battery settings used by the live daily optimizer.
- `metrics`: daily PnL, degradation cost, equivalent cycles, and dispatch totals.
- `evidence.strategy_comparison`: validated ML-versus-UK-baseline evidence.

If the live API request itself fails, the UI falls back to `/demo-dashboard.json`.
