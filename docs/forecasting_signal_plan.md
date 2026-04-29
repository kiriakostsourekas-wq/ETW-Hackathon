# Forecasting Signal Plan

This document stores metadata and modeling decisions only. It does not store downloaded market
or system data.

## Forecast Target

The target is HEnEx Greek Day-Ahead Market MCP at 15-minute resolution. Published MCP, market
coupling, aggregated curves, realized SCADA, and dispatch results are post-clearing diagnostics
unless a timestamp check proves they were available before the modeled decision time.

## Storage Regime-Shift Caveat

Greek standalone BESS participation changes the price formation problem itself. Pre-battery MCP
history does not include fleet-scale battery demand in low-price/high-RES intervals or fleet-scale
battery supply in high-price evening intervals. Forecast models trained only on historic drivers
should therefore be treated as pre-feedback labels that can overstate future spreads.

The implemented mitigation is a storage-aware scenario layer:

- keep the price-taker optimizer as the baseline value case,
- adjust prices counterfactually after the battery schedule is known,
- lift charge intervals, suppress discharge intervals, and compress daily spreads,
- expose low, medium, and high impact assumptions plus participating fleet MW/MWh,
- later replace scenario elasticities with HEnEx aggregated buy/sell curve slopes.

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
- Champion for the March smoke run: histogram gradient boosting selected by validation MAE.
- Ridge remains the linear challenger and interpretability fallback; in the March smoke run it had
  slightly lower validation RMSE but higher MAE than histogram gradient boosting.
- Uncertainty: residual scenario band from historical interval-profile errors.

## Acceptance Criteria

- Every source and candidate feature has a timing class.
- Live forecasting rejects post-clearing and actual columns.
- Walk-forward backtests train only on dates before the forecasted delivery day.
- Evaluation reports price error plus spread/top-bottom interval capture, because battery value
  depends on charge/discharge window ranking as much as level accuracy.
