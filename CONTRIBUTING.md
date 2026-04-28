# Contributing

## Branch Workflow

Create one branch per workstream:

```bash
git switch -c data/henex-ipto-ingestion
git switch -c forecast/price-signals
git switch -c opt/battery-constraints
git switch -c ui/dashboard-story
git switch -c docs/research-pack
```

Before pushing:

```bash
git status --short
PYTHONPATH=src pytest -q
```

Use short commit messages:

```bash
git commit -m "Add HEnEx price parser"
git commit -m "Add battery cycle constraint test"
git commit -m "Document Italy storage analogues"
```

## Pull Requests

Each PR should include:

- what changed,
- how to run it,
- tests or checks performed,
- data sources added or changed,
- known limitations.

Avoid large mixed PRs. Keep data, forecasting, optimization, UI, and docs changes separate where practical.

## Team Ownership

- Data: ingestion, schema, validation, source registry.
- Forecasting: features, baselines, ML experiments, leakage checks.
- Optimization: battery model, constraints, profit metrics, backtests.
- UI/story: Streamlit dashboard, visuals, demo flow, business narrative.

If two people need the same file, agree on the exact section before editing.
