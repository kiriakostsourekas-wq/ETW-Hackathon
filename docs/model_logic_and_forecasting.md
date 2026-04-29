# Model Logic And Forecasting

This document explains the production optimizer, live-safe forecast pipeline, and the separate HEnEx curve experiment used to test whether one METLEN-scale BESS can be treated as a price-taker.

## 1. Battery Optimizer

The battery scheduler is a Mixed-Integer Linear Programming model solved with SciPy/HiGHS.

For each 15-minute market time unit, the model chooses:

- charge power in MW,
- discharge power in MW,
- state of charge in MWh,
- an optional binary operating mode so the asset cannot charge and discharge at the same time.

The objective maximizes:

```text
discharge revenue - charge cost - degradation/throughput cost
```

The model enforces power limits, energy capacity, minimum/maximum SoC, round-trip efficiency losses, initial/terminal SoC, optional equivalent-cycle budget, and no simultaneous charge/discharge when single-mode enforcement is enabled.

Default METLEN-scale assumptions:

```text
Power: 330 MW
Energy: 790 MWh
Duration: 2.39 hours
Round-trip efficiency: 85%
SoC band: 10-90%
Initial/terminal SoC: 50%
Degradation cost: 4 EUR/MWh throughput
Cycle budget: 1.5 equivalent cycles/day
```

## 2. Forecast Target

The production forecast target is Greek HEnEx Day-Ahead Market MCP at 15-minute resolution.

Live-safe features include:

- historical HEnEx DAM prices as labels and lagged price-shape inputs,
- IPTO/ADMIE day-ahead load forecast,
- IPTO/ADMIE day-ahead RES forecast,
- Open-Meteo weather,
- calendar features.

Live forecasts must not use post-clearing or actual values as features. Blocked examples include same-day DAM target price, accepted volumes, aggregated curve slope, real-time SCADA actuals, and actual battery schedules.

## 3. Forecast Model Stack

The training pipeline compares these model families with walk-forward validation:

- `structural_proxy`: transparent rule-based fallback using net load, weather, and calendar.
- `interval_profile`: historical average by 15-minute interval and weekend flag.
- `ridge`: regularized linear model.
- `hist_gradient_boosting`: nonlinear tree-based model from scikit-learn.

Model selection uses validation MAE first, then RMSE. Reporting also includes spread-direction accuracy plus top- and bottom-quartile capture, because arbitrage value depends on finding charge/discharge windows as much as average price level.

## 4. Production Path

The production API and React dashboard now run one clean price-taker dispatch:

```text
build live-safe feature table
walk-forward select the forecast model
forecast the target day's 96 MCP values
optimize the BESS once against forecast_price_eur_mwh
settle that same schedule against published DAM MCP for backtest metrics
```

The implementation entry point is `build_price_taker_forecast()` in `src/batteryhack/production_forecast.py`.

The output includes:

- selected model registry,
- leakage audit,
- base forecast and uncertainty band,
- forecast-driven price-taker schedule,
- objective net revenue on forecast MCP,
- realized net revenue against published DAM MCP,
- oracle comparison when actual MCP exists.

There is no storage-adjusted forecast, no assumed spread-compression layer, and no second optimization loop in the production/API/UI path.

## 5. Market-Impact Hypothesis Test

The project still needs to know whether the price-taker assumption is defensible for a `330 MW / 790 MWh` METLEN/Karatzis BESS. That is handled as an offline research experiment, not as operating logic.

Hypothesis:

```text
H0: one METLEN-scale BESS has negligible impact on national Greek HEnEx DAM MCP.
```

The experiment uses HEnEx anonymous aggregated buy/sell curve files, such as `EL-DAM_AggrCurves_EN`, because those curves expose market depth near the clearing point.

For each active 15-minute interval:

- charge MW is modeled as extra buy demand,
- discharge MW is modeled as extra sell supply,
- the interval is re-cleared counterfactually,
- baseline re-clear must match published MCP within tolerance,
- missing or invalid intervals are flagged.

Headline metrics:

- median absolute MCP shift,
- p95 absolute MCP shift,
- max absolute MCP shift,
- charge-interval average uplift,
- discharge-interval average suppression,
- revenue haircut from settling the same schedule on impacted prices,
- BESS power as percent of load or cleared volume when available,
- market depth near MCP in MW per EUR/MWh.

Decision rule:

- `negligible` only if median absolute MCP shift is `< 0.5 EUR/MWh` and revenue haircut is `< 2%`.
- `locally_material` if median passes but p95 shift is high.
- `inconclusive` if fewer than 80% of active intervals validate.
- otherwise `material`.

Run it with local HEnEx AggrCurves files:

```bash
PYTHONPATH=src python3 scripts/run_market_impact_experiment.py --start-date 2026-04-22 --curve-dir data/raw
```

Outputs:

- `data/processed/market_impact_intervals.csv`
- `data/processed/market_impact_daily_summary.csv`

## 6. API And Artifacts

Start the API:

```bash
PYTHONPATH=src python3 -m batteryhack.api_server --port 8000
```

Main endpoint:

```text
/api/dashboard?date=2026-04-22
```

Export the forecast registry and price-taker forecast artifact:

```bash
PYTHONPATH=src python3 scripts/train_forecast_registry.py --target-date 2026-04-22
```

Outputs:

- `data/processed/forecast_model_registry.json`
- `data/processed/price_taker_forecast.csv`
