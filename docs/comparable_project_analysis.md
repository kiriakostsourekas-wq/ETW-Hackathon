# Comparable BESS Optimization Repositories

This note records the top three public GitHub projects we inspected and how their mental models map
to the Greek METLEN-scale BESS simulator. The goal is not to vendor their code; it is to make our
modeling choices traceable and to avoid unsupported market assumptions.

## Similarity Rubric

Scores are out of 100 and reflect similarity to our target workflow:

- Public market price signal drives charge/discharge decisions.
- Battery has explicit power, energy, SoC, efficiency, and cycle/throughput constraints.
- Output is an explainable schedule plus revenue/backtest metrics.
- Data scarcity is handled through assumptions, sensitivities, or public-data substitution.
- Market structure is close enough to Greece to inform design without direct label transfer.

## 1. FlexPwr/bess-optimizer - 96/100

Link: https://github.com/FlexPwr/bess-optimizer

Why it is close:

- It optimizes a BESS over 96 quarter-hour intervals.
- It has explicit SoC, charge, discharge, cycle, and market-position constraints.
- It separates day-ahead auction, intraday auction, and intraday continuous decisions.
- It includes a mathematical formulation, which is useful for judge-facing model explanation.

What we embedded:

- Keep 96 intervals as the natural Greek DAM horizon.
- Keep the current Greek model as price-taker DAM, but document intraday as the next market layer.
- Explain the constraint story in the UI and docs instead of presenting the optimizer as a black box.

Caution:

- The German day-ahead formulation includes hourly parity constraints for historical DA products.
  Greek DAM is now 15-minute, so we should not copy those parity constraints.

## 2. gschivley/battery_model - 88/100

Link: https://github.com/gschivley/battery_model

Why it is close:

- It studies day-ahead energy arbitrage with historical NYISO LBMP prices.
- It exposes battery power, energy, round-trip efficiency, and daily discharged throughput.
- It reports dispatch, state of charge, annual revenue, and charging cost.
- It uses a clear notebook/module split that is easy to explain.

What we embedded:

- Keep an oracle DAM mode to estimate achievable value.
- Make efficiency, cycle budget, and degradation visible user inputs.
- Report discharged MWh, equivalent cycles, captured spread, gross arbitrage, degradation cost,
  and net revenue in the dashboard.

Caution:

- The NYISO project is hourly and ex-post. Our Greek simulator must stay at 15-minute resolution
  and keep live-safe forecast inputs separate from post-clearing diagnostics.

## 3. romilandc/battery-storage-optimization-energy-ancillary - 84/100

Link: https://github.com/romilandc/battery-storage-optimization-energy-ancillary

Why it is close:

- It co-optimizes battery value across CAISO energy and ancillary-service products.
- It models mutually exclusive buy/sell decisions, SoC dynamics, transaction fees, and product P&L.
- It uses public ISO-style data access through GridStatus.
- It provides useful plots: prices, SoC, product dispatch, net flow, and cumulative profit.

What we embedded:

- Keep DAM as the implemented Greek product, but explicitly identify ancillary services as a future
  value-stacking layer.
- Preserve product-level thinking in the project architecture, so additional market products can be
  added later without changing the core battery constraints.
- Keep the Research tab honest about what is implemented versus what needs Greek market data.

Caution:

- CAISO nodal energy and reserve products do not map one-to-one to HEnEx DAM. This is an
  architecture reference, not a calibration source.

## Implementation Mapping In This Repo

- `src/batteryhack/optimizer.py`: current MILP/SciPy implementation of the constraint-first battery
  schedule.
- `src/batteryhack/presets.py`: METLEN 330 MW / 790 MWh preset and sensitivity defaults.
- `src/batteryhack/comparable_projects.py`: structured top-three comparable-project metadata.
- `app.py`: interactive demo exposing asset assumptions, oracle/forecast scheduling, sensitivity
  grid, research sources, and comparable-project analysis.

