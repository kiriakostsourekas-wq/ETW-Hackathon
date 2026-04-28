# CLAUDE.md

This file is the operating manual for Claude Code, Codex, and any AI-assisted teammate working in this repository.

## Project Mission

Build a presentation-ready prototype for Greek battery optimization under battery-data scarcity. The system should use public market, system, and weather data to schedule utility-scale BESS charging/discharging in the Greek Day-Ahead Market, while clearly explaining economics and constraints.

The correct story is not "we have historical Greek BESS telemetry." We mostly do not. The story is "we can make robust decisions using public price/system/weather signals, transparent battery assumptions, and analogue-market research."

## First Commands

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=src pytest -q
streamlit run app.py
```

Backtest a known public-data day:

```bash
python3 scripts/backtest_recent.py --start 2026-04-22 --end 2026-04-22
```

## Repo Map

- `app.py`: Streamlit dashboard and demo flow.
- `src/batteryhack/data_sources.py`: HEnEx, IPTO, Open-Meteo ingestion and normalization.
- `src/batteryhack/optimizer.py`: battery MILP optimizer.
- `src/batteryhack/forecasting.py`: transparent forecast proxy and ML hooks.
- `src/batteryhack/backtest.py`: backtest helpers.
- `tests/`: optimizer and data-contract tests.
- `docs/`: research notes, source registry, team workflow.

## Collaboration Rules

1. Run `git status --short --branch` before editing.
2. Do not overwrite teammate work. If a file has unrelated edits, work around them or ask.
3. Keep changes scoped to your assigned lane: data, forecasting, optimization, UI/story, or docs.
4. Prefer small branches and small commits with clear messages.
5. Do not commit secrets, API tokens, `.env`, downloaded raw workbooks, logs, pids, caches, or notebook checkpoints.
6. Raw data belongs under `data/raw/` and generated outputs under `data/processed/`; both are gitignored except `.gitkeep`.
7. If adding a source, record it in `docs/research_sources.md` with retrieval notes and whether it is ex-ante usable.
8. If changing optimizer behavior, add or update a test in `tests/`.
9. If changing forecasting features, document leakage risk: what is known before DAM clearing vs only after clearing.
10. If changing UI, verify the app still starts and the default demo date works.

## Data Rules

Use public sources first:

- HEnEx for Greek DAM prices and market publications.
- IPTO/ADMIE for load, RES forecasts, SCADA/system files.
- Open-Meteo for weather.
- ENTSO-E as fallback/cross-check where an API token is available.
- Terna/GME for Italy analogue-market research, not as direct Greek operating labels.

Be explicit about leakage. DAM prices after publication can be used for next-day dispatch optimization. Forecasting experiments must only use signals available before the forecast decision time.

## Battery Assumptions

Default demo assumptions should remain transparent and editable:

- Small demo: 10 MW / 20 MWh or 20 MW / 80 MWh.
- METLEN-scale sensitivity: 330 MW / 790 MWh, about 2.39h.
- Round-trip efficiency: 85% base case, 90% optimistic sensitivity.
- SoC operating band: 10-90% unless justified otherwise.
- Cycle/degradation assumptions must be sensitivity parameters, not claimed facts.

Use NREL ATB and Terna storage studies as external justification for duration, efficiency, cycle, lifetime, and cost ranges.

## AI Agent Behavior

When using this repo as an AI assistant:

- Start by reading this file, `README.md`, and the files relevant to the task.
- Prefer existing architecture over new abstractions.
- Use `rg` for search.
- Use `apply_patch` for manual edits when available.
- Run focused tests before finishing.
- In final responses, report changed files, verification run, and any remaining risk.

## Presentation Standard

Every technical claim used in slides should be traceable to a source or to code output. Do not overclaim forecast accuracy. The strongest winning angle is transparent, constraint-aware economic decision-making under Greek BESS data scarcity.
