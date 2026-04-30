# Strategy Comparison Report

## Current Presentation Headline

Current comparison window: `2026-03-22` to `2026-04-29`, with 38 evaluated Greek
DAM delivery days.

| Metric | Current result |
| --- | ---: |
| Presentation strategy | scarcity-aware ensemble + optimizer |
| Strategy realized PnL | EUR 2,968,322 |
| UK naive baseline realized PnL | EUR 2,571,165 |
| Uplift versus UK naive baseline | EUR 397,157 |
| Uplift percentage | 15.45% |
| Win rate versus UK naive baseline | 78.9% |

This is the presentation comparison: our scarcity-aware Greek forecast plus MILP
optimizer strategy versus an implementable UK-style naive baseline on the same
Greek prices and the same METLEN-scale battery assumptions. The oracle is only
an upper-bound diagnostic because it optimizes with target-day realized prices
that would not be available when scheduling.

Under data scarcity, this result does not require Greek BESS telemetry. The workflow uses public
market, system, and weather signals to forecast Greek DAM prices, then uses the MILP optimizer to
enforce power, energy, efficiency, SoC, terminal SoC, degradation, cycle, and no-simultaneous-mode
battery constraints. The UK naive baseline remains a practical fallback benchmark: it can be
implemented with yesterday's public Greek DAM price shape, and it is the benchmark we must beat.

Ridge remains the simple model baseline/challenger, not the final champion.
Conservative scarcity mode is experimental and should not be used as the
headline even when it is close to, or slightly above, the standard ensemble on
this sample.

## Run After Agent 1 Outputs Exist

Agent 1 should first create the validated scarcity artifact set:

- `data/processed/ml_research_scarcity_daily.csv`
- `data/processed/ml_research_scarcity_predictions.csv` when interval-level comparison is wanted

Reproduce the current ML research outputs with:

```bash
PYTHONPATH=src python scripts/run_ml_research.py \
  --history-start 2026-03-01 \
  --start 2026-03-22 \
  --end 2026-04-29 \
  --min-train-days 14 \
  --models ridge,scarcity_ensemble,scarcity_ensemble_conservative \
  --summary-output ml_research_scarcity_summary.csv \
  --daily-output ml_research_scarcity_daily.csv \
  --predictions-output ml_research_scarcity_predictions.csv \
  --skipped-output ml_research_scarcity_skipped_days.csv \
  --assumptions-output ml_research_scarcity_assumptions.json \
  --daily-winners-output ml_research_scarcity_daily_winners.csv \
  --model-stability-output ml_research_scarcity_model_stability.csv \
  --paired-uplift-output ml_research_scarcity_paired_uplift.csv
```

`scarcity_ensemble_conservative` is kept as an experimental risk-control
comparison and must not be selected as the headline.

Then build the strategy comparison with:

```bash
PYTHONPATH=src python scripts/run_strategy_comparison.py \
  --ml-daily ml_research_scarcity_daily.csv \
  --ml-predictions ml_research_scarcity_predictions.csv \
  --models scarcity_ensemble
```

By default the script:

- reads the requested Agent 1 daily ML rows from `data/processed/`,
- reads the requested Agent 1 interval predictions when present,
- runs the UK naive baseline on the same Greek delivery-date window,
- uses `BATTERY_PRESETS[METLEN_PRESET_NAME].to_params()` for the baseline battery assumptions,
- writes the comparison outputs under `data/processed/`.

Outputs:

- `strategy_comparison_daily.csv`
- `strategy_comparison_intervals.csv` when interval inputs are available
- `strategy_comparison_summary.csv`
- `strategy_comparison_headline.json`

Before a demo, validate artifact consistency with:

```bash
PYTHONPATH=src python scripts/validate_research_outputs.py
```

This validator is intentionally strict. It fails if required processed artifacts are missing,
if the headline does not reconcile with the strategy summary, if the UK baseline method rows
are not aggregated, if date windows mismatch, if the official headline is not
`scarcity_ensemble`, or if `scarcity_ensemble_conservative` is selected as the headline.
When `future_market_impact_headline.json` exists, validation also requires that it was built
from `data/processed/strategy_comparison_intervals.csv`, contains `ml_scarcity_ensemble`, and
has conservative, base, and aggressive scenarios over the same 38 evaluated days. It warns, but
does not fail, when stale ML paired-uplift artifacts lack a full-window UK-baseline row, because
the authoritative headline comes from `strategy_comparison_headline.json`.

Use `--start` and `--end` to force a smaller date window. Use `--baseline-daily` only when
a precomputed UK naive baseline should be consumed instead of rerun.

## Headline JSON

The headline artifact is designed for the presentation's top-line comparison. It contains:

```text
date_window
evaluated_days
best_model
best_ml_strategy
best_ml_by_total_realized_net_revenue_eur
best_ml_by_average_capture_ratio_vs_oracle
best_ml_by_forecast_mae_eur_mwh
uk_baseline
uk_baseline_total_pnl_eur
ml_total_pnl_eur
uplift_eur
uplift_pct
win_rate_vs_uk_baseline
average_capture_ratio_vs_oracle
battery_assumptions
```

Read `best_model`, `ml_total_pnl_eur`, `uk_baseline_total_pnl_eur`, `uplift_eur`,
`uplift_pct`, and `win_rate_vs_uk_baseline` as the final scarcity-ensemble benchmark
numbers. The nested
`uk_baseline` object aggregates all UK naive method rows, so days that used previous-day
persistence and days that used the prior-7-day median fallback are counted together. The
nested best-strategy objects preserve the alternative winners by oracle capture and forecast
MAE, because the model with best economics does not have to be the model with the lowest
price error.

If `--headline-output some_name.csv` is used, the script writes a one-row flattened version
instead of JSON.

## Benchmark Interpretation

The benchmark is the UK-style naive previous-day persistence strategy applied to Greek DAM
prices and the same METLEN-scale battery assumptions. This is the main comparison for the
project story.

The oracle is not the benchmark. It is an upper-bound diagnostic that optimizes against
target-day realized prices, which are unavailable at decision time. Use oracle capture to
explain how much achievable perfect-foresight value a strategy captured, but use uplift
versus `uk_naive_baseline` as the practical ML-vs-naive headline.

## Artifact Authority

Use `data/processed/ml_research_scarcity_summary.csv` for the final ML research table and
`data/processed/strategy_comparison_headline.json` for the UK-baseline total and
official ML-versus-UK benchmark. The strategy comparison artifact is built from
the normalized strategy comparison table and aggregates all `uk_naive_baseline`
method rows before calculating baseline PnL and ML uplift.

Do not use ML paired-uplift CSVs for the headline UK comparison. They are
model-vs-model diagnostics unless a full same-window UK baseline path is passed
explicitly. The authoritative UK comparison is
`strategy_comparison_headline.json`.

## API Evidence Note

`src/batteryhack/api_server.py` should derive the preferred future-stress
strategy from `strategy_comparison_headline.json` when the artifact is present.
That keeps the dashboard aligned with the official `ml_scarcity_ensemble`
headline while leaving future scenarios framed as stress tests.
