# Demo Runbook

Target length: 5 minutes. Keep the future-scenario discussion short unless the
judges allow extra time.

## Recommended Headline

On 38 evaluated Greek DAM days, the scarcity-aware ensemble plus battery
optimizer earned EUR 2.968M versus EUR 2.571M for an implementable UK naive
baseline: EUR 397k uplift, 15.45% improvement, and a 78.9% daily win rate. Ridge
remains the simple model baseline/challenger, not the final champion.

Do not headline the conservative scarcity mode. It is an experimental dispatch
sensitivity; it is useful evidence, but the presentation claim should stay on the
standard scarcity-aware ensemble plus optimizer.

## Flow

### 0:00-0:45 Problem And Data Scarcity

Start with the operating problem: Greece is adding large BESS, but the market
does not yet have a long history of Greek standalone battery dispatch telemetry.
The practical question is whether we can still build a credible day-ahead
operating strategy.

Say:

> We do not need historical Greek BESS telemetry to make the first strategy
> decision. We use public Greek market, system, and weather data, then enforce
> physical battery constraints in the optimizer.

### 0:45-1:30 Public Data Inputs

Show the data stack before the model. Keep this concrete:

- HEnEx Greek Day-Ahead Market prices.
- IPTO/ADMIE load and RES forecasts.
- Weather signals where available.
- Calendar and interval features.
- Public historical price shapes for the UK naive baseline.

Emphasize that the pipeline is built for public-data reproducibility. Avoid
claiming proprietary telemetry or hidden battery operating data.

### 1:30-2:15 Battery Constraints And METLEN Asset

Introduce the asset scale and why the optimizer matters:

- METLEN-scale public demo preset: 330 MW / 790 MWh.
- Duration: about 2.39 hours.
- Round-trip efficiency: configurable, 85% in the research preset.
- SoC band: configurable, 10% to 90% in the research preset.
- Initial and terminal SoC: configurable, both 50% in the research preset.
- Degradation cost: configurable, 4 EUR/MWh throughput in the research preset.
- Cycle limit: configurable, 1.5 equivalent cycles/day in the research preset.
- No simultaneous charge and discharge.

Say:

> The optimizer is not a black box that just buys low and sells high. It respects
> power, energy, efficiency, SoC, degradation, daily cycle budget, and operating
> mode constraints.

Then clarify:

> These are adjustable battery parameters. The official 38-day evidence used the
> research preset, while the live UI can adjust parameters for the daily demo.
> Changing the live daily controls does not automatically regenerate the 38-day
> evidence.

### 2:15-3:15 Scarcity-Aware Forecast Plus Optimizer

Explain the two-stage strategy:

1. Forecast interval Greek DAM prices using live-safe public features.
2. Pass the forecast into the MILP battery optimizer.
3. Settle the resulting schedule against realized Greek DAM prices.

Keep the model claim sober:

> The model is only useful if its forecast errors translate into better dispatch.
> We therefore judge it on realized PnL against an implementable baseline, not
> on MAE alone.

Frame the final model as a scarcity-aware ensemble. Ridge remains the clean,
simple challenger because it is easy to explain and strong in the same public-data
setting, but it is no longer the final champion.

### 3:15-4:30 Evidence Tab: ML Versus UK Naive Baseline

Use the exact headline numbers:

| Metric | Result |
| --- | ---: |
| Evaluated Greek DAM days | 38 |
| Scarcity-aware ensemble realized PnL | EUR 2.968M |
| UK naive baseline realized PnL | EUR 2.571M |
| Uplift | EUR 397k |
| Uplift percentage | 15.45% |
| Daily win rate | 78.9% |

Explain the benchmark:

> The UK naive baseline is previous-day price-shape persistence, applied to the
> same Greek prices and the same METLEN-scale battery constraints. It is simple,
> implementable, and public-data-only.

Then clarify oracle:

> Oracle is not the benchmark. It sees target-day realized prices and is only an
> upper-bound diagnostic.

### 4:30-5:15 Model Credibility Caveat

Use the challenger comparison to avoid overclaiming:

- The scarcity-aware ensemble is the final presentation strategy.
- Ridge remains the simple public-data model baseline/challenger.
- ExtraTrees remains the best MAE challenger from the model comparison.
- Conservative scarcity mode is experimental and should not be the headline.
- Model rankings can change as more Greek data arrives.

Say:

> The ensemble is the current strategy because it improves realized economics
> under data scarcity. Ridge and ExtraTrees remain useful challengers for
> monitoring. We should not declare any model permanently best.

### 5:15-6:30 Future BESS Stress Test

Position the future analysis after the current result:

> Today, price-taking is acceptable as a first-BESS operating assumption. Future
> Greek BESS buildout can compress arbitrage spreads, so the strategy must be
> retrained, re-optimized, and stress-tested as penetration rises.

Use the current scenario interpretation:

| Scenario | Fixed schedule result | Redispatch result | Interpretation |
| --- | --- | --- | --- |
| Conservative | Loses about 16-17% | Can improve this sample period | Do not read as a price forecast |
| Base | Loses about 38-41% | Partially offsets compression | Better dispatch matters |
| Aggressive | Loses about 63-67% | Still materially degraded | Severe compression stress |

Say explicitly:

> These are spread-compression stress tests, not Greek price forecasts.

The latest future run used `data/processed/strategy_comparison_intervals.csv` as
input and wrote the `future_market_impact_*` outputs. Use the scenario readout as
a future-risk overlay, not as the current-performance headline.

### 6:30-7:30 Close

End with the operating loop:

1. Use public data to forecast Greek DAM prices.
2. Optimize dispatch under real battery constraints.
3. Compare against an implementable UK naive baseline.
4. Retrain forecasts and rerun the optimizer as more BESS enters.
5. Stress-test future spread compression before over-investing in today's spreads.

## Do Not Say This

- Do not say Ridge is permanently best.
- Do not say Ridge is the final champion.
- Do not say conservative scarcity mode is the headline.
- Do not say future scenario prices are forecasts.
- Do not say oracle is the benchmark.
- Do not say we trained on Greek BESS telemetry.
- Do not say the EUR 397k uplift is guaranteed out of sample.
