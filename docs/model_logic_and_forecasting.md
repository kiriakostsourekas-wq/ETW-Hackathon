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

## 5. Technical Walkthrough Of The Four-Step Loop

### Forecast 96 Quarter-Hour MCP Values

`build_storage_aware_forecast()` builds one feature table from the selected history window through the target day. The target frame is exactly the target delivery day, so it should contain 96 rows. The training frame is every timestamp before the target day.

The model-selection path is:

```text
load_market_history()
compare_forecast_models_walk_forward()
select_best_model()
forecast_price_with_model()
```

The candidate models are `structural_proxy`, `interval_profile`, `ridge`, and `hist_gradient_boosting`. The selected model writes three target-day columns:

- `forecast_price_eur_mwh`
- `forecast_low_eur_mwh`
- `forecast_high_eur_mwh`

The leakage guard comes from `candidate_feature_columns()` and `assert_live_feature_columns()`: post-clearing columns such as `dam_price_eur_mwh`, actual SCADA, and curve slopes are labels/diagnostics, not live features.

### Optimize Against The Base Forecast

The first battery run is a price-taker schedule:

```python
optimize_battery_schedule(base_forecast_frame, battery_params, price_col="forecast_price_eur_mwh")
```

The optimizer sees the 96 forecast prices and chooses charge MW, discharge MW, and SoC for each interval. It maximizes forecast net revenue subject to power, energy, SoC, efficiency, terminal SoC, degradation, cycle-budget, and single-mode constraints.

### Apply Storage Feedback

The base schedule is then passed to:

```python
adjust_prices_for_storage_feedback(
    base_forecast_frame,
    base_schedule,
    impact_params,
    price_col="forecast_price_eur_mwh",
    output_col="storage_adjusted_forecast_eur_mwh",
)
```

The scenario layer estimates how fleet battery behavior changes the price shape:

- charging intervals get positive price adjustments because fleet charging adds demand;
- discharging intervals get negative price adjustments because fleet discharging adds supply;
- an additional spread-compression factor pulls lows upward and highs downward.

The current elasticities are explicit assumptions in `StorageImpactParams`. They are not claimed as calibrated Greek market facts yet.

### Re-Optimize And Report Economics

The second optimizer run uses the adjusted price column:

```python
optimize_battery_schedule(
    storage_adjusted_frame,
    battery_params,
    price_col="storage_adjusted_forecast_eur_mwh",
)
```

The output compares:

- price-taker objective value on the base forecast;
- storage-aware objective value after spread compression;
- realized value of both schedules settled against published DAM prices when target-day actual MCP exists;
- oracle value from optimizing directly on published DAM MCP;
- capture ratio versus oracle;
- storage impact metrics such as average spread compression and midday/evening adjustments.

## 6. API And Artifacts

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
