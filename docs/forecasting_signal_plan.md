# Forecasting Signal Plan

This document stores metadata and modeling decisions only. It does not store downloaded market
or system data.

## Forecast Target

The target is HEnEx Greek Day-Ahead Market MCP at 15-minute resolution. Published MCP, market
coupling, aggregated curves, realized SCADA, and dispatch results are post-clearing diagnostics
unless a timestamp check proves they were available before the modeled decision time.

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
- Champion: Ridge model using live-safe ex-ante features.
- Challenger: histogram gradient boosting once enough historical rows exist.
- Uncertainty: residual scenario band from historical interval-profile errors.

## Acceptance Criteria

- Every source and candidate feature has a timing class.
- Live forecasting rejects post-clearing and actual columns.
- Walk-forward backtests train only on dates before the forecasted delivery day.
- Evaluation reports price error plus spread/top-bottom interval capture, because battery value
  depends on charge/discharge window ranking as much as level accuracy.
