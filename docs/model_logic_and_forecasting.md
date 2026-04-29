# Model Logic And Forecasting

This document explains the optimizer, forecasting pipeline, and battery regime-change layer used by the ETW Hackathon prototype.

## 1. Battery Optimizer

The battery scheduler is a Mixed-Integer Linear Programming model solved with SciPy/HiGHS.

For each 15-minute market time unit, the model chooses:

- charge power in MW,
- discharge power in MW,
- state of charge in MWh,
- an optional binary operating mode so the asset cannot charge and discharge at the same time.

The objective is to maximize net economic value:

```text
discharge revenue - charge cost - degradation/throughput cost
```

The model enforces:

- charge and discharge power limits,
- energy capacity limits,
- minimum and maximum state of charge,
- round-trip efficiency losses,
- initial and terminal state of charge,
- optional equivalent-cycle budget,
- no simultaneous charge and discharge when single-mode enforcement is enabled.

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

The live-safe feature table uses:

- HEnEx DAM prices as historical labels,
- IPTO/ADMIE day-ahead load forecast,
- IPTO/ADMIE day-ahead RES forecast,
- Open-Meteo weather,
- calendar features,
- lagged/derived price-shape features through historical training data.

Live forecasts must not use post-clearing or actual values as features. Blocked examples include:

- same-day published DAM target price,
- accepted DAM volumes,
- aggregated curve slope unless used only as a post-clearing diagnostic,
- real-time SCADA actual load/RES,
- actual battery schedules.

The code classifies feature timing in `src/batteryhack/forecasting.py` and rejects post-clearing columns for live forecasts.

## 3. Model Stack

The training pipeline compares these model families with walk-forward validation:

- `structural_proxy`: transparent rule-based fallback using net load, weather, and calendar.
- `interval_profile`: historical average by 15-minute interval and weekend flag.
- `ridge`: regularized linear model.
- `hist_gradient_boosting`: nonlinear tree-based model from scikit-learn.

Model selection uses validation MAE first, then RMSE. Reporting also includes:

- MAE,
- RMSE,
- spread-direction accuracy,
- top-quartile price capture,
- bottom-quartile price capture.

Those extra metrics matter because battery profit depends on identifying cheap charge intervals and expensive discharge intervals, not only average price level.

## 4. Battery Regime Change

Historical Greek prices mostly reflect the pre-standalone-battery regime. As utility-scale BESS connects, batteries change price formation:

- charging adds demand in low-price/high-RES hours, lifting low prices;
- discharging adds supply in high-price/scarcity hours, suppressing high prices;
- daily spreads compress.

The current implementation models this with a scenario layer:

```text
forecast base DAM prices
optimize battery schedule on base forecast
adjust forecast prices for fleet charging/discharging
re-optimize on storage-adjusted forecast prices
compare price-taker and storage-aware value
```

Current scenarios are assumption-based:

- low impact,
- medium impact,
- high impact.

The next calibration step is to parse HEnEx aggregated buy/sell curves and estimate interval-level price elasticity. Until that is implemented, storage impact is reported as scenario-based, not observed Greek market fact.

## 5. API And Artifacts

The React dashboard uses:

```bash
PYTHONPATH=src python3 -m batteryhack.api_server --port 8000
```

Main endpoint:

```text
/api/dashboard?date=2026-04-22
```

The response includes:

- direct DAM optimizer metrics,
- selected forecast model registry,
- feature columns and leakage audit,
- base forecast price,
- storage-adjusted forecast price,
- price-taker schedule,
- storage-aware schedule,
- model validation metrics,
- regime-change assumptions.

To write a registry JSON and forecast CSV:

```bash
PYTHONPATH=src python3 scripts/train_forecast_registry.py --target-date 2026-04-22
```
