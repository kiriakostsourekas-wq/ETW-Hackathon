# Greek DAM BESS Optimization

Professional hackathon prototype for operating a METLEN-scale battery energy
storage system in the Greek Day-Ahead Market. The project combines public Greek
market/system/weather data, a chronological ML forecasting harness, and a
constraint-aware MILP battery optimizer.

## Submission Headline

On 38 evaluated Greek DAM days from `2026-03-22` through `2026-04-29`, the
Scarcity Ensemble plus optimizer earned EUR 2.968M versus EUR 2.571M for the
UK naive baseline: EUR 397k uplift, 15.45% improvement, and a 78.9% daily win
rate.

The framing is data scarcity: Greece does not yet have a long public history of
standalone BESS dispatch telemetry. This prototype does not use Greek BESS
telemetry. It uses public Greek DAM prices, IPTO/ADMIE system signals, weather
signals where available, calendar structure, and explicit battery constraints.

Future BESS scenarios in this repo are spread-compression stress tests. They are
not forecasts of future Greek electricity prices.

## Battery Parameter Policy

METLEN `330 MW / 790 MWh` is the public-scale demo preset. The SoC band,
round-trip efficiency, initial SoC, terminal SoC, equivalent-cycle cap, and
degradation cost are configurable sensitivity parameters, not hidden fixed
assumptions.

The official 38-day evidence used the research preset: 10%-90% SoC band, 85%
round-trip efficiency, 50% initial and terminal SoC, 1.5 equivalent cycles/day,
EUR 4/MWh throughput degradation cost, and single-mode charge/discharge
enforcement. The live UI can adjust battery parameters for the daily demo, but
changing live daily parameters does not automatically regenerate the 38-day
research evidence. To change the headline evidence, rerun the ML research and
strategy-comparison commands with the intended parameter preset.

## Local Launch

The simplest way to run the submission demo locally is:

```bash
python3 run_dashboard.py
```

The runner starts the Python optimizer API and the React dashboard, and prints
the local Vite URL, usually `http://127.0.0.1:5173/`.

Manual setup is also supported. Install dependencies:

```bash
python -m pip install -r requirements.txt
cd frontend && npm install
```

Run the backend:

```bash
PYTHONPATH=src python -m batteryhack.api_server
```

Run the frontend:

```bash
cd frontend && npm run dev
```

Open the Vite URL printed by the frontend, usually `http://127.0.0.1:5173/`.

The dashboard includes a compact committed fallback payload, so a clean clone can
show the core demo and evidence even before regenerated CSV artifacts are
available. To regenerate the research artifacts from source, run the commands in
**Reproduce The Evidence**.

## Quick Future-Stress Run After Pull

From the repo root, run:

```bash
PYTHONPATH=src python scripts/run_future_market_impact.py --input data/processed/strategy_comparison_intervals.csv
```

This reruns the future BESS spread-compression stress test using the final
strategy-comparison interval schedules and writes:

- `data/processed/future_market_impact_summary.csv`
- `data/processed/future_market_impact_intervals.csv`
- `data/processed/future_market_impact_headline.json`

Prerequisite: `data/processed/strategy_comparison_intervals.csv` must exist. If
it is missing after a clean pull, first run the ML research and strategy
comparison commands in **Reproduce The Evidence** below.

## Validation

Run the release checks before recording or submitting:

```bash
PYTHONPATH=src python scripts/validate_research_outputs.py
PYTHONPATH=src pytest
cd frontend && npm run build
```

## Reproduce The Evidence

Regenerate the validated ML research artifact set used by the headline:

```bash
PYTHONPATH=src python scripts/run_ml_research.py \
  --history-start 2026-03-01 \
  --start 2026-03-22 \
  --end 2026-04-29 \
  --min-train-days 14 \
  --models ridge,scarcity_ensemble \
  --summary-output ml_research_scarcity_summary.csv \
  --daily-output ml_research_scarcity_daily.csv \
  --predictions-output ml_research_scarcity_predictions.csv \
  --skipped-output ml_research_scarcity_skipped_days.csv \
  --assumptions-output ml_research_scarcity_assumptions.json \
  --daily-winners-output ml_research_scarcity_daily_winners.csv \
  --model-stability-output ml_research_scarcity_model_stability.csv \
  --paired-uplift-output ml_research_scarcity_paired_uplift.csv
```

Regenerate the official ML-versus-UK benchmark:

```bash
PYTHONPATH=src python scripts/run_strategy_comparison.py \
  --ml-daily ml_research_scarcity_daily.csv \
  --ml-predictions ml_research_scarcity_predictions.csv \
  --models scarcity_ensemble
```

Regenerate future BESS penetration stress tests:

```bash
PYTHONPATH=src python scripts/run_future_market_impact.py \
  --input data/processed/strategy_comparison_intervals.csv \
  --output-prefix future_market_impact \
  --headline-output future_market_impact_headline.json
```

Generated data under `data/raw/`, `data/cache/`, and `data/processed/` is
ignored by git. Recreate those artifacts with the commands above.

## What Is Implemented

- `src/batteryhack/ml_research.py`: walk-forward, no-leakage ML research harness
  with Ridge, tree models, interval profile, stacking, scarcity ensemble,
  paired-uplift diagnostics, and dispatch-value metrics.
- `src/batteryhack/optimizer.py`: SciPy HiGHS MILP battery scheduler with power,
  energy, efficiency, SoC, terminal SoC, degradation, cycle, and single-mode
  constraints.
- `src/batteryhack/strategy_comparison.py`: same-window comparison between ML
  strategies and the UK naive baseline applied to Greek DAM prices.
- `src/batteryhack/future_market_impact.py`: future spread-compression stress
  scenarios for increasing BESS penetration.
- `src/batteryhack/api_server.py`: local JSON API for the demo dashboard.
- `frontend/`: React dashboard consuming the local optimizer/evidence API.
- `scripts/validate_research_outputs.py`: strict artifact consistency check for
  the final headline evidence.

## Data Sources

- HEnEx DAM publications: https://www.enexgroup.gr/en/web/guest/markets-publications-el-day-ahead-market
- IPTO/ADMIE market files: https://www.admie.gr/en/market/market-statistics/file-download-api
- Open-Meteo API: https://open-meteo.com/en/docs

## Submission Notes

The benchmark is the implementable UK naive baseline on the same Greek delivery
days and battery assumptions. The oracle is only an upper-bound diagnostic, not
the benchmark. A concise recording script is available at
`docs/video_demo_script_5min.md`.
