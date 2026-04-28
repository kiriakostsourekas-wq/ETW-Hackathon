# ADMIE/IPTO Market Data Catalog

This file stores source definitions and candidate filetypes only. It does not store downloaded
market, system, or operational data.

## API Endpoints

- Filetype catalog: `https://www.admie.gr/getFiletypeInfoEN`
- Exact coverage search: `https://www.admie.gr/getOperationMarketFile?dateStart=YYYY-MM-DD&dateEnd=YYYY-MM-DD&FileCategory=FILETYPE`
- Overlapping range search: `https://www.admie.gr/getOperationMarketFilewRange?dateStart=YYYY-MM-DD&dateEnd=YYYY-MM-DD&FileCategory=FILETYPE`

## Highest-Value Filetypes

| Filetype | Timing | Use |
|---|---|---|
| `ISP1DayAheadLoadForecast` | Ex-ante | Next-day demand signal. |
| `ISP1DayAheadRESForecast` | Ex-ante | Next-day solar/wind and curtailment-risk signal. |
| `ISP1Requirements` | Ex-ante | System requirement context. |
| `ISP1UnitAvailabilities` | Ex-ante | Thermal/hydro availability and marginal-price risk. |
| `DailyAuctionsSpecificationsATC` | Ex-ante | Available transfer capacity for imports/exports. |
| `LTPTRsNominationsSummary` | Ex-ante | Cross-border nomination context. |
| `ReservoirFillingRate` | Ex-ante | Hydro flexibility and scarcity context. |
| `WeekAheadWaterUsageDeclaration` | Ex-ante | Hydro scheduling context for multi-day forecasts. |
| `ISP1ISPResults` | Post-clearing | Validation and backtest context, not ex-ante forecasting input. |
| `DispatchSchedulingResults` | Post-clearing | Dispatch schedule after market outcomes are known. |
| `RealTimeSCADASystemLoad` | Actual | Actual load for backtests and calibration. |
| `RealTimeSCADARES` | Actual | Actual RES output for backtests and curtailment analysis. |
| `RealTimeSCADAImportsExports` | Actual | Actual net interconnector flows. |
| `SystemRealizationSCADA` | Actual | Realized system facts. |
| `UnitProduction` | Actual | Unit-level production backtest data when available. |
| `UnitsMaintenanceSchedule` | Planning | Forward outage scenarios. |
| `InterconnectionsMaintenanceSchedule` | Planning | Forward cross-border outage scenarios. |

## Leakage Rule

Use `ex_ante` and `planning` filetypes as model inputs for day-ahead forecasts. Keep
`post_clearing` and `actual` filetypes for diagnostics, attribution, and backtests unless a
timestamp check proves the data was available before the modeled decision time.
