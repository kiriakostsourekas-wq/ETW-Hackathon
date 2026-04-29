# Forecasting Signal Plan

This document stores metadata and modeling decisions only. It does not store downloaded market or system data.

## Forecast Target

The target is HEnEx Greek Day-Ahead Market MCP at 15-minute resolution. Published MCP, market coupling, aggregated curves, realized SCADA, and dispatch results are post-clearing diagnostics unless a timestamp check proves they were available before the modeled decision time.

## Storage Regime Caveat

Greek standalone BESS participation changes the price formation problem itself. Pre-battery MCP history does not include fleet-scale battery demand in low-price/high-RES intervals or fleet-scale battery supply in high-price evening intervals. Forecast models trained only on historic drivers should therefore be treated as pre-feedback labels that may overstate future spreads.

The implemented production mitigation is deliberately conservative:

- keep the dashboard and API price-taker only;
- do not assume spread compression in the operating forecast;
- optimize once against the forecast MCP signal;
- test the price-taker assumption offline with HEnEx aggregated buy/sell curves;
- move to price-maker or equilibrium dispatch only if the curve experiment shows material impact.

## Live-Eligible Feature Families

- Residual demand: ADMIE/IPTO day-ahead load forecast minus RES forecast.
- Weather: Open-Meteo radiation, cloud cover, wind, and temperature for Greek regional points.
- Dispatchable availability: ADMIE/IPTO unit availability, maintenance, hydro, and reservoir data.
- Cross-border constraints: ADMIE/IPTO ATC and nominations, then ENTSO-E once the token is active.
- Fuel and carbon: TTF gas and EUA carbon latest-known values only when access is reproducible.
- Calendar: interval, weekend, holiday, solar/evening shape features.

## Diagnostic-Only Feature Families

- HEnEx accepted volumes, market coupling results, and aggregated curve slope.
- RAAEY energy surplus and curtailment monitoring.
- ADMIE/IPTO SCADA actuals, ISP results, dispatch results, and realized interconnector flows.
- Neighboring next-day DAM prices if they are only available after Greek market clearing.

## Model Stack

- Baseline: structural proxy and interval price-shape profile.
- ML: Ridge and histogram gradient boosting selected with walk-forward validation.
- Uncertainty: residual scenario band from historical interval-profile errors.

## Production Forecast Pipeline

The production pipeline is implemented in `src/batteryhack/production_forecast.py`.

1. Build a feature table from HEnEx DAM labels, HEnEx pre-market nominations, IPTO load/RES forecasts, IPTO unit/cross-border signals, Open-Meteo weather, calendar features, and lagged historical price shape.
2. Run walk-forward validation only on dates before the target delivery day.
3. Select among `structural_proxy`, `interval_profile`, `ridge`, and `hist_gradient_boosting` using validation MAE, with RMSE as the tie-breaker.
4. Forecast the target day's 96 quarter-hour MCP values.
5. Optimize the battery once against the base forecast.
6. Settle that same schedule against actual DAM MCP when available.
7. Report forecast metrics, dispatch economics, and oracle capture.

The dashboard endpoint returns the selected model registry, feature columns, leakage audit, base forecast, forecast-driven price-taker dispatch, value metrics, and assumptions.

To export artifacts:

```bash
PYTHONPATH=src python3 scripts/train_forecast_registry.py --target-date 2026-04-22
```

## No-Key Training Scraper

The reusable scraper is implemented in `scripts/scrape_training_data.py`:

```bash
PYTHONPATH=src python3 scripts/scrape_training_data.py --start 2025-10-01 --end 2026-04-29
```

Default behavior is strict enough for model training:

- synthetic DAM prices are rejected unless `--allow-synthetic` is passed;
- missing feature columns are left missing unless `--fill-synthetic-features` is passed;
- a JSON manifest stores per-day source URLs and parse warnings;
- the generated CSV is local-only under `data/processed/` and should not be committed.

Currently integrated no-key feature sources:

- HEnEx `ResultsSummary`: target MCP labels.
- HEnEx `PreMarketSummary`: forward nominations by gas, hydro, RES, lignite, BESS, demand, production, imports, and exports.
- HEnEx `POSNOMs`: aggregate buy/sell forward-position nomination signals.
- IPTO `ISP1DayAheadLoadForecast` and `ISP1DayAheadRESForecast`.
- IPTO `ISP1UnitAvailabilities`.
- IPTO `DailyAuctionsSpecificationsATC`.
- IPTO `LTPTRsNominationsSummary`.
- Open-Meteo forecast/historical forecast weather.

The literal `ENTSOE_API_TOKEN=your_token_here` string is a placeholder, not a usable token. Once a real ENTSO-E token is available, store it locally as `ENTSOE_SECURITY_TOKEN` or `ENTSOE_API_TOKEN` in `.env` and never commit it.

## Market-Impact Experiment

Run the separate HEnEx curve test when aggregated curve files are available:

```bash
PYTHONPATH=src python3 scripts/run_market_impact_experiment.py --start-date 2026-04-22 --curve-dir data/raw
```

The experiment tests whether one `330 MW / 790 MWh` BESS is negligible for national DAM MCP using median shift `< 0.5 EUR/MWh`, revenue haircut `< 2%`, and at least 80% valid active-interval coverage.

## Acceptance Criteria

- Every source and candidate feature has a timing class.
- Live forecasting rejects post-clearing and actual columns.
- Walk-forward backtests train only on dates before the forecasted delivery day.
- Every forecast day returns 96 intervals.
- Evaluation reports price error plus spread/top-bottom interval capture, because battery value depends on charge/discharge window ranking as much as level accuracy.
