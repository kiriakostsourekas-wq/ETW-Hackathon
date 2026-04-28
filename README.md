# Greek Battery Optimization Hackathon

This project implements a presentation-ready prototype for constraint-aware battery scheduling in the Greek Day-Ahead Market. It combines public HEnEx DAM prices, IPTO load/RES forecasts, Open-Meteo weather, a transparent forecast proxy, and a MILP battery optimizer.

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
- `src/batteryhack/forecasting.py`: explainable structural forecast proxy and Ridge model hook for deeper history.
- `app.py`: Streamlit dashboard with battery controls, dispatch, SoC, forecast/system signals, business framing, and source traceability.
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

## Demo Narrative

Greece has increasing solar/wind penetration, more midday surplus and curtailment risk, and stronger 15-minute price volatility. The battery charges when prices are low and RES output is high, then discharges into scarcity or evening peak intervals. The prototype avoids dependence on historical battery telemetry by using public market/system/weather signals plus explicit battery constraints.
