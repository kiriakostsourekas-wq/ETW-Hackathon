# Future BESS Market Impact

Research date: 2026-04-30.

This layer supports the scarcity-aware ensemble plus optimizer result; it should
not become the headline. It is strategic stress testing, not a forecast of Greek
prices. The final strategy story should be read in this order:

1. Today: the price-taking assumption is acceptable as a first-BESS operating
   assumption because Greece is just beginning to add large standalone batteries.
2. Current evidence: the scarcity-aware ensemble plus optimizer is the main proof
   point, benchmarked against the UK-style naive baseline on realized interval
   PnL and capture ratio. Ridge remains the simple model challenger, not the
   final champion.
3. Future: as Greek BESS penetration rises, arbitrage spreads should compress,
   so the strategy must keep retraining forecasts, rerunning the optimizer, and
   stress-testing future spread compression.

## How This Fits The Final Pitch

1. Current evidence: the scarcity-aware ensemble plus optimizer beats the UK
   naive baseline, so the first recommendation is based on observed Greek prices
   and dispatch economics.
2. Data scarcity answer: the method does not need battery telemetry. It combines
   public price data, forecasts, battery constraints, and settlement logic to
   evaluate charge/discharge decisions.
3. Future proofing: scenario stress tests show why the strategy must adapt as
   more BESS enters the Greek market. They are a risk-control layer after the
   ML+optimizer result, not a Greek price forecast.

## Hard Sourced Facts

Greek buildout and METLEN:

- METLEN and Karatzis announced a 330 MW / 790 MWh standalone BESS in Thessaly,
  expected in Q2 2026, with METLEN responsible for construction, operation, and
  maintenance through M Renewables.
  Source: https://www.metlen.com/news/press-releases/strategic-agreement-between-metlen-and-karatzis-group-for-the-largest-standalone-energy-storage-unit-in-greece/
- METLEN H1 2025 results say domestic construction progressed on another 48 MW
  of BESS. The same release reports H1 2025 third-party agreements for BESS
  totaling 0.3 GW / 1.3 GWh across Greece, Chile, Bulgaria, and the UK, plus
  0.5 GW / 0.9 GWh of PV and BESS in advanced negotiation.
  Source: https://www.metlen.com/news/financial-results/press-release-financial-results-first-half-2025/
- Greece's Ministry of Environment and Energy extended the application deadline
  for standalone electricity-storage connection requests under Ministerial
  Decision YPEN/GDE/28255/1143/13.3.2025.
  Source: https://ypen.gov.gr/paratasi-prothesmias-ypovolis-aitiseon-gia-egkatastasi-memonomenon-stathmon-apothikefsis-ilektrikis-energeias/
- IPTO/ADMIE published the list process for battery-storage requests with a
  completeness date through 2025-10-31 under the same ministerial decision.
  Source: https://www.admie.gr/en/grid/user-connection/res-producers
- ESS News reported the final Greek ministerial program as 4.7 GW of utility-scale
  standalone BESS, split between 3.8 GW on the transmission network and 900 MW
  on the distribution network.
  Source: https://www.ess-news.com/2025/03/18/greece-launches-4-7-gw-utility-scale-battery-storage-program/

Comparable market evidence:

- NREL / Applied Energy warns that price-taker arbitrage models can overestimate
  storage value when storage deployment suppresses price differentials.
  Source: https://research-hub.nlr.gov/en/publications/a-market-feedback-framework-for-improved-estimates-of-the-arbitra-2/
- A Spain-focused Energy Reports paper uses 2024 Spanish day-ahead bidding curves
  and finds that additional BESS capacity significantly reduces price spreads and
  lowers profitability for new and existing BESS.
  Source: https://www.sciencedirect.com/science/article/pii/S2352484725008674
- Terna's first Italian MACSE auction procured 10 GWh of storage for operation in
  2028, with bids more than four times demand and clearing prices below the
  reserve premium.
  Source: https://download.terna.it/terna/Terna_completed_first_MACSE_auction_8de00ea13c11e89.pdf
- Great Britain is mature enough that BESS revenue analysis now focuses on
  merchant volatility, spread compression, and Balancing Mechanism participation.
  Source: https://modoenergy.com/research/gb-battery-energy-storage-derisking-returns-revenues-great-britain-offtake-ldes-p462-q3-2025
- Spain's updated NECP target is 22.5 GW of energy storage by 2030.
  Source: https://www.energy-storage.news/spain-increases-energy-storage-target-in-necp-to-22-5gw-by-2030/
- Spain intraday evidence shows that even where spreads exist, low continuous-
  market depth can force BESS into day-ahead, balancing, and technical-constraint
  strategies rather than pure intraday algorithms.
  Source: https://modoenergy.com/research/en/spain-icm-liquidity-algorithmic-trading-bess

## Scenario Inferences

These are model assumptions, not sourced facts and not Greek price forecasts.

| Scenario | 2031 power | 2031 energy | Sourced anchor | Inference |
| --- | ---: | ---: | --- | --- |
| conservative | 1,230 MW | 4,400 MWh | METLEN 330 MW plus roughly 900 MW from supported auctions | Awarded projects plus METLEN connect; limited extra merchant buildout |
| base | 3,000 MW | 9,500 MWh | Greek 4.7 GW merchant priority-connection program plus METLEN activity | About half of merchant priority capacity reaches operation by 2031 |
| aggressive | 5,600 MW | 18,000 MWh | 4.7 GW merchant program plus auctioned capacity | Most merchant and auctioned capacity operates by 2031 |

The price-impact settings are deliberately simple:

| Scenario | Spread compression | Responsive fleet share | Depth assumption | Max interval fleet shift |
| --- | ---: | ---: | ---: | ---: |
| conservative | 12% | 25% | 1,200 MW per EUR/MWh | 8 EUR/MWh |
| base | 28% | 35% | 1,000 MW per EUR/MWh | 18 EUR/MWh |
| aggressive | 45% | 45% | 900 MW per EUR/MWh | 32 EUR/MWh |

The compression percentages are scenario parameters informed by storage economics
literature and Spain/GB/Italy analogues. They are not observed Greek outcomes.

## Input Contract

The preferred final input is:

`data/processed/strategy_comparison_intervals.csv`

Expected columns:

- `timestamp` or `delivery_date` plus `interval`
- `delivery_date`
- `interval`
- `actual_price_eur_mwh` or `dam_price_eur_mwh`
- `forecast_price_eur_mwh`
- `charge_mw`
- `discharge_mw`
- `strategy`, `model`, `benchmark`, or `baseline_method` to identify the strategy

Fallback inputs:

- `data/processed/ml_research_predictions.csv`
- `data/processed/price_taker_forecast.csv`

The runner auto-detects available files in that order when `--input` is omitted.
It normalizes `actual_price_eur_mwh` to the simulator's canonical
`dam_price_eur_mwh`, and each `model` or `strategy` group is simulated separately.

## Simulation Method

Implemented in `src/batteryhack/future_market_impact.py`.

For interval-level strategy outputs:

1. Normalize input columns from ML/comparison schemas.
2. Use the supplied `charge_mw` and `discharge_mw` schedule when present.
3. Compress each strategy/day price curve around its median:
   `future_price = median + (base_price - median) * (1 - compression)`.
4. Add a market-depth fleet response. Fleet charging uplifts low-price intervals;
   fleet discharging suppresses high-price intervals.
5. Settle the original strategy schedule on original and stressed future prices.
6. Re-optimize the same battery against future prices to estimate changed dispatch.
7. Report fixed-schedule degradation, re-optimized degradation, and dispatch change.

For daily backtest summaries without interval prices, the simulator uses a proxy:
captured spread and net revenue are scaled by the scenario compression, and the
output is marked `backtest_summary_proxy`.

Run:

```bash
PYTHONPATH=src python scripts/run_future_market_impact.py
```

Current generated outputs:

- `data/processed/future_market_impact_summary.csv`
- `data/processed/future_market_impact_intervals.csv`
- `data/processed/future_market_impact_headline.json`

As of the latest run, the script used
`data/processed/strategy_comparison_intervals.csv`. The JSON artifact records the
input path actually used.

## Headline Artifact

`future_market_impact_headline.json` is the compact presentation artifact. It is
aggregated by strategy/model and scenario using total PnL rather than averaging
daily percentages.

Top-level fields:

- `generated_at`
- `input_file`
- `preferred_input_file`
- `fallback_input_files`
- `notice`
- `rows`

Each row contains:

- `strategy_model`
- `scenario`
- `fixed_schedule_degradation_pct`
- `reoptimized_degradation_pct`
- `reoptimization_recovery_eur`
- `interpretation_label`
- `sample_days`

Interpretation labels are deterministic and intentionally conservative:

- `spread compression risk`
- `redispatch partially offsets compression`
- `redispatch improves this sample day`
- `severe compression stress`

## Current Stress Results

Using `strategy_comparison_intervals.csv` as the final strategy-comparison
interval input, headline rows across ML strategy schedules show the following
risk ranges. These figures should be used as spread-compression stress tests, not
as point forecasts for Greek prices:

| Scenario | Fixed-schedule PnL degradation | Re-optimized PnL degradation | Readout |
| --- | ---: | ---: | --- |
| conservative | About 16-17% | -11.0% to -6.8% | Fixed schedule loses value; redispatch can improve this sample period, so do not overinterpret it as a forecast |
| base | About 38-41% | 16.7% to 19.8% | Fixed schedule loses material value; redispatch partially offsets compression |
| aggressive | About 63-67% | 45.9% to 47.9% | Severe compression stress; simple arbitrage value is materially eroded |

Negative re-optimized degradation means the future-price re-optimization beats the
original forecast-driven schedule on this sample set. It should not be read as a
market forecast.

## How Future BESS Buildout Changes The Strategy

More BESS should reduce the durability of simple buy-low/sell-high spreads. Fleet
charging tends to lift solar-hour lows; fleet discharging tends to suppress evening
peaks. That compresses the spread that historical price-taker backtests monetize.

Value therefore migrates from simple arbitrage toward better forecasting,
constraints, and market selection. The strategy must know which intervals still have
enough residual spread after degradation, efficiency losses, and market depth. It
also needs to choose between DAM, intraday auctions, continuous intraday where
liquid, balancing, ancillary services, and local technical constraints.

The model should be periodically retrained because storage penetration changes the
label distribution. A forecast model trained on pre-storage or early-storage price
shapes can overstate future evening peaks, understate midday floors, and allocate
cycles to windows that no longer clear after the fleet responds.

Strategic use: the operating loop is to retrain forecasts as storage penetration
changes, rerun the optimizer under updated spread and depth conditions, and use
scenario stress tests before committing to strategies that only work on today's
spreads. This is a disciplined risk screen for BESS buildout, not a Greek price
forecast.

## Limitations

- This is not a Greek market-clearing model.
- HEnEx aggregated curves should eventually calibrate market depth directly.
- The simulator does not forecast gas, hydro, imports, curtailment, reserve prices,
  or intraday liquidity.
- The aggressive case is a warning case, not a prediction.
- Re-optimization separates market decay from stale dispatch, but it is still based
  on simplified future prices.
