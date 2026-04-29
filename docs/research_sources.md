# Research Sources

This file tracks sources we can cite in code comments, docs, notebooks, and slides.

## Greece Market And System Data

- HEnEx Day-Ahead Market publications: https://www.enexgroup.gr/en/web/guest/markets-publications-el-day-ahead-market
  - Use for DAM Results, ResultsSummary, aggregated curves, and pre-market files.
  - Direct ResultsSummary pattern: `https://www.enexgroup.gr/documents/20126/366820/YYYYMMDD_EL-DAM_ResultsSummary_EN_v##.xlsx`
- IPTO/ADMIE market statistics API: https://www.admie.gr/en/market/market-statistics/file-download-api
  - Use for load forecasts, RES forecasts, SCADA load/RES, imports/exports.
  - Internal catalogue: `docs/admie_market_data_catalog.md`.
- Open-Meteo API docs: https://open-meteo.com/en/docs
  - Use for weather predictors: radiation, cloud cover, wind, temperature.
- ENTSO-E Transparency Platform API guide: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide_prod_backup_06_11_2024.html
  - Use as fallback/cross-check for price, load, generation, and cross-border signals.
- Forecasting signal plan: `docs/forecasting_signal_plan.md`
  - Use for source scoring, live-feature timing, and leakage boundaries.
- RAAEY energy surplus monitoring: https://www.raaey.gr/energeia/en/market-monitoring/greek-wholesale-electricity-markets/electricity-prices-statistics/estimated-energy-surplus-of-the-day-ahead-market/
- RAAEY DAM energy mix: https://www.raaey.gr/energeia/en/market-monitoring/greek-wholesale-electricity-markets/electricity-prices-statistics/energymixdam/
- IBEX Bulgarian DAM prices: https://ibex.bg/markets/dam/day-ahead-prices-and-volumes-v2-0-2/
- GME Italian electricity market results: https://www.mercatoelettrico.org/en-us/Home/Results/Electricity/MGP
- ICE Dutch TTF futures: https://www.ice.com/products/27996665/Dutch-TTF-Gas-Futures/data
- EEX Market Data Hub: https://www.eex.com/en/market-data/market-data-hub

## Italy Analogue Market

- GME Spot Electricity Market: https://www.gme.it/en/mercati/MercatoElettrico/MPE.aspx
  - Italy's MGP, MI, MPEG, MSD market structure.
- GME market results: https://www.gme.it/en/
  - PUN, prices, volumes, and daily market reports.
- Terna electricity market overview: https://www.terna.it/en/electric-system/electricity-market/mercato-servizi-dispacciamento
  - MSD and MB definitions; useful analogue for ancillary-services framing.
- Terna Data Portal: https://dati.terna.it/en/
- Terna Download Center: https://dati.terna.it/en/download-center
- Terna public API catalog: https://developer.terna.it/docs/read/apis_catalog
- Terna Fast Reserve overview: https://lightbox.terna.it/en/insight/fast-reserve-pilot-project-auction
- Terna Fast Reserve information pack: https://download.terna.it/terna/Fast%20Reserve%20-%20Information%20pack_8d82fe02cbed7ad.pdf
- Terna MACSE overview: https://lightbox.terna.it/en/insight/m-for-macse
- Terna first MACSE auction results: https://download.terna.it/terna/Terna_completed_first_MACSE_auction_8de00ea13c11e89.pdf
- Terna storage technology study: https://download.terna.it/terna/Study_on_reference_technologies_for_electricity_storage_January_2025_8de0262c6cf17ee.pdf

Use Italy as an analogue for market design, storage procurement, technical assumptions, and revenue stacking. Do not use Italian BESS behavior as direct Greek training labels without clearly stating transfer-learning risk.

## Spain Analogue Market

- Red Electrica / REData electricity data: https://www.ree.es/en/datos
- OMIE market results: https://www.omie.es/en/market-results
- Spain BESS and renewable-integration studies are useful for PV-heavy price-shape and balancing-risk analogues, but should not be used as direct labels for Greek battery dispatch.

## Storage Price-Impact And Regime-Shift Sources

- CAISO 2024 battery storage report: https://www.caiso.com/documents/2024-special-report-on-battery-storage-may-29-2025.pdf
  - Use as evidence that large batteries charge heavily in solar hours and discharge in late afternoon/evening scarcity windows.
  - Use revenue decline and capacity-growth context to explain why pre-storage historical spreads can overstate future arbitrage value.
- NREL / Applied Energy storage price-impact summary: https://www.osti.gov/biblio/1845688
  - Use for the modeling caveat that price-taker storage valuations can overestimate value by missing storage's own price-suppression effect.
- Spain BESS spread-compression study: https://www.sciencedirect.com/science/article/pii/S2352484725008674
  - Use for the Greek fallback path: day-ahead bidding curves as an elasticity proxy when direct battery telemetry is unavailable.
- California empirical storage/spread study: https://www.sciencedirect.com/science/article/pii/S0140988321006241
  - Use as evidence that increasing storage penetration can reduce average intraday wholesale price spreads.
- AEMO Q4 2025 renewable/storage note: https://www.aemo.com.au/newsroom/media-release/renewables-supply-more-than-half-of-quarterly-energy-supply
  - Use as non-European operational regime-shift evidence for renewable/storage growth putting downward pressure on wholesale prices, not as a direct Greek market analogue.

Implementation stance: keep the production dashboard price-taker-only, then run a separate HEnEx aggregated-curve re-clearing experiment to test whether one METLEN-scale BESS is negligible for national DAM MCP. Do not present assumed price feedback as factual Greek post-launch prices until curve validation and observed battery bidding data support it.

## Battery And METLEN Sources

- METLEN + Karatzis 330 MW / 790 MWh standalone BESS: https://www.metlen.com/news/press-releases/strategic-agreement-between-metlen-and-karatzis-group-for-the-largest-standalone-energy-storage-unit-in-greece/
  - Model as 330 MW power and 790 MWh nameplate energy; report usable energy separately under the chosen SoC band.
  - Use 85% round-trip efficiency as the base sensitivity and 90% as the optimistic sensitivity unless stronger vendor data becomes available.
  - Treat cycle budget and degradation cost as sensitivities, not public fixed facts.
- METLEN + Tsakos 251.9 MW PV + 375 MWh storage: https://www.metlen.com/news/press-releases/strategic-partnership-between-metlen-and-tsakos-group-for-one-of-greece-s-largest-hybrid-power-generation-projects/
- MYTILINEOS/METLEN 48 MW / 96 MWh storage unit: https://www.metlen.com/news/press-releases/mytilineos-undertakes-a-48mw-96mwh-energy-storage-unit/
- NREL ATB utility-scale battery storage: https://atb.nrel.gov/electricity/2024b/utility-scale_battery_storage
- NREL 2025 utility-scale battery cost projections: https://www.nrel.gov/docs/fy25osti/93281.pdf

## Comparable GitHub Implementations

- FlexPwr BESS optimizer: https://github.com/FlexPwr/bess-optimizer
  - Closest public analogue for 96-interval BESS market scheduling and written formulation.
- NYISO battery dispatch model: https://github.com/gschivley/battery_model
  - Clean day-ahead arbitrage and annual backtest reporting reference.
- CAISO energy plus ancillary-service co-optimization: https://github.com/romilandc/battery-storage-optimization-energy-ancillary
  - Reference for future value stacking beyond DAM.

See `docs/comparable_project_analysis.md` for the scoring and implementation mapping.

## Leakage Notes

Ex-ante forecasting inputs:

- calendar/time features,
- lagged DAM prices,
- load/RES forecasts,
- weather forecasts,
- fuel/carbon daily signals,
- cross-border information available before gate closure.

Post-clearing analysis inputs:

- accepted volumes,
- final market coupling results,
- aggregated buy/sell curves,
- realized battery schedules,
- real-time SCADA data.

Keep these separate in forecasting experiments.
