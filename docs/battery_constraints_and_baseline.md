# Battery Constraints And UK Naive Baseline

## Comparison Story

The project comparison is the Greek ML optimizer strategy versus a naive UK-style benchmark applied to the same Greek Day-Ahead Market data. The oracle dispatch is only a sanity-check upper bound because it optimizes against realized target-day Greek DAM prices.

The baseline must therefore use:

- the same Greek target delivery dates as the ML run,
- the same realized Greek DAM settlement prices,
- the same `BatteryParams`,
- the same optimizer constraints,
- no target-day price information when building its forecast.

## UK Naive Benchmark

The named baseline is `uk_naive_baseline` with method `uk_naive_previous_day_persistence`.

For each target delivery date, the benchmark copies the previous calendar day's 96 public Greek DAM prices interval-by-interval and optimizes the battery against that naive forecast. This is the intended UK-style persistence benchmark already present in the codebase, renamed and documented rather than replaced with an unrelated method.

If the previous day is missing, synthetic, incomplete, duplicated, or has missing prices, the fallback method is `uk_naive_prior_7_day_interval_median`. It uses the interval median over the most recent valid public-price days before the target date. The target date and all later dates are filtered out before either method is built.

Implementation entry points:

- `build_uk_naive_price_forecast(...)`
- `run_uk_naive_self_schedule_baseline(...)`
- `run_uk_naive_baseline_backtest(...)`
- `scripts/baseline_smoke.py`

Backward-compatible `run_persistence_*` aliases remain available, but new benchmark outputs use the UK-naive names.

## Output Contract

The baseline CSV is designed to be joined to ML daily results on
`delivery_date`. If the ML run emits one row per model per day, keep
`delivery_date` as the join key and use each side's method/model column to
identify the strategy.

Required comparison columns:

| Column | Meaning |
| --- | --- |
| `delivery_date` | Greek DAM delivery date, ISO format. |
| `benchmark` | Baseline family, currently `uk_naive_baseline`. |
| `baseline_method` | Exact baseline method used for the day. |
| `forecast_mae_eur_mwh` | Forecast MAE versus realized Greek DAM price. |
| `forecast_rmse_eur_mwh` | Forecast RMSE versus realized Greek DAM price. |
| `forecast_spread_direction_accuracy` | Directional spread score from the shared forecast metric helper. |
| `realized_net_revenue_eur` | Baseline schedule settled against realized Greek DAM prices after degradation cost. |
| `oracle_net_revenue_eur` | Same BatteryParams optimized against realized Greek DAM prices. |
| `capture_ratio_vs_oracle` | Realized baseline net revenue divided by oracle net revenue. |
| `realized_charged_mwh` | Total AC charge energy. |
| `realized_discharged_mwh` | Total AC discharge energy. |
| `realized_equivalent_cycles` | Discharged MWh divided by nameplate capacity MWh. |
| `realized_captured_spread_eur_mwh` | Average discharge price minus average charge price. |

The baseline also keeps prefixed compatibility columns such as `baseline_realized_net_revenue_eur` and `baseline_capture_ratio_vs_oracle`.

## METLEN Demo Preset And Research Parameters

METLEN-scale defaults are centralized in `src/batteryhack/presets.py` and converted to `BatteryParams` through `BATTERY_PRESETS[METLEN_PRESET_NAME].to_params()`.

METLEN `330 MW / 790 MWh` is the public-scale demo preset. The official 38-day
evidence used the research preset below:

| Parameter | Default |
| --- | ---: |
| Power | 330 MW |
| Nameplate energy | 790 MWh |
| Duration | 2.39 h |
| Round-trip efficiency | 85% |
| Minimum SoC | 10% |
| Maximum SoC | 90% |
| Initial SoC | 50% |
| Terminal SoC | 50% |
| Degradation cost | 4 EUR/MWh throughput |
| Cycle limit | 1.5 equivalent cycles/day |
| Simultaneous charge/discharge | Disabled by default through `enforce_single_mode=True` |

The SoC band, round-trip efficiency, initial SoC, terminal SoC, cycle budget,
and degradation cost remain configurable sensitivity parameters, not public
fixed facts. The METLEN public project scale is the 330 MW / 790 MWh asset;
operating assumptions are hackathon research defaults layered on top of that
public scale.

The live UI can adjust battery parameters for a single daily demo run. Those
live daily controls do not automatically regenerate the official 38-day research
evidence; to change the headline comparison, rerun the ML research and strategy
comparison artifacts with the intended parameter preset.

## Constraint Audit

The optimizer in `src/batteryhack/optimizer.py` is parameterized through `BatteryParams`:

- Power: charge and discharge MW are each bounded by `power_mw`.
- Capacity: SoC is represented in MWh and bounded by percentages of `capacity_mwh`.
- Efficiency: charge and discharge each use the square root of round-trip efficiency, so a full charge-discharge path applies the configured round-trip value.
- Minimum/maximum SoC: enforced for every SoC state, including initial and terminal states.
- Initial/terminal SoC: enforced as equality constraints at the start and end of each optimized day.
- Degradation: modeled as a non-negative EUR/MWh throughput cost on charge plus discharge.
- Cycle limit: optional daily equivalent-cycle cap based on discharged MWh divided by nameplate MWh.
- No simultaneous charge/discharge: enforced by default with binary mode variables when `enforce_single_mode=True`.

Parameter validation rejects invalid SoC bands, initial/terminal SoC outside the band, negative degradation, negative cycle limits, non-positive power/capacity, invalid efficiency, empty market frames, and non-positive time-step sizes.

## Smoke Command

Run the baseline over the same default March Greek target window used by the ML smoke simulation:

```bash
PYTHONPATH=src python3 scripts/baseline_smoke.py
```

To compare a different ML run, pass the same `--history-start`, `--start`, `--end`, synthetic-data policy, and METLEN preset-derived `BatteryParams`.

## Strategy Comparison Layer

Once `data/processed/ml_research_scarcity_daily.csv` exists, run:

```bash
PYTHONPATH=src python scripts/run_strategy_comparison.py \
  --ml-daily ml_research_scarcity_daily.csv \
  --ml-predictions ml_research_scarcity_predictions.csv \
  --models scarcity_ensemble
```

The script consumes scarcity-ensemble daily rows and uses
`ml_research_scarcity_predictions.csv` when it is present. It runs the UK naive baseline over
the same delivery-date window with `BATTERY_PRESETS[METLEN_PRESET_NAME].to_params()`,
unless a precomputed baseline CSV is passed with `--baseline-daily`.

Outputs:

- `data/processed/strategy_comparison_daily.csv`
- `data/processed/strategy_comparison_intervals.csv` when interval inputs are available
- `data/processed/strategy_comparison_summary.csv`
- `data/processed/strategy_comparison_headline.json`

Daily schema:

```text
delivery_date
strategy
model_or_method
forecast_mae_eur_mwh
forecast_rmse_eur_mwh
spread_direction_accuracy
realized_net_revenue_eur
oracle_net_revenue_eur
capture_ratio_vs_oracle
realized_charged_mwh
realized_discharged_mwh
realized_equivalent_cycles
realized_captured_spread_eur_mwh
```

Strategy names are `ml_<model name>` for ML strategies and
`uk_naive_baseline` for the benchmark. Summary rows report total PnL, average
PnL/day, average oracle capture, win-rate versus the UK baseline, and total
uplift versus the UK baseline using only shared delivery dates.

## Current Comparison Evidence

The current presentation headline covers `2026-03-22` to `2026-04-29`, with 38 evaluated
Greek DAM delivery days. The official ML strategy is `scarcity_ensemble`: EUR 2,968,322
realized PnL versus EUR 2,571,165 for the UK naive baseline, or EUR 397,157 uplift
and 15.45% improvement. The ML strategy wins 78.9% of shared delivery days.

This is the practical benchmark result. Oracle revenue remains an upper-bound diagnostic only,
because it uses realized target-day prices that would not be known at schedule time.
