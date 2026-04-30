# Judge Q&A

Use short answers first, then add detail only if asked.

## Why Ridge?

Ridge is the simple, transparent challenger. It is useful because it performs
strongly with public Greek market features and is easy to explain, but it is not
the final champion in the current story.

The final presentation strategy is the scarcity-aware ensemble plus optimizer:
EUR 2.968M on 38 evaluated Greek DAM days versus EUR 2.571M for the UK naive
baseline. Ridge remains the clean baseline/challenger for model credibility and
monitoring.

## Why The Scarcity-Aware Ensemble?

It directly answers the data-scarcity problem. Instead of betting on one model as
permanently best, it combines live-safe public-data signals and then lets the
battery optimizer enforce the operating constraints.

The current headline is EUR 397k uplift, 15.45% improvement, and a 78.9% daily
win rate versus the UK naive baseline over 38 evaluated days.

Do not use the conservative scarcity mode as the headline. It is an experimental
dispatch sensitivity, not the main production-style claim.

## Why Not A Deep Model?

The available Greek battery-dispatch evidence is still sparse. A deep model would
add complexity without enough market-specific battery telemetry to justify it.
The scarcity-aware ensemble, Ridge, and tree challengers are easier to validate
with walk-forward public data, and the economic result depends on
forecast-plus-optimizer performance, not model complexity.

Deep learning can be revisited after more Greek DAM history, BESS operations, and
market regime data accumulate.

## How Do You Handle Data Scarcity?

The strategy does not require Greek BESS telemetry. It uses public data:
HEnEx DAM prices, IPTO/ADMIE load and RES forecasts, weather and calendar
features, and explicit battery constraints.

The data-scarcity answer is to separate what must be learned from what is known:
prices are forecast from public market signals, while battery operation is
governed by physical constraints in the optimizer.

## Are You Using Future Prices?

No. The operating strategy uses forecast prices available before dispatch. The
UK naive baseline uses previous-day public Greek price shapes, with a prior-7-day
interval median fallback when needed.

The oracle uses target-day realized prices, but only as an upper-bound diagnostic.
It is not the benchmark and not an implementable strategy.

## What Is The UK Naive Baseline?

It is an implementable previous-day persistence benchmark. For each Greek target
delivery date, it copies the previous calendar day's 96 interval DAM price shape,
optimizes the same METLEN-scale battery against that naive forecast, and settles
the schedule on realized Greek DAM prices.

If the previous day is missing or incomplete, it uses the median price shape from
the most recent valid prior seven days. It uses no target-day price information.

## Why Is Oracle Not The Benchmark?

Oracle is perfect hindsight. It optimizes against realized target-day prices that
would not be known when submitting the schedule.

Use oracle to estimate the upper bound and capture ratio. Use the UK naive
baseline as the practical benchmark because it is implementable with public data.

## What Happens When Many BESS Enter Greece?

More BESS should compress simple arbitrage spreads. Fleet charging can lift low
solar-hour prices, and fleet discharging can suppress evening peaks. That means
today's spreads should not be assumed permanent.

The current future scenarios are stress tests, not Greek price forecasts:

- Conservative: fixed schedule loses about 16-17%; redispatch can improve this
  sample period, so do not overinterpret it.
- Base: fixed schedule loses about 38-41%; redispatch partially offsets
  compression.
- Aggressive: fixed schedule loses about 63-67%; severe compression stress.

The strategy implication is to keep retraining forecasts, rerun the optimizer
under updated spread conditions, and stress-test the portfolio as BESS
penetration rises.

The latest future stress run used the final
`data/processed/strategy_comparison_intervals.csv` input. It should be presented
as a future-risk overlay after the current ML+optimizer evidence.

## What Are The Battery Constraints?

The demo uses METLEN-scale assumptions:

- 330 MW power.
- 790 MWh nameplate energy.
- About 2.39 hours duration.
- 85% round-trip efficiency.
- 10% to 90% SoC operating band.
- 50% initial and terminal SoC.
- 4 EUR/MWh throughput degradation-cost sensitivity.
- 1.5 equivalent cycles per day.
- No simultaneous charge and discharge.

The public asset scale is 330 MW / 790 MWh. Some operating parameters are
hackathon defaults and should be treated as sensitivities, not public fixed
facts.

## What Should We Not Say?

- Do not say Ridge is permanently best.
- Do not say Ridge is the final champion.
- Do not say conservative scarcity mode is the headline.
- Do not say future scenario prices are forecasts.
- Do not say oracle is the benchmark.
- Do not say we trained on Greek BESS telemetry.
- Do not say the uplift is guaranteed in future market regimes.
