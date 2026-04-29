# Team Workflow

## Recommended Split

1. Data engineer
   - Own `src/batteryhack/data_sources.py`, data validation, source registry, and sample pulls.
   - Deliver a stable 15-minute feature table with flags for real vs fallback values.

2. Forecasting/research
   - Own `src/batteryhack/forecasting.py`, notebooks/experiments, predictor research, and leakage notes.
   - Deliver baselines first, then stacked/ML experiments only after data contracts are stable.

3. Optimization
   - Own `src/batteryhack/optimizer.py`, `src/batteryhack/backtest.py`, and optimizer tests.
   - Deliver feasible schedules, profit/regret metrics, and sensitivity runs.

4. UI/story
   - Own `frontend/`, dashboard polish, charts, business case, and presentation screenshots.
   - Deliver a live demo path that works even if live data is temporarily unavailable.

## Handoff Contract

Every workstream should expose outputs through code, not screenshots:

- data: a dataframe with `timestamp`, `dam_price_eur_mwh`, load/RES/weather columns,
- forecast: `forecast_price_eur_mwh` plus explanation fields,
- optimization: charge MW, discharge MW, SoC MWh, action labels, profit metrics,
- UI: consumes those outputs without duplicating business logic.

## Daily Sync

Use this agenda:

1. What changed since last sync?
2. Which files are you editing today?
3. What data/source assumptions changed?
4. What demo path is currently stable?
5. What must be frozen before presentation?
