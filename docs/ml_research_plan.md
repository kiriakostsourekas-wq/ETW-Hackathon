# ML Research Plan

## Purpose

The production forecast path should stay simple enough for the dashboard and registry, but the
METLEN-scale BESS case needs a deeper model research harness. The research harness in
`src/batteryhack/ml_research.py` is designed to compare forecasting candidates over many public
Greek DAM target days, then translate forecast quality into realized price-taking dispatch PnL.

## Chronological Evaluation

The backtest is walk-forward by delivery date:

1. Load a continuous 15-minute feature table.
2. For each target day, train only on rows where `timestamp.date() < target_date`.
3. By default, drop target days marked `synthetic price fallback`.
4. By default, drop synthetic fallback price labels from the training set too.
5. Fit every candidate independently on the same prior history.
6. Forecast the target day's 96 HEnEx DAM MCP intervals.
7. Optimize one price-taking BESS schedule on forecast prices.
8. Settle that same schedule on published target-day DAM prices.
9. Compare realized revenue with an oracle schedule optimized on actual target-day prices.

The target day's `dam_price_eur_mwh` is used only for scoring and settlement. Live-safe feature
selection reuses the existing `candidate_feature_columns()` guard, which excludes post-clearing and
actual columns.

## Candidate Models

Current candidates use only the available project dependencies: `pandas`, `numpy`, `scipy`, and
`scikit-learn`.

- `interval_profile`: average historical price by weekend flag and 15-minute interval, with the
  existing net-load adjustment when available.
- `ridge`: imputed, standardized live-safe features with RidgeCV.
- `elastic_net`: imputed, standardized live-safe features with a sparse linear penalty.
- `hist_gradient_boosting`: scikit-learn histogram gradient boosting regressor.
- `extra_trees`: scikit-learn ExtraTrees regressor as the random-forest-style challenger.
- `stacked_ensemble`: chronological stack of ridge, histogram boosting, and extra trees. It trains
  a Ridge meta-model on the latest prior validation days only; if there is not enough meta data it
  falls back to an average ensemble of trainable base models.

XGBoost is implemented as an optional research candidate only. It is not part of
the default model list or the official submission headline. Future candidates
worth documenting, not adding yet, are LightGBM, quantile gradient boosting, and
weather-regime or curve-depth specialists.

## Metrics

Each model/day row includes:

- price MAE and RMSE,
- spread-direction accuracy,
- top-quartile and bottom-quartile accuracy,
- forecast-objective BESS revenue,
- realized DAM settlement revenue,
- oracle DAM revenue,
- capture ratio versus oracle,
- charged/discharged MWh, equivalent cycles, and captured spread.

The interval-level prediction output keeps `delivery_date`, `timestamp`, `interval`, `model`,
actual price, forecast price, and dispatch columns so later agents can compare the same dates
against the UK naive baseline or other benchmarks.

## CLI

Run a research backtest with:

```bash
PYTHONPATH=src python3 scripts/run_ml_research.py \
  --start 2026-04-01 \
  --end 2026-04-22 \
  --min-train-days 14 \
  --max-days 10
```

Default outputs are written under `data/processed/`:

- `ml_research_summary.csv`
- `ml_research_daily.csv`
- `ml_research_predictions.csv`
- `ml_research_skipped_days.csv`
- `ml_research_assumptions.json`
- `ml_research_daily_winners.csv`
- `ml_research_model_stability.csv`
- `ml_research_paired_uplift.csv`

Paired uplift uses `--primary-model` when provided. If it is omitted, the CLI selects the
best total-realized-PnL model from the current run. UK baseline rows are not included by
default. To include them, pass `--uk-baseline-path` pointing to a full same-window baseline
CSV that covers every evaluated ML target date; one-day smoke-test baselines are rejected.

Feature ablation smoke tests can be run with:

```bash
PYTHONPATH=src python scripts/run_ml_research.py \
  --ablation-only \
  --history-start 2026-04-01 \
  --start 2026-04-22 \
  --end 2026-04-26 \
  --min-train-days 14 \
  --ablation-model ridge \
  --ablation-summary-output ml_research_ablation_summary.csv
```

Use `--history-start` to give the first target day more historical public labels than the minimum.
Use `--include-synthetic-targets` only for demo or resilience testing; public-price research should
leave it off.

## Empirical Results

The final submission evidence uses the scarcity-aware ensemble run and the
separate same-window strategy-comparison artifact. The headline benchmark is not
derived from one-day UK baseline smoke files or oracle revenue.

Final ML research run:

```bash
PYTHONPATH=src python scripts/run_ml_research.py \
  --history-start 2026-03-01 \
  --start 2026-03-22 \
  --end 2026-04-29 \
  --min-train-days 14 \
  --models ridge,extra_trees,scarcity_ensemble \
  --summary-output ml_research_summary.csv \
  --daily-output ml_research_daily.csv \
  --predictions-output ml_research_predictions.csv \
  --skipped-output ml_research_skipped_days.csv \
  --assumptions-output ml_research_assumptions.json \
  --daily-winners-output ml_research_daily_winners.csv \
  --model-stability-output ml_research_model_stability.csv \
  --paired-uplift-output ml_research_paired_uplift.csv
```

Source summary:

- Loaded dates: 2026-03-01 through 2026-04-29, 60 calendar days.
- Public-price source days: 59.
- Synthetic-price source days: 1.
- Evaluated target days: 38 of 39 requested target days.
- Skipped target day: 2026-03-29, marked `synthetic target prices`.
- Optional source gaps: 109 unavailable optional inputs across the loaded window.

Final ML model table:

| Model | MAE EUR/MWh | Total realized EUR | Capture vs oracle | Mean daily capture |
| --- | ---: | ---: | ---: | ---: |
| scarcity ensemble | 20.21 | 2,958,360 | 0.811 | 0.806 |
| extra trees | 19.49 | 2,893,020 | 0.793 | 0.788 |
| ridge | 24.34 | 2,871,597 | 0.787 | 0.776 |

Findings:

- The scarcity ensemble is the final ML research leader by realized PnL and
  aggregate capture in the final three-model run.
- ExtraTrees remains the strongest forecast-MAE challenger.
- Ridge remains a useful simple baseline/challenger, not the final champion.
- MAE alone is not enough for dispatch model selection. Across daily rows,
  realized value depends on ranking low-price charge intervals and high-price
  discharge intervals, not just reducing level error.

Credibility diagnostics from the same run:

| Diagnostic | Result |
| --- | ---: |
| Scarcity ensemble minus Ridge total PnL | 86,763 EUR |
| Scarcity ensemble minus Ridge mean daily PnL | 2,283 EUR/day |
| Scarcity ensemble minus Ridge median daily PnL | 2,523 EUR/day |
| Scarcity ensemble daily wins vs Ridge | 28 of 38 |
| Scarcity ensemble minus ExtraTrees total PnL | 65,340 EUR |
| Scarcity ensemble minus ExtraTrees mean daily PnL | 1,719 EUR/day |
| Scarcity ensemble minus ExtraTrees median daily PnL | 748 EUR/day |
| Scarcity ensemble daily wins vs ExtraTrees | 24 of 38 |

Model-selection stability:

| Criterion | Winner | Runner-up | Margin |
| --- | --- | --- | ---: |
| Total realized PnL | scarcity_ensemble | extra_trees | 65,340 EUR |
| Mean daily PnL | scarcity_ensemble | extra_trees | 1,719 EUR/day |
| MAE | extra_trees | scarcity_ensemble | 0.72 EUR/MWh lower |
| Top-quartile accuracy | scarcity_ensemble | extra_trees | 0.016 |
| Bottom-quartile accuracy | scarcity_ensemble | extra_trees | 0.003 |
| Capture ratio | scarcity_ensemble | extra_trees | 0.018 |
| Daily PnL winner count | scarcity_ensemble | extra_trees | 16 vs 13 days |

Same-window UK benchmark:

```bash
PYTHONPATH=src python scripts/run_strategy_comparison.py \
  --ml-daily ml_research_scarcity_daily.csv \
  --ml-predictions ml_research_scarcity_predictions.csv \
  --models scarcity_ensemble
```

The authoritative headline is `strategy_comparison_headline.json`: Scarcity
Ensemble EUR 2.968M versus UK naive EUR 2.571M, EUR 397k uplift, 15.45%
improvement, and 78.9% win rate over 38 Greek DAM days. The oracle remains only
an upper-bound diagnostic. The default `ml_research_*` files hold the final
three-model diagnostic run; the validated release headline currently uses the
`ml_research_scarcity_*` artifact set.

Ridge feature ablation smoke test, 2026-04-22 through 2026-04-26:

| Ridge feature set | MAE EUR/MWh | Total realized EUR | Capture vs oracle |
| --- | ---: | ---: | ---: |
| load/RES/net-load only | 24.83 | 485,485 | 0.799 |
| all live-safe features | 29.92 | 444,542 | 0.732 |
| calendar only | 28.67 | 430,135 | 0.708 |
| weather only | 32.07 | 389,367 | 0.641 |

The ablation is only a five-day smoke, not a model-selection study. It does explain why Ridge can
be strong: Greek DAM intraday shape is heavily driven by calendar, solar/load shape, RES, and
net-load tightness. A regularized linear model can rank charge/discharge windows well when those
drivers dominate. Extra trees improve level error on the wider run, but dispatch value depends on
correctly ranking the tails, especially low-price charge intervals and high-price discharge
intervals. That is why MAE and PnL disagree.

Current evidence is not final proof. Production-grade model selection needs more public target
months, paired confidence intervals, regime splits, and a matched UK-naive comparison over the same
dates and battery assumptions. Until then, presentation language should say:

> The scarcity-aware ensemble is the current March-April public Greek DAM
> strategy leader versus the implementable UK naive baseline. Ridge remains a
> strong simple challenger and helps explain why regularized public-data models
> can be competitive, but it is not the final champion.

## Scarcity-Aware Ensemble Prototype

The prototype candidate is `scarcity_ensemble`. It combines:

- `ridge`,
- `extra_trees`,
- `hist_gradient_boosting`,
- `interval_profile`.

For each target day, the ensemble runs those base models on the most recent prior validation days
and weights the target-day forecasts by validation capture ratio, not MAE. It also writes interval
diagnostics:

- `model_disagreement_eur_mwh`,
- raw ensemble forecast,
- each base model forecast,
- each base model weight.

Optional experimental variants are kept outside the headline path. The
`scarcity_ensemble_conservative` variant shrinks forecast deviations toward the
daily median on high-disagreement days. The `scarcity_ensemble_xgboost` variant
adds an optional XGBoost base learner when the `xgboost` package is installed.
Neither variant is part of the official submission claim.

Run completed:

```bash
PYTHONPATH=src python scripts/run_ml_research.py \
  --history-start 2026-03-01 \
  --start 2026-03-22 \
  --end 2026-04-29 \
  --min-train-days 14 \
  --models ridge,extra_trees,scarcity_ensemble \
  --summary-output ml_research_summary.csv \
  --daily-output ml_research_daily.csv \
  --predictions-output ml_research_predictions.csv \
  --skipped-output ml_research_skipped_days.csv \
  --assumptions-output ml_research_assumptions.json
```

Top-line result:

| Model | MAE EUR/MWh | Total realized EUR | Capture vs oracle | Mean daily capture |
| --- | ---: | ---: | ---: | ---: |
| scarcity ensemble | 20.21 | 2,958,360 | 0.811 | 0.806 |
| extra trees | 19.49 | 2,893,020 | 0.793 | 0.788 |
| ridge | 24.34 | 2,871,597 | 0.787 | 0.776 |

Pairwise:

| Comparison | Total uplift | Mean daily uplift | Median daily uplift | Wins |
| --- | ---: | ---: | ---: | ---: |
| scarcity ensemble vs ridge | 86,763 EUR | 2,283 EUR/day | 2,523 EUR/day | 28 of 38 |
| scarcity ensemble vs extra trees | 65,340 EUR | 1,719 EUR/day | 748 EUR/day | 24 of 38 |

The final paired-uplift output does not include UK baseline rows, because no explicit full
same-window UK baseline path was passed. The old one-day `uk_naive_baseline_test.csv` is
intentionally not used by default.

Risk-tail view:

| Model | Worst daily EUR | p10 daily EUR | Capture < 0.60 days | Capture < 0.70 days |
| --- | ---: | ---: | ---: | ---: |
| scarcity ensemble | 25,392 | 48,989 | 5 | 7 |
| extra trees | 22,420 | 47,619 | 7 | 8 |
| ridge | 21,944 | 42,991 | 4 | 8 |

Interpretation:

- The standard scarcity ensemble improves aggregate PnL and median daily uplift versus Ridge.
- It wins most paired days against Ridge and improves MAE, quartile accuracy, and capture.
- Against this three-model run, scarcity improves the worst daily PnL floor, p10 daily PnL,
  and sub-0.70 capture count. It does not reduce sub-0.60 capture days versus Ridge.
- Current recommendation: headline `scarcity_ensemble` as the validated
  PnL/capture improvement and keep optional variants as research extensions.

For the presentation benchmark, the authoritative UK comparison is not any
`ml_research_*paired_uplift.csv` row. Build `strategy_comparison_headline.json` from
`ml_research_scarcity_daily.csv` and `ml_research_scarcity_predictions.csv` with
`--models scarcity_ensemble`; that artifact aggregates all UK naive baseline method rows and is
the official ML-versus-UK headline.

## Limitations And Required Full Runs

This harness is ready for deterministic unit tests and cached/public HEnEx runs, but the research is
not complete until we run a longer public-data study.

Still needed:

- Run at least several months of public HEnEx target days once the raw data cache is populated.
- Compare against the UK naive baseline on identical target-day rows and battery assumptions.
- Report model stability by month, weekday/weekend, high-renewables days, and price-spike days.
- Add confidence intervals or paired tests for revenue/capture differences, not only sorted summary
  tables.
- Audit feature availability timestamps for optional HEnEx/IPTO inputs before calling any optional
  column live-tradable.
- Keep market-impact results separate from this price-taking forecast harness; capture ratios here
  assume no price impact.
