# Greek Battery Optimization Hackathon

This project implements a presentation-ready prototype for constraint-aware battery scheduling in the Greek Day-Ahead Market. It combines public HEnEx DAM prices, IPTO load/RES forecasts, Open-Meteo weather, a live-safe forecast pipeline, a MILP battery optimizer, and an offline HEnEx curve experiment for testing whether one METLEN-scale BESS can be treated as price-taker.

## Quick Start

```bash
python3 -m pip install -r requirements.txt
streamlit run app.py
```

The default demo date is `2026-04-22`, which has public HEnEx/IPTO files available. If a source is unavailable, the app fills missing columns with deterministic synthetic data so the live demo remains stable.

## React Dashboard

The React dashboard is under `frontend/` and reads live JSON from the Python optimizer API.

Terminal 1:

```bash
PYTHONPATH=src python3 -m batteryhack.api_server --port 8000
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

Open `http://127.0.0.1:5173/`. The default dashboard request uses the public-data demo day `2026-04-22`, a METLEN-scale `330 MW / 790 MWh` battery, 85% round-trip efficiency, a 1.5 equivalent-cycle daily budget, and a light 8-day forecast refresh for faster first load.

Useful API query controls:

- `include_forecast=false` skips model training and returns the fast DAM optimizer payload.
- `forecast_history_days=21` controls the training/lookback window used by the dashboard request.
- `validation_days=3` controls the walk-forward model selection window.

## Vercel Deployment

The repository is configured for Vercel with `vercel.json`. Vercel builds the React dashboard from `frontend/` and serves the static output from `frontend/dist`.

For a reliable hackathon preview, `/api/dashboard` rewrites to a committed static payload at `frontend/public/demo-dashboard.json`. The frontend still supports the live Python API: set `VITE_API_BASE` in Vercel environment variables when the optimizer API is hosted externally.

See `docs/vercel_deployment.md` for deployment details.

## Collaboration Setup

Clone the shared repo:

```bash
git clone https://github.com/kiriakostsourekas-wq/ETW-Hackathon.git
cd ETW-Hackathon
python3 -m pip install -r requirements.txt
PYTHONPATH=src pytest -q
streamlit run app.py
```

Before starting work, read:

- `CLAUDE.md` for AI-agent and teammate operating rules.
- `CONTRIBUTING.md` for branch, commit, and PR workflow.
- `docs/team_workflow.md` for the four-person workstream split.
- `docs/research_sources.md` for source links and leakage notes.

Generated data is intentionally ignored by git. Use the scripts below to recreate local raw/processed files.

## What Is Implemented

- `src/batteryhack/data_sources.py`: HEnEx, IPTO, and Open-Meteo ingestion with xlsx parsing and local caching under `data/raw/`.
- `src/batteryhack/optimizer.py`: SciPy HiGHS MILP battery scheduler with SoC, power, efficiency, terminal SoC, degradation, cycle, and single charge/discharge mode constraints.
- `src/batteryhack/forecasting.py`: explainable structural forecast proxy and Ridge model hook for deeper history.
- `src/batteryhack/production_forecast.py`: leakage-safe forecast table builder, walk-forward model selection, model registry, price-taker dispatch, and realized/oracle value metrics.
- `src/batteryhack/market_impact.py`: offline HEnEx aggregated-curve re-clearing experiment for testing national DAM MCP impact from one `330 MW / 790 MWh` BESS.
- `src/batteryhack/api_server.py`: JSON API for the React dashboard, backed by HEnEx/IPTO/Open-Meteo ingestion and the MILP optimizer.
- `app.py`: Streamlit dashboard with a submission story, METLEN price-taker dispatch, market-impact test instructions, sensitivity grid, and source traceability.
- `frontend/`: React/Tailwind/Recharts dashboard that consumes the optimizer API.
- `docs/METLEN_BESS_submission_walkthrough.pptx`: six-slide editable teammate deck covering thesis, Greek problem, operational loop, data stack, simulator method, and caveats.
- `tests/`: optimizer and data-contract tests.

## Run Tests

```bash
PYTHONPATH=src pytest -q
```

## Run A Backtest

```bash
python3 scripts/backtest_recent.py --start 2026-04-22 --end 2026-04-22
```

Backtest outputs are written to `data/processed/`.

## Run The March ML Smoke Simulation

```bash
PYTHONPATH=src python3 scripts/march_smoke_simulation.py
```

The script loads March public market data, drops fallback-price days by default, compares live-safe
forecast model families on `2026-03-15` through `2026-03-21`, selects the best ML family, and runs
METLEN-scale dispatch from `2026-03-22` through `2026-03-31` settled against actual DAM prices.
Outputs are written to `data/processed/march_smoke_model_performance.csv`,
`data/processed/march_smoke_daily_model_performance.csv`, and
`data/processed/march_smoke_dispatch.csv`.

## Train The Production Forecast Registry

```bash
PYTHONPATH=src python3 scripts/train_forecast_registry.py --target-date 2026-04-22
```

This builds the live-safe feature table, runs walk-forward model selection, generates the 15-minute price forecast, optimizes one price-taker schedule, then writes:

- `data/processed/forecast_model_registry.json`
- `data/processed/price_taker_forecast.csv`

The registry records the selected model, feature columns, validation metrics, training window, source summary, leakage audit, and price-taker dispatch assumptions.

## Scrape No-Key Training Data

```bash
PYTHONPATH=src python3 scripts/scrape_training_data.py --start 2025-10-01 --end 2026-04-29
```

This builds a leakage-conscious 15-minute training CSV from public no-key sources:

- HEnEx Results Summary MCP target prices.
- HEnEx PreMarketSummary and POSNOMs when listed on the public DAM page.
- IPTO load forecast, RES forecast, unit availability, ATC, and long-term PTR nominations.
- Open-Meteo weather for the configured Greek regional points.

By default, this script does **not** allow synthetic price fallback and does **not** fill missing feature columns with synthetic demo data. Outputs are written to:

- `data/processed/greek_dam_training_dataset.csv`
- `data/processed/greek_dam_training_manifest.json`

## Test Single-BESS Market Impact

After downloading HEnEx `EL-DAM_AggrCurves_EN` files into `data/raw/`, run:

```bash
PYTHONPATH=src python3 scripts/run_market_impact_experiment.py --start-date 2026-04-22 --curve-dir data/raw
```

The experiment optimizes one METLEN-scale dispatch, re-clears active intervals on the HEnEx aggregated curves, and writes:

- `data/processed/market_impact_intervals.csv`
- `data/processed/market_impact_daily_summary.csv`

The decision rule calls one METLEN-scale BESS negligible only if median absolute MCP shift is `< 0.5 EUR/MWh`, revenue haircut is `< 2%`, and at least 80% of active intervals validate.

## Sample HEnEx 15-Minute Prices

```bash
python3 scripts/sample_henex_15min_prices.py --start 2026-04-22 --end 2026-04-24
```

The script loops over a small capped date range, fetches HEnEx DAM Results Summary workbooks, extracts the 96 quarter-hour MCP prices per day, and writes `data/processed/henex_15min_price_sample.csv`.

## Check ENTSO-E Access

```bash
ENTSOE_SECURITY_TOKEN=your_token python3 scripts/check_entsoe_connection.py --sample
```

Without `ENTSOE_SECURITY_TOKEN`, the script only verifies that the ENTSO-E API endpoint is reachable and does not request market data.

## Data Sources

- HEnEx DAM publications: https://www.enexgroup.gr/en/web/guest/markets-publications-el-day-ahead-market
- IPTO Operation & Market Files API: https://www.admie.gr/en/market/market-statistics/file-download-api
- Open-Meteo API: https://open-meteo.com/en/docs

See `docs/admie_market_data_catalog.md` for ADMIE/IPTO filetypes worth integrating later.
See `docs/forecasting_signal_plan.md` for the ranked forecasting signal and leakage plan.
See `docs/model_logic_and_forecasting.md` for the MILP optimizer, forecast pipeline, and HEnEx market-impact experiment.
See `docs/vercel_deployment.md` for the Vercel static dashboard deployment path.
See `docs/comparable_project_analysis.md` for the top GitHub analogue repositories we used to benchmark the simulator design.
See `docs/METLEN_BESS_submission_walkthrough.pptx` for the short teammate walkthrough deck.

## Demo Narrative

Greece has increasing solar/wind penetration, more midday surplus and curtailment risk, and stronger 15-minute price volatility. The battery charges when prices are low and RES output is high, then discharges into scarcity or evening peak intervals. The prototype avoids dependence on historical battery telemetry by using public market/system/weather signals plus explicit battery constraints.

The demo now follows five tabs: `Story`, `Dispatch`, `Market Impact Test`, `Sensitivity`, and `Data Trace`. The main dispatch is price-taker-only; the market-impact tab explains how to test whether that assumption is defensible with HEnEx aggregated curves.
