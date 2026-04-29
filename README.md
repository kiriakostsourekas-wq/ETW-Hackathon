# Greek Battery Optimization Hackathon

This project implements a presentation-ready prototype for constraint-aware battery scheduling in the Greek Day-Ahead Market. It combines public HEnEx DAM prices, IPTO load/RES forecasts, Open-Meteo weather, a transparent forecast proxy, a MILP battery optimizer, and a storage-aware price-impact scenario layer.

## Quick Start

```bash
python3 -m pip install -r requirements.txt
streamlit run app.py
```

The default demo date is `2026-04-22`, which has public HEnEx/IPTO files available. If a source is unavailable, the app fills missing columns with deterministic synthetic data so the live demo remains stable.

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
- `src/batteryhack/price_impact.py`: counterfactual storage-feedback scenarios that lift charging intervals, suppress discharging intervals, and estimate spread compression versus the price-taker baseline.
- `src/batteryhack/forecasting.py`: explainable structural forecast proxy and Ridge model hook for deeper history.
- `app.py`: Streamlit dashboard with a submission story, METLEN dispatch, storage-aware regime-shift comparison, sensitivity grid, and source traceability.
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
See `docs/comparable_project_analysis.md` for the top GitHub analogue repositories we used to benchmark the simulator design.
See `docs/METLEN_BESS_submission_walkthrough.pptx` for the short teammate walkthrough deck.

## Demo Narrative

Greece has increasing solar/wind penetration, more midday surplus and curtailment risk, and stronger 15-minute price volatility. The battery charges when prices are low and RES output is high, then discharges into scarcity or evening peak intervals. The prototype avoids dependence on historical battery telemetry by using public market/system/weather signals plus explicit battery constraints.

The demo now follows five tabs: `Story`, `Dispatch`, `Regime Shift`, `Sensitivity`, and `Data Trace`. `Regime Shift` keeps the price-taker result visible as pre-feedback value, then shows storage-aware scenario haircuts from low/medium/high price-impact assumptions.
