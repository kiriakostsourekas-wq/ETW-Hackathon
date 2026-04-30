# ML And Optimizer Pipeline Report

## Executive Summary

The final strategy is a scarcity-aware ensemble price forecaster connected to a
constraint-aware battery optimizer.

The model does not learn historical Greek battery behavior, because that telemetry
does not exist at useful scale yet. Instead, it learns next-day Greek Day-Ahead
Market price structure from public market, system, calendar, and weather signals.
The optimizer then turns the forecast price curve into a feasible battery schedule.

Official presentation headline from `strategy_comparison_headline.json`:

| Metric | Value |
| --- | ---: |
| Evaluation window | 2026-03-22 to 2026-04-29 |
| Evaluated public Greek DAM days | 38 |
| Final ML strategy | `scarcity_ensemble` |
| ML realized PnL | EUR 2,968,322 |
| UK naive baseline realized PnL | EUR 2,571,165 |
| Uplift | EUR 397,157 |
| Uplift percentage | 15.45% |
| Daily win rate vs UK naive | 78.9% |

The headline comparison is ML strategy versus the implementable UK naive baseline.
Oracle is only a hindsight upper bound and must not be presented as the benchmark.

## Problem Framing

The hackathon data-scarcity problem is mainly battery telemetry scarcity. Greece
does not yet have a mature standalone BESS operating history. The project solves
around that limitation by separating the problem into two parts:

1. Forecast market prices from public ex-ante signals.
2. Enforce battery behavior through physics and operating constraints in the
   optimizer.

That means no Greek BESS telemetry is required to produce a feasible schedule.

## End-To-End Pipeline

1. Load a continuous 15-minute public-data history.
2. Build live-safe features for each delivery interval.
3. For each target day, train only on dates strictly before that target day.
4. Forecast the 96 DAM prices for the target delivery day.
5. Send that forecast curve to the battery optimizer.
6. The optimizer chooses charge, discharge, or idle in every interval.
7. Settle the resulting schedule on realized Greek DAM prices.
8. Compare realized economics against:
   - UK naive baseline: implementable benchmark.
   - Oracle: non-implementable upper-bound diagnostic.

The central files are:

- `src/batteryhack/ml_research.py`: walk-forward ML research harness.
- `scripts/run_ml_research.py`: ML experiment CLI.
- `src/batteryhack/optimizer.py`: MILP battery scheduler.
- `src/batteryhack/baseline.py`: UK naive baseline.
- `src/batteryhack/strategy_comparison.py`: official ML-vs-baseline comparison.
- `scripts/validate_research_outputs.py`: artifact consistency check.

## Data And Features

The model target is `dam_price_eur_mwh`, the Greek DAM price for each 15-minute
interval.

The live-safe feature set includes public ex-ante signals such as:

- load forecast,
- RES forecast,
- net-load forecast,
- RES share forecast,
- weather variables,
- calendar and intraday shape features,
- premarket/system context features when available.

The feature guard in `forecasting.py` blocks post-clearing and actual target-day
columns from the live model. Examples of blocked fields include target-day DAM
price, actual load, actual RES, and other post-clearing values.

Synthetic fallback price days are excluded from target evaluation by default.
Synthetic price labels are also excluded from training by default.

## Evaluation Design

The ML backtest is chronological and no-leakage:

- For target day D, training rows satisfy `timestamp.date() < D`.
- The target day's actual DAM price is used only after scheduling, for scoring and
  settlement.
- Forecast quality is measured, but final model selection focuses on realized
  battery economics.

Metrics include:

- MAE and RMSE,
- spread-direction accuracy,
- top-quartile and bottom-quartile accuracy,
- realized net revenue,
- oracle net revenue,
- capture ratio versus oracle,
- charged/discharged MWh,
- equivalent cycles,
- captured spread.

MAE alone is not enough. A battery earns money by correctly ranking cheap charge
intervals and expensive discharge intervals. A model can have slightly worse MAE
but better dispatch value.

## Models Tried

### Interval Profile

This is the simplest shape model. It estimates historical average price by
15-minute interval and weekend/weekday structure, with a net-load adjustment when
available.

Why it is useful:

- transparent,
- hard to overfit,
- captures repeated daily price shape.

Why it was not final:

- it cannot adapt enough to changing market tightness or nonlinear system states.

### Ridge

Ridge is a regularized linear regression using imputed and standardized live-safe
features.

Why it worked surprisingly well:

- Greek DAM intraday structure is strongly driven by load, RES, net load, solar
  shape, and calendar effects.
- Ridge is stable with limited data.
- Regularization helps avoid overfitting when only a short public Greek 15-minute
  history is available.

Why it was not final:

- it was not dominant day by day.
- it underperformed the scarcity ensemble once model weighting was added.

Ridge remains the simple challenger and interpretability anchor.

### Elastic Net

Elastic Net is another regularized linear model, with an L1/L2 penalty mix.

Why we tried it:

- it can produce a sparser linear model than Ridge.
- it is useful when many features are correlated.

Why it was not final:

- it did not beat Ridge or the ensemble in realized dispatch economics.

### HistGradientBoosting

This is a nonlinear tree boosting model from scikit-learn.

Why we tried it:

- it can capture nonlinear interactions between net load, weather, time of day,
  and market context.

Why it was not final:

- useful challenger, but not the strongest aggregate PnL result.

### ExtraTrees

ExtraTrees is a random-forest-style ensemble of randomized decision trees.

Why it was strong:

- it achieved the best direct price MAE in the latest final ML run.
- it captured nonlinear feature interactions better than a linear model.

Why it was not final:

- best MAE did not translate into best battery PnL.
- the scarcity ensemble delivered higher realized revenue and capture ratio.

ExtraTrees remains the best forecast-accuracy challenger.

### Stacked Ensemble

The stacked ensemble uses base model forecasts and trains a Ridge meta-model on
recent chronological validation days.

Why we tried it:

- stacking is a natural architecture when multiple models have complementary
  strengths.

Why it was not final:

- the meta-model had too little validation data.
- it was more complex without enough evidence of improved dispatch economics.

### Scarcity Ensemble

This is the final selected ML strategy.

Base models:

- Ridge,
- ExtraTrees,
- HistGradientBoosting,
- Interval Profile.

For each target day:

1. Train each base model only on prior data.
2. Score base models on the latest prior validation days.
3. Score them by battery capture ratio versus oracle, not by MAE.
4. Convert those recent capture scores into weights.
5. Produce the target-day forecast as the weighted average of base forecasts.
6. Send the ensemble forecast into the optimizer.

Why this is the best project fit:

- It directly addresses data scarcity.
- It avoids claiming one model is permanently best.
- It adapts to whichever model recently produced better dispatch value.
- It optimizes for the economic objective instead of only price error.

Latest direct ML run:

| Model | Realized PnL | MAE | Capture vs oracle |
| --- | ---: | ---: | ---: |
| Scarcity Ensemble | EUR 2,958,360 | 20.21 | 0.811 |
| ExtraTrees | EUR 2,893,020 | 19.49 | 0.793 |
| Ridge | EUR 2,871,597 | 24.34 | 0.787 |

Pairwise direct ML result:

- Scarcity Ensemble beats Ridge by EUR 86,763 and wins 28 of 38 days.
- Scarcity Ensemble beats ExtraTrees by EUR 65,340 and wins 24 of 38 days.

### Conservative Scarcity Ensemble

This experimental variant shrinks the ensemble forecast toward the daily median on
high-disagreement days.

Why it exists:

- it is a hook for risk control when model disagreement is high.

Why it is not the headline:

- it did not consistently reduce bad-day frequency.
- it adds complexity without enough evidence yet.

## Why The Scarcity Ensemble Works

The final ensemble works because different models are good at different parts of
the problem:

- Ridge captures stable structure from net load, RES, and calendar effects.
- ExtraTrees captures nonlinear price level behavior.
- Histogram boosting captures another nonlinear view.
- Interval profile anchors the model to repeated intraday market shape.

The ensemble weights these models by recent dispatch value. That is important
because the battery does not care about all price errors equally. It cares most
about identifying the intervals where charging and discharging create value after
efficiency losses and degradation cost.

## UK Naive Baseline

The benchmark is `uk_naive_baseline`.

It is intentionally simple and implementable:

1. Copy the previous calendar day's Greek DAM price shape interval by interval.
2. If the previous day is unavailable or incomplete, use a prior-7-day interval
   median fallback.
3. Optimize the same battery against that naive forecast.
4. Settle the schedule on realized Greek DAM prices.

This is the correct benchmark because it uses no target-day prices and no
hindsight. It is a realistic fallback strategy under data scarcity.

## Optimizer Logic

The optimizer is a mixed-integer linear program in `optimizer.py`.

For every interval, it decides:

- charge power in MW,
- discharge power in MW,
- state of charge in MWh,
- optional binary mode variable to prevent simultaneous charge and discharge.

The objective is to maximize net value. In implementation, SciPy's MILP solver
minimizes cost, so the objective is written as:

- charging cost = price paid for energy plus degradation cost,
- discharging value = negative cost from selling energy minus degradation cost,
- net revenue = gross arbitrage revenue minus degradation cost.

The optimizer accounts for round-trip efficiency by splitting it into charge and
discharge efficiency terms.

## Battery Parameters

METLEN `330 MW / 790 MWh` is the public-scale demo preset. The operating
constraints are explicit inputs to `BatteryParams`, so they can be changed for
sensitivity testing instead of being fixed hidden assumptions.

The official 38-day evidence used the research preset:

| Parameter | Value |
| --- | ---: |
| Power | 330 MW |
| Energy capacity | 790 MWh |
| Duration | about 2.39 hours |
| Round-trip efficiency | 85% |
| Minimum SoC | 10% |
| Maximum SoC | 90% |
| Initial SoC | 50% |
| Terminal SoC | 50% |
| Degradation cost | EUR 4/MWh throughput |
| Daily equivalent-cycle cap | 1.5/day in official research artifacts |
| Single-mode enforcement | enabled |

The SoC band, round-trip efficiency, initial SoC, terminal SoC, equivalent-cycle
cap, and degradation cost are configurable sensitivity parameters. The live
presentation UI can adjust these parameters for a daily demo request. That live
daily change does not change the official 38-day research headline unless the ML
research and strategy-comparison artifacts are regenerated with the new
parameter preset.

## Optimizer Constraints

The optimizer enforces:

- charge power between 0 and max MW,
- discharge power between 0 and max MW,
- state of charge between min and max SoC,
- initial SoC fixed,
- terminal SoC fixed,
- energy balance across intervals,
- round-trip efficiency losses,
- optional daily cycle cap,
- optional no simultaneous charge/discharge.

The terminal SoC constraint matters because it prevents the optimizer from
artificially draining the battery at the end of the day to inflate revenue.

The cycle cap and degradation cost matter because they prevent unrealistic
over-trading that would look profitable in pure price arbitrage but damage the
battery.

## Official Comparison Chain

The official presentation result is not taken directly from `ml_research_paired_uplift.csv`.

The authoritative chain is:

1. ML daily/prediction artifacts.
2. `scripts/run_strategy_comparison.py`.
3. UK naive baseline over the same delivery-date window.
4. `data/processed/strategy_comparison_headline.json`.

This matters because the ML paired-uplift artifact is for model-to-model
comparison. The UK baseline comparison must aggregate the two UK baseline methods
over all matched target days.

## Current Caveat

There are two related but slightly different ML artifact families in the workspace:

- `ml_research_summary.csv`: latest direct three-model ML run, where the scarcity
  ensemble total is EUR 2.958M.
- `strategy_comparison_headline.json`: official presentation comparison, where the
  scarcity ensemble total is EUR 2.968M against the UK naive baseline.

Both support the same conclusion: Scarcity Ensemble is the best project strategy.
For slides, demo, and submission narrative, use `strategy_comparison_headline.json`
as the source of truth.

## What To Say In The Presentation

Use this wording:

> We forecast Greek DAM prices from public live-safe features, then pass the
> forecast into a physical battery optimizer. The final model is a scarcity-aware
> ensemble that weights Ridge, tree models, and an interval profile by recent
> battery capture value, not just price MAE. This lets the strategy adapt under
> data scarcity without needing Greek BESS telemetry.

Avoid saying:

- "The model learned Greek battery behavior."
- "Oracle is our benchmark."
- "Future BESS scenarios are price forecasts."
- "Ridge is the final champion."
- "The EUR 397k uplift is guaranteed out of sample."
