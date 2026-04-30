# Submission Checklist

## GitHub / Source Code

- Confirm `README.md` contains the final launch, validation, and reproduction
  commands.
- Run `PYTHONPATH=src python scripts/validate_research_outputs.py`.
- Run `PYTHONPATH=src pytest`.
- Run `cd frontend && npm run build` before recording the dashboard.
- Keep generated bulk data ignored: `data/raw/*`, `data/cache/*`,
  `data/processed/*`, `frontend/dist/`, and dependency folders.
- Do not commit secrets, local logs, `.env` files, `.vercel/`, or runtime PID
  files.
- Default policy: do not commit generated data. Regenerate it locally during the
  demo.
- If judges require frozen evidence artifacts in the repo, explicitly decide
  whether to force-add only these compact files: `data/processed/strategy_comparison_headline.json`,
  `data/processed/strategy_comparison_summary.csv`,
  `data/processed/ml_research_scarcity_summary.csv`,
  `data/processed/ml_research_scarcity_paired_uplift.csv`, and
  `data/processed/future_market_impact_headline.json`.
- Confirm the battery-parameter caveat is stated in the README and demo: METLEN
  `330 MW / 790 MWh` is the public-scale demo preset; SoC band, efficiency,
  initial/terminal SoC, cycle cap, and degradation cost are configurable
  sensitivity parameters.
- Confirm the video distinguishes live daily UI tuning from research evidence:
  changing live daily parameters does not automatically regenerate the 38-day
  research artifacts or headline numbers.

## Final Headline Numbers

Use these exact headline numbers:

| Metric | Value |
| --- | ---: |
| Evaluation window | 2026-03-22 to 2026-04-29 |
| Evaluated Greek DAM days | 38 |
| Scarcity Ensemble realized PnL | EUR 2.968M |
| UK naive baseline realized PnL | EUR 2.571M |
| Uplift | EUR 397k |
| Uplift percentage | 15.45% |
| Daily win rate | 78.9% |

The precise source artifact is `data/processed/strategy_comparison_headline.json`.

## 5-Minute Video Outline

1. `0:00-0:35` Problem: Greek BESS operations under limited local battery
   dispatch history.
2. `0:35-1:10` Data: public HEnEx prices, IPTO/ADMIE system files, weather,
   calendar signals, and explicit battery assumptions.
3. `1:10-2:00` Optimizer: 330 MW / 790 MWh METLEN-scale public demo preset,
   with configurable SoC, efficiency, initial/terminal SoC, degradation, cycle,
   and no-simultaneous-mode constraints.
4. `2:00-3:10` Evidence: Scarcity Ensemble plus optimizer versus UK naive
   baseline on the same Greek delivery days.
5. `3:10-4:10` Dashboard: show dispatch, evidence, and data trace without
   presenting oracle as the benchmark.
6. `4:10-4:45` Future BESS scenarios: describe them as spread-compression
   stress tests, not forecasts.
7. `4:45-5:00` Close: public-data strategy now, retrain and stress-test as more
   Greek BESS data arrives.

## What Not To Say

- Do not say oracle is the benchmark.
- Do not present future BESS scenarios as Greek price forecasts.
- Do not claim the model trained on Greek BESS telemetry.
- Do not call Ridge the final champion.
- Do not headline the conservative scarcity ensemble.
- Do not imply the EUR 397k uplift is guaranteed out of sample.
- Do not imply changing the live daily demo controls has changed the published
  38-day research evidence.
