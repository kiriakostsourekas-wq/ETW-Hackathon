# Research Sources

This file tracks sources we can cite in code comments, docs, notebooks, and slides.

## Greece Market And System Data

- HEnEx Day-Ahead Market publications: https://www.enexgroup.gr/en/web/guest/markets-publications-el-day-ahead-market
  - Use for DAM Results, ResultsSummary, aggregated curves, and pre-market files.
  - Direct ResultsSummary pattern: `https://www.enexgroup.gr/documents/20126/366820/YYYYMMDD_EL-DAM_ResultsSummary_EN_v##.xlsx`
- IPTO/ADMIE market statistics API: https://www.admie.gr/en/market/market-statistics/file-download-api
  - Use for load forecasts, RES forecasts, SCADA load/RES, imports/exports.
- Open-Meteo API docs: https://open-meteo.com/en/docs
  - Use for weather predictors: radiation, cloud cover, wind, temperature.
- ENTSO-E Transparency Platform API guide: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide_prod_backup_06_11_2024.html
  - Use as fallback/cross-check for price, load, generation, and cross-border signals.

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

## Battery And METLEN Sources

- METLEN + Karatzis 330 MW / 790 MWh standalone BESS: https://www.metlen.com/news/press-releases/strategic-agreement-between-metlen-and-karatzis-group-for-the-largest-standalone-energy-storage-unit-in-greece/
- METLEN + Tsakos 251.9 MW PV + 375 MWh storage: https://www.metlen.com/news/press-releases/strategic-partnership-between-metlen-and-tsakos-group-for-one-of-greece-s-largest-hybrid-power-generation-projects/
- MYTILINEOS/METLEN 48 MW / 96 MWh storage unit: https://www.metlen.com/news/press-releases/mytilineos-undertakes-a-48mw-96mwh-energy-storage-unit/
- NREL ATB utility-scale battery storage: https://atb.nrel.gov/electricity/2024b/utility-scale_battery_storage
- NREL 2025 utility-scale battery cost projections: https://www.nrel.gov/docs/fy25osti/93281.pdf

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
